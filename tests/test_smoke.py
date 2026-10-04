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
from trendee.search.query_planner import passthrough_plan, validate_query_plan
from trendee.rag.intent import canonical_content_type, parse_task_intent, retrieval_seed_queries
from trendee.rag.generation import validate_document, render_markdown
from trendee.rag.workflow import RAGWorkflow
from trendee.rag.scope import precheck_scope
from trendee.rag.context import build_context
from trendee.rag.postprocess import process_retrieved_hits, evidence_metadata, near_duplicate
from trendee.runlog import RunLogger
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
                "channel_1": {"rank": 2, "score": 0.0, "weight": 1.0},
                "channel_2": {"rank": 1, "score": 0.0, "weight": 1.0},
            },
        )

    def test_weighted_rrf_preserves_original_query_priority(self):
        original = [{"chunk_id": "original", "score": 10.0}]
        rewrite = [{"chunk_id": "rewrite", "score": 10.0}]
        fused = rrf_fuse(
            [original, rewrite],
            top_k=2,
            labels=["original_bm25", "rewrite_1_bm25"],
            weights=[1.0, 0.7],
        )
        self.assertEqual(fused[0]["chunk_id"], "original")
        self.assertGreater(fused[0]["rrf_score"], fused[1]["rrf_score"])

    def test_query_plan_always_preserves_original_query(self):
        plan = validate_query_plan(
            {
                "rewrite_needed": True,
                "intent": "customer_pain_points",
                "retrieval_queries": [
                    "客户痛点 服务价值",
                    "客户痛点 服务价值",
                    "GEO 客户挑战",
                    "第三个扩展",
                    "第四个扩展应截断",
                ],
                "reason": "抽象问题需要扩展",
            },
            "万悉科技主要帮助客户解决什么问题？",
        )
        self.assertEqual(plan["retrieval_queries"][0], "万悉科技主要帮助客户解决什么问题？")
        self.assertEqual(len(plan["retrieval_queries"]), 4)
        self.assertTrue(plan["rewrite_needed"])

    def test_offline_query_plan_is_passthrough(self):
        plan = passthrough_plan("GEO 原生网站有哪些核心能力？")
        self.assertFalse(plan["rewrite_needed"])
        self.assertEqual(plan["retrieval_queries"], ["GEO 原生网站有哪些核心能力？"])

    def test_task_intent_explicit_type_wins_without_model(self):
        intent = parse_task_intent(
            topic="万悉科技主要帮助客户解决什么问题？",
            audience="市场团队",
            requested_type="FAQ",
            active_mode="live",
            client=None,
            system_prompt=None,
        )
        self.assertEqual(intent["content_type"], "faq")
        self.assertEqual(intent["source"], "explicit")

    def test_task_intent_rule_detects_blog(self):
        intent = parse_task_intent(
            topic="为什么中国出海品牌需要进行 GEO 优化？",
            audience="市场团队",
            requested_type="auto",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "blog")
        self.assertEqual(intent["source"], "rule")

    def test_content_type_aliases(self):
        self.assertEqual(canonical_content_type("品牌介绍"), "brand_intro")
        self.assertEqual(canonical_content_type("产品介绍"), "product_intro")
        self.assertEqual(canonical_content_type("auto"), "auto")

    def test_product_intent_has_schema_retrieval_needs(self):
        intent = parse_task_intent(
            topic="万悉科技主要帮助客户解决什么问题？",
            audience="市场团队",
            requested_type="产品介绍",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "product_intro")
        self.assertIn("产品核心能力与功能", intent["retrieval_needs"])
        seeds = retrieval_seed_queries("product_intro", intent["semantic_focus"])
        self.assertTrue(any("产品能力" in query for query in seeds))
        self.assertTrue(any("使用场景" in query for query in seeds))

    def test_explicit_product_format_preserves_primary_question_focus(self):
        intent = parse_task_intent(
            topic="万悉科技主要帮助客户解决什么问题？",
            audience="市场团队",
            requested_type="产品介绍",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "product_intro")
        self.assertEqual(intent["semantic_focus"], "customer_pain_points")
        self.assertEqual(intent["primary_question"], "万悉科技主要帮助客户解决什么问题？")
        self.assertIn("客户面临的具体问题、痛点或业务挑战", intent["primary_retrieval_needs"])

    def test_faq_first_question_must_preserve_original_question(self):
        hits = [{"id": "pdf-p001-c01", "text": "万悉科技提升品牌在AI问答中的可见性。", "source": "x", "page": 1}]
        good = {
            "title": "FAQ",
            "intro": [{"text": "以下基于资料。", "citations": ["pdf-p001-c01"]}],
            "faq": [{
                "question": "万悉科技主要帮助客户解决什么问题？",
                "answer": {"text": "主要帮助品牌提升AI可见性。", "citations": ["pdf-p001-c01"]},
            }],
            "conclusion": [{"text": "以上基于资料。", "citations": ["pdf-p001-c01"]}],
            "limitations": [],
        }
        result = validate_document(
            "faq",
            good,
            hits,
            topic="万悉科技主要帮助客户解决什么问题？",
        )
        self.assertTrue(result["citation_ids_valid"])

        bad = dict(good)
        bad["faq"] = [{
            "question": "万悉科技有哪些特点？",
            "answer": {"text": "主要帮助品牌提升AI可见性。", "citations": ["pdf-p001-c01"]},
        }]
        with self.assertRaisesRegex(ValueError, "FAQ first question"):
            validate_document(
                "faq",
                bad,
                hits,
                topic="万悉科技主要帮助客户解决什么问题？",
            )

    def test_faq_schema_is_distinct_from_blog(self):
        hits = [{"id": "pdf-p001-c01", "text": "万悉科技提升品牌在AI问答引擎中的可见性。", "source": "x", "page": 1}]
        faq = {
            "title": "FAQ",
            "intro": [{"text": "以下回答基于资料。", "citations": ["pdf-p001-c01"]}],
            "faq": [
                {"question": "问题1", "answer": {"text": "回答。", "citations": ["pdf-p001-c01"]}},
                {"question": "问题2", "answer": {"text": "回答。", "citations": ["pdf-p001-c01"]}},
                {"question": "问题3", "answer": {"text": "回答。", "citations": ["pdf-p001-c01"]}},
            ],
            "conclusion": [{"text": "结语。", "citations": ["pdf-p001-c01"]}],
            "limitations": [],
        }
        result = validate_document("faq", faq, hits)
        self.assertTrue(result["citation_ids_valid"])
        markdown = render_markdown("faq", faq, hits)
        self.assertIn("## 问题1", markdown)
        self.assertNotIn("## FAQ\n", markdown)

    def test_rag_workflow_offline_orchestrates_all_stages(self):
        class FakeConfig:
            api_key = ""
            model = "fake"
            def mode(self, requested="auto"):
                return "offline"

        class FakeRetriever:
            def search(self, **kwargs):
                return [
                    {
                        "chunk_id": "pdf-p001-c01",
                        "content": "GEO 可以帮助品牌组织更容易被 AI 理解和引用的公开内容。",
                        "source_name": "sample.pdf",
                        "page": 1,
                        "heading": "GEO 价值",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "rrf_score": 0.03,
                        "rank": 1,
                    },
                    {
                        "chunk_id": "pdf-p002-c01",
                        "content": "出海品牌需要统一、结构化的品牌知识资产。",
                        "source_name": "sample.pdf",
                        "page": 2,
                        "heading": "知识资产",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "rrf_score": 0.02,
                        "rank": 2,
                    },
                ]

        result = RAGWorkflow(FakeConfig(), FakeRetriever()).run(
            "为什么中国出海品牌需要进行 GEO 优化？",
            content_type="auto",
            mode="offline",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["task_intent"]["content_type"], "blog")
        self.assertEqual(
            [step["step"] for step in result["workflow_trace"]],
            [
                "scope_guard",
                "task_intent",
                "query_planning",
                "hybrid_retrieval",
                "post_retrieval_processing",
                "context_building",
                "generation",
                "grounding_validation",
            ],
        )
        self.assertTrue(result["validation"]["citation_ids_valid"])

    def test_scope_guard_recognizes_greeting_meta_intent(self):
        result = precheck_scope("你好")
        self.assertEqual(result["scope"], "meta")
        self.assertEqual(result["meta_intent"], "greeting")

    def test_rag_workflow_handles_identity_without_retrieval(self):
        class FakeConfig:
            api_key = ""
            model = "fake"
            def mode(self, requested="auto"):
                return "offline"

        class ShouldNotRunRetriever:
            def search(self, **kwargs):
                raise AssertionError("retrieval must not run for meta intent")

        result = RAGWorkflow(FakeConfig(), ShouldNotRunRetriever()).run(
            "你是谁？",
            content_type="auto",
            mode="offline",
        )
        self.assertEqual(result["status"], "meta")
        self.assertEqual(result["meta_intent"], "identity")
        self.assertIn("RAG 写作助手", result["message"])

    def test_scope_guard_rejects_obvious_unrelated_question(self):
        result = precheck_scope("帮我写一份杭州旅游攻略")
        self.assertEqual(result["scope"], "out_of_scope")

    def test_scope_guard_accepts_geo_question(self):
        result = precheck_scope("GEO 和 SEO 有什么区别？")
        self.assertEqual(result["scope"], "in_scope")

    def test_rag_workflow_stops_before_retrieval_for_out_of_scope(self):
        class FakeConfig:
            api_key = ""
            model = "fake"
            def mode(self, requested="auto"):
                return "offline"

        class ShouldNotRunRetriever:
            def search(self, **kwargs):
                raise AssertionError("retrieval must not run for obvious out-of-scope input")

        result = RAGWorkflow(FakeConfig(), ShouldNotRunRetriever()).run(
            "帮我写一份杭州旅游攻略",
            content_type="Blog",
            mode="offline",
        )
        self.assertEqual(result["status"], "out_of_scope")
        self.assertEqual(result["workflow_trace"][0]["step"], "scope_guard")

    def test_postprocessor_filters_hypothetical_without_reranking(self):
        hits = [
            {
                "id": "pdf-p013-c01",
                "text": "合规GEO强调传递真实价值。",
                "source": "sample.pdf",
                "page": 13,
                "heading": "合规GEO",
                "rank": 1,
                "reranker_score": 0.67,
            },
            {
                "id": "pdf-p019-c01",
                "text": "面向招商银行的GEO应用设想。",
                "source": "sample.pdf",
                "page": 19,
                "heading": "面向招商银行的GEO应用设想",
                "rank": 2,
                "reranker_score": 0.60,
            },
            {
                "id": "pdf-p018-c01",
                "text": "大型集团GEO难点包括信息复杂、口径分散、组织协同难。",
                "source": "sample.pdf",
                "page": 18,
                "heading": "大型集团项目经验",
                "rank": 3,
                "reranker_score": 0.47,
            },
        ]
        result = process_retrieved_hits(
            hits,
            topic="万悉科技主要帮助客户解决什么问题？",
            top_n=2,
            max_chars=8000,
        )
        self.assertEqual(
            result["selected_ids"],
            ["pdf-p013-c01", "pdf-p018-c01"],
        )
        by_id = {item["id"]: item for item in result["all_hits"]}
        self.assertEqual(by_id["pdf-p019-c01"]["postprocess_status"], "filtered")
        self.assertEqual(by_id["pdf-p019-c01"]["evidence_type"], "hypothetical")

    def test_product_postprocessor_filters_media_but_backfills(self):
        hits = [
            {"id": "p1", "text": "媒体报道万悉科技。", "page": 3, "heading": "权威媒体广泛报道", "rank": 1},
            {"id": "p2", "text": "Trendee帮助企业提升AI可见性。", "page": 2, "heading": "产品定位", "rank": 2},
            {"id": "p3", "text": "大型集团面临信息复杂、口径分散问题。", "page": 18, "heading": "大型集团项目经验", "rank": 3},
        ]
        result = process_retrieved_hits(
            hits,
            topic="万悉科技主要帮助客户解决什么问题？",
            content_type="product_intro",
            top_n=2,
            max_chars=8000,
        )
        self.assertEqual(result["selected_ids"], ["p2", "p3"])
        by_id = {item["id"]: item for item in result["all_hits"]}
        self.assertEqual(by_id["p1"]["postprocess_status"], "filtered")
        self.assertEqual(by_id["p1"]["postprocess_reason"], "media_not_admissible_for_product_intro")

    def test_postprocessor_deduplicates_near_duplicate_chunks(self):
        hits = [
            {
                "id": "a",
                "text": "万悉科技通过结构化品牌内容提升AI可见性并形成统一知识资产。",
                "page": 18,
                "heading": "知识治理",
                "rank": 1,
            },
            {
                "id": "b",
                "text": "万悉科技通过结构化品牌内容提升 AI 可见性，并形成统一知识资产。",
                "page": 18,
                "heading": "知识治理",
                "rank": 2,
            },
            {
                "id": "c",
                "text": "Trendee提供AI可见性监测与持续优化。",
                "page": 20,
                "heading": "持续监测",
                "rank": 3,
            },
        ]
        self.assertTrue(near_duplicate(hits[0], hits[1]))
        result = process_retrieved_hits(
            hits,
            topic="介绍万悉科技GEO能力",
            top_n=3,
            max_chars=8000,
        )
        self.assertEqual(result["selected_ids"], ["a", "c"])
        by_id = {item["id"]: item for item in result["all_hits"]}
        self.assertEqual(by_id["b"]["postprocess_status"], "deduplicated")

    def test_evidence_metadata_does_not_turn_incidental_media_word_into_media_type(self):
        hit = {
            "heading": "大型集团项目经验：知识治理能力",
            "text": "整合官网、媒体、社媒等信源，解决信息复杂、口径分散问题。",
        }
        metadata = evidence_metadata(hit)
        self.assertEqual(metadata["primary_type"], "case")
        self.assertIn("media_reference", metadata["risk_flags"])

    def test_hypothetical_is_kept_when_explicitly_requested(self):
        hits = [{
            "id": "pdf-p019-c01",
            "text": "面向招商银行的GEO应用设想。",
            "source": "sample.pdf",
            "page": 19,
            "heading": "面向招商银行的GEO应用设想",
            "rank": 1,
            "reranker_score": 0.80,
        }]
        result = process_retrieved_hits(
            hits,
            topic="万悉科技对招商银行有什么GEO应用设想？",
            top_n=1,
        )
        self.assertEqual(result["selected_ids"], ["pdf-p019-c01"])
        self.assertEqual(result["selected"][0]["evidence_type"], "hypothetical")

    def test_context_builder_only_serializes_selected_hits(self):
        hits = [
            {
                "id": "pdf-p018-c01",
                "text": "大型集团存在信息复杂、口径分散、组织协同难。",
                "source": "sample.pdf",
                "page": 18,
                "heading": "知识治理",
                "evidence_type": "case",
                "risk_flags": ["media_reference"],
            }
        ]
        context = build_context(hits)
        self.assertEqual(context["evidence_ids"], ["pdf-p018-c01"])
        self.assertIn("evidence_type=case", context["text"])
        self.assertIn("risk_flags=media_reference", context["text"])

    def test_run_logger_records_complete_payload_and_redacts_secret(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            logger = RunLogger(directory)
            run_id = logger.new_run_id()
            logger.record(
                run_id,
                "/api/write",
                {"topic": "test", "api_key": "should-not-leak"},
                result={"status": "ok", "document": {"title": "完整结果"}},
                http_status=200,
                duration_ms=123,
            )
            recent = logger.recent(1)
            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0]["run_id"], run_id)
            self.assertEqual(recent[0]["request"]["topic"], "test")
            self.assertEqual(recent[0]["request"]["api_key"], "[REDACTED]")
            self.assertEqual(recent[0]["result"]["document"]["title"], "完整结果")
            self.assertTrue((Path(directory) / "logs" / "rag_runs.jsonl").exists())

    def test_web_debug_studio_assets_exist(self):
        from trendee.config import ROOT
        for relative in ["web/index.html", "web/app.js", "web/styles.css"]:
            self.assertTrue((ROOT / relative).exists(), relative)

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
