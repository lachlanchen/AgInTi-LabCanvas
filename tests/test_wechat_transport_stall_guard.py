from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


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
        self.assertIn("wechat_transport_stall_guard.py", wecom)
        self.assertIn("--loop --repair", wecom)
        self.assertIn("window_exists health", wecom)
        self.assertIn("kill_window_if_present", wecom)
        self.assertNotIn('tmux kill-window -t "$SESSION:external"', wecom)


if __name__ == "__main__":
    unittest.main()
