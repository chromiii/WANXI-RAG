"""Lightweight post-retrieval processing for Project 1 RAG.

Responsibilities are intentionally narrower than reranking:
- attach evidence metadata/risk flags;
- apply deterministic hard-safety filters;
- remove near-duplicate chunks;
- keep the original reranker order for final Top-N;
- enforce a context character budget.

The processor never re-scores relevance.
"""
from __future__ import annotations

import re
from typing import Any, Sequence


def _text(hit: dict[str, Any]) -> str:
    return str(hit.get("text") or hit.get("content") or "").strip()


def _heading(hit: dict[str, Any]) -> str:
    return str(hit.get("heading") or "").strip()


def evidence_metadata(hit: dict[str, Any]) -> dict[str, Any]:
    """Describe source semantics without changing retrieval rank."""
    heading = _heading(hit)
    text = _text(hit)
    combined = heading + "\n" + text
    heading_lower = heading.lower()

    if re.search(r"设想|假设场景|概念方案|拟议|模拟场景", heading, re.I):
        primary_type = "hypothetical"
    elif re.search(r"客户案例|合作案例|项目经验|合作客户|已服务", heading, re.I):
        primary_type = "case"
    elif re.search(r"媒体|报道|新闻|专访|采访|获奖|奖项|荣誉|入选", heading, re.I):
        primary_type = "media"
    elif re.search(r"创始人|CEO|CTO|核心团队|团队成员|顾问|专家团队", heading, re.I):
        primary_type = "profile"
    elif re.search(r"数据|效果|指标|增长|覆盖率|推荐率|转化率", heading, re.I):
        primary_type = "metric"
    else:
        primary_type = "factual"

    flags: list[str] = []
    checks = [
        ("hypothetical", r"设想|假设场景|概念方案|拟议|模拟场景"),
        ("marketing_claim", r"行业.{0,6}标杆|领先|首创|唯一|第一|长期记忆|深度记忆"),
        ("metric_claim", r"\d+(?:\.\d+)?[%％]|增长率|提升率|覆盖率|推荐率|转化率"),
        ("media_reference", r"媒体|报道|新闻|专访|采访"),
        ("profile_reference", r"创始人|CEO|CTO|核心团队|团队成员"),
        ("case_reference", r"客户案例|合作案例|项目经验|合作客户|已服务"),
    ]
    for name, pattern in checks:
        if re.search(pattern, combined, re.I):
            flags.append(name)

    return {
        "primary_type": primary_type,
        "risk_flags": flags,
    }


def _hypothetical_subject(hit: dict[str, Any]) -> str:
    combined = _heading(hit) + "\n" + _text(hit)
    match = re.search(r"面向\s*([^\n：:，,]{2,30}?)\s*的.{0,20}(?:设想|方案)", combined)
    return match.group(1).strip() if match else ""


def hard_filter_reason(hit: dict[str, Any], topic: str) -> str | None:
    metadata = evidence_metadata(hit)
    if "hypothetical" in metadata["risk_flags"]:
        subject = _hypothetical_subject(hit)
        explicitly_requested = (
            "设想" in topic
            or "假设" in topic
            or (subject and subject.lower() in topic.lower())
        )
        if not explicitly_requested:
            return "unrequested_hypothetical"
    return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+|[，。！？；：、,.!?;:\-—_()（）\[\]【】"'“”‘’]", "", text).lower()


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    value = _normalize(text)
    if len(value) < n:
        return {value} if value else set()
    return {value[i:i+n] for i in range(len(value) - n + 1)}


def near_duplicate(a: dict[str, Any], b: dict[str, Any], threshold: float = 0.82) -> bool:
    ta = _normalize(_text(a))
    tb = _normalize(_text(b))
    if not ta or not tb:
        return False
    if ta == tb:
        return True

    # Same page/heading gets a slightly more permissive overlap check because
    # PDF normalization can split neighboring blocks with repeated lead text.
    same_location = (
        a.get("page") == b.get("page")
        and _heading(a)
        and _heading(a) == _heading(b)
    )
    grams_a = _char_ngrams(ta)
    grams_b = _char_ngrams(tb)
    if not grams_a or not grams_b:
        return False
    score = len(grams_a & grams_b) / len(grams_a | grams_b)
    return score >= (0.70 if same_location else threshold)


def process_retrieved_hits(
    hits: Sequence[dict[str, Any]],
    *,
    topic: str,
    top_n: int = 6,
    max_chars: int = 8000,
) -> dict[str, Any]:
    """Filter/deduplicate reranked hits while preserving their order."""
    if top_n < 1:
        raise ValueError("top_n must be >= 1")

    annotated: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []

    for raw in hits:
        item = dict(raw)
        meta = evidence_metadata(item)
        item["evidence_type"] = meta["primary_type"]
        item["risk_flags"] = meta["risk_flags"]

        reason = hard_filter_reason(item, topic)
        if reason:
            item["postprocess_status"] = "filtered"
            item["postprocess_reason"] = reason
            annotated.append(item)
            continue

        duplicate_of = None
        for existing in kept:
            if near_duplicate(item, existing):
                duplicate_of = existing.get("id")
                break
        if duplicate_of:
            item["postprocess_status"] = "deduplicated"
            item["postprocess_reason"] = f"near_duplicate_of:{duplicate_of}"
            annotated.append(item)
            continue

        kept.append(item)
        annotated.append(item)

    selected: list[dict[str, Any]] = []
    total_chars = 0
    for item in kept:
        if len(selected) >= top_n:
            item["postprocess_status"] = "not_selected"
            item["postprocess_reason"] = "outside_final_top_n"
            continue

        block_chars = len(_heading(item)) + len(_text(item)) + 120
        if selected and total_chars + block_chars > max_chars:
            item["postprocess_status"] = "budget_dropped"
            item["postprocess_reason"] = "context_budget_exceeded"
            continue

        item["postprocess_status"] = "selected"
        item["postprocess_reason"] = "kept_in_reranker_order"
        item["selected_rank"] = len(selected) + 1
        selected.append(item)
        total_chars += block_chars

    # annotated contains copies created before final status assignment for kept
    # items. Refresh by id so debug/log output reflects final decisions.
    final_by_id = {str(item.get("id")): item for item in kept}
    refreshed: list[dict[str, Any]] = []
    for item in annotated:
        replacement = final_by_id.get(str(item.get("id")))
        if replacement is not None and item.get("postprocess_status") not in {"filtered", "deduplicated"}:
            refreshed.append(dict(replacement))
        else:
            refreshed.append(item)

    counts: dict[str, int] = {}
    for item in refreshed:
        status = str(item.get("postprocess_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1

    return {
        "selected": selected,
        "all_hits": refreshed,
        "status_counts": counts,
        "selected_ids": [item.get("id") for item in selected],
        "context_chars_estimate": total_chars,
        "max_chars": max_chars,
        "top_n": top_n,
    }
