import unittest

from trendee.rag.evidence_gate import (
    assess_evidence_sufficiency,
    validate_evidence_sufficiency,
)


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def json(self, system, user, validator=None, purpose="generation"):
        self.calls.append({"purpose": purpose, "user": user})
        if validator:
            validator(self.response)
        return self.response


class Project1EvidenceGateTests(unittest.TestCase):
    def test_no_hits_is_deterministically_insufficient(self):
        result = assess_evidence_sufficiency(
            topic="任意问题",
            user_goal="获取事实",
            hits=[],
            active_mode="live",
            client=FakeClient({}),
            system_prompt="judge",
        )
        self.assertFalse(result["answerable"])
        self.assertEqual(result["source"], "deterministic")

    def test_offline_mode_does_not_fake_semantic_sufficiency(self):
        result = assess_evidence_sufficiency(
            topic="公司总部办公面积是多少？",
            user_goal="查询一个具体事实",
            hits=[{"id": "x", "text": "公司提供 GEO 服务。"}],
            active_mode="offline",
            client=FakeClient({}),
            system_prompt="judge",
        )
        self.assertTrue(result["answerable"])
        self.assertEqual(result["source"], "offline_passthrough")

    def test_live_gate_handles_arbitrary_missing_fact_without_field_blacklist(self):
        client = FakeClient({
            "answerable": False,
            "missing_information": ["总部办公面积"],
            "reason": "当前证据只描述业务能力，没有办公面积信息。",
        })
        result = assess_evidence_sufficiency(
            topic="公司总部办公面积是多少？",
            user_goal="查询总部办公面积",
            hits=[{
                "id": "pdf-p001-c01",
                "page": 1,
                "heading": "业务能力",
                "text": "公司提供 GEO 服务。",
            }],
            active_mode="live",
            client=client,
            system_prompt="judge",
        )
        self.assertFalse(result["answerable"])
        self.assertEqual(result["missing_information"], ["总部办公面积"])
        self.assertEqual(client.calls[0]["purpose"], "evidence_sufficiency")

    def test_invalid_judge_shape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "answerable"):
            validate_evidence_sufficiency({
                "missing_information": [],
                "reason": "missing answerable",
            })


if __name__ == "__main__":
    unittest.main()
