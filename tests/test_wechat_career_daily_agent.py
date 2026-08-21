import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_wechat_career_daily_agent():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_career_daily_agent.py"
    spec = importlib.util.spec_from_file_location("wechat_career_daily_agent_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatCareerDailyAgentTests(unittest.TestCase):
    def test_main_defaults_to_medium_reasoning(self):
        module = load_wechat_career_daily_agent()
        captured = {}
        original_argv = sys.argv[:]
        original_effort = os.environ.pop("WECHAT_CAREER_AGENT_EFFORT", None)
        try:
            sys.argv = ["wechat_career_daily_agent.py"]
            module.run_daily = lambda args: captured.update({"model": args.model, "effort": args.reasoning_effort}) or {"ok": True, "summary": "ok"}
            rc = module.main()
        finally:
            sys.argv = original_argv
            if original_effort is not None:
                os.environ["WECHAT_CAREER_AGENT_EFFORT"] = original_effort

        self.assertEqual(rc, 0)
        self.assertEqual(captured["model"], "gpt-5.5")
        self.assertEqual(captured["effort"], "medium")

    def test_retry_action_reuses_generated_report(self):
        module = load_wechat_career_daily_agent()
        captured = {}
        original_argv = sys.argv[:]
        original_retry = module.retry_existing_career_delivery
        try:
            sys.argv = [
                "wechat_career_daily_agent.py",
                "retry",
                "--date",
                "2026-07-29",
                "--json",
            ]
            module.retry_existing_career_delivery = (
                lambda args, stamp, force=False: captured.update(
                    {"stamp": stamp, "force": force}
                )
                or {"ok": True, "status": "done"}
            )
            rc = module.main()
        finally:
            sys.argv = original_argv
            module.retry_existing_career_delivery = original_retry

        self.assertEqual(rc, 0)
        self.assertEqual(captured, {"stamp": "2026-07-29", "force": True})

    def test_uncertain_file_delivery_reconciles_from_exact_outbound_echo(self):
        module = load_wechat_career_daily_agent()
        original_private = module.PRIVATE
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            private.mkdir()
            module.PRIVATE = private
            report = Path(tmp) / "daily.pdf"
            report.write_bytes(b"%PDF-1.4\nexact report\n")
            identity = module.file_transport_identity(report)
            db = private / "wechat_mirror.sqlite"
            with sqlite3.connect(db) as conn:
                conn.executescript(
                    """
                    CREATE TABLE chats (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE
                    );
                    CREATE TABLE events (
                        id INTEGER PRIMARY KEY,
                        chat_id INTEGER NOT NULL,
                        action TEXT NOT NULL,
                        direction TEXT,
                        message TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute("INSERT INTO chats(id, name) VALUES (1, ?)", ("写作 外语 挣钱",))
                conn.execute(
                    """
                    INSERT INTO events(
                        chat_id, action, direction, message, status, created_at
                    ) VALUES (1, 'direct_message', 'outbound', ?, 'synced', ?)
                    """,
                    (
                        (
                            "<msg><appmsg>"
                            f"<title>{report.name}</title>"
                            f"<appattach><totallen>{identity['size_bytes']}</totallen></appattach>"
                            f"<md5>{identity['md5']}</md5>"
                            "</appmsg></msg>"
                        ),
                        "2026-07-29T11:10:00",
                    ),
                )

            try:
                observed = module.observed_outbound_file(
                    "写作 外语 挣钱",
                    report,
                    not_before="2026-07-29T08:30:00",
                )
            finally:
                module.PRIVATE = original_private

        self.assertTrue(observed)

    def test_prompt_requires_three_self_discovery_questions(self):
        module = load_wechat_career_daily_agent()
        prompt = module.build_prompt(
            {
                "memory_snapshot": "- writing/money pattern",
                "project_surface": "- LabCanvas",
                "lazyinvestment_snapshot": "",
                "voidabyss_snapshot": "",
                "identity_surface": "",
            }
        )

        self.assertIn("deep, useful morning note", prompt)
        self.assertIn("Do not write a shallow checklist", prompt)
        self.assertIn("exactly three self-discovery questions", prompt)
        self.assertIn("specific to", prompt)
        self.assertIn("Q1:", prompt)
        self.assertIn("Use an evidence hierarchy", prompt)
        self.assertIn("ordinary memo/todo/inbox/grocery/hardware-list", prompt)
        self.assertIn("Do not turn", prompt)
        self.assertIn("GitHub, website, local repos", prompt)
        self.assertIn("model-budgeted lifetime-memory hierarchy", prompt)
        self.assertIn("every authorized history", prompt)
        self.assertIn("raw excerpts for exact wording", prompt)
        self.assertIn("Prior daily strategy decisions", prompt)
        self.assertIn("identify what changed", prompt)

    def test_extract_self_discovery_questions_for_chat_message(self):
        module = load_wechat_career_daily_agent()
        report = """
## 9. Today’s 3 self-discovery questions

Q1: Which public problem would I still want to explain if nobody praised me for it?
Why it matters: It reveals durable motivation.
Q2: What am I avoiding by building one more tool instead of publishing one clear offer?
Why it matters: It exposes avoidance disguised as productivity.
Q3: Which project would hurt most to abandon, and what does that say about my real identity?
Why it matters: It shows attachment and leverage.

## Appendix
Other text?
"""

        questions = module.extract_self_discovery_questions(report)

        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0], "Which public problem would I still want to explain if nobody praised me for it?")
        self.assertIn("one more tool", questions[1])
        self.assertIn("real identity", questions[2])

    def test_extract_self_discovery_questions_without_section_heading(self):
        module = load_wechat_career_daily_agent()
        report = """
## 今天做什么
先完成一个可验证的作品。

Q1: 今天我要留下什么可以给别人看的证据?
为什么重要：它把想法变成资产。
Q2: 哪一个项目值得我拒绝其他机会?
为什么重要：它迫使我选择。
Q3: 今天谁可以给我一个真实反馈?
为什么重要：它防止闭门造车。
"""

        questions = module.extract_self_discovery_questions(report)

        self.assertEqual(len(questions), 3)
        self.assertIn("什么可以给别人看的证据", questions[0])

    def test_send_daily_result_includes_self_discovery_questions(self):
        module = load_wechat_career_daily_agent()
        sent_messages = []
        sent_files = []
        module.send_message = lambda message, chat, send_targets: sent_messages.append((message, chat, send_targets))
        module.send_file = lambda report, chat, send_targets: sent_files.append((report, chat, send_targets))
        module.ensure_markdown_pdf_companions = lambda report: [
            report.with_name("report.zh.pdf"),
            report.with_name("report.en.pdf"),
        ]
        args = argparse.Namespace(
            send_chat="lachlanchan",
            send_targets=Path("/tmp/send-targets.json"),
            attach_report=True,
        )
        body = """
## 1. Today’s thesis
A precise thesis for the day.

微信摘要：今天最强的新证据是用户已经连续完成了三个可复用工具。主赌注是把其中一个包装成可购买的服务，今天先写清楚报价并找一个真实用户验证。

## 9. Today’s 3 self-discovery questions
Q1: What desire am I protecting by not choosing one public offer?
Why it matters: It names avoidance.
Q2: Which audience would I be willing to disappoint in order to serve the right one?
Why it matters: It clarifies tradeoffs.
Q3: What small proof today would make this identity feel real?
Why it matters: It turns reflection into evidence.
"""

        status = module.send_daily_result(args, Path("/tmp/report.md"), body)

        self.assertTrue(status["message_sent"])
        self.assertTrue(status["file_sent"])
        self.assertTrue(status["complete"])
        self.assertIn("今天最强的新证据", sent_messages[0][0])
        self.assertIn("今天值得认真回答的三个问题", sent_messages[0][0])
        self.assertIn("not choosing one public offer", sent_messages[0][0])
        self.assertIn("small proof today", sent_messages[0][0])
        self.assertEqual(sent_messages[0][1], "lachlanchan")
        self.assertEqual(sent_files[0][0], Path("/tmp/report.zh.pdf"))
        self.assertEqual(sent_files[1][0], Path("/tmp/report.en.pdf"))
        self.assertEqual(status["files_sent"], ["/tmp/report.zh.pdf", "/tmp/report.en.pdf"])
        self.assertEqual(status["pdf_companion"], "/tmp/report.zh.pdf")
        self.assertEqual(status["pdf_companions"], ["/tmp/report.zh.pdf", "/tmp/report.en.pdf"])

    def test_send_daily_result_marks_missing_pdf_companion(self):
        module = load_wechat_career_daily_agent()
        sent_messages = []
        sent_files = []
        module.send_message = lambda message, chat, send_targets: sent_messages.append((message, chat, send_targets))
        module.send_file = lambda report, chat, send_targets: sent_files.append((report, chat, send_targets))
        module.ensure_markdown_pdf_companions = lambda report: []
        args = argparse.Namespace(
            send_chat="lachlanchan",
            send_targets=Path("/tmp/send-targets.json"),
            attach_report=True,
        )

        status = module.send_daily_result(args, Path("/tmp/report.md"), "## Today")

        self.assertFalse(status["message_sent"])
        self.assertFalse(status["file_sent"])
        self.assertEqual(sent_files, [])
        self.assertEqual(sent_messages, [])
        self.assertEqual(status["pdf_companions"], [])
        self.assertTrue(status["pdf_required"])
        self.assertTrue(any("required bilingual companions" in error for error in status["errors"]))

    def test_send_daily_result_reserves_gui_lane_and_releases_it(self):
        module = load_wechat_career_daily_agent()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        module.GUI_SEND_PRIORITY = Path(temp_dir.name) / "send-priority.json"
        observed = []

        def fake_send(message, chat, send_targets):
            payload = json.loads(module.GUI_SEND_PRIORITY.read_text(encoding="utf-8"))
            observed.append((message, chat, send_targets, payload))

        module.send_message = fake_send
        args = argparse.Namespace(
            send_chat="lachlanchan",
            send_targets=Path("/tmp/send-targets.json"),
            attach_report=False,
        )

        status = module.send_daily_result(
            args,
            Path("/tmp/report.md"),
            "微信摘要：今天聚焦一个可验证的客户问题，并交付一个可购买的结果。",
        )

        self.assertTrue(status["complete"])
        self.assertEqual(observed[0][3]["owner"], "career_daily")
        self.assertEqual(observed[0][3]["chat"], "lachlanchan")
        self.assertFalse(module.GUI_SEND_PRIORITY.exists())

    def test_send_daily_result_releases_gui_lane_after_send_failure(self):
        module = load_wechat_career_daily_agent()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        module.GUI_SEND_PRIORITY = Path(temp_dir.name) / "send-priority.json"
        module.send_message = lambda *_args: (_ for _ in ()).throw(RuntimeError("send failed"))
        args = argparse.Namespace(
            send_chat="lachlanchan",
            send_targets=Path("/tmp/send-targets.json"),
            attach_report=False,
        )

        status = module.send_daily_result(args, Path("/tmp/report.md"), "微信摘要：发送测试。")

        self.assertFalse(status["complete"])
        self.assertTrue(any("send failed" in error for error in status["errors"]))
        self.assertFalse(module.GUI_SEND_PRIORITY.exists())

    def test_run_daily_writes_trace_bundle_and_sanitized_share_report(self):
        module = load_wechat_career_daily_agent()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        module.ROOT = root
        module.PRIVATE = root / ".private"
        module.OUTPUT = root / "output"
        module.DEFAULT_SEND_TARGETS = module.PRIVATE / "wechat_send_targets.local.json"
        module.collect_evidence = lambda _chats, _memory_db, **_kwargs: {
            "memory_snapshot": "- private pattern: writing and money",
            "project_surface": "- AgenticApp: local tool surface",
            "lazyinvestment_snapshot": "- LazyInvestment missing in test",
            "voidabyss_snapshot": "- VoidAbyss narrative evidence",
            "identity_surface": "- lazying.art identity evidence",
        }
        module.select_agent_backend = lambda _config: "codex"
        agent_calls = []

        def fake_agent(*args, **kwargs):
            agent_calls.append((args, kwargs))
            return {
                "ok": True,
                "message": f"# Today\nUse {module.PRIVATE} as private evidence, then write one public action.",
                "backend": "codex",
                "thread_id": "thread-test",
                "resumed": True,
                "returncode": 0,
            }

        module.run_agent_session = fake_agent
        args = argparse.Namespace(
            chat=[],
            send=False,
            attach_report=False,
            memory_db=root / "memory.sqlite",
            send_targets=module.DEFAULT_SEND_TARGETS,
            model="gpt-test",
            reasoning_effort="high",
            timeout_seconds=30,
        )

        payload = module.run_daily(args)

        self.assertTrue(payload["ok"])
        self.assertEqual(agent_calls[0][1]["role"], "career_research")
        self.assertEqual(agent_calls[0][1]["sandbox"], "read-only")
        trace_dir = Path(payload["trace_dir"])
        self.assertTrue((trace_dir / "manifest.json").exists())
        self.assertTrue((trace_dir / "agent_prompt.md").exists())
        self.assertTrue((trace_dir / "memory_snapshot.md").exists())
        self.assertTrue((trace_dir / "private_report.md").exists())
        self.assertTrue((trace_dir / "share_report.md").exists())
        self.assertTrue((trace_dir / "agent_result.json").exists())

        manifest = json.loads((trace_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "labcanvas.wechat.career_daily.trace.v1")
        self.assertEqual(manifest["agent"]["model"], "gpt-test")
        self.assertIn("memory_snapshot.md", manifest["inputs"]["evidence_files"]["memory_snapshot"])
        self.assertIn("private_report.md", manifest["outputs"]["private_report_trace"])

        private_report = Path(payload["private_report"]).read_text(encoding="utf-8")
        share_report = Path(payload["share_report"]).read_text(encoding="utf-8")
        self.assertIn(str(module.PRIVATE), private_report)
        self.assertNotIn(str(module.PRIVATE), share_report)
        self.assertIn("<private-wechat-workspace>", share_report)

    def test_life_memo_snapshot_deduplicates_classifier_categories(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "memory.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE memory_items (
                        id INTEGER PRIMARY KEY,
                        source_message_id INTEGER,
                        chat_name TEXT,
                        category TEXT,
                        title TEXT,
                        body TEXT,
                        status TEXT,
                        due_at TEXT,
                        created_at TEXT
                    )
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO memory_items
                    (source_message_id, chat_name, category, title, body, status, due_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (7, "写作 外语 挣钱", "todo", "same", "整理最近的想法", "open", None, "2026-07-28T06:00:00"),
                        (7, "写作 外语 挣钱", "memo", "same", "整理最近的想法", "open", None, "2026-07-28T06:00:00"),
                        (8, "写作 外语 挣钱", "writing", "next", "写下一段接口", "open", None, "2026-07-27T06:00:00"),
                    ],
                )

            snapshot = module.life_memo_snapshot(db, "写作 外语 挣钱")

        self.assertEqual(snapshot.count("整理最近的想法"), 1)
        self.assertIn("memo/todo", snapshot)
        self.assertIn("写下一段接口", snapshot)

    def test_organizer_includes_history_from_renamed_same_profile_chat(self):
        module = load_wechat_career_daily_agent()
        chats = module.organizer_memory_chats("MEMO写作—外语—挣钱")
        self.assertIn("MEMO写作—外语—挣钱", chats)
        self.assertIn("写作 外语 挣钱", chats)
        self.assertEqual(module.organizer_memory_chats("Unrelated Group"), ["Unrelated Group"])

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "memory.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute(
                    """
                    CREATE TABLE memory_items (
                        id INTEGER PRIMARY KEY,
                        source_message_id INTEGER,
                        chat_name TEXT,
                        category TEXT,
                        title TEXT,
                        body TEXT,
                        status TEXT,
                        due_at TEXT,
                        created_at TEXT
                    )
                    """
                )
                conn.executemany(
                    """
                    INSERT INTO memory_items
                    (source_message_id, chat_name, category, title, body, status, due_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            1,
                            "写作 外语 挣钱",
                            "memo",
                            "before rename",
                            "保留改名前的重要写作想法",
                            "open",
                            None,
                            "2026-07-28T06:00:00",
                        ),
                        (
                            2,
                            "MEMO写作—外语—挣钱",
                            "todo",
                            "after rename",
                            "整理改名后的行动",
                            "open",
                            None,
                            "2026-07-29T06:00:00",
                        ),
                    ],
                )

            snapshot = module.life_memo_snapshot(db, chats)

        self.assertIn("保留改名前的重要写作想法", snapshot)
        self.assertIn("整理改名后的行动", snapshot)

    def test_organizer_prompt_keeps_daily_notes_below_life_direction(self):
        module = load_wechat_career_daily_agent()
        prompt = module.build_organizer_prompt(
            "写作 外语 挣钱",
            "- memo: 买锡丝\n- todo: 写 200 字\n- project: EchoMind",
        )

        self.assertIn("待办 / To-do", prompt)
        self.assertIn("物品和资源", prompt)
        self.assertIn("小事和日常备忘", prompt)
        self.assertIn("想做的项目和作品", prompt)
        self.assertIn("人生方向 / 长期战略", prompt)
        self.assertIn("lowest valid category", prompt)
        self.assertIn("Do not turn them", prompt)
        self.assertIn("GitHub, website, local repos", prompt)

    def test_catch_up_skips_delivered_career_and_runs_organizer_once(self):
        module = load_wechat_career_daily_agent()
        calls = []
        private_dir = tempfile.TemporaryDirectory()
        self.addCleanup(private_dir.cleanup)
        module.PRIVATE = Path(private_dir.name) / ".private"
        module.career_delivery_complete_for_date = lambda *_args, **_kwargs: True
        module.run_daily = lambda _args: self.fail("delivered career must not rerun")
        module.run_organizer = (
            lambda _args, **_kwargs: calls.append("organizer")
            or {"ok": True, "status": "already_delivered"}
        )
        args = argparse.Namespace(
            send=True,
            organize_report=True,
        )

        payload = module.run_catch_up(args)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["career"]["status"], "already_delivered")
        self.assertEqual(payload["organizer"]["status"], "already_delivered")
        self.assertEqual(calls, ["organizer"])

    def test_catch_up_forces_artifact_delivery_without_regenerating(self):
        module = load_wechat_career_daily_agent()
        calls = {}
        private_dir = tempfile.TemporaryDirectory()
        self.addCleanup(private_dir.cleanup)
        module.PRIVATE = Path(private_dir.name) / ".private"
        module.career_delivery_complete_for_date = lambda *_args, **_kwargs: False
        module.retry_existing_career_delivery = (
            lambda _args, stamp, force=False: calls.update(
                {"career_stamp": stamp, "career_force": force}
            )
            or {"ok": True, "status": "done"}
        )
        module.run_daily = lambda _args: self.fail("existing career report must be reused")
        module.run_organizer = (
            lambda _args, force_delivery=False: calls.update(
                {"organizer_force_delivery": force_delivery}
            )
            or {"ok": True, "status": "delivered", "generated": False}
        )
        args = argparse.Namespace(send=True, organize_report=True)

        payload = module.run_catch_up(args)

        self.assertTrue(payload["ok"])
        self.assertTrue(calls["career_force"])
        self.assertTrue(calls["organizer_force_delivery"])

    def test_safe_daily_call_keeps_scheduler_alive_after_exception(self):
        module = load_wechat_career_daily_agent()

        payload = module.safe_daily_call(
            lambda: (_ for _ in ()).throw(RuntimeError("temporary sender failure"))
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "scheduler_error")
        self.assertIn("temporary sender failure", payload["error"])

    def test_daily_operation_lock_prevents_overlapping_generation(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            module.PRIVATE = Path(tmp) / ".private"
            lock_path = (
                module.PRIVATE
                / "output"
                / "career_daily"
                / "career.lock"
            )
            lock_path.parent.mkdir(parents=True)
            with lock_path.open("a+", encoding="utf-8") as handle:
                module.fcntl.flock(
                    handle,
                    module.fcntl.LOCK_EX | module.fcntl.LOCK_NB,
                )
                try:
                    payload = module.run_with_daily_operation_lock(
                        "career",
                        lambda: self.fail("overlapping callback must not run"),
                    )
                finally:
                    module.fcntl.flock(handle, module.fcntl.LOCK_UN)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "already_running")

    def test_organizer_sends_only_compiled_pdf_and_is_idempotent(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module.ROOT = root
            module.PRIVATE = root / ".private"
            module.OUTPUT = root / "output"
            sent_files = []
            agent_calls = []
            module.life_memo_snapshot = lambda *_args, **_kwargs: "- memo: one exact item"
            module.select_agent_backend = lambda _config: "codex"

            def fake_agent(*args, **kwargs):
                agent_calls.append((args, kwargs))
                return {
                    "ok": True,
                    "message": "# 今日整理\n\n只保留一个重要行动。",
                    "backend": "codex",
                    "thread_id": "organizer-thread",
                    "resumed": False,
                }

            def fake_render(source, output):
                self.assertTrue(source.is_file())
                output.write_bytes(b"%PDF-1.4 organizer")
                return output

            module.run_agent_session = fake_agent
            module.render_interactive_organizer_pdf = fake_render
            module.send_file = lambda path, chat, targets: sent_files.append((path, chat, targets))
            args = argparse.Namespace(
                organize_chat="写作 外语 挣钱",
                memory_db=root / "memory.sqlite",
                model="gpt-test",
                reasoning_effort="medium",
                timeout_seconds=30,
                send=True,
                send_targets=root / "targets.json",
            )

            first = module.run_organizer(args)
            second = module.run_organizer(args)

        self.assertTrue(first["ok"])
        self.assertEqual(first["status"], "delivered")
        self.assertEqual(second["status"], "already_delivered")
        self.assertEqual(len(agent_calls), 1)
        self.assertEqual(len(sent_files), 1)
        self.assertEqual(sent_files[0][0].suffix, ".pdf")
        self.assertEqual(sent_files[0][1], "写作 外语 挣钱")

    def test_organizer_retries_existing_pdf_without_rerunning_agent(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module.ROOT = root
            module.PRIVATE = root / ".private"
            module.OUTPUT = root / "output"
            module.OUTPUT.mkdir(parents=True)
            stamp = module.datetime.now().strftime("%Y-%m-%d")
            report = module.OUTPUT / f"{stamp}-recent-items.zh.md"
            pdf = module.OUTPUT / f"{stamp}-recent-items.zh.pdf"
            report.write_text("# Existing", encoding="utf-8")
            pdf.write_bytes(b"%PDF existing")
            state_path = module.organizer_state_path()
            module.write_json_file(
                state_path,
                {
                    "date": stamp,
                    "chat": "写作 外语 挣钱",
                    "status": "delivery_failed",
                    "report": str(report),
                    "pdf": str(pdf),
                },
            )
            module.run_agent_session = lambda *_args, **_kwargs: self.fail("agent must not rerun")
            sent = []
            module.send_file = lambda path, chat, targets: sent.append((path, chat))
            args = argparse.Namespace(
                organize_chat="写作 外语 挣钱",
                memory_db=root / "memory.sqlite",
                model="gpt-test",
                reasoning_effort="medium",
                timeout_seconds=30,
                send=True,
                send_targets=root / "targets.json",
            )

            payload = module.run_organizer(args)

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["generated"])
        self.assertEqual(sent, [(pdf, "写作 外语 挣钱")])

    def test_organizer_markdown_builds_interactive_tasks_only_for_actions(self):
        module = load_wechat_career_daily_agent()
        body, count = module.organizer_markdown_to_latex(
            """
# 今日整理

## 证据
- 一个普通事实

## 本周可推进
1. 完成一个小实验
2. 发送一封邮件

## 灵感
- [ ] 验证一个明确想法
"""
        )

        self.assertEqual(count, 3)
        self.assertEqual(body.count(r"\CheckBox["), 3)
        self.assertIn(r"\item 一个普通事实", body)
        self.assertIn("完成一个小实验", body)

    @unittest.skipUnless(shutil.which("xelatex"), "xelatex is required")
    def test_interactive_organizer_pdf_contains_acroform_fields(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "organizer.md"
            output = root / "organizer.pdf"
            source.write_text(
                "# 今日整理\n\n## 下一步\n- [ ] 完成一个可验证的行动\n",
                encoding="utf-8",
            )

            rendered = module.render_interactive_organizer_pdf(source, output)

            self.assertEqual(rendered, output)
            self.assertTrue(module.pdf_has_interactive_form(output))
            self.assertTrue(output.with_suffix(".interactive.tex").is_file())

    def test_failed_delivery_uses_persisted_exponential_backoff(self):
        module = load_wechat_career_daily_agent()
        state = {}

        module.update_delivery_retry_state(
            state,
            {"attempted": True, "complete": False, "errors": ["send timeout"]},
        )

        self.assertEqual(state["delivery_attempts"], 1)
        self.assertFalse(module.delivery_retry_due(state))
        self.assertIn("next_delivery_attempt_at", state)

    def test_retry_existing_career_delivery_reuses_report_without_agent(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module.ROOT = root
            module.PRIVATE = root / ".private"
            module.OUTPUT = root / "output"
            stamp = module.datetime.now().strftime("%Y-%m-%d")
            run_dir = module.PRIVATE / "output" / "career_daily" / "runs" / f"{stamp}-083000"
            run_dir.mkdir(parents=True)
            report = module.OUTPUT / f"{stamp}-career-strategy.md"
            private_report = module.PRIVATE / "output" / "career_daily" / f"{stamp}-career-strategy-private.md"
            report.parent.mkdir(parents=True)
            private_report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("# Existing report", encoding="utf-8")
            private_report.write_text("微信摘要：复用今天已生成的报告。", encoding="utf-8")
            manifest = {
                "outputs": {
                    "share_report_latest": str(report),
                    "private_report_latest": str(private_report),
                },
                "send": {"attempted": True, "complete": False},
            }
            module.write_json_file(run_dir / "manifest.json", manifest)
            sent = []
            module.send_daily_result = lambda *args, **kwargs: sent.append((args, kwargs)) or {
                "attempted": True,
                "complete": True,
                "message_sent": True,
                "file_sent": True,
                "files_sent": ["report.zh.pdf", "report.en.pdf"],
                "errors": [],
            }
            args = argparse.Namespace(send=True)

            payload = module.retry_existing_career_delivery(args, stamp)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "done")
            self.assertEqual(len(sent), 1)
            saved = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["send"]["complete"])
            self.assertEqual(saved["delivery_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
