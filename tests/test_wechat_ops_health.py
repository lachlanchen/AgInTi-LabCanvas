from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from agenticapp import wechat_ops


class WeChatOpsHealthTests(unittest.TestCase):
    def test_desktop_status_reports_fresh_watchdog_lock(self) -> None:
        original_run = wechat_ops.run_command
        original_port = wechat_ops.port_listening
        original_watchdog = wechat_ops.fresh_unlock_watchdog_state
        try:
            wechat_ops.run_command = lambda *args, **kwargs: subprocess.CompletedProcess(  # type: ignore[assignment]
                args[0],
                0,
                "123\n",
                "",
            )
            wechat_ops.port_listening = lambda _port: True  # type: ignore[assignment]
            wechat_ops.fresh_unlock_watchdog_state = lambda: {  # type: ignore[assignment]
                "desktop": {"status": "locked"},
                "age_seconds": 2,
            }

            payload = wechat_ops.desktop_status()
        finally:
            wechat_ops.run_command = original_run  # type: ignore[assignment]
            wechat_ops.port_listening = original_port  # type: ignore[assignment]
            wechat_ops.fresh_unlock_watchdog_state = original_watchdog  # type: ignore[assignment]

        self.assertEqual(payload["status"], "locked")
        self.assertEqual(payload["watchdog"]["desktop"]["status"], "locked")

    def test_direct_monitor_health_reports_stale_sources_not_ready(self) -> None:
        original_discover = wechat_ops.discover_direct_monitor_configs
        original_config_health = wechat_ops.direct_config_health
        original_backend = wechat_ops.external_backend_summary
        original_separation = wechat_ops.direct_config_separation_summary
        try:
            wechat_ops.discover_direct_monitor_configs = lambda: [Path("echo.local.json")]  # type: ignore[assignment]
            wechat_ops.direct_config_health = lambda _path: {  # type: ignore[assignment]
                "ok": False,
                "chat_name": "EchoMind",
                "caught_up": True,
                "ready": False,
                "source_stale": True,
                "db_stale": True,
            }
            wechat_ops.external_backend_summary = lambda: {"ok": True}  # type: ignore[assignment]
            wechat_ops.direct_config_separation_summary = lambda _paths: {"ok": True}  # type: ignore[assignment]

            payload = wechat_ops.direct_monitor_health()
        finally:
            wechat_ops.discover_direct_monitor_configs = original_discover  # type: ignore[assignment]
            wechat_ops.direct_config_health = original_config_health  # type: ignore[assignment]
            wechat_ops.external_backend_summary = original_backend  # type: ignore[assignment]
            wechat_ops.direct_config_separation_summary = original_separation  # type: ignore[assignment]

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["caught_up_groups"], 1)
        self.assertEqual(payload["ready_groups"], 0)
        self.assertEqual(payload["stale_source_groups"], 1)
        self.assertIn("ready also requires", payload["notes"][-1])

    def test_cli_health_uses_transport_heartbeats_for_exit_status(self) -> None:
        original_direct = wechat_ops.direct_monitor_health
        original_transport = wechat_ops.persistent_transport_health
        try:
            wechat_ops.direct_monitor_health = lambda: {  # type: ignore[assignment]
                "ok": False,
                "ready_groups": 0,
                "group_count": 1,
                "stale_source_groups": 1,
                "queue": {"attention": {"needs_attention": False}},
            }
            wechat_ops.persistent_transport_health = lambda: {  # type: ignore[assignment]
                "ok": True,
                "severity": "ok",
                "direct_monitors": {"healthy": 1, "configured": 1},
            }
            with redirect_stdout(io.StringIO()) as stdout:
                rc = wechat_ops.cmd_health(argparse.Namespace(json=True))
        finally:
            wechat_ops.direct_monitor_health = original_direct  # type: ignore[assignment]
            wechat_ops.persistent_transport_health = original_transport  # type: ignore[assignment]

        payload = json.loads(stdout.getvalue())
        self.assertEqual(rc, 0)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["diagnostic_ok"])
        self.assertTrue(payload["transport_health"]["ok"])

    def test_persistent_transport_health_reuses_fresh_snapshot(self) -> None:
        original = wechat_ops.TRANSPORT_HEALTH_SNAPSHOT
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "latest.json"
            snapshot.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                ),
                encoding="utf-8",
            )
            try:
                wechat_ops.TRANSPORT_HEALTH_SNAPSHOT = snapshot
                payload = wechat_ops.persistent_transport_health(max_age_seconds=90)
            finally:
                wechat_ops.TRANSPORT_HEALTH_SNAPSHOT = original

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "persistent_guard")


class WeChatOpsSendApiTests(unittest.TestCase):
    def test_send_api_rejects_internal_no_reply_control(self) -> None:
        variants = [
            "CHAT: NO_REPLY：internal explanation",
            "aginti: startup log\nNO-REPLY: internal explanation",
        ]
        for message in variants:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, "empty after sanitization"):
                wechat_ops.send_wechat_message_api(
                    message=message,
                    target={"name": "EchoMind", "expected_title": "EchoMind"},
                    dry_run=True,
                )

    def test_send_api_uses_guarded_target_registry_and_filters_logs(self) -> None:
        original_run = wechat_ops.run_command
        original_runtime_paths = wechat_ops.configured_runtime_paths
        calls: list[list[str]] = []
        try:
            def fake_run(command, *, capture, env=None):
                calls.append(command)
                target_file = Path(command[command.index("--targets-file") + 1])
                payload = json.loads(target_file.read_text(encoding="utf-8"))
                self.assertEqual(payload["message"], "hello\nuseful line")
                self.assertEqual(payload["targets"][0]["name"], "EchoMind")
                return subprocess.CompletedProcess(command, 0, json.dumps({"results": [{"status": "sent"}]}), "")

            wechat_ops.run_command = fake_run  # type: ignore[assignment]
            wechat_ops.configured_runtime_paths = lambda: {"mirror_db": Path("/tmp/mirror.sqlite"), "queue": Path("/tmp/q.jsonl")}  # type: ignore[assignment]
            with tempfile.TemporaryDirectory() as tmp:
                target_file = Path(tmp) / "targets.json"
                target_file.write_text(
                    json.dumps({"EchoMind": {"name": "EchoMind", "query": "EchoMind", "expected_title": "EchoMind"}}),
                    encoding="utf-8",
                )
                config = Path(tmp) / "chat.json"
                config.write_text(json.dumps({"display": ":99"}), encoding="utf-8")

                payload = wechat_ops.send_wechat_message_api(
                    message="aginti: noisy startup\nhello\nstdout: internal trace\nuseful line",
                    chat="EchoMind",
                    send_targets=target_file,
                    config=config,
                    dry_run=False,
                )
        finally:
            wechat_ops.run_command = original_run  # type: ignore[assignment]
            wechat_ops.configured_runtime_paths = original_runtime_paths  # type: ignore[assignment]

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"]["expected_title"], "EchoMind")
        self.assertIn("--send", calls[0])
        self.assertIn("--no-search", calls[0])

    def test_send_api_rejects_target_without_title_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                wechat_ops.send_wechat_message_api(
                    message="hello",
                    target={"expected_title": ""},
                    send_targets=Path(tmp) / "missing-targets.json",
                    config=Path(tmp) / "missing.json",
                    dry_run=True,
                )


class WeChatOpsApprovalTests(unittest.TestCase):
    def test_approve_story_confirmation_promotes_to_generated_video_and_preserves_story(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            story_path = Path(tmp) / "story.md"
            task = {
                "id": "task-story",
                "chat": "懒人科研",
                "status": "waiting_confirmation",
                "request": "Current coalesced request:\nWrite a LALACHAN story first.",
                "route_decision": {
                    "route_kind": "story_or_script",
                    "project": "lalachan",
                    "worker_needed": True,
                    "public_publish_allowed": False,
                },
                "routine": {"id": "story_script_generation"},
                "story_confirmation_required": True,
                "generation_blocked_until_story_confirmed": True,
                "result": {
                    "message": "A clean approved story about Uma Gumi and konnyaku.",
                    "files": [str(story_path)],
                    "confirmation": "这个故事可以用来生成 30s 视频吗？",
                },
            }
            queue.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")

            updated = wechat_ops.update_waiting_task(
                queue,
                "task-story",
                decision="approve",
                note="story ok generate video now",
            )

        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["route_decision"]["route_kind"], "generate_video")
        self.assertEqual(updated["routine"]["id"], "generated_video")
        self.assertFalse(updated["story_confirmation_required"])
        self.assertFalse(updated["generation_blocked_until_story_confirmed"])
        self.assertEqual(updated["story_confirmation_result"]["message"], "A clean approved story about Uma Gumi and konnyaku.")
        self.assertEqual(updated["approved_story_files"], [str(story_path)])
        self.assertEqual(updated["stage_transition"]["from"], "story_script_generation")
        self.assertEqual(updated["stage_transition"]["to"], "generated_video")
        self.assertNotIn("result", updated)

    def test_approve_story_confirmation_negative_note_does_not_promote_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            task = {
                "id": "task-story",
                "chat": "懒人科研",
                "status": "waiting_confirmation",
                "request": "Current coalesced request:\nWrite a LALACHAN story first.",
                "route_decision": {"route_kind": "story_or_script", "project": "lalachan"},
                "routine": {"id": "story_script_generation"},
                "story_confirmation_required": True,
                "result": {
                    "message": "Draft story.",
                    "files": [],
                    "confirmation": "这个故事可以用来生成 30s 视频吗？",
                },
            }
            queue.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")

            updated = wechat_ops.update_waiting_task(
                queue,
                "task-story",
                decision="approve",
                note="story ok but do not generate video yet",
            )

        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["route_decision"]["route_kind"], "story_or_script")
        self.assertEqual(updated["routine"]["id"], "story_script_generation")
        self.assertIn("result", updated)


class WeChatOpsUserScriptTests(unittest.TestCase):
    def test_install_user_scripts_writes_after_reboot_stack_launcher(self) -> None:
        original_home = os.environ.get("HOME")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HOME"] = tmp
            try:
                args = argparse.Namespace(json=True)
                with redirect_stdout(io.StringIO()) as stdout:
                    rc = wechat_ops.cmd_install_user_scripts(args)
            finally:
                if original_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = original_home

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            installed = payload["installed"]
            reboot_wrapper = Path(tmp) / "scripts" / "create-labcanvas-wechat-after-reboot.sh"
            stack_wrapper = Path(tmp) / "scripts" / "create-labcanvas-wechat-stack.sh"
            self.assertIn(str(reboot_wrapper), installed)
            self.assertTrue(reboot_wrapper.exists())
            self.assertTrue(stack_wrapper.exists())

            reboot_text = reboot_wrapper.read_text(encoding="utf-8")
            stack_text = stack_wrapper.read_text(encoding="utf-8")
            self.assertIn("wechat stack \"$ACTION\"", reboot_text)
            self.assertIn("WECHAT_CAREER_AGENT_EFFORT=${WECHAT_CAREER_AGENT_EFFORT:-medium}", reboot_text)
            self.assertIn("WECHAT_MARKDOWN_PDF_PANDOC=${WECHAT_MARKDOWN_PDF_PANDOC:-$HOME/miniconda3/bin/pandoc}", reboot_text)
            self.assertIn("WECHAT_MARKDOWN_PDF_LANGUAGES=${WECHAT_MARKDOWN_PDF_LANGUAGES:-zh,en}", stack_text)
            self.assertIn("wechat career-agent status", reboot_text)
            self.assertIn("--career-session \"$WECHAT_CAREER_SESSION\"", stack_text)


if __name__ == "__main__":
    unittest.main()
