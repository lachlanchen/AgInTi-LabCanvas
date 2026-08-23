from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_history_rag.py"


def load_history_rag():
    spec = importlib.util.spec_from_file_location("wechat_history_rag_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatHistoryRagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_history_rag()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "memory.sqlite"
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """
                CREATE TABLE source_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_name TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    sender_display TEXT,
                    body TEXT NOT NULL,
                    create_time INTEGER,
                    observed_at TEXT
                )
                """
            )

    def insert(self, chat: str, body: str, when: datetime, *, direction: str = "outbound") -> None:
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """
                INSERT INTO source_messages(
                    chat_name, direction, sender_display, body, create_time, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chat, direction, "Lachlan", body, int(when.timestamp()), when.isoformat()),
            )

    def test_retrieval_scans_full_history_instead_of_last_n_rows(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.insert(
            "MEMO",
            "我的长期目标是把写作和开源软件结合成可持续事业，并用真实读者验证。",
            start,
        )
        for index in range(300):
            self.insert("MEMO", f"普通近期备忘 {index}", start + timedelta(days=index + 1))

        payload = self.module.build_history_context(
            self.db,
            ["MEMO"],
            "写作 开源 软件 事业 职业 赚钱 读者",
            char_budget=7000,
        )

        self.assertEqual(payload["manifest"]["scanned_messages"], 301)
        self.assertIn("长期目标是把写作和开源软件结合", payload["snapshot"])

    def test_retrieval_preserves_consecutive_message_context(self) -> None:
        when = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        self.insert("MEMO", "我想写一本关于实验工具与人的故事。", when)
        self.insert("MEMO", "第二条补充：主角不是科学家，而是维护设备的人。", when + timedelta(minutes=4))
        self.insert("MEMO", "无关的晚间购物清单。", when + timedelta(hours=8))

        payload = self.module.build_history_context(
            self.db,
            ["MEMO"],
            "写作 故事 实验 工具 主角",
            char_budget=6000,
        )

        self.assertIn("维护设备的人", payload["snapshot"])

    def test_retrieval_isolates_authorized_chats(self) -> None:
        when = datetime(2026, 8, 1, tzinfo=timezone.utc)
        self.insert("MEMO", "公开给职业分析使用的写作计划。", when)
        self.insert("OtherGroup", "PRIVATE_OTHER_GROUP_SENTINEL", when)

        payload = self.module.build_history_context(
            self.db,
            ["MEMO"],
            "职业 写作",
            char_budget=5000,
        )

        self.assertIn("写作计划", payload["snapshot"])
        self.assertNotIn("PRIVATE_OTHER_GROUP_SENTINEL", payload["snapshot"])
        self.assertEqual(payload["manifest"]["authorized_chats"], ["MEMO"])

    def test_retrieval_can_keep_user_authored_history_only(self) -> None:
        when = datetime(2026, 8, 1, tzinfo=timezone.utc)
        self.insert(
            "MEMO",
            "我想把光学仪器和写作结合成长期项目。",
            when,
            direction="inbound",
        )
        self.insert(
            "MEMO",
            "助手建议把它改成通用翻译接单服务。",
            when + timedelta(minutes=1),
            direction="outbound",
        )

        payload = self.module.build_history_context(
            self.db,
            ["MEMO"],
            "光学 写作 长期项目",
            char_budget=5000,
            directions=("inbound",),
        )

        self.assertIn("光学仪器和写作", payload["snapshot"])
        self.assertNotIn("通用翻译接单服务", payload["snapshot"])
        self.assertEqual(payload["manifest"]["scanned_messages"], 1)
        self.assertEqual(payload["manifest"]["authorized_directions"], ["inbound"])

    def test_retrieval_deduplicates_repeated_messages_with_provenance(self) -> None:
        when = datetime(2026, 8, 1, tzinfo=timezone.utc)
        for offset in range(3):
            self.insert("MEMO", "我希望发布 PocketPolyglot。", when + timedelta(minutes=offset))

        payload = self.module.build_history_context(
            self.db,
            ["MEMO"],
            "PocketPolyglot 发布",
            char_budget=5000,
        )

        self.assertEqual(payload["manifest"]["scanned_messages"], 3)
        self.assertEqual(payload["manifest"]["unique_messages"], 1)
        self.assertIn("repeated=3", payload["snapshot"])

    def test_wecom_adapter_scans_complete_exact_group_history(self) -> None:
        db = Path(self.temp.name) / "wecom.sqlite"
        with sqlite3.connect(db) as connection:
            connection.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    chat TEXT,
                    direction TEXT,
                    sender TEXT,
                    sender_display TEXT,
                    body TEXT,
                    create_time INTEGER,
                    created_at TEXT
                )
                """
            )
            rows = [
                (
                    1,
                    "LabAgent",
                    "inbound",
                    "member-a",
                    "Professor Ma",
                    "mechanobiology optical phenotyping",
                    1,
                    "",
                ),
                *[
                    (
                        index,
                        "LabAgent",
                        "inbound",
                        "member-b",
                        "Other",
                        f"recent noise {index}",
                        index,
                        "",
                    )
                    for index in range(2, 302)
                ],
                (
                    302,
                    "OtherGroup",
                    "inbound",
                    "member-x",
                    "Private",
                    "mechanobiology secret",
                    302,
                    "",
                ),
            ]
            connection.executemany(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
            )

        payload = self.module.build_wecom_history_context(
            db,
            ["LabAgent"],
            "mechanobiology phenotyping",
            char_budget=8000,
        )

        self.assertEqual(payload["manifest"]["scanned_messages"], 301)
        self.assertIn("mechanobiology optical phenotyping", payload["snapshot"])
        self.assertNotIn("mechanobiology secret", payload["snapshot"])

    def test_deduplication_keeps_same_text_from_different_senders(self) -> None:
        messages = [
            self.module.HistoryMessage(
                1,
                "LabAgent",
                "inbound",
                "A",
                "same idea",
                datetime.fromtimestamp(1, timezone.utc),
            ),
            self.module.HistoryMessage(
                2,
                "LabAgent",
                "inbound",
                "B",
                "same idea",
                datetime.fromtimestamp(2, timezone.utc),
            ),
        ]

        unique = self.module.deduplicate_history(messages)

        self.assertEqual(len(unique), 2)

    def test_lifetime_compaction_represents_every_row_with_small_budget(self) -> None:
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        for index in range(1000):
            self.insert(
                "MEMO",
                f"lifetime event {index}: project observation and decision trace",
                start + timedelta(hours=index * 12),
            )

        payload = self.module.build_history_context(
            self.db,
            ["MEMO"],
            "unrelated current question",
            char_budget=5000,
            token_budget=2200,
            model="localllm-fast",
        )

        manifest = payload["manifest"]
        self.assertEqual(manifest["scanned_messages"], 1000)
        self.assertEqual(manifest["represented_messages"], 1000)
        self.assertEqual(manifest["coverage_ratio"], 1.0)
        self.assertGreater(manifest["compaction_levels"], 1)
        self.assertLessEqual(len(payload["snapshot"]), 5000)
        self.assertLessEqual(self.module.estimate_tokens(payload["snapshot"]), 2200)
        self.assertIn("Lifetime memory compaction", payload["full_memory"])
        self.assertIn("High-fidelity query excerpts", payload["high_fidelity_excerpts"])

    def test_old_goal_survives_full_memory_when_query_is_unrelated(self) -> None:
        start = datetime(2022, 1, 1, tzinfo=timezone.utc)
        self.insert(
            "MEMO",
            "My long term goal is to combine open-source instruments with careful writing.",
            start,
        )
        for index in range(220):
            self.insert(
                "MEMO",
                f"routine observation {index}",
                start + timedelta(days=index + 1),
            )

        payload = self.module.build_history_context(
            self.db,
            ["MEMO"],
            "grocery list",
            char_budget=6500,
            token_budget=3000,
        )

        self.assertIn("combine open-source instruments", payload["full_memory"])

    def test_model_policy_controls_memory_budget(self) -> None:
        policy = Path(self.temp.name) / "model-policy.json"
        policy.write_text(
            """
            {
              "memory": {
                "context_window_tokens": {
                  "small": 8192,
                  "large": 65536,
                  "default": 4096
                },
                "output_reserve_tokens": 1024,
                "tool_reserve_tokens": 1024,
                "minimum_memory_tokens": 512,
                "maximum_memory_tokens": 20000,
                "role_memory_fraction": {"task": 0.4},
                "full_memory_fraction": 0.7
              }
            }
            """,
            encoding="utf-8",
        )

        small = self.module.resolve_memory_budget(model="small", role="task", policy_path=policy)
        large = self.module.resolve_memory_budget(model="large", role="task", policy_path=policy)

        self.assertLess(small["memory_token_budget"], large["memory_token_budget"])
        self.assertEqual(small["context_window_tokens"], 8192)
        self.assertEqual(large["context_window_tokens"], 65536)

    def test_incremental_cache_reuses_unchanged_segments(self) -> None:
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        for index in range(60):
            self.insert("MEMO", f"append-only memory {index}", start + timedelta(minutes=index))

        first = self.module.build_history_context(
            self.db, ["MEMO"], "memory", char_budget=5000
        )
        second = self.module.build_history_context(
            self.db, ["MEMO"], "memory", char_budget=5000
        )
        self.insert("MEMO", "one new append", start + timedelta(minutes=61))
        third = self.module.build_history_context(
            self.db, ["MEMO"], "memory", char_budget=5000
        )

        self.assertEqual(first["manifest"]["cache_misses"], 2)
        self.assertEqual(second["manifest"]["cache_hits"], 2)
        self.assertEqual(third["manifest"]["cache_hits"], 1)
        self.assertEqual(third["manifest"]["cache_misses"], 1)


if __name__ == "__main__":
    unittest.main()
