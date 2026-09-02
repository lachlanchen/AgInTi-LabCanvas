from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agenticapp import aginti_shadow


class AgintiShadowTests(unittest.TestCase):
    def test_worker_codex_result_is_queued_privately_without_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            aginti_shadow, "PENDING_DIR", Path(tmp) / "pending"
        ), mock.patch.object(aginti_shadow, "_launch_processor") as launch:
            result = aginti_shadow.enqueue_codex_shadow_review(
                "Research this mechanism",
                {"ok": True, "message": "Evidence-based result"},
                role="worker",
            )
            packets = list((Path(tmp) / "pending").glob("*.json"))

        self.assertTrue(result["queued"])
        self.assertEqual(len(packets), 1)
        launch.assert_not_called()

    def test_fast_chat_and_sensitive_prompts_are_not_shadowed(self) -> None:
        normal = aginti_shadow.enqueue_codex_shadow_review(
            "hello",
            {"ok": True, "message": "hi"},
            role="fast",
            launch=False,
        )
        sensitive = aginti_shadow.enqueue_codex_shadow_review(
            "API_KEY=secret",
            {"ok": True, "message": "done"},
            role="worker",
            launch=False,
        )
        self.assertFalse(normal["queued"])
        self.assertFalse(sensitive["queued"])

    def test_extracts_only_the_final_review_json_from_runtime_logs(self) -> None:
        value = 'runtime log\n{"task_understanding":"t","strengths":"s","missed_requirements":"m","safer_or_faster_approach":"a","reusable_agent_improvements":"i"}\n'
        review = aginti_shadow._extract_review_json(value)
        self.assertEqual(review["task_understanding"], "t")
        self.assertEqual(review["reusable_agent_improvements"], "i")


if __name__ == "__main__":
    unittest.main()
