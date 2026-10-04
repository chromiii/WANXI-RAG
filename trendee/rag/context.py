"""Deterministic evidence selection and context construction."""
from __future__ import annotations

import re
from typing import Any, Sequence


def generation_exclusion_reason(hit: dict[str, Any], topic: str) -> str | None:
    """Keep risky scenario/proposal evidence out of unrelated generation context."""
    heading = str(hit.get("heading", ""))
    text = str(hit.get("text", ""))
    combined = heading + "\n" + text

    if re.search(r"设想|假设场景|概念方案", combined):
        match = re.search(r"面向\s*([^\n：:]{2,30}?)\s*的.*?设想", heading)
        subject = match.group(1).strip() if match else ""
        if not subject or subject not in topic:
            return "hypothetical_evidence_not_requested"
    return None


def select_generation_evidence(
    hits: Sequence[dict[str, Any]],
    topic: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for hit in hits:
        reason = generation_exclusion_reason(hit, topic)
        if reason:
            excluded.append({
                "id": hit.get("id"),
                "page": hit.get("page"),
                "heading": hit.get("heading"),
                "reason": reason,
            })
        else:
            selected.append(hit)

    if not selected and hits:
        return list(hits), []
    return selected, excluded


def build_context(
    hits: Sequence[dict[str, Any]],
    topic: str = "",
    max_chars: int = 8000,
) -> dict[str, Any]:
    selected_hits, excluded = select_generation_evidence(hits, topic)
    parts: list[str] = []
    selected_ids: list[str] = []
    total = 0

    for hit in selected_hits:
        block = (
            f"[{hit['id']}] 来源={hit.get('source')}; 页码={hit.get('page')}; "
            f"小节={hit.get('heading')}\n{hit.get('text', '')}"
        ).strip()
        if selected_ids and total + len(block) > max_chars:
            continue
        if not selected_ids and len(block) > max_chars:
            block = block[:max_chars]
        parts.append(block)
        selected_ids.append(hit["id"])
        total += len(block)

    return {
        "text": "\n\n".join(parts),
        "evidence_ids": selected_ids,
        "evidence_count": len(selected_ids),
        "context_chars": total,
        "max_chars": max_chars,
        "excluded_evidence": excluded,
    }
