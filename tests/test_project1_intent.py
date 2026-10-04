import unittest

from trendee.rag.intent import (
    canonical_content_type,
    parse_task_intent,
    retrieval_seed_queries,
    semantic_focus,
)
from trendee.rag.scope import precheck_scope


class Project1IntentTests(unittest.TestCase):
    def test_semantic_focus_customer_pain_points(self):
        self.assertEqual(
            semantic_focus("万悉科技主要帮助客户解决什么问题？"),
            "customer_pain_points",
        )

    def test_semantic_focus_geo_value(self):
        self.assertEqual(
            semantic_focus("为什么中国出海品牌需要进行 GEO 优化？"),
            "geo_value",
        )

    def test_semantic_focus_product_capabilities(self):
        self.assertEqual(
            semantic_focus("Trendee 有哪些核心产品能力？"),
            "product_capabilities",
        )

    def test_explicit_presentation_type_does_not_replace_semantic_focus(self):
        intent = parse_task_intent(
            topic="万悉科技主要帮助客户解决什么问题？",
            audience="市场团队",
            requested_type="产品介绍",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "product_intro")
        self.assertEqual(intent["semantic_focus"], "customer_pain_points")
        self.assertEqual(
            intent["primary_question"],
            "万悉科技主要帮助客户解决什么问题？",
        )
        self.assertIn(
            "客户面临的具体问题、痛点或业务挑战",
            intent["primary_retrieval_needs"],
        )

    def test_product_seed_queries_preserve_original_focus(self):
        queries = retrieval_seed_queries(
            "product_intro",
            "customer_pain_points",
        )
        self.assertTrue(queries)
        joined = "\n".join(queries)
        self.assertRegex(joined, r"客户痛点|解决问题")

    def test_auto_rule_detects_blog(self):
        intent = parse_task_intent(
            topic="为什么中国出海品牌需要进行 GEO 优化？",
            audience="市场团队",
            requested_type="auto",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "blog")
        self.assertEqual(intent["source"], "rule")

    def test_auto_rule_detects_faq(self):
        intent = parse_task_intent(
            topic="请生成FAQ：万悉科技主要帮助客户解决什么问题？",
            audience="市场团队",
            requested_type="auto",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "faq")

    def test_unknown_content_type_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_content_type("短视频脚本")

    def test_greeting_is_meta_and_should_not_enter_rag(self):
        result = precheck_scope("你好")
        self.assertEqual(result["scope"], "meta")
        self.assertEqual(result["meta_intent"], "greeting")

    def test_obvious_unrelated_question_is_out_of_scope(self):
        result = precheck_scope("帮我写一份杭州旅游攻略")
        self.assertEqual(result["scope"], "out_of_scope")

    def test_geo_question_is_in_scope(self):
        result = precheck_scope("GEO 和 SEO 有什么区别？")
        self.assertEqual(result["scope"], "in_scope")


if __name__ == "__main__":
    unittest.main()
