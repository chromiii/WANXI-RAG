"""Content-type specific schemas, validation, offline drafts and rendering."""
from __future__ import annotations

from typing import Any, Sequence

from ..grounding import validate_grounding


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


def validate_document(content_type: str, value: dict[str, Any], hits: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("title"), str) or not value["title"].strip():
        raise ValueError("document.title is required")
    limitations = value.get("limitations")
    if not isinstance(limitations, list):
        raise ValueError("document.limitations must be a list")

    if content_type == "blog":
        _require_claim_list(value, "lead")
        _validate_sections(value)
        _validate_faq(value, 0, 5)
        _require_claim_list(value, "conclusion")
    elif content_type == "faq":
        _require_claim_list(value, "intro")
        _validate_faq(value, 3, 8)
        _require_claim_list(value, "conclusion")
        if "sections" in value:
            raise ValueError("FAQ output must not contain article sections")
    elif content_type == "brand_intro":
        _require_claim_list(value, "positioning")
        _require_claim_list(value, "value_propositions")
        _validate_sections(value, "capabilities", 6)
        _require_claim_list(value, "audiences")
        _require_claim_list(value, "proof_points", non_empty=False)
    elif content_type == "product_intro":
        _require_claim_list(value, "summary")
        _require_claim_list(value, "pain_points", non_empty=False)
        _validate_sections(value, "capabilities", 6)
        _require_claim_list(value, "use_cases", non_empty=False)
        _require_claim_list(value, "boundaries", non_empty=False)
    else:
        raise ValueError("Unsupported content type")
    return validate_grounding(value, list(hits))


def offline_document(content_type: str, topic: str, hits: Sequence[dict[str, Any]]) -> dict[str, Any]:
    chosen = list(hits[:4])
    if not chosen:
        raise ValueError("offline document requires evidence")
    first = chosen[0]
    limitations = ["离线草稿：未调用模型，仅用于验证工作流。", "正式发布前应复核品宣资料中的营销主张与统计口径。"]

    if content_type == "faq":
        faq = [
            {"question": h.get("heading") or topic, "answer": _claim("品宣资料自述：" + h["text"], h)}
            for h in chosen[:4]
        ]
        while len(faq) < 3:
            faq.append({"question": topic, "answer": _claim("品宣资料自述：" + first["text"], first)})
        return {"title": topic, "intro": [_claim("以下回答仅依据已检索的万悉品宣资料。", first)],
                "faq": faq, "conclusion": [_claim("以上回答均可回查对应 PDF 页。", first)],
                "limitations": limitations}
    if content_type == "brand_intro":
        return {"title": topic, "positioning": [_claim("品宣资料自述：" + first["text"], first)],
                "value_propositions": [_claim("品宣资料自述：" + h["text"], h) for h in chosen[1:3] or [first]],
                "capabilities": [{"heading": h.get("heading") or "能力", "paragraphs": [_claim("品宣资料自述：" + h["text"], h)]} for h in chosen[:3]],
                "audiences": [_claim("服务对象需以资料表述为准：" + chosen[-1]["text"], chosen[-1])],
                "proof_points": [], "limitations": limitations}
    if content_type == "product_intro":
        return {"title": topic, "summary": [_claim("品宣资料自述：" + first["text"], first)],
                "pain_points": [_claim("相关客户问题可从资料中归纳：" + h["text"], h) for h in chosen[:2]],
                "capabilities": [{"heading": h.get("heading") or "能力", "paragraphs": [_claim("品宣资料自述：" + h["text"], h)]} for h in chosen[:3]],
                "use_cases": [_claim("应用场景以资料为准：" + chosen[-1]["text"], chosen[-1])],
                "boundaries": [_claim("当前说明只覆盖已检索资料，不对未提供的效果作承诺。", first)],
                "limitations": limitations}

    return {"title": topic,
            "lead": [_claim("以下文章草稿仅依据已检索的万悉品宣资料。", first)],
            "sections": [{"heading": h.get("heading") or "资料要点", "paragraphs": [_claim("品宣资料自述：" + h["text"], h)]} for h in chosen],
            "faq": [], "conclusion": [_claim("上述内容均可回查原始 PDF。", first)],
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
        if value["faq"]:
            lines.extend(["## FAQ", ""])
            for item in value["faq"]:
                lines.extend(["### " + item["question"], "", paragraph(item["answer"]), ""])
        lines.extend(["## 结语", ""])
        lines.extend(paragraph(x) + "\n" for x in value["conclusion"])
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

    if value.get("limitations"):
        lines.extend(["## 资料与限制", "", *["- " + str(x) for x in value["limitations"]]])
    return "\n".join(lines)
