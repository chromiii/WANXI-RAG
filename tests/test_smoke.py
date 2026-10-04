import tempfile
from pathlib import Path
import unittest

from trendee.agents import execution_plan, rule_route
from trendee.rag.workflow import RAGWorkflow
from trendee.retrieval import Chunk, Index
from trendee.runlog import RunLogger
from trendee.search.elasticsearch_store import (
    EMBEDDING_DIMS,
    evidence_index_body,
    rrf_fuse,
)


class CodeOnlySmokeTests(unittest.TestCase):
    def test_package_level_retrieval_primitives_import_and_run(self):
        index = Index([
            Chunk("web-01", "GEO 生成式引擎优化关注 AI 引用和品牌可见性。", "synthetic"),
            Chunk("web-02", "仓储系统用于库存管理。", "synthetic"),
        ])
        hits = index.search("GEO AI 引用", top_k=2)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["id"], "web-01")

    def test_agent_dependency_plan_is_constructible(self):
        routed = rule_route("请分析官网哪里需要优化，并给出内容策略")
        plan = execution_plan(routed["agents"])
        names = [step["agent"] for step in plan]
        self.assertIn("website_analysis", names)
        self.assertIn("geo_diagnosis", names)
        self.assertLess(names.index("website_analysis"), names.index("geo_diagnosis"))

    def test_elasticsearch_schema_and_rrf_are_available(self):
        body = evidence_index_body()
        props = body["mappings"]["properties"]
        self.assertEqual(props["embedding"]["dims"], EMBEDDING_DIMS)
        self.assertEqual(props["content"]["analyzer"], "cjk")

        fused = rrf_fuse(
            [
                [{"chunk_id": "a", "content": "A"}, {"chunk_id": "b", "content": "B"}],
                [{"chunk_id": "b", "content": "B"}, {"chunk_id": "c", "content": "C"}],
            ],
            top_k=3,
        )
        self.assertEqual(fused[0]["chunk_id"], "b")

    def test_project1_offline_workflow_runs_end_to_end_with_fake_retriever(self):
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
            content_type="Blog",
            mode="offline",
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["validation"]["citation_ids_valid"])
        self.assertEqual(
            [step["step"] for step in result["workflow_trace"]],
            [
                "scope_guard",
                "task_intent",
                "query_planning",
                "hybrid_retrieval",
                "evidence_gate",
                "post_retrieval_processing",
                "context_building",
                "generation",
                "grounding_validation",
            ],
        )

    def test_run_logger_writes_private_jsonl_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = RunLogger(Path(tmp))
            logger.record(
                "smoke",
                "/api/write",
                {"topic": "GEO"},
                result={"status": "ok"},
            )
            lines = logger.path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn('"run_id": "smoke"', lines[0])


if __name__ == "__main__":
    unittest.main()
