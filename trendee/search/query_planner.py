"""Query planning for multi-query RAG retrieval."""
from __future__ import annotations

from typing import Any


MAX_EXPANSIONS = 3


def passthrough_plan(query: str, reason: str = "offline_passthrough") -> dict[str, Any]:
    query = query.strip()
    return {
        "original_query": query,
        "rewrite_needed": False,
        "intent": "unspecified",
        "retrieval_queries": [query],
        "reason": reason,
    }


def validate_query_plan(value: dict[str, Any], original_query: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("query plan must be a JSON object")
    if not isinstance(value.get("rewrite_needed"), bool):
        raise ValueError("query_plan.rewrite_needed must be boolean")
    if not isinstance(value.get("intent"), str) or not value["intent"].strip():
        raise ValueError("query_plan.intent is required")
    queries = value.get("retrieval_queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("query_plan.retrieval_queries must be a non-empty list")
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
    # The user's original wording is always preserved as the first retrieval
    # channel. Rewrites expand recall; they never replace user intent.
    expansions = [q for q in cleaned if q != original][:MAX_EXPANSIONS]
    return {
        "original_query": original,
        "rewrite_needed": bool(value["rewrite_needed"] and expansions),
        "intent": value["intent"].strip()[:80],
        "retrieval_queries": [original, *expansions],
        "reason": str(value.get("reason", "")).strip()[:400],
    }
