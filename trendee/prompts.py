"""Shared prompt loading utilities."""
from __future__ import annotations

from .config import ROOT


def load_prompt(name: str, include_common: bool = True) -> str:
    specific = (ROOT / f"prompts/{name}.md").read_text(encoding="utf-8")
    if not include_common:
        return specific
    common = (ROOT / "prompts/common.md").read_text(encoding="utf-8")
    return common + "\n\n" + specific
