from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from agentic_tools.wechat_gui_agent.scripts import echomind_language_scheduler as scheduler


class EchoMindLanguageSchedulerTests(unittest.TestCase):
    def test_default_interval_is_three_hours(self) -> None:
        self.assertEqual(scheduler.INTERVAL, 10_800)
        self.assertEqual(scheduler.PERIODIC_MODEL, "gpt-5.3-codex-spark")

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

    def test_daily_pdf_is_independent_of_quiet_hours_and_catches_up(self) -> None:
        before = datetime(2026, 7, 23, 7, 59, tzinfo=scheduler.LOCAL_TZ)
        due = datetime(2026, 7, 23, 8, 0, tzinfo=scheduler.LOCAL_TZ)
        catch_up = datetime(2026, 7, 23, 19, 30, tzinfo=scheduler.LOCAL_TZ)

        self.assertFalse(scheduler.daily_pdf_due({}, now=before))
        self.assertTrue(scheduler.daily_pdf_due({}, now=due))
        self.assertTrue(scheduler.daily_pdf_due({}, now=catch_up))

    def test_daily_pdf_force_runs_before_eight_but_never_duplicates(self) -> None:
        now = datetime(2026, 7, 23, 6, 30, tzinfo=scheduler.LOCAL_TZ)
        self.assertTrue(scheduler.daily_pdf_due({}, now=now, force=True))
        self.assertFalse(
            scheduler.daily_pdf_due(
                {"last_daily_pdf_date": "2026-07-22"},
                now=now,
                force=True,
            )
        )

    def test_daily_pdf_document_accepts_ipa_and_strips_wrappers(self) -> None:
        body = scheduler.normalize_latex_body("```latex\n\\section{Travel}\nIPA: /tɛst/\n```")
        document = scheduler.daily_pdf_document("2026-07-22", body)

        self.assertNotIn("```", document)
        self.assertIn("\\usepackage{tipa}", document)
        self.assertIn("IPA: /tɛst/", document)

    def test_pending_lesson_retries_delivery_without_regenerating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                '{"pending_lesson":{"message":"lesson","topic":"travel","next_topic_index":2,"agent":"codex","model":"gpt-5.3-codex-spark"}}',
                encoding="utf-8",
            )
            config = {"chat_name": "EchoMind"}
            screenshot = Path(tmp) / "sent.png"
            screenshot.write_bytes(b"png")
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(scheduler.direct, "load_config", return_value=config),
                mock.patch.object(scheduler.direct, "send_gui_message", return_value=str(screenshot)),
                mock.patch.object(scheduler, "run_agent_session") as agent,
            ):
                result = scheduler.run_once()
                stored = scheduler.load_state()

        self.assertTrue(result["ok"])
        agent.assert_not_called()
        self.assertNotIn("pending_lesson", stored)
        self.assertEqual(stored["last_delivery"]["status"], "sent_verified")

    def test_failed_delivery_keeps_generated_lesson_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text("{}", encoding="utf-8")
            config = {"chat_name": "EchoMind", "history_limit": 5, "agent_fallbacks": {}}
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(scheduler.direct, "load_config", return_value=config),
                mock.patch.object(scheduler.direct, "read_recent_history", return_value=[]),
                mock.patch.object(
                    scheduler,
                    "run_agent_session",
                    return_value={
                        "ok": True,
                        "message": "new lesson",
                        "backend": "codex",
                        "model": "gpt-5.3-codex-spark",
                    },
                ) as agent,
                mock.patch.object(
                    scheduler.direct,
                    "send_gui_message",
                    side_effect=RuntimeError("locked"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "locked"):
                    scheduler.run_once()
                stored = scheduler.load_state()

        agent.assert_called_once()
        self.assertEqual(stored["pending_lesson"]["message"], "new lesson")
        self.assertEqual(stored["scheduler_phase"], "lesson_delivery_deferred")


if __name__ == "__main__":
    unittest.main()
