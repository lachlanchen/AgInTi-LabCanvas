import importlib.util
from contextlib import nullcontext
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_sender():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_android_send.py"
    scripts = str(path.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    android_scripts = str(ROOT / "agentic_tools" / "android_device_agent" / "scripts")
    if android_scripts not in sys.path:
        sys.path.insert(0, android_scripts)
    spec = importlib.util.spec_from_file_location("wechat_android_send_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WechatAndroidSendTests(unittest.TestCase):
    def test_target_aliases_accept_count_suffix_but_not_short_substring(self):
        module = load_sender()
        aliases = module.target_aliases(
            {
                "name": "Shares鏈接",
                "expected_title": "Shares鏈接",
                "expected_title_aliases": ["Shares", "鏈接"],
            }
        )
        self.assertTrue(module.text_matches_alias("Shares鏈接(4)", aliases))
        self.assertTrue(module.text_matches_alias("Shares", aliases))
        self.assertFalse(module.text_matches_alias("鏈接和其他内容", ("鏈接",)))

    def test_target_aliases_tolerate_traditional_title_and_dash_ocr(self):
        module = load_sender()
        aliases = module.target_aliases(
            {
                "name": "MEMO写作—外语—挣钱",
                "expected_title": "MEMO写作—外语—挣钱",
            }
        )

        self.assertTrue(
            module.text_matches_alias("S88) MEMO 寫 作 一 外 語 一 掙 錢", aliases)
        )
        self.assertFalse(module.text_matches_alias("MEMO 写作一外语一赚钱", aliases))
        self.assertTrue(module.text_matches_alias("MEMO 写作一外一挣钱", aliases))

    def test_readable_android_filename_preserves_meaningful_basename(self):
        module = load_sender()

        self.assertEqual(
            module.readable_android_filename(
                "/private/task/output/2026-08-22-recent-items.zh.pdf"
            ),
            "2026-08-22-recent-items.zh.pdf",
        )
        self.assertEqual(
            module.readable_android_filename("每日研究：类器官与成像.pdf"),
            "每日研究_类器官与成像.pdf",
        )

    def test_component_state_prevents_duplicate_delivery(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-1",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            component = sender.text_component("hello")
            sender.mark_component(component, "sent", {"message": "must not persist"})

            self.assertEqual(sender.component_status(component["key"]), "sent")
            with sqlite3.connect(sender.state_db) as conn:
                details = json.loads(
                    conn.execute(
                        "SELECT details_json FROM components WHERE component_key = ?",
                        (component["key"],),
                    ).fetchone()[0]
                )
            self.assertNotIn("message", details)

    def test_ensure_exact_chat_taps_only_matching_ocr_row_and_verifies_header(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={
                    "name": "Shares鏈接",
                    "expected_title": "Shares鏈接",
                    "expected_title_aliases": ["Shares"],
                },
                task_id="task-2",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "screen.png"
            screen.write_bytes(b"png")
            match = module.OcrLine("Shares鏈接", 170, 740, 430, 815)
            with mock.patch.object(sender, "screenshot", return_value=screen), mock.patch.object(
                sender, "current_chat_matches", side_effect=[False, True]
            ), mock.patch.object(sender, "find_target_line", return_value=match), mock.patch.object(
                sender, "shell"
            ) as shell, mock.patch.object(sender_module_time(module), "sleep"):
                result = sender.ensure_exact_chat()

            self.assertEqual(result, screen)
            shell.assert_called_once_with(["input", "tap", "500", str(match.center_y)])

    def test_find_target_line_retries_with_enhanced_ocr(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={
                    "name": "MEMO写作—外语—挣钱",
                    "expected_title": "MEMO写作—外语—挣钱",
                },
                task_id="task-enhanced-ocr",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "screen.png"
            screen.write_bytes(b"png")
            expected = module.OcrLine("MEMO 寫 作 一 外 語 一 掙 錢", 90, 400, 600, 470)
            with mock.patch.object(module, "ocr_lines", return_value=[]), mock.patch.object(
                module, "enhanced_ocr_lines", return_value=[expected]
            ) as enhanced:
                result = sender.find_target_line(screen)

            self.assertEqual(result, expected)
            enhanced.assert_called_once_with(screen)

    def test_find_target_line_reconstructs_split_same_row_title(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={
                    "name": "MEMO写作—外语—挣钱",
                    "expected_title": "MEMO写作—外语—挣钱",
                },
                task_id="task-split-title",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "screen.png"
            screen.write_bytes(b"png")
            fragments = [
                module.OcrLine("MEMO 写 作 一 外", 208, 385, 531, 427),
                module.OcrLine("一 挣 钱", 580, 385, 715, 426),
                module.OcrLine("上午 9:18", 912, 382, 1034, 410),
                module.OcrLine("[文件] recent-items.pdf", 209, 446, 881, 489),
            ]
            with mock.patch.object(
                module, "ocr_lines", return_value=fragments
            ), mock.patch.object(module, "enhanced_ocr_lines") as enhanced:
                result = sender.find_target_line(screen)

            self.assertIsNotNone(result)
            self.assertEqual(result.text, "MEMO 写 作 一 外 一 挣 钱")
            self.assertEqual(result.center_y, 406)
            enhanced.assert_not_called()

    def test_parse_ocr_tsv_scales_enhanced_coordinates_back_to_device(self):
        module = load_sender()
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t150\t600\t300\t90\t90\tMEMO\n"
            "5\t1\t1\t1\t1\t2\t480\t600\t150\t90\t90\t写作\n"
        )

        lines = module.parse_ocr_tsv(tsv, coordinate_scale=1.5)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "MEMO 写作")
        self.assertEqual((lines[0].left, lines[0].top), (100, 400))
        self.assertEqual((lines[0].right, lines[0].bottom), (420, 460))

    def test_successful_file_send_is_not_failed_by_post_send_chat_restore(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "memo.pdf"
            artifact.write_bytes(b"pdf")
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "MEMO写作—外语—挣钱", "expected_title": "MEMO写作—外语—挣钱"},
                task_id="task-final-file",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            with mock.patch.object(module, "require_tools"), mock.patch.object(
                module, "priority_android_control", return_value=nullcontext()
            ), mock.patch.object(sender, "wake_and_launch"), mock.patch.object(
                sender, "ensure_exact_chat"
            ) as ensure, mock.patch.object(
                sender,
                "send_file_component",
                return_value={"kind": "file", "status": "sent", "key": "file"},
            ):
                result = sender.send(messages=[], files=[artifact])

            self.assertTrue(result["ok"])
            self.assertEqual(result["components"][0]["status"], "sent")
            self.assertEqual(ensure.call_count, 1)

    def test_unknown_target_is_rejected_by_allowlist(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "targets.json"
            path.write_text(json.dumps({"EchoMind": {"expected_title": "EchoMind"}}))
            with self.assertRaises(SystemExit):
                module.load_target("Unknown", path)

    def test_media_store_uri_requires_exact_indexed_filename(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-3",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            response = mock.MagicMock(
                stdout="Row: 0 _id=36939, _display_name=LabCanvas_exact_report.pdf\n"
            )
            with mock.patch.object(sender, "shell", return_value=response) as shell:
                uri = sender.media_store_uri("LabCanvas_exact_report.pdf")

            self.assertEqual(uri, "content://media/external/file/36939")
            self.assertIn("_display_name=\\'LabCanvas_exact_report.pdf\\'", shell.call_args.args[0])

    def test_share_confirmation_uses_focused_title_ocr_after_full_screen_noise(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={
                    "name": "MEMO写作—外语—挣钱",
                    "expected_title": "MEMO写作—外语—挣钱",
                },
                task_id="task-confirmation-ocr",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "confirmation.png"
            screen.write_bytes(b"png")
            with mock.patch.object(
                module,
                "ocr_lines",
                return_value=[
                    module.OcrLine("MEMOS (F—Sa—i# (4A)", 0, 0, 100, 30),
                    module.OcrLine("取消", 300, 1850, 400, 1910),
                ],
            ), mock.patch.object(module, "image_size", return_value=(1080, 2116)), mock.patch.object(
                module, "run_checked", return_value=mock.MagicMock(stdout="")
            ) as run_checked, mock.patch.object(
                module,
                "ocr_plain",
                side_effect=["MEMO写作一外语一挣钱(4人)", ""],
            ):
                matched = sender.share_confirmation_matches_target(screen)

            self.assertTrue(matched)
            self.assertIn("-crop", run_checked.call_args.args[0])

    def test_share_search_result_does_not_select_query_text(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "lachlanchan", "expected_title": "陈苗"},
                task_id="task-share-search",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "search.png"
            screen.write_bytes(b"png")
            lines = [
                module.OcrLine("陈苗", 155, 250, 270, 310),
                module.OcrLine("陈苗", 198, 505, 286, 570),
                module.OcrLine("陈苗", 198, 657, 286, 721),
                module.OcrLine("包含: 陈苗", 196, 939, 338, 982),
            ]
            with mock.patch.object(module, "ocr_lines", return_value=lines), mock.patch.object(
                module, "image_size", return_value=(1080, 2160)
            ):
                match = sender.find_share_target_line(screen, search_results=True)

            self.assertIsNotNone(match)
            self.assertEqual(match.center_y, 537)

    def test_share_recipient_tap_uses_matched_horizontal_tile(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "lachlanchan", "expected_title": "陈苗"},
                task_id="task-share-tile",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            line = module.OcrLine("陈苗", 671, 672, 730, 714)
            with mock.patch.object(sender, "shell") as shell:
                sender.tap_share_target(line)

            shell.assert_called_once_with(["input", "tap", "700", "693"])

    def test_share_confirmation_rejects_search_results_screen(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "lachlanchan", "expected_title": "陈苗"},
                task_id="task-no-false-confirmation",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "search.png"
            screen.write_bytes(b"png")
            with mock.patch.object(
                module,
                "ocr_lines",
                return_value=[module.OcrLine("陈苗", 198, 505, 286, 570)],
            ), mock.patch.object(module, "image_size", return_value=(1080, 2160)):
                matched = sender.share_confirmation_matches_target(screen)

            self.assertFalse(matched)

    def test_share_confirmation_preserves_exact_short_alias_line_in_crop(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "lachlanchan", "expected_title": "陈苗"},
                task_id="task-focused-short-alias",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "confirmation.png"
            screen.write_bytes(b"png")
            initial = [module.OcrLine("取消", 300, 1850, 400, 1910)]
            focused = [
                module.OcrLine("陈 苗", 140, 143, 410, 409),
                module.OcrLine("report.pdf", 320, 607, 600, 666),
            ]
            with mock.patch.object(
                module, "ocr_lines", side_effect=[initial, focused]
            ), mock.patch.object(
                module, "image_size", return_value=(1080, 2160)
            ), mock.patch.object(
                module, "run_checked", return_value=mock.MagicMock(stdout="")
            ), mock.patch.object(module, "ocr_plain") as plain:
                matched = sender.share_confirmation_matches_target(screen)

            self.assertTrue(matched)
            plain.assert_not_called()

    def test_wake_and_launch_closes_logged_device_page_before_main_surface(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-webwx-recovery",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            components = [
                (module.PACKAGE, ".plugin.webwx.ui.WebWXLogoutUI"),
                (module.PACKAGE, ".ui.LauncherUI"),
            ]
            with mock.patch.object(sender, "shell") as shell, mock.patch.object(
                sender, "launch_wechat_main"
            ) as launch, mock.patch.object(
                sender, "current_component", side_effect=components
            ), mock.patch.object(sender, "screenshot"), mock.patch.object(
                sender_module_time(module), "sleep"
            ):
                sender.wake_and_launch()

            self.assertEqual(launch.call_count, 2)
            self.assertGreaterEqual(
                shell.call_args_list.count(
                    mock.call(["cmd", "statusbar", "collapse"], check=False)
                ),
                2,
            )
            shell.assert_any_call(["input", "tap", "55", "132"], check=False)

    def test_collapse_system_overlays_is_fail_closed_visual_normalization(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-overlay-collapse",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            with mock.patch.object(sender, "shell") as shell, mock.patch.object(
                sender_module_time(module), "sleep"
            ):
                sender.collapse_system_overlays()

            shell.assert_called_once_with(
                ["cmd", "statusbar", "collapse"], check=False
            )

    def test_current_component_reads_exact_foreground_activity(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-component",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            response = mock.MagicMock(
                stdout=(
                    "mResumedActivity: ActivityRecord{x u0 "
                    "com.tencent.mm/.plugin.webwx.ui.WebWXLogoutUI t1}"
                )
            )
            with mock.patch.object(sender, "shell", return_value=response):
                component = sender.current_component()

            self.assertEqual(
                component,
                ("com.tencent.mm", ".plugin.webwx.ui.WebWXLogoutUI"),
            )

    def test_green_action_center_ignores_heading_and_finds_button(self):
        module = load_sender()
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            image = Image.new("RGB", (1080, 2116), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((530, 1710, 840, 1845), fill=(7, 193, 96))
            path = Path(tmp) / "confirm.png"
            image.save(path)

            point = module.green_action_center(path, min_y_ratio=0.65)

        self.assertIsNotNone(point)
        self.assertTrue(650 <= point[0] <= 730)
        self.assertTrue(1760 <= point[1] <= 1800)


def sender_module_time(module):
    return module.time
