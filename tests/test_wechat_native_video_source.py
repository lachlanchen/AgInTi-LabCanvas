from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wechat_android_native_video_save as native_save
import wechat_autopublish_video as autopublish
import wechat_video_source_policy as source_policy


class WeChatNativeVideoSourceTests(unittest.TestCase):
    def test_android_intake_requires_checksum_bound_native_manifest_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "wechat_android_intake" / "task" / "native_original"
            directory.mkdir(parents=True)
            video = directory / "source.mp4"
            video.write_bytes(b"native-video")

            missing = source_policy.evaluate_publishable_video_source(video)
            self.assertFalse(missing.accepted)
            self.assertEqual(missing.status, "native-export-proof-required")

            manifest = {
                "status": "verified",
                "source_kind": "wechat_android_native_album_export",
                "host_path": str(video.resolve()),
                "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                "automation_screen_capture": False,
                "device_copy_removed": False,
            }
            (directory / source_policy.NATIVE_MANIFEST).write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            pending = source_policy.evaluate_publishable_video_source(video)
            self.assertFalse(pending.accepted)
            self.assertEqual(pending.status, "phone-export-cleanup-required")

            manifest["device_copy_removed"] = True
            (directory / source_policy.NATIVE_MANIFEST).write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            accepted = source_policy.evaluate_publishable_video_source(video)
            self.assertTrue(accepted.accepted)
            self.assertEqual(accepted.status, "verified-native-source")

            video.write_bytes(b"changed")
            changed = source_policy.evaluate_publishable_video_source(video)
            self.assertFalse(changed.accepted)
            self.assertEqual(changed.status, "native-export-checksum-mismatch")

    def test_native_manifest_allows_user_supplied_screen_recording_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "wechat_android_intake" / "task" / "native_original"
            directory.mkdir(parents=True)
            video = directory / "my-screenrecord-demo.mp4"
            video.write_bytes(b"exact attachment")
            (directory / source_policy.NATIVE_MANIFEST).write_text(
                json.dumps(
                    {
                        "status": "verified",
                        "source_kind": "wechat_android_native_album_export",
                        "host_path": str(video.resolve()),
                        "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                        "automation_screen_capture": False,
                        "device_copy_removed": True,
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(source_policy.evaluate_publishable_video_source(video).accepted)

    def test_automation_capture_is_rejected_at_autopublish_copy_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "screen_raw.mp4"
            video.write_bytes(b"captured player")
            candidate = autopublish.VideoCandidate(
                media_id=1,
                chat_name="My devices",
                path=video,
                suffix=".mp4",
                size_bytes=video.stat().st_size,
                source_mtime=video.stat().st_mtime,
                updated_at="",
                status="copied",
                matched_by="exact",
            )
            result = autopublish.copy_candidate(
                candidate,
                dest_dir=root / "autopublish",
                title="demo",
                replace=False,
                dry_run=False,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "native-source-required")
            self.assertFalse((root / "autopublish" / "demo_COMPLETED.mp4").exists())

    def test_advertised_size_and_compressed_export_validation(self) -> None:
        self.assertEqual(
            native_save.parse_advertised_size_mb("查看原视频206MB"),
            206.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "native.mp4"
            video.write_bytes(b"x" * 1024)
            probe = {"format": {"duration": "35.5", "size": str(8 * 1024 * 1024)}}
            with self.assertRaisesRegex(native_save.NativeVideoSaveError, "expected original"):
                native_save.validate_video(
                    video,
                    probe,
                    expected_duration=35.5,
                    duration_tolerance=1.0,
                    expected_size_mb=206.0,
                )

    def test_phone_export_removal_is_verified(self) -> None:
        class Sender:
            def __init__(self) -> None:
                self.commands: list[list[str]] = []

            def shell(self, command: list[str], **_: object) -> SimpleNamespace:
                self.commands.append(command)
                if command[:2] == ["ls", "/storage/emulated/0/DCIM/WeiXin/mmexport.mp4"]:
                    return SimpleNamespace(returncode=1, stdout="", stderr="")
                if command[:2] == ["content", "query"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

        sender = Sender()
        native_save.remove_device_export(
            sender,  # type: ignore[arg-type]
            {
                "id": 42,
                "path": "/storage/emulated/0/DCIM/WeiXin/mmexport.mp4",
            },
        )
        self.assertIn(["rm", "-f", "/storage/emulated/0/DCIM/WeiXin/mmexport.mp4"], sender.commands)
        self.assertTrue(any(command[:2] == ["content", "delete"] for command in sender.commands))


if __name__ == "__main__":
    unittest.main()
