"""Local cross-encoder reranker for final retrieval precision.

The reranker scores query-passage pairs directly. It first tries the local
Hugging Face cache to keep normal search offline; if the model is not cached
and downloads are allowed, it falls back to a one-time Hub download.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence


DEFAULT_RERANKER = "BAAI/bge-reranker-base"


@dataclass(frozen=True)
class RerankerSettings:
    model_name: str = DEFAULT_RERANKER
    batch_size: int = 8
    max_length: int = 512
    device: str = "auto"
    allow_download: bool = True


class LocalReranker:
    def __init__(self, settings: RerankerSettings = RerankerSettings()):
        self.settings = settings
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Reranker dependencies are missing. "
                "Run: py -m pip install -r requirements-ml.txt"
            ) from exc

        self.torch = torch
        if settings.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = settings.device

        def load(local_only: bool):
            tokenizer = AutoTokenizer.from_pretrained(
                settings.model_name,
                local_files_only=local_only,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                settings.model_name,
                local_files_only=local_only,
            )
            return tokenizer, model

        try:
            self.tokenizer, self.model = load(local_only=True)
            self.loaded_from_cache = True
        except OSError:
            if not settings.allow_download:
                raise RuntimeError(
                    f"Reranker model is not cached locally: {settings.model_name}"
                ) from None
            self.tokenizer, self.model = load(local_only=False)
            self.loaded_from_cache = False

        self.model.to(self.device)
        self.model.eval()

    def score_pairs(self, pairs: Sequence[tuple[str, str]]) -> list[tuple[float, float]]:
        """Return (raw_logit, sigmoid_score) for each query-passage pair."""
        if not pairs:
            return []

        raw_scores: list[float] = []
        for start in range(0, len(pairs), self.settings.batch_size):
            batch = pairs[start : start + self.settings.batch_size]
            encoded = self.tokenizer(
                [[query, passage] for query, passage in batch],
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=self.settings.max_length,
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with self.torch.no_grad():
                logits = self.model(**encoded, return_dict=True).logits.view(-1).float()
            raw_scores.extend(float(value) for value in logits.detach().cpu().tolist())

        return [
            (raw, 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, raw)))))
            for raw in raw_scores
        ]

    def rerank(
        self,
        query: str,
        hits: Sequence[dict[str, Any]],
        top_k: int = 6,
    ) -> list[dict[str, Any]]:
        if not hits:
            return []

        pairs = [
            (
                query,
                f"{hit.get('heading', '')}\n{hit.get('content', '')}".strip(),
            )
            for hit in hits
        ]
        scores = self.score_pairs(pairs)
        rescored: list[dict[str, Any]] = []
        for pre_rank, (hit, (raw, normalized)) in enumerate(zip(hits, scores), 1):
            item = dict(hit)
            item["pre_rerank_rank"] = pre_rank
            item["reranker_score_raw"] = round(raw, 6)
            item["reranker_score"] = round(normalized, 6)
            rescored.append(item)

        rescored.sort(
            key=lambda item: (
                -float(item["reranker_score_raw"]),
                -float(item.get("rrf_score", 0.0)),
                str(item.get("chunk_id", "")),
            )
        )
        result = rescored[: max(1, top_k)]
        for rank, item in enumerate(result, 1):
            item["rank"] = rank
        return result
