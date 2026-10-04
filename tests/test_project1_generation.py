import unittest

from trendee.rag.generation import render_markdown, validate_document
from trendee.rag.workflow import source_visuals


class Project1GenerationContractTests(unittest.TestCase):
    def setUp(self):
        self.hits = [
            {
                "id": "pdf-p002-c01",
                "text": "Trendee 致力于提升品牌在 AI 问答引擎中的可见性。",
                "source": "sample.pdf",
                "page": 2,
            },
            {
                "id": "pdf-p018-c01",
                "text": "大型集团存在信息复杂、口径分散和组织协同问题。",
                "source": "sample.pdf",
                "page": 18,
            },
        ]

    def _faq3(self):
        return [
            {
                "question": f"延展问题{i}？",
                "answer": {
                    "text": "Trendee 聚焦品牌 AI 可见性。",
                    "citations": ["pdf-p002-c01"],
                },
            }
            for i in range(1, 4)
        ]

    def test_blog_requires_exactly_three_extension_faqs(self):
        blog = {
            "title": "为什么需要 GEO",
            "lead": [{"text": "AI 正在改变品牌信息发现方式。", "citations": ["pdf-p002-c01"]}],
            "sections": [{
                "heading": "品牌可见性",
                "paragraphs": [{
                    "text": "Trendee 聚焦品牌在 AI 问答中的可见性。",
                    "citations": ["pdf-p002-c01"],
                }],
            }],
            "conclusion": [{"text": "GEO 应围绕可见性和知识资产展开。", "citations": ["pdf-p002-c01"]}],
            "faq": self._faq3(),
            "limitations": [],
        }
        result = validate_document("blog", blog, self.hits, topic="为什么需要 GEO？")
        self.assertTrue(result["citation_ids_valid"])

        blog["faq"] = blog["faq"][:2]
        with self.assertRaisesRegex(ValueError, "faq must contain 3-3"):
            validate_document("blog", blog, self.hits, topic="为什么需要 GEO？")

    def test_brand_intro_requires_three_extension_faqs(self):
        brand = {
            "title": "万悉科技品牌介绍",
            "positioning": [{"text": "万悉科技聚焦品牌 AI 可见性。", "citations": ["pdf-p002-c01"]}],
            "value_propositions": [{"text": "帮助品牌更容易被 AI 理解。", "citations": ["pdf-p002-c01"]}],
            "capabilities": [{
                "heading": "知识治理",
                "paragraphs": [{
                    "text": "大型集团需要解决信息复杂与口径分散问题。",
                    "citations": ["pdf-p018-c01"],
                }],
            }],
            "audiences": [{"text": "适用于关注 AI 可见性的品牌团队。", "citations": ["pdf-p002-c01"]}],
            "proof_points": [],
            "faq": self._faq3(),
            "limitations": [],
        }
        self.assertTrue(
            validate_document("brand_intro", brand, self.hits)["citation_ids_valid"]
        )

    def test_product_intro_can_leave_unsupported_optional_sections_empty(self):
        product = {
            "title": "Trendee 产品介绍",
            "summary": [{"text": "Trendee 聚焦品牌 AI 可见性。", "citations": ["pdf-p002-c01"]}],
            "pain_points": [],
            "capabilities": [{
                "heading": "AI 可见性",
                "paragraphs": [{
                    "text": "Trendee 致力于提升品牌在 AI 问答中的可见性。",
                    "citations": ["pdf-p002-c01"],
                }],
            }],
            "use_cases": [],
            "boundaries": [],
            "faq": self._faq3(),
            "limitations": ["当前证据未覆盖价格和交付周期。"],
        }
        result = validate_document("product_intro", product, self.hits)
        self.assertTrue(result["citation_ids_valid"])

    def test_standalone_faq_first_question_preserves_original_topic(self):
        topic = "万悉科技主要帮助客户解决什么问题？"
        faq = {
            "title": "客户问题 FAQ",
            "intro": [{"text": "以下回答围绕客户问题展开。", "citations": ["pdf-p002-c01"]}],
            "faq": [{
                "question": topic,
                "answer": {
                    "text": "Trendee 聚焦品牌 AI 可见性。",
                    "citations": ["pdf-p002-c01"],
                },
            }],
            "conclusion": [{"text": "核心方向是 AI 可见性。", "citations": ["pdf-p002-c01"]}],
            "limitations": [],
        }
        self.assertTrue(validate_document("faq", faq, self.hits, topic=topic)["citation_ids_valid"])

        faq["faq"][0]["question"] = "万悉科技有哪些特点？"
        with self.assertRaisesRegex(ValueError, "FAQ first question"):
            validate_document("faq", faq, self.hits, topic=topic)

    def test_blog_markdown_places_extension_faq_after_conclusion(self):
        blog = {
            "title": "测试",
            "lead": [{"text": "导语。", "citations": ["pdf-p002-c01"]}],
            "sections": [{"heading": "正文", "paragraphs": [{"text": "正文。", "citations": ["pdf-p002-c01"]}]}],
            "conclusion": [{"text": "结语。", "citations": ["pdf-p002-c01"]}],
            "faq": self._faq3(),
            "limitations": [],
        }
        refs = [{"id": "pdf-p002-c01", "page": 2}]
        markdown = render_markdown("blog", blog, refs)
        self.assertLess(markdown.index("## 结语"), markdown.index("## 延展 FAQ"))

    def test_source_visuals_are_unique_limited_and_citation_driven(self):
        refs = [
            {"id": "a", "page": 2, "heading": "A", "source": "x", "asset_path": "assets/pages/p002.png"},
            {"id": "b", "page": 2, "heading": "B", "source": "x", "asset_path": "assets/pages/p002.png"},
            {"id": "c", "page": 18, "heading": "C", "source": "x", "asset_path": "assets/pages/p018.png"},
            {"id": "d", "page": 20, "heading": "D", "source": "x", "asset_path": "assets/pages/p020.png"},
            {"id": "e", "page": 21, "heading": "E", "source": "x", "asset_path": "assets/pages/p021.png"},
        ]
        visuals = source_visuals(refs, max_items=3)
        self.assertEqual([x["page"] for x in visuals], [2, 18, 20])


if __name__ == "__main__":
    unittest.main()
