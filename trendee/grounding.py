"""Deterministic citation/data guards. These are checks, not proof of semantic entailment."""
import re


def claims(value):
    if isinstance(value, dict):
        if "text" in value and "citations" in value:
            yield value
        for child in value.values():
            yield from claims(child)
    elif isinstance(value, list):
        for child in value:
            yield from claims(child)


def numbers(text):
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:[%％])?", text))


def validate_grounding(value, hits, require_claims=True):
    evidence = {x["id"]: x for x in hits}
    errors, count = [], 0
    for claim in claims(value):
        count += 1
        text, ids = claim["text"], claim["citations"]
        if not isinstance(text, str) or not text.strip():
            errors.append("claim.text must be a non-empty string")
            continue
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
            errors.append("every factual claim must carry a non-empty citations list")
            continue
        bad = [i for i in ids if i not in evidence]
        if bad:
            errors.append("unknown citations: " + ", ".join(bad))
            continue
        source = "\n".join(evidence[i]["text"] for i in ids)
        missing = numbers(text) - numbers(source)
        if missing:
            errors.append("numbers absent from cited evidence: " + ", ".join(sorted(missing)))
        if ("招商银行" in text and re.search(r"客户|合作|已服务|交付|帮助.*提升", text) and
                not re.search(r"设想|假设|拟|不能|不代表|并非", text)):
            errors.append("招商银行应用设想 cannot be asserted as an delivered client case")
        if (re.search(r"保证.{0,12}(第一|推荐|提升|增长)|一定.{0,8}(推荐|引用)|永久写入.*参数", text)
                and not re.search(r"不能|不保证|无法保证|并非|不代表", text)):
            errors.append("unsupported guarantee about AI recommendation or model memory")
    def walk(item):
        if isinstance(item, dict):
            if "evidence_ids" in item:
                ids = item["evidence_ids"]
                if not isinstance(ids, list) or not ids or any(i not in evidence for i in ids):
                    errors.append("evidence_ids must refer to retrieved evidence")
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    if require_claims and not count:
        errors.append("response contains no grounded claims")
    if errors:
        raise ValueError("; ".join(errors[:10]))
    return {"claim_count": count, "citation_ids_valid": True, "numeric_guard_passed": True,
            "semantic_entailment": "not independently verified",
            "note": "ID/数字一致性与已知误用检查通过；引用存在不等于观点已获独立验证。"}


def unknown_fact_request(query, hits):
    targets = ["营收", "融资金额", "估值", "员工总人数", "年利润", "ARR", "融资额"]
    requested = [w for w in targets if w.lower() in query.lower()]
    return [w for w in requested if not any(w.lower() in h["text"].lower() for h in hits)]


def injection_request(query):
    return bool(re.search(r"忽略.{0,12}(指令|规则|引用|要求)|伪造|编造.{0,10}(数据|案例|引用)|"
                          r"ignore.{0,20}(instruction|previous|rules)|reveal.{0,10}(key|secret)", query, re.I))


def reference_list(hits, used_ids=None):
    return [{"id": h["id"], "source": h["source"], "page": h.get("page"), "url": h.get("url"),
             "heading": h.get("heading"), "quote": h["text"], "score": h.get("score"),
             "captured_at_utc": h.get("captured_at_utc")}
            for h in hits if used_ids is None or h["id"] in used_ids]


def used_citations(value):
    result = {i for c in claims(value) for i in c["citations"]}
    def walk(item):
        if isinstance(item, dict):
            result.update(item.get("evidence_ids", []))
            for child in item.values(): walk(child)
        elif isinstance(item, list):
            for child in item: walk(child)
    walk(value)
    return result
