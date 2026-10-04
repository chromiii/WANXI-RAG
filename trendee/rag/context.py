"""Context assembly for Project 1 RAG."""
from __future__ import annotations

from typing import Any, Sequence

from .evidence_policy import evaluate_evidence, selected_ids


def build_context(
    hits: Sequence[dict[str, Any]],
    topic: str = "",
    retrieval_intent: str = "",
    max_chars: int = 8000,
) -> dict[str, Any]:
    policy = evaluate_evidence(
        hits,
        topic=topic,
        retrieval_intent=retrieval_intent,
    )
    allowed = set(selected_ids(policy))

    parts: list[str] = []
    selected: list[str] = []
    total = 0

    # Preserve policy priority order rather than raw retrieval order.
    by_id = {str(hit.get("id")): hit for hit in hits}
    for decision in policy["decisions"]:
        evidence_id = decision.get("id")
        if evidence_id not in allowed:
            continue
        hit = by_id.get(str(evidence_id))
        if not hit:
            continue
        block = (
            f"[{hit['id']}] 来源={hit.get('source')}; 页码={hit.get('page')}; "
            f"priority={decision['priority']}; evidence_type={decision['evidence_type']}; "
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
        "focus": policy["focus"],
        "priority_counts": policy["priority_counts"],
        "type_counts": policy["type_counts"],
        "evidence_selection": policy["decisions"],
        "excluded_evidence": [
            item for item in policy["decisions"]
            if item["priority"] == "excluded"
        ],
        "low_priority_evidence": [
            item for item in policy["decisions"]
            if item["priority"] == "low_priority"
        ],
    }
