import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "agentic_tools/wechat_gui_agent/scripts/wechat_ubuntu_cutover.py"
spec = importlib.util.spec_from_file_location("wechat_ubuntu_cutover", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UbuntuCutoverTests(unittest.TestCase):
    def test_only_consumed_prefix_advances(self):
        self.assertEqual(module.reconcile_cursor([(1, 100), (2, 200), (3, 300)], 0, {"100"}),
                         (1, 1, [2, 3]))

    def test_existing_cursor_never_rewinds(self):
        self.assertEqual(module.reconcile_cursor([(1, 100), (2, 200)], 2, set()), (2, 0, []))

    def test_zero_id_is_not_identity(self):
        self.assertEqual(module.reconcile_cursor([(1, 0)], 0, {"0"}), (0, 0, [1]))

    def test_interleaved_overlap_refuses_to_skip_unknown(self):
        with self.assertRaises(ValueError):
            module.reconcile_cursor([(1, 100), (2, 200)], 0, {"200"})

    def test_all_consumed_rows_do_not_replay(self):
        self.assertEqual(module.reconcile_cursor([(10, 100), (12, 200)], 9, {"100", "200"}),
                         (12, 2, []))

    def test_plan_preserves_sessions_and_other_cursors_and_ignores_fts(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "message_999998.db"
            destination = root / "ubuntu"
            destination.mkdir()
            table = "Msg_" + "a" * 32
            for db, rows in [(source, [(90, 100)]),
                             (destination / "message_1.db", [(1, 100), (2, 200)])]:
                with sqlite3.connect(db) as conn:
                    conn.execute(f'CREATE TABLE "{table}" (local_id INTEGER, server_id INTEGER)')
                    conn.executemany(f'INSERT INTO "{table}" VALUES (?,?)', rows)
            (destination / "message_fts.db").touch()
            state = {"message_db_cursors": {source.name: 90}, "codex_thread": "retain-session"}
            result, report = module.plan_state({"message_table": table}, state, source, destination)
            self.assertEqual(result["message_db_cursors"], {source.name: 90, "message_1.db": 1})
            self.assertEqual(result["codex_thread"], "retain-session")
            self.assertEqual(result["active_message_db"], "message_1.db")
            self.assertEqual(report[0]["pending"], 1)
            self.assertNotIn("message_1.db", state["message_db_cursors"])


if __name__ == "__main__":
    unittest.main()
