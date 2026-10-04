"""Elasticsearch evidence store for hybrid RAG retrieval."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from elasticsearch import Elasticsearch, helpers


EMBEDDING_DIMS = 1024
DEFAULT_INDEX = "wanxi-rag-evidence-v1"


def evidence_index_body(dims: int = EMBEDDING_DIMS) -> dict[str, Any]:
    """Return a deterministic mapping for retrieval evidence."""
    if dims <= 0:
        raise ValueError("dims must be positive")
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "chunk_id": {"type": "keyword"},
                "source_id": {"type": "keyword"},
                "source_name": {"type": "keyword"},
                "source_sha256": {"type": "keyword"},
                "page": {"type": "integer"},
                "modality": {"type": "keyword"},
                "heading": {"type": "text", "analyzer": "cjk"},
                "content": {"type": "text", "analyzer": "cjk"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dims,
                    "index": True,
                    "similarity": "cosine",
                },
                "asset_path": {"type": "keyword", "index": False, "doc_values": False},
                "bbox": {"type": "float"},
                "text_length": {"type": "integer"},
                "created_at": {"type": "date"},
                "metadata": {"type": "flattened"},
            },
        },
    }


def rrf_fuse(
    channels: Sequence[Sequence[dict[str, Any]]],
    top_k: int = 6,
    rank_constant: int = 60,
    labels: Sequence[str] | None = None,
    weights: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    """Fuse ranked hit lists by chunk_id with transparent per-channel metadata."""
    scores: dict[str, float] = {}
    payloads: dict[str, dict[str, Any]] = {}
    channel_meta: dict[str, dict[str, dict[str, float | int]]] = {}

    if labels is not None and len(labels) != len(channels):
        raise ValueError("labels must match the number of RRF channels")
    if weights is not None and len(weights) != len(channels):
        raise ValueError("weights must match the number of RRF channels")

    for channel_number, hits in enumerate(channels, 1):
        label = labels[channel_number - 1] if labels else f"channel_{channel_number}"
        weight = float(weights[channel_number - 1]) if weights else 1.0
        if weight <= 0:
            raise ValueError("RRF weights must be positive")
        for rank, hit in enumerate(hits, 1):
            chunk_id = str(hit["chunk_id"])
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (rank_constant + rank)
            payloads.setdefault(chunk_id, hit)
            channel_meta.setdefault(chunk_id, {})[label] = {
                "rank": rank,
                "score": round(float(hit.get("score") or 0.0), 6),
                "weight": weight,
            }

    ordered = sorted(scores, key=lambda cid: (-scores[cid], cid))
    result: list[dict[str, Any]] = []
    for rank, chunk_id in enumerate(ordered[: max(1, top_k)], 1):
        item = dict(payloads[chunk_id])
        # The raw ES _score is channel-specific and should not be mistaken for
        # the final fused score.
        item.pop("score", None)
        item["pre_rerank_rank"] = rank
        item["rrf_score"] = round(scores[chunk_id], 8)
        item["retrieval_channels"] = channel_meta[chunk_id]
        result.append(item)
    return result


@dataclass(frozen=True)
class ElasticsearchSettings:
    url: str = "http://127.0.0.1:9200"
    index_name: str = DEFAULT_INDEX
    request_timeout: int = 30


class ElasticsearchEvidenceStore:
    def __init__(self, settings: ElasticsearchSettings):
        self.settings = settings
        self.client = Elasticsearch(
            settings.url,
            request_timeout=settings.request_timeout,
        )

    def close(self) -> None:
        self.client.close()

    def ping(self) -> bool:
        return bool(self.client.ping())

    def health(self) -> dict[str, Any]:
        info = self.client.info()
        health = self.client.cluster.health()
        count = 0
        if self.client.indices.exists(index=self.settings.index_name):
            count = int(self.client.count(index=self.settings.index_name)["count"])
        return {
            "cluster_name": info.get("cluster_name"),
            "version": info.get("version", {}).get("number"),
            "status": health.get("status"),
            "index": self.settings.index_name,
            "index_exists": bool(self.client.indices.exists(index=self.settings.index_name)),
            "document_count": count,
        }

    def ensure_index(self, dims: int = EMBEDDING_DIMS) -> bool:
        """Create the evidence index once. Returns True only when created."""
        if self.client.indices.exists(index=self.settings.index_name):
            return False
        self.client.indices.create(
            index=self.settings.index_name,
            **evidence_index_body(dims),
        )
        return True

    def delete_source(self, source_id: str) -> int:
        if not self.client.indices.exists(index=self.settings.index_name):
            return 0
        response = self.client.delete_by_query(
            index=self.settings.index_name,
            query={"term": {"source_id": source_id}},
            conflicts="proceed",
            refresh=True,
        )
        return int(response.get("deleted", 0))

    def bulk_index(
        self,
        records: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]],
        replace_source: bool = True,
    ) -> dict[str, Any]:
        if len(records) != len(embeddings):
            raise ValueError("records and embeddings must have equal length")
        if not records:
            return {"indexed": 0, "deleted_previous": 0}

        self.ensure_index()
        source_ids = {str(record["source_id"]) for record in records}
        if len(source_ids) != 1:
            raise ValueError("bulk_index currently expects records from exactly one source")
        source_id = next(iter(source_ids))
        deleted = self.delete_source(source_id) if replace_source else 0

        actions = []
        for record, embedding in zip(records, embeddings):
            if len(embedding) != EMBEDDING_DIMS:
                raise ValueError(
                    f"Embedding for {record.get('id')} has {len(embedding)} dimensions; "
                    f"expected {EMBEDDING_DIMS}"
                )
            document = {
                "chunk_id": record["id"],
                "source_id": record["source_id"],
                "source_name": record["source_name"],
                "source_sha256": record["source_sha256"],
                "page": int(record["page"]),
                "modality": record.get("modality", "text"),
                "heading": record.get("heading", ""),
                "content": record.get("content", ""),
                "embedding": list(embedding),
                "asset_path": record.get("asset_path"),
                "bbox": record.get("bbox"),
                "text_length": int(record.get("text_length") or len(record.get("content", ""))),
                "created_at": record["created_at"],
                "metadata": record.get("metadata") or {},
            }
            actions.append({
                "_op_type": "index",
                "_index": self.settings.index_name,
                "_id": record["id"],
                "_source": document,
            })

        success, errors = helpers.bulk(
            self.client,
            actions,
            refresh="wait_for",
            raise_on_error=False,
        )
        if errors:
            first = errors[0]
            raise RuntimeError(f"Elasticsearch bulk indexing failed: {first}")
        return {
            "indexed": int(success),
            "deleted_previous": deleted,
            "source_id": source_id,
            "index": self.settings.index_name,
        }

    @staticmethod
    def _hit_payload(hit: dict[str, Any]) -> dict[str, Any]:
        source = dict(hit.get("_source") or {})
        source["score"] = float(hit.get("_score") or 0.0)
        return source

    def bm25_search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        response = self.client.search(
            index=self.settings.index_name,
            size=max(1, top_k),
            query={
                "multi_match": {
                    "query": query,
                    "fields": ["heading^2", "content"],
                    "type": "best_fields",
                }
            },
            source_excludes=["embedding"],
        )
        return [self._hit_payload(hit) for hit in response["hits"]["hits"]]

    def knn_search(
        self,
        query_vector: Sequence[float],
        top_k: int = 20,
        num_candidates: int | None = None,
    ) -> list[dict[str, Any]]:
        if len(query_vector) != EMBEDDING_DIMS:
            raise ValueError(f"query vector must have {EMBEDDING_DIMS} dimensions")
        k = max(1, top_k)
        candidates = max(k, num_candidates or max(100, k * 5))
        response = self.client.search(
            index=self.settings.index_name,
            size=k,
            knn={
                "field": "embedding",
                "query_vector": list(query_vector),
                "k": k,
                "num_candidates": candidates,
            },
            source_excludes=["embedding"],
        )
        return [self._hit_payload(hit) for hit in response["hits"]["hits"]]
