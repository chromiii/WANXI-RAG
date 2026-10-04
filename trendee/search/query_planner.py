"""Query planning for multi-query RAG retrieval."""
from __future__ import annotations

from typing import Any


MAX_EXPANSIONS = 3
STRATEGIES = {"passthrough", "rewrite", "expand", "decompose"}


def passthrough_plan(query: str, reason: str = "offline_passthrough") -> dict[str, Any]:
    query = query.strip()
    return {
        "original_query": query,
        "strategy": "passthrough",
        "rewrite_needed": False,
        "intent": "unspecified",
        "retrieval_queries": [query],
        "reason": reason,
    }


def validate_query_plan(value: dict[str, Any], original_query: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("query plan must be a JSON object")

    strategy = str(value.get("strategy", "")).strip().lower()
    if strategy not in STRATEGIES:
        raise ValueError(
            "query_plan.strategy must be passthrough, rewrite, expand or decompose"
        )

    if not isinstance(value.get("rewrite_needed"), bool):
        raise ValueError("query_plan.rewrite_needed must be boolean")
    if not isinstance(value.get("intent"), str) or not value["intent"].strip():
        raise ValueError("query_plan.intent is required")

    queries = value.get("retrieval_queries")
    if not isinstance(queries, list):
        raise ValueError("query_plan.retrieval_queries must be a list")

    cleaned: list[str] = []
    for item in queries:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("retrieval queries must be non-empty strings")
        text = item.strip()
        if len(text) > 300:
            raise ValueError("retrieval query is too long")
        if text not in cleaned:
            cleaned.append(text)

    original = original_query.strip()
    expansions = [q for q in cleaned if q != original][:MAX_EXPANSIONS]

    if strategy == "passthrough":
        expansions = []
    if strategy in {"rewrite", "expand", "decompose"} and not expansions:
        raise ValueError(f"query_plan.strategy={strategy} requires at least one extra query")

    return {
        "original_query": original,
        "strategy": strategy,
        "rewrite_needed": bool(strategy != "passthrough" and expansions),
        "intent": value["intent"].strip()[:120],
        # Original wording is always the first retrieval channel.
        "retrieval_queries": [original, *expansions],
        "reason": str(value.get("reason", "")).strip()[:500],
    }
