from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_member_knowledge.py"


def load_module():
    spec = importlib.util.spec_from_file_location("wecom_member_knowledge_for_tests", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeComMemberKnowledgeTests(unittest.TestCase):
    def test_member_context_infers_repeated_pdf_report_preference_without_leaking_messages(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "knowledge.sqlite"
            archive = root / "archive"
            report_a = root / "first_research_report.pdf"
            report_b = root / "second_research_report.pdf"
            report_a.write_bytes(b"%PDF-1.4\nfirst")
            report_b.write_bytes(b"%PDF-1.4\nsecond")
            event = {
                "message_id": "pdf-request",
                "sender_userid": "member-a",
                "sender_display": "Member A",
                "sender_identity_confidence": "transport_userid",
                "create_time": 100,
                "msgtype": "text",
                "transport_channel": "wecom_bot_websocket",
            }
            recorded = module.record_incoming_event(
                db,
                event,
                "wecom:test:group:one",
                "生成pdf",
                archive_root=archive,
            )
            for index, report in enumerate((report_a, report_b), start=1):
                module.record_member_file(
                    db,
                    member_key=recorded["member_key"],
                    chat="wecom:test:group:one",
                    path=report,
                    source_type="worker_result",
                    source_id=f"source-{index}",
                    source_task_id=f"task-{index}",
                    archive_root=archive,
                )
            context = module.member_context(
                db,
                "wecom:test:group:one",
                recorded["member_key"],
            )

        preference = context["preferences"]["pdf_reports"]
        self.assertTrue(preference["preferred_for_substantial_research"])
        self.assertEqual(preference["explicit_request_count"], 1)
        self.assertEqual(preference["completed_report_count"], 2)
        self.assertNotIn("生成pdf", json.dumps(context, ensure_ascii=False))

    def test_member_events_knowledge_and_files_remain_isolated(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "knowledge.sqlite"
            archive = root / "archive"
            source = root / "paper.pdf"
            source.write_bytes(b"%PDF-1.4\nmember-a-paper")
            event_a = {
                "message_id": "message-a",
                "sender_userid": "member-a",
                "sender_display": "Member A",
                "sender_identity_confidence": "transport_userid",
                "create_time": 100,
                "msgtype": "file",
                "transport_channel": "wecom_bot_websocket",
            }
            event_b = {
                "message_id": "message-b",
                "sender_userid": "member-b",
                "sender_display": "Member B",
                "sender_identity_confidence": "transport_userid",
                "create_time": 101,
                "msgtype": "text",
                "transport_channel": "wecom_bot_websocket",
            }
            first = module.record_incoming_event(
                db,
                event_a,
                "wecom:test:group:one",
                "A spatial quality-control loop #idea",
                attachments=[{"path": str(source), "kind": "file"}],
                archive_root=archive,
            )
            second = module.record_incoming_event(
                db,
                event_b,
                "wecom:test:group:one",
                "Mechanical state may predict fate #insight",
                archive_root=archive,
            )
            source.write_bytes(b"changed-after-intake")
            context_a = module.member_context(db, "wecom:test:group:one", first["member_key"])
            context_b = module.member_context(db, "wecom:test:group:one", second["member_key"])
            status = module.knowledge_status(db)
            archived_file_exists = Path(context_a["files"][0]["path"]).is_file()
            archived_file_content = Path(context_a["files"][0]["path"]).read_bytes()

        self.assertEqual(status["member_count"], 2)
        self.assertEqual(first["files"], 1)
        self.assertEqual(context_a["knowledge"][0]["kind"], "idea")
        self.assertNotIn("Mechanical state", json.dumps(context_a, ensure_ascii=False))
        self.assertEqual(context_b["knowledge"][0]["kind"], "insight")
        self.assertTrue(archived_file_exists)
        self.assertEqual(archived_file_content, b"%PDF-1.4\nmember-a-paper")

    def test_completed_daily_task_indexes_reports_papers_and_agent_insights_once(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "knowledge.sqlite"
            queue = root / "queue.jsonl"
            archive = root / "archive"
            report = root / "organoid-briefing.pdf"
            paper = root / "Liao_2026_Nature_Communications.pdf"
            report.write_bytes(b"%PDF-1.4\nreport")
            paper.write_bytes(b"%PDF-1.4\npaper")
            task = {
                "id": "daily-1",
                "chat": "wecom:test:group:one",
                "request": "Prepare the daily organoid briefing",
                "status": "done",
                "source": {"server_id": "daily:1", "sender": "labcanvas-daily-scheduler"},
                "daily_research": {"member_key": "member-key-a", "topics": ["organoid quality control"]},
                "result": {
                    "message": "The strongest opportunity is programmable quality control.",
                    "files": [str(report), str(paper)],
                    "data": {
                        "knowledge_items": [
                            {
                                "kind": "insight",
                                "title": "Programmable QC",
                                "content": "Link material state to a measurable quality vector.",
                                "tags": ["organoid", "qc"],
                            }
                        ]
                    },
                },
            }
            queue.write_text(json.dumps(task) + "\n", encoding="utf-8")
            first = module.sync_once(db, root / "missing-history.sqlite", queue, archive)
            second = module.sync_once(db, root / "missing-history.sqlite", queue, archive)
            search = module.search_knowledge(
                db,
                query="",
                member_key="member-key-a",
                chat="",
                kind="",
                limit=20,
            )
            archived_files_exist = all(Path(item["archive_path"]).is_file() for item in search["files"])

        self.assertEqual(first["indexed_tasks"], 1)
        self.assertEqual(second["indexed_tasks"], 0)
        self.assertEqual({item["category"] for item in search["files"]}, {"paper", "report"})
        self.assertEqual({item["kind"] for item in search["items"]}, {"agent_summary", "insight"})
        self.assertTrue(archived_files_exist)

    def test_nonterminal_task_result_waits_for_completion(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "knowledge.sqlite"
            queue = root / "queue.jsonl"
            task = {
                "id": "task-1",
                "chat": "wecom:test:group:one",
                "status": "in_progress",
                "source": {"member_key": "member-key-a", "server_id": "source-1"},
                "result": {"message": "Progress only", "files": []},
            }
            queue.write_text(json.dumps(task) + "\n", encoding="utf-8")
            waiting = module.sync_once(db, root / "missing.sqlite", queue, root / "archive")
            task["status"] = "done"
            task["result"]["message"] = "Final conclusion"
            queue.write_text(json.dumps(task) + "\n", encoding="utf-8")
            completed = module.sync_once(db, root / "missing.sqlite", queue, root / "archive")
            search = module.search_knowledge(
                db,
                query="",
                member_key="member-key-a",
                chat="wecom:test:group:one",
                kind="agent_summary",
                limit=20,
            )

        self.assertEqual(waiting["indexed_tasks"], 0)
        self.assertEqual(completed["indexed_tasks"], 1)
        self.assertEqual([item["content"] for item in search["items"]], ["Final conclusion"])

    def test_history_backfill_is_idempotent_and_gui_duplicate_aware(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            db = root / "knowledge.sqlite"
            with sqlite3.connect(history) as conn:
                conn.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, message_id TEXT, chat TEXT, direction TEXT, sender TEXT, body TEXT, create_time INTEGER, created_at TEXT)"
                )
                conn.executemany(
                    "INSERT INTO messages(message_id, chat, direction, sender, body, create_time, created_at) VALUES (?, ?, 'inbound', ?, ?, ?, ?)",
                    [
                        ("one", "wecom:external-gui:group:test", "ocr-a", "same bubble", 100, "2026-07-20T06:00:00"),
                        ("two", "wecom:external-gui:group:test", "ocr-b", "same bubble", 101, "2026-07-20T06:00:01"),
                    ],
                )
            first = module.backfill_history(db, history)
            second = module.backfill_history(db, history)
            status = module.knowledge_status(db)

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(sum(item["event_count"] for item in status["members"]), 1)

    def test_live_ingest_then_history_backfill_does_not_duplicate_tagged_memory(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.sqlite"
            db = root / "knowledge.sqlite"
            event = {
                "message_id": "same-message",
                "sender_userid": "member-a",
                "sender_display": "Member A",
                "create_time": 100,
                "msgtype": "text",
            }
            module.record_incoming_event(
                db,
                event,
                "wecom:test:group:one",
                "Mechanical state is a useful latent variable #idea",
            )
            with sqlite3.connect(history) as conn:
                conn.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, message_id TEXT, chat TEXT, direction TEXT, sender TEXT, body TEXT, create_time INTEGER, created_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO messages(message_id, chat, direction, sender, body, create_time, created_at) VALUES (?, ?, 'inbound', ?, ?, ?, ?)",
                    (
                        "same-message",
                        "wecom:test:group:one",
                        "member-a",
                        "Mechanical state is a useful latent variable #idea",
                        100,
                        "2026-07-20T06:00:00",
                    ),
                )
            first = module.backfill_history(db, history)
            second = module.backfill_history(db, history)
            search = module.search_knowledge(
                db,
                query="Mechanical state",
                member_key=module.short_hash("member-a"),
                chat="wecom:test:group:one",
                kind="idea",
                limit=20,
            )

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(len(search["items"]), 1)

    def test_export_writes_private_markdown_and_json(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "knowledge.sqlite"
            module.record_knowledge_item(
                db,
                member_key="member-a",
                chat="chat-a",
                item={"kind": "intuition", "title": "Boundary mechanics", "content": "Boundary mechanics controls fate."},
                source_type="test",
                source_id="source-a",
            )
            payload = module.export_member(db, "member-a", root / "export")
            json_exists = Path(payload["json"]).is_file()
            markdown = Path(payload["markdown"]).read_text(encoding="utf-8")

        self.assertTrue(json_exists)
        self.assertIn("Boundary mechanics", markdown)


if __name__ == "__main__":
    unittest.main()
