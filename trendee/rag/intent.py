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


def canonical_content_type(value: str | None) -> str:
    key = "" if value is None else str(value).strip()
    if key not in ALIASES:
        raise ValueError("content_type must be auto, Blog, FAQ, 品牌介绍 or 产品介绍")
    return ALIASES[key]


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


def validate_task_intent(value: dict[str, Any], topic: str, audience: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("task intent must be a JSON object")
    content_type = canonical_content_type(value.get("content_type"))
    if content_type == "auto":
        raise ValueError("task intent must resolve content_type")
    goal = value.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("task_intent.goal is required")
    return {
        "content_type": content_type,
        "content_type_label": CONTENT_TYPES[content_type],
        "topic": topic.strip(),
        "audience": audience.strip(),
        "goal": goal.strip()[:120],
        "source": "llm",
        "reason": str(value.get("reason", "")).strip()[:300],
    }


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
        return {
            "content_type": requested,
            "content_type_label": CONTENT_TYPES[requested],
            "topic": topic.strip(),
            "audience": audience.strip(),
            "goal": "generate_requested_content_type",
            "source": "explicit",
            "reason": "用户显式指定内容类型。",
        }

    ruled = _rule_intent(topic)
    if ruled:
        return {
            "content_type": ruled,
            "content_type_label": CONTENT_TYPES[ruled],
            "topic": topic.strip(),
            "audience": audience.strip(),
            "goal": "generate_content_from_topic_intent",
            "source": "rule",
            "reason": "根据题目中的明显写作意图词识别内容类型。",
        }

    if active_mode == "live" and client is not None and system_prompt:
        raw = client.json(
            system_prompt,
            __import__("json").dumps({"topic": topic, "audience": audience}, ensure_ascii=False),
            lambda value: validate_task_intent(value, topic, audience),
            purpose="task_intent",
        )
        return validate_task_intent(raw, topic, audience)

    return {
        "content_type": "blog",
        "content_type_label": "Blog",
        "topic": topic.strip(),
        "audience": audience.strip(),
        "goal": "generate_general_brand_content",
        "source": "offline_default",
        "reason": "离线且无明确类型时使用 Blog 作为保守默认。",
    }
