"""Task-intent parsing for the Project 1 writing workflow.

The user's semantic objective and the requested presentation format are kept
separate. Content type controls presentation; it must not replace the original
question as the primary retrieval/generation objective.
"""
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

FORMAT_NEEDS = {
    "blog": ["主题背景", "核心论点", "相关业务事实或能力"],
    "faq": ["直接回答原问题的事实", "必要的定义/能力/边界"],
    "brand_intro": ["品牌定位", "核心价值", "相关能力", "服务对象"],
    "product_intro": ["产品定位", "与原问题相关的产品能力", "相关使用场景"],
}

FOCUS_NEEDS = {
    "customer_pain_points": [
        "客户面临的具体问题、痛点或业务挑战",
        "万悉/Trendee如何解决这些问题",
    ],
    "product_capabilities": [
        "与原问题直接相关的产品能力或功能",
        "能力对应的用户价值或解决的问题",
    ],
    "brand_positioning": [
        "品牌/公司定位",
        "品牌核心价值与解决的问题",
    ],
    "geo_value": [
        "为什么需要GEO的直接原因",
        "GEO带来的业务价值与相关能力",
    ],
    "industries": [
        "服务行业或适用对象",
        "行业对应的场景或需求",
    ],
    "compliance": [
        "合规GEO的定义/原则",
        "与合规相关的可核验表述",
    ],
    "case": [
        "用户明确询问的案例或场景",
        "案例性质、是否为真实合作或应用设想",
    ],
    "generic": ["能够直接回答用户原问题的资料"],
}


def canonical_content_type(value: str | None) -> str:
    key = "" if value is None else str(value).strip()
    if key not in ALIASES:
        raise ValueError("content_type must be auto, Blog, FAQ, 品牌介绍 or 产品介绍")
    return ALIASES[key]


def semantic_focus(topic: str) -> str:
    text = topic.strip()
    rules = [
        ("customer_pain_points", r"解决.{0,8}问题|什么问题|痛点|难点|挑战"),
        ("industries", r"哪些行业|什么行业|服务行业|行业覆盖|适合哪些|客户类型"),
        ("compliance", r"合规|可信|标杆|规范"),
        ("case", r"案例|客户案例|合作客户|招商银行|项目经验|应用设想"),
        ("product_capabilities", r"产品能力|产品功能|核心功能|核心能力|服务能力|有哪些功能"),
        ("brand_positioning", r"品牌介绍|公司介绍|企业介绍|是谁|定位|愿景|做什么"),
        ("geo_value", r"为什么.{0,12}GEO|GEO.{0,12}为什么|需要.{0,12}GEO|GEO.{0,12}价值|必要性"),
    ]
    for focus, pattern in rules:
        if re.search(pattern, text, re.I):
            return focus
    return "generic"


def _rule_intent(topic: str) -> str | None:
    text = topic.strip()
    if re.search(r"FAQ|常见问题|问答|答疑|问题清单|问题列表", text, re.I):
        return "faq"
    if re.search(r"品牌介绍|公司介绍|企业介绍|万悉科技.{0,8}(是谁|做什么|简介)", text, re.I):
        return "brand_intro"
    if re.search(r"产品介绍|产品能力|产品功能|核心功能|解决方案|服务能力", text, re.I):
        return "product_intro"
    if re.search(r"\bblog\b|博客|文章|指南|解读|趋势|为什么|如何|怎么", text, re.I):
        return "blog"
    return None


def retrieval_seed_queries(content_type: str, focus: str) -> list[str]:
    """Small deterministic recall hints; the original question remains primary."""
    value = canonical_content_type(content_type)
    if value == "product_intro":
        if focus == "customer_pain_points":
            return [
                "万悉科技 Trendee 客户痛点 产品能力 解决问题",
                "万悉科技 Trendee 产品定位 与客户问题相关能力",
            ]
        if focus == "product_capabilities":
            return [
                "万悉科技 Trendee 产品定位 核心能力 功能",
                "万悉科技 Trendee 产品能力 使用场景",
            ]
        return ["万悉科技 Trendee 产品定位 核心能力"]
    if value == "brand_intro":
        if focus == "customer_pain_points":
            return ["万悉科技 品牌定位 客户问题 核心价值"]
        return ["万悉科技 品牌定位 核心价值 服务对象"]
    return []


def _intent_payload(
    content_type: str,
    topic: str,
    audience: str,
    goal: str,
    source: str,
    reason: str,
) -> dict[str, Any]:
    focus = semantic_focus(topic)
    primary_needs = list(FOCUS_NEEDS[focus])
    format_needs = list(FORMAT_NEEDS[content_type])
    return {
        "content_type": content_type,
        "content_type_label": CONTENT_TYPES[content_type],
        "topic": topic.strip(),
        "primary_question": topic.strip(),
        "semantic_focus": focus,
        "audience": audience.strip(),
        "goal": goal,
        "primary_retrieval_needs": primary_needs,
        "format_retrieval_needs": format_needs,
        "retrieval_needs": [*primary_needs, *format_needs],
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
            "answer_primary_topic_in_requested_format",
            "explicit",
            "用户显式指定呈现类型；原始主题仍是最高优先级语义目标。",
        )

    ruled = _rule_intent(topic)
    if ruled:
        return _intent_payload(
            ruled,
            topic,
            audience,
            "answer_primary_topic_in_inferred_format",
            "rule",
            "根据题目中的明显写作意图词识别呈现类型；不改变原始主题。",
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
        "answer_primary_topic_in_default_blog_format",
        "offline_default",
        "离线且无明确类型时使用 Blog 作为呈现形式，原始主题不变。",
    )
