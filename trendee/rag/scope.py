"""Project 1 domain/scope guard."""
from __future__ import annotations

import re
from typing import Any, Sequence


META_PATTERNS = [
    ("greeting", re.compile(r"^(你好|您好|嗨|hi|hello|hey)[！!。,.， ]*$", re.I)),
    ("identity", re.compile(r"你是谁|你是什么|自我介绍|介绍一下你自己|who are you", re.I)),
    ("capabilities", re.compile(r"你能做什么|你会什么|能干什么|支持什么|有哪些功能|怎么用|如何使用|help|usage", re.I)),
]

IN_SCOPE = re.compile(
    r"万悉|Trendee|GEO|生成式引擎优化|AI.{0,8}(搜索|问答|引用|推荐|可见性|品牌)|"
    r"(品牌|官网|内容|产品|出海|营销|知识资产).{0,12}(AI|GEO|搜索|问答|引用|可见性)|"
    r"(AI|GEO).{0,12}(品牌|官网|内容|产品|出海|营销|知识资产)|"
    r"SEO.{0,12}GEO|GEO.{0,12}SEO",
    re.I,
)

OUT_OF_SCOPE = re.compile(
    r"天气|旅游攻略|酒店|机票|菜谱|星座|八字|塔罗|股票|基金|汇率|"
    r"写代码|编程题|LeetCode|数学题|物理题|化学题|"
    r"医疗诊断|法律咨询|情感咨询|游戏攻略",
    re.I,
)


def precheck_scope(topic: str) -> dict[str, Any]:
    text = topic.strip()
    for meta_intent, pattern in META_PATTERNS:
        if pattern.search(text):
            return {
                "scope": "meta",
                "meta_intent": meta_intent,
                "source": "rule",
                "reason": "识别为系统问候/身份/能力说明类交互，无需进入知识库检索。",
            }
    if IN_SCOPE.search(text):
        return {
            "scope": "in_scope",
            "source": "rule",
            "reason": "问题包含万悉/GEO/AI可见性/品牌内容等项目范围信号。",
        }
    if OUT_OF_SCOPE.search(text):
        return {
            "scope": "out_of_scope",
            "source": "rule",
            "reason": "问题属于与万悉品牌/GEO内容生成无关的主题。",
        }
    return {
        "scope": "ambiguous",
        "source": "rule",
        "reason": "无法仅根据输入可靠判断，需要结合检索证据判断。",
    }


def evidence_scope_check(
    topic: str,
    hits: Sequence[dict[str, Any]],
    *,
    min_reranker_score: float = 0.03,
) -> dict[str, Any]:
    """Conservative post-retrieval scope fallback.

    Do not use this as a relevance benchmark; it only rejects obviously empty or
    extremely weak retrieval when the precheck was ambiguous.
    """
    if not hits:
        return {
            "scope": "out_of_scope",
            "source": "retrieval",
            "reason": "未检索到可支持该主题的品宣证据。",
        }

    best = max(float(h.get("reranker_score") or h.get("score") or 0.0) for h in hits)
    if best < min_reranker_score:
        return {
            "scope": "out_of_scope",
            "source": "retrieval",
            "reason": "检索结果与输入主题相关性过低，无法基于品宣资料可靠生成。",
            "best_score": round(best, 6),
        }
    return {
        "scope": "in_scope",
        "source": "retrieval",
        "reason": "检索到可用于回答该主题的品宣证据。",
        "best_score": round(best, 6),
    }
