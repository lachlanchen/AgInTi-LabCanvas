from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import tempfile
import unittest
from unittest import mock

from agentic_tools.wechat_gui_agent.scripts import echomind_language_scheduler as scheduler


class EchoMindLanguageSchedulerTests(unittest.TestCase):
    def write_accepted_daily_pdf_quality(
        self,
        pdf: Path,
        *,
        report_date: str,
    ) -> Path:
        quality_path = scheduler.daily_pdf_quality_path(pdf)
        quality_path.write_text(
            json.dumps(
                {
                    "status": "accepted",
                    "report_date": report_date,
                    "contract_issues": [],
                    "semantic_audit": {
                        "accepted": True,
                        "scores": {
                            dimension: 4
                            for dimension in scheduler.DAILY_PDF_AUDIT_DIMENSIONS
                        },
                        "critical_issues": [],
                        "revision_instructions": [],
                    },
                    "pdf_identity": scheduler.file_transport_identity(pdf),
                }
            ),
            encoding="utf-8",
        )
        return quality_path

    def test_default_interval_is_six_hours(self) -> None:
        self.assertEqual(scheduler.INTERVAL, 21_600)
        self.assertEqual(scheduler.PERIODIC_MODEL, "gpt-5.3-codex-spark")
        self.assertEqual(scheduler.DAILY_PDF_MAX_REPAIR_PASSES, 7)
        self.assertEqual(scheduler.DAILY_PDF_LONGITUDINAL_CHAR_BUDGET, 6000)

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
        self.assertIn("\\usepackage{amsmath}", document)
        self.assertIn("IPA: /tɛst/", document)

    def test_normalize_latex_body_unwraps_machine_response_json(self) -> None:
        wrapped = json.dumps(
            {"response": r"\section*{Lesson Focus} 内容"},
            ensure_ascii=False,
        )

        self.assertEqual(
            scheduler.normalize_latex_body(wrapped),
            r"\section*{Lesson Focus} 内容",
        )

    def test_exact_language_history_falls_back_to_transport_mirror(self) -> None:
        mirror_row = mock.Mock(source_id=-8, body="预约", created_at=datetime.now(timezone.utc))
        with (
            mock.patch.object(
                scheduler,
                "load_wechat_mirror_history",
                return_value=[mirror_row],
            ) as mirror,
            mock.patch.object(scheduler, "load_history") as memory,
        ):
            rows = scheduler.exact_chat_language_history({"chat_name": "EchoMind"})

        self.assertEqual(rows, [mirror_row])
        mirror.assert_called_once()
        memory.assert_not_called()

    def test_previous_day_source_excludes_outbound_artifact_filenames(self) -> None:
        target = datetime(2026, 8, 25, 12, 0, tzinfo=scheduler.LOCAL_TZ)
        lesson = mock.Mock(
            direction="outbound",
            body="中文：别担心。 English: Don't worry. 日本語：心配しないで。",
            created_at=target,
        )
        prior_pdf = mock.Mock(
            direction="outbound",
            body="echomind-language-review-2026-08-24.pdf",
            created_at=target,
        )
        inbound_filename = mock.Mock(
            direction="inbound",
            body="learner-notes.pdf",
            created_at=target,
        )
        with mock.patch.object(
            scheduler,
            "exact_chat_language_history",
            return_value=[lesson, prior_pdf, inbound_filename],
        ):
            rows = scheduler.previous_day_language_messages(
                {"chat_name": "EchoMind"},
                "2026-08-25",
            )

        self.assertEqual(rows, [lesson, inbound_filename])

    def test_longitudinal_daily_context_can_omit_old_exact_excerpts(self) -> None:
        with (
            mock.patch.object(
                scheduler,
                "exact_chat_language_history",
                return_value=[mock.Mock()],
            ),
            mock.patch.object(
                scheduler,
                "build_context_from_messages",
                return_value={
                    "full_memory": "bounded learner profile",
                    "snapshot": "bounded learner profile\nold exact examples",
                },
            ) as build,
        ):
            context = scheduler.long_term_language_context(
                {"chat_name": "EchoMind"},
                "recurring learner needs",
                char_budget=6000,
                model="gpt-5.6-sol",
                role="daily",
                include_exact_excerpts=False,
            )

        self.assertEqual(context, "bounded learner profile")
        self.assertEqual(build.call_args.kwargs["char_budget"], 6000)

    def test_daily_pdf_quality_rejects_source_note_and_broken_ruby_inflection(self) -> None:
        source = [
            mock.Mock(
                body=(
                    "中文：我想预约明天上午的医生。 English: I would like to book an appointment. "
                    "日本語：明日の午前に医者の予約をしたいです。"
                )
            )
        ]
        body = r"""
\section{Chinese 中文}
Pinyin: Wǒ xiǎng yùyuē. Grammar 语法 Vocabulary 词汇 Common mistakes 易错 Practice 练习.
\section{English}
I would like to book an appointment.
\section{Japanese 日本語}
\ruby{起き}{お}きます。 Romaji: okimasu.
The source logs contain no recorded conversation.
""" + ("Useful explanation about the appointment and 预约. " * 120)

        issues = scheduler.daily_pdf_contract_issues(body, source_messages=source)

        self.assertIn("student_facing_source_process_note", issues)
        self.assertIn("suspected_japanese_inflection_typo", issues)

    def test_daily_pdf_editor_uses_high_effort_and_exact_source(self) -> None:
        reviewed = r"\section{中文} Wǒ yào yùyuē. \section{English} booking. \section{日本語} \ruby{予約}{よやく}. Romaji."
        with mock.patch.object(
            scheduler,
            "run_agent_session",
            return_value={"message": reviewed, "backend": "aginti", "model": "deepseek"},
        ) as agent:
            body, result = scheduler.review_daily_pdf_body(
                "draft",
                report_date="2026-08-24",
                history="预约 appointment 予約",
                config={
                    "agent_fallbacks": {},
                    "daily_pdf_quality_backend": "codex",
                    "daily_pdf_quality_model": "gpt-5.6-sol",
                    "daily_pdf_quality_effort": "high",
                },
                source_messages=[mock.Mock(body="预约")],
            )

        self.assertEqual(body, reviewed)
        self.assertEqual(result["backend"], "aginti")
        self.assertEqual(agent.call_args.kwargs["role"], "daily_language_pdf_editor")
        self.assertEqual(agent.call_args.kwargs["backend"], "codex")
        self.assertEqual(agent.call_args.kwargs["model"], "gpt-5.6-sol")
        self.assertEqual(agent.call_args.kwargs["reasoning_effort"], "high")
        self.assertFalse(agent.call_args.kwargs["reuse"])
        self.assertIn("预约 appointment 予約", agent.call_args.args[0])

    def test_daily_pdf_author_uses_document_quality_route(self) -> None:
        authored = r"\section*{Lesson Focus / 学习重点 / 学習ポイント} Useful body."
        config = {
            "daily_pdf_quality_backend": "codex",
            "daily_pdf_quality_model": "gpt-5.6-sol",
            "daily_pdf_quality_effort": "high",
            "agent_fallbacks": {"fallback_to_aginti": False},
        }
        with mock.patch.object(
            scheduler,
            "run_agent_session",
            return_value={
                "message": authored,
                "backend": "codex",
                "model": "gpt-5.6-sol",
            },
        ) as agent:
            body, result = scheduler.author_daily_pdf_body(
                "Write the complete source-grounded tutorial.",
                config=config,
            )

        self.assertEqual(body, authored)
        self.assertEqual(result["backend"], "codex")
        self.assertEqual(agent.call_args.kwargs["backend"], "codex")
        self.assertEqual(agent.call_args.kwargs["model"], "gpt-5.6-sol")
        self.assertEqual(agent.call_args.kwargs["reasoning_effort"], "high")
        self.assertEqual(agent.call_args.kwargs["role"], "daily_language_pdf_author")
        self.assertFalse(agent.call_args.kwargs["reuse"])
        self.assertEqual(
            agent.call_args.kwargs["backend_config"]["agent_fallbacks"],
            {"fallback_to_aginti": False},
        )

    def test_daily_pdf_quality_allows_corrections_but_keeps_source_coverage(self) -> None:
        source = mock.Mock(
            body=(
                "场景：预约。 中文：我喉咙痛，想预约一下明天上午的医生。 "
                "拼音：Wǒ hóulóng tòng, xiǎng yùyuē yīxià míngtiān shàngwǔ de yīshēng. "
                "English: I have a sore throat and I'd like to book a doctor's appointment for tomorrow morning. "
                "(appointment /əˈpɔɪnt.mənt/) "
                "日本語：喉（のど）が痛（いた）いので、明日（あした）の午前（ごぜん）に医者（いしゃ）の予約（よやく）をしたいです。 "
                "Romaji: Nodo ga itai node, ashita no gozen ni isha no yoyaku o shitai desu. "
                "对照：症状＋预约。"
            )
        )
        body = r"""
\section{Chinese 中文}
我喉咙痛，想预约一下明天上午的医生。
Pinyin: Wǒ hóulóng tòng, xiǎng yùyuē yīxià míngtiān shàngwǔ de yīshēng.
\section{English}
I have a sore throat and I'd like to book a doctor's appointment for tomorrow morning.
Grammar. Vocabulary / 词汇 / 語彙. Common mistakes. Practice. Exercise.
\section{Japanese 日本語}
\ruby{喉}{のど}が\ruby{痛}{いた}いので、\ruby{明日}{あした}の\ruby{午前}{ごぜん}に\ruby{医者}{いしゃ}の\ruby{予約}{よやく}をしたいです。
Romaji: Nodo ga itai node, ashita no gozen ni isha no yoyaku o shitai desu.
""" + ("Substantial usage comparison and explained answer. " * 120)

        issues = scheduler.daily_pdf_contract_issues(body, source_messages=[source])
        self.assertNotIn("source_1_weak_semantic_coverage", issues)

        altered = body.replace("I have a sore throat", "My throat hurts", 1)
        altered_issues = scheduler.daily_pdf_contract_issues(altered, source_messages=[source])
        self.assertNotIn("source_1_weak_semantic_coverage", altered_issues)

        unrelated = body.replace("我喉咙痛，想预约一下明天上午的医生。", "今天学习天气。")
        unrelated = unrelated.replace(
            "Pinyin: Wǒ hóulóng tòng, xiǎng yùyuē yīxià míngtiān shàngwǔ de yīshēng.",
            "Pinyin: Jīntiān xuéxí tiānqì.",
        )
        unrelated = unrelated.replace(
            "I have a sore throat and I'd like to book a doctor's appointment for tomorrow morning.",
            "The weather is pleasant today.",
        )
        unrelated = unrelated.replace(
            r"\ruby{喉}{のど}が\ruby{痛}{いた}いので、\ruby{明日}{あした}の\ruby{午前}{ごぜん}に\ruby{医者}{いしゃ}の\ruby{予約}{よやく}をしたいです。",
            r"\ruby{今日}{きょう}は天気がいいです。",
        )
        unrelated = unrelated.replace(
            "Romaji: Nodo ga itai node, ashita no gozen ni isha no yoyaku o shitai desu.",
            "Romaji: Kyō wa tenki ga ii desu.",
        )
        self.assertIn(
            "source_1_weak_semantic_coverage",
            scheduler.daily_pdf_contract_issues(unrelated, source_messages=[source]),
        )

    def test_daily_pdf_semantic_audit_requires_all_quality_dimensions(self) -> None:
        self.assertIn("source_specificity", scheduler.DAILY_PDF_AUDIT_DIMENSIONS)
        self.assertIn("coherence", scheduler.DAILY_PDF_AUDIT_DIMENSIONS)
        self.assertIn("reader_value", scheduler.DAILY_PDF_AUDIT_DIMENSIONS)
        accepted = {
            "accepted": True,
            "scores": {
                dimension: 4
                for dimension in scheduler.DAILY_PDF_AUDIT_DIMENSIONS
            },
            "critical_issues": [],
            "revision_instructions": [],
        }
        self.assertEqual(scheduler.daily_pdf_semantic_audit_issues(accepted), [])

        weak = json.loads(json.dumps(accepted))
        weak["scores"]["japanese_naturalness"] = 3
        weak["accepted"] = False
        weak["critical_issues"] = ["The Japanese appointment phrase is unnatural."]
        issues = scheduler.daily_pdf_semantic_audit_issues(weak)
        self.assertIn("semantic_japanese_naturalness_below_standard", issues)
        self.assertIn("semantic_audit_has_critical_issues", issues)
        self.assertIn("semantic_audit_rejected", issues)

        polish_needed = json.loads(json.dumps(accepted))
        polish_needed["revision_instructions"] = ["Use the idiomatic collocation."]
        self.assertIn(
            "semantic_audit_has_required_revisions",
            scheduler.daily_pdf_semantic_audit_issues(polish_needed),
        )

    def test_daily_pdf_repair_keeps_prior_defects_as_regression_checks(self) -> None:
        feedback = scheduler.cumulative_daily_pdf_audit_feedback(
            [
                {
                    "critical_issues": ["Do not use the awkward Chinese phrase."],
                    "revision_instructions": ["Use the natural appointment wording."],
                },
                {
                    "critical_issues": ["The exercise is ambiguous."],
                    "revision_instructions": ["Constrain the exercise."],
                },
            ]
        )

        self.assertEqual(
            feedback["current"]["critical_issues"],
            ["The exercise is ambiguous."],
        )
        self.assertIn(
            "Use the natural appointment wording.",
            feedback["regression_checks"],
        )
        self.assertNotIn("Constrain the exercise.", feedback["regression_checks"])

    def test_daily_pdf_contract_rejects_body_level_title_commands(self) -> None:
        body = r"\maketitle \section{Chinese 中文} Pinyin: yùyuē. English. Japanese 日本語. Grammar 语法 Vocabulary 词汇 Common mistakes 易错 Practice 练习 Romaji. \ruby{予約}{よやく}."
        body += " Substantial teaching content." * 300
        self.assertIn(
            "contains_document_title_command",
            scheduler.daily_pdf_contract_issues(body),
        )

    def test_daily_pdf_contract_rejects_invalid_reading_commands(self) -> None:
        body = (
            r"\section*{Lesson Focus / 学习重点 / 学習ポイント} "
            r"\section*{Core Examples / 核心例句 / 基本例} "
            r"\ruby{準備}{junbi} \ruby{漢字}{かな} \textipa{test} "
            r"\section*{Grammar and Usage / 语法与用法 / 文法と用法} "
            r"\section*{Vocabulary and Pronunciation / 词汇与发音 / 語彙と発音} "
            r"\section*{Common Mistakes / 常见错误 / よくある間違い} "
            r"\section*{Practice and Answers / 练习与答案 / 練習と解答} "
            "Romaji: junbi. Pinyin: zhǔnbèi. "
            + ("useful explanation " * 300)
        )

        issues = scheduler.daily_pdf_contract_issues(body)

        self.assertIn("contains_textipa_command", issues)
        self.assertIn("contains_ruby_placeholder", issues)
        self.assertIn("ruby_reading_uses_latin_letters", issues)

    def test_global_quality_failures_choose_full_rewrite(self) -> None:
        self.assertTrue(
            scheduler.daily_pdf_requires_full_rewrite(
                ["too_shallow", "semantic_reader_value_below_standard"]
            )
        )
        self.assertTrue(
            scheduler.daily_pdf_requires_full_rewrite(
                ["missing_section_core_examples", "missing_section_grammar_usage"]
            )
        )
        self.assertFalse(
            scheduler.daily_pdf_requires_full_rewrite(
                ["suspected_japanese_inflection_typo"]
            )
        )

    def test_daily_pdf_contract_rejects_padding_beyond_maximum(self) -> None:
        body = "x" * (scheduler.DAILY_PDF_MAX_BODY_CHARS + 1)
        self.assertIn("too_verbose", scheduler.daily_pdf_contract_issues(body))

    def test_daily_pdf_audit_uses_xhigh_by_default(self) -> None:
        self.assertEqual(scheduler.daily_pdf_audit_effort({}), "xhigh")
        self.assertEqual(
            scheduler.daily_pdf_audit_effort({"daily_pdf_audit_effort": "high"}),
            "high",
        )

    def test_daily_pdf_audit_parser_accepts_fenced_json(self) -> None:
        payload = scheduler.parse_daily_pdf_audit(
            '```json\n{"accepted": true, "scores": {}, "critical_issues": []}\n```'
        )
        self.assertTrue(payload["accepted"])

    def test_daily_pdf_structure_requires_one_section_per_teaching_role(self) -> None:
        canonical = "\n\n".join(
            [
                r"\section*{Lesson Focus / 学习重点 / 学習ポイント}\nFocus.",
                r"\section*{Core Examples / 核心例句 / 基本例}\nExamples.",
                r"\section*{Grammar and Usage / 语法与用法 / 文法と用法}\nGrammar.",
                r"\section*{Vocabulary and Pronunciation / 词汇与发音 / 語彙と発音}\nVocabulary.",
                r"\section*{Common Mistakes / 常见错误 / よくある間違い}\nMistakes.",
                r"\section*{Practice and Answers / 练习与答案 / 練習と解答}\nPractice.",
            ]
        ).replace(r"\n", "\n")

        self.assertEqual(scheduler.daily_pdf_structure_issues(canonical), [])

        noncanonical = canonical.replace("Grammar and Usage", "Focused Contrast")
        self.assertIn(
            "missing_section_grammar_usage",
            scheduler.daily_pdf_structure_issues(noncanonical),
        )

    def test_daily_pdf_section_patch_preserves_unselected_sections(self) -> None:
        body = "\n\n".join(
            f"\\section*{{Section {index}}}\nOriginal {index}."
            for index in range(1, 4)
        )
        raw = r"""<patches>
<replace section="2">
\section*{Section 2}
Corrected grammar only.
</replace>
</patches>"""

        patches, issues = scheduler.parse_daily_pdf_section_patches(
            raw,
            section_count=3,
        )
        repaired = scheduler.apply_daily_pdf_section_patches(body, patches)

        self.assertEqual(issues, [])
        self.assertIn("Original 1.", repaired)
        self.assertIn("Corrected grammar only.", repaired)
        self.assertIn("Original 3.", repaired)
        self.assertNotIn("Original 2.", repaired)

    def test_daily_pdf_section_patch_rejects_multiple_top_level_sections(self) -> None:
        raw = r"""<patches>
<replace section="1">
\section*{One}
Text.
\section*{Injected}
More text.
</replace>
</patches>"""

        patches, issues = scheduler.parse_daily_pdf_section_patches(
            raw,
            section_count=2,
        )

        self.assertEqual(patches, [])
        self.assertIn("repair_patch_invalid_replacement_section", issues)
        self.assertIn("repair_patch_empty", issues)

    def test_daily_pdf_repair_uses_surgical_section_protocol(self) -> None:
        body = "\n\n".join(
            f"\\section*{{Section {index}}}\nOriginal {index}."
            for index in range(1, 4)
        )
        patch_response = r"""<patches>
<replace section="2">
\section*{Section 2}
Corrected section.
</replace>
</patches>"""
        with mock.patch.object(
            scheduler,
            "run_agent_session",
            return_value={
                "message": patch_response,
                "backend": "codex",
                "model": "gpt-5.6-sol",
            },
        ) as agent:
            repaired, result = scheduler.repair_daily_pdf_body(
                body,
                report_date="2026-08-24",
                history="source evidence",
                config={"agent_fallbacks": {}},
                source_messages=[mock.Mock(body="source evidence")],
                issues=["semantic_concision_below_standard"],
                audit_feedback={"revision_instructions": ["Fix section 2."]},
            )

        self.assertIn("Original 1.", repaired)
        self.assertIn("Corrected section.", repaired)
        self.assertIn("Original 3.", repaired)
        self.assertEqual(result["repair_patch_issues"], [])
        prompt = agent.call_args.args[0]
        self.assertIn("Return ONLY a <patches> block", prompt)
        self.assertIn("===== SECTION 2 =====", prompt)

    def test_daily_pdf_repair_keeps_monotonic_compression_above_soft_target(self) -> None:
        body = "\n\n".join(
            f"\\section*{{Section {index}}}\n" + ("Original material. " * 45)
            for index in range(1, 4)
        )
        replacement = "Compressed useful material. " * 15
        patch_response = f"""<patches>
<replace section="2">
\\section*{{Section 2}}
{replacement}
</replace>
<replace section="3">
\\section*{{Section 3}}
{replacement}
</replace>
</patches>"""
        with (
            mock.patch.object(scheduler, "DAILY_PDF_MIN_BODY_CHARS", 100),
            mock.patch.object(scheduler, "DAILY_PDF_TARGET_MAX_BODY_CHARS", 1200),
            mock.patch.object(scheduler, "DAILY_PDF_MAX_BODY_CHARS", 1800),
            mock.patch.object(
                scheduler,
                "run_agent_session",
                return_value={"message": patch_response, "backend": "codex"},
            ),
        ):
            repaired, result = scheduler.repair_daily_pdf_body(
                body,
                report_date="2026-08-24",
                history="source evidence",
                config={"agent_fallbacks": {}},
                source_messages=[mock.Mock(body="source evidence")],
                issues=["too_verbose"],
                audit_feedback={"revision_instructions": ["Remove repetition."]},
            )

        self.assertLess(len(repaired), len(body))
        self.assertGreater(len(repaired), 1200)
        self.assertEqual(result["repair_patch_issues"], [])
        self.assertTrue(result["repair_candidate_above_target"])
        self.assertTrue(result["repair_candidate_improved"])

    def test_daily_pdf_repair_allows_accuracy_fix_within_hard_ceiling(self) -> None:
        body = "\n\n".join(
            [
                "\\section*{Section 1}\n" + ("Useful material. " * 38),
                "\\section*{Section 2}\n" + ("Reading detail. " * 38),
            ]
        )
        patch_response = r"""<patches>
<replace section="2">
\section*{Section 2}
Reading detail with corrected pinyin and romaji. Reading detail with corrected pronunciation evidence.
</replace>
</patches>"""
        with (
            mock.patch.object(scheduler, "DAILY_PDF_MIN_BODY_CHARS", 100),
            mock.patch.object(scheduler, "DAILY_PDF_TARGET_MAX_BODY_CHARS", 500),
            mock.patch.object(scheduler, "DAILY_PDF_MAX_BODY_CHARS", 1000),
            mock.patch.object(
                scheduler,
                "run_agent_session",
                return_value={"message": patch_response, "backend": "codex"},
            ),
        ):
            repaired, result = scheduler.repair_daily_pdf_body(
                body,
                report_date="2026-08-24",
                history="source evidence",
                config={"agent_fallbacks": {}},
                source_messages=[mock.Mock(body="source evidence")],
                issues=["semantic_reading_accuracy_below_standard"],
                audit_feedback={"revision_instructions": ["Correct the reading."]},
            )

        self.assertLessEqual(len(repaired), 1000)
        self.assertGreater(len(repaired), 500)
        self.assertIn("corrected pinyin and romaji", repaired)
        self.assertEqual(result["repair_patch_issues"], [])

    def test_daily_pdf_repair_reauthors_instead_of_expanding_above_target(self) -> None:
        body = "\n\n".join(
            [
                "\\section*{Section 1}\n" + ("Useful material. " * 20),
                "\\section*{Section 2}\n" + ("Focused practice. " * 20),
            ]
        )
        replacement = "Expanded local checklist material. " * 30
        patch_response = f"""<patches>
<replace section="2">
\\section*{{Section 2}}
{replacement}
</replace>
</patches>"""
        with (
            mock.patch.object(scheduler, "DAILY_PDF_MIN_BODY_CHARS", 100),
            mock.patch.object(scheduler, "DAILY_PDF_TARGET_MAX_BODY_CHARS", 500),
            mock.patch.object(scheduler, "DAILY_PDF_MAX_BODY_CHARS", 2000),
            mock.patch.object(
                scheduler,
                "run_agent_session",
                return_value={"message": patch_response, "backend": "codex"},
            ),
        ):
            repaired, result = scheduler.repair_daily_pdf_body(
                body,
                report_date="2026-08-24",
                history="source evidence",
                config={"agent_fallbacks": {}},
                source_messages=[mock.Mock(body="source evidence")],
                issues=["semantic_concision_below_standard"],
                audit_feedback={"revision_instructions": ["Remove repetition."]},
            )

        self.assertEqual(repaired, scheduler.normalize_latex_body(body))
        self.assertIn(
            "repair_patch_worsened_above_target",
            result["repair_patch_issues"],
        )
        self.assertTrue(result["repair_candidate_above_target"])
        self.assertFalse(result["repair_candidate_improved"])

    def test_daily_pdf_reauthor_uses_source_and_reader_value_contract(self) -> None:
        replacement = r"\section*{Lesson Focus / 学习重点 / 学習ポイント} New body."
        with mock.patch.object(
            scheduler,
            "run_agent_session",
            return_value={
                "message": replacement,
                "backend": "codex",
                "model": "gpt-5.6-sol",
            },
        ) as agent:
            body, result = scheduler.rewrite_daily_pdf_body(
                "rejected body",
                report_date="2026-08-24",
                history="exact source situation",
                config={"agent_fallbacks": {}},
                source_messages=[mock.Mock(body="source")],
                issues=["semantic_reader_value_below_standard"],
                audit_feedback={"current": {"accepted": False}},
            )

        self.assertEqual(body, replacement)
        self.assertEqual(result["repair_strategy"], "full_rewrite")
        prompt = agent.call_args.args[0]
        self.assertIn("exact previous-day evidence", prompt)
        self.assertIn("durable reader value", prompt)
        self.assertIn("exact source situation", prompt)

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
                mock.patch.object(scheduler, "run_agent_session", side_effect=agent) as agent_mock,
            ):
                result = scheduler.run_once(deliver=False)

        self.assertTrue(result["ok"])
        self.assertIn("full-sentence pinyin with tone marks", observed["prompt"])
        self.assertIn("予約（よやく）", observed["prompt"])
        self.assertIn("plus romaji", observed["prompt"])
        self.assertIn("exactly one aligned core example", observed["prompt"])
        self.assertEqual(agent_mock.call_args.kwargs["backend"], "aginti")

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
            quality = self.write_accepted_daily_pdf_quality(
                pdf,
                report_date="2026-07-22",
            )
            state = {
                "pending_daily_pdf": {
                    "date": "2026-07-22",
                    "pdf": str(pdf),
                    "quality": str(quality),
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
            quality = self.write_accepted_daily_pdf_quality(
                pdf,
                report_date="2026-07-22",
            )
            state = {
                "pending_daily_pdf": {
                    "date": "2026-07-22",
                    "pdf": str(pdf),
                    "quality": str(quality),
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

    def test_rejected_pending_daily_pdf_is_never_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_path = tmp_path / "state.json"
            pdf = tmp_path / "review.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            quality = scheduler.daily_pdf_quality_path(pdf)
            quality.write_text(
                json.dumps(
                    {
                        "status": "content_rejected",
                        "report_date": "2026-07-22",
                        "contract_issues": ["semantic_reader_value_below_standard"],
                    }
                ),
                encoding="utf-8",
            )
            state = {
                "pending_daily_pdf": {
                    "date": "2026-07-22",
                    "pdf": str(pdf),
                    "quality": str(quality),
                }
            }
            with (
                mock.patch.object(scheduler, "STATE", state_path),
                mock.patch.object(scheduler, "send_file") as send,
                mock.patch.object(
                    scheduler,
                    "run_agent_session",
                    side_effect=RuntimeError("regeneration started"),
                ),
                mock.patch.object(
                    scheduler,
                    "previous_day_language_messages",
                    return_value=[],
                ),
                mock.patch.object(
                    scheduler,
                    "long_term_language_context",
                    return_value="",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "regeneration started"):
                    scheduler.run_daily_pdf(
                        {"chat_name": "EchoMind", "agent_fallbacks": {}},
                        state,
                        now=datetime(2026, 7, 23, 6, 5, tzinfo=scheduler.LOCAL_TZ),
                        force=True,
                    )
                stored = scheduler.load_state()

        send.assert_not_called()
        self.assertNotIn("pending_daily_pdf", stored)
        self.assertIn(
            "pending_pdf_quality_not_accepted",
            stored["last_rejected_pending_daily_pdf"]["issues"],
        )

    def test_accepted_pending_daily_pdf_rejects_content_identity_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "review.pdf"
            pdf.write_bytes(b"%PDF-1.4\noriginal")
            quality = self.write_accepted_daily_pdf_quality(
                pdf,
                report_date="2026-07-22",
            )
            pdf.write_bytes(b"%PDF-1.4\nchanged")

            issues = scheduler.accepted_daily_pdf_issues(
                pdf,
                report_date="2026-07-22",
                quality_path=quality,
            )

        self.assertIn("pending_pdf_identity_mismatch", issues)

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
