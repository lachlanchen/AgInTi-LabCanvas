from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_autopublish_video.py"


class WeChatAutoPublishVideoTests(unittest.TestCase):
    def test_copies_latest_mirrored_video_with_completed_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_dir = base / "mirror" / "懒人科研"
            source_dir.mkdir(parents=True)
            source = source_dir / "wechat clip.mp4"
            source.write_bytes(b"video-bytes")
            db = base / "mirror.sqlite"
            create_media_db(db, source, chat="懒人科研")
            dest = base / "AutoPublish"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--db",
                    str(db),
                    "--dest",
                    str(dest),
                    "--chat",
                    "懒人科研",
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "copied")
            target = dest / "wechat_clip_COMPLETED.mp4"
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), b"video-bytes")

    def test_source_dry_run_uses_title_and_does_not_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "demo.mov"
            source.write_bytes(b"video")
            dest = base / "AutoPublish"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source",
                    str(source),
                    "--dest",
                    str(dest),
                    "--title",
                    "field test",
                    "--dry-run",
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "dry-run")
            self.assertEqual(payload["target_name"], "field_test_COMPLETED.mov")
            self.assertFalse((dest / "field_test_COMPLETED.mov").exists())


def create_media_db(path: Path, source: Path, *, chat: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    source_mtime = time.time()
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE chats (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        conn.execute(
            """
            CREATE TABLE media_files (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                event_id INTEGER,
                source_path TEXT NOT NULL,
                mirror_path TEXT NOT NULL,
                suffix TEXT,
                size_bytes INTEGER,
                source_mtime REAL,
                status TEXT NOT NULL,
                matched_by TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO chats(id, name) VALUES (1, ?)", (chat,))
        conn.execute(
            """
            INSERT INTO media_files(
                chat_id, event_id, source_path, mirror_path, suffix, size_bytes,
                source_mtime, status, matched_by, metadata_json, created_at, updated_at
            )
            VALUES (1, 1, ?, ?, '.mp4', ?, ?, 'copied', 'mtime', '{}', ?, ?)
            """,
            (str(source), str(source), source.stat().st_size, source_mtime, now, now),
        )


if __name__ == "__main__":
    unittest.main()
