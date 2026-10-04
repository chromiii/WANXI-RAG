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
from .scope import precheck_scope, evidence_scope_check


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

        scope = precheck_scope(topic)
        trace.append({
            "step": "scope_guard",
            "status": scope["scope"],
            "source": scope["source"],
            "reason": scope["reason"],
        })
        if scope["scope"] == "meta":
            messages = {
                "greeting": "你好，我是这个项目的万悉 RAG 内容写作助手。你可以给我一个与万悉科技、GEO、AI 搜索可见性、品牌内容或产品能力相关的主题。",
                "identity": "我是万悉科技 Project 1 的 RAG 写作助手，负责基于品宣 PDF 生成 Blog、FAQ、品牌介绍和产品介绍，并展示检索证据、页码与引用校验。",
                "capabilities": "我支持四类内容：Blog、FAQ、品牌介绍、产品介绍。系统会进行范围判断、任务意图识别、Query Planning、Hybrid Retrieval、Reranking、证据构建、内容生成和 Grounding 校验。",
            }
            return {
                "status": "meta",
                "project": "rag_writer",
                "mode": active_mode,
                "topic": topic,
                "meta_intent": scope.get("meta_intent"),
                "message": messages.get(scope.get("meta_intent"), "你好，我是万悉 RAG 内容写作助手。"),
                "scope": scope,
                "workflow_trace": trace,
                "model_calls": client.calls,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "created_at_utc": now_utc(),
            }

        if scope["scope"] == "out_of_scope":
            return {
                "status": "out_of_scope",
                "project": "rag_writer",
                "mode": active_mode,
                "topic": topic,
                "message": "该问题与万悉品牌/GEO内容生成任务无关，请输入与万悉、GEO、AI搜索可见性、品牌内容或产品能力相关的写作主题。",
                "scope": scope,
                "workflow_trace": trace,
                "model_calls": client.calls,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "created_at_utc": now_utc(),
            }

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

        if scope["scope"] == "ambiguous":
            verified_scope = evidence_scope_check(topic, hits)
            trace.append({
                "step": "scope_verification",
                "status": verified_scope["scope"],
                "source": verified_scope["source"],
                "reason": verified_scope["reason"],
                "best_score": verified_scope.get("best_score"),
            })
            scope = verified_scope
            if scope["scope"] == "out_of_scope":
                return {
                    "status": "out_of_scope",
                    "project": "rag_writer",
                    "mode": active_mode,
                    "topic": topic,
                    "task_intent": intent,
                    "query_plan": query_plan,
                    "message": "检索不到足以支持该主题的万悉品宣资料，因此停止生成，避免用无关证据硬写。",
                    "scope": scope,
                    "retrieval_hits": hits,
                    "references": reference_list(hits),
                    "workflow_trace": trace,
                    "model_calls": client.calls,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "created_at_utc": now_utc(),
                }

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

        context = build_context(
            hits,
            topic=topic,
            retrieval_intent=query_plan.get("intent", ""),
        )
        selection_by_id = {
            item["id"]: item for item in context["evidence_selection"]
        }
        for hit in hits:
            decision = selection_by_id.get(hit["id"], {})
            hit["evidence_priority"] = decision.get("priority")
            hit["evidence_type"] = decision.get("evidence_type")
            hit["evidence_reason"] = decision.get("reason")
            hit["evidence_focus"] = decision.get("focus")
            hit["matched_signals"] = decision.get("matched_signals", [])

        trace.append({
            "step": "evidence_selection",
            "status": "ok",
            "focus": context["focus"],
            "priority_counts": context["priority_counts"],
            "type_counts": context["type_counts"],
        })

        generation_ids = set(context["evidence_ids"])
        generation_hits = [hit for hit in hits if hit["id"] in generation_ids]
        if not generation_hits:
            trace.append({
                "step": "context_building",
                "status": "insufficient_evidence",
                "evidence_count": 0,
            })
            return {
                "status": "insufficient_evidence",
                "project": "rag_writer",
                "mode": active_mode,
                "topic": topic,
                "task_intent": intent,
                "query_plan": query_plan,
                "message": "检索到了候选资料，但 Evidence Policy 未找到足够适合进入生成上下文的证据。",
                "scope": scope,
                "evidence_selection": context["evidence_selection"],
                "retrieval_hits": hits,
                "references": reference_list(hits),
                "workflow_trace": trace,
                "model_calls": client.calls,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "created_at_utc": now_utc(),
            }

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
                lambda value: validate_document(intent["content_type"], value, generation_hits),
                purpose="writer:" + intent["content_type"],
            )
        else:
            document = offline_document(intent["content_type"], topic, generation_hits)

        trace.append({
            "step": "generation",
            "status": "ok",
            "generator": "DeepSeek" if active_mode == "live" else "deterministic_offline_draft",
            "writer": intent["content_type"],
        })

        validation = validate_document(intent["content_type"], document, generation_hits)
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
            "scope": scope,
            "task_intent": intent,
            "query_plan": query_plan,
            "evidence_selection": context["evidence_selection"],
            "document": document,
            "article": document,
            "markdown": markdown,
            "references": refs,
            "retrieval_hits": hits,
            "context": {
                "evidence_ids": context["evidence_ids"],
                "evidence_count": context["evidence_count"],
                "context_chars": context["context_chars"],
                "focus": context["focus"],
                "priority_counts": context["priority_counts"],
                "type_counts": context["type_counts"],
                "excluded_evidence": context["excluded_evidence"],
                "low_priority_evidence": context["low_priority_evidence"],
            },
            "validation": validation,
            "workflow_trace": trace,
            "model_calls": client.calls,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "created_at_utc": now_utc(),
        }
