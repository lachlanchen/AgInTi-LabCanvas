from __future__ import annotations

import copy
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agentic_tools/wechat_gui_agent/scripts"))
import wechat_direct_chatops as direct
import wechat_task_worker as worker


TABLE = "Msg_" + "a" * 32
RECALL_XML = '<sysmsg type="revokemsg"><revokemsg><content>recalled</content></revokemsg></sysmsg>'


class SourceRecallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = self.root / "message_999998.db"
        self.queue = self.root / "queue.jsonl"
        self.task = {
            "id": "source-one", "chat": "Shares", "status": "in_progress",
            "worker_id": "test-worker", "execution_generation": 1,
            "queue_path": str(self.queue),
            "source": {"chat": "Shares", "message_db": self.db.name,
                       "message_table": TABLE, "local_id": 7, "server_id": "123"},
        }
        with sqlite3.connect(self.db) as conn:
            conn.execute(f"CREATE TABLE {TABLE} (local_id INTEGER,server_id TEXT,"
                         "local_type INTEGER,message_content TEXT,compress_content BLOB,"
                         "WCDB_CT_message_content INTEGER)")
            conn.execute(f"INSERT INTO {TABLE} VALUES(7,'123',10000,?,NULL,0)", (RECALL_XML,))
        patched = mock.patch.object(direct, "message_db_path", return_value=self.db)
        patched.start()
        self.addCleanup(patched.stop)

    def test_detects_native_in_place_recall_with_exact_identity(self):
        evidence = worker.recalled_source_evidence(self.task)
        self.assertEqual(evidence["server_id"], "123")
        self.assertEqual(evidence["local_id"], 7)

    def test_mismatched_chat_server_or_table_never_cancels(self):
        for key, value in (("chat", "Other"), ("server_id", "124"),
                           ("local_id", 8), ("message_table", "Msg_" + "b" * 32)):
            with self.subTest(key=key):
                task = copy.deepcopy(self.task)
                task["source"][key] = value
                self.assertIsNone(worker.recalled_source_evidence(task))

    def test_ordinary_text_and_non_recall_system_events_are_not_withdrawals(self):
        for kind, content in ((1, RECALL_XML), (10000, "I recalled that message"),
                              (10000, '<sysmsg type="other"><revokemsg/></sysmsg>')):
            with self.subTest(kind=kind, content=content), sqlite3.connect(self.db) as conn:
                conn.execute(f"UPDATE {TABLE} SET local_type=?,message_content=?", (kind, content))
            self.assertIsNone(worker.recalled_source_evidence(self.task))

    def test_unavailable_database_does_not_invent_recall_or_create_database(self):
        self.db.unlink()
        self.assertIsNone(worker.recalled_source_evidence(self.task))
        self.assertFalse(self.db.exists())

    def test_cancellation_invalidates_late_worker_without_touching_next_card(self):
        other = {**self.task, "id": "next-card", "status": "pending",
                 "source": {**self.task["source"], "local_id": 8, "server_id": "124"}}
        worker.write_tasks(self.queue, [self.task, other])
        self.assertTrue(worker.suppress_recalled_source(self.task))
        current = worker.find_task(self.queue, self.task["id"])
        self.assertEqual(current["status"], "canceled")
        self.assertEqual(current["execution_generation"], 2)
        self.assertTrue(current["result"]["no_reply"])
        self.assertFalse(worker.task_claim_is_current(self.queue, self.task))
        self.assertFalse(worker.rewrite_task(self.queue, {**self.task, "status": "done"}))
        self.assertEqual(worker.find_task(self.queue, other["id"]), other)

    def test_completed_delivery_is_preserved_but_cannot_be_resent(self):
        task = {**self.task, "status": "done", "sent_file_paths": ["original.mp4"]}
        worker.write_tasks(self.queue, [task])
        self.assertTrue(worker.suppress_recalled_source(task))
        self.assertEqual(worker.find_task(self.queue, task["id"]), task)
        with mock.patch.object(worker, "send_result_once") as send, \
                mock.patch.object(worker, "prepare_long_response_delivery") as prepare:
            errors = worker.send_result_with_retries(
                {"message": "old answer", "files": ["original.mp4"]},
                "Shares", self.root / "targets.json", task=task,
            )
        self.assertEqual(errors, ["source_message_recalled"])
        send.assert_not_called()
        prepare.assert_not_called()

    def test_queued_recalled_source_never_starts_backend(self):
        worker.write_tasks(self.queue, [self.task])
        with mock.patch.object(worker, "reconcile_passive_video_publish_followups", return_value=0), \
                mock.patch.object(worker, "reconcile_numbered_message_coverage", return_value=0), \
                mock.patch.object(worker, "merge_existing_pending_interruptions", return_value=0), \
                mock.patch.object(worker, "adopt_active_generated_video_tasks", return_value=None), \
                mock.patch.object(worker, "claim_next_pending", return_value=dict(self.task)), \
                mock.patch.object(worker, "log_worker_event"), \
                mock.patch.object(worker, "run_worker_codex") as backend:
            self.assertTrue(worker.process_one(self.queue, "Shares", send=True))
        backend.assert_not_called()
        self.assertEqual(worker.find_task(self.queue, self.task["id"])["status"], "canceled")

    def test_recall_between_text_parts_stops_remaining_delivery(self):
        with mock.patch.object(worker, "split_chat_message", return_value=["first", "second"]), \
                mock.patch.object(worker, "suppress_recalled_source", side_effect=[False, True]), \
                mock.patch.object(worker, "persist_task_progress"), \
                mock.patch.object(worker, "send_message") as send:
            with self.assertRaises(worker.SourceMessageRecalled):
                worker.send_result_text_parts(
                    "text", field="message", task=self.task, target_chat="Shares",
                    send_targets=self.root / "targets.json", target={},
                )
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "first")

    def test_recall_during_delivery_is_not_retried_or_sent_to_fallback(self):
        with mock.patch.object(worker, "suppress_recalled_source", return_value=False), \
                mock.patch.object(worker, "enforce_worker_result_response_policy"), \
                mock.patch.object(worker, "prepare_long_response_delivery"), \
                mock.patch.object(worker, "send_result_once", side_effect=worker.SourceMessageRecalled) as send, \
                mock.patch.object(worker, "android_text_fallback_allowed") as fallback:
            errors = worker.send_result_with_retries(
                {"message": "old answer", "files": []}, "Shares",
                self.root / "targets.json", task=self.task,
            )
        self.assertEqual(errors, ["source_message_recalled"])
        send.assert_called_once()
        fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
