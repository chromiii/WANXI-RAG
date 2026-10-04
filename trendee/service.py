from dataclasses import asdict
import json
from pathlib import Path
import re
import time

from .agents import REGISTRY, rule_route, validate_route, execution_plan, validate_agent
from .config import ROOT, Config, runtime_data_dir
from .documents import prepare_brand, now_utc
from .grounding import validate_grounding, reference_list, used_citations, unknown_fact_request, injection_request
from .llm import Client
from .retrieval import Index, pdf_chunks, website_chunks, context_from_hits
from .search.pipeline import HybridRetriever
from .search.query_planner import passthrough_plan, validate_query_plan
from .rag.workflow import RAGWorkflow


def prompt(name, include_common=True):
    specific = (ROOT / f"prompts/{name}.md").read_text(encoding="utf-8")
    if not include_common:
        return specific
    return (ROOT / "prompts/common.md").read_text(encoding="utf-8") + "\n\n" + specific


def claim(text, hit):
    return {"text": text, "citations": [hit["id"]]}




class Workbench:
    def __init__(self, config=None, data_dir=None):
        self.config = config or Config.from_env()
        if data_dir is None:
            data_dir = runtime_data_dir()
        else:
            data_dir = Path(data_dir).expanduser()
            if not data_dir.is_absolute():
                data_dir = ROOT / data_dir
        self.pages, self.brand_manifest = prepare_brand(data_dir)
        snapshot_path = data_dir / "website_snapshot.json"
        self.snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else None
        self.pdf_index = Index(pdf_chunks(self.pages))
        self.site_index = Index(website_chunks(self.snapshot)) if self.snapshot else None
        self._rag_retriever = None

    def info(self):
        return {"version": "1.1.0", "api_configured": bool(self.config.api_key), "model": self.config.model,
                "default_mode": self.config.mode(), "pdf_pages": len(self.pages),
                "pdf_chunks": len(self.pdf_index.chunks),
                "website_pages": self.snapshot["page_count"] if self.snapshot else 0,
                "website_chunks": len(self.site_index.chunks) if self.site_index else 0,
                "website_captured_at_utc": self.snapshot["captured_at_utc"] if self.snapshot else None,
                "website_urls": [p["url"] for p in self.snapshot["pages"]] if self.snapshot else [],
                "retrieval": "Elasticsearch BM25 + BGE-M3 dense kNN + weighted multi-query RRF + local cross-encoder reranker",
                "query_planner": "DeepSeek in live mode; original-query passthrough offline",
                "rag_workflow": "Task Intent -> Query Plan -> Hybrid Retrieval -> Context -> Type-specific Writer -> Grounding",
                "content_types": ["Blog", "FAQ", "品牌介绍", "产品介绍"],
                "agents": [{**asdict(s), "dependencies": list(s.dependencies)} for s in REGISTRY.values()]}

    @staticmethod
    def check_input(question):
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("请输入 1-2000 字符的问题。")
        return question.strip()

    def _get_pdf_retriever(self):
        if self._rag_retriever is None:
            self._rag_retriever = HybridRetriever(
                elasticsearch_url=self.config.elasticsearch_url,
                index_name=self.config.elasticsearch_index,
            )
        return self._rag_retriever

    @staticmethod
    def _adapt_pdf_hit(hit):
        """Adapt Elasticsearch evidence to the existing grounding/citation contract."""
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

    def plan_pdf_query(self, query, active_mode, client):
        if active_mode != "live":
            return passthrough_plan(query)
        raw = client.json(
            prompt("query_planner", include_common=False),
            json.dumps({"query": query}, ensure_ascii=False),
            lambda value: validate_query_plan(value, query),
            purpose="query_planner",
        )
        return validate_query_plan(raw, query)

    def search_pdf(self, query, mode="auto", top_k=6, client=None):
        query = self.check_input(query)
        active_mode = self.config.mode(mode)
        client = client or Client(self.config)
        plan = self.plan_pdf_query(query, active_mode, client)
        raw_hits = self._get_pdf_retriever().search(
            original_query=query,
            retrieval_queries=plan["retrieval_queries"],
            top_k=top_k,
            rerank=True,
        )
        return {
            "status": "ok" if raw_hits else "insufficient_evidence",
            "mode": active_mode,
            "query": query,
            "query_plan": plan,
            "hits": [self._adapt_pdf_hit(hit) for hit in raw_hits],
            "model_calls": client.calls,
        }

    def write(self, topic, audience="中国出海品牌的市场与运营团队", content_type="auto", mode="auto", top_k=6):
        """Run the single Project 1 production workflow."""
        workflow = RAGWorkflow(self.config, self._get_pdf_retriever())
        return workflow.run(
            topic=topic,
            audience=audience,
            content_type=content_type,
            mode=mode,
            top_k=top_k,
        )

    def route(self, question, history=None, mode="auto", router="rules", client=None):
        question = self.check_input(question)
        if router not in {"rules", "llm"}:
            raise ValueError("router must be rules or llm")
        if injection_request(question):
            return {"agents": [], "reason": "拒绝伪造事实或覆盖系统规则的请求。", "router": router, "rejected": True}
        if router == "llm":
            if self.config.mode(mode) != "live":
                raise ValueError("LLM Router 需要真实模型模式；离线模式请选择规则路由。")
            client = client or Client(self.config)
            decision = client.json(prompt("router"), json.dumps({"question": question,
                                   "previous_questions": (history or [])[-3:]}, ensure_ascii=False), validate_route,
                                   purpose="router")
            decision["router"] = "llm"
        else:
            decision = rule_route(question)
            if not decision["agents"] and history and re.search(r"这些|那|上述|继续|进一步", question):
                decision = rule_route(history[-1] + "\n" + question)
                decision["reason"] += "；使用上轮问题解析指代。"
        decision["plan"] = execution_plan(decision["agents"])
        return decision

    def agent_evidence(self, question):
        hits = self.site_index.search(question, top_k=6, max_context_chars=4500)
        extra = self.site_index.search("GEO 产品能力 中国 全球化 服务对象 用户提示模拟 AI可见性追踪", top_k=4)
        candidates = hits + extra
        for c in self.site_index.chunks:
            if c.id == "web-01-meta" or any(k in c.heading for k in ["用户提示模拟", "AI可见性追踪", "内容优化策略", "GEO到底是什么"]):
                candidates.append({**asdict(c), "score": 0, "retrieval_channel": "task_required_context"})
        result, seen, budget = [], set(), 0
        for h in candidates:
            if h["id"] not in seen and budget + len(h["text"]) <= 10000:
                result.append(h)
                seen.add(h["id"])
                budget += len(h["text"])
        return result

    def offline_agent(self, name, hits, state, question):
        def find(pattern, fallback=None):
            return next((h for h in hits if re.search(pattern, h["heading"] + " " + h["text"])), fallback or hits[0])
        positioning = find("全球化|中国.*出海")
        ability = find("用户提示模拟|AI可见性追踪|内容优化策略")
        faq = find("GEO到底是什么|SEO")
        meta = find("静态HTML结构检测")
        if name == "website_analysis":
            capabilities = [h for h in hits if any(k in h["heading"] for k in ["用户提示模拟", "AI可见性追踪", "内容优化策略"])]
            return {"brand_positioning": claim("官网资料自述：" + positioning["text"], positioning),
                    "capabilities": [claim(h["heading"] + "：" + h["text"], h) for h in (capabilities or [ability])[:5]],
                    "audience": [claim("官网的全球化/出海品牌相关表述：" + positioning["text"], positioning)],
                    "technical_keywords": [k for k in ["GEO", "RAG", "LLM", "AI"] if any(k in h["text"] for h in hits)],
                    "summary": claim("官网围绕以下定位和价值展开：" + positioning["text"], positioning)}
        if name == "geo_diagnosis":
            page = self.snapshot["pages"][0]
            return {"findings": [
                {"type": "strength", "observation": claim("已抓取内容有直接解释 GEO/SEO 的问答，支持围绕客户问题组织答案。资料原文：" + faq["text"], faq),
                 "recommendation": "保留短回答与展开解释，并补充适用边界和资料日期。", "priority": "P1", "verification": "observed_static_html"},
                {"type": "gap", "observation": claim(f"抓取的首页静态 HTML 检测到 {page['jsonld_count']} 块 JSON-LD、{page['h1_count']} 个 H1。这只描述本次静态检测。", meta),
                 "recommendation": "核对渲染 DOM；结合实际页面补全清晰主标题及适用的 Organization/Article 等结构化描述。", "priority": "P1", "verification": "observed_static_html"},
                {"type": "risk", "observation": claim("官网的服务能力表述需要配套证据与方法边界；资料原文：" + ability["text"], ability),
                 "recommendation": "补充检测方法、模型版本、样本问题集与案例统计口径；不保证永久写入模型参数或固定排名。", "priority": "P0", "verification": "inference_to_verify"}],
                "measurement_plan": ["先建立固定客户问题集，保存各模型的回答及引用URL；按同一口径比较优化前后的引用覆盖率、品牌提及率及事实正确率。",
                                     "记录模型版本、日期和采样次数；页面结构检测不能替代实际 AI 引用效果评测。"],
                "scope_note": f"已抓取 {self.snapshot['page_count']} 个公开页面；静态 HTML 检测，未测量真实 AI 平台引用效果。"}
        if name == "user_questions":
            audience = "跨境电商运营团队" if "电商" in question else "中国出海品牌的市场与运营团队"
            items = [("GEO 和 SEO 有什么区别，企业应该分别解决哪些问题？", "learn", faq),
                     ("出海品牌如何让产品信息更容易被 AI 理解和引用？", "evaluate", positioning),
                     ("如何判断我们的品牌在 AI 回答中被提及或被引用？", "verify", ability),
                     ("GEO 服务商应提供哪些可核验的监测数据和交付物？", "select", ability),
                     ("怎样把产品参数转化为目标客户愿意提问的使用场景？", "evaluate", positioning),
                     ("启动官网 GEO 内容优化时，FAQ 和产品介绍应先补充什么？", "evaluate", faq)]
            return {"questions": [{"question": q, "intent": intent, "audience": audience, "evidence_ids": [h["id"]]}
                                  for q, intent, h in items], "status": "hypotheses_to_validate"}
        if name == "content_strategy":
            diagnostic = state["geo_diagnosis"]["findings"]
            questions = state.get("user_questions", state.get("previous_user_questions", {})).get("questions", [])
            selected = 0
            ordinal = re.search(r"第([一二三四五六七八九]|\d+)条", question)
            if ordinal:
                numeral = ordinal.group(1)
                selected = int(numeral) - 1 if numeral.isdigit() else "一二三四五六七八九".index(numeral)
                selected = max(0, min(selected, len(questions)-1))
            topic = questions[selected]["question"] if questions else "GEO 和 SEO 的区别、适用范围与效果边界"
            actions = []
            for i, (kind, title, target, criteria) in enumerate([
                ("方法页", "AI 引用监测方法与案例口径", "GEO 效果应该怎样验证？", "给出问题集、模型版本、测试日期、原始回答与引用 URL；区分测试结果与营销主张。"),
                ("FAQ", topic, topic, "每条问题提供直接回答、解释、出处与适用边界；引用可回查。"),
                ("产品页", "从产品能力到客户使用场景", "这些功能解决哪些出海运营任务？", "逐项对应用户任务、所需输入、输出样例及局限，不编造效果数据。"),
            ]):
                finding = diagnostic[i % len(diagnostic)]
                actions.append({"priority": "P0" if i == 0 else "P1", "content_type": kind, "topic": title,
                                "target_question": target, "reason": finding["observation"],
                                "acceptance_criteria": criteria,
                                "measurement": "上线后使用固定问题集复测，并核查回答准确性及引用来源；不承诺固定增长。"})
            return {"actions": actions, "scope_note": "根据已抓取网页、前置官网分析及诊断整理；候选问题需实际用户数据验证。"}
        raise ValueError("Unknown Agent")

    def collaborate(self, question, history=None, mode="auto", router="rules", on_event=None, prior_result=None):
        question = self.check_input(question)
        if history is None:
            history = []
        if not isinstance(history, list) or len(history) > 10 or any(not isinstance(x, str) or len(x) > 2000 for x in history):
            raise ValueError("history must contain at most ten previous question strings")
        active_mode = self.config.mode(mode)
        client, started, events = Client(self.config), time.perf_counter(), []
        def emit(event):
            event = {**event, "elapsed_ms": round((time.perf_counter()-started)*1000)}
            events.append(event)
            if on_event:
                on_event(event)
        decision = self.route(question, history, mode, router, client)
        emit({"type": "plan", "route": decision})
        if not decision["agents"]:
            result = {"status": "rejected" if decision.get("rejected") else "not_supported", "mode": active_mode,
                      "message": decision["reason"], "route": decision, "called_agents": [], "events": events}
            if on_event: on_event({"type": "result", "result": result})
            return result
        previous = history[-1] if history and re.search(r"这些|那|上述|继续|进一步|优先", question) else ""
        hits = self.agent_evidence(question + " " + previous)
        if previous and prior_result:
            existing = {h["id"] for h in hits}
            for ref in prior_result.get("references", []):
                chunk = self.site_index.by_id.get(ref["id"])
                if chunk and chunk.id not in existing:
                    hits.append({**asdict(chunk), "score": 0, "retrieval_channel": "validated_prior_result"})
                    existing.add(chunk.id)
        missing = unknown_fact_request(question, hits)
        if missing:
            result = {"status": "insufficient_evidence", "mode": active_mode, "message": "官网资料未提供：" + "、".join(missing),
                      "route": decision, "called_agents": [], "references": reference_list(hits), "events": events}
            if on_event: on_event({"type": "result", "result": result})
            return result
        state, intermediate, validations = {}, [], []
        if previous and prior_result:
            prior_questions = prior_result.get("integrated", {}).get("candidate_questions", [])
            if prior_questions:
                state["previous_user_questions"] = {"questions": prior_questions, "status": "hypotheses_to_validate"}
        for step in decision["plan"]:
            name, agent_started = step["agent"], time.perf_counter()
            dependencies = {p: state[p] for p in REGISTRY[name].dependencies}
            if name == "content_strategy" and "user_questions" in state:
                dependencies["user_questions"] = state["user_questions"]
            elif name == "content_strategy" and "previous_user_questions" in state:
                dependencies["previous_user_questions"] = state["previous_user_questions"]
            emit({"type": "agent_started", "agent": name, "label": step["label"], "depends_on": list(dependencies)})
            if active_mode == "live":
                user = json.dumps({"question": question, "previous_question": previous, "upstream_results": dependencies,
                                   "evidence": context_from_hits(hits)}, ensure_ascii=False)
                value = client.json(prompt(name), user, lambda x: validate_agent(name, x, hits), purpose="agent:" + name)
            else:
                value = self.offline_agent(name, hits, state, question + " " + previous)
            validation = validate_agent(name, value, hits)
            state[name] = value
            validations.append({"agent": name, **validation})
            entry = {"agent": name, "label": step["label"], "result": value,
                     "input_dependencies": list(dependencies),
                     "duration_ms": round((time.perf_counter()-agent_started)*1000)}
            intermediate.append(entry)
            emit({"type": "agent_completed", **entry})
        integrated = {"summary": state["website_analysis"]["summary"]}
        if "geo_diagnosis" in decision["agents"]: integrated["findings"] = state["geo_diagnosis"]["findings"]
        if "user_questions" in decision["agents"]: integrated["candidate_questions"] = state["user_questions"]["questions"]
        if "content_strategy" in decision["agents"]: integrated["actions"] = state["content_strategy"]["actions"]
        all_ids = set().union(*(used_citations(value) for value in state.values()))
        result = {"status": "ok", "project": "geo_agents", "question": question, "mode": active_mode,
                  "model": self.config.model if active_mode == "live" else None, "route": decision,
                  "called_agents": [x["agent"] for x in intermediate], "intermediate_results": intermediate,
                  "integrated": integrated, "references": reference_list(hits, all_ids), "validation": validations,
                  "model_calls": client.calls, "events": events,
                  "scope": {"urls": [p["url"] for p in self.snapshot["pages"]],
                            "captured_at_utc": self.snapshot["captured_at_utc"], "method": "static HTML"},
                  "duration_ms": round((time.perf_counter()-started)*1000), "created_at_utc": now_utc(),
                  "limitations": ["离线模式执行真实检索与规则调度，但输出为确定性资料整理，不是模型生成。"] if active_mode == "offline" else
                                 ["诊断限于已抓取页面；引用校验不能证明语义蕴含，建议复核生成事实。"]}
        if on_event: on_event({"type": "result", "result": result})
        return result
