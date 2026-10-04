"""Query-conditioned evidence policy for Project 1 RAG.

Retrieval relevance and generation usefulness are different concerns. This
module classifies each retrieved chunk by:
1) evidence_type: what kind of source claim it contains;
2) priority: how useful it is for the current query.

The policy is deterministic and does not add another LLM call.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Sequence


PRIORITY_ORDER = {"core": 0, "supporting": 1, "low_priority": 2, "excluded": 3}

FOCUS_TERMS = {
    "customer_pain_points": (
        "问题", "痛点", "难点", "挑战", "信息复杂", "口径分散", "组织协同",
        "信息孤岛", "知识治理", "知识资产", "可见性", "需求",
    ),
    "geo_value": (
        "可见性", "AI问答", "AI 搜索", "引用", "理解", "知识资产", "结构化",
        "品牌", "需求", "连接", "搜索匹配", "可信",
    ),
    "product_capabilities": (
        "能力", "功能", "监测", "追踪", "优化", "结构化", "诊断", "策略",
        "内容体系", "知识资产", "数据标准",
    ),
    "brand_positioning": (
        "定位", "愿景", "使命", "品牌", "公司", "Trendee", "万悉", "连接", "可见性",
    ),
    "industries": (
        "行业", "电商", "零售", "时尚", "制造", "机械", "SaaS", "化工",
        "物流", "金融", "餐饮", "教育",
    ),
    "compliance": ("合规", "可信", "真实价值", "标杆", "规范", "透明"),
    "case": ("案例", "客户", "项目", "合作", "服务", "招商银行"),
    "metrics": ("数据", "效果", "增长", "提升", "比例", "转化", "覆盖率", "推荐率"),
}


def classify_query_focus(topic: str, retrieval_intent: str = "") -> str:
    text = f"{topic} {retrieval_intent}".strip()
    rules = [
        ("customer_pain_points", r"解决.{0,8}问题|什么问题|痛点|难点|挑战|customer[_ ]?pain"),
        ("industries", r"哪些行业|什么行业|服务行业|行业覆盖|适合哪些|客户类型"),
        ("compliance", r"合规|可信|标杆|规范"),
        ("case", r"案例|客户案例|合作客户|招商银行|项目经验"),
        ("metrics", r"效果|增长|提升多少|数据|比例|推荐率|转化"),
        ("product_capabilities", r"产品能力|产品功能|核心能力|服务能力|有哪些功能|如何帮助|怎么帮助"),
        ("brand_positioning", r"品牌介绍|公司介绍|企业介绍|是谁|定位|愿景|做什么"),
        ("geo_value", r"为什么.{0,12}GEO|GEO.{0,12}为什么|需要.{0,12}GEO|GEO.{0,12}价值|必要性"),
    ]
    for focus, pattern in rules:
        if re.search(pattern, text, re.I):
            return focus
    return "generic"


def classify_evidence_type(hit: dict[str, Any]) -> str:
    heading = str(hit.get("heading") or "")
    text = str(hit.get("text") or hit.get("content") or "")
    combined = heading + "\n" + text

    if re.search(r"设想|假设场景|概念方案|拟议|模拟场景", combined):
        return "hypothetical"
    if re.search(r"媒体|报道|新闻|专访|采访|获奖|奖项|荣誉|入选", combined):
        return "media"
    if re.search(r"创始人|CEO|核心团队|团队成员|顾问|专家团队", combined, re.I):
        return "profile"
    if re.search(r"客户案例|合作案例|已服务|合作客户|项目经验", combined):
        return "case"
    if re.search(r"\d+(?:\.\d+)?[%％]|增长率|提升率|覆盖率|推荐率|转化率", combined):
        return "metric"
    if re.search(r"行业.{0,6}标杆|领先|首创|唯一|第一|长期记忆|深度记忆", combined):
        return "marketing_claim"
    return "factual"


def _hypothetical_subject(hit: dict[str, Any]) -> str:
    heading = str(hit.get("heading") or "")
    text = str(hit.get("text") or hit.get("content") or "")
    combined = heading + "\n" + text
    match = re.search(r"面向\s*([^\n：:，,]{2,30}?)\s*的.{0,20}(?:设想|方案)", combined)
    return match.group(1).strip() if match else ""


def _focus_matches(hit: dict[str, Any], focus: str) -> list[str]:
    if focus == "generic":
        return []
    combined = (str(hit.get("heading") or "") + "\n" + str(hit.get("text") or hit.get("content") or "")).lower()
    return [term for term in FOCUS_TERMS.get(focus, ()) if term.lower() in combined]


def _reranker_score(hit: dict[str, Any]) -> float:
    value = hit.get("reranker_score", hit.get("score", 0.0))
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def evaluate_evidence(
    hits: Sequence[dict[str, Any]],
    topic: str,
    retrieval_intent: str = "",
) -> dict[str, Any]:
    """Assign query-conditioned priority and evidence type to retrieved hits."""
    focus = classify_query_focus(topic, retrieval_intent)
    decisions: list[dict[str, Any]] = []

    for fallback_rank, hit in enumerate(hits, 1):
        evidence_type = classify_evidence_type(hit)
        rank = int(hit.get("rank") or fallback_rank)
        score = _reranker_score(hit)
        matches = _focus_matches(hit, focus)
        reason_parts: list[str] = []

        if evidence_type == "hypothetical":
            subject = _hypothetical_subject(hit)
            explicitly_requested = (
                "设想" in topic
                or "假设" in topic
                or (subject and subject.lower() in topic.lower())
            )
            if not explicitly_requested:
                priority = "excluded"
                reason_parts.append("应用设想未被当前主题明确请求")
            else:
                priority = "core" if rank <= 4 else "supporting"
                reason_parts.append("当前主题明确请求该应用设想")
        elif evidence_type in {"media", "profile"} and focus not in {"brand_positioning", "case"}:
            priority = "low_priority"
            reason_parts.append(f"{evidence_type} 证据不直接回答当前 {focus} 意图")
        elif focus == "industries" and any(term in (str(hit.get("heading") or "") + str(hit.get("text") or "")) for term in FOCUS_TERMS["industries"]):
            priority = "core"
            reason_parts.append("直接支持行业/服务对象问题")
        elif focus != "generic" and len(matches) >= 2:
            priority = "core"
            reason_parts.append("直接命中当前意图的多个语义信号")
        elif focus != "generic" and len(matches) == 1 and rank <= 4:
            priority = "core"
            reason_parts.append("命中当前意图且位于高相关候选")
        elif focus != "generic" and matches:
            priority = "supporting"
            reason_parts.append("与当前意图相关，可作为补充证据")
        elif evidence_type == "marketing_claim":
            priority = (
                "supporting"
                if focus in {"brand_positioning", "compliance"} or score >= 0.45
                else "low_priority"
            )
            reason_parts.append("营销主张不能作为独立事实；仅在主题相关度足够时作为补充证据")
        elif rank <= 2 or score >= 0.45:
            priority = "supporting"
            reason_parts.append("语义相关度较高，但不是当前意图的直接证据")
        else:
            priority = "low_priority"
            reason_parts.append("与主题有一定相关性，但不应主导生成")

        decisions.append({
            "id": hit.get("id"),
            "page": hit.get("page"),
            "heading": hit.get("heading"),
            "priority": priority,
            "evidence_type": evidence_type,
            "focus": focus,
            "matched_signals": matches[:8],
            "reranker_score": round(score, 6),
            "rank": rank,
            "reason": "；".join(reason_parts),
        })

    # A generic or difficult query can have no rule-level CORE even when the
    # reranker found good evidence. Promote the best safe candidate so the
    # policy does not over-prune useful context.
    if decisions and not any(d["priority"] == "core" for d in decisions):
        candidates = [d for d in decisions if d["priority"] in {"supporting", "low_priority"}]
        if candidates:
            best = min(
                candidates,
                key=lambda d: (
                    PRIORITY_ORDER[d["priority"]],
                    d["rank"],
                    -d["reranker_score"],
                ),
            )
            best["priority"] = "core"
            best["reason"] += "；无其他 CORE，提升为本轮核心证据"

    counts = Counter(d["priority"] for d in decisions)
    type_counts = Counter(d["evidence_type"] for d in decisions)
    return {
        "focus": focus,
        "decisions": sorted(
            decisions,
            key=lambda d: (PRIORITY_ORDER[d["priority"]], d["rank"], d["id"] or ""),
        ),
        "priority_counts": {
            key: counts.get(key, 0)
            for key in ("core", "supporting", "low_priority", "excluded")
        },
        "type_counts": dict(sorted(type_counts.items())),
    }


def selected_ids(policy: dict[str, Any]) -> list[str]:
    return [
        item["id"]
        for item in policy.get("decisions", [])
        if item.get("priority") in {"core", "supporting"} and item.get("id")
    ]
