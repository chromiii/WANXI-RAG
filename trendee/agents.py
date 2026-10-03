from dataclasses import dataclass
import re


@dataclass(frozen=True)
class AgentSpec:
    name: str
    label: str
    responsibility: str
    dependencies: tuple[str, ...]


REGISTRY = {
    "website_analysis": AgentSpec("website_analysis", "官网信息分析", "提取品牌定位、能力、受众和官网摘要", ()),
    "geo_diagnosis": AgentSpec("geo_diagnosis", "GEO 内容诊断", "评估已抓取内容的表达、结构与可引用性", ("website_analysis",)),
    "user_questions": AgentSpec("user_questions", "客户问题生成", "生成有官网依据的目标客户候选问题", ("website_analysis",)),
    "content_strategy": AgentSpec("content_strategy", "内容行动策略", "把诊断结果转成可验收的内容任务", ("website_analysis", "geo_diagnosis")),
}
RULES = {
    "website_analysis": r"表达了什么|品牌定位|服务对象|产品能力|核心能力|摘要|概况|介绍|官网.*(有什么|做什么|说了什么)|summary|positioning|audience",
    "geo_diagnosis": r"优化|诊断|引用|误解|忽略|缺少|缺口|改进|结构化|diagnos|citation|optimiz",
    "user_questions": r"会怎么问|会问|客户.*问题|用户.*问题|生成.*(问题|提问|FAQ)|模拟.*(问题|用户)|question|prompt",
    "content_strategy": r"应该写|写什么|选题|优先|行动计划|内容.*(方向|策略|计划)|排期|strategy|prioriti|content plan",
}


def rule_route(question):
    selected = [name for name, pattern in RULES.items() if re.search(pattern, question, re.I)]
    if not selected and re.search(r"万悉|Trendee|官网|GEO|网站|website", question, re.I):
        selected = ["website_analysis"]
    return {"agents": selected, "reason": "按显式任务意图匹配：" +
            "、".join(REGISTRY[name].label for name in selected) if selected else "问题超出官网/GEO任务范围。",
            "router": "rules"}


def validate_route(value):
    names = value.get("agents")
    if not isinstance(names, list) or len(names) > 4 or any(x not in REGISTRY for x in names):
        raise ValueError("router.agents must contain at most four registered Agent names")
    if not isinstance(value.get("reason"), str):
        raise ValueError("router.reason must be a string")


def execution_plan(selected):
    """Topological execution; always materialize required upstream state."""
    ordered, visiting = [], set()
    def add(name):
        if name in ordered:
            return
        if name in visiting:
            raise ValueError("Agent dependency cycle")
        visiting.add(name)
        for parent in REGISTRY[name].dependencies:
            add(parent)
        visiting.remove(name)
        ordered.append(name)
    for name in REGISTRY:
        if name in selected:
            add(name)
    return [{"step": i + 1, "agent": name, "label": REGISTRY[name].label,
             "depends_on": list(REGISTRY[name].dependencies),
             "reason": "用户要求" if name in selected else "前置资料依赖"}
            for i, name in enumerate(ordered)]


def validate_agent(name, value, hits):
    from .grounding import validate_grounding
    required = {"website_analysis": ["brand_positioning", "capabilities", "audience", "technical_keywords", "summary"],
                "geo_diagnosis": ["findings", "measurement_plan", "scope_note"],
                "user_questions": ["questions", "status"],
                "content_strategy": ["actions", "scope_note"]}[name]
    if any(key not in value for key in required):
        raise ValueError(f"{name} is missing required keys: {required}")
    for key in {"website_analysis": ["capabilities", "audience"], "geo_diagnosis": ["findings", "measurement_plan"],
                "user_questions": ["questions"], "content_strategy": ["actions"]}[name]:
        if not isinstance(value[key], list) or not value[key]:
            raise ValueError(f"{name}.{key} must be a non-empty list")
    if name == "geo_diagnosis":
        for item in value["findings"]:
            if item.get("type") not in {"strength", "gap", "risk"} or item.get("priority") not in {"P0", "P1", "P2"}:
                raise ValueError("invalid finding type/priority")
            if not isinstance(item.get("observation"), dict) or not item.get("recommendation"):
                raise ValueError("finding needs an observation claim and recommendation")
    if name == "user_questions":
        for item in value["questions"]:
            if not item.get("question") or not item.get("intent") or not item.get("evidence_ids"):
                raise ValueError("question needs question, intent and evidence_ids")
    if name == "content_strategy":
        for item in value["actions"]:
            if item.get("priority") not in {"P0", "P1", "P2"} or not item.get("acceptance_criteria"):
                raise ValueError("action needs priority and acceptance_criteria")
            if not isinstance(item.get("reason"), dict) or not item.get("topic"):
                raise ValueError("action needs a topic and reason claim")
    return validate_grounding(value, hits, require_claims=name != "user_questions")
