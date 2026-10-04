"""Orchestration for Project 1: intent -> retrieval -> postprocess -> generation -> grounding."""
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
from .postprocess import process_retrieved_hits
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


def source_visuals(refs: list[dict[str, Any]], max_items: int = 3) -> list[dict[str, Any]]:
    """Return unique PDF page visuals actually used by generated citations."""
    visuals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        asset_path = ref.get("asset_path")
        if not asset_path or asset_path in seen:
            continue
        seen.add(asset_path)
        visuals.append({
            "id": ref.get("id"),
            "page": ref.get("page"),
            "heading": ref.get("heading"),
            "source": ref.get("source"),
            "asset_path": asset_path,
        })
        if len(visuals) >= max_items:
            break
    return visuals


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

    def _query_plan(
        self,
        topic: str,
        intent: dict[str, Any],
        active_mode: str,
        client: Client,
    ) -> dict[str, Any]:
        if active_mode != "live":
            return passthrough_plan(topic)

        payload = {
            "query": topic,
            "audience": intent.get("audience"),
            "task_intent": {
                "content_type": intent["content_type"],
                "content_type_label": intent["content_type_label"],
                "semantic_focus": intent.get("semantic_focus"),
                "user_goal": intent.get("user_goal") or intent.get("goal"),
            },
        }
        raw = client.json(
            _prompt("query_planner", include_common=False),
            json.dumps(payload, ensure_ascii=False),
            lambda value: validate_query_plan(value, topic),
            purpose="query_planner",
        )
        return validate_query_plan(raw, topic)

    @staticmethod
    def _rerank_query(topic: str, intent: dict[str, Any]) -> str:
        user_goal = str(intent.get("user_goal") or intent.get("goal") or "").strip()
        semantic_focus = str(intent.get("semantic_focus") or "").strip()
        parts = [topic]
        if user_goal and user_goal != topic:
            parts.append("用户目标：" + user_goal)
        if semantic_focus and semantic_focus != "generic":
            parts.append("语义焦点：" + semantic_focus)
        return "\n".join(parts)

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
        top_k = int(top_k)
        if not 1 <= top_k <= 12:
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
                "capabilities": "我支持四类内容：Blog、FAQ、品牌介绍、产品介绍。系统会进行范围判断、任务意图识别、Query Planning、Hybrid Retrieval、Reranking、后检索处理、内容生成和 Grounding 校验。",
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
            "presentation_source": intent.get("presentation_source"),
            "semantic_focus": intent.get("semantic_focus"),
            "user_goal": intent.get("user_goal"),
            "confidence": intent.get("confidence"),
        })

        query_plan = self._query_plan(topic, intent, active_mode, client)
        trace.append({
            "step": "query_planning",
            "status": "ok",
            "strategy": query_plan.get("strategy"),
            "rewrite_needed": query_plan["rewrite_needed"],
            "intent": query_plan["intent"],
            "query_count": len(query_plan["retrieval_queries"]),
        })

        # Rerank a wider pool than the final context Top-K so hard filters and
        # dedup can backfill from lower-ranked safe candidates.
        candidate_pool = min(12, max(top_k * 2, top_k + 4))
        rerank_query = self._rerank_query(topic, intent)
        query_plan["rerank_query"] = rerank_query
        raw_hits = self.retriever.search(
            original_query=topic,
            retrieval_queries=query_plan["retrieval_queries"],
            top_k=candidate_pool,
            rerank=True,
            rerank_candidates=candidate_pool,
            rerank_query=rerank_query,
        )
        retrieved_hits = [adapt_pdf_hit(hit) for hit in raw_hits]
        trace.append({
            "step": "hybrid_retrieval",
            "status": "ok" if retrieved_hits else "empty",
            "method": "BM25 + BGE-M3 dense + weighted RRF + cross-encoder reranker",
            "candidate_pool": candidate_pool,
            "retrieved": len(retrieved_hits),
        })

        if scope["scope"] == "ambiguous":
            verified_scope = evidence_scope_check(topic, retrieved_hits)
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
                    "retrieval_hits": retrieved_hits,
                    "references": reference_list(retrieved_hits),
                    "workflow_trace": trace,
                    "model_calls": client.calls,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                    "created_at_utc": now_utc(),
                }

        missing = unknown_fact_request(topic, retrieved_hits)
        if not retrieved_hits or missing:
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
                "retrieval_hits": retrieved_hits,
                "references": reference_list(retrieved_hits),
                "workflow_trace": trace,
                "model_calls": client.calls,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "created_at_utc": now_utc(),
            }

        processed = process_retrieved_hits(
            retrieved_hits,
            topic=topic,
            content_type=intent["content_type"],
            top_n=top_k,
            max_chars=8000,
        )
        retrieval_hits = processed["all_hits"]
        generation_hits = processed["selected"]
        trace.append({
            "step": "post_retrieval_processing",
            "status": "ok" if generation_hits else "insufficient_evidence",
            "status_counts": processed["status_counts"],
            "final_top_n": top_k,
            "selected": len(generation_hits),
            "context_budget": processed["max_chars"],
        })

        if not generation_hits:
            return {
                "status": "insufficient_evidence",
                "project": "rag_writer",
                "mode": active_mode,
                "topic": topic,
                "task_intent": intent,
                "query_plan": query_plan,
                "message": "检索到了候选资料，但在安全过滤、去重和上下文预算处理后没有足够证据进入生成。",
                "scope": scope,
                "post_retrieval": {
                    "status_counts": processed["status_counts"],
                    "selected_ids": processed["selected_ids"],
                },
                "retrieval_hits": retrieval_hits,
                "references": reference_list(retrieval_hits),
                "workflow_trace": trace,
                "model_calls": client.calls,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "created_at_utc": now_utc(),
            }

        context = build_context(generation_hits, max_chars=processed["max_chars"])
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
                "instruction": (
                    "只使用真正支持当前主题和内容类型的 evidence。"
                    "检索排序只是相关性线索，不要求覆盖全部 evidence；"
                    "按照 evidence_type / risk_flags 正确归因营销主张、设想、案例和数据。"
                ),
            }, ensure_ascii=False)
            writer_name = WRITER_PROMPTS[intent["content_type"]]
            document = client.json(
                _prompt(writer_name),
                request,
                lambda value: validate_document(intent["content_type"], value, generation_hits, topic=topic),
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

        validation = validate_document(intent["content_type"], document, generation_hits, topic=topic)
        used_ids = used_citations(document)
        refs = reference_list(retrieval_hits, used_ids)
        visuals = source_visuals(refs, max_items=3)
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
            "post_retrieval": {
                "status_counts": processed["status_counts"],
                "selected_ids": processed["selected_ids"],
                "candidate_count": len(retrieval_hits),
                "final_top_n": top_k,
                "context_budget": processed["max_chars"],
            },
            "document": document,
            "article": document,
            "markdown": markdown,
            "references": refs,
            "source_visuals": visuals,
            "retrieval_hits": retrieval_hits,
            "context": {
                "evidence_ids": context["evidence_ids"],
                "evidence_count": context["evidence_count"],
                "context_chars": context["context_chars"],
                "max_chars": context["max_chars"],
            },
            "validation": validation,
            "workflow_trace": trace,
            "model_calls": client.calls,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "created_at_utc": now_utc(),
        }
