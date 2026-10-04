"""Legacy lexical retrieval used only by the bounded website agent pipeline.

Project 1 PDF retrieval uses Elasticsearch BM25 + BGE-M3 dense retrieval,
weighted RRF and local cross-encoder reranking in trendee.search.
"""
from collections import Counter
from dataclasses import dataclass, asdict
import math
import re


STOP = {"的", "了", "是", "在", "和", "与", "我", "你", "请", "如何", "为什么", "什么", "一个", "以及",
        "需要", "进行", "这些", "应该", "根据", "基于", "生成", "一篇", "官网", "内容", "品牌", "公司",
        "万悉", "科技", "目前", "问题", "相关", "提供", "分析", "关于", "介绍", "帮我"}
ALIASES = {"geo": "生成式引擎优化 AI 引用 推荐 可见性", "rag": "检索增强生成 资料 知识库",
           "出海": "全球化 中国 海外 用户", "产品": "产品 服务 核心能力", "faq": "问答 用户问题"}


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    page: int | None = None
    url: str | None = None
    heading: str = ""
    captured_at_utc: str | None = None


def terms(text, expand=False):
    value = text.lower()
    if expand:
        value += " " + " ".join(v for k, v in ALIASES.items() if k in value)
    result = re.findall(r"[a-z][a-z0-9_-]*|\d+(?:\.\d+)?%?", value)
    for span in re.findall(r"[\u4e00-\u9fff]+", value):
        result.extend(span[i:i+2] for i in range(max(0, len(span)-1)))
    return [t for t in result if t not in STOP and len(t) > 1]


def split_page(text, max_chars=900, overlap=100):
    if len(text) <= max_chars:
        return [text]
    result, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundaries = [m.end() for m in re.finditer(r"[。！？\n]", text[start:end])]
            candidates = [start + p for p in boundaries if p >= max_chars // 2]
            if candidates:
                end = candidates[-1]
        result.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return result


def website_chunks(snapshot):
    output = []
    for page_number, page in enumerate(snapshot["pages"], 1):
        prefix = f"web-{page_number:02d}"
        metadata = (f"网页标题：{page['title']}。静态 HTML H1 数量：{page['h1_count']}；"
                    f"JSON-LD 块数量：{page['jsonld_count']}。描述：{page['meta'].get('description', '未检测到')}。"
                    f"范围：{page['scope_note']}")
        output.append(Chunk(prefix + "-meta", metadata, "official_website", url=page["url"],
                            heading="静态HTML结构检测", captured_at_utc=page["captured_at_utc"]))
        for number, block in enumerate(page["blocks"], 1):
            for part, text in enumerate(split_page(block["text"]), 1):
                output.append(Chunk(f"{prefix}-b{number:03d}-c{part:02d}", text, "official_website",
                                    url=page["url"], heading=block["heading"],
                                    captured_at_utc=page["captured_at_utc"]))
    return output


class Index:
    def __init__(self, chunks):
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}
        self.counters = [Counter(terms(c.heading + " " + c.text)) for c in chunks]
        self.df = Counter(t for c in self.counters for t in c)
        self.lengths = [sum(c.values()) for c in self.counters]
        self.average_length = sum(self.lengths) / max(len(chunks), 1)
        self.vectors = [{t: (1 + math.log(n)) * self.idf(t) for t, n in c.items()} for c in self.counters]
        self.norms = [math.sqrt(sum(v*v for v in x.values())) for x in self.vectors]

    def idf(self, term):
        return math.log(1 + (len(self.chunks) - self.df[term] + .5) / (self.df[term] + .5))

    def search(self, query, top_k=6, max_context_chars=6500):
        if not query.strip():
            return []
        raw_terms = set(terms(query))
        q = Counter(terms(query, expand=True))
        if not q or not any(t in self.df for t in raw_terms):
            return []
        qvector = {t: (1 + math.log(n)) * self.idf(t) for t, n in q.items()}
        qnorm = math.sqrt(sum(v*v for v in qvector.values()))
        bm25, cosine = [], []
        for i, counter in enumerate(self.counters):
            score = 0
            for t in q:
                tf = counter[t]
                denominator = tf + 1.5 * (1 - .75 + .75 * self.lengths[i] / max(self.average_length, 1))
                if tf:
                    score += self.idf(t) * tf * 2.5 / denominator
            bm25.append(score)
            cosine.append(sum(self.vectors[i].get(t, 0)*v for t, v in qvector.items()) /
                          max(qnorm * self.norms[i], 1e-12))
        scores = Counter()
        for channel in (bm25, cosine):
            order = sorted(range(len(channel)), key=lambda i: (-channel[i], self.chunks[i].id))
            for rank, i in enumerate(order, 1):
                if channel[i] > 0:
                    scores[i] += 1 / (60 + rank)
        results, total, duplicate_text = [], 0, set()
        for i in sorted(scores, key=lambda i: (-scores[i], self.chunks[i].id)):
            chunk = self.chunks[i]
            raw_overlap = sorted(raw_terms.intersection(self.counters[i]))
            if not raw_overlap or chunk.text in duplicate_text:
                continue
            if total + len(chunk.text) > max_context_chars:
                continue
            results.append({**asdict(chunk), "score": round(scores[i], 6),
                            "bm25_score": round(bm25[i], 4), "tfidf_cosine": round(cosine[i], 4),
                            "matched_terms": raw_overlap[:20]})
            total += len(chunk.text)
            duplicate_text.add(chunk.text)
            if len(results) >= max(1, min(top_k, 12)):
                break
        return results


def context_from_hits(hits):
    return "\n\n".join(f"[{h['id']}] 来源={h['source']}; 页码={h.get('page')}; "
                       f"URL={h.get('url')}; 小节={h.get('heading')}\n{h['text']}" for h in hits)
