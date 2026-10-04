"""LLM-backed task intent parsing for Project 1 RAG.

Intent understanding and query reformulation are deliberately separated:
- this module determines presentation type, semantic focus and user goal;
- query_planner.py decides whether retrieval should passthrough, rewrite,
  expand or decompose the original query.

No business entity or topic keyword rules are used for semantic classification.
"""
from __future__ import annotations

import json
from typing import Any


CONTENT_TYPES = {
    "blog": "Blog",
    "faq": "FAQ",
    "brand_intro": "品牌介绍",
    "product_intro": "产品介绍",
}
ALIASES = {
    "blog": "blog",
    "Blog": "blog",
    "文章": "blog",
    "官网Blog": "blog",
    "faq": "faq",
    "FAQ": "faq",
    "问答": "faq",
    "brand_intro": "brand_intro",
    "品牌介绍": "brand_intro",
    "公司介绍": "brand_intro",
    "product_intro": "product_intro",
    "产品介绍": "product_intro",
    "auto": "auto",
    "自动": "auto",
    "": "auto",
}


def canonical_content_type(value: str | None) -> str:
    key = "" if value is None else str(value).strip()
    if key not in ALIASES:
        raise ValueError("content_type must be auto, Blog, FAQ, 品牌介绍 or 产品介绍")
    return ALIASES[key]


def _payload(
    *,
    content_type: str,
    topic: str,
    audience: str,
    semantic_focus: str,
    user_goal: str,
    confidence: float,
    source: str,
    reason: str,
    presentation_source: str,
) -> dict[str, Any]:
    return {
        "content_type": content_type,
        "content_type_label": CONTENT_TYPES[content_type],
        "topic": topic.strip(),
        "primary_question": topic.strip(),
        "semantic_focus": semantic_focus.strip() or "generic",
        "user_goal": user_goal.strip() or topic.strip(),
        # goal is kept as a compatibility alias for existing UI/log consumers.
        "goal": user_goal.strip() or topic.strip(),
        "audience": audience.strip(),
        "confidence": max(0.0, min(1.0, float(confidence))),
        "source": source,
        "presentation_source": presentation_source,
        "reason": reason.strip()[:400],
    }


def validate_task_intent(
    value: dict[str, Any],
    topic: str,
    audience: str,
    requested_type: str = "auto",
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("task intent must be a JSON object")

    requested = canonical_content_type(requested_type)
    predicted = canonical_content_type(value.get("content_type"))
    if predicted == "auto":
        raise ValueError("task intent must resolve content_type")

    # Explicit UI selection is an immutable presentation contract. The model
    # may analyze semantic focus, but it cannot override the requested format.
    content_type = requested if requested != "auto" else predicted

    semantic_focus = value.get("semantic_focus")
    if not isinstance(semantic_focus, str) or not semantic_focus.strip():
        raise ValueError("task_intent.semantic_focus is required")

    user_goal = value.get("user_goal") or value.get("goal")
    if not isinstance(user_goal, str) or not user_goal.strip():
        raise ValueError("task_intent.user_goal is required")

    confidence = value.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        raise ValueError("task_intent.confidence must be numeric")

    return _payload(
        content_type=content_type,
        topic=topic,
        audience=audience,
        semantic_focus=semantic_focus[:120],
        user_goal=user_goal[:240],
        confidence=float(confidence),
        source="llm+explicit" if requested != "auto" else "llm",
        presentation_source="explicit" if requested != "auto" else "auto",
        reason=str(value.get("reason", "")).strip(),
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

    if active_mode == "live" and client is not None and system_prompt:
        request = {
            "topic": topic,
            "audience": audience,
            "requested_content_type": None if requested == "auto" else requested,
            "allowed_content_types": list(CONTENT_TYPES),
        }
        raw = client.json(
            system_prompt,
            json.dumps(request, ensure_ascii=False),
            lambda value: validate_task_intent(
                value,
                topic,
                audience,
                requested_type=requested,
            ),
            purpose="task_intent",
        )
        return validate_task_intent(
            raw,
            topic,
            audience,
            requested_type=requested,
        )

    # Offline mode intentionally does not pretend to perform semantic
    # understanding. It exists for deterministic pipeline regression tests.
    if requested != "auto":
        return _payload(
            content_type=requested,
            topic=topic,
            audience=audience,
            semantic_focus="generic",
            user_goal=topic,
            confidence=1.0,
            source="explicit",
            presentation_source="explicit",
            reason="用户显式指定呈现类型；离线模式不进行语义意图推断。",
        )

    return _payload(
        content_type="blog",
        topic=topic,
        audience=audience,
        semantic_focus="generic",
        user_goal=topic,
        confidence=0.0,
        source="offline_default",
        presentation_source="offline_default",
        reason="离线模式不进行语义意图推断；仅使用 Blog 作为确定性演示默认格式。",
    )
