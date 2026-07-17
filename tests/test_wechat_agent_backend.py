from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


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

    def test_spark_quota_falls_back_to_codex_56_sol_low(self) -> None:
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
                return {"ok": True, "message": "CHAT: recovered", "thread_id": "codex-56-sol"}

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
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertTrue(result["backend_fallback_used"])
        self.assertEqual(calls[0]["model"], "gpt-5.3-codex-spark")
        self.assertEqual(calls[0]["reasoning_effort"], "high")
        self.assertEqual(calls[1]["model"], "gpt-5.6-sol")
        self.assertEqual(calls[1]["reasoning_effort"], "low")

    def test_codex_quota_falls_back_to_aginti_after_56_sol_low(self) -> None:
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
        self.assertEqual([call["model"] for call in codex_calls], ["gpt-5.3-codex-spark", "gpt-5.6-sol"])
        self.assertEqual(len(aginti_calls), 1)
        self.assertEqual(result["backend_attempts"][-1]["backend"], "aginti")

    def test_empty_spark_response_falls_back_to_codex_56_sol_low(self) -> None:
        backend = load_backend()
        calls: list[dict[str, object]] = []
        original = backend.run_codex_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append({"prompt": prompt, **kwargs})
                if len(calls) == 1:
                    return {"ok": True, "message": "", "thread_id": "spark-thread", "returncode": 0}
                return {"ok": True, "message": "CHAT: recovered from empty output", "thread_id": "sol-thread"}

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
        self.assertEqual([call["model"] for call in calls], ["gpt-5.3-codex-spark", "gpt-5.6-sol"])
        self.assertEqual(result["backend_attempts"][0]["failure_kind"], "empty")

    def test_codex_timeout_falls_back_to_aginti_when_enabled(self) -> None:
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
                    "message": "Codex failed: timed out before completing the turn.",
                    "thread_id": "",
                    "returncode": 124,
                    "stderr_tail": "timeout",
                }

            def fake_run_aginti_session(prompt: str, **kwargs: object) -> dict[str, object]:
                aginti_calls.append({"prompt": prompt, **kwargs})
                return {"ok": True, "message": "CHAT: handled after timeout", "thread_id": "", "returncode": 0}

            backend.run_codex_session = fake_run_codex_session
            backend.run_aginti_session = fake_run_aginti_session
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
        self.assertEqual(result["message"], "CHAT: handled after timeout")
        self.assertTrue(result["backend_fallback_used"])
        self.assertEqual(len(codex_calls), 1)
        self.assertEqual(len(aginti_calls), 1)
        self.assertEqual(result["backend_attempts"][0]["failure_kind"], "timeout")
        self.assertEqual(result["backend_attempts"][-1]["backend"], "aginti")

    def test_backend_session_banner_is_not_user_facing_content(self) -> None:
        backend = load_backend()

        self.assertEqual(backend.user_facing_backend_message("Session: web-agent-4a6d272a-b13d-4a16-ab2e-5fcdececdd12"), "")
        self.assertFalse(backend.backend_result_has_content({"message": "web-agent-4a6d272a-b13d-4a16-ab2e-5fcdececdd12"}))
        self.assertEqual(backend.user_facing_backend_message("CHAT: useful answer"), "CHAT: useful answer")

    def test_default_aginti_command_uses_backward_compatible_one_shot(self) -> None:
        backend = load_backend()

        command = backend.aginti_command(model="aginti", role="fast", backend_config={})

        self.assertEqual(command, ["aginti"])

    def test_default_aginti_run_passes_the_wrapped_prompt_as_one_argument(self) -> None:
        backend = load_backend()
        completed = subprocess.CompletedProcess(
            ["aginti", "original prompt"],
            0,
            stdout="CHAT: actual answer",
            stderr="",
        )
        with (
            mock.patch.object(backend, "command_available", return_value=True),
            mock.patch.object(backend.subprocess, "run", return_value=completed) as run,
        ):
            result = backend.run_aginti_session(
                "original prompt",
                chat_name="EchoMind",
                role="fast",
                model="aginti",
                reasoning_effort="low",
                sandbox="read-only",
                timeout_seconds=120,
                workdir=ROOT,
                backend_config={"wrap_prompt": False},
            )

        command = run.call_args.args[0]
        self.assertEqual(command, ["aginti", "original prompt"])
        self.assertIsNone(run.call_args.kwargs["input"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "CHAT: actual answer")

    def test_aginti_message_comes_from_final_session_assistant_turn(self) -> None:
        backend = load_backend()
        session_id = "web-agent-11111111-2222-3333-4444-555555555555"
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / session_id
            state_dir.mkdir(parents=True)
            (state_dir / "state.json").write_text(
                '{"messages":['
                '{"role":"user","content":"Goal: exact current prompt"},'
                '{"role":"assistant","content":"CHAT: actual language answer"}'
                ']}',
                encoding="utf-8",
            )
            message, source = backend.extract_aginti_user_message(
                f"Session: {session_id}\nProvider: test\nPlan:\n1. internal plan\n",
                backend_config={"sessions_dir": tmp},
                expected_prompt="exact current prompt",
            )

        self.assertEqual(message, "CHAT: actual language answer")
        self.assertEqual(source, "session_state")

    def test_aginti_session_state_must_belong_to_the_current_prompt(self) -> None:
        backend = load_backend()
        session_id = "web-agent-11111111-2222-3333-4444-555555555555"
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / session_id
            state_dir.mkdir(parents=True)
            (state_dir / "state.json").write_text(
                '{"messages":['
                '{"role":"user","content":"Goal: unrelated old task"},'
                '{"role":"assistant","content":"CHAT: stale answer"}'
                ']}',
                encoding="utf-8",
            )
            message, source = backend.extract_aginti_user_message(
                f"Session: {session_id}\nProvider: test\n",
                backend_config={"sessions_dir": tmp},
                expected_prompt="exact current prompt",
            )

        self.assertEqual(message, "")
        self.assertEqual(source, "unavailable")

    def test_metadata_only_aginti_fallback_is_rejected(self) -> None:
        backend = load_backend()
        original_codex = backend.run_codex_session
        original_aginti = backend.run_aginti_session
        try:
            backend.run_codex_session = lambda *args, **kwargs: {
                "ok": False,
                "message": "Codex failed: timed out before completing the turn.",
                "thread_id": "",
                "returncode": 124,
                "stderr_tail": "timeout",
            }
            backend.run_aginti_session = lambda *args, **kwargs: {
                "ok": True,
                "message": "Session: web-agent-4a6d272a-b13d-4a16-ab2e-5fcdececdd12",
                "thread_id": "",
                "returncode": 0,
            }
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="EchoMind",
                role="fast",
                model="gpt-5.6-sol",
                reasoning_effort="low",
                sandbox="read-only",
                timeout_seconds=25,
                workdir=ROOT,
                backend_config={"agent_fallbacks": {"fallback_to_aginti": True}},
            )
        finally:
            backend.run_codex_session = original_codex
            backend.run_aginti_session = original_aginti

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "")
        self.assertEqual(result["reason"], "empty_response")
        self.assertTrue(result["backend_fallback_used"])

    def test_timeout_fallback_can_be_disabled(self) -> None:
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
                backend_config={"agent_fallbacks": {"fallback_to_aginti": True, "fallback_on_timeout": False}},
            )
        finally:
            backend.run_codex_session = original

        self.assertFalse(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertFalse(result["backend_fallback_used"])
        self.assertEqual(result["backend_attempts"][0]["failure_kind"], "timeout")

    def test_fallback_reads_top_level_aginti_config(self) -> None:
        backend = load_backend()
        aginti_calls: list[dict[str, object]] = []
        original_codex = backend.run_codex_session
        original_aginti = backend.run_aginti_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                return {
                    "ok": False,
                    "message": "Codex failed: timed out before completing the turn.",
                    "thread_id": "",
                    "returncode": 124,
                    "stderr_tail": "timeout",
                }

            def fake_run_aginti_session(prompt: str, **kwargs: object) -> dict[str, object]:
                aginti_calls.append({"prompt": prompt, **kwargs})
                return {"ok": True, "message": "CHAT: top-level aginti config", "thread_id": "", "returncode": 0}

            backend.run_codex_session = fake_run_codex_session
            backend.run_aginti_session = fake_run_aginti_session
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="懒人科研",
                role="worker",
                model="gpt-5.5",
                reasoning_effort="medium",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
                backend_config={
                    "aginti": {"model": "aginti-fast", "reasoning_effort": "low", "timeout_seconds": 88},
                    "agent_fallbacks": {"fallback_to_aginti": True},
                },
            )
        finally:
            backend.run_codex_session = original_codex
            backend.run_aginti_session = original_aginti

        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "aginti")
        self.assertEqual(result["message"], "CHAT: top-level aginti config")
        self.assertEqual(result["model"], "aginti-fast")
        self.assertEqual(aginti_calls[0]["timeout_seconds"], 88)

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
