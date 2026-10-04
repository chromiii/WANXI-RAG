"""Local dense embedding boundary for retrieval.

The model is downloaded once and then executed locally. Source content is not
sent to a hosted embedding API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


DEFAULT_MODEL = "BAAI/bge-m3"
EXPECTED_DIMS = 1024


@dataclass(frozen=True)
class EmbeddingSettings:
    model_name: str = DEFAULT_MODEL
    batch_size: int = 8
    device: str | None = None
    local_files_only: bool = False


class LocalSentenceEmbedder:
    def __init__(self, settings: EmbeddingSettings = EmbeddingSettings()):
        self.settings = settings
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Dense embedding dependencies are not installed. "
                "Run: py -m pip install -r requirements-ml.txt"
            ) from exc

        kwargs = {}
        if settings.device and settings.device.lower() != "auto":
            kwargs["device"] = settings.device
        self.model = SentenceTransformer(
            settings.model_name,
            local_files_only=settings.local_files_only,
            **kwargs,
        )

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        values = self.model.encode(
            list(texts),
            batch_size=self.settings.batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > self.settings.batch_size,
            convert_to_numpy=True,
        )
        result = values.tolist()
        if result and len(result[0]) != EXPECTED_DIMS:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {EXPECTED_DIMS}, got {len(result[0])}"
            )
        return result

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]


def embedding_text(record: dict) -> str:
    """Keep the dense representation focused on searchable semantic content."""
    heading = str(record.get("heading") or "").strip()
    content = str(record.get("content") or "").strip()
    return f"{heading}\n{content}".strip()
