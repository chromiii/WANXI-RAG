# Development

## Principle

GitHub stores source code. Runtime knowledge data is injected separately.

The repository must remain cloneable and testable without the Wanxi PDF, website snapshot, embeddings, vector database files or API credentials.

## Bootstrap

Python 3.12 is recommended:

```bash
python scripts/setup_dev.py
```

This creates `.venv`, installs `requirements.lock`, compiles the package and runs code-only unit tests. It does not initialize the private knowledge base.

## Runtime data

By default the application reads private runtime data from:

```text
data/private/
```

Override this with:

```dotenv
WANXI_DATA_DIR=/absolute/private/path
```

The runtime directory can contain the authorized source PDF and generated artifacts. It is explicitly excluded by `.gitignore`.

## Secrets

Use the runtime secret mechanism or a local ignored `.env`:

```dotenv
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=90
LLM_MAX_TOKENS=5000
```

Never commit a populated secret file.

## CI

GitHub Actions validates only code and synthetic fixtures. Real Wanxi data is not required and must not be uploaded as a CI artifact.

## Real demo

After private data has been injected:

```bash
python -m trendee.cli info
python -m trendee.cli search "GEO 和 SEO 的区别" --source pdf
python -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode offline
```

Use `--mode live` only when a model key has been injected securely.
