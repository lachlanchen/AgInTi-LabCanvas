from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest

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
