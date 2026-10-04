"""Adapters for Elasticsearch evidence returned to RAG/grounding layers."""
from __future__ import annotations

from typing import Any


def adapt_pdf_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Normalize an Elasticsearch evidence hit to the grounding contract."""
    return {
        "id": hit["chunk_id"],
        "text": hit.get("content", ""),
        "source": hit.get("source_name") or "unknown_source",
        "page": hit.get("page"),
        "url": None,
        "heading": hit.get("heading", ""),
        "captured_at_utc": hit.get("created_at"),
        "asset_path": hit.get("asset_path"),
        "score": hit.get("reranker_score", hit.get("rrf_score")),
        "pre_rerank_rank": hit.get("pre_rerank_rank"),
        "reranker_score": hit.get("reranker_score"),
        "reranker_score_raw": hit.get("reranker_score_raw"),
        "rrf_score": hit.get("rrf_score"),
        "retrieval_channels": hit.get("retrieval_channels", {}),
        "query_variants": hit.get("query_variants", []),
        "rank": hit.get("rank"),
    }
