from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import tempfile
import unittest
from unittest import mock

from agentic_tools.wechat_gui_agent.scripts import echomind_language_scheduler as scheduler


class EchoMindLanguageSchedulerTests(unittest.TestCase):
    def test_default_interval_is_six_hours(self) -> None:
        self.assertEqual(scheduler.INTERVAL, 21_600)
        self.assertEqual(scheduler.PERIODIC_MODEL, "gpt-5.3-codex-spark")

    def test_restart_waits_for_remaining_interval(self) -> None:
        state = {"last_run_at": "2026-07-22T07:02:37+00:00"}
        now = datetime(2026, 7, 22, 7, 32, 37, tzinfo=timezone.utc)

        remaining = scheduler.seconds_until_due(state, scheduler.INTERVAL, now=now)

        self.assertEqual(remaining, 19_800)

    def test_due_when_six_hours_have_elapsed(self) -> None:
        state = {"last_run_at": "2026-07-22T07:02:37+00:00"}
        now = datetime(2026, 7, 22, 13, 2, 37, tzinfo=timezone.utc)

        remaining = scheduler.seconds_until_due(state, scheduler.INTERVAL, now=now)

        self.assertEqual(remaining, 0)

    def test_quiet_hours_wake_at_six_for_daily_pdf_then_poll_until_eight(self) -> None:
        before_daily = datetime(2026, 7, 23, 5, 50, tzinfo=scheduler.LOCAL_TZ)
        after_daily = datetime(2026, 7, 23, 6, 5, tzinfo=scheduler.LOCAL_TZ)

        self.assertEqual(scheduler.quiet_seconds(now=before_daily), 600)
        self.assertEqual(
            scheduler.quiet_seconds(now=after_daily),
            scheduler.SCHEDULER_POLL_SECONDS,
        )

    def test_daily_pdf_is_independent_of_quiet_hours_and_catches_up(self) -> None:
        before = datetime(2026, 7, 23, 5, 59, tzinfo=scheduler.LOCAL_TZ)
        due = datetime(2026, 7, 23, 6, 0, tzinfo=scheduler.LOCAL_TZ)
        catch_up = datetime(2026, 7, 23, 19, 30, tzinfo=scheduler.LOCAL_TZ)

        self.assertFalse(scheduler.daily_pdf_due({}, now=before))
        self.assertTrue(scheduler.daily_pdf_due({}, now=due))
        self.assertTrue(scheduler.daily_pdf_due({}, now=catch_up))

    def test_daily_pdf_force_runs_before_six_but_never_duplicates(self) -> None:
        now = datetime(2026, 7, 23, 5, 30, tzinfo=scheduler.LOCAL_TZ)
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

    def test_periodic_lesson_contract_rejects_clipping_prone_output(self) -> None:
        oversized = ("一句有用的三语课程。" * 300) + "\n\n不应到达这里。"

        issues = scheduler.periodic_lesson_contract_issues(oversized, max_chars=800)

        self.assertIn("too_long", issues)
        self.assertIn("missing_inline_furigana", issues)
        self.assertIn("missing_tone_marked_pinyin", issues)

    def test_periodic_prompt_requires_complete_aligned_trilingual_readings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text("{}", encoding="utf-8")
            observed: dict[str, str] = {}

            def agent(prompt: str, **_kwargs):
                observed["prompt"] = prompt
                return {
                    "ok": True,
                    "message": "场景：预约。\n中文：我想预约。\n拼音：Wǒ xiǎng yùyuē.\nEnglish: I'd like to make a reservation.\n日本語：予約（よやく）したいです。\nRomaji: Yoyaku shitai desu.\n对照：三语都先表达意愿。\n易错：不要直译语序。\n练习：改成明天。\n答案：我想预约明天。",
                    "backend": "codex",
                    "model": "gpt-5.3-codex-spark",
                }

            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(
                    scheduler.direct,
                    "load_config",
                    return_value={"chat_name": "EchoMind", "agent_fallbacks": {}},
                ),
                mock.patch.object(scheduler.direct, "read_recent_history", return_value=[]),
                mock.patch.object(scheduler, "run_agent_session", side_effect=agent),
            ):
                result = scheduler.run_once(deliver=False)

        self.assertTrue(result["ok"])
        self.assertIn("full-sentence pinyin with tone marks", observed["prompt"])
        self.assertIn("予約（よやく）", observed["prompt"])
        self.assertIn("plus romaji", observed["prompt"])
        self.assertIn("exactly one aligned core example", observed["prompt"])

    def test_incomplete_periodic_lesson_is_agent_edited_before_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text("{}", encoding="utf-8")
            repaired = "场景：购物。\n中文：这个多少钱？\n拼音：Zhège duōshao qián?\nEnglish: How much is this?\n日本語：これは幾（いく）らですか。\nRomaji: Kore wa ikura desu ka.\n对照：三语都可直接询价。\n易错：英语需要 is。\n练习：问两个多少钱。\n答案：这两个多少钱？"
            results = [
                {
                    "ok": True,
                    "message": "过长而且不完整。" * 200,
                    "backend": "codex",
                    "model": "gpt-5.3-codex-spark",
                },
                {
                    "ok": True,
                    "message": repaired,
                    "backend": "codex",
                    "model": "gpt-5.6-sol",
                },
            ]
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(
                    scheduler.direct,
                    "load_config",
                    return_value={"chat_name": "EchoMind", "agent_fallbacks": {}},
                ),
                mock.patch.object(scheduler.direct, "read_recent_history", return_value=[]),
                mock.patch.object(scheduler, "run_agent_session", side_effect=results) as agent,
            ):
                result = scheduler.run_once(deliver=False)
                stored = scheduler.load_state()

        self.assertTrue(result["ok"])
        self.assertEqual(agent.call_count, 2)
        self.assertEqual(stored["last_message"], repaired)
        self.assertEqual(stored["last_model"], "gpt-5.6-sol")

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

    def test_pending_lesson_recovers_recorded_delivery_without_sending_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                '{"pending_lesson":{"message":"lesson","topic":"travel","next_topic_index":2,"generated_at":"2026-07-27T01:00:00+00:00"}}',
                encoding="utf-8",
            )
            config = {"chat_name": "EchoMind"}
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(scheduler.direct, "load_config", return_value=config),
                mock.patch.object(scheduler, "periodic_lesson_delivery_recorded", return_value=True),
                mock.patch.object(scheduler.direct, "send_gui_message") as send,
            ):
                result = scheduler.run_once()
                stored = scheduler.load_state()

        send.assert_not_called()
        self.assertEqual(result["delivery"]["status"], "sent_verified_recovered")
        self.assertNotIn("pending_lesson", stored)

    def test_failed_delivery_keeps_generated_lesson_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text("{}", encoding="utf-8")
            config = {"chat_name": "EchoMind", "history_limit": 5, "agent_fallbacks": {}}
            lesson = "场景：问路。\n中文：地铁站在哪里？\n拼音：Dìtiě zhàn zài nǎlǐ?\nEnglish: Where is the metro station?\n日本語：地下鉄（ちかてつ）の駅（えき）はどこですか。\nRomaji: Chikatetsu no eki wa doko desu ka.\n对照：三语都询问地点。\n易错：英语需要 is。\n练习：改成洗手间。\n答案：洗手间在哪里？"
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(scheduler.direct, "load_config", return_value=config),
                mock.patch.object(scheduler.direct, "read_recent_history", return_value=[]),
                mock.patch.object(
                    scheduler,
                    "run_agent_session",
                    return_value={
                        "ok": True,
                        "message": lesson,
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
        self.assertEqual(stored["pending_lesson"]["message"], lesson)
        self.assertEqual(stored["scheduler_phase"], "lesson_retry_wait")
        self.assertEqual(stored["pending_lesson"]["delivery_attempts"], 1)
        self.assertTrue(stored["pending_lesson"]["next_attempt_at"])

    def test_pending_lesson_waits_for_durable_retry_without_sending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "pending_lesson": {
                            "message": "lesson",
                            "next_attempt_at": "2099-01-01T00:00:00+00:00",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(
                    scheduler.direct,
                    "load_config",
                    return_value={"chat_name": "EchoMind"},
                ),
                mock.patch.object(scheduler.direct, "send_gui_message") as send,
            ):
                result = scheduler.run_once()
                stored = scheduler.load_state()

        self.assertEqual(result["status"], "delivery_deferred")
        self.assertGreater(result["retry_in_seconds"], 0)
        send.assert_not_called()
        self.assertEqual(stored["scheduler_phase"], "lesson_retry_wait")

    def test_forced_pending_retry_sends_existing_lesson_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "pending_lesson": {
                            "message": "lesson",
                            "next_attempt_at": "2099-01-01T00:00:00+00:00",
                        }
                    }
                ),
                encoding="utf-8",
            )
            screenshot = Path(tmp) / "sent.png"
            screenshot.write_bytes(b"png")
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(
                    scheduler.direct,
                    "load_config",
                    return_value={"chat_name": "EchoMind"},
                ),
                mock.patch.object(
                    scheduler.direct,
                    "send_gui_message",
                    return_value=str(screenshot),
                ) as send,
                mock.patch.object(scheduler, "run_agent_session") as agent,
            ):
                result = scheduler.run_once(force_pending_retry=True)
                stored = scheduler.load_state()

        self.assertTrue(result["ok"])
        send.assert_called_once()
        agent.assert_not_called()
        self.assertNotIn("pending_lesson", stored)

    def test_pending_daily_pdf_reserves_lane_and_retries_without_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_path = tmp_path / "state.json"
            priority_path = tmp_path / "priority.json"
            pdf = tmp_path / "review.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            state = {
                "pending_daily_pdf": {
                    "date": "2026-07-22",
                    "pdf": str(pdf),
                }
            }
            config = {"chat_name": "EchoMind"}
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(scheduler, "GUI_SEND_PRIORITY", priority_path),
                mock.patch.object(scheduler, "daily_pdf_delivery_recorded", return_value=False),
                mock.patch.object(
                    scheduler,
                    "send_file",
                    side_effect=[RuntimeError("WECHAT_SEND_BUSY"), None],
                ) as send,
                mock.patch.object(scheduler.time, "sleep"),
            ):
                result = scheduler.run_daily_pdf(
                    config,
                    state,
                    now=datetime(2026, 7, 23, 6, 5, tzinfo=scheduler.LOCAL_TZ),
                    force=True,
                )

        self.assertEqual(result["status"], "sent_verified")
        self.assertEqual(send.call_count, 2)
        self.assertFalse(priority_path.exists())
        self.assertNotIn("pending_daily_pdf", state)
        self.assertEqual(state["last_daily_pdf_attempt_date"], "2026-07-22")
        self.assertEqual(
            state["last_daily_pdf_attempt_at"],
            "2026-07-23T06:05:00+08:00",
        )

    def test_pending_daily_pdf_persists_retry_timestamp_before_send_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_path = tmp_path / "state.json"
            priority_path = tmp_path / "priority.json"
            pdf = tmp_path / "review.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            state = {
                "pending_daily_pdf": {
                    "date": "2026-07-22",
                    "pdf": str(pdf),
                }
            }
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(scheduler, "GUI_SEND_PRIORITY", priority_path),
                mock.patch.object(
                    scheduler,
                    "daily_pdf_delivery_recorded",
                    return_value=False,
                ),
                mock.patch.object(
                    scheduler,
                    "send_file",
                    side_effect=RuntimeError("delivery unavailable"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "delivery unavailable"):
                    scheduler.run_daily_pdf(
                        {"chat_name": "EchoMind"},
                        state,
                        now=datetime(2026, 7, 23, 6, 5, tzinfo=scheduler.LOCAL_TZ),
                        force=True,
                    )
                stored = scheduler.load_state()

        self.assertIn("pending_daily_pdf", stored)
        self.assertEqual(stored["last_daily_pdf_attempt_date"], "2026-07-22")
        self.assertEqual(
            stored["last_daily_pdf_attempt_at"],
            "2026-07-23T06:05:00+08:00",
        )

    def test_priority_marker_is_visible_during_scheduled_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            priority_path = Path(tmp) / "priority.json"
            observed: dict[str, object] = {}

            def sender(*_args):
                observed.update(json.loads(priority_path.read_text(encoding="utf-8")))
                return "sent.png"

            with (
                mock.patch.object(scheduler, "GUI_SEND_PRIORITY", priority_path),
                mock.patch.object(scheduler.direct, "send_gui_message", side_effect=sender),
            ):
                screenshot = scheduler.send_scheduled_message(
                    {"chat_name": "EchoMind"},
                    "lesson",
                )

        self.assertEqual(screenshot, "sent.png")
        self.assertEqual(observed["chat"], "EchoMind")
        self.assertEqual(observed["owner"], "echomind_periodic_lesson")
        self.assertFalse(priority_path.exists())


if __name__ == "__main__":
    unittest.main()
