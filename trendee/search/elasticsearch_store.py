"""Elasticsearch evidence store for hybrid RAG retrieval.

Phase 1 defines the durable evidence schema and connection boundary. Embedding,
hybrid retrieval, and reranking are added in later phases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elasticsearch import Elasticsearch


EMBEDDING_DIMS = 1024
DEFAULT_INDEX = "wanxi-rag-evidence-v1"


def evidence_index_body(dims: int = EMBEDDING_DIMS) -> dict[str, Any]:
    """Return a deterministic mapping for text and image-derived evidence."""
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
        return {
            "cluster_name": info.get("cluster_name"),
            "version": info.get("version", {}).get("number"),
            "status": health.get("status"),
            "index": self.settings.index_name,
            "index_exists": bool(self.client.indices.exists(index=self.settings.index_name)),
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
