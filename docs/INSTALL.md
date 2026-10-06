# Installation & Local Run

This guide is for reviewers or developers who want to reproduce the Project 1 RAG demo locally.

## 1. Prerequisites

Recommended environment:

- Windows 10/11 or macOS/Linux
- Python 3.12
- Git
- Docker Desktop / Docker Engine
- At least 8 GB RAM; 16 GB recommended for smoother local embedding/reranking
- Internet access on first setup to download Python packages and Hugging Face model weights
- A DeepSeek API key only for `live` generation

Project 1 uses:

- Elasticsearch 9.5.4
- BAAI/bge-m3 for local dense embedding
- BAAI/bge-reranker-base for local cross-encoder reranking
- DeepSeek-compatible chat completion API for intent, query planning, evidence sufficiency and writing

The employer-provided PDF is private runtime data and is intentionally not included in Git.

---

## 2. Clone

### Windows PowerShell

```powershell
git clone https://github.com/chromiii/WANXI-RAG.git
cd WANXI-RAG
```

### macOS / Linux

```bash
git clone https://github.com/chromiii/WANXI-RAG.git
cd WANXI-RAG
```

Make sure the current directory is `WANXI-RAG` before running any `trendee.cli` command.

---

## 3. Create the Python environment

For the full RAG demo, install both the base runtime and local ML dependencies.

### Windows

```powershell
py scripts\setup_dev.py --with-ml
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 scripts/setup_dev.py --with-ml
source .venv/bin/activate
```

The bootstrap script:

1. creates `.venv`;
2. installs `requirements.lock`;
3. installs `requirements-ml.txt` when `--with-ml` is supplied;
4. compiles the package;
5. runs the code-only test suite.

It does **not** read the private PDF or any API key.

If you only want to review the code and run CI-equivalent tests:

```powershell
py scripts\setup_dev.py
```

---

## 4. Configure environment variables

Create a local `.env` from the template.

### Windows

```powershell
Copy-Item .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

For live generation, set:

```dotenv
DEEPSEEK_API_KEY=your_key_here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

Defaults for local Elasticsearch are already provided:

```dotenv
ELASTICSEARCH_URL=http://127.0.0.1:9200
ELASTICSEARCH_INDEX=wanxi-rag-evidence-v1
```

Never commit the populated `.env`.

---

## 5. Add the authorized PDF

Place the employer-provided brochure at:

```text
data/private/trendee_brand.pdf
```

Alternatively, set `WANXI_DATA_DIR` in `.env` to another private directory.

Example:

```dotenv
WANXI_DATA_DIR=C:/private/wanxi-data
```

The runtime directory is gitignored and may contain generated staging files, normalized evidence, page renders, evaluation reports and logs.

---

## 6. Start Elasticsearch

```powershell
docker compose up -d elasticsearch
```

Check Docker:

```powershell
docker compose ps
```

Elasticsearch is bound only to:

```text
127.0.0.1:9200
```

---

## 7. Parse and normalize the PDF

The convenience command runs the canonical Project 1 PDF preparation path:

```powershell
py -m trendee.cli prepare
```

Equivalent explicit commands are:

```powershell
py -m trendee.cli ingest
py -m trendee.cli normalize
```

Expected private runtime artifacts include:

```text
data/private/
  trendee_brand.pdf
  evidence_staging.jsonl
  evidence_normalized.jsonl
  ingestion_manifest.json
  normalization_manifest.json
  assets/pages/
```

Chunks never cross physical PDF page boundaries and retain page-level visual provenance.

---

## 8. Build the local search index

```powershell
py -m trendee.cli index-build
```

On first run, the local embedding model may be downloaded. `index-build` automatically creates the Elasticsearch index if it does not yet exist.

Check the result:

```powershell
py -m trendee.cli index-info
py -m trendee.cli info
```

A normal setup should report a non-zero PDF page/chunk count and an available Elasticsearch index.

---

## 9. Run tests

Code-only regression tests:

```powershell
py -m unittest discover -s tests -v
```

Project 1 tests only:

```powershell
py -m unittest discover -s tests -p "test_project1_*.py" -v
```

Offline acceptance run:

```powershell
py scripts\eval_project1.py --mode offline
```

Full live acceptance run using the real local PDF/index:

```powershell
py scripts\eval_project1.py --mode live --require-pdf-artifacts
```

The live report is written to:

```text
data/private/eval/project1_eval_live.json
```

---

## 10. Start the Debug Studio

```powershell
py -m trendee.cli serve
```

Open:

```text
http://127.0.0.1:8000
```

The UI exposes:

- Intent classification
- Query transformation
- Hybrid retrieval and rerank evidence
- Evidence Sufficiency
- Post-Retrieval decisions
- Generated structured content
- Citation links and source page images
- Grounding validation
- Model-call latency/token metadata
- Local run logs

---

## 11. Useful CLI commands

Write with automatic intent classification:

```powershell
py -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode live
```

Explicit FAQ format:

```powershell
py -m trendee.cli write "万悉科技主要帮助客户解决什么问题？" --mode live --type FAQ
```

Inspect the full retrieval path:

```powershell
py -m trendee.cli rag-search "万悉科技主要帮助客户解决什么问题？" --mode live
```

Run shared demo cases:

```powershell
py -m trendee.cli demo --mode live
```

---

## 12. Troubleshooting

### `ModuleNotFoundError: No module named 'trendee'`

Check that the terminal is inside the `WANXI-RAG` repository, not the separate multi-agent repository.

```powershell
Get-Location
Get-ChildItem
```

You should see `trendee/`, `prompts/`, `tests/`, `eval/` and `docker-compose.yml`.

### Elasticsearch unavailable

```powershell
docker compose up -d elasticsearch
docker compose ps
```

Then retry:

```powershell
py -m trendee.cli index-info
```

### Dense embedding dependencies are missing

```powershell
py -m pip install -r requirements-ml.txt
```

### Local model is not cached

The first `index-build` downloads BGE-M3. The first reranked search may also download `BAAI/bge-reranker-base`. Later runs reuse the local Hugging Face cache.

### Live mode says the API key is missing

Confirm the project-root `.env` contains:

```dotenv
DEEPSEEK_API_KEY=...
```

Then restart the CLI/server process.

### Port 8000 is already in use

```powershell
py -m trendee.cli serve --port 8001
```

### Rebuild after the PDF changes

```powershell
py -m trendee.cli prepare
py -m trendee.cli index-build
```

The index build replaces chunks from the same source rather than silently accumulating stale copies.
