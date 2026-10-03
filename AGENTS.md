# WANXI-RAG agent instructions

This repository is the cloud development source of truth for the Wanxi/Trendee RAG take-home project.

## Before changing code
- Read `README.md` and `docs/DEVELOPMENT.md`.
- Never add a real `.env`, API key, token, or credential to commits or logs.
- The public repository intentionally omits `data/trendee_brand.pdf` and demo MP4 binaries. Use the validated `data/brand_pages.json` cache in cloud environments.

## Validate every change
```bash
python -m pip install -r requirements.lock
python -m unittest discover -s tests -v
python -m trendee.cli info
python -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode offline
```

For UI changes also run:
```bash
node --check web/app.js
```

## Architecture boundaries
- `trendee/documents.py`: source ingestion and page-preserving cache.
- `trendee/retrieval.py`: retrieval and context construction.
- `trendee/grounding.py`: citation/grounding guards.
- `trendee/llm.py`: DeepSeek-compatible model boundary; no silent offline fallback in live mode.
- `trendee/service.py`: RAG orchestration and multi-agent execution.
- `prompts/`: model instructions; keep source-grounding requirements explicit.

Prefer small, test-backed changes. Preserve stable citation ids such as `pdf-p012-c01`.
