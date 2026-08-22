import importlib.util
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
                return_value=[module.OcrLine("MEMOS (F—Sa—i# (4A)", 0, 0, 100, 30)],
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
            shell.assert_any_call(["input", "tap", "55", "132"], check=False)

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
