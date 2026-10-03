import unittest

from trendee.agents import execution_plan, rule_route
from trendee.config import Config
from trendee.retrieval import Chunk, Index, pdf_chunks, split_page


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

    def test_live_mode_requires_secret(self):
        with self.assertRaises(ValueError):
            Config(api_key="").mode("live")


if __name__ == "__main__":
    unittest.main()
