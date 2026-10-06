# Development

## Principle

GitHub stores source code, prompts, tests and documentation. Runtime knowledge data is injected separately.

The repository must remain cloneable and testable without the employer PDF, parsed evidence, embeddings, Elasticsearch data or API credentials.

For full installation instructions, use docs/INSTALL.md.

## Bootstrap

Python 3.12 is recommended.

Code-only environment:

~~~bash
python scripts/setup_dev.py
~~~

Full local RAG environment:

~~~bash
python scripts/setup_dev.py --with-ml
~~~

The bootstrap script creates .venv, installs dependencies, compiles the package and runs the code-only test suite. It does not initialize the private knowledge base.

## Runtime data

Default location:

~~~text
data/private/
~~~

Override with:

~~~dotenv
WANXI_DATA_DIR=/absolute/private/path
~~~

Typical runtime artifacts include:

~~~text
trendee_brand.pdf
evidence_staging.jsonl
evidence_normalized.jsonl
ingestion_manifest.json
normalization_manifest.json
assets/pages/
eval/
logs/
~~~

All are excluded from Git.

## Secrets

Copy .env.example to .env and set secrets locally.

~~~dotenv
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=90
LLM_MAX_TOKENS=5000
~~~

Never commit a populated .env.

## Canonical Project 1 data path

There is only one production PDF path:

~~~text
authorized PDF
→ trendee.cli prepare
→ PyMuPDF ingest
→ normalized page-bound chunks
→ trendee.cli index-build
→ BGE-M3 embeddings
→ Elasticsearch
→ BM25 + dense retrieval
→ weighted RRF
→ local cross-encoder
~~~

Do not add a second PDF parser/index fallback to the production writing path.

## Testing

Code-only:

~~~bash
python -m unittest discover -s tests -v
python -m compileall -q trendee
~~~

Project 1 only:

~~~bash
python -m unittest discover -s tests -p "test_project1_*.py" -v
~~~

Real-data acceptance:

~~~bash
python scripts/eval_project1.py --mode live --require-pdf-artifacts
~~~

Acceptance cases live only in eval/project1_cases.json.

## CI

GitHub Actions validates source code and synthetic fixtures only. Real employer data and API keys are not required and must not be uploaded as CI artifacts.

## Design constraints

- Preserve the original user query as a retrieval channel.
- Keep intent classification separate from query transformation.
- Do not let presentation type replace the user’s semantic objective.
- Let reranking determine relevance; post-processing should not become a second semantic ranker.
- Prefer generic evidence sufficiency over field/entity-specific missing-fact patches.
- Keep stable citation IDs tied to physical PDF pages.
- Grounding checks are bounded deterministic guards, not a claim of complete semantic entailment.
