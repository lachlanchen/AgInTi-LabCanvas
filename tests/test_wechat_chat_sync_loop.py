import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []


def load_wechat_chat_sync_loop():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chat_sync_loop.py"
    spec = importlib.util.spec_from_file_location("wechat_chat_sync_loop_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    test_lock_dir = tempfile.TemporaryDirectory()
    MODULE_TEMP_DIRS.append(test_lock_dir)
    module._test_gui_lock_dir = test_lock_dir
    module.GUI_SEND_LOCK = Path(test_lock_dir.name) / "wechat_gui_send.lock"
    return module


def tearDownModule():
    while MODULE_TEMP_DIRS:
        MODULE_TEMP_DIRS.pop().cleanup()


class WeChatChatSyncLoopTests(unittest.TestCase):
    def test_subprocess_timeout_enters_same_backoff_as_sender_timeout(self):
        module = load_wechat_chat_sync_loop()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "target.json"
            config.write_text(json.dumps({"chat_name": "first", "send_target": {"name": "first"}}))
            args = argparse.Namespace(
                configs=str(config), display=":97", interval=45, pause=0.8, timeout=18,
                priority="", loop=False, once=True, only=[], output_dir=root,
                queue=root / "queue.jsonl", yield_to_queue=False, failure_backoff=300,
                max_targets_per_cycle=0,
            )
            backoff = {}
            with mock.patch.object(module, "gui_send_lock_busy", return_value=False), mock.patch.object(
                module, "open_chat_dry_run", side_effect=subprocess.TimeoutExpired(["gui-send"], 23)
            ) as opener:
                result = module.sync_once(args, failure_backoff_until=backoff)
                again = module.sync_once(args, failure_backoff_until=backoff)
            self.assertEqual(result[0]["returncode"], 124)
            self.assertEqual(result[0]["failure_backoff_seconds"], 300)
            self.assertEqual(again[0]["skipped"], "failure_backoff")
            opener.assert_called_once()

    def write_queue(self, rows):
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "wechat_task_queue.jsonl"
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        self.addCleanup(temp_dir.cleanup)
        return path

    def test_queue_send_lane_busy_detects_retryable_deferred_send(self):
        module = load_wechat_chat_sync_loop()
        queue = self.write_queue(
            [
                {"id": "old", "chat": "EchoMind", "status": "done"},
                {
                    "id": "reply-1",
                    "chat": "🍓我的设备",
                    "status": "send_deferred_locked",
                    "send_deferred_reason": "gui_send_busy",
                },
            ]
        )

        result = module.queue_send_lane_busy(queue)

        self.assertTrue(result["busy"])
        self.assertEqual(result["active"][0]["id"], "reply-1")
        self.assertEqual(result["active"][0]["reason"], "gui_send_busy")

    def test_gui_send_lock_busy_observes_actual_nonblocking_lock(self):
        module = load_wechat_chat_sync_loop()
        lock_path = module.GUI_SEND_LOCK
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with lock_path.open("a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertTrue(module.gui_send_lock_busy())
            fcntl.flock(lock, fcntl.LOCK_UN)

        self.assertFalse(module.gui_send_lock_busy())

    def test_quiet_success_suppresses_routine_target_event(self):
        module = load_wechat_chat_sync_loop()
        emitted = []
        original_emit = module.emit_target_event
        try:
            module.emit_target_event = emitted.append
            args = argparse.Namespace(quiet_success=True)
            module.maybe_emit_target_event(args, {"chat": "EchoMind", "ok": True})
            module.maybe_emit_target_event(args, {"chat": "EchoMind", "ok": False, "error": "failed"})
        finally:
            module.emit_target_event = original_emit

        self.assertEqual(emitted, [{"chat": "EchoMind", "ok": False, "error": "failed"}])

    def test_chat_sync_uses_ephemeral_success_evidence(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output_dir = Path(temp_dir.name) / "persistent"
        evidence_dirs = []
        original_run = module.subprocess.run
        try:
            def fake_run(command, **_kwargs):
                evidence_dir = Path(command[command.index("--output-dir") + 1])
                evidence_dirs.append(evidence_dir)
                (evidence_dir / "01-EchoMind-before.png").write_bytes(b"temporary")
                return subprocess.CompletedProcess(command, 0, stdout='{"results": []}', stderr="")

            module.subprocess.run = fake_run
            args = argparse.Namespace(display=":97", pause=0.1, timeout=60, output_dir=output_dir)
            result = module.open_chat_dry_run(args, "EchoMind", {"name": "EchoMind"})
        finally:
            module.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(len(evidence_dirs), 1)
        self.assertFalse(evidence_dirs[0].exists())
        self.assertFalse(output_dir.exists())

    def test_chat_sync_keeps_only_one_failure_screenshot_and_clears_it_on_success(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        output_dir = Path(temp_dir.name) / "persistent"
        original_run = module.subprocess.run
        calls = 0
        try:
            def fake_run(command, **_kwargs):
                nonlocal calls
                calls += 1
                evidence_dir = Path(command[command.index("--output-dir") + 1])
                (evidence_dir / "01-EchoMind-opened.png").write_bytes(b"failure")
                return subprocess.CompletedProcess(
                    command,
                    1 if calls == 1 else 0,
                    stdout="",
                    stderr="title guard failed" if calls == 1 else "",
                )

            module.subprocess.run = fake_run
            args = argparse.Namespace(display=":97", pause=0.1, timeout=60, output_dir=output_dir)
            failed = module.open_chat_dry_run(args, "EchoMind", {"name": "EchoMind"})
            failure_path = Path(failed["failure_screenshot"])
            self.assertTrue(failure_path.exists())
            self.assertEqual(failure_path.read_bytes(), b"failure")

            succeeded = module.open_chat_dry_run(args, "EchoMind", {"name": "EchoMind"})
        finally:
            module.subprocess.run = original_run

        self.assertTrue(succeeded["ok"])
        self.assertFalse(failure_path.exists())

    def test_sync_once_yields_to_actual_gui_lock_before_opening_chats(self):
        module = load_wechat_chat_sync_loop()
        original_open = module.open_chat_dry_run
        original_emit = module.emit_target_event
        lock_path = module.GUI_SEND_LOCK
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            module.open_chat_dry_run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("should not open chat")
            )
            module.emit_target_event = lambda _result: None
            args = argparse.Namespace(
                configs="missing-config.json",
                display=":97",
                interval=45,
                pause=0.8,
                timeout=60,
                priority="",
                loop=False,
                once=True,
                only=[],
                output_dir=Path("/tmp"),
                queue=Path("/tmp/missing-wechat-queue.jsonl"),
                yield_to_queue=False,
                max_targets_per_cycle=0,
            )
            with lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                results = module.sync_once(args)
                fcntl.flock(lock, fcntl.LOCK_UN)
        finally:
            module.open_chat_dry_run = original_open
            module.emit_target_event = original_emit

        self.assertEqual(results, [{"ok": True, "skipped": "gui_send_lock_reserved"}])

    def test_queue_send_lane_busy_ignores_non_retryable_deferred_send(self):
        module = load_wechat_chat_sync_loop()
        queue = self.write_queue(
            [
                {
                    "id": "needs-human",
                    "chat": "懒人科研",
                    "status": "send_deferred_locked",
                    "send_deferred_reason": "unknown_manual_blocker",
                }
            ]
        )

        result = module.queue_send_lane_busy(queue)

        self.assertFalse(result["busy"])

    def test_queue_send_lane_busy_honors_external_sender_reservation(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        marker = Path(temp_dir.name) / "send-priority.json"
        marker.write_text(
            json.dumps(
                {
                    "token": "daily-1",
                    "owner": "career_daily",
                    "chat": "lachlanchan",
                    "expires_at": time.time() + 60,
                }
            ),
            encoding="utf-8",
        )
        module.GUI_SEND_PRIORITY = marker

        result = module.queue_send_lane_busy(Path(temp_dir.name) / "missing-queue.jsonl")

        self.assertTrue(result["busy"])
        self.assertEqual(result["active"][0]["id"], "daily-1")
        self.assertEqual(result["active"][0]["chat"], "lachlanchan")
        self.assertEqual(result["active"][0]["reason"], "career_daily")

    def test_queue_send_lane_busy_removes_expired_sender_reservation(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        marker = Path(temp_dir.name) / "send-priority.json"
        marker.write_text(
            json.dumps(
                {
                    "token": "expired-1",
                    "owner": "career_daily",
                    "chat": "lachlanchan",
                    "expires_at": time.time() - 1,
                }
            ),
            encoding="utf-8",
        )
        module.GUI_SEND_PRIORITY = marker

        result = module.queue_send_lane_busy(Path(temp_dir.name) / "missing-queue.jsonl")

        self.assertFalse(result["busy"])
        self.assertFalse(marker.exists())

    def test_queue_send_lane_busy_removes_corrupt_sender_reservation(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        marker = Path(temp_dir.name) / "send-priority.json"
        marker.write_text("{not-json", encoding="utf-8")
        module.GUI_SEND_PRIORITY = marker

        result = module.queue_send_lane_busy(Path(temp_dir.name) / "missing-queue.jsonl")

        self.assertFalse(result["busy"])
        self.assertFalse(marker.exists())

    def test_queue_send_lane_busy_removes_dead_sender_reservation(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        marker = Path(temp_dir.name) / "send-priority.json"
        marker.write_text(
            json.dumps(
                {
                    "token": "dead-1",
                    "owner": "career_daily",
                    "chat": "lachlanchan",
                    "pid": 2_000_000_000,
                    "expires_at": time.time() + 600,
                }
            ),
            encoding="utf-8",
        )
        module.GUI_SEND_PRIORITY = marker

        result = module.queue_send_lane_busy(Path(temp_dir.name) / "missing-queue.jsonl")

        self.assertFalse(result["busy"])
        self.assertFalse(marker.exists())

    def test_sync_once_yields_to_queue_before_opening_chats(self):
        module = load_wechat_chat_sync_loop()
        queue = self.write_queue(
            [
                {
                    "id": "reply-2",
                    "chat": "EchoMind",
                    "status": "send_deferred_locked",
                    "send_deferred_reason": "gui_send_timeout",
                }
            ]
        )
        original_open = module.open_chat_dry_run
        original_emit = module.emit_target_event
        try:
            module.open_chat_dry_run = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not open chat"))
            module.emit_target_event = lambda _result: None
            args = argparse.Namespace(
                configs="missing-config.json",
                display=":97",
                interval=45,
                pause=0.8,
                timeout=60,
                priority="",
                loop=False,
                once=True,
                only=[],
                output_dir=Path("/tmp"),
                queue=queue,
                yield_to_queue=True,
                max_targets_per_cycle=0,
            )

            results = module.sync_once(args)
        finally:
            module.open_chat_dry_run = original_open
            module.emit_target_event = original_emit

        self.assertEqual(results[0]["skipped"], "send_lane_reserved")
        self.assertEqual(results[0]["active"][0]["id"], "reply-2")

    def test_sync_once_rechecks_queue_between_targets(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        first = root / "first.json"
        second = root / "second.json"
        first.write_text(json.dumps({"chat_name": "first", "send_target": {"name": "first"}}), encoding="utf-8")
        second.write_text(json.dumps({"chat_name": "second", "send_target": {"name": "second"}}), encoding="utf-8")
        queue = self.write_queue([])
        opened = []
        original_open = module.open_chat_dry_run
        original_emit = module.emit_target_event
        try:
            def fake_open(_args, chat_name, _target):
                opened.append(chat_name)
                queue.write_text(
                    json.dumps(
                        {
                            "id": "appeared-after-first",
                            "chat": "EchoMind",
                            "status": "send_deferred_locked",
                            "send_deferred_reason": "gui_send_busy",
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return {"chat": chat_name, "ok": True}

            module.open_chat_dry_run = fake_open
            module.emit_target_event = lambda _result: None
            args = argparse.Namespace(
                configs=f"{first},{second}",
                display=":97",
                interval=45,
                pause=0.8,
                timeout=60,
                priority="",
                loop=False,
                once=True,
                only=[],
                output_dir=Path("/tmp"),
                queue=queue,
                yield_to_queue=True,
                max_targets_per_cycle=0,
            )

            results = module.sync_once(args)
        finally:
            module.open_chat_dry_run = original_open
            module.emit_target_event = original_emit

        self.assertEqual(opened, ["first"])
        self.assertEqual(results[0], {"chat": "first", "ok": True})
        self.assertEqual(results[1]["skipped"], "send_lane_reserved")
        self.assertEqual(results[1]["active"][0]["id"], "appeared-after-first")

    def test_sync_once_backs_off_retryable_failure_without_blocking_other_chats(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        first = root / "first.json"
        second = root / "second.json"
        first.write_text(json.dumps({"chat_name": "first", "send_target": {"name": "first"}}), encoding="utf-8")
        second.write_text(json.dumps({"chat_name": "second", "send_target": {"name": "second"}}), encoding="utf-8")
        opened = []
        backoff = {}
        original_open = module.open_chat_dry_run
        original_emit = module.emit_target_event
        try:
            def fake_open(_args, chat_name, _target):
                opened.append(chat_name)
                if chat_name == "first":
                    return {
                        "chat": chat_name,
                        "ok": False,
                        "returncode": 124,
                        "stderr_tail": "WECHAT_SEND_TIMEOUT: GUI sender exceeded 55 seconds",
                    }
                return {"chat": chat_name, "ok": True}

            module.open_chat_dry_run = fake_open
            module.emit_target_event = lambda _result: None
            args = argparse.Namespace(
                configs=f"{first},{second}",
                display=":97",
                interval=45,
                pause=0.8,
                timeout=60,
                priority="",
                loop=False,
                once=True,
                only=[],
                output_dir=Path("/tmp"),
                queue=Path("/tmp/missing-wechat-queue.jsonl"),
                yield_to_queue=False,
                failure_backoff=300,
                max_targets_per_cycle=0,
            )

            results = module.sync_once(args, failure_backoff_until=backoff)
            opened.clear()
            second_results = module.sync_once(args, failure_backoff_until=backoff)
        finally:
            module.open_chat_dry_run = original_open
            module.emit_target_event = original_emit

        self.assertEqual(results[0]["chat"], "first")
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["failure_backoff_seconds"], 300)
        self.assertIn("retry_at", results[0])
        self.assertEqual(results[1], {"chat": "second", "ok": True})
        self.assertEqual(second_results[0]["skipped"], "failure_backoff")
        self.assertEqual(second_results[0]["chat"], "first")
        self.assertEqual(second_results[1], {"chat": "second", "ok": True})
        self.assertEqual(opened, ["second"])

    def test_sync_once_limits_opened_targets_per_cycle(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        paths = []
        for name in ("first", "second", "third"):
            path = root / f"{name}.json"
            path.write_text(json.dumps({"chat_name": name, "send_target": {"name": name}}), encoding="utf-8")
            paths.append(path)
        opened = []
        original_open = module.open_chat_dry_run
        original_emit = module.emit_target_event
        try:
            def fake_open(_args, chat_name, _target):
                opened.append(chat_name)
                return {"chat": chat_name, "ok": True}

            module.open_chat_dry_run = fake_open
            module.emit_target_event = lambda _result: None
            args = argparse.Namespace(
                configs=",".join(str(path) for path in paths),
                display=":97",
                interval=45,
                pause=0.8,
                timeout=60,
                priority="",
                loop=False,
                once=True,
                only=[],
                output_dir=Path("/tmp"),
                queue=Path("/tmp/missing-wechat-queue.jsonl"),
                yield_to_queue=False,
                failure_backoff=300,
                max_targets_per_cycle=1,
            )

            results = module.sync_once(args, failure_backoff_until={})
        finally:
            module.open_chat_dry_run = original_open
            module.emit_target_event = original_emit

        self.assertEqual(opened, ["first"])
        self.assertEqual(results[0], {"chat": "first", "ok": True})
        self.assertEqual(results[1]["skipped"], "max_targets_per_cycle")
        self.assertEqual(results[2]["skipped"], "max_targets_per_cycle")

    def test_limited_sync_round_robins_across_cycles(self):
        module = load_wechat_chat_sync_loop()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        paths = []
        for name in ("first", "second", "third"):
            path = root / f"{name}.json"
            path.write_text(json.dumps({"chat_name": name, "send_target": {"name": name}}), encoding="utf-8")
            paths.append(path)
        opened = []
        original_open = module.open_chat_dry_run
        original_emit = module.emit_target_event
        try:
            def fake_open(_args, chat_name, _target):
                opened.append(chat_name)
                return {"chat": chat_name, "ok": True}

            module.open_chat_dry_run = fake_open
            module.emit_target_event = lambda _result: None
            args = argparse.Namespace(
                configs=",".join(str(path) for path in paths),
                display=":97",
                interval=45,
                pause=0.8,
                timeout=60,
                priority="",
                loop=False,
                once=True,
                only=[],
                output_dir=Path("/tmp"),
                queue=Path("/tmp/missing-wechat-queue.jsonl"),
                yield_to_queue=False,
                failure_backoff=300,
                max_targets_per_cycle=1,
            )

            first_results = module.sync_once(args, failure_backoff_until={})
            second_results = module.sync_once(args, failure_backoff_until={})
            third_results = module.sync_once(args, failure_backoff_until={})
        finally:
            module.open_chat_dry_run = original_open
            module.emit_target_event = original_emit

        self.assertEqual(opened, ["first", "second", "third"])
        self.assertEqual(first_results[0], {"chat": "first", "ok": True})
        self.assertEqual(second_results[0], {"chat": "second", "ok": True})
        self.assertEqual(third_results[0], {"chat": "third", "ok": True})

    def test_chat_sync_failure_retryable_covers_timeout_and_noisy_title_guard(self):
        module = load_wechat_chat_sync_loop()

        self.assertTrue(module.chat_sync_failure_retryable({"returncode": 124}))
        self.assertTrue(
            module.chat_sync_failure_retryable(
                {"returncode": 1, "stderr_tail": "RuntimeError: Opened chat title guard failed: OCR='3 - oO\\n|'."}
            )
        )
        self.assertTrue(
            module.chat_sync_failure_retryable(
                {"returncode": 1, "stderr_tail": "WECHAT_ENTRY_REQUIRED: approve login on phone"}
            )
        )
        self.assertFalse(module.chat_sync_failure_retryable({"returncode": 1, "stderr_tail": "missing config"}))

    def test_chat_sync_gui_send_env_uses_sync_timeout_for_dry_open(self):
        module = load_wechat_chat_sync_loop()
        args = argparse.Namespace(timeout=60, pause=0.8)

        env = module.chat_sync_gui_send_env(args)

        self.assertEqual(env["WECHAT_GUI_SEND_MAX_SECONDS"], "55")
        self.assertEqual(env["WECHAT_INITIAL_TITLE_WAIT"], "0.4")
        self.assertEqual(env["WECHAT_GUI_SEND_LOCK_WAIT_SECONDS"], "0")
        self.assertLessEqual(float(env["WECHAT_TITLE_RETRY_SECONDS"]), 2.0)
        self.assertEqual(module.chat_sync_subprocess_timeout(args), 60)


if __name__ == "__main__":
    unittest.main()
