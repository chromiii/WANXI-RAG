"""Context assembly for Project 1 RAG.

Selection, safety filtering and deduplication happen before this module. The
context builder only serializes the final evidence set with provenance and risk
metadata for the Writer.
"""
from __future__ import annotations

from typing import Any, Sequence


def build_context(
    hits: Sequence[dict[str, Any]],
    max_chars: int = 8000,
) -> dict[str, Any]:
    parts: list[str] = []
    selected: list[str] = []
    total = 0

    for hit in hits:
        flags = ",".join(hit.get("risk_flags", [])) or "none"
        block = (
            f"[{hit['id']}] 来源={hit.get('source')}; 页码={hit.get('page')}; "
            f"evidence_type={hit.get('evidence_type', 'factual')}; "
            f"risk_flags={flags}; 小节={hit.get('heading')}\n"
            f"{hit.get('text', '')}"
        ).strip()

        if selected and total + len(block) > max_chars:
            break
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
