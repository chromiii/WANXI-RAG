# Project 1 Local Demo & Acceptance Guide

This document describes how to run and verify the local Project 1 demo.

## Start the local demo

Prepare the runtime first:

~~~powershell
docker compose up -d elasticsearch
py -m trendee.cli index-info
py -m trendee.cli info
py scripts\eval_project1.py --mode live --require-pdf-artifacts
py -m trendee.cli serve
~~~

Open:

~~~text
http://127.0.0.1:8000
~~~

The local page exposes:

- Intent classification and user goal
- Query transformation
- BM25 / dense retrieval / RRF / reranking
- Evidence Sufficiency
- Post-Retrieval processing
- Generated Blog / FAQ / brand / product content
- Citation → chunk → physical PDF page provenance
- Grounding validation
- Model-call latency and token metadata

## Recommended verification cases

### 1. Official Blog workflow

~~~text
为什么中国出海品牌需要进行 GEO 优化？
~~~

Expected behavior:

- preserve the original topic;
- retrieve relevant PDF evidence;
- generate a structured Blog;
- include citations;
- expose supporting PDF pages;
- pass grounding validation.

### 2. Unsupported fact / Evidence Sufficiency

~~~text
万悉科技总部办公面积是多少？
~~~

Expected behavior:

~~~text
insufficient_evidence
~~~

The system should stop before generation when the requested fact is not supported by the retrieved PDF evidence.

### 3. Hypothetical evidence boundary

~~~text
万悉科技对招商银行有什么 GEO 应用设想？
~~~

Expected behavior:

- preserve hypothetical / proposed wording;
- do not rewrite the source as a confirmed customer case;
- avoid claims such as “已服务 / 已合作 / 已交付” unless explicitly supported.

## CLI equivalents

Generate the official Blog case:

~~~powershell
py -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode live --type Blog
~~~

Run acceptance cases:

~~~powershell
py scripts\eval_project1.py --mode live --case official_blog
py scripts\eval_project1.py --mode live --case hypothetical_bank_scenario
~~~

Run the shared demo catalog:

~~~powershell
py -m trendee.cli demo --mode live
~~~

## Validation

Code-only checks:

~~~powershell
py -m unittest discover -s tests -v
py -m compileall -q trendee
~~~

Full live acceptance:

~~~powershell
py scripts\eval_project1.py --mode live --require-pdf-artifacts
~~~

## Data and security boundary

Do not commit or publish:

- `.env` or API keys;
- employer-provided PDF;
- `data/private/` runtime artifacts;
- normalized evidence and page renders;
- embeddings / Elasticsearch data;
- live evaluation reports and run logs.

The repository intentionally keeps private source material and generated runtime evidence outside Git.
