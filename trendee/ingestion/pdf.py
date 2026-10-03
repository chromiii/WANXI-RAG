"""Page-aware PDF ingestion for text plus full-page visual evidence.

For slide-style brochures, the meaningful visual is often the composed PDF page
(text + vector graphics + icons), not any one embedded raster image. Therefore
the default visual asset is a rendered full page. Embedded image extraction is
optional and disabled by default.

No external model/API is called here. All generated assets remain in the private
runtime data directory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pymupdf


DEFAULT_RENDER_SCALE = 2.0
MIN_EMBEDDED_IMAGE_PAGE_RATIO = 0.08


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize(text: str) -> str:
    return "\n".join(
        re.sub(r"[ \t\u00a0]+", " ", line).strip()
        for line in text.replace("\r", "").splitlines()
        if line.strip()
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    source_id: str
    source_name: str
    source_sha256: str
    page: int
    modality: str
    heading: str
    content: str
    asset_path: str | None = None
    bbox: list[float] | None = None
    text_length: int = 0
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _page_heading(text_blocks: list[tuple[list[float], str]]) -> str:
    for _, text in text_blocks:
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if first:
            return first[:160]
    return "页面内容"


def _text_blocks(page: pymupdf.Page) -> list[tuple[list[float], str]]:
    result: list[tuple[list[float], str]] = []
    for block in page.get_text("blocks", sort=True):
        if len(block) >= 7 and block[6] != 0:
            continue
        text = _normalize(str(block[4]))
        if not text:
            continue
        result.append(([round(float(x), 2) for x in block[:4]], text))
    return result


def _render_page(
    page: pymupdf.Page,
    page_number: int,
    pages_dir: Path,
    scale: float,
) -> tuple[Path, int, int]:
    if scale <= 0:
        raise ValueError("render_scale must be positive")
    target = pages_dir / f"p{page_number:03d}.png"
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(scale, scale),
        alpha=False,
    )
    pix.save(target)
    return target, int(pix.width), int(pix.height)


def extract_pdf_evidence(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    render_pages: bool = True,
    render_scale: float = DEFAULT_RENDER_SCALE,
    include_embedded_images: bool = False,
    min_embedded_image_page_ratio: float = MIN_EMBEDDED_IMAGE_PAGE_RATIO,
) -> dict[str, Any]:
    """Extract text blocks and page-render visual evidence from a PDF.

    Private runtime output:
      - evidence_staging.jsonl
      - ingestion_manifest.json
      - assets/pages/pNNN.png
      - optionally assets/embedded/<sha>.<ext>

    Page renders are the primary visual evidence because slide-style PDFs are
    commonly composed from text, vector shapes, and small icons. Extracting
    embedded raster objects alone loses that composition.

    No embeddings, OCR, vision model, or network calls happen here.
    """
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing PDF: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("ingest currently accepts a PDF file")

    output_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else pdf_path.parent
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    assets_dir = output_dir / "assets"
    pages_dir = assets_dir / "pages"
    embedded_dir = assets_dir / "embedded"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if render_pages:
        pages_dir.mkdir(parents=True, exist_ok=True)
    if include_embedded_images:
        embedded_dir.mkdir(parents=True, exist_ok=True)

    source_sha256 = _sha256_file(pdf_path)
    source_id = "wanxi-brand-" + source_sha256[:12]
    created_at = _now_utc()
    records: list[EvidenceRecord] = []

    rendered_page_count = 0
    embedded_evidence_count = 0
    skipped_embedded_occurrences = 0
    unique_embedded_assets: set[str] = set()

    with pymupdf.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            blocks = _text_blocks(page)
            heading = _page_heading(blocks)
            page_text = _normalize(page.get_text("text", sort=True))
            page_context = page_text[:5000]

            for number, (bbox, text) in enumerate(blocks, 1):
                records.append(
                    EvidenceRecord(
                        id=f"pdf-p{page_number:03d}-t{number:02d}",
                        source_id=source_id,
                        source_name=pdf_path.name,
                        source_sha256=source_sha256,
                        page=page_number,
                        modality="text",
                        heading=heading,
                        content=text,
                        bbox=bbox,
                        text_length=len(text),
                        created_at=created_at,
                        metadata={"stage": "raw_text_block"},
                    )
                )

            if render_pages:
                asset_path, width, height = _render_page(
                    page,
                    page_number,
                    pages_dir,
                    render_scale,
                )
                relative_asset = asset_path.relative_to(output_dir).as_posix()
                page_content = (
                    f"第{page_number}页完整页面视觉证据。页面标题：{heading}。"
                    f"页面文本：{page_context or '该页文本层为空。'}"
                )
                records.append(
                    EvidenceRecord(
                        id=f"pdf-p{page_number:03d}-page",
                        source_id=source_id,
                        source_name=pdf_path.name,
                        source_sha256=source_sha256,
                        page=page_number,
                        modality="page_image",
                        heading=heading,
                        content=page_content,
                        asset_path=relative_asset,
                        bbox=[
                            0.0,
                            0.0,
                            round(float(page.rect.width), 2),
                            round(float(page.rect.height), 2),
                        ],
                        text_length=len(page_content),
                        created_at=created_at,
                        metadata={
                            "stage": "full_page_render",
                            "render_scale": render_scale,
                            "pixel_width": width,
                            "pixel_height": height,
                            "description_method": "page_heading_plus_full_page_text",
                            "ocr_applied": False,
                            "vision_model_applied": False,
                        },
                    )
                )
                rendered_page_count += 1

            if include_embedded_images:
                page_area = max(float(page.rect.width * page.rect.height), 1.0)
                image_number = 0
                for image in page.get_images(full=True):
                    xref = int(image[0])
                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue
                    extracted = document.extract_image(xref)
                    image_bytes = extracted.get("image", b"")
                    if not image_bytes:
                        continue

                    for rect in rects:
                        area_ratio = float(rect.width * rect.height) / page_area
                        if area_ratio < min_embedded_image_page_ratio:
                            skipped_embedded_occurrences += 1
                            continue

                        extension = str(extracted.get("ext") or "bin").lower()
                        image_sha256 = _sha256_bytes(image_bytes)
                        asset_name = f"{image_sha256[:20]}.{extension}"
                        asset_path = embedded_dir / asset_name
                        if not asset_path.exists():
                            asset_path.write_bytes(image_bytes)
                        unique_embedded_assets.add(image_sha256)

                        image_number += 1
                        relative_asset = asset_path.relative_to(output_dir).as_posix()
                        content = (
                            f"第{page_number}页较大内嵌图片。页面标题：{heading}。"
                            f"同页文本：{page_context or '该页文本层为空。'}"
                        )
                        records.append(
                            EvidenceRecord(
                                id=f"pdf-p{page_number:03d}-img{image_number:02d}",
                                source_id=source_id,
                                source_name=pdf_path.name,
                                source_sha256=source_sha256,
                                page=page_number,
                                modality="embedded_image",
                                heading=heading,
                                content=content,
                                asset_path=relative_asset,
                                bbox=[
                                    round(float(rect.x0), 2),
                                    round(float(rect.y0), 2),
                                    round(float(rect.x1), 2),
                                    round(float(rect.y1), 2),
                                ],
                                text_length=len(content),
                                created_at=created_at,
                                metadata={
                                    "stage": "embedded_image_context",
                                    "xref": xref,
                                    "asset_sha256": image_sha256,
                                    "page_area_ratio": round(area_ratio, 6),
                                    "description_method": "page_heading_plus_full_page_text",
                                    "ocr_applied": False,
                                    "vision_model_applied": False,
                                },
                            )
                        )
                        embedded_evidence_count += 1

        page_count = len(document)

    staging_path = output_dir / "evidence_staging.jsonl"
    temporary = staging_path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    temporary.replace(staging_path)

    text_count = sum(record.modality == "text" for record in records)
    page_image_count = sum(record.modality == "page_image" for record in records)
    manifest = {
        "source_id": source_id,
        "source_name": pdf_path.name,
        "source_sha256": source_sha256,
        "created_at": created_at,
        "page_count": page_count,
        "evidence_count": len(records),
        "text_evidence_count": text_count,
        "page_image_evidence_count": page_image_count,
        "embedded_image_evidence_count": embedded_evidence_count,
        "rendered_page_count": rendered_page_count,
        "unique_embedded_asset_count": len(unique_embedded_assets),
        "skipped_embedded_image_occurrences": skipped_embedded_occurrences,
        "render_scale": render_scale,
        "embedded_images_enabled": include_embedded_images,
        "staging_file": staging_path.name,
        "page_assets_dir": pages_dir.relative_to(output_dir).as_posix() if render_pages else None,
        "network_calls": 0,
        "embedding_status": "not_started",
        "ocr_status": "not_started",
    }
    manifest_path = output_dir / "ingestion_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
