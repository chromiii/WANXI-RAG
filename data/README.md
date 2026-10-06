# Runtime data

This directory is intentionally data-free in Git.

The repository stores code, prompts, tests, configuration examples and documentation only. Real employer-provided documents and all derived knowledge artifacts are runtime data and must not be committed.

Keep these outside version control:

- `trendee_brand.pdf` and any other employer-provided source documents
- parsed staging/normalized evidence such as `evidence_staging.jsonl` and `evidence_normalized.jsonl`
- captured website snapshots used as runtime evidence
- embeddings and vector indexes (FAISS, Chroma, Qdrant local storage, etc.)
- SQLite/local databases, pickle/NumPy retrieval caches
- demo videos and generated outputs (including repository-root `examples/` created by the demo CLI)
- credentials and real `.env` files

Recommended local layout:

```text
data/
  README.md
  private/          # gitignored
    trendee_brand.pdf
  processed/        # gitignored
  index/            # gitignored
```

For cloud development, inject the private document into the workspace/runtime through the cloud environment's private file or storage mechanism. Do not use GitHub as the data store.

Synthetic fixtures that contain no Wanxi/Trendee confidential or employer-provided content may live under `tests/fixtures/` so CI can test parsing, retrieval, grounding and routing without private data.
