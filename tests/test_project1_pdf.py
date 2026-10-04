import json
from pathlib import Path
import tempfile
import unittest

import pymupdf

from trendee.ingestion.pdf import extract_pdf_evidence
from trendee.ingestion.normalize import normalize_staging


class Project1PdfTests(unittest.TestCase):
    def _make_pdf(self, target: Path) -> None:
        doc = pymupdf.open()
        texts = [
            "GEO visibility for AI engines. " * 12,
            "Knowledge governance unifies brand content and data standards. " * 12,
            "3",
        ]
        for body in texts:
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), "WANXI REPEATED HEADER")
            page.insert_text((72, 120), body)
        doc.save(target)
        doc.close()

    def test_extract_preserves_page_numbers_and_renders_page_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            self._make_pdf(pdf)

            manifest = extract_pdf_evidence(
                pdf,
                root / "out",
                render_pages=True,
                render_scale=1.0,
            )
            self.assertEqual(manifest["page_count"], 3)
            self.assertEqual(manifest["rendered_page_count"], 3)
            self.assertEqual(manifest["page_image_evidence_count"], 3)
            self.assertEqual(manifest["network_calls"], 0)

            staging = root / "out" / "evidence_staging.jsonl"
            rows = [
                json.loads(line)
                for line in staging.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            page_images = [row for row in rows if row["modality"] == "page_image"]
            self.assertEqual([row["page"] for row in page_images], [1, 2, 3])
            for row in page_images:
                self.assertRegex(row["id"], r"^pdf-p\d{3}-page$")
                self.assertTrue((root / "out" / row["asset_path"]).exists())
                self.assertFalse(row["metadata"]["ocr_applied"])
                self.assertFalse(row["metadata"]["vision_model_applied"])

    def test_normalization_never_crosses_physical_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            self._make_pdf(pdf)
            out = root / "out"
            extract_pdf_evidence(pdf, out, render_scale=1.0)

            manifest = normalize_staging(
                out / "evidence_staging.jsonl",
                out / "evidence_normalized.jsonl",
                target_chars=120,
                max_chars=180,
                min_text_chars=30,
            )
            self.assertIn(3, manifest["sparse_text_pages"])

            rows = [
                json.loads(line)
                for line in (out / "evidence_normalized.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(rows)
            self.assertTrue(all(row["page"] in {1, 2} for row in rows))
            self.assertTrue(all(len(row["content"]) <= 180 for row in rows))
            self.assertTrue(all(row["asset_path"] for row in rows))

            for row in rows:
                self.assertRegex(row["id"], rf"^pdf-p{row['page']:03d}-c\d{{2}}$")
                for source_id in row["metadata"]["source_block_ids"]:
                    self.assertTrue(
                        source_id.startswith(f"pdf-p{row['page']:03d}-"),
                        msg=f"chunk {row['id']} crossed page boundary via {source_id}",
                    )

    def test_repeated_short_header_is_removed_as_boilerplate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            self._make_pdf(pdf)
            out = root / "out"
            extract_pdf_evidence(pdf, out, render_scale=1.0)
            manifest = normalize_staging(
                out / "evidence_staging.jsonl",
                out / "evidence_normalized.jsonl",
                target_chars=120,
                max_chars=180,
                min_text_chars=30,
            )
            self.assertGreaterEqual(manifest["removed_repeated_boilerplate_blocks"], 3)
            normalized_text = (out / "evidence_normalized.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("WANXI REPEATED HEADER", normalized_text)

    def test_invalid_render_scale_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "sample.pdf"
            self._make_pdf(pdf)
            with self.assertRaisesRegex(ValueError, "render_scale"):
                extract_pdf_evidence(pdf, root / "out", render_scale=0)

    def test_invalid_normalization_budget_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "evidence_staging.jsonl"
            staging.write_text(
                json.dumps({
                    "id": "pdf-p001-t01",
                    "source_id": "s",
                    "source_name": "x.pdf",
                    "source_sha256": "abc",
                    "page": 1,
                    "modality": "text",
                    "heading": "h",
                    "content": "content long enough to be parsed",
                }) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "target_chars"):
                normalize_staging(staging, target_chars=500, max_chars=100)


if __name__ == "__main__":
    unittest.main()
