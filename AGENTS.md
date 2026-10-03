# WANXI-RAG agent instructions

This repository is the cloud source of truth for code, prompts, tests and documentation.

## Security boundary
- Never commit real `.env`, API keys, tokens or credentials.
- Never commit employer-provided documents or derived knowledge artifacts.
- Runtime data belongs in `data/private/` or the directory specified by `WANXI_DATA_DIR`.
- Do not commit parsed page caches, website snapshots, embeddings, vector indexes or local databases.
- Synthetic test fixtures are allowed when they contain no employer-provided content.

## Before changing code
Read `README.md` and `docs/DEVELOPMENT.md`.

## Validate code-only changes
```bash
python -m pip install -r requirements.lock
python -m unittest discover -s tests -v
python -m compileall -q trendee
```

These checks must work without private Wanxi data and without an API key.

## Validate real-data behavior
Only in a runtime that has authorized private data:
```bash
python -m trendee.cli info
python -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode offline
```

For live model checks, inject `DEEPSEEK_API_KEY` via the runtime secret mechanism; never write it to source control.

## Architecture boundaries
- `trendee/documents.py`: source ingestion and page-preserving parsing.
- `trendee/retrieval.py`: chunking, retrieval and context construction.
- `trendee/grounding.py`: citation/grounding guards.
- `trendee/llm.py`: model boundary; live mode must not silently fall back to offline output.
- `trendee/agents.py`: registered agents, routing and dependency graph.
- `trendee/service.py`: orchestration.
- `prompts/`: model instructions; keep source-grounding requirements explicit.

Prefer small, test-backed changes. Preserve stable citation IDs such as `pdf-p012-c01`.
