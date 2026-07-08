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
        self.assertEqual(backend.select_agent_backend({"agent_backend": "agintiflow"}), "aginti")
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

    def test_spark_quota_falls_back_to_codex_55_low(self) -> None:
        backend = load_backend()
        calls: list[dict[str, object]] = []
        original = backend.run_codex_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append({"prompt": prompt, **kwargs})
                if len(calls) == 1:
                    return {
                        "ok": False,
                        "message": "Quota exceeded for gpt-5.3-codex-spark.",
                        "thread_id": "",
                        "returncode": 1,
                        "stderr_tail": "quota exceeded",
                    }
                return {"ok": True, "message": "CHAT: recovered", "thread_id": "codex-55"}

            backend.run_codex_session = fake_run_codex_session
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="EchoMind",
                role="route",
                model="gpt-5.3-codex-spark",
                reasoning_effort="high",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
                backend_config={"agent_fallbacks": {"fallback_to_aginti": False}},
            )
        finally:
            backend.run_codex_session = original

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "codex")
        self.assertEqual(result["model"], "gpt-5.5")
        self.assertTrue(result["backend_fallback_used"])
        self.assertEqual(calls[0]["model"], "gpt-5.3-codex-spark")
        self.assertEqual(calls[0]["reasoning_effort"], "high")
        self.assertEqual(calls[1]["model"], "gpt-5.5")
        self.assertEqual(calls[1]["reasoning_effort"], "low")

    def test_codex_quota_falls_back_to_aginti_after_55_low(self) -> None:
        backend = load_backend()
        codex_calls: list[dict[str, object]] = []
        aginti_calls: list[dict[str, object]] = []
        original_codex = backend.run_codex_session
        original_aginti = backend.run_aginti_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                codex_calls.append({"prompt": prompt, **kwargs})
                return {
                    "ok": False,
                    "message": "rate limit quota",
                    "thread_id": "",
                    "returncode": 1,
                    "stderr_tail": "rate limit quota",
                }

            def fake_run_aginti_session(prompt: str, **kwargs: object) -> dict[str, object]:
                aginti_calls.append({"prompt": prompt, **kwargs})
                return {"ok": True, "message": "CHAT: handled by aginti", "thread_id": "", "returncode": 0}

            backend.run_codex_session = fake_run_codex_session
            backend.run_aginti_session = fake_run_aginti_session
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="懒人科研",
                role="worker",
                model="gpt-5.3-codex-spark",
                reasoning_effort="high",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
                backend_config={
                    "_backends": {"aginti": {"model": "aginti-auto", "reasoning_effort": "low"}},
                    "agent_fallbacks": {"fallback_to_aginti": True},
                },
            )
        finally:
            backend.run_codex_session = original_codex
            backend.run_aginti_session = original_aginti

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "aginti")
        self.assertEqual(result["message"], "CHAT: handled by aginti")
        self.assertTrue(result["backend_fallback_used"])
        self.assertEqual([call["model"] for call in codex_calls], ["gpt-5.3-codex-spark", "gpt-5.5"])
        self.assertEqual(len(aginti_calls), 1)
        self.assertEqual(result["backend_attempts"][-1]["backend"], "aginti")

    def test_timeout_does_not_trigger_backend_fallback(self) -> None:
        backend = load_backend()
        calls: list[dict[str, object]] = []
        original = backend.run_codex_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append({"prompt": prompt, **kwargs})
                return {
                    "ok": False,
                    "message": "Codex failed: timed out before completing the turn.",
                    "thread_id": "",
                    "returncode": 124,
                    "stderr_tail": "timeout",
                }

            backend.run_codex_session = fake_run_codex_session
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="EchoMind",
                role="fast",
                model="gpt-5.3-codex-spark",
                reasoning_effort="high",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
            )
        finally:
            backend.run_codex_session = original

        self.assertFalse(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertFalse(result["backend_fallback_used"])
        self.assertEqual(result["backend_attempts"][0]["failure_kind"], "timeout")

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
