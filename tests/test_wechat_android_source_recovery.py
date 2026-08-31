from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
ANDROID_SCRIPTS = ROOT / "agentic_tools" / "android_device_agent" / "scripts"


def load_recovery():
    for path in (SCRIPTS, ANDROID_SCRIPTS):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    source = SCRIPTS / "wechat_android_source_recovery.py"
    spec = importlib.util.spec_from_file_location(
        "wechat_android_source_recovery_for_tests", source
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WechatAndroidSourceRecoveryTests(unittest.TestCase):
    def test_article_title_identity_allows_only_strong_publisher_suffix_match(self) -> None:
        module = load_recovery()

        self.assertTrue(
            module.article_titles_match(
                "第一次，我们看到了高自由度灵巧手的另一种可能",
                "第一次，我们看到了高自由度灵巧手的另一种可能｜具身智能研究所",
            )
        )
        self.assertFalse(module.article_titles_match("AI", "AI 工具日报"))
        self.assertFalse(
            module.article_titles_match(
                "第一次，我们看到了高自由度灵巧手的另一种可能",
                "完全无关的公众号文章标题",
            )
        )

    def test_article_recovery_uses_copied_canonical_link_and_exact_title(self) -> None:
        module = load_recovery()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = mock.Mock()
            with mock.patch.object(
                module, "open_exact_card", return_value=root / "identity.png"
            ) as opened, mock.patch.object(
                module,
                "copy_article_link",
                return_value="https://mp.weixin.qq.com/s/canonical-token",
            ), mock.patch.object(
                module,
                "recover_mp_weixin_article",
                return_value={
                    "status": "recovered",
                    "source_quality": "full_article",
                    "title": "精确的公众号文章标题｜研究账号",
                    "author": "研究账号",
                    "article_chars": 2400,
                    "markdown_path": str(root / "article.md"),
                },
            ):
                result = module.recover_article(
                    sender,
                    title="精确的公众号文章标题",
                    output_dir=root,
                    max_scrolls=3,
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["source_quality"], "full_article")
        self.assertTrue(result["identity_verified"])
        opened.assert_called_once()

    def test_shipinhao_reenters_exact_chat_after_audio_helper_prewarm(self) -> None:
        module = load_recovery()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = mock.Mock()
            sender.chat = "Shares鏈接"
            events: list[str] = []
            sender.ensure_exact_chat.side_effect = lambda: events.append("exact-chat")

            def prewarm(_sender):
                events.append("prewarm")

            def open_card(_sender, **_kwargs):
                events.append("open-card")
                return root / "identity.png"

            with mock.patch.object(module, "prewarm_sndcpy", side_effect=prewarm), mock.patch.object(
                module, "open_exact_card", side_effect=open_card
            ), mock.patch.object(
                module,
                "capture_player",
                return_value={
                    "audio_path": str(root / "audio.wav"),
                    "audio_sha256": "a" * 64,
                    "video_path": str(root / "video.mp4"),
                    "video_sha256": "b" * 64,
                    "duration_seconds": 12.0,
                },
            ):
                result = module.recover_shipinhao(
                    sender,
                    object_id="finder-1",
                    source_id="message-1",
                    title="[视频号] Hui世界的视频",
                    author="Hui世界",
                    identity_terms=["Hui世界"],
                    output_dir=root / "output",
                    cache_root=root / "cache",
                    max_scrolls=3,
                    max_seconds=30,
                    expected_duration_seconds=0,
                )

            self.assertEqual(events, ["prewarm", "exact-chat", "open-card"])
            self.assertTrue(result["ok"])
            self.assertTrue(Path(result["capture_manifest"]).is_file())

    def test_audio_loop_candidate_finds_repeated_playback(self) -> None:
        module = load_recovery()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "loop.wav"
            rate = 8000
            seconds = 14
            rng = np.random.default_rng(42)
            one_loop = rng.integers(-12000, 12000, rate * seconds, dtype=np.int16)
            repeated = np.concatenate([one_loop, one_loop, one_loop[: rate * 4]])
            import wave

            with wave.open(str(path), "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(rate)
                target.writeframes(repeated.astype("<i2").tobytes())

            period, correlation = module.audio_loop_candidate(path)

            self.assertAlmostEqual(period, 14.0, delta=0.04)
            self.assertGreater(correlation, 0.99)

    def test_verified_loop_requires_visual_confirmation(self) -> None:
        module = load_recovery()
        with mock.patch.object(
            module, "audio_loop_candidate", return_value=(57.64, 0.96)
        ), mock.patch.object(
            module, "visual_loop_difference", return_value=0.01
        ):
            period = module.verified_loop_period(
                Path("audio.wav"),
                Path("video.mp4"),
                duration_seconds=90.0,
            )

        self.assertEqual(period, 57.64)


if __name__ == "__main__":
    unittest.main()
