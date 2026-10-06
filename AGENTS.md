# WANXI-RAG agent instructions

This repository is the source of truth for Project 1 code, prompts, tests and documentation.

## Security boundary

- Never commit a populated .env, API key, token or credential.
- Never commit employer-provided documents or derived knowledge artifacts.
- Runtime data belongs in data/private/ or the directory configured by WANXI_DATA_DIR.
- Do not commit parsed evidence, page renders, website snapshots, embeddings, evaluation reports, run logs or local database/index files.
- Synthetic fixtures are allowed only when they contain no employer-provided content.

## Before changing code

Read:

1. README.md
2. docs/PROJECT1_RAG.md
3. docs/PROJECT1_TESTING.md
4. docs/DEVELOPMENT.md

## Validate code-only changes

~~~bash
python -m pip install -r requirements.lock
python -m unittest discover -s tests -v
python -m compileall -q trendee
~~~

These checks must work without private Wanxi data and without an API key.

## Validate the full local RAG

The full runtime additionally requires requirements-ml.txt, Elasticsearch and the authorized PDF.

~~~bash
python -m pip install -r requirements-ml.txt
docker compose up -d elasticsearch
python -m trendee.cli prepare
python -m trendee.cli index-build
python scripts/eval_project1.py --mode live --require-pdf-artifacts
~~~

Inject DEEPSEEK_API_KEY through .env or another runtime secret mechanism. Never place it in source code.

## Project 1 architecture boundaries

- trendee/ingestion/: PDF extraction and page-preserving normalization.
- trendee/search/: Elasticsearch store, BGE-M3 embedding, RRF and local reranking.
- trendee/rag/intent.py: task understanding and presentation contract.
- trendee/search/query_planner.py: retrieval query transformation.
- trendee/rag/evidence_gate.py: semantic evidence sufficiency judgment.
- trendee/rag/postprocess.py: evidence metadata, hard safety, dedup and context budget.
- trendee/rag/generation.py: output schemas, deterministic validators and Markdown rendering.
- trendee/grounding.py: citation, numeric and guarantee guards.
- trendee/rag/workflow.py: Project 1 orchestration.
- trendee/llm.py: model boundary; live mode must never silently fall back to offline output.
- prompts/: model instructions.
- eval/project1_cases.json: single shared Project 1 acceptance/demo case catalog.

Prefer small, test-backed changes. Do not add entity-specific production rules to make one acceptance case pass.
