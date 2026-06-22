from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
SCRIPT = SCRIPTS / "wechat_agent_backend.py"


def load_backend():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("wechat_agent_backend_for_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatAgentBackendTests(unittest.TestCase):
    def test_select_backend_defaults_to_codex_and_accepts_aliases(self) -> None:
        backend = load_backend()

        self.assertEqual(backend.select_agent_backend({}), "codex")
        self.assertEqual(backend.select_agent_backend({"agent_backend": "claude-code"}), "claude")
        self.assertEqual(backend.select_agent_backend({"agent_backend": "unknown"}), "codex")

    def test_codex_backend_delegates_to_existing_session_runner(self) -> None:
        backend = load_backend()
        calls: list[dict[str, object]] = []
        original = backend.run_codex_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append({"prompt": prompt, **kwargs})
                return {"ok": True, "message": "ok", "thread_id": "codex-thread"}

            backend.run_codex_session = fake_run_codex_session
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="EchoMind",
                role="fast",
                model="gpt-5.5",
                reasoning_effort="low",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
            )
        finally:
            backend.run_codex_session = original

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "codex")
        self.assertEqual(calls[0]["chat_name"], "EchoMind")
        self.assertEqual(calls[0]["role"], "fast")

    def test_claude_backend_uses_stdin_and_readonly_tool_block(self) -> None:
        backend = load_backend()
        original_run = backend.subprocess.run
        original_registry = backend.CLAUDE_REGISTRY
        original_session_dir = backend.CLAUDE_SESSION_DIR
        calls: list[dict[str, object]] = []
        try:
            with tempfile.TemporaryDirectory() as tmp:
                backend.CLAUDE_SESSION_DIR = Path(tmp)
                backend.CLAUDE_REGISTRY = Path(tmp) / "sessions.local.json"

                def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                    calls.append({"command": command, **kwargs})
                    return subprocess.CompletedProcess(command, 0, "CHAT: ok\n", "")

                backend.subprocess.run = fake_run
                result = backend.run_agent_session(
                    "long prompt body",
                    backend="claude",
                    chat_name="EchoMind",
                    role="fast",
                    model="gpt-5.5",
                    reasoning_effort="low",
                    sandbox="read-only",
                    timeout_seconds=30,
                    workdir=ROOT,
                    backend_config={"bin": "claude", "permission_mode": "bypassPermissions", "timeout_seconds": 77},
                )
        finally:
            backend.subprocess.run = original_run
            backend.CLAUDE_REGISTRY = original_registry
            backend.CLAUDE_SESSION_DIR = original_session_dir

        command = calls[0]["command"]
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "claude")
        self.assertEqual(calls[0]["input"], "long prompt body")
        self.assertEqual(calls[0]["timeout"], 77)
        self.assertIn("--session-id", command)
        self.assertIn("--disallowedTools", command)
        self.assertNotIn("gpt-5.5", command)


if __name__ == "__main__":
    unittest.main()
