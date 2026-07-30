from __future__ import annotations

import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / "scripts"
    / "wechat_message_shards.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "wechat_message_shards_for_tests",
        SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatMessageShardTests(unittest.TestCase):
    def test_paths_are_numeric_sorted_filtered_and_table_bounded(self) -> None:
        shards = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name, table in (
                ("message_10.db", "Msg_target"),
                ("message_2.db", "Msg_target"),
                ("message_1.db", "Msg_other"),
            ):
                with sqlite3.connect(directory / name) as conn:
                    conn.execute(f"CREATE TABLE {table} (local_id INTEGER)")
            (directory / "message_latest.db").write_bytes(b"not-a-db")

            paths = shards.list_message_db_paths(
                directory,
                table="Msg_target",
            )
            selected = shards.list_message_db_paths(
                directory,
                names={"message_10.db", "../message_2.db"},
                table="Msg_target",
                newest_first=True,
            )

        self.assertEqual([path.name for path in paths], ["message_2.db", "message_10.db"])
        self.assertEqual([path.name for path in selected], ["message_10.db"])

    def test_message_ref_rejects_invalid_or_nonpositive_identity(self) -> None:
        shards = load_module()
        self.assertEqual(
            shards.parse_message_ref("message_12.db:7"),
            ("message_12.db", 7),
        )
        for value in ("message.db:7", "message_1.db:0", "../message_1.db:7"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    shards.parse_message_ref(value)


if __name__ == "__main__":
    unittest.main()
