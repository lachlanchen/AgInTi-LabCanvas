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
    def test_native_share_menu_copies_only_exact_link_action(self) -> None:
        module = load_module()
        clipboard_reads = 0
        tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
               "5\t1\t1\t1\t1\t1\t90\t240\t180\t60\t95\t转发给朋友\n"
               "5\t1\t1\t1\t2\t1\t90\t450\t180\t60\t95\t复制链接\n")
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(module.shutil, "which", return_value="/usr/bin/xclip"), \
             mock.patch.object(module, "capture_identity_evidence", return_value={"matched": True}), \
             mock.patch.object(module.subprocess, "run") as write, \
             mock.patch.object(module.time, "sleep"), \
             mock.patch.object(module, "run") as run:
            def execute(command, **kwargs):
                nonlocal clipboard_reads
                output = ""
                if command[0] == "xclip":
                    clipboard_reads += 1
                    output = write.call_args.kwargs["input"] if clipboard_reads == 1 else "https://weixin.qq.com/sph/test1234"
                elif command[0] == "tesseract":
                    output = tsv
                return mock.Mock(stdout=output, returncode=0)
            run.side_effect = execute
            result = module.recover_share_link_from_player(
                player={"id": "20", "x": 100, "y": 100, "width": 920, "height": 890},
                env={"DISPLAY": ":97"}, output_dir=Path(tmp), identity_terms=["Exact title"], min_term_matches=1)
            self.assertEqual(result["status"], "verified")
            clicks = [call.args[0] for call in run.call_args_list if "click" in call.args[0]]
            self.assertEqual(len(clicks), 2)
            self.assertEqual(clicks[-1], ["xdotool", "mousemove", "700", "850", "click", "1"])
            self.assertNotIn("3", clicks[0])

    def test_copy_link_label_is_not_a_substring_of_another_action(self) -> None:
        module = load_module()
        tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
               "5\t1\t1\t1\t1\t1\t800\t820\t100\t20\t95\t复制链接后分享\n")
        self.assertEqual(module.copy_link_menu_candidates(tsv), [])

    def test_failed_menu_image_never_uses_stale_ocr(self) -> None:
        module = load_module()
        for failed_tool in ("import", "convert"):
            with self.subTest(failed_tool=failed_tool), tempfile.TemporaryDirectory() as tmp, \
                 mock.patch.object(module.shutil, "which", return_value="/usr/bin/xclip"), \
                 mock.patch.object(module, "capture_identity_evidence", return_value={"matched": True}), \
                 mock.patch.object(module.subprocess, "run") as write, \
                 mock.patch.object(module.time, "sleep"), \
                 mock.patch.object(module, "run") as run:
                def execute(command, **kwargs):
                    self.assertNotEqual(command[0], "tesseract")
                    output = write.call_args.kwargs["input"] if command[0] == "xclip" else ""
                    return mock.Mock(stdout=output, returncode=int(command[0] == failed_tool))
                run.side_effect = execute
                result = module.recover_share_link_from_player(
                    player={"id": "20", "x": 100, "y": 100, "width": 920, "height": 890},
                    env={"DISPLAY": ":97"}, output_dir=Path(tmp),
                    identity_terms=["Exact title"], min_term_matches=1)
                self.assertEqual(result["status"], "unavailable")

    def test_share_link_only_never_records_and_releases_player(self) -> None:
        module = load_module()
        gui = mock.Mock()
        gui.find_wechat_window.return_value = mock.Mock(wid="16")
        gui.open_target.return_value = {"ok": True}
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(module, "require_tools"), \
             mock.patch.object(module, "load_wechat_gui_module", return_value=gui), \
             mock.patch.object(module, "exclusive_gui_lock", side_effect=lambda *a, **k: nullcontext()), \
             mock.patch.object(module, "close_channels_players") as close, \
             mock.patch.object(module, "open_exact_card_from_visible_history", return_value=({"id": "20"}, {"status": "identity_verified"})), \
             mock.patch.object(module, "recover_share_link_from_player") as recover, \
             mock.patch.object(module, "capture_exact_player") as capture:
            gui.load_targets.return_value = ([mock.Mock()], {})
            args = dict(chat="Shares", targets_file=Path(tmp)/"targets.json", max_scrolls=8,
                        scroll_clicks=4, player_open_timeout=4, lock_timeout=3, object_id="exact-id",
                        title="Exact title", author="Author", identity_terms=["Author"], min_term_matches=1,
                        display=":97", output_dir=Path(tmp), interval=1, loss_polls=3, max_seconds=5,
                        audio_stream_timeout=2, expected_duration_seconds=0, share_link_only=True)
            recover.return_value = {"status": "unavailable", "error_code": "native_copy_link_action_missing"}
            with self.assertRaises(module.CaptureFailure) as error:
                module.capture_exact_card_from_chat(**args)
            self.assertEqual(error.exception.failure_stage, "share_link")
            self.assertEqual(close.call_count, 2)
            capture.assert_not_called()
            recover.return_value = {"status": "verified", "share_url": "https://weixin.qq.com/sph/test1234", "share_url_sha256": "hash"}
            result = module.capture_exact_card_from_chat(**args)
            self.assertEqual(result["status"], "share_link_recovered")
            self.assertEqual(close.call_count, 4)
            capture.assert_not_called()

    def test_unresponsive_player_cleanup_is_bounded_and_never_force_destroys(self) -> None:
        module = load_module()
        gui = mock.Mock()
        with mock.patch.object(module, "load_wechat_gui_module", return_value=gui), \
             mock.patch.object(module, "find_channels_window", return_value={"id": "20"}), \
             mock.patch.object(module, "run") as run, \
             mock.patch.object(module.time, "sleep"):
            with self.assertRaises(module.CaptureFailure) as error:
                module.close_channels_players({"DISPLAY": ":97"}, excluded_window_ids={"16"})
        self.assertEqual(error.exception.error_code, "finder_player_close_pending")
        gui.request_close.assert_called_once_with("20", display_name=":97", protected_window_ids={"16"})
        self.assertNotIn("windowclose", str(run.call_args_list))

    def test_card_identity_matches_traditional_ocr_to_simplified_metadata(self) -> None:
        module = load_module()
        if module.IDENTITY_T2S is None:
            self.skipTest("OpenCC is an optional OCR normalization dependency")
        terms = module.derive_identity_terms("文学史上最著名的一场雪", "何凯文讲英语")
        matches, _ = module.match_identity_terms("文學史上 最著名的一場雪 何凱文講英語", terms)
        self.assertIn("何凯文讲英语", matches)
        other, _ = module.match_identity_terms("另一个作者 其他视频", terms)
        self.assertEqual(other, [])

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

    def test_copy_link_menu_candidate_requires_explicit_action_label(self) -> None:
        module = load_module()
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t800\t300\t60\t24\t95\t复制\n"
            "5\t1\t1\t1\t1\t2\t862\t300\t60\t24\t95\t链接\n"
            "5\t1\t2\t1\t1\t1\t800\t340\t60\t24\t95\t转发\n"
        )

        candidates = module.copy_link_menu_candidates(tsv)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["label"], "复制链接")
        self.assertAlmostEqual(candidates[0]["center_x"], 861.0)
        self.assertAlmostEqual(candidates[0]["center_y"], 312.0)

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

    def test_latest_message_button_is_detected_without_ocr(self) -> None:
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV is not installed")
        module = load_module()
        image = np.full((700, 1000, 3), 242, dtype=np.uint8)
        region = {"left": 350, "top": 60, "width": 640, "height": 520}
        # A green outgoing bubble is a decoy. Its background is not white, so
        # it must not be mistaken for the latest-message control.
        image[455:525, 650:940] = (92, 225, 140)
        cv2.rectangle(image, (805, 540), (980, 575), (255, 255, 255), thickness=-1)
        cv2.putText(
            image,
            "Go to latest message",
            (820, 563),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (80, 190, 40),
            1,
            cv2.LINE_AA,
        )

        with tempfile.TemporaryDirectory() as tmp:
            screenshot = Path(tmp) / "latest.png"
            cv2.imwrite(str(screenshot), image)
            candidate = module.latest_message_button_candidate(screenshot, region=region)

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertAlmostEqual(candidate["center_x"], 890, delta=50)
        self.assertAlmostEqual(candidate["center_y"], 557, delta=20)

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
