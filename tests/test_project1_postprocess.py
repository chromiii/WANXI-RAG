import unittest

from trendee.rag.context import build_context
from trendee.rag.postprocess import (
    evidence_metadata,
    near_duplicate,
    process_retrieved_hits,
)


class Project1PostRetrievalTests(unittest.TestCase):
    def test_unrequested_hypothetical_is_filtered_and_lower_hit_backfills(self):
        hits = [
            {
                "id": "p1",
                "text": "面向招商银行的 GEO 应用设想。",
                "heading": "面向招商银行的 GEO 应用设想",
                "page": 19,
                "rank": 1,
            },
            {
                "id": "p2",
                "text": "Trendee 提升品牌在 AI 问答引擎中的可见性。",
                "heading": "产品定位",
                "page": 2,
                "rank": 2,
            },
            {
                "id": "p3",
                "text": "大型集团面临信息复杂、口径分散和组织协同问题。",
                "heading": "大型集团项目经验",
                "page": 18,
                "rank": 3,
            },
        ]
        result = process_retrieved_hits(
            hits,
            topic="万悉科技主要帮助客户解决什么问题？",
            top_n=2,
        )
        self.assertEqual(result["selected_ids"], ["p2", "p3"])
        by_id = {item["id"]: item for item in result["all_hits"]}
        self.assertEqual(by_id["p1"]["postprocess_status"], "filtered")
        self.assertEqual(by_id["p1"]["postprocess_reason"], "unrequested_hypothetical")

    def test_requested_hypothetical_is_kept_but_remains_typed(self):
        hits = [{
            "id": "p19",
            "text": "面向招商银行的 GEO 应用设想。",
            "heading": "面向招商银行的 GEO 应用设想",
            "page": 19,
            "rank": 1,
        }]
        result = process_retrieved_hits(
            hits,
            topic="万悉科技对招商银行有什么 GEO 应用设想？",
            top_n=1,
        )
        self.assertEqual(result["selected_ids"], ["p19"])
        self.assertEqual(result["selected"][0]["evidence_type"], "hypothetical")

    def test_product_intro_filters_media_and_backfills(self):
        hits = [
            {
                "id": "media",
                "text": "多家媒体报道万悉科技。",
                "heading": "权威媒体广泛报道",
                "page": 3,
                "rank": 1,
            },
            {
                "id": "product",
                "text": "Trendee 提升品牌 AI 可见性。",
                "heading": "产品定位",
                "page": 2,
                "rank": 2,
            },
            {
                "id": "case",
                "text": "大型集团存在信息复杂、口径分散问题。",
                "heading": "大型集团项目经验",
                "page": 18,
                "rank": 3,
            },
        ]
        result = process_retrieved_hits(
            hits,
            topic="介绍 Trendee 的产品能力",
            content_type="product_intro",
            top_n=2,
        )
        self.assertEqual(result["selected_ids"], ["product", "case"])
        by_id = {item["id"]: item for item in result["all_hits"]}
        self.assertEqual(
            by_id["media"]["postprocess_reason"],
            "media_not_admissible_for_product_intro",
        )

    def test_incidental_media_word_does_not_change_primary_type(self):
        hit = {
            "heading": "大型集团项目经验：知识治理能力",
            "text": "协同官网、媒体、社媒信源，解决信息复杂和口径分散问题。",
        }
        meta = evidence_metadata(hit)
        self.assertEqual(meta["primary_type"], "case")
        self.assertIn("media_reference", meta["risk_flags"])

    def test_near_duplicate_keeps_higher_ranked_copy(self):
        hits = [
            {
                "id": "a",
                "text": "万悉科技通过结构化品牌内容提升AI可见性并形成统一知识资产。",
                "heading": "知识治理",
                "page": 18,
                "rank": 1,
            },
            {
                "id": "b",
                "text": "万悉科技通过结构化品牌内容提升 AI 可见性，并形成统一知识资产。",
                "heading": "知识治理",
                "page": 18,
                "rank": 2,
            },
            {
                "id": "c",
                "text": "Trendee 提供 AI 可见性监测。",
                "heading": "持续监测",
                "page": 20,
                "rank": 3,
            },
        ]
        self.assertTrue(near_duplicate(hits[0], hits[1]))
        result = process_retrieved_hits(hits, topic="介绍 GEO 能力", top_n=3)
        self.assertEqual(result["selected_ids"], ["a", "c"])

    def test_context_budget_drops_later_hit_without_reordering(self):
        hits = [
            {"id": "a", "text": "A" * 150, "heading": "A", "page": 1, "rank": 1},
            {"id": "b", "text": "B" * 150, "heading": "B", "page": 2, "rank": 2},
        ]
        result = process_retrieved_hits(
            hits,
            topic="GEO",
            top_n=2,
            max_chars=300,
        )
        self.assertEqual(result["selected_ids"], ["a"])
        by_id = {item["id"]: item for item in result["all_hits"]}
        self.assertEqual(by_id["b"]["postprocess_status"], "budget_dropped")

    def test_context_builder_preserves_provenance_metadata(self):
        hits = [{
            "id": "pdf-p018-c01",
            "text": "大型集团存在信息复杂和口径分散问题。",
            "source": "sample.pdf",
            "page": 18,
            "heading": "知识治理",
            "evidence_type": "case",
            "risk_flags": ["media_reference"],
        }]
        context = build_context(hits)
        self.assertIn("[pdf-p018-c01]", context["text"])
        self.assertIn("页码=18", context["text"])
        self.assertIn("evidence_type=case", context["text"])
        self.assertIn("risk_flags=media_reference", context["text"])


if __name__ == "__main__":
    unittest.main()
