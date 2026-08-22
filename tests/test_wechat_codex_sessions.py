from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_codex_sessions.py"


def load_sessions():
    spec = importlib.util.spec_from_file_location("wechat_codex_sessions_for_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatCodexSessionTests(unittest.TestCase):
    def test_parse_thread_id_from_json_events(self) -> None:
        sessions = load_sessions()
        events = '{"type":"thread.started","thread_id":"abc"}\n{"type":"turn.completed"}\n'

        self.assertEqual(sessions.parse_thread_id(events), "abc")

    def test_session_key_is_exact_chat_scoped(self) -> None:
        sessions = load_sessions()

        keys = {
            sessions.session_key("EchoMind", "fast"),
            sessions.session_key("懒人科研", "fast"),
            sessions.session_key("鏈接", "fast"),
            sessions.session_key("写作 外语 挣钱", "fast"),
        }

        self.assertEqual(len(keys), 4)
        self.assertTrue(all(key.startswith("v2:") for key in keys))
        self.assertTrue(all(":fast" in key for key in keys))
        self.assertNotIn("wechat:fast", keys)

    def test_personal_wechat_and_wecom_transport_sessions_cannot_collide(self) -> None:
        sessions = load_sessions()
        personal = sessions.session_key("LabAgent", "worker")
        wecom = sessions.session_key(
            "wecom:external-gui:group:65cbe9ac4a4c",
            "worker",
        )

        self.assertNotEqual(personal, wecom)
        self.assertIn("labagent", personal)
        self.assertIn("wecom-external-gui-group", wecom)

    def test_load_registry_ignores_legacy_keys(self) -> None:
        sessions = load_sessions()

        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "sessions.local.json"
            current_key = sessions.session_key("懒人科研", "fast")
            registry.write_text(
                json.dumps(
                    {
                        "wechat:fast": {"thread_id": "legacy", "chat_name": "懒人科研", "role": "fast"},
                        current_key: {"thread_id": "current", "chat_name": "懒人科研", "role": "fast"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            data = sessions.load_registry(registry)

        self.assertEqual(list(data), [current_key])
        self.assertEqual(data[current_key]["thread_id"], "current")

    def test_run_codex_session_stores_and_resumes_thread(self) -> None:
        sessions = load_sessions()
        calls: list[list[str]] = []
        original_run = sessions.run_process_group
        try:
            with tempfile.TemporaryDirectory() as tmp:
                registry = Path(tmp) / "sessions.local.json"

                def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                    calls.append(command)
                    self.assertIn("input", kwargs)
                    self.assertIn(kwargs["input"], {"hello", "again"})
                    output = Path(command[command.index("-o") + 1])
                    output.write_text("CHAT: ok", encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, '{"type":"thread.started","thread_id":"thread-1"}\n', "")

                sessions.run_process_group = fake_run
                with mock.patch.object(sessions, "resolve_codex_binary", return_value="/usr/bin/codex"):
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
            sessions.run_process_group = original_run

        self.assertTrue(first["ok"])
        self.assertTrue(second["resumed"])
        self.assertNotIn("resume", calls[0])
        self.assertIn("resume", calls[1])
        self.assertIn("thread-1", calls[1])
        self.assertIn("-", calls[0])
        self.assertIn("-", calls[1])
        self.assertNotIn("hello", calls[0])
        self.assertNotIn("again", calls[1])
        self.assertEqual(next(iter(data.values()))["thread_id"], "thread-1")

    def test_run_codex_session_does_not_fallback_after_timeout(self) -> None:
        sessions = load_sessions()
        calls: list[list[str]] = []
        original_run = sessions.run_process_group
        try:
            with tempfile.TemporaryDirectory() as tmp:
                registry = Path(tmp) / "sessions.local.json"
                key = sessions.session_key("EchoMind", "fast")
                registry.write_text(
                    json.dumps({key: {"thread_id": "thread-1", "chat_name": "EchoMind", "role": "fast"}}),
                    encoding="utf-8",
                )

                def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                    calls.append(command)
                    raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))

                sessions.run_process_group = fake_run
                with mock.patch.object(sessions, "resolve_codex_binary", return_value="/usr/bin/codex"):
                    result = sessions.run_codex_session(
                        "hello",
                        chat_name="EchoMind",
                        role="fast",
                        model="gpt-5.5",
                        reasoning_effort="low",
                        sandbox="read-only",
                        timeout_seconds=5,
                        registry_path=registry,
                    )
        finally:
            sessions.run_process_group = original_run

        self.assertFalse(result["ok"])
        self.assertTrue(result["resumed"])
        self.assertFalse(result["fallback_started"])
        self.assertEqual(result["returncode"], 124)
        self.assertEqual(len(calls), 1)
        self.assertIn("resume", calls[0])

    def test_startup_failure_retries_only_before_turn_starts(self) -> None:
        sessions = load_sessions()
        calls = []

        def fake_run(*_args: object, **_kwargs: object) -> dict[str, object]:
            calls.append(True)
            if len(calls) == 1:
                return {
                    "ok": False,
                    "message": "",
                    "thread_id": "",
                    "returncode": 1,
                    "stderr_tail": "failed to refresh available models: timeout waiting for child process to exit",
                    "stdout_tail": "",
                    "execution_started": False,
                    "tool_activity": False,
                }
            return {
                "ok": True,
                "message": "handled",
                "thread_id": "thread-recovered",
                "returncode": 0,
                "stderr_tail": "",
                "stdout_tail": "",
                "execution_started": True,
                "tool_activity": False,
            }

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            sessions, "run_codex_once", side_effect=fake_run
        ), mock.patch.object(sessions.time, "sleep"):
            result = sessions.run_codex_session(
                "hello",
                chat_name="LabAgent",
                role="worker",
                model="gpt-5.6-sol",
                reasoning_effort="medium",
                sandbox="danger-full-access",
                timeout_seconds=30,
                registry_path=Path(tmp) / "sessions.local.json",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["startup_retry_count"], 1)
        self.assertEqual(len(calls), 2)

    def test_startup_failure_does_not_retry_after_tool_activity(self) -> None:
        sessions = load_sessions()
        result = {
            "ok": False,
            "message": "",
            "thread_id": "thread-1",
            "returncode": 1,
            "stderr_tail": "failed to connect to websocket",
            "stdout_tail": "",
            "execution_started": True,
            "tool_activity": True,
        }
        with mock.patch.object(sessions, "run_codex_once", return_value=result) as run:
            actual = sessions.run_codex_with_startup_retries(
                "hello",
                thread_id="thread-1",
                model="gpt-5.6-sol",
                reasoning_effort="medium",
                sandbox="danger-full-access",
                timeout_seconds=30,
                workdir=ROOT,
                web_search=True,
            )

        self.assertFalse(actual["ok"])
        self.assertEqual(actual["startup_retry_count"], 0)
        run.assert_called_once()

    def test_resumed_session_does_not_replay_arbitrary_failure_in_fresh_thread(self) -> None:
        sessions = load_sessions()
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "sessions.local.json"
            key = sessions.session_key("LabAgent", "worker")
            registry.write_text(
                json.dumps({key: {"thread_id": "thread-1", "chat_name": "LabAgent", "role": "worker"}}),
                encoding="utf-8",
            )
            failure = {
                "ok": False,
                "message": "task failed after a tool call",
                "thread_id": "thread-1",
                "returncode": 1,
                "stderr_tail": "tool failed",
                "stdout_tail": "",
                "execution_started": True,
                "tool_activity": True,
            }
            with mock.patch.object(sessions, "run_codex_once", return_value=failure) as run:
                result = sessions.run_codex_session(
                    "hello",
                    chat_name="LabAgent",
                    role="worker",
                    model="gpt-5.6-sol",
                    reasoning_effort="medium",
                    sandbox="danger-full-access",
                    timeout_seconds=30,
                    registry_path=registry,
                )

        self.assertFalse(result["ok"])
        self.assertFalse(result["fallback_started"])
        run.assert_called_once()

    def test_codex_event_evidence_distinguishes_message_from_tool(self) -> None:
        sessions = load_sessions()
        message_only = sessions.codex_event_evidence(
            '{"type":"turn.started"}\n'
            '{"type":"item.completed","item":{"type":"agent_message"}}\n'
        )
        with_tool = sessions.codex_event_evidence(
            '{"type":"turn.started"}\n'
            '{"type":"item.completed","item":{"type":"command_execution"}}\n'
        )

        self.assertEqual(message_only, {"execution_started": True, "tool_activity": False})
        self.assertEqual(with_tool, {"execution_started": True, "tool_activity": True})

    def test_unrelated_chat_sessions_do_not_share_a_long_running_lock(self) -> None:
        sessions = load_sessions()
        first_entered = threading.Event()
        second_entered = threading.Event()
        release = threading.Event()
        results: dict[str, dict[str, object]] = {}

        def fake_run(prompt: str, **_kwargs: object) -> dict[str, object]:
            if prompt == "first":
                first_entered.set()
            else:
                second_entered.set()
            release.wait(timeout=3)
            return {
                "ok": True,
                "message": prompt,
                "thread_id": f"thread-{prompt}",
                "returncode": 0,
                "stderr_tail": "",
                "stdout_tail": "",
            }

        def invoke(name: str, prompt: str, registry: Path) -> None:
            results[name] = sessions.run_codex_session(
                prompt,
                chat_name=name,
                role="fast",
                model="gpt-5.6-sol",
                reasoning_effort="low",
                sandbox="read-only",
                timeout_seconds=30,
                registry_path=registry,
            )

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            sessions, "run_codex_once", side_effect=fake_run
        ):
            registry = Path(tmp) / "sessions.local.json"
            first = threading.Thread(target=invoke, args=("LabAgent", "first", registry))
            second = threading.Thread(target=invoke, args=("EchoMind", "second", registry))
            first.start()
            self.assertTrue(first_entered.wait(timeout=1))
            second.start()
            try:
                self.assertTrue(
                    second_entered.wait(timeout=1),
                    "an unrelated chat was blocked by the first chat's Codex turn",
                )
            finally:
                release.set()
                first.join(timeout=3)
                second.join(timeout=3)
            saved = json.loads(registry.read_text(encoding="utf-8"))

        self.assertTrue(results["LabAgent"]["ok"])
        self.assertTrue(results["EchoMind"]["ok"])
        self.assertEqual(len(saved), 2)

    def test_busy_registry_lock_does_not_block_agent_turn(self) -> None:
        sessions = load_sessions()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            sessions, "acquire_exclusive_lock", return_value=False
        ), mock.patch.object(
            sessions,
            "run_codex_once",
            return_value={
                "ok": True,
                "message": "handled",
                "thread_id": "thread-new",
                "returncode": 0,
                "stderr_tail": "",
                "stdout_tail": "",
            },
        ):
            result = sessions.run_codex_session(
                "new message",
                chat_name="LabAgent",
                role="route",
                model="gpt-5.6-sol",
                reasoning_effort="low",
                sandbox="read-only",
                timeout_seconds=30,
                registry_path=Path(tmp) / "sessions.local.json",
            )

        self.assertTrue(result["ok"])
        self.assertFalse(result["resumed"])
        self.assertFalse(result["registry_persisted"])

    def test_worker_session_enables_native_web_search(self) -> None:
        sessions = load_sessions()
        calls: list[list[str]] = []

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            output = Path(command[command.index("-o") + 1])
            output.write_text("done", encoding="utf-8")
            return subprocess.CompletedProcess(
                command,
                0,
                '{"type":"thread.started","thread_id":"thread-search"}\n',
                "",
            )

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sessions, "resolve_codex_binary", return_value="/usr/bin/codex"), mock.patch.object(
                sessions,
                "run_process_group",
                side_effect=fake_run,
            ), mock.patch.dict(os.environ, {"WECHAT_CODEX_WEB_SEARCH": "1"}, clear=False):
                result = sessions.run_codex_session(
                    "research this",
                    chat_name="LabAgent",
                    role="worker",
                    model="gpt-5.6-sol",
                    reasoning_effort="low",
                    sandbox="danger-full-access",
                    timeout_seconds=30,
                    registry_path=Path(tmp) / "sessions.local.json",
                )

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0][:3], ["/usr/bin/codex", "--search", "exec"])

    def test_process_group_timeout_terminates_all_codex_descendants(self) -> None:
        sessions = load_sessions()
        proc = mock.Mock()
        proc.pid = 1234
        proc.returncode = -15
        proc.poll.return_value = None
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(["codex"], 1),
            ("partial stdout", "partial stderr"),
        ]
        proc.wait.return_value = -15

        with mock.patch.object(sessions.subprocess, "Popen", return_value=proc) as popen, mock.patch.object(
            sessions.os, "getpgid", return_value=1234
        ), mock.patch.object(sessions.os, "killpg") as killpg:
            with self.assertRaises(subprocess.TimeoutExpired):
                sessions.run_process_group(
                    ["codex", "exec"],
                    input="prompt",
                    cwd=ROOT,
                    timeout=1,
                    env={},
                )

        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        killpg.assert_called_once_with(1234, sessions.signal.SIGTERM)
        proc.wait.assert_called_once()

    def test_route_session_does_not_enable_web_search_by_default(self) -> None:
        sessions = load_sessions()

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(sessions.codex_web_search_enabled("route"))
            self.assertTrue(sessions.codex_web_search_enabled("worker"))
            self.assertTrue(sessions.codex_web_search_enabled("career_daily"))
            self.assertTrue(sessions.codex_web_search_enabled("daily_organizer"))

    def test_resolve_codex_binary_finds_nvm_install_when_path_is_minimal(self) -> None:
        sessions = load_sessions()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".nvm" / "versions" / "node" / "v22.21.0" / "bin" / "codex"
            codex.parent.mkdir(parents=True)
            codex.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            codex.chmod(0o755)
            with mock.patch.object(sessions.Path, "home", return_value=home), mock.patch.object(sessions.shutil, "which", return_value=None), mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=False):
                resolved = sessions.resolve_codex_binary()

        self.assertEqual(resolved, str(codex))

    def test_resolve_codex_binary_prefers_nvm_over_home_bin_wrapper(self) -> None:
        sessions = load_sessions()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            wrapper = home / "bin" / "codex"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text("#!/usr/bin/env bash\nexit 127\n", encoding="utf-8")
            wrapper.chmod(0o755)
            codex = home / ".nvm" / "versions" / "node" / "v22.21.0" / "bin" / "codex"
            codex.parent.mkdir(parents=True)
            codex.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            codex.chmod(0o755)
            with mock.patch.object(sessions.Path, "home", return_value=home), mock.patch.object(sessions.shutil, "which", return_value=str(wrapper)), mock.patch.dict(os.environ, {"PATH": str(wrapper.parent), "WECHAT_CODEX_BIN": "", "CODEX_BIN": ""}, clear=False):
                resolved = sessions.resolve_codex_binary()

        self.assertEqual(resolved, str(codex))

    def test_run_codex_once_returns_structured_error_when_codex_missing(self) -> None:
        sessions = load_sessions()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with mock.patch.object(sessions.Path, "home", return_value=home), mock.patch.object(sessions.shutil, "which", return_value=None), mock.patch.dict(os.environ, {"PATH": "/usr/bin", "WECHAT_CODEX_BIN": ""}, clear=False):
                result = sessions.run_codex_once(
                    "hello",
                    thread_id="",
                    model="gpt-5.5",
                    reasoning_effort="low",
                    sandbox="read-only",
                    timeout_seconds=1,
                    workdir=ROOT,
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["returncode"], 127)
