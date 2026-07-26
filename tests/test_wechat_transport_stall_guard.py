from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / "scripts"
    / "wechat_transport_stall_guard.py"
)
SPEC = importlib.util.spec_from_file_location("wechat_transport_stall_guard", SCRIPT)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class WeChatTransportStallGuardTests(unittest.TestCase):
    def test_old_unlocked_sender_file_is_not_treated_as_stall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "sender.lock"
            lock.touch()
            result = guard.sender_lock_health(lock, max_holder_seconds=1)

        self.assertTrue(result["ok"])
        self.assertFalse(result["held"])
        self.assertEqual(result["state"], "free")

    def test_queue_health_flags_only_current_stale_active_tasks(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            rows = [
                {
                    "id": "old-active",
                    "status": "in_progress",
                    "claimed_at": "2026-07-22T06:00:00+00:00",
                },
                {
                    "id": "recent-pending",
                    "status": "pending",
                    "created_at": "2026-07-22T11:59:30+00:00",
                },
                {
                    "id": "terminal",
                    "status": "done",
                    "created_at": "2026-07-01T00:00:00+00:00",
                },
            ]
            queue.write_text(
                "\n".join(json.dumps(item) for item in rows) + "\n",
                encoding="utf-8",
            )
            result = guard.queue_health(
                queue,
                now=now,
                stale_active_seconds=3600,
                stale_pending_seconds=3600,
            )

        self.assertEqual(result["active"], 2)
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["stale_ids"], ["old-active"])

    def test_tmux_snapshot_filters_exact_session_and_keeps_all_windows(self) -> None:
        original = guard.run_command
        try:
            guard.run_command = lambda *_args, **_kwargs: subprocess.CompletedProcess(  # type: ignore[assignment]
                [],
                0,
                "wanted\tworker\t0\t101\tpython3\n"
                "other\tworker\t0\t102\tpython3\n"
                "wanted\tdirect-name.with-dot-\t0\t103\tbash\n",
                "",
            )
            result = guard.tmux_snapshot("wanted")
        finally:
            guard.run_command = original  # type: ignore[assignment]

        self.assertTrue(result["running"])
        self.assertEqual(set(result["windows"]), {"worker", "direct-name.with-dot-"})

    def test_officially_unsupported_wecom_cli_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            state = Path(tmp) / "state.json"
            config.write_text('{"enabled": true}\n', encoding="utf-8")
            state.write_text(
                json.dumps(
                    {
                        "state": "message_permission_unavailable",
                        "msg_permission": False,
                        "last_error": "当前企业暂不支持授权机器人消息使用权限",
                    }
                ),
                encoding="utf-8",
            )

            result = guard.cli_transport_health(config, state)

        self.assertTrue(result["enabled"])
        self.assertFalse(result["required"])
        self.assertFalse(result["official_message_permission"])

    def test_direct_monitor_health_uses_loop_heartbeat_not_message_age(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp)
            healthy_state = private / "healthy.state.json"
            stale_state = private / "stale.state.json"
            healthy_state.write_text('{"last_loop_at":"2026-07-22T11:59:50+00:00"}', encoding="utf-8")
            stale_state.write_text('{"last_loop_at":"2026-07-22T11:00:00+00:00"}', encoding="utf-8")
            (private / "healthy-direct-chatops.local.json").write_text(
                json.dumps({"state_path": str(healthy_state), "poll_seconds": 0.8}),
                encoding="utf-8",
            )
            (private / "stale-direct-chatops.local.json").write_text(
                json.dumps({"state_path": str(stale_state), "poll_seconds": 0.8}),
                encoding="utf-8",
            )

            result = guard.direct_monitor_health(private_dir=private, now=now)

        self.assertFalse(result["ok"])
        self.assertEqual(result["configured"], 2)
        self.assertEqual(result["healthy"], 1)
        self.assertEqual(result["stale_configs"], ["stale-direct-chatops.local.json"])

    def test_direct_monitor_health_does_not_kill_bounded_inflight_agent_turn(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp)
            state = private / "processing.state.json"
            state.write_text(
                json.dumps(
                    {
                        "last_loop_at": "2026-07-22T11:55:00+00:00",
                        "inflight_local_ids": [710],
                        "inflight_started_at": "2026-07-22T11:59:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            (private / "processing-direct-chatops.local.json").write_text(
                json.dumps({"state_path": str(state), "poll_seconds": 0.8}),
                encoding="utf-8",
            )

            result = guard.direct_monitor_health(
                private_dir=private,
                now=now,
                processing_stale_seconds=600,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["monitors"][0]["state"], "processing")
        self.assertEqual(result["monitors"][0]["inflight_count"], 1)

    def test_schedule_health_detects_stale_labagent_heartbeat(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "daily.health.json"
            heartbeat.write_text(
                json.dumps({"checked_at": "2026-07-22T11:59:30+00:00", "status": "ok"}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(guard, "tmux_session_live", return_value=True),
                mock.patch.object(
                    guard,
                    "read_json",
                    side_effect=lambda path: (
                        {
                            "interval_seconds": guard.ECHOMIND_INTERVAL_SECONDS,
                            "last_loop_at": "2026-07-22T11:59:30+00:00",
                        }
                        if path == guard.ECHOMIND_SCHEDULE_STATE
                        else json.loads(path.read_text(encoding="utf-8"))
                    ),
                ),
            ):
                healthy = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                    labagent_stale_seconds=60,
                )
                stale = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=datetime(2026, 7, 22, 12, 2, tzinfo=timezone.utc),
                    labagent_stale_seconds=60,
                )

        self.assertTrue(healthy["labagent_idle_inspiration"]["ok"])
        self.assertFalse(stale["labagent_idle_inspiration"]["ok"])
        self.assertFalse(stale["ok"])

    def test_schedule_health_detects_live_tmux_with_stale_echomind_heartbeat(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "daily.health.json"
            heartbeat.write_text(
                json.dumps({"checked_at": "2026-07-22T11:59:30+00:00", "status": "ok"}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(guard, "tmux_session_live", return_value=True),
                mock.patch.object(
                    guard,
                    "read_json",
                    side_effect=lambda path: (
                        {
                            "interval_seconds": guard.ECHOMIND_INTERVAL_SECONDS,
                            "last_loop_at": "2026-07-22T11:30:00+00:00",
                            "scheduler_phase": "waiting",
                        }
                        if path == guard.ECHOMIND_SCHEDULE_STATE
                        else json.loads(path.read_text(encoding="utf-8"))
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertFalse(result["echomind"]["ok"])
        self.assertFalse(result["ok"])

    def test_quota_alert_requires_terminal_exhaustion_not_successful_fallback(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            rows = [
                {
                    "id": "fallback-succeeded",
                    "status": "done",
                    "completed_at": "2026-07-22T11:59:30+00:00",
                    "worker_result_exhausted": False,
                    "agent_session": {
                        "backend_attempts": [
                            {"backend": "codex", "failure_kind": "quota"},
                            {"backend": "aginti", "ok": True},
                        ]
                    },
                },
                {
                    "id": "all-fallbacks-exhausted",
                    "status": "worker_failed",
                    "completed_at": "2026-07-22T11:59:40+00:00",
                    "worker_result_exhausted": True,
                    "worker_policy_attempts": [{"result_excerpt": "out of quota"}],
                },
            ]
            queue.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            result = guard.recent_terminal_agent_failures((queue,), now=now)

        self.assertFalse(result["ok"])
        self.assertEqual(result["quota_failure_ids"], ["all-fallbacks-exhausted"])

    def test_serious_alert_is_state_transition_deduplicated(self) -> None:
        snapshot = {
            "issues": [
                {
                    "code": "wechat_direct_monitor_stalled",
                    "severity": "critical",
                    "detail": "one stale monitor",
                }
            ]
        }
        state = {"fault_counts": {"wechat_direct_monitor_stalled": 3}}
        with mock.patch.object(guard, "send_health_alert", return_value={"ok": True}) as sender:
            first = guard.maybe_alert(
                snapshot,
                state,
                transport="wecom-android",
                chat="LabAgent",
                consecutive_failures=3,
                cooldown_seconds=0,
            )
            second = guard.maybe_alert(
                snapshot,
                state,
                transport="wecom-android",
                chat="LabAgent",
                consecutive_failures=3,
                cooldown_seconds=0,
            )

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "deduplicated")
        sender.assert_called_once()

    def test_repair_requires_repeated_fault_and_respects_cooldown(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        state = {"fault_counts": {"android_endpoint_down": 1}}
        self.assertFalse(
            guard.repair_due(
                "android_endpoint_down",
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                now=now,
            )
        )
        state["fault_counts"]["android_endpoint_down"] = 2
        self.assertTrue(
            guard.repair_due(
                "android_endpoint_down",
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                now=now,
            )
        )
        state["last_repair_at"] = {"android_endpoint_down": "2026-07-22T11:59:00+00:00"}
        self.assertFalse(
            guard.repair_due(
                "android_endpoint_down",
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                now=now,
            )
        )

    def test_android_poll_stall_uses_android_relay_repair(self) -> None:
        snapshot = {
            "issues": [
                {
                    "code": "android_poll_stalled",
                    "severity": "degraded",
                    "detail": "surface=anr, failures=2",
                }
            ]
        }
        state = {"fault_counts": {"android_poll_stalled": 2}}
        with mock.patch.object(
            guard,
            "run_repair",
            return_value={"label": "android_relay", "ok": True},
        ) as repair:
            result = guard.perform_repairs(
                snapshot,
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                max_sender_seconds=180,
            )

        self.assertEqual(result, [{"label": "android_relay", "ok": True}])
        repair.assert_called_once_with(
            "android_relay",
            [str(guard.WECOM_SUPERVISOR), "android-restart"],
        )

    def test_repair_agent_never_runs_for_healthy_poll(self) -> None:
        due, signature, codes = guard.repair_agent_due(
            {"ok": True, "issues": []},
            {"fault_counts": {}},
            consecutive_failures=4,
            cooldown_seconds=3600,
            now=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        )

        self.assertFalse(due)
        self.assertEqual(signature, "")
        self.assertEqual(codes, [])

    def test_repair_agent_requires_repeated_unresolved_incident_and_cooldown(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        snapshot = {
            "ok": False,
            "issues": [
                {
                    "code": "wechat_direct_monitor_stalled",
                    "severity": "critical",
                    "detail": "stale",
                }
            ],
        }
        state = {"fault_counts": {"wechat_direct_monitor_stalled": 4}}
        due, signature, codes = guard.repair_agent_due(
            snapshot,
            state,
            consecutive_failures=4,
            cooldown_seconds=3600,
            now=now,
        )
        self.assertTrue(due)
        self.assertEqual(codes, ["wechat_direct_monitor_stalled"])

        state.update(
            {
                "last_repair_agent_signature": signature,
                "last_repair_agent_attempt_at": "2026-07-22T11:59:30+00:00",
            }
        )
        due_again, _, _ = guard.repair_agent_due(
            snapshot,
            state,
            consecutive_failures=4,
            cooldown_seconds=3600,
            now=now,
        )
        self.assertFalse(due_again)

    def test_repair_agent_escalates_only_on_explicit_marker(self) -> None:
        with mock.patch.object(
            guard,
            "run_repair_agent",
            side_effect=[
                {"ok": True, "escalation_requested": True, "reasoning_effort": "medium"},
                {"ok": True, "escalation_requested": False, "reasoning_effort": "high"},
            ],
        ) as runner:
            result = guard.run_repair_agent_with_escalation(
                {"issues": []},
                [],
                timeout_seconds=60,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(
            [call.kwargs["reasoning_effort"] for call in runner.call_args_list],
            ["medium", "high"],
        )

    def test_android_health_probe_preserves_poll_failure_evidence(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "ok": False,
                "transport": "wecom_android",
                "device_authorized": True,
                "wecom_foreground": True,
                "surface_state": "anr",
                "poll_healthy": False,
                "consecutive_poll_failures": 7,
                "last_poll_error": "BridgeError: WeCom chat list is not visible",
            }
        ).encode()
        with mock.patch.object(guard.request, "urlopen", return_value=response):
            result = guard.probe_json_url("http://127.0.0.1:19581/health")

        self.assertTrue(result["endpoint_reachable"])
        self.assertFalse(result["poll_healthy"])
        self.assertEqual(result["surface_state"], "anr")
        self.assertEqual(result["consecutive_poll_failures"], 7)
        self.assertIn("chat list", result["last_poll_error"])

    def test_supervisors_use_idempotent_missing_window_repair(self) -> None:
        wechat = (
            ROOT
            / "agentic_tools"
            / "wechat_gui_agent"
            / "scripts"
            / "wechat_supervisor_tmux.sh"
        ).read_text(encoding="utf-8")
        wecom = (
            ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_tmux.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("start|ensure|stop", wechat)
        self.assertIn("ensure_runtime_windows", wechat)
        self.assertIn("window_id_by_name", wechat)
        self.assertIn("Started missing window", wechat)
        self.assertIn("reload-monitors", wechat)
        self.assertIn("reload_monitor_windows", wechat)
        self.assertIn("reload-unlock", wechat)
        self.assertIn("reload_unlock_watchdog", wechat)
        self.assertIn("wechat_transport_stall_guard.py", wecom)
        self.assertIn("--loop --repair", wecom)
        self.assertIn("--repair-agent", wecom)
        self.assertIn("window_exists health", wecom)
        self.assertIn("health-restart", wecom)
        self.assertIn("start_health_window", wecom)
        self.assertIn("kill_window_if_present", wecom)
        self.assertIn("external_required", wecom)
        self.assertIn("message_permission_unavailable", wecom)
        self.assertNotIn('tmux kill-window -t "$SESSION:external"', wecom)

        stack = (
            ROOT
            / "agentic_tools"
            / "wechat_gui_agent"
            / "scripts"
            / "wechat_stack_tmux.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("echomind_language_scheduler_tmux.sh", stack)
        self.assertIn("start_echomind", stack)


if __name__ == "__main__":
    unittest.main()
