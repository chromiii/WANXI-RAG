# Demo Guide

This document is a suggested 5–8 minute walkthrough for Project 1.

## Demo goal

Show that the system is not just “PDF + LLM”. The demo should make the complete engineering chain visible:

~~~text
User request
→ Intent
→ Query Transformation
→ Hybrid Retrieval
→ Reranking
→ Evidence Sufficiency
→ Post-Retrieval Processing
→ Type-specific Writer
→ Grounding
→ Cited output + source page
~~~

The most persuasive demo is one successful writing case plus one safe early-stop / hallucination boundary case.

## 1. Pre-demo checklist

Before recording:

~~~powershell
docker compose up -d elasticsearch
py -m trendee.cli index-info
py -m trendee.cli info
py -m unittest discover -s tests -v
py scripts\eval_project1.py --mode live --require-pdf-artifacts
~~~

Then start the UI:

~~~powershell
py -m trendee.cli serve
~~~

Open http://127.0.0.1:8000.

Do not display the real .env, API key, local file-system secrets or private evaluation JSON in the recording.

## 2. Recommended 5–8 minute structure

### 0:00–0:45 — Explain the task

Use one sentence:

> The system reads the employer-provided brochure, builds page-traceable evidence, retrieves relevant content with hybrid search, generates website copy and validates every factual claim against retrieved evidence.

Briefly mention the four output formats: Blog, FAQ, brand introduction and product introduction.

### 0:45–1:30 — Show the architecture

~~~text
Intent Classifier
→ Query Planner
→ BM25 + BGE-M3
→ weighted RRF
→ Cross-Encoder
→ Evidence Sufficiency
→ Post-Retrieval
→ Writer
→ Grounding
~~~

Key design points worth saying aloud:

- the original user query is always preserved;
- presentation format cannot overwrite the user’s semantic goal;
- retrieval relevance is decided before post-processing;
- missing facts stop before generation;
- citations point back to stable chunk IDs and physical PDF pages.

### 1:30–4:30 — Run the official Blog case

Use:

~~~text
为什么中国出海品牌需要进行 GEO 优化？
~~~

Walk through the UI in this order:

1. Intent & Run — show content type, semantic focus and user goal.
2. Query Plan — show the original query and any rewrite/expand/decompose queries.
3. Workflow Trace — point out each observable execution stage.
4. Evidence Clues — show BM25/dense/RRF/reranker provenance.
5. Generated Content — show structured website copy rather than a retrieval report.
6. Citation — trace a citation back to the chunk and PDF page image.
7. Validation — show citation/numeric grounding pass.

Do not spend time reading the entire generated article.

### 4:30–6:00 — Show a missing-fact boundary

Recommended manual query:

~~~text
万悉科技总部办公面积是多少？
~~~

This phrase is intentionally not a hardcoded missing-fact field.

Expected behavior:

~~~text
Retrieval may still find company-related chunks
→ Evidence Sufficiency checks whether the requested fact is actually present
→ insufficient_evidence
→ Writer is not allowed to invent an answer
~~~

### 6:00–7:00 — Show the hypothetical-case boundary

Use:

~~~text
万悉科技对招商银行有什么 GEO 应用设想？
~~~

Explain that the runtime no longer contains an entity-specific “招商银行” grounding rule.

The output should preserve hypothetical wording and must not upgrade the source into an already-served customer, confirmed cooperation, delivered project or measured effect.

### 7:00–8:00 — Close with engineering evidence

Show:

~~~powershell
py -m unittest discover -s tests -v
~~~

and mention:

~~~powershell
py scripts\eval_project1.py --mode live --require-pdf-artifacts
~~~

Close with the privacy boundary: the employer PDF, parsed evidence, embeddings, model key, run logs and evaluation reports are runtime-only and are not committed to GitHub.

## 3. What to avoid in the recording

Avoid:

- scrolling through hundreds of lines of JSON;
- showing .env or API keys;
- spending time on package installation;
- reading every retrieval score;
- presenting marketing claims as independently verified facts;
- claiming the grounding validator proves full semantic entailment;
- claiming OCR/vision is implemented when it is not.

## 4. Backup CLI demo

If the browser UI fails:

~~~powershell
py -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode live --type Blog
py scripts\eval_project1.py --mode live --case official_blog
py scripts\eval_project1.py --mode live --case hypothetical_bank_scenario
~~~

## 5. Suggested submission bundle

The external submission can contain:

1. GitHub repository link;
2. Demo video;
3. README as the entry point;
4. optional screenshot or terminal capture showing regression tests and the live acceptance suite passing.

Do not submit the private runtime directory unless the employer explicitly asks for it through an approved channel.
