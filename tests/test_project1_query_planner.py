import unittest

from trendee.search.query_planner import passthrough_plan, validate_query_plan


class Project1QueryPlannerTests(unittest.TestCase):
    def test_passthrough_keeps_only_original_query(self):
        plan = passthrough_plan("原始问题")
        self.assertEqual(plan["strategy"], "passthrough")
        self.assertFalse(plan["rewrite_needed"])
        self.assertEqual(plan["retrieval_queries"], ["原始问题"])

    def test_expand_preserves_original_and_deduplicates(self):
        plan = validate_query_plan(
            {
                "strategy": "expand",
                "rewrite_needed": True,
                "intent": "topic_retrieval",
                "retrieval_queries": [
                    "角度一",
                    "角度一",
                    "角度二",
                    "角度三",
                    "角度四会被截断",
                ],
                "reason": "需要多角度召回",
            },
            "原始问题",
        )
        self.assertEqual(plan["retrieval_queries"][0], "原始问题")
        self.assertEqual(plan["retrieval_queries"][1:], ["角度一", "角度二", "角度三"])
        self.assertEqual(plan["strategy"], "expand")

    def test_decompose_requires_extra_query(self):
        with self.assertRaisesRegex(ValueError, "requires at least one extra query"):
            validate_query_plan(
                {
                    "strategy": "decompose",
                    "rewrite_needed": True,
                    "intent": "multi_part",
                    "retrieval_queries": [],
                    "reason": "复杂问题",
                },
                "原始问题",
            )

    def test_passthrough_discards_accidental_expansions(self):
        plan = validate_query_plan(
            {
                "strategy": "passthrough",
                "rewrite_needed": True,
                "intent": "specific_fact",
                "retrieval_queries": ["不应被保留的扩展"],
                "reason": "原问题已经足够具体",
            },
            "原始问题",
        )
        self.assertEqual(plan["retrieval_queries"], ["原始问题"])
        self.assertFalse(plan["rewrite_needed"])

    def test_unknown_strategy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "strategy"):
            validate_query_plan(
                {
                    "strategy": "invent",
                    "rewrite_needed": True,
                    "intent": "x",
                    "retrieval_queries": ["扩展"],
                },
                "原始问题",
            )


if __name__ == "__main__":
    unittest.main()
