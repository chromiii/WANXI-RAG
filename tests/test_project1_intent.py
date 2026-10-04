import unittest

from trendee.rag.intent import (
    canonical_content_type,
    parse_task_intent,
    validate_task_intent,
)
from trendee.rag.scope import precheck_scope


class FakeIntentClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def json(self, system, user, validator=None, purpose="generation"):
        self.calls.append({"system": system, "user": user, "purpose": purpose})
        if validator:
            validator(self.response)
        return self.response


class Project1IntentTests(unittest.TestCase):
    def test_content_type_aliases_are_schema_mapping(self):
        self.assertEqual(canonical_content_type("Blog"), "blog")
        self.assertEqual(canonical_content_type("FAQ"), "faq")
        self.assertEqual(canonical_content_type("品牌介绍"), "brand_intro")
        self.assertEqual(canonical_content_type("产品介绍"), "product_intro")
        self.assertEqual(canonical_content_type("auto"), "auto")

    def test_unknown_content_type_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_content_type("短视频脚本")

    def test_explicit_type_offline_does_not_fake_semantic_understanding(self):
        intent = parse_task_intent(
            topic="某个复杂但未分类的问题",
            audience="市场团队",
            requested_type="产品介绍",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "product_intro")
        self.assertEqual(intent["semantic_focus"], "generic")
        self.assertEqual(intent["user_goal"], "某个复杂但未分类的问题")
        self.assertEqual(intent["source"], "explicit")
        self.assertEqual(intent["presentation_source"], "explicit")

    def test_auto_offline_is_deterministic_fallback_not_rule_classifier(self):
        intent = parse_task_intent(
            topic="请生成FAQ：某个问题",
            audience="市场团队",
            requested_type="auto",
            active_mode="offline",
        )
        self.assertEqual(intent["content_type"], "blog")
        self.assertEqual(intent["semantic_focus"], "generic")
        self.assertEqual(intent["source"], "offline_default")
        self.assertEqual(intent["confidence"], 0.0)

    def test_auto_live_uses_llm_intent_classifier(self):
        client = FakeIntentClient({
            "content_type": "faq",
            "semantic_focus": "customer_needs",
            "user_goal": "了解目标客户最需要解决的核心问题",
            "confidence": 0.94,
            "reason": "用户希望获得直接问答式说明",
        })
        intent = parse_task_intent(
            topic="这个服务主要替客户处理哪些麻烦？",
            audience="市场团队",
            requested_type="auto",
            active_mode="live",
            client=client,
            system_prompt="intent prompt",
        )
        self.assertEqual(intent["content_type"], "faq")
        self.assertEqual(intent["semantic_focus"], "customer_needs")
        self.assertEqual(intent["source"], "llm")
        self.assertEqual(client.calls[0]["purpose"], "task_intent")

    def test_explicit_live_type_cannot_be_overridden_by_model(self):
        client = FakeIntentClient({
            "content_type": "blog",
            "semantic_focus": "solution_fit",
            "user_goal": "了解解决方案是否适合当前需求",
            "confidence": 0.87,
            "reason": "语义上像解释型问题",
        })
        intent = parse_task_intent(
            topic="这套方案适合什么场景？",
            audience="市场团队",
            requested_type="FAQ",
            active_mode="live",
            client=client,
            system_prompt="intent prompt",
        )
        self.assertEqual(intent["content_type"], "faq")
        self.assertEqual(intent["semantic_focus"], "solution_fit")
        self.assertEqual(intent["source"], "llm+explicit")
        self.assertEqual(intent["presentation_source"], "explicit")

    def test_classifier_requires_semantic_focus_and_user_goal(self):
        with self.assertRaisesRegex(ValueError, "semantic_focus"):
            validate_task_intent(
                {
                    "content_type": "faq",
                    "user_goal": "回答问题",
                    "confidence": 0.8,
                },
                topic="问题",
                audience="用户",
            )

    def test_classifier_confidence_is_bounded(self):
        result = validate_task_intent(
            {
                "content_type": "faq",
                "semantic_focus": "topic_understanding",
                "user_goal": "回答用户问题",
                "confidence": 1.7,
                "reason": "test",
            },
            topic="问题",
            audience="用户",
        )
        self.assertEqual(result["confidence"], 1.0)

    def test_greeting_is_meta_and_should_not_enter_rag(self):
        result = precheck_scope("你好")
        self.assertEqual(result["scope"], "meta")
        self.assertEqual(result["meta_intent"], "greeting")

    def test_obvious_unrelated_question_is_out_of_scope(self):
        result = precheck_scope("帮我写一份杭州旅游攻略")
        self.assertEqual(result["scope"], "out_of_scope")

    def test_product_capability_question_is_not_mistaken_for_meta(self):
        result = precheck_scope("Trendee 有哪些功能？")
        self.assertEqual(result["scope"], "in_scope")

    def test_product_usage_question_is_not_mistaken_for_meta(self):
        result = precheck_scope("万悉产品如何使用？")
        self.assertNotEqual(result["scope"], "meta")

    def test_geo_question_is_in_scope(self):
        result = precheck_scope("GEO 和 SEO 有什么区别？")
        self.assertEqual(result["scope"], "in_scope")


if __name__ == "__main__":
    unittest.main()
