"""Deterministic evidence-context construction."""
from __future__ import annotations

from typing import Any, Sequence


def build_context(hits: Sequence[dict[str, Any]], max_chars: int = 8000) -> dict[str, Any]:
    parts: list[str] = []
    selected: list[str] = []
    total = 0
    for hit in hits:
        block = (
            f"[{hit['id']}] 来源={hit.get('source')}; 页码={hit.get('page')}; "
            f"小节={hit.get('heading')}\n{hit.get('text', '')}"
        ).strip()
        if selected and total + len(block) > max_chars:
            continue
        if not selected and len(block) > max_chars:
            block = block[:max_chars]
        parts.append(block)
        selected.append(hit["id"])
        total += len(block)
    return {
        "text": "\n\n".join(parts),
        "evidence_ids": selected,
        "evidence_count": len(selected),
        "context_chars": total,
        "max_chars": max_chars,
    }
