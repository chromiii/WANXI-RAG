"""Dense indexing and hybrid retrieval pipeline for normalized evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .embeddings import EmbeddingSettings, LocalSentenceEmbedder, embedding_text
from .elasticsearch_store import ElasticsearchEvidenceStore, ElasticsearchSettings, rrf_fuse
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
            raise ValueError(
                f"Normalized evidence {record.get('id', '<unknown>')} missing: {sorted(missing)}"
            )
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


class HybridRetriever:
    """Reusable local retriever for CLI/API/Web requests.

    The embedding model and reranker are lazy-loaded once per process, so the
    local web demo does not reload model weights on every request.
    """

    def __init__(
        self,
        elasticsearch_url: str,
        index_name: str,
        model_name: str = "BAAI/bge-m3",
        reranker_model: str = DEFAULT_RERANKER,
        device: str | None = None,
    ):
        self.model_name = model_name
        self.reranker_model = reranker_model
        self.device = device
        self.store = ElasticsearchEvidenceStore(
            ElasticsearchSettings(url=elasticsearch_url, index_name=index_name)
        )
        self._embedder: LocalSentenceEmbedder | None = None
        self._reranker: LocalReranker | None = None

    def close(self) -> None:
        self.store.close()

    def _get_embedder(self) -> LocalSentenceEmbedder:
        if self._embedder is None:
            self._embedder = LocalSentenceEmbedder(
                EmbeddingSettings(
                    model_name=self.model_name,
                    batch_size=4,
                    device=self.device,
                    local_files_only=True,
                )
            )
        return self._embedder

    def _get_reranker(self) -> LocalReranker:
        if self._reranker is None:
            self._reranker = LocalReranker(
                RerankerSettings(
                    model_name=self.reranker_model,
                    device=self.device or "auto",
                    allow_download=True,
                )
            )
        return self._reranker

    @staticmethod
    def _queries(original_query: str, retrieval_queries: Sequence[str] | None) -> list[str]:
        original = original_query.strip()
        if not original:
            return []
        values = [original]
        for query in retrieval_queries or []:
            value = str(query).strip()
            if value and value not in values:
                values.append(value)
        return values[:4]

    def search(
        self,
        original_query: str,
        retrieval_queries: Sequence[str] | None = None,
        top_k: int = 6,
        candidate_k: int = 20,
        rerank: bool = True,
        rerank_candidates: int = 12,
        expansion_weight: float = 0.70,
    ) -> list[dict[str, Any]]:
        queries = self._queries(original_query, retrieval_queries)
        if not queries:
            return []
        if not self.store.ping():
            raise RuntimeError(
                "Elasticsearch is unavailable. Start it with: docker compose up -d elasticsearch"
            )

        vectors = self._get_embedder().encode(queries)
        channels: list[list[dict[str, Any]]] = []
        labels: list[str] = []
        weights: list[float] = []

        per_query_k = max(candidate_k, top_k, rerank_candidates if rerank else top_k)
        for index, (query, vector) in enumerate(zip(queries, vectors)):
            prefix = "original" if index == 0 else f"rewrite_{index}"
            weight = 1.0 if index == 0 else expansion_weight
            lexical = self.store.bm25_search(query, per_query_k)
            dense = self.store.knn_search(vector, per_query_k)
            channels.extend([lexical, dense])
            labels.extend([f"{prefix}_bm25", f"{prefix}_dense"])
            weights.extend([weight, weight])

        retrieval_k = max(top_k, rerank_candidates) if rerank else top_k
        candidates = rrf_fuse(
            channels,
            top_k=retrieval_k,
            labels=labels,
            weights=weights,
        )
        for item in candidates:
            item["query_variants"] = queries

        if not rerank:
            result = candidates[:top_k]
            for rank, item in enumerate(result, 1):
                item["rank"] = rank
            return result

        return self._get_reranker().rerank(
            original_query,
            candidates,
            top_k=top_k,
        )


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
    retrieval_queries: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """One-shot wrapper used by the CLI diagnostic command."""
    retriever = HybridRetriever(
        elasticsearch_url=elasticsearch_url,
        index_name=index_name,
        model_name=model_name,
        reranker_model=reranker_model,
        device=device,
    )
    try:
        return retriever.search(
            original_query=query,
            retrieval_queries=retrieval_queries,
            top_k=top_k,
            candidate_k=candidate_k,
            rerank=rerank,
            rerank_candidates=rerank_candidates,
        )
    finally:
        retriever.close()
