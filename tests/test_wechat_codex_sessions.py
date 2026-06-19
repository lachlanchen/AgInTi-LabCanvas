from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_codex_sessions.py"


def load_sessions():
    spec = importlib.util.spec_from_file_location("wechat_codex_sessions_for_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatCodexSessionTests(unittest.TestCase):
    def test_parse_thread_id_from_json_events(self) -> None:
        sessions = load_sessions()
        events = '{"type":"thread.started","thread_id":"abc"}\n{"type":"turn.completed"}\n'

        self.assertEqual(sessions.parse_thread_id(events), "abc")

    def test_run_codex_session_stores_and_resumes_thread(self) -> None:
        sessions = load_sessions()
        calls: list[list[str]] = []
        original_run = sessions.subprocess.run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                registry = Path(tmp) / "sessions.local.json"

                def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                    calls.append(command)
                    output = Path(command[command.index("-o") + 1])
                    output.write_text("CHAT: ok", encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, '{"type":"thread.started","thread_id":"thread-1"}\n', "")

                sessions.subprocess.run = fake_run
                first = sessions.run_codex_session(
                    "hello",
                    chat_name="EchoMind",
                    role="fast",
                    model="gpt-5.5",
                    reasoning_effort="low",
                    sandbox="read-only",
                    timeout_seconds=30,
                    registry_path=registry,
                )
                second = sessions.run_codex_session(
                    "again",
                    chat_name="EchoMind",
                    role="fast",
                    model="gpt-5.5",
                    reasoning_effort="low",
                    sandbox="read-only",
                    timeout_seconds=30,
                    registry_path=registry,
                )
                data = json.loads(registry.read_text(encoding="utf-8"))
        finally:
            sessions.subprocess.run = original_run

        self.assertTrue(first["ok"])
        self.assertTrue(second["resumed"])
        self.assertNotIn("resume", calls[0])
        self.assertIn("resume", calls[1])
        self.assertIn("thread-1", calls[1])
        self.assertEqual(next(iter(data.values()))["thread_id"], "thread-1")
