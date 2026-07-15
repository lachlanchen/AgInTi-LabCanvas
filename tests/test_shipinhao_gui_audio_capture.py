from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
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
        self.assertIn("一个人的能力是怎么来的", candidates[0]["matched_terms"])
        self.assertNotIn("TED英语演讲", candidates[0]["text"])

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
            "matched_terms": ["Exact title"],
            "center_x": 220.0,
            "center_y": 230.0,
            "score": 100,
        }

        with mock.patch.object(module, "jump_to_latest_message", return_value=True), mock.patch.object(
            module, "capture_message_pane_tsv", return_value="tsv"
        ), mock.patch.object(module, "ocr_line_candidates", return_value=[]), mock.patch.object(
            module, "play_button_candidates", return_value=[]
        ), mock.patch.object(
            module, "associate_play_candidates_with_identity", return_value=[candidate]
        ), mock.patch.object(module, "deduplicate_click_candidates", return_value=[candidate]), mock.patch.object(
            module, "wait_for_channels_window", return_value=None
        ):
            player, evidence = module.open_exact_card_from_visible_history(
                env={"DISPLAY": ":97"},
                gui=gui,
                main_window=window,
                output_dir=ROOT / "output" / "test-card-open",
                identity_terms=["Exact title"],
                min_term_matches=1,
                max_scrolls=1,
                scroll_clicks=1,
                player_open_timeout=2,
            )

        self.assertIsNone(player)
        self.assertEqual(evidence["status"], "source_card_found_player_unavailable")
        self.assertTrue(evidence["source_card_found"])
        self.assertEqual(evidence["matched_terms"], ["Exact title"])


if __name__ == "__main__":
    unittest.main()
