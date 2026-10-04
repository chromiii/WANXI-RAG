"""Generic evidence sufficiency gate for Project 1 RAG."""
from __future__ import annotations

import json
from typing import Any, Sequence


def validate_evidence_sufficiency(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("evidence sufficiency result must be a JSON object")
    if not isinstance(value.get("answerable"), bool):
        raise ValueError("answerable must be boolean")
    missing = value.get("missing_information")
    if not isinstance(missing, list) or any(not isinstance(x, str) for x in missing):
        raise ValueError("missing_information must be a list of strings")
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason is required")
    return {
        "answerable": value["answerable"],
        "missing_information": [x.strip() for x in missing if x.strip()][:8],
        "reason": reason.strip()[:500],
    }


def assess_evidence_sufficiency(
    *,
    topic: str,
    user_goal: str,
    hits: Sequence[dict[str, Any]],
    active_mode: str,
    client,
    system_prompt: str,
) -> dict[str, Any]:
    if not hits:
        return {
            "answerable": False,
            "missing_information": ["未检索到相关证据"],
            "reason": "没有可供回答的检索证据。",
            "source": "deterministic",
        }

    if active_mode != "live":
        return {
            "answerable": True,
            "missing_information": [],
            "reason": "离线模式不执行语义充分性判断；仅验证后续工作流。",
            "source": "offline_passthrough",
        }

    evidence = []
    for hit in list(hits)[:8]:
        evidence.append({
            "id": hit.get("id"),
            "page": hit.get("page"),
            "heading": hit.get("heading"),
            "text": str(hit.get("text") or "")[:1400],
        })
    raw = client.json(
        system_prompt,
        json.dumps({
            "topic": topic,
            "user_goal": user_goal,
            "evidence": evidence,
        }, ensure_ascii=False),
        validate_evidence_sufficiency,
        purpose="evidence_sufficiency",
    )
    result = validate_evidence_sufficiency(raw)
    result["source"] = "llm"
    return result
