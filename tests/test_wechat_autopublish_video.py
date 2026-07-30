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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_autopublish_video.py"


class WeChatAutoPublishVideoTests(unittest.TestCase):
    def test_message_refs_require_rotated_db_and_positive_local_id(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_autopublish_video

        self.assertEqual(
            wechat_autopublish_video.parse_message_refs(
                ["message_1.db:7", "message_1.db:7", "message_12.db:3"]
            ),
            [("message_1.db", 7), ("message_12.db", 3)],
        )
        with self.assertRaises(SystemExit):
            wechat_autopublish_video.parse_message_refs(["message.db:7"])
        with self.assertRaises(SystemExit):
            wechat_autopublish_video.parse_message_refs(["message_1.db:0"])

    def test_recent_video_messages_bind_duplicate_local_id_to_exact_rotated_shard(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_autopublish_video

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            private = base / "agentic_tools" / "wechat_gui_agent" / ".private"
            message_dir = private / "wechat_decrypt" / "decrypted" / "message"
            message_dir.mkdir(parents=True)
            (private / "devices-direct-chatops.local.json").write_text(
                json.dumps({"chat_name": "My devices", "message_table": "Msg_devices"}),
                encoding="utf-8",
            )
            now = int(time.time())
            create_message_db(
                message_dir / "message_0.db",
                table="Msg_devices",
                local_id=7,
                create_time=now - 20,
                md5="a" * 32,
            )
            create_message_db(
                message_dir / "message_1.db",
                table="Msg_devices",
                local_id=7,
                create_time=now - 10,
                md5="b" * 32,
            )
            with mock.patch.object(wechat_autopublish_video, "ROOT", base):
                legacy = wechat_autopublish_video.recent_video_messages(
                    ["My devices"],
                    60,
                    message_local_ids=[7],
                )
                exact = wechat_autopublish_video.recent_video_messages(
                    ["My devices"],
                    60,
                    message_refs=[("message_1.db", 7)],
                )

        self.assertEqual([item.message_db for item in legacy], ["message_1.db", "message_0.db"])
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0].message_db, "message_1.db")
        self.assertEqual(exact[0].local_id, 7)
        self.assertEqual(exact[0].stems, ("b" * 32,))

    def test_parse_video_metadata_extracts_stems_and_sizes(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_autopublish_video

        xml = (
            '<msg><videomsg md5="c43f397a0572fb697d26dad0b60abfe0" '
            'newmd5="f6f04092fb889141347d7b4067a3be6d" '
            'rawmd5="20ce6116367236e51d76b816161685c2" '
            'length="13616508" rawlength="129918644" /></msg>'
        )
        packed = b"\x08\x01\x12 c347ab61d55d3e4ee3b2653c17263c4f"

        stems, sizes = wechat_autopublish_video.parse_video_metadata(xml.encode(), b"", packed)

        self.assertIn("c43f397a0572fb697d26dad0b60abfe0", stems)
        self.assertIn("f6f04092fb889141347d7b4067a3be6d", stems)
        self.assertIn("20ce6116367236e51d76b816161685c2", stems)
        self.assertIn("c347ab61d55d3e4ee3b2653c17263c4f", stems)
        self.assertIn(13616508, sizes)
        self.assertIn(129918644, sizes)

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

    def test_exact_message_candidates_use_message_local_id_match(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_autopublish_video

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "exact-message.mp4"
            video.write_bytes(b"video")
            message = wechat_autopublish_video.VideoMessage(
                chat_name="🍓我的设备",
                local_id=14,
                create_time=int(time.time()),
                stems=("exact-message",),
                sizes=(video.stat().st_size,),
            )
            with mock.patch.object(wechat_autopublish_video, "recent_video_messages", return_value=[message]) as recent:
                with mock.patch.object(wechat_autopublish_video, "matching_video_files", return_value=[video]) as matching:
                    candidates = wechat_autopublish_video.exact_message_candidates(
                        chats=["🍓我的设备"],
                        since_minutes=720,
                        message_local_ids=[14],
                    )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].path, video.resolve())
        self.assertEqual(candidates[0].matched_by, "message-local-id:14")
        recent.assert_called_once()
        matching.assert_called_once()

    def test_exact_message_candidates_preserve_rotated_message_reference(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_autopublish_video

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "exact-message.mp4"
            video.write_bytes(b"video")
            message = wechat_autopublish_video.VideoMessage(
                chat_name="My devices",
                local_id=4,
                create_time=int(time.time()),
                stems=("exact-message",),
                sizes=(video.stat().st_size,),
                message_db="message_2.db",
            )
            with mock.patch.object(
                wechat_autopublish_video,
                "recent_video_messages",
                return_value=[message],
            ):
                with mock.patch.object(
                    wechat_autopublish_video,
                    "matching_video_files",
                    return_value=[video],
                ):
                    candidates = wechat_autopublish_video.exact_message_candidates(
                        chats=["My devices"],
                        since_minutes=720,
                        message_local_ids=[4],
                        message_refs=[("message_2.db", 4)],
                    )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].matched_by, "message-ref:message_2.db:4")
        self.assertEqual(candidates[0].message_db, "message_2.db")
        self.assertEqual(candidates[0].message_local_id, 4)

    def test_exact_message_candidates_prefer_original_send_temp_over_playback_transcode(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_autopublish_video

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            playback = base / "e0ba7c26e2e13ef56e4b08f5eb01cc81.mp4"
            playback.write_bytes(b"compressed")
            send_temp = base / "SendTemp" / "163_1785332281_send_temp.mp4"
            send_temp.parent.mkdir()
            send_temp.write_bytes(b"original-video-bytes")
            db = base / "mirror.sqlite"
            create_media_db(db, send_temp, chat="MEMO写作—外语—挣钱")
            now = time.time()
            playback.touch()
            message = wechat_autopublish_video.VideoMessage(
                chat_name="MEMO写作—外语—挣钱",
                local_id=163,
                create_time=int(now),
                stems=("e0ba7c26e2e13ef56e4b08f5eb01cc81",),
                sizes=(playback.stat().st_size,),
            )
            with mock.patch.object(wechat_autopublish_video, "recent_video_messages", return_value=[message]):
                with mock.patch.object(
                    wechat_autopublish_video,
                    "matching_video_files",
                    return_value=[playback],
                ):
                    candidates = wechat_autopublish_video.exact_message_candidates(
                        chats=[message.chat_name],
                        since_minutes=720,
                        message_local_ids=[163],
                        db_path=db,
                    )

        self.assertEqual(candidates[0].path, send_temp.resolve())
        self.assertEqual(candidates[0].size_bytes, len(b"original-video-bytes"))

    def test_parse_clicks_accepts_fallback_points(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_autopublish_video

        self.assertEqual(wechat_autopublish_video.parse_clicks("510,430;510,280;510,430"), [(510, 430), (510, 280)])
        self.assertIn((510, 430), wechat_autopublish_video.default_video_clicks())


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


def create_message_db(
    path: Path,
    *,
    table: str,
    local_id: int,
    create_time: int,
    md5: str,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            CREATE TABLE {table} (
                local_id INTEGER,
                create_time INTEGER,
                message_content BLOB,
                source BLOB,
                packed_info_data BLOB,
                local_type INTEGER
            )
            """
        )
        conn.execute(
            f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)",
            (
                local_id,
                create_time,
                f'<msg><videomsg md5="{md5}" length="4096" /></msg>',
                b"",
                b"",
                43,
            ),
        )


if __name__ == "__main__":
    unittest.main()
