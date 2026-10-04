"""Orchestration for Project 1: intent -> retrieval -> generation -> grounding."""
from __future__ import annotations

import json
import time
from typing import Any

from ..config import ROOT
from ..documents import now_utc
from ..grounding import (
    injection_request,
    reference_list,
    unknown_fact_request,
    used_citations,
)
from ..llm import Client
from ..search.query_planner import passthrough_plan, validate_query_plan
from .context import build_context
from .generation import offline_document, render_markdown, validate_document
from .intent import parse_task_intent


WRITER_PROMPTS = {
    "blog": "writer_blog",
    "faq": "writer_faq",
    "brand_intro": "writer_brand",
    "product_intro": "writer_product",
}


def _prompt(name: str, include_common: bool = True) -> str:
    specific = (ROOT / f"prompts/{name}.md").read_text(encoding="utf-8")
    if not include_common:
        return specific
    common = (ROOT / "prompts/common.md").read_text(encoding="utf-8")
    return common + "\n\n" + specific


def adapt_pdf_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Normalize Elasticsearch evidence to the shared grounding contract."""
    return {
        "id": hit["chunk_id"],
        "text": hit.get("content", ""),
        "source": hit.get("source_name", "trendee_brand.pdf"),
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


class RAGWorkflow:
    def __init__(self, config, retriever):
        self.config = config
        self.retriever = retriever

    @staticmethod
    def _validate_text(value: str, label: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError(f"{label} must contain 1-2000 characters")
        return value.strip()

    def _query_plan(self, topic: str, active_mode: str, client: Client) -> dict[str, Any]:
        if active_mode != "live":
            return passthrough_plan(topic)
        raw = client.json(
            _prompt("query_planner", include_common=False),
            json.dumps({"query": topic}, ensure_ascii=False),
            lambda value: validate_query_plan(value, topic),
            purpose="query_planner",
        )
        return validate_query_plan(raw, topic)

    def run(
        self,
        topic: str,
        audience: str = "中国出海品牌的市场与运营团队",
        content_type: str = "auto",
        mode: str = "auto",
        top_k: int = 6,
    ) -> dict[str, Any]:
        topic = self._validate_text(topic, "topic")
        audience = self._validate_text(audience, "audience")
        if not 1 <= int(top_k) <= 12:
            raise ValueError("top_k must be between 1 and 12")

        active_mode = self.config.mode(mode)
        if injection_request(topic):
            return {
                "status": "rejected",
                "project": "rag_writer",
                "mode": active_mode,
                "message": "不能伪造公司事实、数据或引用。请提供基于资料的写作任务。",
                "workflow_trace": [{"step": "input_guard", "status": "rejected"}],
            }

        started = time.perf_counter()
        client = Client(self.config)
        trace: list[dict[str, Any]] = []

        intent = parse_task_intent(
            topic=topic,
            audience=audience,
            requested_type=content_type,
            active_mode=active_mode,
            client=client,
            system_prompt=_prompt("task_intent", include_common=False),
        )
        trace.append({
            "step": "task_intent",
            "status": "ok",
            "content_type": intent["content_type"],
            "content_type_label": intent["content_type_label"],
            "source": intent["source"],
        })

        query_plan = self._query_plan(topic, active_mode, client)
        trace.append({
            "step": "query_planning",
            "status": "ok",
            "rewrite_needed": query_plan["rewrite_needed"],
            "intent": query_plan["intent"],
            "query_count": len(query_plan["retrieval_queries"]),
        })

        raw_hits = self.retriever.search(
            original_query=topic,
            retrieval_queries=query_plan["retrieval_queries"],
            top_k=int(top_k),
            rerank=True,
        )
        hits = [adapt_pdf_hit(hit) for hit in raw_hits]
        trace.append({
            "step": "hybrid_retrieval",
            "status": "ok" if hits else "empty",
            "method": "BM25 + BGE-M3 dense + weighted RRF + cross-encoder reranker",
            "retrieved": len(hits),
        })

        missing = unknown_fact_request(topic, hits)
        if not hits or missing:
            trace.append({
                "step": "evidence_gate",
                "status": "insufficient_evidence",
                "missing": missing,
            })
            return {
                "status": "insufficient_evidence",
                "project": "rag_writer",
                "mode": active_mode,
                "topic": topic,
                "task_intent": intent,
                "query_plan": query_plan,
                "message": "资料未提供：" + "、".join(missing) if missing else "检索不到足够相关的 PDF 依据。",
                "retrieval_hits": hits,
                "references": reference_list(hits),
                "workflow_trace": trace,
                "model_calls": client.calls,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "created_at_utc": now_utc(),
            }

        context = build_context(hits)
        trace.append({
            "step": "context_building",
            "status": "ok",
            "evidence_count": context["evidence_count"],
            "context_chars": context["context_chars"],
            "evidence_ids": context["evidence_ids"],
        })

        if active_mode == "live":
            request = json.dumps({
                "topic": topic,
                "audience": audience,
                "task_intent": intent,
                "query_plan": query_plan,
                "evidence": context["text"],
                "instruction": "只使用真正支持当前主题的 evidence，不要求覆盖全部检索结果。",
            }, ensure_ascii=False)
            writer_name = WRITER_PROMPTS[intent["content_type"]]
            document = client.json(
                _prompt(writer_name),
                request,
                lambda value: validate_document(intent["content_type"], value, hits),
                purpose="writer:" + intent["content_type"],
            )
        else:
            document = offline_document(intent["content_type"], topic, hits)

        trace.append({
            "step": "generation",
            "status": "ok",
            "generator": "DeepSeek" if active_mode == "live" else "deterministic_offline_draft",
            "writer": intent["content_type"],
        })

        validation = validate_document(intent["content_type"], document, hits)
        used_ids = used_citations(document)
        refs = reference_list(hits, used_ids)
        trace.append({
            "step": "grounding_validation",
            "status": "ok",
            "claim_count": validation["claim_count"],
            "used_evidence_count": len(used_ids),
            "citation_ids_valid": validation["citation_ids_valid"],
            "numeric_guard_passed": validation["numeric_guard_passed"],
        })

        markdown = render_markdown(intent["content_type"], document, refs)
        return {
            "status": "ok",
            "project": "rag_writer",
            "mode": active_mode,
            "model": self.config.model if active_mode == "live" else None,
            "topic": topic,
            "audience": audience,
            "content_type": intent["content_type_label"],
            "task_intent": intent,
            "query_plan": query_plan,
            "document": document,
            "article": document,
            "markdown": markdown,
            "references": refs,
            "retrieval_hits": hits,
            "context": {
                "evidence_ids": context["evidence_ids"],
                "evidence_count": context["evidence_count"],
                "context_chars": context["context_chars"],
            },
            "validation": validation,
            "workflow_trace": trace,
            "model_calls": client.calls,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "created_at_utc": now_utc(),
        }
