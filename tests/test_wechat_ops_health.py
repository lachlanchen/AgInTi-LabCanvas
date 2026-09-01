from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from agenticapp import wechat_ops


class WeChatOpsHealthTests(unittest.TestCase):
    def compact_health_fixture(self) -> dict:
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "transport_health": {
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "issues": [{"code": "wechat_login_required"}],
                "wechat_client": {"available": False, "status": "entry_required"},
                "direct_monitors": {"configured": 6, "heartbeat_healthy": 6},
                "agent_failures": {"terminal_failures": 0},
                "queues": {
                    "wechat": {
                        "ok": True,
                        "active": 0,
                        "pending": 0,
                        "recent_failed_ids": [],
                        "stale_ids": [],
                    },
                    "wecom": {
                        "ok": True,
                        "active": 0,
                        "pending": 0,
                        "recent_failed_ids": [],
                        "stale_ids": [],
                    },
                },
                "schedules": {
                    "ok": True,
                    "career_daily": {
                        "running": True,
                        "career_status": "delivered",
                        "career_complete": True,
                        "organizer_required": True,
                        "organizer_status": "delivered",
                        "organizer_complete": True,
                    },
                    "echomind": {
                        "running": True,
                        "interval_seconds": 21600,
                        "daily_pdf_target_date": "2026-08-30",
                        "daily_pdf_generation_retry_active": True,
                        "pending_daily_pdf_next_attempt_at": "2026-08-31T01:41:51+00:00",
                    },
                    "labagent_idle_inspiration": {"ok": True, "status": "ok"},
                },
            },
        }

    def test_compact_health_treats_fresh_phone_fallback_as_operational(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload = wechat_ops.compact_health_payload(
            self.compact_health_fixture(),
            notification_status={
                "ok": True,
                "routes": 6,
                "listener_enabled": True,
                "listener_live": True,
                "last_poll_at": now,
            },
            self_status={
                "ok": True,
                "routes": 6,
                "seeded_routes": 6,
                "deferred_routes": 0,
                "last_poll_at": now,
                "last_error": "",
            },
        )

        self.assertTrue(payload["operational"])
        self.assertTrue(payload["degraded"])
        self.assertEqual(payload["desktop_wechat"]["status"], "entry_required")
        self.assertTrue(payload["phone_ingress"]["other_people"]["reaches_agent"])
        self.assertTrue(payload["phone_ingress"]["self_authored"]["reaches_agent"])
        self.assertEqual(payload["schedules"]["career_daily"]["status"], "delivered")
        self.assertEqual(payload["schedules"]["memo_daily"]["status"], "delivered")
        self.assertEqual(
            payload["schedules"]["echomind_daily_pdf"]["status"],
            "quality_retry_pending",
        )

    def test_configured_agent_backends_uses_shared_model_policy_by_default(self) -> None:
        with (
            mock.patch.object(wechat_ops, "discover_direct_monitor_configs", return_value=[]),
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "agenticapp.backends.load_model_policy",
                return_value={"primary_backend": "codex"},
            ),
        ):
            self.assertEqual(wechat_ops.configured_agent_backends(), ["codex"])

    def test_compact_health_rejects_stale_phone_lane(self) -> None:
        stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
        payload = wechat_ops.compact_health_payload(
            self.compact_health_fixture(),
            notification_status={
                "ok": True,
                "routes": 6,
                "listener_enabled": True,
                "listener_live": True,
                "last_poll_at": stale,
            },
            self_status={
                "ok": True,
                "routes": 6,
                "seeded_routes": 6,
                "deferred_routes": 0,
                "last_poll_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "last_error": "",
            },
        )

        self.assertFalse(payload["operational"])
        self.assertFalse(payload["phone_ingress"]["other_people"]["fresh"])

    def test_production_selftest_targets_resolve(self) -> None:
        for check in wechat_ops.selftest_checks_for_suite("all"):
            module_name, class_name, method_name = check["test"].rsplit(".", 2)
            module = importlib.import_module(module_name)
            case = getattr(module, class_name)
            self.assertTrue(
                hasattr(case, method_name),
                f"Missing production self-test target: {check['test']}",
            )

    def test_kill_tmux_reaps_captured_detached_children(self) -> None:
        completed = subprocess.CompletedProcess(["tmux"], 0, "", "")
        with (
            mock.patch.object(wechat_ops, "run_command", return_value=completed) as run,
            mock.patch.object(
                wechat_ops,
                "tmux_session_descendant_pids",
                return_value=[101, 202],
            ) as descendants,
            mock.patch.object(wechat_ops, "terminate_process_ids") as terminate,
        ):
            stopped = wechat_ops.kill_tmux("labcanvas-career-daily")

        self.assertTrue(stopped)
        descendants.assert_called_once_with("labcanvas-career-daily")
        terminate.assert_called_once_with([101, 202])
        self.assertIn(
            ["tmux", "kill-session", "-t", "labcanvas-career-daily"],
            [call.args[0] for call in run.call_args_list],
        )

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

    def test_desktop_status_uses_terminal_watchdog_observation(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "123\n", "")
        with (
            mock.patch.object(wechat_ops, "run_command", return_value=completed),
            mock.patch.object(wechat_ops, "port_listening", return_value=True),
            mock.patch.object(
                wechat_ops,
                "fresh_unlock_watchdog_state",
                return_value={
                    "desktop": {"status": "locked"},
                    "after": {"status": "unlocked"},
                    "age_seconds": 2,
                },
            ),
        ):
            payload = wechat_ops.desktop_status()

        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["client"]["available"])

    def test_watchdog_retry_window_keeps_login_requirement_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "watchdog.json"
            state_path.write_text(
                json.dumps(
                    {
                        "desktop": {"status": "entry_required"},
                        "retry_after_seconds": 300,
                    }
                ),
                encoding="utf-8",
            )
            old_mtime = datetime.now().timestamp() - 180
            os.utime(state_path, (old_mtime, old_mtime))
            payload = wechat_ops.fresh_unlock_watchdog_state(
                state_path,
                max_age_seconds=90,
            )

        self.assertEqual(payload["desktop"]["status"], "entry_required")
        self.assertEqual(payload["valid_for_seconds"], 330.0)

    def test_direct_monitor_health_reports_stale_heartbeat_not_ready(self) -> None:
        original_discover = wechat_ops.discover_direct_monitor_configs
        original_config_health = wechat_ops.direct_config_health
        original_backend = wechat_ops.external_backend_summary
        original_separation = wechat_ops.direct_config_separation_summary
        try:
            wechat_ops.discover_direct_monitor_configs = lambda: [Path("echo.local.json")]  # type: ignore[assignment]
            wechat_ops.direct_config_health = lambda _path, **_kwargs: {  # type: ignore[assignment]
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
        self.assertIn("fresh monitor heartbeat", payload["notes"][-2])

    def test_quiet_chat_with_fresh_monitor_heartbeat_remains_ready(self) -> None:
        original_latest = wechat_ops.latest_direct_db_local_id
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_path = tmp_path / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_local_id": 25,
                        "last_loop_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                ),
                encoding="utf-8",
            )
            config_path = tmp_path / "quiet.local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "chat_name": "QuietChat",
                        "message_table": "Msg_test",
                        "state_path": str(state_path),
                        "poll_seconds": 0.8,
                        "stale_warning_seconds": 60,
                        "ignore_self_messages": True,
                        "respond_to_self": False,
                        "send_target": {"expected_title": "QuietChat"},
                    }
                ),
                encoding="utf-8",
            )
            try:
                wechat_ops.latest_direct_db_local_id = lambda _table: {  # type: ignore[assignment]
                    "ok": True,
                    "status": "ok",
                    "latest_local_id": 25,
                    "latest_at": "2026-01-01T00:00:00",
                    "age_seconds": 7200,
                }
                payload = wechat_ops.direct_config_health(config_path)
            finally:
                wechat_ops.latest_direct_db_local_id = original_latest  # type: ignore[assignment]

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["ready"])
        self.assertTrue(payload["chat_quiet"])
        self.assertTrue(payload["last_message_old"])
        self.assertFalse(payload["monitor_stale"])
        self.assertFalse(payload["source_stale"])

    def test_fresh_monitor_is_not_ready_when_client_requires_login(self) -> None:
        original_latest = wechat_ops.latest_direct_db_local_id
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_path = tmp_path / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_local_id": 25,
                        "last_loop_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                ),
                encoding="utf-8",
            )
            config_path = tmp_path / "login-required.local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "chat_name": "LoginRequired",
                        "message_table": "Msg_test",
                        "state_path": str(state_path),
                        "poll_seconds": 0.8,
                        "ignore_self_messages": True,
                        "respond_to_self": False,
                        "send_target": {"expected_title": "LoginRequired"},
                    }
                ),
                encoding="utf-8",
            )
            try:
                wechat_ops.latest_direct_db_local_id = lambda _table: {  # type: ignore[assignment]
                    "ok": True,
                    "status": "ok",
                    "latest_local_id": 25,
                    "latest_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "age_seconds": 1,
                }
                payload = wechat_ops.direct_config_health(
                    config_path,
                    client={
                        "available": False,
                        "status": "entry_required",
                    },
                )
            finally:
                wechat_ops.latest_direct_db_local_id = original_latest  # type: ignore[assignment]

        self.assertTrue(payload["caught_up"])
        self.assertFalse(payload["ready"])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["client_blocked"])
        self.assertTrue(payload["source_stale"])
        self.assertEqual(payload["client_status"], "entry_required")

    def test_caught_up_chat_with_stale_monitor_heartbeat_is_not_ready(self) -> None:
        original_latest = wechat_ops.latest_direct_db_local_id
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_path = tmp_path / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_local_id": 25,
                        "last_loop_at": (
                            datetime.now(timezone.utc) - timedelta(minutes=5)
                        ).isoformat(timespec="seconds"),
                    }
                ),
                encoding="utf-8",
            )
            config_path = tmp_path / "stale.local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "chat_name": "StaleChat",
                        "message_table": "Msg_test",
                        "state_path": str(state_path),
                        "poll_seconds": 0.8,
                        "monitor_stale_seconds": 30,
                        "ignore_self_messages": True,
                        "respond_to_self": False,
                        "send_target": {"expected_title": "StaleChat"},
                    }
                ),
                encoding="utf-8",
            )
            try:
                wechat_ops.latest_direct_db_local_id = lambda _table: {  # type: ignore[assignment]
                    "ok": True,
                    "status": "ok",
                    "latest_local_id": 25,
                    "latest_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "age_seconds": 1,
                }
                payload = wechat_ops.direct_config_health(config_path)
            finally:
                wechat_ops.latest_direct_db_local_id = original_latest  # type: ignore[assignment]

        self.assertTrue(payload["caught_up"])
        self.assertFalse(payload["ready"])
        self.assertTrue(payload["monitor_stale"])
        self.assertTrue(payload["source_stale"])

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

    def test_cli_health_does_not_override_authoritative_login_requirement(self) -> None:
        with (
            mock.patch.object(
                wechat_ops,
                "direct_monitor_health",
                return_value={
                    "ok": False,
                    "ready_groups": 0,
                    "group_count": 1,
                    "stale_source_groups": 1,
                    "client": {"available": False, "status": "entry_required"},
                    "queue": {"attention": {"needs_attention": False}},
                },
            ),
            mock.patch.object(
                wechat_ops,
                "persistent_transport_health",
                return_value={
                    "ok": True,
                    "severity": "ok",
                    "direct_monitors": {"healthy": 1, "configured": 1},
                },
            ),
            redirect_stdout(io.StringIO()) as stdout,
        ):
            rc = wechat_ops.cmd_health(argparse.Namespace(json=True))

        payload = json.loads(stdout.getvalue())
        self.assertEqual(rc, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["client"]["status"], "entry_required")

    def test_cli_health_keeps_recent_queue_failure_visible(self) -> None:
        original_direct = wechat_ops.direct_monitor_health
        original_transport = wechat_ops.persistent_transport_health
        try:
            wechat_ops.direct_monitor_health = lambda: {  # type: ignore[assignment]
                "ok": True,
                "ready_groups": 1,
                "group_count": 1,
                "stale_source_groups": 0,
                "queue": {"attention": {"needs_attention": True, "counts": {"failed": 1}}},
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
        self.assertEqual(rc, 1)
        self.assertFalse(payload["ok"])

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
    def test_approve_publish_consent_resets_stale_state_and_allows_same_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            task = {
                "id": "publish-consent",
                "chat": "MEMO",
                "status": "expired_stale",
                "waiting_reason": "third_party_publish_consent",
                "expires_at": "2000-01-01T00:00:00",
                "completed_at": "2026-07-30T17:07:31",
                "claimed_at": "2026-07-30T17:06:00",
                "worker_id": "old-worker",
                "expired_at": "2026-07-30T17:07:31",
                "expired_from_status": "pending",
                "expire_reason": "pending_task_ttl_exceeded",
                "worker_result_ready_at": "2026-07-30T17:07:30",
                "agent_session": {"backend": "aginti"},
                "codex_session": {"role": "worker"},
                "existing_video_publish_poststage": {"stage": "no_local_job"},
                "request": "Publish the exact current video.",
                "route_decision": {
                    "route_kind": "publish_video",
                    "public_publish_intent": True,
                    "public_publish_allowed": False,
                    "external_action_allowed": False,
                    "requires_third_party_publish_confirmation": True,
                },
                "preflight": {"media_resolution": {"status": "wrong-old-path"}},
                "result": {"message": "waiting for another participant"},
            }
            queue.write_text(
                json.dumps(task, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            updated = wechat_ops.update_waiting_task(
                queue,
                "publish-consent",
                decision="approve",
                note="The requester directly authorized publication.",
            )

        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["approval_previous_status"], "expired_stale")
        self.assertEqual(
            updated["approval_from_waiting_reason"],
            "third_party_publish_consent",
        )
        self.assertNotIn("waiting_reason", updated)
        self.assertNotIn("completed_at", updated)
        self.assertNotIn("claimed_at", updated)
        self.assertNotIn("worker_id", updated)
        self.assertNotIn("preflight", updated)
        self.assertNotIn("result", updated)
        self.assertNotIn("expired_at", updated)
        self.assertNotIn("expired_from_status", updated)
        self.assertNotIn("expire_reason", updated)
        self.assertNotIn("worker_result_ready_at", updated)
        self.assertNotIn("agent_session", updated)
        self.assertNotIn("codex_session", updated)
        self.assertNotIn("existing_video_publish_poststage", updated)
        self.assertGreater(
            wechat_ops.parse_queue_datetime(updated["expires_at"]),
            datetime.now(),
        )
        route = updated["route_decision"]
        self.assertTrue(route["public_publish_allowed"])
        self.assertTrue(route["external_action_allowed"])
        self.assertFalse(route["requires_third_party_publish_confirmation"])
        self.assertTrue(route["requester_publish_override"])
        self.assertEqual(route["confirmation_kind"], "direct_requester_publish")
        self.assertIn("directly authorized publication", route["reason"].lower())
        self.assertIn("no third-party confirmation", route["reason"].lower())
        self.assertNotIn("wait", route["ack"].lower())
        self.assertEqual(
            updated["third_party_publish_consent"]["status"],
            "requester_override",
        )

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
            self.assertIn("WECHAT_WEB_SESSION=${WECHAT_WEB_SESSION:-labcanvas-web}", reboot_text)
            self.assertIn("WECHAT_WEB_SESSION=${WECHAT_WEB_SESSION:-labcanvas-web}", stack_text)
            self.assertIn("WECHAT_CAREER_AGENT_EFFORT=${WECHAT_CAREER_AGENT_EFFORT:-medium}", reboot_text)
            self.assertIn("WECHAT_MARKDOWN_PDF_PANDOC=${WECHAT_MARKDOWN_PDF_PANDOC:-$HOME/miniconda3/bin/pandoc}", reboot_text)
            self.assertIn("WECHAT_MARKDOWN_PDF_LANGUAGES=${WECHAT_MARKDOWN_PDF_LANGUAGES:-zh,en}", stack_text)
            self.assertIn("wechat career-agent status", reboot_text)
            self.assertIn("--career-session \"$WECHAT_CAREER_SESSION\"", stack_text)


if __name__ == "__main__":
    unittest.main()
