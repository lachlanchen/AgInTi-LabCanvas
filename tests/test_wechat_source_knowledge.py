from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"
sys.path.insert(0, str(SCRIPTS))
import wechat_source_knowledge as knowledge


class SourceKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "knowledge.sqlite"
        self.transcript = self.root / "transcript.json"
        self.transcript.write_text(json.dumps({"text": "Optical sensors measure spectra. 光谱分析技术用于材料研究。"}), encoding="utf-8")
        self.task = {"id": "task-1", "chat": "shares", "artifact_dir": str(self.root),
                     "source": {"chat": "shares", "server_id": "source-1", "sender": "member-1"},
                     "preflight": {"shipinhao_media_transcript": {
                         "status": "transcribed", "content_identity_verified": True,
                         "profile": {"title": "Optical sensors"},
                         "transcript_json": str(self.transcript)}}}

    def store(self, **kwargs):
        return knowledge.store_task_knowledge(self.task, db=self.db, allowed_roots=[self.root], **kwargs)

    def test_full_transcript_summary_and_provenance_persist_without_delivery(self):
        result = self.store(result={"message": "A summary about optical sensors."})
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(self.db) as conn:
            rows = conn.execute("SELECT kind,body,source_json FROM source_knowledge").fetchall()
        self.assertIn("光谱分析技术", rows[0][1])
        self.assertEqual(json.loads(rows[0][2])["server_id"], "source-1")
        self.assertEqual(self.store(result={"message": "A summary about optical sensors."})["inserted"], 0)

    def test_retrieval_is_exact_chat_and_transport_scoped(self):
        self.store()
        found = knowledge.knowledge_context(self.task, "optical", db=self.db)
        self.assertEqual(found["retrieved_chunks"], 1)
        other = {**self.task, "chat": "other", "source": {"chat": "other"}}
        self.assertEqual(knowledge.knowledge_context(other, "optical", db=self.db), {})
        other_transport = {**self.task, "transport": "wecom"}
        self.assertEqual(knowledge.knowledge_context(other_transport, "optical", db=self.db), {})
        with self.assertRaises(ValueError):
            knowledge.knowledge_context({**self.task, "chat": "other"}, "optical", db=self.db)

    def test_chinese_search_and_bounded_context(self):
        self.store()
        found = knowledge.knowledge_context(self.task, "请解释之前的光谱分析文章", db=self.db, char_budget=500)
        self.assertEqual(found["retrieved_chunks"], 1)
        self.assertLessEqual(len(found["items"][0]["excerpt"]), 150)

    def test_locked_database_respects_lookup_timeout(self):
        self.store()
        with sqlite3.connect(self.db) as writer:
            writer.execute("BEGIN EXCLUSIVE")
            started = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError):
                knowledge.knowledge_context(self.task, "optical", db=self.db, timeout_seconds=0.05)
            self.assertLess(time.monotonic() - started, 1.0)

    def test_lookup_closes_its_connection_after_reading(self):
        self.store()
        conn = sqlite3.connect(self.db)
        with mock.patch.object(knowledge.sqlite3, "connect", return_value=conn):
            found = knowledge.knowledge_context(self.task, "optical", db=self.db)
        self.assertEqual(found["retrieved_chunks"], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_store_closes_schema_and_write_connections(self):
        connections = []
        connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            conn = connect(*args, **kwargs)
            connections.append(conn)
            return conn

        with mock.patch.object(knowledge.sqlite3, "connect", side_effect=tracked_connect):
            self.assertEqual(self.store()["inserted"], 1)
        self.assertEqual(len(connections), 2)
        for conn in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")

    def test_store_respects_short_database_lock_timeout(self):
        self.store()
        with sqlite3.connect(self.db) as writer:
            writer.execute("BEGIN EXCLUSIVE")
            started = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError):
                self.store(timeout_seconds=0.05)
            self.assertLess(time.monotonic() - started, 1.0)

    def test_failed_or_unverified_card_does_not_become_knowledge(self):
        finder = self.task["preflight"]["shipinhao_media_transcript"]
        finder["status"] = "failed"
        self.assertEqual(self.store(result={"message": "Title-based guesses"})["inserted"], 0)
        finder["status"] = "transcribed"
        finder["content_identity_verified"] = False
        self.assertEqual(self.store()["inserted"], 0)

    def test_article_and_partial_pdf_preserve_evidence_labels(self):
        text = self.root / "source.md"
        text.write_text("Source content", encoding="utf-8")
        self.task["preflight"] = {
            "wechat_source_recovery": {"articles": [{"source_quality": "full_article",
                "markdown_path": str(text), "title": "A source"}]},
            "media_resolution": {"copied": [{"matched_by": "message_id", "document_read": {
                "status": "partial", "text_path": str(text), "text_truncated": True}}]}}
        self.assertEqual(self.store()["inserted"], 2)
        with sqlite3.connect(self.db) as conn:
            statuses = {row[0] for row in conn.execute("SELECT evidence_status FROM source_knowledge")}
        self.assertEqual(statuses, {"full_article", "partial_document"})

    def test_no_arbitrary_model_paths_or_mtime_only_documents(self):
        self.task["preflight"] = {"media_resolution": {"copied": [{
            "matched_by": "mtime", "document_read": {"status": "readable", "text_path": str(self.transcript)}}]}}
        self.assertEqual(self.store(result={"files": [str(self.transcript)]})["inserted"], 0)

    def test_outside_and_symlink_evidence_rejected(self):
        other = self.root / "other"
        other.mkdir()
        link = other / "link.json"
        link.symlink_to(self.transcript)
        with self.assertRaises(ValueError):
            knowledge.read_evidence(str(link), [other])

    def test_failed_backend_does_not_store_its_summary_but_keeps_source(self):
        self.assertEqual(self.store(result={"message": "raw failure", "private_failure": {"kind": "error"}})["inserted"], 1)


if __name__ == "__main__":
    unittest.main()
