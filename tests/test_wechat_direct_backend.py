from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from agenticapp.cli import main


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_direct_backend.py"


def load_backend():
    spec = importlib.util.spec_from_file_location("wechat_direct_backend_for_tests", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatDirectBackendTests(unittest.TestCase):
    def test_live_profile_wins_over_newer_unrelated_directory(self) -> None:
        backend = load_backend()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            active = home / "Documents/xwechat_files/active/db_storage"
            unrelated = home / "Documents/xwechat_files/unrelated/db_storage"
            active.mkdir(parents=True)
            unrelated.mkdir(parents=True)
            proc = home / "proc"
            (proc / "123/fd").mkdir(parents=True)
            (proc / "123/comm").write_text("wechat\n")
            source = active / "message_0.db"
            source.touch()
            (proc / "123/fd/4").symlink_to(source)
            selected = backend.active_wechat_db_dirs([active, unrelated], proc)
            self.assertEqual(selected, [active])
            with mock.patch.object(backend.Path, "home", return_value=home), mock.patch.object(
                backend, "active_wechat_db_dirs", return_value=selected
            ):
                self.assertEqual(backend.discover_xwechat_db(), active)

    def test_multiple_live_profiles_require_explicit_selection(self) -> None:
        backend = load_backend()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            paths = [home / f"Documents/xwechat_files/{name}/db_storage" for name in ("one", "two")]
            for path in paths:
                path.mkdir(parents=True)
            with mock.patch.object(backend.Path, "home", return_value=home), mock.patch.object(
                backend, "active_wechat_db_dirs", return_value=paths
            ), self.assertRaises(SystemExit):
                backend.discover_xwechat_db()

    def test_decrypt_fails_closed_but_distinguishes_optional_stores(self) -> None:
        backend = load_backend()
        self.assertFalse(backend.decrypt_summary("结果: 0 成功, 15 失败, 0 跳过(无密钥)")["ok"])
        self.assertFalse(backend.decrypt_summary("no summary")["ok"])
        self.assertFalse(backend.decrypt_summary("结果: 0 成功, 0 失败, 1 跳过(无密钥)")["ok"])
        for path, expected in (("message/message_2.db", False), ("session/session.db", False), ("newtips/newtips.db", True)):
            with self.subTest(path=path):
                summary = backend.decrypt_summary(f"SKIP: {path} (无密钥)\n结果: 0 成功, 0 失败, 1 跳过(无密钥)")
                self.assertEqual(summary["ok"], expected)

    def test_decrypt_wrapper_rejects_zero_exit_failure_and_records_private_state(self) -> None:
        backend = load_backend()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def fail(_command, **kwargs):
                kwargs["stdout"].write("结果: 0 成功, 15 失败, 0 跳过(无密钥)".encode())
                return mock.Mock(returncode=0)
            with mock.patch.object(backend, "PRIVATE", root), mock.patch.object(
                backend.subprocess, "run", side_effect=fail
            ), redirect_stdout(io.StringIO()):
                code = backend.run_decrypt(root, ["decrypt"], root / "config.json")
            state_path = root / "wechat_decrypt.refresh.status.json"
            state = json.loads(state_path.read_text())
            self.assertEqual(code, 1)
            self.assertFalse(state["ok"])
            self.assertEqual(state["failed_count"], 15)
            self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)

    def test_public_path_redacts_wechat_profile(self) -> None:
        backend = load_backend()
        raw = Path.home() / "Documents" / "xwechat_files" / "wxid_secret123" / "db_storage"

        redacted = backend.public_path(raw)

        self.assertIn("<wechat-profile>", redacted)
        self.assertNotIn("wxid_secret123", redacted)

    def test_status_reports_sanitized_external_backend_shape(self) -> None:
        backend = load_backend()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            external = base / "wechat-decrypt"
            db_dir = base / "xwechat_files" / "wxid_private" / "db_storage"
            external.mkdir()
            db_dir.mkdir(parents=True)
            (external / "decrypt_db.py").write_text("# test\n", encoding="utf-8")
            (external / "find_all_keys_linux.py").write_text("# test\n", encoding="utf-8")
            (db_dir / "message").mkdir()
            (db_dir / "message" / "message_0.db").write_bytes(b"")

            payload = backend.status(external, db_dir)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["private_paths_redacted"])
        self.assertNotIn("keys_file", payload)
        self.assertNotIn("wxid_private", json.dumps(payload, ensure_ascii=False))

    def test_wechat_backend_status_cli_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            external = base / "wechat-decrypt"
            db_dir = base / "db_storage"
            external.mkdir()
            db_dir.mkdir()
            (external / "decrypt_db.py").write_text("# test\n", encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["wechat", "backend", "status", "--external", str(external), "--db-dir", str(db_dir), "--json"])

            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["scripts"]["decrypt_db.py"])


if __name__ == "__main__":
    unittest.main()
