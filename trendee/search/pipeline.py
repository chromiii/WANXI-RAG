"""Dense indexing and hybrid retrieval pipeline for normalized evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .embeddings import EmbeddingSettings, LocalSentenceEmbedder, embedding_text
from .elasticsearch_store import ElasticsearchEvidenceStore, ElasticsearchSettings
from .reranker import DEFAULT_RERANKER, LocalReranker, RerankerSettings


def load_normalized_records(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Missing normalized evidence: {path}")
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError("Normalized evidence is empty")
    required = {"id", "source_id", "source_name", "source_sha256", "page", "content", "created_at"}
    for record in records:
        missing = required.difference(record)
        if missing:
            raise ValueError(f"Normalized evidence {record.get('id', '<unknown>')} missing: {sorted(missing)}")
    return records


def build_dense_index(
    evidence_path: str | Path,
    elasticsearch_url: str,
    index_name: str,
    model_name: str = "BAAI/bge-m3",
    batch_size: int = 8,
    device: str | None = None,
) -> dict[str, Any]:
    records = load_normalized_records(evidence_path)
    embedder = LocalSentenceEmbedder(
        EmbeddingSettings(
            model_name=model_name,
            batch_size=batch_size,
            device=device,
        )
    )
    texts = [embedding_text(record) for record in records]
    embeddings = embedder.encode(texts)

    store = ElasticsearchEvidenceStore(
        ElasticsearchSettings(url=elasticsearch_url, index_name=index_name)
    )
    try:
        if not store.ping():
            raise RuntimeError(
                "Elasticsearch is unavailable. Start it with: docker compose up -d elasticsearch"
            )
        result = store.bulk_index(records, embeddings, replace_source=True)
        result.update({
            "model": model_name,
            "embedding_dimensions": len(embeddings[0]) if embeddings else 0,
            "record_count": len(records),
            "network_content_uploads": 0,
        })
        return result
    finally:
        store.close()


def hybrid_query(
    query: str,
    elasticsearch_url: str,
    index_name: str,
    model_name: str = "BAAI/bge-m3",
    top_k: int = 6,
    candidate_k: int = 20,
    device: str | None = None,
    rerank: bool = False,
    reranker_model: str = DEFAULT_RERANKER,
    rerank_candidates: int = 12,
) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    embedder = LocalSentenceEmbedder(
        EmbeddingSettings(
            model_name=model_name,
            batch_size=1,
            device=device,
            local_files_only=True,
        )
    )
    query_vector = embedder.encode_one(query)

    store = ElasticsearchEvidenceStore(
        ElasticsearchSettings(url=elasticsearch_url, index_name=index_name)
    )
    try:
        if not store.ping():
            raise RuntimeError(
                "Elasticsearch is unavailable. Start it with: docker compose up -d elasticsearch"
            )
        retrieval_k = max(top_k, rerank_candidates) if rerank else top_k
        candidates = store.hybrid_search(
            query=query,
            query_vector=query_vector,
            top_k=retrieval_k,
            candidate_k=max(candidate_k, retrieval_k),
        )
    finally:
        store.close()

    if not rerank:
        result = candidates[:top_k]
        for rank, item in enumerate(result, 1):
            item["rank"] = rank
        return result

    reranker = LocalReranker(
        RerankerSettings(
            model_name=reranker_model,
            device=device or "auto",
            allow_download=True,
        )
    )
    return reranker.rerank(query, candidates, top_k=top_k)
