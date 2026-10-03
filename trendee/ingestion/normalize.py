"""Normalize raw PDF staging records into retrieval-ready evidence chunks.

The raw parser intentionally preserves many PDF text blocks. This stage removes
repeated boilerplate, merges blocks within a physical page, and links every
retrievable text chunk to the rendered full-page visual asset for citation/UI.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any


DEFAULT_TARGET_CHARS = 700
DEFAULT_MAX_CHARS = 1000
DEFAULT_MIN_TEXT_CHARS = 30


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(text: str) -> str:
    return "\n".join(
        re.sub(r"[ \t\u00a0]+", " ", line).strip()
        for line in str(text).replace("\r", "").splitlines()
        if line.strip()
    )


def _boilerplate_key(text: str) -> str:
    return re.sub(r"\s+", "", _clean(text)).lower()


def _is_trivial(text: str) -> bool:
    value = _clean(text)
    if not value:
        return True
    if re.fullmatch(r"[\d\s./_-]{1,12}", value):
        return True
    if len(value) <= 2:
        return True
    return False


def _bbox_union(boxes: list[list[float]]) -> list[float] | None:
    boxes = [box for box in boxes if isinstance(box, list) and len(box) == 4]
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _split_long_text(text: str, max_chars: int) -> list[str]:
    text = _clean(text)
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            segment = text[start:end]
            boundaries = [m.end() for m in re.finditer(r"[。！？；;\n]", segment)]
            good = [x for x in boundaries if x >= max_chars // 2]
            if good:
                end = start + good[-1]
        value = text[start:end].strip()
        if value:
            parts.append(value)
        start = end
    return parts


def _merge_blocks(
    blocks: list[dict[str, Any]],
    target_chars: int,
    max_chars: int,
) -> list[tuple[str, list[str], list[list[float]]]]:
    """Merge adjacent raw blocks without crossing a physical page."""
    merged: list[tuple[str, list[str], list[list[float]]]] = []
    current_text: list[str] = []
    current_ids: list[str] = []
    current_boxes: list[list[float]] = []

    def flush() -> None:
        nonlocal current_text, current_ids, current_boxes
        if current_text:
            merged.append(("\n".join(current_text), current_ids[:], current_boxes[:]))
        current_text, current_ids, current_boxes = [], [], []

    for block in blocks:
        text = _clean(block["content"])
        if not text:
            continue
        for part in _split_long_text(text, max_chars):
            projected = len("\n".join(current_text + [part]))
            if current_text and projected > max_chars:
                flush()
            current_text.append(part)
            current_ids.append(block["id"])
            if block.get("bbox"):
                current_boxes.append(block["bbox"])
            if len("\n".join(current_text)) >= target_chars:
                flush()
    flush()
    return merged


def normalize_staging(
    staging_path: str | Path,
    output_path: str | Path | None = None,
    target_chars: int = DEFAULT_TARGET_CHARS,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS,
) -> dict[str, Any]:
    """Create retrieval-ready chunks linked to full-page visual assets."""
    staging_path = Path(staging_path).expanduser().resolve()
    if not staging_path.exists():
        raise FileNotFoundError(f"Missing staging file: {staging_path}")
    if target_chars <= 0 or max_chars < target_chars:
        raise ValueError("Require 0 < target_chars <= max_chars")

    records = [
        json.loads(line)
        for line in staging_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError("Staging file is empty")

    text_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    page_asset: dict[int, dict[str, Any]] = {}
    for record in records:
        page = int(record["page"])
        if record.get("modality") == "text":
            text_by_page[page].append(record)
        elif record.get("modality") == "page_image":
            page_asset[page] = record

    page_count = max({int(record["page"]) for record in records})
    occurrences: Counter[str] = Counter()
    example_by_key: dict[str, str] = {}
    for page, blocks in text_by_page.items():
        seen_on_page: set[str] = set()
        for block in blocks:
            text = _clean(block.get("content", ""))
            key = _boilerplate_key(text)
            if not key or len(text) > 120:
                continue
            seen_on_page.add(key)
            example_by_key.setdefault(key, text)
        occurrences.update(seen_on_page)

    repeat_threshold = max(3, math.ceil(page_count * 0.25))
    boilerplate = {
        key for key, count in occurrences.items()
        if count >= repeat_threshold
    }

    normalized: list[dict[str, Any]] = []
    removed_trivial = 0
    removed_boilerplate = 0
    sparse_pages: list[int] = []
    pages_with_assets = 0

    for page in range(1, page_count + 1):
        raw_blocks = text_by_page.get(page, [])
        kept: list[dict[str, Any]] = []
        for block in raw_blocks:
            text = _clean(block.get("content", ""))
            if _is_trivial(text):
                removed_trivial += 1
                continue
            key = _boilerplate_key(text)
            if key in boilerplate:
                removed_boilerplate += 1
                continue
            kept.append({**block, "content": text})

        asset = page_asset.get(page)
        asset_path = asset.get("asset_path") if asset else None
        if asset_path:
            pages_with_assets += 1

        total_text = sum(len(block["content"]) for block in kept)
        if total_text < min_text_chars:
            sparse_pages.append(page)
            continue

        chunks = _merge_blocks(kept, target_chars, max_chars)
        heading = next(
            (str(block.get("heading", "")).strip() for block in kept if str(block.get("heading", "")).strip()),
            f"PDF 第{page}页",
        )
        source = kept[0]
        for number, (content, source_ids, boxes) in enumerate(chunks, 1):
            normalized.append({
                "id": f"pdf-p{page:03d}-c{number:02d}",
                "source_id": source["source_id"],
                "source_name": source["source_name"],
                "source_sha256": source["source_sha256"],
                "page": page,
                "modality": "text",
                "heading": heading[:160],
                "content": content,
                "asset_path": asset_path,
                "bbox": _bbox_union(boxes),
                "text_length": len(content),
                "created_at": _now_utc(),
                "metadata": {
                    "stage": "normalized_text_chunk",
                    "source_block_ids": source_ids,
                    "page_asset_linked": bool(asset_path),
                    "visual_evidence_type": "full_page_render" if asset_path else None,
                },
            })

    output_path = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else staging_path.with_name("evidence_normalized.jsonl")
    )
    temporary = output_path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in normalized:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(output_path)

    manifest = {
        "created_at": _now_utc(),
        "input_file": staging_path.name,
        "output_file": output_path.name,
        "page_count": page_count,
        "raw_text_block_count": sum(len(v) for v in text_by_page.values()),
        "normalized_chunk_count": len(normalized),
        "pages_with_visual_assets": pages_with_assets,
        "sparse_text_pages": sparse_pages,
        "removed_trivial_blocks": removed_trivial,
        "removed_repeated_boilerplate_blocks": removed_boilerplate,
        "boilerplate_patterns_detected": len(boilerplate),
        "boilerplate_examples": [example_by_key[key] for key in sorted(boilerplate)[:20]],
        "target_chars": target_chars,
        "max_chars": max_chars,
        "next_stage": "ocr_sparse_pages_then_embedding",
    }
    manifest_path = output_path.with_name("normalization_manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
