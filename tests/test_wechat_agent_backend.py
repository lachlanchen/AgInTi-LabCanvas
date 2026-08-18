from __future__ import annotations

import importlib.util
import json
import os
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
    def test_low_normal_quota_prefers_spark_for_cached_lightweight_turn(self) -> None:
        backend = load_backend()
        calls: list[dict[str, object]] = []
        with (
            mock.patch.object(
                backend,
                "current_codex_quota_status",
                return_value={"ok": True, "remaining_percent": 24.9},
            ),
            mock.patch.object(
                backend,
                "run_codex_session",
                side_effect=lambda prompt, **kwargs: (
                    calls.append(kwargs)
                    or {"ok": True, "message": "spark response", "thread_id": "spark"}
                ),
            ),
        ):
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="EchoMind",
                role="route",
                model="gpt-5.6-sol",
                reasoning_effort="medium",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0]["model"], "gpt-5.3-codex-spark")
        self.assertEqual(calls[0]["reasoning_effort"], "low")
        self.assertEqual(result["backend_attempts"][0]["model"], "gpt-5.3-codex-spark")

    def test_low_quota_preference_is_strict_cache_only_and_worker_safe(self) -> None:
        backend = load_backend()
        unchanged = backend.quota_aware_codex_preference(
            backend="codex",
            model="gpt-5.6-sol",
            reasoning_effort="medium",
            role="worker",
            backend_config={},
        )
        self.assertEqual(unchanged, ("gpt-5.6-sol", "medium", None))
        with mock.patch.object(
            backend,
            "current_codex_quota_status",
            return_value={"ok": True, "remaining_percent": 25.0},
        ) as quota:
            threshold = backend.quota_aware_codex_preference(
                backend="codex",
                model="gpt-5.6-sol",
                reasoning_effort="low",
                role="fast",
                backend_config={},
            )
        self.assertEqual(threshold, ("gpt-5.6-sol", "low", None))
        self.assertFalse(quota.call_args.kwargs["refresh"])

    def test_unknown_preferred_model_retries_configured_codex_fallback(self) -> None:
        backend = load_backend()
        calls: list[dict[str, object]] = []
        original = backend.run_codex_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append(kwargs)
                if len(calls) == 1:
                    return {"ok": False, "message": "Unknown model: auto-code-review", "returncode": 1}
                return {"ok": True, "message": "recovered", "thread_id": "fallback-thread"}
            backend.run_codex_session = fake_run_codex_session
            result = backend.run_agent_session(
                "hello",
                backend="codex",
                chat_name="EchoMind",
                role="fast",
                model="auto-code-review",
                reasoning_effort="low",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
                backend_config={"agent_fallbacks": {"fallback_to_aginti": False}},
                fallback_model="gpt-5.6-sol",
                fallback_reasoning_effort="low",
            )
        finally:
            backend.run_codex_session = original
        self.assertTrue(result["ok"])
        self.assertEqual(calls[1]["model"], "gpt-5.6-sol")
    def test_select_backend_defaults_to_aginti_and_accepts_aliases(self) -> None:
        backend = load_backend()

        self.assertEqual(backend.select_agent_backend({}), "aginti")
        self.assertEqual(backend.select_agent_backend({"agent_backend": "claude-code"}), "claude")
        self.assertEqual(backend.select_agent_backend({"agent_backend": "agintiflow"}), "aginti")
        self.assertEqual(backend.select_agent_backend({"agent_backend": "unknown"}), "aginti")

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
                    "agent_fallbacks": {
                        "fallback_to_aginti": True,
                        "purchased_credit_retry": False,
                    },
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

    def test_fast_role_rejects_generic_aginti_execution_evidence_refusal(self) -> None:
        backend = load_backend()
        refusal = (
            "I could not verify that the requested action was executed, so I "
            "stopped instead of claiming success. Missing evidence categories: "
            "file, command, artifact, browser, visual, publish. Retry with an "
            "enabled execution tool or resolve the reported environment blocker."
        )
        with (
            mock.patch.object(
                backend,
                "run_codex_session",
                return_value={
                    "ok": False,
                    "message": "Codex timed out",
                    "returncode": 124,
                    "stderr_tail": "timeout",
                },
            ),
            mock.patch.object(
                backend,
                "run_aginti_session",
                return_value={
                    "ok": True,
                    "message": refusal,
                    "thread_id": "",
                    "returncode": 0,
                },
            ),
        ):
            result = backend.run_agent_session(
                "Answer this ordinary memo naturally.",
                backend="codex",
                chat_name="MEMO写作—外语—挣钱",
                role="fast",
                model="gpt-5.6-sol",
                reasoning_effort="low",
                sandbox="read-only",
                timeout_seconds=25,
                workdir=ROOT,
                backend_config={
                    "agent_fallbacks": {"fallback_to_aginti": True},
                },
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "")
        self.assertEqual(
            result["reason"],
            "invalid_conversational_evidence_refusal",
        )
        self.assertEqual(result["backend_attempts"][-1]["failure_kind"], "empty")

    def test_worker_role_preserves_real_execution_evidence_blocker(self) -> None:
        backend = load_backend()
        refusal = (
            "I could not verify that the requested action was executed, so I "
            "stopped instead of claiming success. Missing evidence categories: "
            "file, command, artifact, browser, visual, publish. Retry with an "
            "enabled execution tool or resolve the reported environment blocker."
        )
        with mock.patch.object(
            backend,
            "run_aginti_session",
            return_value={
                "ok": True,
                "message": refusal,
                "thread_id": "",
                "returncode": 0,
            },
        ):
            result = backend.run_agent_session(
                "Create and verify the requested artifact.",
                backend="aginti",
                chat_name="MEMO写作—外语—挣钱",
                role="worker",
                model="aginti",
                reasoning_effort="medium",
                sandbox="danger-full-access",
                timeout_seconds=60,
                workdir=ROOT,
                backend_config={
                    "agent_fallbacks": {"fallback_to_aginti": False},
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], refusal)

    def test_backend_session_banner_is_not_user_facing_content(self) -> None:
        backend = load_backend()

        self.assertEqual(backend.user_facing_backend_message("Session: web-agent-4a6d272a-b13d-4a16-ab2e-5fcdececdd12"), "")
        self.assertFalse(backend.backend_result_has_content({"message": "web-agent-4a6d272a-b13d-4a16-ab2e-5fcdececdd12"}))
        self.assertEqual(backend.user_facing_backend_message("CHAT: useful answer"), "CHAT: useful answer")

    def test_default_aginti_command_uses_strict_machine_chatops_mode(self) -> None:
        backend = load_backend()

        command = backend.aginti_command(
            model="aginti",
            role="fast",
            sandbox="read-only",
            backend_config={},
        )

        self.assertEqual(command[:4], ["aginti", "run", "--stdin", "--json"])
        self.assertIn("chatops", command)
        self.assertIn("--no-scs", command)
        self.assertIn("--no-shell", command)
        self.assertIn("--no-file-tools", command)
        self.assertIn("--no-mcp", command)
        self.assertIn("host", command)

    def test_named_route_role_stays_conversational_and_scopes_evidence(self) -> None:
        backend = load_backend()
        command = backend.aginti_command(
            model="aginti",
            role="route-context-v3",
            sandbox="read-only",
            backend_config={},
        )
        prompt = backend.aginti_prompt(
            "Return strict routing JSON.",
            chat_name="LabAgent",
            role="route-context-v3",
            model="aginti",
            reasoning_effort="low",
            sandbox="read-only",
            backend_config={},
        )

        self.assertIn("--no-shell", command)
        self.assertIn("--no-file-tools", command)
        self.assertIn('"mode":"chat-response"', prompt)

    def test_aginti_machine_command_cannot_override_managed_sandbox_args(self) -> None:
        backend = load_backend()

        command = backend.aginti_command(
            model="aginti",
            role="worker",
            sandbox="read-only",
            backend_config={
                "command": [
                    "aginti",
                    "run",
                    "--permission-mode",
                    "danger",
                    "--trusted-host-shell",
                    "--mcp",
                ],
                "args": [
                    "--sandbox-mode",
                    "host",
                    "--package-install-policy",
                    "allow",
                    "--allow-shell",
                    "--allow-file-tools",
                    "--allow-auxiliary-tools",
                    "--allow-wrappers",
                    "--scs",
                    "auto",
                    "--provider",
                    "deepseek",
                ],
            },
        )

        self.assertEqual(command.count("run"), 1)
        self.assertEqual(command[command.index("--permission-mode") + 1], "safe")
        self.assertEqual(command[command.index("--sandbox-mode") + 1], "docker-readonly")
        self.assertEqual(command[command.index("--package-install-policy") + 1], "block")
        self.assertIn("--no-scs", command)
        self.assertIn("--no-mcp", command)
        self.assertNotIn("danger", command)
        self.assertNotIn("--trusted-host-shell", command)
        self.assertNotIn("--allow-shell", command)
        self.assertNotIn("--allow-file-tools", command)
        self.assertNotIn("--allow-auxiliary-tools", command)
        self.assertNotIn("--allow-wrappers", command)
        self.assertIn("--provider", command)
        self.assertIn("deepseek", command)

    def test_default_aginti_run_uses_stdin_and_extracts_only_machine_result(self) -> None:
        backend = load_backend()
        completed = subprocess.CompletedProcess(
            ["aginti", "run", "--stdin", "--json"],
            0,
            stdout='{"ok":true,"sessionId":"test","result":"CHAT: actual answer","failed":false}',
            stderr="",
        )
        with (
            mock.patch.object(backend, "resolve_command_executable", return_value="aginti"),
            mock.patch.object(backend, "run_process_group", return_value=completed) as run,
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
                reuse=False,
                backend_config={"wrap_prompt": False},
            )

        command = run.call_args.args[0]
        self.assertEqual(Path(command[0]).name, "aginti")
        self.assertEqual(command[1], "run")
        self.assertIn("--session-id", command)
        self.assertIn("--stdin", command)
        self.assertIn("--json", command)
        self.assertEqual(run.call_args.kwargs["input"], "original prompt")
        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "CHAT: actual answer")
        self.assertEqual(result["message_source"], "machine_json")
        self.assertEqual(result["stdout_tail"], "")

    def test_stopped_aginti_machine_result_is_not_forwarded_to_chat(self) -> None:
        backend = load_backend()
        completed = subprocess.CompletedProcess(
            ["aginti", "run", "--stdin", "--json"],
            1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "sessionId": "stopped-session",
                    "result": "I stopped safely instead of claiming completion.",
                    "stopped": True,
                    "failed": True,
                    "reason": "tool_contract_violation",
                }
            ),
            stderr="",
        )
        with (
            mock.patch.object(backend, "resolve_command_executable", return_value="aginti"),
            mock.patch.object(backend, "run_process_group", return_value=completed),
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
                reuse=False,
                backend_config={"wrap_prompt": False, "provider_chain": ["deepseek"]},
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "")
        self.assertIn("tool_contract_violation", result["stderr_tail"])

    def test_aginti_reuses_one_private_session_per_chat_and_role(self) -> None:
        backend = load_backend()
        first = subprocess.CompletedProcess(
            ["aginti", "run"],
            0,
            stdout='{"ok":true,"sessionId":"web-agent-reused","result":"CHAT: first","failed":false}',
            stderr="",
        )
        second = subprocess.CompletedProcess(
            ["aginti", "resume"],
            0,
            stdout='{"ok":true,"sessionId":"web-agent-reused","result":"CHAT: second","failed":false}',
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "aginti_sessions"
            with (
                mock.patch.object(backend, "AGINTI_SESSION_DIR", session_dir),
                mock.patch.object(backend, "AGINTI_REGISTRY", session_dir / "sessions.local.json"),
                mock.patch.object(backend, "resolve_command_executable", return_value="aginti"),
                mock.patch.object(
                    backend,
                    "run_process_group",
                    side_effect=[first, second],
                ) as run,
            ):
                initial = backend.run_aginti_session(
                    "first prompt",
                    chat_name="EchoMind",
                    role="fast",
                    model="aginti",
                    reasoning_effort="low",
                    sandbox="read-only",
                    timeout_seconds=120,
                    workdir=ROOT,
                    backend_config={"wrap_prompt": False, "provider_chain": ["deepseek"]},
                )
                resumed = backend.run_aginti_session(
                    "follow-up prompt",
                    chat_name="EchoMind",
                    role="fast",
                    model="aginti",
                    reasoning_effort="low",
                    sandbox="read-only",
                    timeout_seconds=120,
                    workdir=ROOT,
                    backend_config={"wrap_prompt": False, "provider_chain": ["deepseek"]},
                )

            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0][1], "run")
            self.assertIn("--session-id", commands[0])
            self.assertEqual(commands[1][1:3], ["resume", "web-agent-reused"])
            self.assertFalse(initial["resumed"])
            self.assertTrue(resumed["resumed"])
            registry = json.loads((session_dir / "sessions.local.json").read_text(encoding="utf-8"))
            record = next(iter(registry.values()))
            self.assertEqual(record["thread_id"], "web-agent-reused")
            self.assertEqual(record["turn_count"], 2)

    def test_backend_specific_prompt_replaces_oversized_codex_prompt_for_aginti(self) -> None:
        backend = load_backend()
        codex_prompts: list[str] = []
        aginti_prompts: list[str] = []

        def codex(prompt: str, **_kwargs: object) -> dict[str, object]:
            codex_prompts.append(prompt)
            return {
                "ok": False,
                "message": "quota exceeded",
                "returncode": 1,
                "stderr_tail": "quota exceeded",
            }

        def aginti(prompt: str, **_kwargs: object) -> dict[str, object]:
            aginti_prompts.append(prompt)
            return {
                "ok": True,
                "message": "CHAT: compact fallback worked",
                "returncode": 0,
                "thread_id": "",
            }

        with (
            mock.patch.object(backend, "run_codex_session", side_effect=codex),
            mock.patch.object(backend, "run_aginti_session", side_effect=aginti),
        ):
            result = backend.run_agent_session(
                "FULL " + ("global handbook " * 5000),
                backend="codex",
                chat_name="LabAgent",
                role="worker",
                model="gpt-5.6-sol",
                reasoning_effort="medium",
                sandbox="read-only",
                timeout_seconds=30,
                workdir=ROOT,
                backend_config={
                    "agent_fallbacks": {
                        "fallback_to_aginti": True,
                        "purchased_credit_retry": False,
                    }
                },
                backend_prompts={"aginti": "COMPACT exact routine packet"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(len(codex_prompts), 1)
        self.assertGreater(len(codex_prompts[0]), 50000)
        self.assertEqual(aginti_prompts, ["COMPACT exact routine packet"])

    def test_aginti_retries_explicit_provider_only_for_pre_inference_failure(self) -> None:
        backend = load_backend()
        failed = subprocess.CompletedProcess(
            ["aginti", "run"],
            1,
            stdout='{"ok":false,"reason":"DeepSeek API key is not configured"}',
            stderr="",
        )
        succeeded = subprocess.CompletedProcess(
            ["aginti", "run"],
            0,
            stdout='{"ok":true,"sessionId":"test","result":"CHAT: local fallback worked","failed":false}',
            stderr="",
        )
        with (
            mock.patch.object(backend, "resolve_command_executable", return_value="aginti"),
            mock.patch.object(
                backend,
                "run_process_group",
                side_effect=[failed, succeeded],
            ) as run,
        ):
            result = backend.run_aginti_session(
                "exact prompt",
                chat_name="LabAgent",
                role="worker",
                model="aginti",
                reasoning_effort="medium",
                sandbox="read-only",
                timeout_seconds=120,
                workdir=ROOT,
                reuse=False,
                backend_config={
                    "wrap_prompt": False,
                    "provider_chain": ["deepseek", "localllm"],
                    "provider_models": {"deepseek": "deepseek-v4-flash", "localllm": "localllm-fast"},
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "localllm")
        self.assertEqual([item["provider"] for item in result["provider_attempts"]], ["deepseek", "localllm"])
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][commands[0].index("--provider") + 1], "deepseek")
        self.assertEqual(commands[1][commands[1].index("--provider") + 1], "localllm")
        self.assertEqual(commands[0][commands[0].index("--model") + 1], "deepseek-v4-flash")
        self.assertEqual(commands[1][commands[1].index("--model") + 1], "localllm-fast")
        generated_session = commands[0][commands[0].index("--session-id") + 1]
        self.assertEqual(commands[1][1:3], ["resume", generated_session])
        prompts = [call.kwargs["input"] for call in run.call_args_list]
        self.assertEqual(prompts[0], "exact prompt")
        self.assertIn("Provider handoff", prompts[1])
        self.assertNotIn("exact prompt", prompts[1])
        self.assertTrue(result["fallback_continued_same_session"])
        self.assertFalse(result["resumed"])

    def test_aginti_shared_backend_reads_wecom_provider_environment(self) -> None:
        backend = load_backend()

        with mock.patch.dict(
            os.environ,
            {
                "WECOM_AGINTI_PROVIDER_CHAIN": "localllm,deepseek",
                "WECOM_AGINTI_WORKSPACE": str(ROOT),
            },
            clear=True,
        ):
            providers = backend.aginti_provider_chain({})
            workdir = backend.aginti_workdir_from_config({}, ROOT.parent)

        self.assertEqual(providers, ["localllm", "deepseek"])
        self.assertEqual(workdir, ROOT)

    def test_aginti_does_not_replay_unknown_task_failure_on_another_provider(self) -> None:
        backend = load_backend()
        failed = subprocess.CompletedProcess(
            ["aginti", "run"],
            1,
            stdout='{"ok":false,"reason":"artifact validation failed after execution"}',
            stderr="",
        )
        with (
            mock.patch.object(backend, "resolve_command_executable", return_value="aginti"),
            mock.patch.object(backend, "run_process_group", return_value=failed) as run,
        ):
            result = backend.run_aginti_session(
                "exact prompt",
                chat_name="LabAgent",
                role="worker",
                model="aginti",
                reasoning_effort="medium",
                sandbox="read-only",
                timeout_seconds=120,
                workdir=ROOT,
                reuse=False,
                backend_config={
                    "wrap_prompt": False,
                    "provider_chain": ["deepseek", "localllm"],
                },
            )

        self.assertFalse(result["ok"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["provider"], "deepseek")

    def test_aginti_resolves_from_nvm_when_service_path_is_minimal(self) -> None:
        backend = load_backend()
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / ".nvm" / "versions" / "node" / "v22.0.0" / "bin" / "aginti"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            with mock.patch.object(backend.shutil, "which", return_value=None), mock.patch.object(
                backend.Path, "home", return_value=Path(tmp)
            ):
                resolved = backend.resolve_command_executable("aginti")

        self.assertEqual(resolved, str(executable.resolve()))

    def test_backend_available_checks_aginti_not_codex(self) -> None:
        backend = load_backend()
        with mock.patch.object(backend, "resolve_command_executable", return_value="/opt/aginti") as resolve:
            available = backend.backend_available("aginti")

        self.assertEqual(available, "/opt/aginti")
        resolve.assert_called_once_with("aginti")

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
                backend_config={
                    "sessions_dir": tmp,
                    "machine_mode": False,
                    "allow_legacy_output": True,
                },
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
                backend_config={
                    "sessions_dir": tmp,
                    "machine_mode": False,
                    "allow_legacy_output": True,
                },
                expected_prompt="exact current prompt",
            )

        self.assertEqual(message, "")
        self.assertEqual(source, "unavailable")

    def test_aginti_machine_mode_rejects_console_pollution(self) -> None:
        backend = load_backend()

        message, source = backend.extract_aginti_user_message(
            'Session: old\n{"ok":true,"result":"CHAT: answer"}',
            backend_config={},
        )

        self.assertEqual(message, "")
        self.assertEqual(source, "invalid_machine_json")

    def test_aginti_contract_rejects_internal_runtime_report(self) -> None:
        backend = load_backend()

        reason = backend.aginti_result_contract_error(
            "## SCS Hard Contract\nValidator report: unrelated output",
            expected_prompt="Answer the current question.",
        )

        self.assertEqual(reason, "internal_runtime_report_rejected")

        tool_reason = backend.aginti_result_contract_error(
            "CHAT: answer\nTool: web_search\nOutput: internal trace",
            expected_prompt="Answer the current question.",
        )
        self.assertEqual(tool_reason, "internal_tool_output_rejected")

    def test_codex_quota_retries_once_when_purchased_credits_are_available(self) -> None:
        backend = load_backend()
        calls: list[dict[str, object]] = []
        original = backend.run_codex_session
        try:
            def fake_run_codex_session(prompt: str, **kwargs: object) -> dict[str, object]:
                calls.append({"prompt": prompt, **kwargs})
                if len(calls) == 1:
                    return {
                        "ok": False,
                        "message": "quota exceeded",
                        "thread_id": "",
                        "returncode": 1,
                        "stderr_tail": "quota exceeded",
                    }
                return {
                    "ok": True,
                    "message": "CHAT: paid-credit retry worked",
                    "thread_id": "paid-credit",
                    "returncode": 0,
                }

            backend.run_codex_session = fake_run_codex_session
            with mock.patch.object(backend, "purchased_codex_credits_available", return_value=True):
                result = backend.run_agent_session(
                    "hello",
                    backend="codex",
                    chat_name="LabAgent",
                    role="worker",
                    model="gpt-5.6-sol",
                    reasoning_effort="medium",
                    sandbox="read-only",
                    timeout_seconds=30,
                    workdir=ROOT,
                    backend_config={
                        "agent_fallbacks": {
                            "fallback_to_aginti": False,
                            "purchased_credit_retry": True,
                        }
                    },
                )
        finally:
            backend.run_codex_session = original

        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(result["backend_attempts"][1]["credit_retry"])
        self.assertEqual(
            result["backend_attempts"][1]["fallback_reason"],
            "codex_purchased_credit_retry",
        )

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
        original_run = backend.run_process_group
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

                backend.run_process_group = fake_run
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
            backend.run_process_group = original_run
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
