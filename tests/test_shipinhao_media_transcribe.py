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
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "shipinhao_media_transcribe.py"
    spec = importlib.util.spec_from_file_location("shipinhao_media_transcribe_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def card_xml(url: str = "http://wxapp.tc.qq.com/video?id=exact-token") -> str:
    return f"""
    <finderFeed>
      <objectId><![CDATA[14712921966547245212]]></objectId>
      <objectNonceId><![CDATA[nonce-exact]]></objectNonceId>
      <nickname><![CDATA[Creator]]></nickname>
      <desc><![CDATA[Exact Finder subject]]></desc>
      <coverUrl><![CDATA[http://wxapp.tc.qq.com/cover?id=cover-token]]></coverUrl>
      <mediaList><media>
        <videoPlayDuration><![CDATA[237]]></videoPlayDuration>
        <url><![CDATA[{url}]]></url>
        <mediaType><![CDATA[4]]></mediaType>
      </media></mediaList>
      <megaVideo><objectId><![CDATA[]]></objectId></megaVideo>
    </finderFeed>
    """


class ShipinhaoMediaTranscribeTests(unittest.TestCase):
    def test_profile_extracts_exact_media_identity_and_url(self) -> None:
        module = load_module()

        profile = module.extract_shipinhao_media_profile(card_xml())

        self.assertTrue(profile["detected"])
        self.assertEqual(profile["object_id"], "14712921966547245212")
        self.assertEqual(profile["title"], "Exact Finder subject")
        self.assertEqual(profile["duration_seconds"], 237.0)
        self.assertEqual(profile["media_urls"], ["http://wxapp.tc.qq.com/video?id=exact-token"])
        self.assertEqual(profile["cover_urls"], ["http://wxapp.tc.qq.com/cover?id=cover-token"])

    def test_media_url_requires_allowlisted_tencent_host_and_tls_output(self) -> None:
        module = load_module()

        safe = module.validate_media_url("http://wxapp.tc.qq.com/video?id=token")

        self.assertEqual(safe, "https://wxapp.tc.qq.com/video?id=token")
        with self.assertRaises(ValueError):
            module.validate_media_url("https://example.com/video.mp4")
        with self.assertRaises(ValueError):
            module.validate_media_url("http://127.0.0.1/private.mp4")

    def test_pipeline_writes_agent_context_without_signed_url(self) -> None:
        module = load_module()
        signed_url = "http://wxapp.tc.qq.com/video?id=private-signed-token"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_download(_url, target, **_kwargs):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"verified-video")
                return {"bytes": 14, "sha256": "a" * 64, "source_url_sha256": "b" * 64}

            def fake_extract(_media, target, **_kwargs):
                target.write_bytes(b"RIFF" + b"0" * 100)

            transcript = {
                "text": "The speaker explains a concrete idea.",
                "segments": [{"start": 0.0, "end": 3.2, "text": "The speaker explains a concrete idea."}],
                "model": "turbo",
                "backend": "whisper",
                "language": "en",
                "duration": 3.2,
            }
            with mock.patch.object(module, "download_media", side_effect=fake_download), mock.patch.object(
                module,
                "probe_media",
                return_value={"duration_seconds": 3.2, "audio_stream_count": 1, "video_stream_count": 1},
            ), mock.patch.object(module, "extract_audio", side_effect=fake_extract), mock.patch.object(
                module, "transcribe_audio", return_value=transcript
            ), mock.patch.object(module, "resolve_whisper_model", return_value="turbo"):
                result = module.run_pipeline(
                    card_xml(signed_url),
                    root / "output",
                    cache_root=root / "cache",
                    model="turbo",
                )

            context = Path(result["agent_context_path"]).read_text(encoding="utf-8")
            manifest = Path(result["manifest_json"]).read_text(encoding="utf-8")
            transcript_payload = json.loads(Path(result["transcript_json"]).read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "transcribed")
        self.assertIn("speaker explains", context)
        self.assertEqual(transcript_payload["object_id"], "14712921966547245212")
        self.assertNotIn("private-signed-token", manifest)
        self.assertNotIn("cover-token", manifest)
        self.assertNotIn("private-signed-token", context)

    def test_download_failure_is_not_reported_as_no_audio(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(module, "download_media", side_effect=RuntimeError("HTTP 400")):
                result = module.run_pipeline(
                    card_xml(),
                    root / "output",
                    cache_root=root / "cache",
                    model="turbo",
                    public_mirror_recovery=False,
                )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failure_stage"], "download")
        self.assertNotEqual(result["status"], "no_audio")

    def test_public_mirror_match_requires_duration_and_content_evidence(self) -> None:
        module = load_module()
        profile = module.extract_shipinhao_media_profile(card_xml())
        profile["duration_seconds"] = 38.0
        candidate = {
            "id": "video12345",
            "title": "I Don't Care Who Is Doing Better Than Me",
            "description": "Denzel Washington motivation",
            "channel": "Public mirror",
            "duration": 40.0,
        }
        evidence = module.public_mirror_match_evidence(
            profile,
            "I don't care who is doing better than me. Because the truth is.",
            (
                "I don't care who is doing better than me because the truth is I'm not in competition "
                "with anyone else. The only person I need to be better than is the person I was yesterday."
            ),
            candidate,
            {"duration_seconds": 40.0, "audio_stream_count": 1},
        )

        self.assertTrue(evidence["accepted"])
        self.assertGreaterEqual(evidence["longest_english_word_run"], 6)

        unrelated = module.public_mirror_match_evidence(
            profile,
            "I don't care who is doing better than me.",
            "An unrelated cooking demonstration with no matching speech.",
            candidate,
            {"duration_seconds": 40.0, "audio_stream_count": 1},
        )
        self.assertFalse(unrelated["accepted"])

    def test_search_queries_use_chinese_ocr_and_bounded_translation(self) -> None:
        module = load_module()
        profile = module.extract_shipinhao_media_profile(card_xml())

        queries = module.public_mirror_search_queries(
            profile,
            "乔布斯 1992 年演讲\n我认为你不能真正拥有某样东西",
            {
                "title": "Steve Jobs speech in 1992",
                "cover_lines": ["I think you cannot really own something"],
            },
            ["Steve Jobs consulting responsibility recommendations"],
        )

        self.assertIn("i think you cannot really own something", [query.casefold() for query in queries])
        self.assertTrue(any("我认为你不能真正拥有某样东西" in query for query in queries))
        self.assertIn("Steve Jobs speech in 1992", queries)
        self.assertIn("Steve Jobs consulting responsibility recommendations", queries)
        self.assertLessEqual(len(queries), module.PUBLIC_MIRROR_QUERY_LIMIT)

    def test_longer_public_source_requires_strong_excerpt_content(self) -> None:
        module = load_module()
        profile = module.extract_shipinhao_media_profile(card_xml())
        profile["duration_seconds"] = 43.0
        candidate = {
            "id": "video12345",
            "title": "Steve Jobs 1992 speech",
            "description": "A longer interview excerpt",
            "channel": "Archive",
            "duration": 147.0,
        }
        translated = {
            "title": "Steve Jobs speech in 1992",
            "cover_lines": ["I think you cannot really own something"],
        }

        evidence = module.public_mirror_match_evidence(
            profile,
            "我认为你不能真正拥有某样东西",
            "I think you cannot really own something until you understand how it was made.",
            candidate,
            {"duration_seconds": 147.0, "audio_stream_count": 1},
            translated,
        )
        unrelated = module.public_mirror_match_evidence(
            profile,
            "我认为你不能真正拥有某样东西",
            "This is an unrelated product review with no matching statement.",
            candidate,
            {"duration_seconds": 147.0, "audio_stream_count": 1},
            translated,
        )

        self.assertTrue(evidence["accepted"])
        self.assertTrue(evidence["source_excerpt_verified"])
        self.assertFalse(evidence["duration_match"])
        self.assertFalse(unrelated["accepted"])
        self.assertFalse(unrelated["source_excerpt_verified"])

    def test_paraphrase_match_rejects_related_but_wrong_speaker_clip(self) -> None:
        module = load_module()
        profile = module.extract_shipinhao_media_profile(card_xml())
        profile["duration_seconds"] = 43.0
        translated = {
            "title": (
                "Steve Jobs stick to ideas and take responsibility for suggestions, "
                "practice them, and learn from the results"
            ),
            "cover_lines": ["I don't think you can really own something"],
        }
        candidate = {"id": "consult123", "title": "Steve Jobs on Consulting", "duration": 134.0}

        correct = module.public_mirror_match_evidence(
            profile,
            "我认为你不能真正拥有某样东西",
            (
                "I don't think there is anything inherently evil in consulting. Without owning something "
                "over an extended period, taking responsibility for recommendations, seeing them through "
                "all action stages, you can really own the outcome and learn from mistakes."
            ),
            candidate,
            {"duration_seconds": 134.0, "audio_stream_count": 1},
            translated,
        )
        related_but_wrong = module.public_mirror_match_evidence(
            profile,
            "我认为你不能真正拥有某样东西",
            (
                "You can influence life and build your own things that other people can use. "
                "Once you learn that, you will want to change life and make it better."
            ),
            {"id": "other123", "title": "Steve Jobs Secrets of Life", "duration": 100.0},
            {"duration_seconds": 100.0, "audio_stream_count": 1},
            translated,
        )

        self.assertTrue(correct["accepted"])
        self.assertTrue(correct["fuzzy_paraphrase_match"])
        self.assertFalse(related_but_wrong["accepted"])
        self.assertFalse(related_but_wrong["fuzzy_paraphrase_match"])

    def test_matching_excerpt_window_is_bounded_to_card_duration(self) -> None:
        module = load_module()
        segments = [
            {"start": 0.0, "end": 10.0, "text": "An unrelated introduction."},
            {"start": 50.0, "end": 58.0, "text": "I think you cannot really own something"},
            {"start": 58.0, "end": 68.0, "text": "until you understand how it was made."},
            {"start": 120.0, "end": 130.0, "text": "An unrelated conclusion."},
        ]

        window = module.matching_excerpt_window(
            segments,
            ["I think you cannot really own something"],
            expected_duration=43.0,
            source_duration=147.0,
        )

        self.assertTrue(window)
        self.assertAlmostEqual(window["end_seconds"] - window["start_seconds"], 43.0, places=2)
        self.assertLessEqual(window["start_seconds"], 50.0)
        self.assertGreaterEqual(window["end_seconds"], 58.0)

    def test_verified_captions_can_corroborate_fuzzy_excerpt_asr(self) -> None:
        module = load_module()
        audio_evidence = {
            "accepted": False,
            "title_transcript_stem_overlap": 3,
            "longest_english_word_run": 3,
            "english_token_coverage": 0.625,
        }
        subtitle_evidence = {"accepted": True, "source_excerpt_verified": True}
        excerpt = {"start_seconds": 20.0, "end_seconds": 63.0}

        accepted = module.reconcile_excerpt_evidence(audio_evidence, subtitle_evidence, excerpt)
        rejected = module.reconcile_excerpt_evidence(audio_evidence, {"accepted": False}, excerpt)

        self.assertTrue(accepted["accepted"])
        self.assertTrue(accepted["caption_then_audio_corroborated"])
        self.assertFalse(rejected["accepted"])

    def test_expired_direct_url_can_use_content_verified_public_mirror(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "cache" / "public-mirror-video12345.mp4"
            audio = root / "cache" / "public-mirror-video12345.wav"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"verified-public-video")
            audio.write_bytes(b"RIFF" + b"0" * 100)
            transcript = {
                "text": "The only person I need to be better than is the person I was yesterday.",
                "segments": [{"start": 0.0, "end": 3.2, "text": "The only person I need to be better than is the person I was yesterday."}],
                "model": "turbo",
                "backend": "whisper",
                "language": "en",
                "duration": 3.2,
            }
            recovered = {
                "status": "verified",
                "media_path": str(media),
                "audio_path": str(audio),
                "media_probe": {"duration_seconds": 237.0, "audio_stream_count": 1, "video_stream_count": 1},
                "transcript": transcript,
                "validation": {"accepted": True, "candidate_id": "video12345"},
            }
            with mock.patch.object(module, "download_media", side_effect=RuntimeError("HTTP 400")), mock.patch.object(
                module, "recover_public_mirror", return_value=recovered
            ), mock.patch.object(module, "resolve_whisper_model", return_value="turbo"):
                result = module.run_pipeline(
                    card_xml(),
                    root / "output",
                    cache_root=root / "cache",
                    model="turbo",
                )

        self.assertEqual(result["status"], "transcribed")
        self.assertEqual(result["input_kind"], "content_verified_public_mirror")
        self.assertTrue(result["content_identity_verified"])
        self.assertEqual(result["public_mirror_validation"]["candidate_id"], "video12345")

    def test_no_audio_requires_verified_readable_media(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_download(_url, target, **_kwargs):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"verified-silent-video")
                return {"bytes": 21, "sha256": "a" * 64, "source_url_sha256": "b" * 64}

            with mock.patch.object(module, "download_media", side_effect=fake_download), mock.patch.object(
                module,
                "probe_media",
                return_value={
                    "duration_seconds": 3.2,
                    "audio_stream_count": 0,
                    "video_stream_count": 1,
                },
            ):
                result = module.run_pipeline(
                    card_xml(),
                    root / "output",
                    cache_root=root / "cache",
                    model="turbo",
                )

        self.assertEqual(result["status"], "no_audio")
        self.assertTrue(result["verified_silent_media"])
        self.assertNotIn("failure_stage", result)

    def test_verified_capture_manifest_is_source_scoped_and_hash_checked(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            cache_root = Path(tmp) / "cache"
            object_dir = cache_root / "14712921966547245212"
            object_dir.mkdir(parents=True)
            audio = object_dir / "captured-source.wav"
            audio.write_bytes(b"RIFF-source-scoped-audio")
            manifest = object_dir / "verified-capture.json"
            payload = {
                "status": "verified",
                "visual_identity_verified": True,
                "object_id": "14712921966547245212",
                "title": "Exact Finder subject",
                "author": "Creator",
                "identity_terms": ["Exact Finder"],
                "audio_path": str(audio),
                "audio_sha256": module.sha256_file(audio),
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")

            verified = module.load_verified_capture_manifest(
                manifest,
                profile=module.extract_shipinhao_media_profile(card_xml()),
                cache_root=cache_root,
            )
            self.assertEqual(verified["audio_path"], str(audio.resolve()))
            self.assertTrue(verified["manifest_sha256"])

            payload["object_id"] = "different-object"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "object ID"):
                module.load_verified_capture_manifest(
                    manifest,
                    profile=module.extract_shipinhao_media_profile(card_xml()),
                    cache_root=cache_root,
                )

    def test_capture_cache_names_include_audio_identity(self) -> None:
        module = load_module()

        self.assertEqual(module.transcript_cache_name("turbo"), "transcript-turbo.json")
        self.assertEqual(
            module.transcript_cache_name("turbo", capture_sha256="abcdef0123456789"),
            "transcript-turbo-abcdef012345.json",
        )


if __name__ == "__main__":
    unittest.main()
