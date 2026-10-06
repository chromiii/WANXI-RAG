# Interactive Review Website

Project 1 uses the local website as the primary interactive review surface.

The goal is that a reviewer can understand and verify the RAG workflow without a narrated recording.

## 1. Start the website

With the authorized PDF, Elasticsearch index and local environment prepared:

~~~powershell
docker compose up -d elasticsearch
py -m trendee.cli index-info
py -m trendee.cli info
py -m trendee.cli serve
~~~

Open:

~~~text
http://127.0.0.1:8000
~~~

The website is intentionally local because the employer PDF, parsed evidence, page images, Elasticsearch data and model key are runtime-only private assets.

## 2. Recommended review order

The landing area explains the pipeline and displays the loaded PDF/chunk status.

Recommended sequence:

### Case A — Official Blog

~~~text
为什么中国出海品牌需要进行 GEO 优化？
~~~

This demonstrates the complete successful path:

~~~text
Intent
→ Query Transformation
→ BM25 + BGE-M3
→ weighted RRF
→ Cross-Encoder
→ Evidence Sufficiency
→ Post-Retrieval
→ Writer
→ Grounding
→ cited output
~~~

A reviewer can inspect:

- semantic focus / user goal;
- original and additional retrieval queries;
- retrieval channels and reranker score;
- selected / filtered / deduplicated evidence;
- generated website copy;
- citation → chunk → PDF physical page;
- grounding and model-call metadata.

### Case B — Unsupported fact

Use the built-in missing-fact case or manually ask:

~~~text
万悉科技总部办公面积是多少？
~~~

The phrase “总部办公面积” is not a hardcoded missing-fact field.

Expected behavior:

~~~text
related evidence may still be retrieved
→ Evidence Sufficiency checks direct support
→ insufficient_evidence
→ Writer does not invent an answer
~~~

### Case C — Hypothetical evidence

Use:

~~~text
万悉科技对招商银行有什么 GEO 应用设想？
~~~

The runtime does not contain an entity-specific “招商银行” grounding rule.

The generated answer should preserve the source as an application hypothesis and must not silently promote it into confirmed cooperation, delivered work or measured client results.

## 3. What the website is designed to prove

The website is not a decorative frontend. It exposes engineering behavior that can be checked directly:

1. **Intent is separate from presentation format.**
2. **Original query is preserved during query transformation.**
3. **Retrieval combines lexical and semantic channels.**
4. **Reranking owns relevance ordering.**
5. **Evidence Sufficiency can stop unsupported questions before writing.**
6. **Post-Retrieval handles safety, dedup and context budget without becoming another semantic ranker.**
7. **Generated claims carry stable citation IDs.**
8. **Citations map back to physical PDF pages.**
9. **Grounding applies deterministic checks after generation.**

## 4. Website sections

### Interactive Test

Choose an acceptance case or enter a custom question.

### Intent & Run

Shows:

- content type;
- semantic focus;
- user goal;
- confidence;
- run identity.

### Query Plan

Shows:

- original query;
- strategy: passthrough / rewrite / expand / decompose;
- additional retrieval queries;
- rerank query.

### Workflow Trace

Shows observable execution stages only. It does not expose hidden model reasoning.

### Evidence Clues

Shows each candidate’s:

- PDF page and stable evidence ID;
- reranker / RRF information;
- retrieval channels;
- evidence type and risk flags;
- post-retrieval state;
- physical page preview.

### Generated Content

Renders Blog / FAQ / brand / product output in a publishable layout.

Citation buttons jump directly to the supporting evidence.

### Validation & Model Calls

Shows deterministic validation results plus model-call latency/token metadata.

### Run Logs

Shows the local append-only JSONL execution log. Credential-shaped fields are redacted.

## 5. Pre-review validation

Before handing the repository to a reviewer:

~~~powershell
py -m unittest discover -s tests -v
py scripts\eval_project1.py --mode live --require-pdf-artifacts
~~~

Expected: all regression and selected live acceptance cases pass.

## 6. Privacy boundary

Do not expose or commit:

- populated .env;
- DeepSeek API key;
- employer PDF;
- normalized evidence;
- PDF page images;
- Elasticsearch volume;
- live evaluation JSON;
- local run logs.

The website reads these from the local runtime only.

## 7. If the reviewer only wants to inspect code

The repository remains testable without private data:

~~~powershell
py scripts\setup_dev.py
~~~

The README and docs/PROJECT1_RAG.md explain the architecture; the full interactive website requires the authorized private runtime data.
