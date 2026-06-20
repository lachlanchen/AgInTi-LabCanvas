from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_media_sync.py"


class WeChatMediaSyncTests(unittest.TestCase):
    def test_decode_keys_read_stable_private_media_config(self) -> None:
        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_media_sync

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = base / "agentic_tools" / "wechat_gui_agent" / ".private" / "wechat_image_keys.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                json.dumps({"image_aes_key": "1234567890abcdef", "image_xor_key": "0x44"}),
                encoding="utf-8",
            )
            original_root = wechat_media_sync.ROOT
            try:
                wechat_media_sync.ROOT = base
                with mock.patch.dict("os.environ", {"WECHAT_IMAGE_AES_KEY": "", "WECHAT_IMAGE_XOR_KEY": ""}, clear=False):
                    key, xor_key = wechat_media_sync.image_decode_keys("", "")
            finally:
                wechat_media_sync.ROOT = original_root

        self.assertEqual(key, b"1234567890abcdef")
        self.assertEqual(xor_key, 0x44)

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

    def test_sync_decodes_xor_dat_image_and_records_decoded_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source-cache"
            source.mkdir()
            jpg = b"\xff\xd8\xff\xe0" + b"jpeg-demo"
            encoded = bytes(byte ^ 0x88 for byte in jpg)
            dat = source / "abc123quotedimage.dat"
            dat.write_bytes(encoded)
            dest = base / "downloads"
            db = base / "mirror.sqlite"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--chat",
                    "lachlanchan",
                    "--source",
                    str(source),
                    "--dest",
                    str(dest),
                    "--db",
                    str(db),
                    "--since-minutes",
                    "0",
                    "--match-token",
                    "abc123quotedimage",
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
            decoded = list(dest.rglob("abc123quotedimage.jpg"))
            self.assertEqual(len(decoded), 1)
            self.assertEqual(decoded[0].read_bytes(), jpg)

            with sqlite3.connect(db) as conn:
                row = conn.execute(
                    """
                    SELECT chats.name, media_files.mirror_path, media_files.suffix,
                           media_files.status, media_files.matched_by,
                           media_files.metadata_json
                    FROM media_files
                    JOIN chats ON chats.id = media_files.chat_id
                    """
                ).fetchone()

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row[0], "lachlanchan")
            self.assertTrue(row[1].endswith("abc123quotedimage.jpg"))
            self.assertEqual(row[2], ".jpg")
            self.assertEqual(row[3], "decoded")
            self.assertEqual(row[4], "token:abc123quotedimage")
            metadata = json.loads(row[5])
            self.assertEqual(metadata["decode_status"], "decoded-xor")

    def test_decodes_v2_dat_container_with_image_key(self) -> None:
        try:
            from Crypto.Cipher import AES
            from Crypto.Util import Padding
        except ModuleNotFoundError:
            self.skipTest("pycryptodome is not installed")

        sys.path.insert(0, str(SCRIPT.parent))
        import wechat_media_sync

        key = b"1234567890abcdef"
        xor_key = 0x44
        payload = b"\xff\xd8\xff\xe0" + b"jpeg-v2-container"
        aes_payload = payload[:8]
        raw_payload = payload[8:12]
        xor_payload = payload[12:]
        encrypted = AES.new(key, AES.MODE_ECB).encrypt(Padding.pad(aes_payload, AES.block_size))
        container = (
            b"\x07\x08V2\x08\x07"
            + struct.pack("<LL", len(aes_payload), len(xor_payload))
            + b"\x00"
            + encrypted
            + raw_payload
            + bytes(byte ^ xor_key for byte in xor_payload)
        )
        with tempfile.TemporaryDirectory() as tmp:
            dat = Path(tmp) / "quoted_v2.dat"
            dat.write_bytes(container)
            decoded = wechat_media_sync.decode_wechat_dat(dat, image_aes_key=key, image_xor_key=xor_key)

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["status"], "decoded-v-container")
        self.assertEqual(decoded["format"], "jpg")
        self.assertEqual(decoded["data"], payload)

    def test_sync_adds_associated_thumb_for_attach_token_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            profile = base / "xwechat_files" / "wxid_demo"
            attach = profile / "msg" / "attach" / "chat_hash" / "2026-06" / "Img"
            thumb = profile / "cache" / "2026-06" / "Message" / "chat_hash" / "Thumb"
            attach.mkdir(parents=True)
            thumb.mkdir(parents=True)
            token = "feedfacecafebeef0011223344556677"
            (attach / f"{token}.dat").write_bytes(b"\x07\x08V2\x08\x07not-decodable")
            readable = thumb / "7_1781783136_thumb.jpg"
            readable.write_bytes(b"\xff\xd8\xff\xe0" + b"thumb")
            dest = base / "downloads"
            db = base / "mirror.sqlite"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--chat",
                    "lachlanchan",
                    "--source",
                    str(profile / "msg" / "attach"),
                    "--dest",
                    str(dest),
                    "--db",
                    str(db),
                    "--since-minutes",
                    "0",
                    "--match-token",
                    token,
                    "--summary-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["file_count"], 2)
            self.assertEqual(len(list(dest.rglob(f"{token}.dat"))), 1)
            self.assertEqual(len(list(dest.rglob("7_1781783136_thumb.jpg"))), 1)

            with sqlite3.connect(db) as conn:
                matched = conn.execute(
                    "SELECT matched_by FROM media_files WHERE mirror_path LIKE ?",
                    ("%7_1781783136_thumb.jpg",),
                ).fetchone()

            self.assertIsNotNone(matched)
            assert matched is not None
            self.assertEqual(matched[0], f"associated:{token}")

    def test_sync_adds_associated_thumb_for_cache_bubble_token_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            profile = base / "xwechat_files" / "wxid_demo"
            bubble = profile / "cache" / "2026-06" / "Message" / "chat_hash" / "Bubble"
            thumb = profile / "cache" / "2026-06" / "Message" / "chat_hash" / "Thumb"
            bubble.mkdir(parents=True)
            thumb.mkdir(parents=True)
            token = "cafed00d1234567890abcdef12345678"
            (bubble / f"{token}_b.dat").write_bytes(b"\x07\x08V2\x08\x07not-decodable")
            readable = thumb / "8_1781788117_thumb.jpg"
            readable.write_bytes(b"\xff\xd8\xff\xe0" + b"thumb")
            dest = base / "downloads"
            db = base / "mirror.sqlite"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--chat",
                    "lachlanchan",
                    "--source",
                    str(profile / "cache"),
                    "--dest",
                    str(dest),
                    "--db",
                    str(db),
                    "--since-minutes",
                    "0",
                    "--match-token",
                    token,
                    "--summary-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["file_count"], 2)
            self.assertEqual(len(list(dest.rglob(f"{token}_b.dat"))), 1)
            self.assertEqual(len(list(dest.rglob("8_1781788117_thumb.jpg"))), 1)

            with sqlite3.connect(db) as conn:
                matched = conn.execute(
                    "SELECT matched_by FROM media_files WHERE mirror_path LIKE ?",
                    ("%8_1781788117_thumb.jpg",),
                ).fetchone()

            self.assertIsNotNone(matched)
            assert matched is not None
            self.assertEqual(matched[0], f"associated:{token}")


if __name__ == "__main__":
    unittest.main()
