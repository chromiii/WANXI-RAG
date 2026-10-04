"""Task-intent parsing for the Project 1 writing workflow."""
from __future__ import annotations

import re
from typing import Any

CONTENT_TYPES = {
    "blog": "Blog",
    "faq": "FAQ",
    "brand_intro": "品牌介绍",
    "product_intro": "产品介绍",
}
ALIASES = {
    "blog": "blog", "Blog": "blog", "文章": "blog", "官网Blog": "blog",
    "faq": "faq", "FAQ": "faq", "问答": "faq",
    "brand_intro": "brand_intro", "品牌介绍": "brand_intro", "公司介绍": "brand_intro",
    "product_intro": "product_intro", "产品介绍": "product_intro",
    "auto": "auto", "自动": "auto", "": "auto",
}

RETRIEVAL_NEEDS = {
    "blog": [
        "直接支持主题的背景与原因",
        "与主题相关的万悉/GEO业务事实",
        "可支撑正文主张的能力或方法",
    ],
    "faq": [
        "能够直接回答用户问题的事实",
        "回答所需的定义、能力、场景或边界",
        "必要的限制与可核验依据",
    ],
    "brand_intro": [
        "品牌/公司定位与愿景",
        "核心价值与解决的问题",
        "核心能力",
        "服务对象",
        "可核验的公司信息或可信依据",
    ],
    "product_intro": [
        "产品名称与产品定位",
        "产品解决的用户问题",
        "产品核心能力与功能",
        "使用场景与适用对象",
        "产品边界、未覆盖信息或限制",
    ],
}


def canonical_content_type(value: str | None) -> str:
    key = "" if value is None else str(value).strip()
    if key not in ALIASES:
        raise ValueError("content_type must be auto, Blog, FAQ, 品牌介绍 or 产品介绍")
    return ALIASES[key]


def retrieval_needs(content_type: str) -> list[str]:
    return list(RETRIEVAL_NEEDS[canonical_content_type(content_type)])


def retrieval_seed_queries(content_type: str) -> list[str]:
    """High-value schema coverage queries for structured introductions.

    Blog/FAQ stay topic-driven. Brand/product introductions need evidence for
    multiple schema fields, so deterministic seeds prevent the exact user
    wording from collapsing retrieval onto only one facet.
    """
    value = canonical_content_type(content_type)
    if value == "product_intro":
        return [
            "万悉科技 Trendee 产品定位 核心产品 GEO",
            "万悉科技 Trendee 产品能力 功能 解决问题",
            "万悉科技 Trendee 使用场景 服务对象 产品边界",
        ]
    if value == "brand_intro":
        return [
            "万悉科技 品牌定位 公司定位 愿景 核心价值",
            "万悉科技 核心能力 服务对象",
            "万悉科技 品牌介绍 可信信息 公司信息",
        ]
    return []


def _rule_intent(topic: str) -> str | None:
    text = topic.strip()
    if re.search(r"\bFAQ\b|常见问题|问答|答疑|问题清单|问题列表", text, re.I):
        return "faq"
    if re.search(r"品牌介绍|公司介绍|企业介绍|万悉科技.{0,8}(是谁|做什么|简介)", text, re.I):
        return "brand_intro"
    if re.search(r"产品介绍|产品能力|产品功能|核心功能|解决方案|服务能力", text, re.I):
        return "product_intro"
    if re.search(r"\bblog\b|博客|文章|指南|解读|趋势|为什么|如何|怎么", text, re.I):
        return "blog"
    return None


def _intent_payload(
    content_type: str,
    topic: str,
    audience: str,
    goal: str,
    source: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "content_type": content_type,
        "content_type_label": CONTENT_TYPES[content_type],
        "topic": topic.strip(),
        "audience": audience.strip(),
        "goal": goal,
        "retrieval_needs": list(RETRIEVAL_NEEDS[content_type]),
        "source": source,
        "reason": reason,
    }


def validate_task_intent(value: dict[str, Any], topic: str, audience: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("task intent must be a JSON object")
    content_type = canonical_content_type(value.get("content_type"))
    if content_type == "auto":
        raise ValueError("task intent must resolve content_type")
    goal = value.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("task_intent.goal is required")
    return _intent_payload(
        content_type,
        topic,
        audience,
        goal.strip()[:120],
        "llm",
        str(value.get("reason", "")).strip()[:300],
    )


def parse_task_intent(
    topic: str,
    audience: str,
    requested_type: str | None,
    active_mode: str,
    client=None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    requested = canonical_content_type(requested_type)
    if requested != "auto":
        return _intent_payload(
            requested,
            topic,
            audience,
            "generate_requested_content_type",
            "explicit",
            "用户显式指定内容类型；检索目标同时覆盖该内容类型所需字段。",
        )

    ruled = _rule_intent(topic)
    if ruled:
        return _intent_payload(
            ruled,
            topic,
            audience,
            "generate_content_from_topic_intent",
            "rule",
            "根据题目中的明显写作意图词识别内容类型。",
        )

    if active_mode == "live" and client is not None and system_prompt:
        raw = client.json(
            system_prompt,
            __import__("json").dumps({"topic": topic, "audience": audience}, ensure_ascii=False),
            lambda value: validate_task_intent(value, topic, audience),
            purpose="task_intent",
        )
        return validate_task_intent(raw, topic, audience)

    return _intent_payload(
        "blog",
        topic,
        audience,
        "generate_general_brand_content",
        "offline_default",
        "离线且无明确类型时使用 Blog 作为保守默认。",
    )
