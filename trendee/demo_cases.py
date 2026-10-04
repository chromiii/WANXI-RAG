"""Shared Project 1 demo/acceptance case catalog."""
from __future__ import annotations

import json
from typing import Any

from .config import ROOT


CASE_FILE = ROOT / "eval" / "project1_cases.json"


def load_project1_cases() -> list[dict[str, Any]]:
    value = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Project 1 case catalog must be a JSON array")
    return value


def ui_project1_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": case["id"],
            "label": case.get("label", case["id"]),
            "topic": case["topic"],
            "content_type": case.get("content_type", "auto"),
        }
        for case in load_project1_cases()
        if case.get("show_in_ui")
    ]


def demo_project1_cases() -> list[dict[str, Any]]:
    return [case for case in load_project1_cases() if case.get("demo")]
