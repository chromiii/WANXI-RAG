import base64
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf

from trendee.agents import execution_plan, rule_route
from trendee.config import Config
from trendee.retrieval import Chunk, Index, pdf_chunks, split_page
from trendee.search.elasticsearch_store import EMBEDDING_DIMS, evidence_index_body, rrf_fuse
from trendee.search.embeddings import embedding_text
from trendee.ingestion.pdf import extract_pdf_evidence
from trendee.ingestion.normalize import normalize_staging


class CodeOnlySmokeTests(unittest.TestCase):
    def test_page_chunks_preserve_physical_page(self):
        pages = [
            {"page": 7, "text": "GEO 生成式引擎优化可以帮助品牌组织适合 AI 理解与引用的公开内容。" * 4}
        ]
        chunks = pdf_chunks(pages)
        self.assertTrue(chunks)
        self.assertTrue(all(chunk.page == 7 for chunk in chunks))
        self.assertTrue(all(chunk.id.startswith("pdf-p007-") for chunk in chunks))

    def test_retrieval_works_on_synthetic_content(self):
        index = Index([
            Chunk("c1", "GEO 生成式引擎优化关注 AI 引用和品牌可见性。", "synthetic", page=1),
            Chunk("c2", "仓储系统用于库存管理。", "synthetic", page=2),
        ])
        hits = index.search("GEO AI 引用", top_k=2)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["id"], "c1")

    def test_split_page_is_bounded(self):
        parts = split_page("甲乙丙丁。" * 400, max_chars=120, overlap=20)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 120 for part in parts))

    def test_rule_router_and_dependency_plan(self):
        routed = rule_route("请分析官网哪里需要优化，并给出内容策略")
        self.assertIn("geo_diagnosis", routed["agents"])
        plan = execution_plan(routed["agents"])
        names = [step["agent"] for step in plan]
        self.assertIn("website_analysis", names)
        self.assertLess(names.index("website_analysis"), names.index("geo_diagnosis"))

    def test_elasticsearch_mapping_is_code_only_and_multimodal_ready(self):
        body = evidence_index_body()
        props = body["mappings"]["properties"]
        self.assertEqual(props["embedding"]["dims"], EMBEDDING_DIMS)
        self.assertEqual(props["embedding"]["similarity"], "cosine")
        self.assertEqual(props["modality"]["type"], "keyword")
        self.assertFalse(props["asset_path"]["index"])
        self.assertEqual(props["content"]["analyzer"], "cjk")

    def test_rrf_fusion_rewards_cross_channel_hits(self):
        lexical = [
            {"chunk_id": "a", "content": "A"},
            {"chunk_id": "b", "content": "B"},
        ]
        dense = [
            {"chunk_id": "b", "content": "B"},
            {"chunk_id": "c", "content": "C"},
        ]
        fused = rrf_fuse([lexical, dense], top_k=3)
        self.assertEqual(fused[0]["chunk_id"], "b")
        self.assertEqual(
            fused[0]["retrieval_channels"],
            {
                "channel_1": {"rank": 2, "score": 0.0},
                "channel_2": {"rank": 1, "score": 0.0},
            },
        )

    def test_embedding_text_combines_heading_and_content(self):
        value = embedding_text({"heading": "GEO 原生网站", "content": "结构化内容与 AI 引用"})
        self.assertEqual(value, "GEO 原生网站\n结构化内容与 AI 引用")

    def test_pdf_ingestion_extracts_text_and_image_evidence(self):
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.pdf"
            doc = pymupdf.open()
            page = doc.new_page(width=400, height=400)
            page.insert_text((50, 50), "GEO evidence for retrieval and citation.")
            page.insert_image(pymupdf.Rect(50, 100, 250, 250), stream=png)
            doc.save(source)
            doc.close()

            manifest = extract_pdf_evidence(source, root)
            self.assertEqual(manifest["page_count"], 1)
            self.assertGreaterEqual(manifest["text_evidence_count"], 1)
            self.assertEqual(manifest["page_image_evidence_count"], 1)

            records = [
                json.loads(line)
                for line in (root / "evidence_staging.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            modalities = {record["modality"] for record in records}
            self.assertIn("text", modalities)
            self.assertIn("page_image", modalities)
            image = next(record for record in records if record["modality"] == "page_image")
            self.assertTrue((root / image["asset_path"]).exists())
            self.assertEqual(image["metadata"]["ocr_applied"], False)
            self.assertEqual(image["metadata"]["vision_model_applied"], False)

    def test_normalization_merges_blocks_and_links_page_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "evidence_staging.jsonl"
            records = []
            for page in range(1, 5):
                records.extend([
                    {
                        "id": f"pdf-p{page:03d}-t01",
                        "source_id": "source-1",
                        "source_name": "sample.pdf",
                        "source_sha256": "abc",
                        "page": page,
                        "modality": "text",
                        "heading": "GEO 报告",
                        "content": "公司机密页眉",
                        "asset_path": None,
                        "bbox": [0, 0, 100, 20],
                        "text_length": 6,
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "metadata": {},
                    },
                    {
                        "id": f"pdf-p{page:03d}-t02",
                        "source_id": "source-1",
                        "source_name": "sample.pdf",
                        "source_sha256": "abc",
                        "page": page,
                        "modality": "text",
                        "heading": "GEO 报告",
                        "content": f"第{page}页 GEO 正文，介绍 AI 引用、结构化内容和品牌可见性。" * 8,
                        "asset_path": None,
                        "bbox": [10, 30, 300, 300],
                        "text_length": 200,
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "metadata": {},
                    },
                    {
                        "id": f"pdf-p{page:03d}-page",
                        "source_id": "source-1",
                        "source_name": "sample.pdf",
                        "source_sha256": "abc",
                        "page": page,
                        "modality": "page_image",
                        "heading": "GEO 报告",
                        "content": "page image surrogate",
                        "asset_path": f"assets/pages/p{page:03d}.png",
                        "bbox": [0, 0, 400, 400],
                        "text_length": 20,
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "metadata": {},
                    },
                ])
            staging.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
                encoding="utf-8",
            )
            manifest = normalize_staging(staging)
            self.assertGreater(manifest["normalized_chunk_count"], 0)
            self.assertGreaterEqual(manifest["removed_repeated_boilerplate_blocks"], 4)
            self.assertEqual(manifest["markdown_preview_file"], "evidence_normalized.md")
            self.assertTrue((root / "evidence_normalized.md").exists())
            markdown = (root / "evidence_normalized.md").read_text(encoding="utf-8-sig")
            self.assertIn("# WANXI RAG Evidence Preview", markdown)
            self.assertIn("![PDF Page 1](assets/pages/p001.png)", markdown)

            normalized = [
                json.loads(line)
                for line in (root / "evidence_normalized.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(all(item["modality"] == "text" for item in normalized))
            self.assertTrue(all(item["asset_path"].startswith("assets/pages/") for item in normalized))
            self.assertFalse(any("公司机密页眉" in item["content"] for item in normalized))

    def test_live_mode_requires_secret(self):
        with self.assertRaises(ValueError):
            Config(api_key="").mode("live")


if __name__ == "__main__":
    unittest.main()
