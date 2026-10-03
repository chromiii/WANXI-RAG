# Source data in the public repository

`brand_pages.json` is the validated, page-preserving extraction cache used by the cloud/offline demo.
`brand_manifest.json` records the original source hash and parsing metadata.

The employer-provided `trendee_brand.pdf` is intentionally not committed to the public repository.
To re-run PDF parsing locally, place the authorized source file at `data/trendee_brand.pdf` and run:

```bash
python -m trendee.cli prepare
```

Without the original PDF, the application uses `brand_pages.json`; citations and physical page numbers remain stable.
