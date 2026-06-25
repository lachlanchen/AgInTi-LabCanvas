import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_wechat_career_daily_agent():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_career_daily_agent.py"
    spec = importlib.util.spec_from_file_location("wechat_career_daily_agent_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatCareerDailyAgentTests(unittest.TestCase):
    def test_prompt_requires_three_self_discovery_questions(self):
        module = load_wechat_career_daily_agent()
        prompt = module.build_prompt(
            {
                "memory_snapshot": "- writing/money pattern",
                "project_surface": "- LabCanvas",
                "lazyinvestment_snapshot": "",
                "voidabyss_snapshot": "",
                "identity_surface": "",
            }
        )

        self.assertIn("Today’s 3 self-discovery questions", prompt)
        self.assertIn("exactly three questions", prompt)
        self.assertIn("specific to the", prompt)
        self.assertIn("Q1:", prompt)

    def test_extract_self_discovery_questions_for_chat_message(self):
        module = load_wechat_career_daily_agent()
        report = """
## 9. Today’s 3 self-discovery questions

Q1: Which public problem would I still want to explain if nobody praised me for it?
Why it matters: It reveals durable motivation.
Q2: What am I avoiding by building one more tool instead of publishing one clear offer?
Why it matters: It exposes avoidance disguised as productivity.
Q3: Which project would hurt most to abandon, and what does that say about my real identity?
Why it matters: It shows attachment and leverage.

## Appendix
Other text?
"""

        questions = module.extract_self_discovery_questions(report)

        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0], "Which public problem would I still want to explain if nobody praised me for it?")
        self.assertIn("one more tool", questions[1])
        self.assertIn("real identity", questions[2])

    def test_send_daily_result_includes_self_discovery_questions(self):
        module = load_wechat_career_daily_agent()
        sent_messages = []
        sent_files = []
        module.send_message = lambda message, chat, send_targets: sent_messages.append((message, chat, send_targets))
        module.send_file = lambda report, chat, send_targets: sent_files.append((report, chat, send_targets))
        args = argparse.Namespace(
            send_chat="lachlanchan",
            send_targets=Path("/tmp/send-targets.json"),
            attach_report=True,
        )
        body = """
## 1. Today’s thesis
A precise thesis for the day.

## 9. Today’s 3 self-discovery questions
Q1: What desire am I protecting by not choosing one public offer?
Why it matters: It names avoidance.
Q2: Which audience would I be willing to disappoint in order to serve the right one?
Why it matters: It clarifies tradeoffs.
Q3: What small proof today would make this identity feel real?
Why it matters: It turns reflection into evidence.
"""

        status = module.send_daily_result(args, Path("/tmp/report.md"), body)

        self.assertTrue(status["message_sent"])
        self.assertTrue(status["file_sent"])
        self.assertIn("今日3个自我发现问题", sent_messages[0][0])
        self.assertIn("not choosing one public offer", sent_messages[0][0])
        self.assertIn("small proof today", sent_messages[0][0])
        self.assertEqual(sent_messages[0][1], "lachlanchan")
        self.assertEqual(sent_files[0][0], Path("/tmp/report.md"))

    def test_run_daily_writes_trace_bundle_and_sanitized_share_report(self):
        module = load_wechat_career_daily_agent()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        module.ROOT = root
        module.PRIVATE = root / ".private"
        module.OUTPUT = root / "output"
        module.DEFAULT_SEND_TARGETS = module.PRIVATE / "wechat_send_targets.local.json"
        module.collect_evidence = lambda _chats, _memory_db: {
            "memory_snapshot": "- private pattern: writing and money",
            "project_surface": "- AgenticApp: local tool surface",
            "lazyinvestment_snapshot": "- LazyInvestment missing in test",
            "voidabyss_snapshot": "- VoidAbyss narrative evidence",
            "identity_surface": "- lazying.art identity evidence",
        }
        module.select_agent_backend = lambda _config: "codex"
        module.run_agent_session = lambda *args, **kwargs: {
            "ok": True,
            "message": f"# Today\nUse {module.PRIVATE} as private evidence, then write one public action.",
            "backend": "codex",
            "thread_id": "thread-test",
            "resumed": True,
            "returncode": 0,
        }
        args = argparse.Namespace(
            chat=[],
            send=False,
            attach_report=False,
            memory_db=root / "memory.sqlite",
            send_targets=module.DEFAULT_SEND_TARGETS,
            model="gpt-test",
            reasoning_effort="high",
            timeout_seconds=30,
        )

        payload = module.run_daily(args)

        self.assertTrue(payload["ok"])
        trace_dir = Path(payload["trace_dir"])
        self.assertTrue((trace_dir / "manifest.json").exists())
        self.assertTrue((trace_dir / "agent_prompt.md").exists())
        self.assertTrue((trace_dir / "memory_snapshot.md").exists())
        self.assertTrue((trace_dir / "private_report.md").exists())
        self.assertTrue((trace_dir / "share_report.md").exists())
        self.assertTrue((trace_dir / "agent_result.json").exists())

        manifest = json.loads((trace_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "labcanvas.wechat.career_daily.trace.v1")
        self.assertEqual(manifest["agent"]["model"], "gpt-test")
        self.assertIn("memory_snapshot.md", manifest["inputs"]["evidence_files"]["memory_snapshot"])
        self.assertIn("private_report.md", manifest["outputs"]["private_report_trace"])

        private_report = Path(payload["private_report"]).read_text(encoding="utf-8")
        share_report = Path(payload["share_report"]).read_text(encoding="utf-8")
        self.assertIn(str(module.PRIVATE), private_report)
        self.assertNotIn(str(module.PRIVATE), share_report)
        self.assertIn("<private-wechat-workspace>", share_report)


if __name__ == "__main__":
    unittest.main()
