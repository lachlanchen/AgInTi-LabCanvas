from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "agentic_tools" / "wechat_gui_agent" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import wechat_memory  # noqa: E402


class WeChatMemoryTests(unittest.TestCase):
    def row(self, local_id: int, text: str, *, sender: str = "friend") -> dict[str, object]:
        return {
            "local_id": local_id,
            "server_id": f"s-{local_id}",
            "sender": sender,
            "sender_display": "Friend",
            "local_type": 1,
            "create_time": 1_700_000_000 + local_id,
            "content": text,
        }

    def config(self, db_path: Path) -> dict[str, object]:
        return {
            "chat_name": "写作 外语 挣钱",
            "self_wxid": "self",
            "organizer": {
                "enabled": True,
                "db_path": str(db_path),
                "capture_unclassified": True,
                "default_tags": ["writing", "foreign-language", "money"],
            },
        }

    def test_organize_messages_creates_structured_items_and_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.sqlite"
            rows = [
                self.row(1, "记一下：明天 9点 buy milk and eggs"),
                self.row(2, "beat board idea for writing language money project"),
            ]

            result = wechat_memory.organize_messages(self.config(db_path), rows)
            second = wechat_memory.organize_messages(self.config(db_path), rows)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["inserted_sources"], 2)
            self.assertGreaterEqual(result["items"], 4)
            self.assertEqual(second["inserted_sources"], 0)
            self.assertEqual(second["items"], 0)

            with sqlite3.connect(db_path) as conn:
                categories = {row[0] for row in conn.execute("SELECT DISTINCT category FROM memory_items")}
                tags = {row[0] for row in conn.execute("SELECT name FROM tags")}

            self.assertIn("memo", categories)
            self.assertIn("calendar", categories)
            self.assertIn("grocery", categories)
            self.assertIn("beat_board", categories)
            self.assertIn("foreign-language", tags)
            self.assertIn("money", tags)

    def test_web_clip_messages_are_tagged_for_read_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.sqlite"
            config = {
                "chat_name": "鏈接",
                "self_wxid": "self",
                "organizer": {
                    "enabled": True,
                    "db_path": str(db_path),
                    "capture_unclassified": True,
                    "default_tags": ["web-clip-inbox"],
                },
            }

            result = wechat_memory.organize_messages(config, [self.row(1, "https://example.com/article?id=1")])

            self.assertEqual(result["inserted_sources"], 1)
            with sqlite3.connect(db_path) as conn:
                categories = {row[0] for row in conn.execute("SELECT DISTINCT category FROM memory_items")}
                tags = {row[0] for row in conn.execute("SELECT name FROM tags")}
            self.assertIn("web_clip", categories)
            self.assertIn("read-later", tags)

    def test_wechat_link_cards_are_web_clips_not_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.sqlite"
            config = {
                "chat_name": "鏈接",
                "self_wxid": "self",
                "organizer": {
                    "enabled": True,
                    "db_path": str(db_path),
                    "capture_unclassified": True,
                    "default_tags": ["web-clip-inbox"],
                },
            }
            row = self.row(1, '<?xml version="1.0"?><msg><appmsg><title>Paper</title><url>https://example.com</url></appmsg></msg>')

            wechat_memory.organize_messages(config, [row], kind_fn=lambda _row: "file/link")

            with sqlite3.connect(db_path) as conn:
                categories = {row[0] for row in conn.execute("SELECT DISTINCT category FROM memory_items")}
                tags = {row[0] for row in conn.execute("SELECT name FROM tags")}
            self.assertIn("web_clip", categories)
            self.assertIn("attachment", categories)
            self.assertNotIn("question", tags)

    def test_summary_reports_counts_by_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.sqlite"
            wechat_memory.organize_messages(self.config(db_path), [self.row(1, "todo write article")])

            summary = wechat_memory.database_summary(db_path, chat_name="写作 外语 挣钱")

            self.assertEqual(summary["message_count"], 1)
            self.assertGreaterEqual(summary["item_count"], 1)
            self.assertIn("todo", summary["by_category"])


if __name__ == "__main__":
    unittest.main()
