import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"
sys.path.insert(0, str(SCRIPTS))
import wechat_task_worker as worker


class TranslationPolicyTests(unittest.TestCase):
    def test_translation_uses_shared_policy_and_preserves_override(self):
        policy = {
            "model": "policy-model", "reasoning_effort": "low",
            "fallback_model": "fallback-model", "fallback_reasoning_effort": "medium",
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "report.md"
            output = Path(tmp) / "report.en.md"
            source.write_text("Report source")
            for override in ("", "explicit-model"):
                with (
                    self.subTest(override=override),
                    mock.patch.dict(os.environ, {}, clear=True),
                    mock.patch.object(worker, "load_worker_model_policy", return_value=policy),
                    mock.patch.object(worker, "select_agent_backend", return_value="codex"),
                    mock.patch.object(worker, "run_codex_session", return_value={
                        "ok": True, "message": "# Translated report",
                    }) as run,
                ):
                    if override:
                        os.environ["WECHAT_MARKDOWN_TRANSLATION_MODEL"] = override
                    self.assertEqual(worker.translate_markdown_for_pdf(source, output, "en"), output)
                    self.assertEqual(run.call_args.kwargs["model"], override or "policy-model")
                    self.assertEqual(run.call_args.kwargs["fallback_model"], "fallback-model")
                    self.assertFalse(run.call_args.kwargs["reuse"])
                    self.assertEqual(output.read_text(), "# Translated report\n")


if __name__ == "__main__":
    unittest.main()
