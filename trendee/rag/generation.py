"""Content-type specific schemas, validation, offline drafts and rendering."""
from __future__ import annotations

import re
from typing import Any, Sequence

from ..grounding import claims, validate_grounding




FORBIDDEN_SOURCE_META_PHRASES = (
    "资料显示",
    "资料中列出",
    "资料中提到",
    "资料提到",
    "资料指出",
    "根据资料",
    "品宣资料自述",
    "资料自述",
)


def _validate_publishable_style(value: dict[str, Any]) -> None:
    """Keep source-provenance language out of publishable body claims.

    Limitations are intentionally excluded because they are expected to state
    what the source material does not provide.
    """
    errors: list[str] = []
    for claim in claims(value):
        text = str(claim.get("text", ""))
        bad = [phrase for phrase in FORBIDDEN_SOURCE_META_PHRASES if phrase in text]
        if bad:
            errors.append("publishable claim contains source-meta wording: " + ", ".join(bad))
    if errors:
        raise ValueError("; ".join(errors[:5]))


def _claim(text: str, hit: dict[str, Any]) -> dict[str, Any]:
    return {"text": text, "citations": [hit["id"]]}


def _require_claim_list(value: dict[str, Any], key: str, non_empty: bool = True) -> None:
    items = value.get(key)
    if not isinstance(items, list) or (non_empty and not items):
        raise ValueError(f"{key} must be a {'non-empty ' if non_empty else ''}list")
    for item in items:
        if not isinstance(item, dict) or not {"text", "citations"} <= item.keys():
            raise ValueError(f"{key} must contain claim objects")


def _validate_sections(value: dict[str, Any], key: str = "sections", max_items: int = 8) -> None:
    sections = value.get(key)
    if not isinstance(sections, list) or not sections or len(sections) > max_items:
        raise ValueError(f"{key} must contain 1-{max_items} sections")
    for section in sections:
        if not isinstance(section, dict) or not section.get("heading"):
            raise ValueError(f"{key} sections need headings")
        paragraphs = section.get("paragraphs")
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ValueError(f"{key} sections need paragraphs")
        for item in paragraphs:
            if not isinstance(item, dict) or not {"text", "citations"} <= item.keys():
                raise ValueError(f"{key} paragraphs must be claim objects")


def _validate_faq(value: dict[str, Any], min_items: int = 0, max_items: int = 8) -> None:
    items = value.get("faq")
    if not isinstance(items, list) or not (min_items <= len(items) <= max_items):
        raise ValueError(f"faq must contain {min_items}-{max_items} items")
    for item in items:
        if not isinstance(item, dict) or not item.get("question"):
            raise ValueError("FAQ item needs question")
        answer = item.get("answer")
        if not isinstance(answer, dict) or not {"text", "citations"} <= answer.keys():
            raise ValueError("FAQ answer must be a claim object")


def _normalize_question(text: str) -> str:
    return re.sub(r"[？?！!。．.\s]+$", "", str(text).strip())


def _question_like(text: str) -> bool:
    value = str(text).strip()
    return bool(
        re.search(r"[？?]$", value)
        or re.search(r"为什么|什么|哪些|如何|怎么|是否|能否|有没有|多少|哪里|谁", value)
    )


def validate_document(
    content_type: str,
    value: dict[str, Any],
    hits: Sequence[dict[str, Any]],
    topic: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("title"), str) or not value["title"].strip():
        raise ValueError("document.title is required")
    limitations = value.get("limitations")
    if not isinstance(limitations, list):
        raise ValueError("document.limitations must be a list")

    if content_type == "blog":
        _require_claim_list(value, "lead")
        _validate_sections(value)
        _require_claim_list(value, "conclusion")
        _validate_faq(value, 3, 3)
    elif content_type == "faq":
        _require_claim_list(value, "intro")
        _validate_faq(value, 1, 6)
        _require_claim_list(value, "conclusion")
        if "sections" in value:
            raise ValueError("FAQ output must not contain article sections")
        if topic and _question_like(topic):
            first_question = value["faq"][0]["question"]
            if _normalize_question(first_question) != _normalize_question(topic):
                raise ValueError(
                    "FAQ first question must directly preserve the user's original question"
                )
    elif content_type == "brand_intro":
        _require_claim_list(value, "positioning")
        _require_claim_list(value, "value_propositions")
        _validate_sections(value, "capabilities", 6)
        _require_claim_list(value, "audiences")
        _require_claim_list(value, "proof_points", non_empty=False)
        _validate_faq(value, 3, 3)
    elif content_type == "product_intro":
        _require_claim_list(value, "summary")
        _require_claim_list(value, "pain_points", non_empty=False)
        _validate_sections(value, "capabilities", 6)
        _require_claim_list(value, "use_cases", non_empty=False)
        _require_claim_list(value, "boundaries", non_empty=False)
        _validate_faq(value, 3, 3)
    else:
        raise ValueError("Unsupported content type")
    _validate_publishable_style(value)
    return validate_grounding(value, list(hits))


def offline_document(content_type: str, topic: str, hits: Sequence[dict[str, Any]]) -> dict[str, Any]:
    chosen = list(hits[:4])
    if not chosen:
        raise ValueError("offline document requires evidence")
    first = chosen[0]
    limitations = ["离线草稿：未调用模型，仅用于验证工作流。", "正式发布前应复核品宣资料中的营销主张与统计口径。"]

    if content_type == "faq":
        faq = [
            {"question": topic, "answer": _claim(first["text"], first)}
        ]
        for h in chosen[1:4]:
            faq.append({
                "question": h.get("heading") or "补充问题",
                "answer": _claim(h["text"], h),
            })
        return {"title": topic, "intro": [_claim("以下回答围绕当前问题展开。", first)],
                "faq": faq, "conclusion": [_claim("以上回答围绕当前主题进行总结。", first)],
                "limitations": limitations}
    if content_type == "brand_intro":
        return {"title": topic, "positioning": [_claim(first["text"], first)],
                "value_propositions": [_claim(h["text"], h) for h in chosen[1:3] or [first]],
                "capabilities": [{"heading": h.get("heading") or "能力", "paragraphs": [_claim(h["text"], h)]} for h in chosen[:3]],
                "audiences": [_claim(chosen[-1]["text"], chosen[-1])],
                "proof_points": [],
                "faq": [
                    {"question": "品牌主要解决什么问题？", "answer": _claim(chosen[0]["text"], chosen[0])},
                    {"question": "品牌具备哪些核心能力？", "answer": _claim(chosen[min(1, len(chosen)-1)]["text"], chosen[min(1, len(chosen)-1)])},
                    {"question": "品牌适合哪些组织关注？", "answer": _claim(chosen[-1]["text"], chosen[-1])},
                ],
                "limitations": limitations}
    if content_type == "product_intro":
        return {"title": topic, "summary": [_claim(first["text"], first)],
                "pain_points": [_claim(h["text"], h) for h in chosen[:2]],
                "capabilities": [{"heading": h.get("heading") or "能力", "paragraphs": [_claim(h["text"], h)]} for h in chosen[:3]],
                "use_cases": [_claim(chosen[-1]["text"], chosen[-1])],
                "boundaries": [],
                "faq": [
                    {"question": "产品主要解决什么问题？", "answer": _claim(chosen[0]["text"], chosen[0])},
                    {"question": "产品有哪些核心能力？", "answer": _claim(chosen[min(1, len(chosen)-1)]["text"], chosen[min(1, len(chosen)-1)])},
                    {"question": "产品适合哪些使用场景？", "answer": _claim(chosen[-1]["text"], chosen[-1])},
                ],
                "limitations": limitations}

    return {"title": topic,
            "lead": [_claim("本文围绕当前主题展开。", first)],
            "sections": [{"heading": h.get("heading") or "资料要点", "paragraphs": [_claim(h["text"], h)]} for h in chosen],
            "faq": [
                {"question": "这一主题最核心的问题是什么？", "answer": _claim(chosen[0]["text"], chosen[0])},
                {"question": "企业可以从哪些能力入手？", "answer": _claim(chosen[min(1, len(chosen)-1)]["text"], chosen[min(1, len(chosen)-1)])},
                {"question": "实施时还需要关注什么？", "answer": _claim(chosen[-1]["text"], chosen[-1])},
            ], "conclusion": [_claim("以上要点共同构成当前主题的核心结论。", first)],
            "limitations": limitations}


def render_markdown(content_type: str, value: dict[str, Any], refs: Sequence[dict[str, Any]]) -> str:
    locations = {r["id"]: f"PDF p.{r['page']} / {r['id']}" for r in refs}
    def paragraph(item: dict[str, Any]) -> str:
        citations = " ".join(f"[{locations.get(i, i)}]" for i in item["citations"])
        return (item["text"] + (" " + citations if citations else "")).strip()
    lines = ["# " + value["title"], ""]

    if content_type == "blog":
        lines.extend(paragraph(x) + "\n" for x in value["lead"])
        for section in value["sections"]:
            lines.extend(["## " + section["heading"], ""])
            lines.extend(paragraph(x) + "\n" for x in section["paragraphs"])
        lines.extend(["## 结语", ""])
        lines.extend(paragraph(x) + "\n" for x in value["conclusion"])
        lines.extend(["## 延展 FAQ", ""])
        for item in value["faq"]:
            lines.extend(["### " + item["question"], "", paragraph(item["answer"]), ""])
    elif content_type == "faq":
        lines.extend(paragraph(x) + "\n" for x in value["intro"])
        for item in value["faq"]:
            lines.extend(["## " + item["question"], "", paragraph(item["answer"]), ""])
        lines.extend(["## 结语", ""])
        lines.extend(paragraph(x) + "\n" for x in value["conclusion"])
    elif content_type == "brand_intro":
        for heading, key in [
            ("品牌定位", "positioning"), ("核心价值", "value_propositions"),
            ("服务对象", "audiences"), ("可信信息", "proof_points"),
        ]:
            if value.get(key):
                lines.extend(["## " + heading, ""])
                lines.extend(paragraph(x) + "\n" for x in value[key])
        lines.extend(["## 核心能力", ""])
        for section in value["capabilities"]:
            lines.extend(["### " + section["heading"], ""])
            lines.extend(paragraph(x) + "\n" for x in section["paragraphs"])
        lines.extend(["## 延展 FAQ", ""])
        for item in value["faq"]:
            lines.extend(["### " + item["question"], "", paragraph(item["answer"]), ""])
    else:
        for heading, key in [
            ("产品定位", "summary"), ("用户问题", "pain_points"),
            ("使用场景", "use_cases"), ("适用边界", "boundaries"),
        ]:
            lines.extend(["## " + heading, ""])
            lines.extend(paragraph(x) + "\n" for x in value[key])
        lines.extend(["## 核心能力", ""])
        for section in value["capabilities"]:
            lines.extend(["### " + section["heading"], ""])
            lines.extend(paragraph(x) + "\n" for x in section["paragraphs"])
        lines.extend(["## 延展 FAQ", ""])
        for item in value["faq"]:
            lines.extend(["### " + item["question"], "", paragraph(item["answer"]), ""])

    if value.get("limitations"):
        lines.extend(["## 资料与限制", "", *["- " + str(x) for x in value["limitations"]]])
    return "\n".join(lines)
