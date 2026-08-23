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

    def test_daily_artifact_reconciles_exact_title_after_regeneration(self):
        module = load_wechat_career_daily_agent()
        original_private = module.PRIVATE
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            private.mkdir()
            module.PRIVATE = private
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
                conn.execute("INSERT INTO chats(id, name) VALUES (1, ?)", ("Memo",))
                conn.execute(
                    """
                    INSERT INTO events(
                        chat_id, action, direction, message, status, created_at
                    ) VALUES (1, 'direct_message', 'outbound', ?, 'synced', ?)
                    """,
                    (
                        (
                            "<msg><appmsg>"
                            "<title>2026-08-22-recent-items.zh.pdf</title>"
                            "<appattach><totallen>96214</totallen></appattach>"
                            "<md5>2d41a4b391f1f901aac1f218f1927ec3</md5>"
                            "</appmsg></msg>"
                        ),
                        "2026-08-22T11:23:52",
                    ),
                )

            try:
                observed = module.observed_outbound_filename(
                    "Memo",
                    "2026-08-22-recent-items.zh.pdf",
                    not_before="2026-08-22T08:42:06",
                )
                wrong_title = module.observed_outbound_filename(
                    "Memo",
                    "2026-08-22-career-strategy.zh.pdf",
                    not_before="2026-08-22T08:42:06",
                )
            finally:
                module.PRIVATE = original_private

        self.assertTrue(observed)
        self.assertFalse(wrong_title)

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
        self.assertIn("not a raw chat\ndump", prompt)
        self.assertIn("several substantial prose\n   paragraphs", prompt)
        self.assertIn("complete organized reference section", prompt)
        self.assertIn("not an audit trail", prompt)
        self.assertIn("A voice note contributes only its cleaned meaning", prompt)

    def test_organizer_unwraps_agent_json_without_rendering_raw_envelope(self):
        module = load_wechat_career_daily_agent()

        body = module.normalize_organizer_output(
            '{"response":"# 今日整理\\n\\n## 物品\\n- Pi 5 墨水屏"}'
        )

        self.assertEqual(body, "# 今日整理\n\n## 物品\n- Pi 5 墨水屏")
        self.assertNotIn('"response"', body)

    def test_organizer_quality_rejects_generic_unrounded_advice(self):
        module = load_wechat_career_daily_agent()
        snapshot = """- inbox: Pi 5 墨水屏 录音 RAG 词库
- web_clip: Nature 光计算维度
- inbox: 竹书纪年 西京杂记 孔子家语
- request: 千与千寻 桃源世界
- memo: 讯飞声卡 焊台 LED灯珠 锡丝 磁铁
- idea: 树莓派本地语言学习卡
- writing: 建立简单写作习惯
- project: 历史博弈游戏《势》
"""
        quality = module.organizer_output_quality(
            "目标：提供翻译服务、语言教学和内容订阅。",
            snapshot,
        )

        self.assertFalse(quality["accepted"])
        self.assertIn("too_short_for_evidence", quality["reasons"])
        self.assertIn("insufficient_evidence_grounding", quality["reasons"])

    def test_organizer_quality_rejects_grounded_but_raw_bullet_dump(self):
        module = load_wechat_career_daily_agent()
        snapshot = """- memo: Pi 5 墨水屏 录音 RAG 词库
- web_clip: Nature 光计算维度
- inbox: 竹书纪年 西京杂记 孔子家语
- request: 千与千寻 桃源世界
- memo: 讯飞声卡 焊台 LED灯珠 锡丝 磁铁
- idea: 树莓派本地语言学习卡
- writing: 建立简单写作习惯
- project: 历史博弈游戏
- project: 视觉大模型预测实验
- memo: 香港取回物品清单
- idea: 懒人聊天网站
- writing: 个人叙事与历史叙事
"""
        body = """# 每日整理

## 物品
- Pi 5 墨水屏 录音 RAG 词库
- 讯飞声卡 焊台 LED灯珠 锡丝 磁铁
- 香港取回物品清单

## 阅读
- Nature 光计算维度
- 竹书纪年 西京杂记 孔子家语
- 建立简单写作习惯

## 项目
- 树莓派本地语言学习卡
- 历史博弈游戏
- 视觉大模型预测实验
- 懒人聊天网站
- 千与千寻 桃源世界
- 个人叙事与历史叙事
"""

        quality = module.organizer_output_quality(body, snapshot)

        self.assertFalse(quality["accepted"])
        self.assertIn("insufficient_contextual_synthesis", quality["reasons"])
        self.assertIn("raw_list_dominance", quality["reasons"])

    def test_organizer_quality_accepts_contextual_full_memo(self):
        module = load_wechat_career_daily_agent()
        snapshot = """- memo: Pi 5 墨水屏 录音 RAG 词库
- web_clip: Nature 光计算维度
- inbox: 竹书纪年 西京杂记 孔子家语
- request: 千与千寻 桃源世界
- memo: 讯飞声卡 焊台 LED灯珠 锡丝 磁铁
- idea: 树莓派本地语言学习卡
- writing: 建立简单写作习惯
- project: 历史博弈游戏
"""
        body = """# 每日整理

## 今天的脉络

今天的信息并不是八件互不相关的碎片。Pi 5、墨水屏、录音与 RAG 词库共同指向一个可以落地的本地语言学习卡，而不是单纯的采购清单。当前最值得保留的是它们之间已经形成了输入、检索和显示的完整链条。

Nature 光计算维度和视觉大模型预测实验属于另一条技术探索线。它们暂时不应被硬接成一个结论，但可以作为同一个问题的两种观察方式：前者关注光学计算表示，后者关注视觉表示怎样进入预测模型。

阅读与写作材料也在汇聚。竹书纪年、西京杂记、孔子家语提供历史材料，建立简单写作习惯则提供把阅读变成持续输出的方法。千与千寻式桃源世界可以成为一次具体的故事实验，而不是继续停留在主题词。

香港取回物品中的讯飞声卡、焊台、LED 灯珠、锡丝和磁铁仍然只是物流事项。它们支持后续制作，但目前没有证据表明它们本身改变长期方向，因此应和项目判断分开。

## 完整整理

### 当前项目
- **树莓派本地语言学习卡**：Pi 5、墨水屏、录音和 RAG 词库组成第一版边界。
- **视觉大模型预测实验**：保留为研究问题，先明确输入、预测目标和评价方法。
- **历史博弈游戏**：仍是独立创作方向，需要一个最小可玩的历史场景。

### 阅读与写作
- **光学**：继续读 Nature 光计算维度，并记录可验证的技术含义。
- **古籍**：竹书纪年、西京杂记、孔子家语归为史料阅读线。
- **故事**：把千与千寻桃源世界写成一个有人物行动和冲突的短场景。
- **习惯**：建立简单写作习惯只承担持续记录，不夸大为商业路线。

### 物品
- 香港取回：讯飞声卡、焊台、LED 灯珠、锡丝、磁铁。

## 未决问题

语言学习卡最需要先确认的是离线模型能否在 Pi 5 上达到可接受响应速度，以及录音是否是首版必要输入。光计算文章与当前硬件项目是否真的有关，也需要通过阅读原文而不是标题联想来判断。

## 下一步
- [ ] 写出语言学习卡的一页规格，区分首版必需与以后扩展。
- [ ] 阅读 Nature 原文并记录三个可验证主张。
- [ ] 把桃源世界写成一个 300 字场景。
"""

        quality = module.organizer_output_quality(body, snapshot)

        self.assertTrue(quality["accepted"], quality)
        self.assertGreaterEqual(quality["prose_paragraphs"], 4)
        self.assertLess(quality["bullet_character_ratio"], 0.82)

    def test_organizer_quality_rejects_raw_evidence_appendix_and_media_metadata(self):
        module = load_wechat_career_daily_agent()
        snapshot = "\n".join(f"- memo: evidence item {index} Pi 5" for index in range(12))
        body = """# 每日整理

## 今日脉络

这些记录共同指向一个本地学习工具，而不是十二条互不相关的采购事项。Pi 5 是算力底座，显示、输入与词库仍要按首版需求取舍。

当前变化是想法已经从设备名称进入系统边界。下一步需要先明确首版任务，再决定硬件，而不是继续堆叠部件。

长期记录说明这个项目同时连接语言学习和本地计算，但还没有证据证明它已经形成产品，因此这里保留不确定性。

物料记录仍然只是物流依据。它们不应被解释为人生方向，也不自动成为当天待办。

## 完整整理
- Pi 5：候选算力底座。
- 本地词库：候选内容层。
- 显示与录音：待确认首版是否必需。
- 产品边界：尚未确定。
- 成本：需要验证。
- 离线响应：需要验证。

## 未决问题
首版到底解决查词、跟读还是长期复习，目前还没有决定。

## 下一步
- [ ] 写一页首版规格。

## 证据逐条转述（按来源顺序）
1. 微信语音证据：时长 32.5 秒、58,058 字节。
2. evidence item 1 Pi 5。
3. evidence item 2 Pi 5。
4. evidence item 3 Pi 5。
5. evidence item 4 Pi 5。
6. evidence item 5 Pi 5。
"""

        quality = module.organizer_output_quality(body, snapshot)

        self.assertFalse(quality["accepted"])
        self.assertIn("source_by_source_evidence_dump", quality["reasons"])
        self.assertIn("private_media_metadata_exposed", quality["reasons"])

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
            module.organizer_output_quality = lambda *_args, **_kwargs: {
                "accepted": True,
                "reasons": [],
            }

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
            module.send_file = lambda path, chat, targets, **_kwargs: sent_files.append(
                (path, chat, targets)
            )
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

    def test_organizer_repairs_low_quality_output_in_same_session_before_render(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module.ROOT = root
            module.PRIVATE = root / ".private"
            module.OUTPUT = root / "output"
            module.life_memo_snapshot = lambda *_args, **_kwargs: "- memo: Pi 5 墨水屏"
            module.build_history_context = lambda *_args, **_kwargs: {
                "snapshot": "historical context",
                "manifest": {"represented_messages": 10},
            }
            module.select_agent_backend = lambda _config: "aginti"
            module.agent_context_model = lambda *_args, **_kwargs: "localllm-fast"
            calls = []

            def fake_agent(prompt, **kwargs):
                calls.append((prompt, kwargs))
                message = (
                    '{"response":"generic advice"}'
                    if len(calls) == 1
                    else "# 今日整理\n\n## 修订\n- [ ] 复核 Pi 5 墨水屏方案"
                )
                return {
                    "ok": True,
                    "message": message,
                    "backend": "aginti",
                    "provider": "deepseek",
                    "thread_id": "same-organizer-thread",
                    "resumed": len(calls) > 1,
                }

            module.run_agent_session = fake_agent
            module.organizer_output_quality = lambda body, _snapshot, **_kwargs: {
                "accepted": "复核 Pi 5" in body,
                "reasons": [] if "复核 Pi 5" in body else ["too_short_for_evidence"],
                "characters": len(body),
                "headings": body.count("#"),
                "bullets": body.count("- "),
                "grounded_items": int("Pi 5" in body),
                "minimum_characters": 50,
                "minimum_headings": 2,
                "minimum_bullets": 1,
                "missing_examples": ["Pi 5 墨水屏"],
            }

            def fake_render(source, output):
                markdown = source.read_text(encoding="utf-8")
                self.assertIn("复核 Pi 5", markdown)
                self.assertNotIn('"response"', markdown)
                output.write_bytes(b"%PDF repaired")
                return output

            module.render_interactive_organizer_pdf = fake_render
            args = argparse.Namespace(
                organize_chat="MEMO写作—外语—挣钱",
                memory_db=root / "memory.sqlite",
                model="gpt-test",
                reasoning_effort="medium",
                timeout_seconds=30,
                send=False,
                send_targets=root / "targets.json",
            )

            payload = module.run_organizer(args, force=True)

        self.assertTrue(payload["ok"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1]["role"], "daily_organizer")
        self.assertEqual(calls[1][1]["role"], "daily_organizer")
        self.assertEqual(calls[0][1]["chat_name"], calls[1][1]["chat_name"])

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
                    "quality": {"accepted": True},
                },
            )
            module.run_agent_session = lambda *_args, **_kwargs: self.fail("agent must not rerun")
            sent = []
            module.send_file = lambda path, chat, targets, **_kwargs: sent.append(
                (path, chat)
            )
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

    def test_generated_only_organizer_can_be_reviewed_then_sent_without_rerun(self):
        module = load_wechat_career_daily_agent()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module.ROOT = root
            module.PRIVATE = root / ".private"
            module.OUTPUT = root / "output"
            module.life_memo_snapshot = lambda *_args, **_kwargs: "- memo: one exact item"
            module.build_history_context = lambda *_args, **_kwargs: {
                "snapshot": "historical context",
                "manifest": {"represented_messages": 10},
            }
            module.select_agent_backend = lambda _config: "aginti"
            module.agent_context_model = lambda *_args, **_kwargs: "localllm-fast"
            module.organizer_output_quality = lambda *_args, **_kwargs: {
                "accepted": True,
                "reasons": [],
            }
            agent_calls = []
            module.run_agent_session = lambda *_args, **_kwargs: (
                agent_calls.append(True)
                or {
                    "ok": True,
                    "message": "# 今日整理\n\n## 脉络\n\n这是一段完整解释。\n\n## 行动\n- [ ] 处理事项",
                    "backend": "aginti",
                    "thread_id": "organizer-thread",
                }
            )
            module.render_interactive_organizer_pdf = lambda _source, output: (
                output.parent.mkdir(parents=True, exist_ok=True)
                or output.write_bytes(b"%PDF reviewable")
                or output
            )
            sent = []
            module.send_file = lambda path, chat, _targets, **_kwargs: sent.append(
                (path, chat)
            )
            common = {
                "organize_chat": "MEMO写作—外语—挣钱",
                "memory_db": root / "memory.sqlite",
                "model": "gpt-test",
                "reasoning_effort": "medium",
                "timeout_seconds": 30,
                "send_targets": root / "targets.json",
            }

            generated = module.run_organizer(
                argparse.Namespace(**common, send=False),
                force=True,
            )
            delivered = module.run_organizer(
                argparse.Namespace(**common, send=True),
            )

        self.assertEqual(generated["status"], "generated")
        self.assertEqual(delivered["status"], "delivered")
        self.assertEqual(len(agent_calls), 1)
        self.assertEqual(len(sent), 1)

    def test_organizer_delivery_uses_stable_android_component_scope(self):
        module = load_wechat_career_daily_agent()
        captured = {}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "2026-08-23-recent-items.zh.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            module.send_file = lambda path, chat, targets, **kwargs: captured.update(
                {
                    "path": path,
                    "chat": chat,
                    "targets": targets,
                    "task": kwargs.get("task"),
                }
            )
            args = argparse.Namespace(send_targets=root / "targets.json")

            status = module.send_organizer_pdf(
                args,
                pdf,
                "MEMO写作—外语—挣钱",
            )

        expected_id = "daily-organizer-2026-08-23-v3"
        self.assertTrue(status["complete"])
        self.assertEqual(status["delivery_task_id"], expected_id)
        self.assertEqual(captured["task"], {"id": expected_id})
        self.assertEqual(captured["path"], pdf)
        self.assertEqual(captured["chat"], "MEMO写作—外语—挣钱")

    def test_organizer_delivery_task_id_rejects_ambiguous_filename(self):
        module = load_wechat_career_daily_agent()

        with self.assertRaisesRegex(ValueError, "Unexpected organizer PDF name"):
            module.organizer_delivery_task_id(Path("recent-items.pdf"))

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

    def test_organizer_markdown_compacts_bullets_and_omits_duplicate_h1(self):
        module = load_wechat_career_daily_agent()

        body, _count = module.organizer_markdown_to_latex(
            """# 每日整理

## 完整整理
- **设备**：Pi 5
- **文章**：Nature
"""
        )

        self.assertNotIn("每日整理", body)
        self.assertEqual(body.count(r"\begin{itemize}"), 1)
        self.assertEqual(body.count(r"\end{itemize}"), 1)
        self.assertIn(r"\textbf{设备}", body)
        self.assertIn(r"$\rightarrow$", module.markdown_inline_to_latex("A → B"))

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
