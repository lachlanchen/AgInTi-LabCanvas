from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def schedule_state_reader(
    *,
    echo_last_loop_at: str,
    career_last_loop_at: str = "2026-07-22T11:59:30+00:00",
    career_overdue: bool = False,
    organizer_overdue: bool = False,
    career_next_attempt_at: str = "",
    organizer_next_attempt_at: str = "",
    echomind_pending_daily_pdf: bool = False,
    echomind_pending_daily_pdf_generated_at: str = "",
    echomind_last_daily_pdf_attempt_at: str = "",
    echomind_pending_lesson: bool = False,
    echomind_pending_lesson_generated_at: str = "",
    echomind_phase: str = "waiting",
    echomind_pending_lesson_next_attempt_at: str = "",
    career_phase: str = "complete",
):
    def read(path: Path):
        if path == guard.ECHOMIND_SCHEDULE_STATE:
            state = {
                "interval_seconds": guard.ECHOMIND_INTERVAL_SECONDS,
                "last_loop_at": echo_last_loop_at,
                "scheduler_phase": echomind_phase,
            }
            if echomind_pending_daily_pdf:
                state["pending_daily_pdf"] = {
                    "date": "2026-07-21",
                    "pdf": "/private/review.pdf",
                }
                if echomind_pending_daily_pdf_generated_at:
                    state["pending_daily_pdf"]["generated_at"] = (
                        echomind_pending_daily_pdf_generated_at
                    )
                if echomind_last_daily_pdf_attempt_at:
                    state["last_daily_pdf_attempt_date"] = "2026-07-21"
                    state["last_daily_pdf_attempt_at"] = (
                        echomind_last_daily_pdf_attempt_at
                    )
            if echomind_pending_lesson:
                state["pending_lesson"] = {"message": "private lesson"}
                if echomind_pending_lesson_generated_at:
                    state["pending_lesson"]["generated_at"] = (
                        echomind_pending_lesson_generated_at
                    )
                if echomind_pending_lesson_next_attempt_at:
                    state["pending_lesson"]["next_attempt_at"] = (
                        echomind_pending_lesson_next_attempt_at
                    )
            return state
        if path == guard.WECHAT_CAREER_SCHEDULE_STATE:
            return {
                "last_loop_at": career_last_loop_at,
                "phase": career_phase,
                "date": "2026-07-22",
                "morning_time": "08:30",
                "career_complete": not career_overdue,
                "career_overdue": career_overdue,
                "organizer_required": True,
                "organizer_complete": not organizer_overdue,
                "organizer_overdue": organizer_overdue,
                "career_next_attempt_at": career_next_attempt_at,
                "organizer_next_attempt_at": organizer_next_attempt_at,
            }
        return json.loads(path.read_text(encoding="utf-8"))

    return read


class WeChatTransportStallGuardTests(unittest.TestCase):
    def test_health_alert_can_target_private_personal_wechat_device_inbox(self) -> None:
        completed = subprocess.CompletedProcess(
            ["wechat_gui_send.py"],
            0,
            json.dumps({"results": [{"target": "🍓My devices", "sent": True}]}),
            "",
        )
        with mock.patch.object(guard, "run_command", return_value=completed) as runner:
            result = guard.send_health_alert(
                transport="wechat",
                chat="🍓My devices",
                message="health degraded",
                task_id="health-1",
            )

        self.assertTrue(result["ok"])
        command = runner.call_args.args[0]
        self.assertIn(str(guard.WECHAT_GUI_SEND), command)
        self.assertEqual(command[command.index("--target") + 1], "🍓My devices")
        self.assertIn("--no-search", command)
        self.assertNotIn("LabAgent", command)

    def test_virtual_desktop_closes_lifecycle_lock_in_wechat_child(self) -> None:
        script = (
            ROOT
            / "agentic_tools"
            / "wechat_gui_agent"
            / "scripts"
            / "wechat_virtual_desktop.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("setsid -f /usr/bin/wechat 9>&-", script)

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

    def test_queue_health_flags_recent_terminal_worker_failure(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "id": "failed-recent",
                        "status": "worker_failed",
                        "completed_at": "2026-07-22T11:30:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = guard.queue_health(queue, now=now)

        self.assertFalse(result["ok"])
        self.assertEqual(result["recent_failed_ids"], ["failed-recent"])

    def test_queue_health_exposes_numbered_messages_unresolved_after_retry(self) -> None:
        now = datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "id": "message-42",
                        "status": "done",
                        "coverage_status": "unresolved_after_retry",
                        "completed_at": "2026-07-30T07:30:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = guard.queue_health(queue, now=now)

        self.assertFalse(result["ok"])
        self.assertEqual(result["coverage_unresolved_ids"], ["message-42"])

    def test_queue_health_keeps_old_unresolved_coverage_as_audit_only(self) -> None:
        now = datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "id": "historical-message",
                        "status": "worker_failed",
                        "coverage_status": "unresolved_after_retry",
                        "completed_at": "2026-07-29T23:00:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = guard.queue_health(queue, now=now)

        self.assertTrue(result["ok"])
        self.assertEqual(result["coverage_unresolved_ids"], [])
        self.assertEqual(result["historical_coverage_unresolved_count"], 1)
        self.assertEqual(
            result["historical_coverage_unresolved_ids"],
            ["historical-message"],
        )
        self.assertEqual(
            result["historical_coverage_categories"],
            {"worker_failed": 1},
        )

    def test_queue_health_classifies_historical_coverage_without_replaying_it(self) -> None:
        now = datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            rows = [
                {
                    "id": "delivered",
                    "status": "done",
                    "coverage_status": "unresolved_after_retry",
                    "completed_at": "2026-07-29T20:00:00+00:00",
                    "wecom_delivery": {"status": "sent"},
                },
                {
                    "id": "expired",
                    "status": "send_expired",
                    "coverage_status": "unresolved_after_retry",
                    "completed_at": "2026-07-29T20:00:00+00:00",
                },
                {
                    "id": "failed",
                    "status": "worker_failed",
                    "coverage_status": "unresolved_after_retry",
                    "completed_at": "2026-07-29T20:00:00+00:00",
                },
            ]
            queue.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            result = guard.queue_health(queue, now=now)

        self.assertTrue(result["ok"])
        self.assertEqual(result["active"], 0)
        self.assertEqual(result["coverage_unresolved_ids"], [])
        self.assertEqual(
            result["historical_coverage_categories"],
            {
                "delivered_unverified": 1,
                "delivery_expired": 1,
                "worker_failed": 1,
            },
        )

    def test_gui_timeout_health_ignores_failure_before_client_restart(self) -> None:
        now = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "id": "old-timeout",
                        "status": "send_deferred_locked",
                        "last_send_attempt_at": "2026-07-28T15:55:00+00:00",
                        "send_deferred_reason": "gui_send_timeout",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = guard.recent_wechat_gui_timeout_health(
                queue,
                now=now,
                client_started_at=now - timedelta(minutes=2),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["task_ids"], [])

    def test_gui_timeout_health_flags_failure_against_current_client(self) -> None:
        now = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "id": "current-timeout",
                        "status": "send_deferred_locked",
                        "last_send_attempt_at": "2026-07-28T15:59:30+00:00",
                        "file_send_errors": [
                            {"error": "WECHAT_SEND_TIMEOUT: GUI sender exceeded 115 seconds"}
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = guard.recent_wechat_gui_timeout_health(
                queue,
                now=now,
                client_started_at=now - timedelta(minutes=5),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["task_ids"], ["current-timeout"])

    def test_gui_timeout_health_includes_daily_scheduler_delivery(self) -> None:
        now = datetime(2026, 7, 29, 3, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "queue.jsonl"
            queue.write_text("", encoding="utf-8")
            scheduler = root / "organizer-delivery.json"
            scheduler.write_text(
                json.dumps(
                    {
                        "status": "delivery_failed",
                        "updated_at": "2026-07-29T10:59:00+08:00",
                        "send": {
                            "errors": [
                                "WECHAT_SEND_TIMEOUT: GUI sender exceeded 115 seconds"
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = guard.recent_wechat_gui_timeout_health(
                queue,
                now=now,
                client_started_at=now - timedelta(hours=1),
                scheduler_state_paths=(scheduler,),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["task_ids"], ["scheduler:organizer-delivery"])

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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:30:00+00:00",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertFalse(result["echomind"]["ok"])
        self.assertFalse(result["ok"])

    def test_schedule_health_detects_pending_echomind_daily_pdf(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        echomind_pending_daily_pdf=True,
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertFalse(result["echomind"]["ok"])
        self.assertTrue(result["echomind"]["pending_daily_pdf"])
        self.assertTrue(result["echomind"]["pending_delivery"])
        self.assertFalse(result["ok"])

    def test_schedule_health_graces_fresh_pending_echomind_daily_pdf(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        echomind_pending_daily_pdf=True,
                        echomind_pending_daily_pdf_generated_at=(
                            "2026-07-22T11:58:00+00:00"
                        ),
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["echomind"]["ok"])
        self.assertTrue(result["echomind"]["pending_daily_pdf"])
        self.assertFalse(result["echomind"]["pending_daily_pdf_actionable"])
        self.assertEqual(result["echomind"]["pending_daily_pdf_age_seconds"], 120)
        self.assertTrue(result["ok"])

    def test_schedule_health_graces_pending_daily_pdf_until_scheduler_retry(self) -> None:
        now = datetime(2026, 7, 22, 12, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "daily.health.json"
            heartbeat.write_text(
                json.dumps({"checked_at": "2026-07-22T12:19:30+00:00", "status": "ok"}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(guard, "tmux_session_live", return_value=True),
                mock.patch.object(
                    guard,
                    "read_json",
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T12:19:30+00:00",
                        echomind_pending_daily_pdf=True,
                        echomind_pending_daily_pdf_generated_at=(
                            "2026-07-22T12:05:00+00:00"
                        ),
                        echomind_last_daily_pdf_attempt_at=(
                            "2026-07-22T12:00:00+00:00"
                        ),
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["echomind"]["ok"])
        self.assertTrue(result["echomind"]["pending_daily_pdf_retry_pending"])
        self.assertFalse(result["echomind"]["pending_daily_pdf_actionable"])
        self.assertEqual(
            result["echomind"]["pending_daily_pdf_next_attempt_at"],
            "2026-07-22T12:30:00+00:00",
        )
        self.assertTrue(result["ok"])

    def test_schedule_health_graces_fresh_pending_echomind_lesson(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        echomind_pending_lesson=True,
                        echomind_pending_lesson_generated_at=(
                            "2026-07-22T11:58:00+00:00"
                        ),
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["echomind"]["ok"])
        self.assertTrue(result["echomind"]["pending_lesson"])
        self.assertFalse(result["echomind"]["pending_lesson_actionable"])
        self.assertEqual(result["echomind"]["pending_lesson_age_seconds"], 120)
        self.assertTrue(result["ok"])

    def test_schedule_health_waits_for_fresh_lesson_delivery_attempt(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:58:30+00:00",
                        echomind_pending_lesson=True,
                        echomind_pending_lesson_generated_at=(
                            "2026-07-22T11:00:00+00:00"
                        ),
                        echomind_phase="lesson_delivery_attempt",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["echomind"]["ok"])
        self.assertTrue(result["echomind"]["pending_lesson_in_progress"])
        self.assertFalse(result["echomind"]["pending_lesson_actionable"])

    def test_schedule_health_flags_stale_lesson_delivery_attempt(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:00:00+00:00",
                        echomind_pending_lesson=True,
                        echomind_pending_lesson_generated_at=(
                            "2026-07-22T11:00:00+00:00"
                        ),
                        echomind_phase="lesson_delivery_attempt",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertFalse(result["echomind"]["ok"])
        self.assertFalse(result["echomind"]["pending_lesson_in_progress"])
        self.assertTrue(result["echomind"]["pending_lesson_actionable"])

    def test_schedule_health_defers_pending_lesson_during_quiet_hours(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        echomind_pending_lesson=True,
                        echomind_pending_lesson_generated_at=(
                            "2026-07-22T06:00:00+00:00"
                        ),
                        echomind_phase="quiet_hours",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["echomind"]["ok"])
        self.assertTrue(
            result["echomind"]["pending_lesson_quiet_hours_deferred"]
        )
        self.assertFalse(result["echomind"]["pending_lesson_actionable"])
        self.assertTrue(result["ok"])

    def test_schedule_health_waits_for_persisted_lesson_retry(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        echomind_pending_lesson=True,
                        echomind_pending_lesson_generated_at=(
                            "2026-07-22T06:00:00+00:00"
                        ),
                        echomind_pending_lesson_next_attempt_at=(
                            "2026-07-22T12:30:00+00:00"
                        ),
                        echomind_phase="lesson_retry_wait",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["echomind"]["ok"])
        self.assertTrue(result["echomind"]["pending_lesson_retry_pending"])
        self.assertFalse(result["echomind"]["pending_lesson_actionable"])

    def test_schedule_health_detects_overdue_career_and_memo_delivery(self) -> None:
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
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        career_overdue=True,
                        organizer_overdue=True,
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertFalse(result["career_daily"]["ok"])
        self.assertTrue(result["career_daily"]["career_overdue"])
        self.assertTrue(result["career_daily"]["organizer_overdue"])
        self.assertFalse(result["ok"])

    def test_schedule_health_waits_for_persisted_delivery_retry(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "daily.health.json"
            heartbeat.write_text(
                json.dumps(
                    {"checked_at": "2026-07-22T11:59:30+00:00", "status": "ok"}
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(guard, "tmux_session_live", return_value=True),
                mock.patch.object(
                    guard,
                    "read_json",
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        career_overdue=True,
                        organizer_overdue=True,
                        career_next_attempt_at="2026-07-22T12:15:00+00:00",
                        organizer_next_attempt_at="2026-07-22T12:30:00+00:00",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["career_daily"]["ok"])
        self.assertFalse(result["career_daily"]["career_overdue"])
        self.assertFalse(result["career_daily"]["organizer_overdue"])
        self.assertTrue(result["career_daily"]["career_retry_pending"])
        self.assertTrue(result["career_daily"]["organizer_retry_pending"])
        self.assertTrue(result["ok"])

    def test_schedule_health_waits_for_fresh_in_progress_career_delivery(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "daily.health.json"
            heartbeat.write_text(
                json.dumps(
                    {"checked_at": "2026-07-22T11:59:30+00:00", "status": "ok"}
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(guard, "tmux_session_live", return_value=True),
                mock.patch.object(
                    guard,
                    "read_json",
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        career_last_loop_at="2026-07-22T11:58:30+00:00",
                        career_overdue=True,
                        career_phase="career_running",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertTrue(result["career_daily"]["ok"])
        self.assertTrue(result["career_daily"]["career_in_progress"])
        self.assertFalse(result["career_daily"]["career_overdue"])

    def test_schedule_health_flags_stale_in_progress_career_delivery(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "daily.health.json"
            heartbeat.write_text(
                json.dumps(
                    {"checked_at": "2026-07-22T11:59:30+00:00", "status": "ok"}
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(guard, "tmux_session_live", return_value=True),
                mock.patch.object(
                    guard,
                    "read_json",
                    side_effect=schedule_state_reader(
                        echo_last_loop_at="2026-07-22T11:59:30+00:00",
                        career_last_loop_at="2026-07-22T11:00:00+00:00",
                        career_overdue=True,
                        career_phase="career_running",
                    ),
                ),
            ):
                result = guard.schedule_health(
                    labagent_heartbeat=heartbeat,
                    now=now,
                )

        self.assertFalse(result["career_daily"]["ok"])
        self.assertFalse(result["career_daily"]["career_in_progress"])
        self.assertTrue(result["career_daily"]["career_overdue"])

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

    def test_live_android_relay_is_not_restarted_for_native_foreground_failure(self) -> None:
        snapshot = {
            "issues": [
                {
                    "code": "android_poll_stalled",
                    "severity": "degraded",
                    "detail": "surface=unavailable, failures=3",
                }
            ],
            "android": {
                "endpoint_reachable": True,
                "poll_stale": False,
                "poll_in_progress": False,
                "last_poll_error": "BridgeError: WeCom did not reach the foreground",
            },
        }
        state = {"fault_counts": {"android_poll_stalled": 2}}
        with mock.patch.object(guard, "run_repair") as repair:
            result = guard.perform_repairs(
                snapshot,
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                max_sender_seconds=180,
            )

        self.assertEqual(result, [])
        repair.assert_not_called()

    def test_live_android_relay_is_not_restarted_for_locked_keyguard(self) -> None:
        snapshot = {
            "issues": [
                {
                    "code": "android_poll_stalled",
                    "severity": "degraded",
                    "detail": "surface=other_app, failures=5",
                }
            ],
            "android": {
                "endpoint_reachable": True,
                "poll_stale": False,
                "poll_in_progress": False,
                "last_poll_error": "BridgeError: Android keyguard is locked",
            },
        }
        state = {"fault_counts": {"android_poll_stalled": 2}}
        with mock.patch.object(guard, "run_repair") as repair:
            result = guard.perform_repairs(
                snapshot,
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                max_sender_seconds=180,
            )

        self.assertEqual(result, [])
        repair.assert_not_called()

    def test_overdue_daily_delivery_restarts_only_career_scheduler(self) -> None:
        snapshot = {
            "issues": [
                {
                    "code": "schedule_memo_delivery_overdue",
                    "severity": "degraded",
                    "detail": "daily organizer PDF is overdue",
                }
            ]
        }
        state = {"fault_counts": {"schedule_memo_delivery_overdue": 2}}
        with mock.patch.object(
            guard,
            "run_repair",
            return_value={"label": "career_schedule", "ok": True},
        ) as repair:
            result = guard.perform_repairs(
                snapshot,
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                max_sender_seconds=180,
            )

        self.assertEqual(result, [{"label": "career_schedule", "ok": True}])
        repair.assert_called_once_with(
            "career_schedule",
            [str(guard.WECHAT_STACK), "restart-career"],
        )

    def test_android_serialized_gui_busy_is_not_a_stall_until_poll_is_stale(self) -> None:
        busy = {
            "poll_healthy": False,
            "poll_in_progress": True,
            "poll_stale": False,
            "surface_state": "polling",
            "last_poll_error": "BridgeError: WECOM_ANDROID_BUSY: serialized GUI control exceeded 5.0s",
        }

        self.assertFalse(guard.android_poll_failure_is_actionable(busy))
        self.assertTrue(
            guard.android_poll_failure_is_actionable(
                {**busy, "poll_stale": True}
            )
        )
        self.assertTrue(
            guard.android_poll_failure_is_actionable(
                {**busy, "surface_state": "anr"}
            )
        )

    def test_current_client_gui_timeout_restarts_only_wechat_client(self) -> None:
        snapshot = {
            "issues": [
                {
                    "code": "wechat_gui_delivery_stalled",
                    "severity": "degraded",
                    "detail": "one current-client timeout",
                }
            ]
        }
        state = {"fault_counts": {"wechat_gui_delivery_stalled": 2}}
        with mock.patch.object(
            guard,
            "run_repair",
            return_value={"label": "wechat_input_stalled", "ok": True},
        ) as repair:
            result = guard.perform_repairs(
                snapshot,
                state,
                consecutive_failures=2,
                cooldown_seconds=300,
                max_sender_seconds=180,
            )

        self.assertEqual(result, [{"label": "wechat_input_stalled", "ok": True}])
        repair.assert_called_once_with(
            "wechat_input_stalled",
            [str(guard.WECHAT_VIRTUAL_DESKTOP), "restart-client"],
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
        self.assertIn("health_guard_reload_needed", wecom)
        self.assertIn("sha256sum \"$HEALTH_GUARD\"", wecom)
        self.assertIn("android_bridge_reload_needed", wecom)
        self.assertIn("sha256sum \"$ANDROID_BRIDGE\"", wecom)
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
