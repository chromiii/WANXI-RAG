# Project 1 Demo Recording Guide

This document is for the recorded demo required by the take-home assignment. The local website is still the main visual tool, but the submission should include a narrated screen recording.

Recommended length: **5–7 minutes**.

## 1. Pre-recording checklist

Run these checks before recording:

~~~powershell
docker compose up -d elasticsearch
py -m trendee.cli index-info
py -m trendee.cli info
py -m unittest discover -s tests -v
py scripts\eval_project1.py --mode live --require-pdf-artifacts
py -m trendee.cli serve
~~~

Open:

~~~text
http://127.0.0.1:8000
~~~

Do not show `.env`, API keys, private local paths beyond the project root, or raw runtime files containing private PDF excerpts.

## 2. Demo structure

### 0:00–0:40 — Project goal

Say:

> This is Project 1, an evidence-backed RAG writing system for Wanxi/Trendee brand content. It reads the provided PDF, builds page-traceable evidence, retrieves relevant chunks with hybrid search, generates Blog/FAQ/brand/product copy, and validates factual claims against retrieved evidence.

Show the README or the website landing area.

### 0:40–1:20 — Architecture overview

Show the page header / workflow explanation.

Narration:

~~~text
PDF ingest
→ normalize and stable chunk IDs
→ Intent Classifier
→ Query Transformation
→ BM25 + BGE-M3 retrieval
→ weighted RRF
→ local cross-encoder rerank
→ Evidence Sufficiency
→ Post-Retrieval
→ Writer
→ Grounding
~~~

Key point:

> I separate user intent, query transformation, retrieval relevance, and grounding so the system is not just “PDF plus one prompt”.

### 1:20–3:40 — Official Blog case

Use the quick case:

~~~text
为什么中国出海品牌需要进行 GEO 优化？
~~~

Walk through:

1. **Intent & Run** — content type, semantic focus, user goal.
2. **Query Plan** — original query is preserved; rewrites only expand retrieval.
3. **Workflow Trace** — each observable stage.
4. **Evidence Clues** — retrieval channel, reranker score, selected evidence.
5. **Generated Content** — structured Blog output.
6. **Citation** — click citation and open the supporting evidence/PDF page.
7. **Validation** — citation and grounding checks.

Do not read the entire article.

### 3:40–4:50 — Evidence Sufficiency / no hallucination case

Use the missing-fact case or manually input:

~~~text
万悉科技总部办公面积是多少？
~~~

Say:

> This exact field is not hardcoded. The system may retrieve company-related evidence, but the Evidence Sufficiency stage checks whether the requested fact is directly supported. If not, it stops before writing instead of asking the model to invent an answer.

Expected behavior: `insufficient_evidence`.

### 4:50–5:50 — Hypothetical evidence boundary

Use:

~~~text
万悉科技对招商银行有什么 GEO 应用设想？
~~~

Say:

> The runtime does not contain an entity-specific “招商银行” grounding patch. The generated answer should preserve the source as an application hypothesis, not a confirmed delivered client case.

Look for language such as “应用设想 / 设想中 / 可用于”，not “已服务 / 已合作 / 已交付”.

### 5:50–6:30 — Engineering closure

Show terminal commands or README:

~~~powershell
py -m unittest discover -s tests -v
py scripts\eval_project1.py --mode live --require-pdf-artifacts
~~~

Say:

> The repository contains code, prompts, tests, and docs. The private PDF, parsed evidence, embeddings, run logs, evaluation reports, and API key remain local and are not committed.

## 3. What not to show

Avoid showing:

- `.env` or API keys;
- raw `data/private` content;
- long JSON dumps unless necessary;
- private PDF pages unrelated to the evidence being cited;
- generated evaluation JSON containing source excerpts.

## 4. Backup CLI commands

If the website fails during recording:

~~~powershell
py -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode live --type Blog
py scripts\eval_project1.py --mode live --case official_blog
py scripts\eval_project1.py --mode live --case hypothetical_bank_scenario
~~~

## 5. Submission bundle

Recommended bundle:

1. GitHub repository link;
2. recorded demo video;
3. README as entry point;
4. optional PPT overview.

The website remains the recording interface, not a replacement for the video.
