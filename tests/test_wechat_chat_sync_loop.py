import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


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
    return module


class WeChatChatSyncLoopTests(unittest.TestCase):
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

    def test_chat_sync_failure_retryable_covers_timeout_and_noisy_title_guard(self):
        module = load_wechat_chat_sync_loop()

        self.assertTrue(module.chat_sync_failure_retryable({"returncode": 124}))
        self.assertTrue(
            module.chat_sync_failure_retryable(
                {"returncode": 1, "stderr_tail": "RuntimeError: Opened chat title guard failed: OCR='3 - oO\\n|'."}
            )
        )
        self.assertFalse(module.chat_sync_failure_retryable({"returncode": 1, "stderr_tail": "missing config"}))

    def test_chat_sync_gui_send_env_uses_sync_timeout_for_dry_open(self):
        module = load_wechat_chat_sync_loop()
        args = argparse.Namespace(timeout=60, pause=0.8)

        env = module.chat_sync_gui_send_env(args)

        self.assertEqual(env["WECHAT_GUI_SEND_MAX_SECONDS"], "55")
        self.assertEqual(env["WECHAT_INITIAL_TITLE_WAIT"], "0.4")
        self.assertLessEqual(float(env["WECHAT_TITLE_RETRY_SECONDS"]), 2.0)
        self.assertEqual(module.chat_sync_subprocess_timeout(args), 60)


if __name__ == "__main__":
    unittest.main()
