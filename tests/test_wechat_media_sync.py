from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_media_sync.py"


class WeChatMediaSyncTests(unittest.TestCase):
    def test_sync_detects_extension_and_records_media_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source-cache"
            source.mkdir()
            image = source / "quoted_image_blob"
            image.write_bytes(b"\xff\xd8\xff\xe0" + b"jpeg-demo")
            dest = base / "downloads"
            db = base / "mirror.sqlite"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--chat",
                    "懒人科研",
                    "--source",
                    str(source),
                    "--dest",
                    str(dest),
                    "--db",
                    str(db),
                    "--since-minutes",
                    "999",
                    "--summary-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "copied")
            self.assertEqual(payload["file_count"], 1)
            self.assertEqual(payload["recorded_files"], 1)
            copied = list(dest.rglob("quoted_image_blob.jpg"))
            self.assertEqual(len(copied), 1)

            with sqlite3.connect(db) as conn:
                row = conn.execute(
                    """
                    SELECT chats.name, media_files.mirror_path, media_files.suffix,
                           media_files.status, media_files.matched_by
                    FROM media_files
                    JOIN chats ON chats.id = media_files.chat_id
                    """
                ).fetchone()

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row[0], "懒人科研")
            self.assertTrue(row[1].endswith("quoted_image_blob.jpg"))
            self.assertEqual(row[2], ".jpg")
            self.assertEqual(row[3], "copied")
            self.assertEqual(row[4], "mtime")


if __name__ == "__main__":
    unittest.main()
