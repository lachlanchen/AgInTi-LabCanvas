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
