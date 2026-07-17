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
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "shipinhao_gui_audio_capture.py"
    spec = importlib.util.spec_from_file_location("shipinhao_gui_audio_capture_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ShipinhaoGuiAudioCaptureTests(unittest.TestCase):
    def test_identity_terms_prefer_book_title_hashtags_and_author(self) -> None:
        module = load_module()

        terms = module.derive_identity_terms(
            "蒋勋开讲《寒食帖》#寒食帖#苏东坡书法",
            "我是大熊熊.",
        )

        self.assertIn("寒食帖", terms)
        self.assertIn("苏东坡书法", terms)
        self.assertIn("我是大熊熊", terms)

    def test_identity_terms_include_stable_chunks_from_long_plain_title(self) -> None:
        module = load_module()

        terms = module.derive_identity_terms(
            "一个人的能力是怎么来的而不是从听课学出来的",
            "NLP大师-罗伯特迪尔茨",
        )

        self.assertIn("一个人的能力是怎么来", terms)
        self.assertIn("NLP大师-罗伯特迪尔茨", terms)

    def test_ocr_line_candidates_restore_resized_coordinates(self) -> None:
        module = load_module()
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t160\t80\t96\t32\t95\t寒食帖\n"
            "5\t1\t2\t1\t1\t1\t320\t240\t120\t32\t95\tunrelated\n"
        )

        candidates = module.ocr_line_candidates(tsv, ["寒食帖"])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["matched_terms"], ["寒食帖"])
        self.assertAlmostEqual(candidates[0]["center_x"], 130.0)
        self.assertAlmostEqual(candidates[0]["center_y"], 60.0)

    def test_tesseract_quote_token_does_not_merge_following_rows(self) -> None:
        module = load_module()
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t100\t100\t10\t20\t90\t\"\n"
            "5\t1\t2\t1\t1\t1\t160\t160\t96\t32\t95\t寒食帖\n"
        )

        words = module.parse_tesseract_tsv_words(tsv)
        candidates = module.ocr_line_candidates(tsv, ["寒食帖"])

        self.assertEqual([word["text"] for word in words], ['"', "寒食帖"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["matched_terms"], ["寒食帖"])

    def test_play_control_is_bound_only_to_nearby_card_identity(self) -> None:
        module = load_module()
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            # Exact source title and author surround the first card's play control.
            "5\t1\t1\t1\t1\t1\t210\t120\t180\t35\t95\t一个人的能力\n"
            "5\t1\t2\t1\t1\t1\t200\t610\t220\t35\t95\tNLP大师-罗伯特迪尔\n"
            # Our later summary repeats the title but is too far from either card.
            "5\t1\t3\t1\t1\t1\t640\t900\t260\t35\t95\t一个人的能力是怎么来的\n"
            # An unrelated second card has no local identity evidence.
            "5\t1\t4\t1\t1\t1\t610\t300\t180\t35\t95\tTED英语演讲\n"
        )
        plays = [
            {"text": "visible video play control", "matched_terms": [], "center_x": 200.0, "center_y": 230.0, "score": 64},
            {"text": "visible video play control", "matched_terms": [], "center_x": 480.0, "center_y": 230.0, "score": 64},
        ]
        terms = ["一个人的能力是怎么来的", "NLP大师-罗伯特迪尔茨"]

        candidates = module.associate_play_candidates_with_identity(tsv, plays, terms, 1)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["center_x"], 200.0)
        self.assertEqual(candidates[0]["kind"], "play_control")
        self.assertIn("一个人的能力是怎么来的", candidates[0]["matched_terms"])
        self.assertNotIn("TED英语演讲", candidates[0]["text"])

    def test_identity_binding_rejects_right_aligned_play_control(self) -> None:
        module = load_module()
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t720\t220\t180\t35\t95\tExact title\n"
        )
        plays = [
            {
                "text": "visible video play control",
                "kind": "play_control",
                "matched_terms": [],
                "center_x": 480.0,
                "center_y": 150.0,
                "score": 64,
            }
        ]

        candidates = module.associate_play_candidates_with_identity(
            tsv,
            plays,
            ["Exact title"],
            1,
            source_side_width=350.0,
        )

        self.assertEqual(candidates, [])

    def test_exact_cover_match_returns_source_scoped_click_target(self) -> None:
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV is not installed")
        module = load_module()
        rng = np.random.default_rng(42)
        cover = rng.integers(0, 256, size=(240, 180), dtype=np.uint8)
        screenshot = np.full((700, 1000), 235, dtype=np.uint8)
        displayed = cv2.resize(cover, (90, 120), interpolation=cv2.INTER_AREA)
        region = {"left": 300, "top": 50, "width": 690, "height": 600}
        screenshot[150:270, 350:440] = displayed

        with tempfile.TemporaryDirectory() as tmp:
            screenshot_path = Path(tmp) / "screen.png"
            cover_path = Path(tmp) / "cover.png"
            cv2.imwrite(str(screenshot_path), screenshot)
            cv2.imwrite(str(cover_path), cover)
            candidates = module.exact_cover_candidates(
                screenshot_path,
                cover_path,
                region=region,
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["kind"], "exact_cover")
        self.assertGreaterEqual(candidates[0]["match_confidence"], 0.70)
        self.assertAlmostEqual(candidates[0]["center_x"], 95.0, delta=3.0)
        self.assertAlmostEqual(candidates[0]["center_y"], 160.0, delta=3.0)

    def test_play_control_preserves_tesseract_reading_order_across_baselines(self) -> None:
        module = load_module()
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            # Deliberately vary the baselines. Sorting by top would scramble
            # this source title even though TSV order is correct.
            "5\t1\t1\t1\t1\t1\t200\t18\t20\t25\t95\t昨\n"
            "5\t1\t1\t1\t1\t2\t224\t12\t20\t25\t95\t天\n"
            "5\t1\t1\t1\t1\t3\t248\t20\t20\t25\t95\t的\n"
            "5\t1\t1\t1\t1\t4\t272\t14\t20\t25\t95\t自\n"
            "5\t1\t1\t1\t1\t5\t296\t10\t20\t25\t95\t己\n"
        )
        plays = [
            {
                "text": "visible video play control",
                "matched_terms": [],
                "center_x": 160.0,
                "center_y": 96.0,
                "score": 64,
            }
        ]

        candidates = module.associate_play_candidates_with_identity(
            tsv,
            plays,
            ["昨天的自己"],
            1,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["matched_terms"], ["昨天的自己"])

    def test_fuzzy_identity_match_keeps_distinctive_source_chunks(self) -> None:
        module = load_module()

        matched, score = module.match_identity_terms(
            "一个人的能力 NLP大师 罗伯特迪尔欧",
            ["一个人的能力是怎么来的", "NLP大师-罗伯特迪尔茨"],
        )

        self.assertEqual(matched, ["一个人的能力是怎么来的", "NLP大师-罗伯特迪尔茨"])
        self.assertGreaterEqual(score, 12)

    def test_pipewire_stream_is_limited_to_wechat_and_display(self) -> None:
        module = load_module()
        payload = [
            {
                "id": 10,
                "info": {
                    "props": {
                        "media.class": "Stream/Output/Audio",
                        "application.process.binary": "firefox",
                        "object.serial": 100,
                        "window.x11.display": ":97",
                    }
                },
            },
            {
                "id": 68,
                "info": {
                    "props": {
                        "media.class": "Stream/Output/Audio",
                        "application.process.binary": "WeChatAppEx",
                        "application.process.id": 899390,
                        "object.serial": 644,
                        "window.x11.display": ":97",
                    }
                },
            },
        ]
        completed = mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")

        with mock.patch.object(module, "run", return_value=completed):
            stream = module.find_wechat_audio_stream(":97")

        self.assertEqual(stream, {"node_id": 68, "serial": 644, "process_id": 899390})

    def test_audio_stream_wait_starts_verified_player_once(self) -> None:
        module = load_module()
        stream = {"node_id": 68, "serial": 644, "process_id": 899390}
        completed = mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(
            module,
            "find_wechat_audio_stream",
            side_effect=[RuntimeError("not started"), stream],
        ), mock.patch.object(module, "run", return_value=completed) as run, mock.patch.object(
            module.time, "sleep"
        ):
            result = module.wait_for_wechat_audio_stream(
                display=":97",
                window={"x": 100, "y": 50, "width": 800, "height": 600},
                env={"DISPLAY": ":97"},
                timeout=4,
            )

        self.assertEqual(result, stream)
        run.assert_called_once()
        self.assertIn("click", run.call_args.args[0])

    def test_source_bound_card_reports_player_unavailable(self) -> None:
        module = load_module()
        gui = mock.Mock()
        gui.run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        window = mock.Mock(width=1000, height=700, wid="100", x=20, y=30)
        candidate = {
            "text": "identity-bound video card",
            "kind": "play_control",
            "matched_terms": ["Exact title"],
            "center_x": 220.0,
            "center_y": 230.0,
            "score": 100,
        }

        with mock.patch.object(module, "jump_to_latest_message", return_value=True), mock.patch.object(
            module, "capture_message_pane_tsv", return_value="tsv"
        ), mock.patch.object(
            module, "exact_cover_candidates", return_value=[]
        ), mock.patch.object(module, "ocr_line_candidates", return_value=[]), mock.patch.object(
            module, "play_button_candidates", return_value=[]
        ), mock.patch.object(
            module, "associate_play_candidates_with_identity", return_value=[candidate]
        ), mock.patch.object(module, "deduplicate_click_candidates", return_value=[candidate]), mock.patch.object(
            module, "wait_for_channels_window", return_value=None
        ) as wait_for_player:
            player, evidence = module.open_exact_card_from_visible_history(
                env={"DISPLAY": ":97"},
                gui=gui,
                main_window=window,
                output_dir=ROOT / "output" / "test-card-open",
                identity_terms=["Exact title"],
                min_term_matches=1,
                max_scrolls=1,
                scroll_clicks=1,
                player_open_timeout=8,
            )

        self.assertIsNone(player)
        self.assertEqual(evidence["status"], "source_card_found_player_unavailable")
        self.assertTrue(evidence["source_card_found"])
        self.assertEqual(evidence["matched_terms"], ["Exact title"])
        self.assertEqual(wait_for_player.call_args.kwargs["timeout"], 8)


if __name__ == "__main__":
    unittest.main()
