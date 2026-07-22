from __future__ import annotations

from datetime import datetime, timezone
import unittest

from agentic_tools.wechat_gui_agent.scripts import echomind_language_scheduler as scheduler


class EchoMindLanguageSchedulerTests(unittest.TestCase):
    def test_default_interval_is_three_hours(self) -> None:
        self.assertEqual(scheduler.INTERVAL, 10_800)

    def test_restart_waits_for_remaining_interval(self) -> None:
        state = {"last_run_at": "2026-07-22T07:02:37+00:00"}
        now = datetime(2026, 7, 22, 7, 32, 37, tzinfo=timezone.utc)

        remaining = scheduler.seconds_until_due(state, scheduler.INTERVAL, now=now)

        self.assertEqual(remaining, 9_000)

    def test_due_when_three_hours_have_elapsed(self) -> None:
        state = {"last_run_at": "2026-07-22T07:02:37+00:00"}
        now = datetime(2026, 7, 22, 10, 2, 37, tzinfo=timezone.utc)

        remaining = scheduler.seconds_until_due(state, scheduler.INTERVAL, now=now)

        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
