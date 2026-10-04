import unittest

from trendee.grounding import validate_grounding
from trendee.rag.generation import validate_document


class Project1GroundingTests(unittest.TestCase):
    def setUp(self):
        self.hits = [
            {
                "id": "pdf-p002-c01",
                "text": "Trendee 致力于提升品牌在 AI 问答引擎中的可见性。",
                "source": "sample.pdf",
                "page": 2,
            },
            {
                "id": "pdf-p019-c01",
                "text": "面向招商银行的 GEO 应用设想，用于说明金融行业可能的应用方向。",
                "source": "sample.pdf",
                "page": 19,
            },
            {
                "id": "pdf-p030-c01",
                "text": "品宣材料提到覆盖 20 个场景。",
                "source": "sample.pdf",
                "page": 30,
            },
        ]

    def test_unknown_citation_id_is_rejected(self):
        value = {
            "answer": {
                "text": "Trendee 提升品牌 AI 可见性。",
                "citations": ["pdf-p999-c01"],
            }
        }
        with self.assertRaisesRegex(ValueError, "unknown citations"):
            validate_grounding(value, self.hits)

    def test_empty_citation_list_is_rejected(self):
        value = {
            "answer": {
                "text": "Trendee 提升品牌 AI 可见性。",
                "citations": [],
            }
        }
        with self.assertRaisesRegex(ValueError, "non-empty citations"):
            validate_grounding(value, self.hits)

    def test_numeric_hallucination_is_rejected(self):
        value = {
            "answer": {
                "text": "该方案覆盖 30 个场景。",
                "citations": ["pdf-p030-c01"],
            }
        }
        with self.assertRaisesRegex(ValueError, "numbers absent"):
            validate_grounding(value, self.hits)

    def test_numeric_value_present_in_source_is_allowed(self):
        value = {
            "answer": {
                "text": "品宣内容提到覆盖 20 个场景。",
                "citations": ["pdf-p030-c01"],
            }
        }
        result = validate_grounding(value, self.hits)
        self.assertTrue(result["numeric_guard_passed"])

    def test_hypothetical_bank_scenario_cannot_become_delivered_case(self):
        value = {
            "answer": {
                "text": "万悉科技已服务招商银行并帮助其提升 AI 可见性。",
                "citations": ["pdf-p019-c01"],
            }
        }
        with self.assertRaisesRegex(ValueError, "招商银行应用设想"):
            validate_grounding(value, self.hits)

    def test_hypothetical_bank_scenario_can_stay_hypothetical(self):
        value = {
            "answer": {
                "text": "万悉科技提出了面向招商银行的 GEO 应用设想。",
                "citations": ["pdf-p019-c01"],
            }
        }
        result = validate_grounding(value, self.hits)
        self.assertTrue(result["citation_ids_valid"])

    def test_unsupported_ranking_guarantee_is_rejected(self):
        value = {
            "answer": {
                "text": "该服务保证品牌在 AI 搜索中排名第一。",
                "citations": ["pdf-p002-c01"],
            }
        }
        with self.assertRaisesRegex(ValueError, "unsupported guarantee"):
            validate_grounding(value, self.hits)

    def test_publishable_body_rejects_source_meta_wording(self):
        blog = {
            "title": "GEO",
            "lead": [{
                "text": "资料显示 Trendee 致力于提升品牌 AI 可见性。",
                "citations": ["pdf-p002-c01"],
            }],
            "sections": [{
                "heading": "为什么",
                "paragraphs": [{
                    "text": "Trendee 致力于提升品牌 AI 可见性。",
                    "citations": ["pdf-p002-c01"],
                }],
            }],
            "conclusion": [{
                "text": "AI 可见性是其核心方向之一。",
                "citations": ["pdf-p002-c01"],
            }],
            "faq": [
                {"question": "问题一？", "answer": {"text": "围绕 AI 可见性。", "citations": ["pdf-p002-c01"]}},
                {"question": "问题二？", "answer": {"text": "围绕 AI 可见性。", "citations": ["pdf-p002-c01"]}},
                {"question": "问题三？", "answer": {"text": "围绕 AI 可见性。", "citations": ["pdf-p002-c01"]}},
            ],
            "limitations": [],
        }
        with self.assertRaisesRegex(ValueError, "source-meta wording"):
            validate_document("blog", blog, self.hits, topic="为什么需要 GEO？")


if __name__ == "__main__":
    unittest.main()
