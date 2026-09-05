from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts"
sys.path.insert(0, str(SCRIPTS))
import wechat_native_text_delivery as delivery


class NativeTextDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name)
        self.target = {"name": "Shares", "query": "Shares"}
        (self.private / "shares-direct-chatops.local.json").write_text(json.dumps({
            "chat_name": "Shares", "send_target": self.target,
            "message_table": "Msg_abcd", "self_wxid": "self_sender",
        }))
        self.database = self.private / "wechat_decrypt/decrypted/message/message_1.db"
        self.database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.database)) as conn:
            conn.executescript('''
                CREATE TABLE Name2Id (user_name TEXT);
                INSERT INTO Name2Id VALUES ('self_sender'), ('peer_sender');
                CREATE TABLE Msg_abcd (local_id INTEGER, server_id INTEGER, local_type INTEGER,
                    real_sender_id INTEGER, create_time INTEGER, status INTEGER, message_content TEXT,
                    compress_content BLOB, WCDB_CT_message_content INTEGER);
                CREATE TABLE Msg_dcba AS SELECT * FROM Msg_abcd;
            ''')

    def insert(self, receipt, *, text="reply", sender=1, status=2, server_id=100,
               table="Msg_abcd", timestamp=None, local_id=1):
        with closing(sqlite3.connect(self.database)) as conn:
            conn.execute(f"INSERT INTO {table} VALUES (?, ?, 1, ?, ?, ?, ?, NULL, 0)",
                         (local_id, server_id, sender, receipt["started_at"] if timestamp is None else timestamp,
                          status, text))
            conn.commit()

    def test_exact_self_native_echo_only(self):
        receipt = delivery.prepare_receipt(self.target, self.private)
        self.insert(receipt, text="reply", sender=2, local_id=1)
        self.insert(receipt, text="reply", table="Msg_dcba", local_id=2)
        self.insert(receipt, text="different reply", local_id=3)
        self.insert(receipt, text="reply", status=1, local_id=4)
        self.insert(receipt, text="reply", server_id=0, local_id=5)
        self.insert(receipt, text="reply", timestamp=receipt["started_at"] - 1, local_id=6)
        self.assertIsNone(delivery.find_native_receipt(receipt, "reply", self.private))
        self.insert(receipt, text="self_sender:\nreply", local_id=7)
        evidence = delivery.find_native_receipt(receipt, "reply", self.private)
        self.assertEqual(evidence["local_id"], 7)
        self.assertTrue(evidence["verified"])

    def test_previous_identical_reply_cannot_confirm_new_send(self):
        receipt = delivery.prepare_receipt(self.target, self.private)
        self.insert(receipt)
        receipt = delivery.prepare_receipt(self.target, self.private)
        self.assertIsNone(delivery.find_native_receipt(receipt, "reply", self.private))

    def test_preserves_multiline_heading_and_unicode(self):
        receipt = delivery.prepare_receipt(self.target, self.private)
        text = "Summary:\n研究室（けんきゅうしつ）"
        self.insert(receipt, text=text)
        self.assertIsNotNone(delivery.find_native_receipt(receipt, text.replace("\n", "\r\n"), self.private))

    def test_missing_and_ambiguous_chat_fail_before_send(self):
        with self.assertRaisesRegex(RuntimeError, "exact-chat receipt binding unavailable"):
            delivery.prepare_receipt({"name": "Other"}, self.private)
        (self.private / "other-direct-chatops.local.json").write_text(json.dumps({
            "chat_name": "Shares", "message_table": "Msg_dcba", "self_wxid": "self_sender",
        }))
        with self.assertRaisesRegex(RuntimeError, "exact-chat receipt binding unavailable"):
            delivery.prepare_receipt(self.target, self.private)

    def test_pending_receipt_is_private_and_stable_across_retries(self):
        receipt = delivery.prepare_receipt(self.target, self.private)
        path = delivery.pending_receipt_path(self.target, "reply", self.private)
        delivery.retain_pending_receipt(path, receipt)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text()), receipt)
        self.assertEqual(path, delivery.pending_receipt_path(self.target, "reply", self.private))
        self.assertNotEqual(path, delivery.pending_receipt_path({"name": "Other"}, "reply", self.private))

    def test_zero_timeout_wait_does_not_send_or_write_history(self):
        receipt = delivery.prepare_receipt(self.target, self.private)
        self.assertIsNone(delivery.wait_native_receipt(receipt, "reply", timeout=0, private=self.private))
        self.insert(receipt)
        self.assertIsNotNone(delivery.wait_native_receipt(receipt, "reply", timeout=0, private=self.private))


if __name__ == "__main__":
    unittest.main()
