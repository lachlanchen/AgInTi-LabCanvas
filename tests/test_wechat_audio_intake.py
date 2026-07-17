from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_audio_intake.py"
    spec = importlib.util.spec_from_file_location("wechat_audio_intake_for_tests", path)
    assert spec and spec.loader
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatAudioIntakeTests(unittest.TestCase):
    def test_pipeline_writes_source_scoped_agent_context_and_reuses_cache(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "exact-group-video.mp4"
            source.write_bytes(b"source-scoped-video")

            def fake_extract(_source, target, **_kwargs):
                target.write_bytes(b"RIFF" + b"0" * 100)

            transcript = {
                "text": "请帮我总结这个实验。",
                "segments": [{"start": 0.0, "end": 2.5, "text": "请帮我总结这个实验。"}],
                "backend": "whisper",
                "language": "zh",
                "duration": 2.5,
            }
            with mock.patch.object(
                module,
                "probe_media",
                return_value={"duration_seconds": 2.5, "audio_stream_count": 1, "video_stream_count": 1},
            ), mock.patch.object(module, "extract_audio", side_effect=fake_extract), mock.patch.object(
                module, "transcribe_wav", return_value=transcript
            ) as transcribe:
                result = module.run_pipeline(source, root / "output", source_local_id=42, model="medium")
                cached = module.run_pipeline(source, root / "output", source_local_id=42, model="medium")

            self.assertEqual(result["status"], "transcribed")
            self.assertEqual(cached["status"], "cached")
            self.assertEqual(transcribe.call_count, 1)
            context = Path(result["agent_context_path"]).read_text(encoding="utf-8")
            self.assertIn("请帮我总结这个实验", context)
            self.assertIn("Source local ID: `42`", context)
            self.assertIn("untrusted", context)
            manifest = json.loads(Path(result["manifest_json"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_sha256"], module.sha256_file(source))

    def test_no_audio_requires_verified_readable_local_media(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "silent.mp4"
            source.write_bytes(b"silent-video")
            with mock.patch.object(
                module,
                "probe_media",
                return_value={"duration_seconds": 4.0, "audio_stream_count": 0, "video_stream_count": 1},
            ), mock.patch.object(module, "extract_audio") as extract:
                result = module.run_pipeline(source, root / "output")

            self.assertEqual(result["status"], "no_audio")
            self.assertTrue(result["verified_silent_media"])
            extract.assert_not_called()

    def test_probe_failure_is_not_reported_as_silence(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "broken.mp4"
            source.write_bytes(b"broken")
            with mock.patch.object(module, "probe_media", side_effect=RuntimeError("unreadable media")):
                result = module.run_pipeline(source, root / "output")

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failure_stage"], "media_probe")
            self.assertNotIn("verified_silent_media", result)


if __name__ == "__main__":
    unittest.main()
