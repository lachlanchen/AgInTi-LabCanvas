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

    def test_video_artifacts_use_reliable_generic_file_share_lane(self):
        module = load_sender()

        self.assertEqual(
            module.outbound_share_mime(Path("巴塔哥尼亚.mp4")),
            "application/octet-stream",
        )
        self.assertEqual(module.outbound_share_mime(Path("report.pdf")), "application/pdf")

    def test_paste_text_replaces_stale_composer_draft_before_pasting(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-retry-draft",
                state_db=Path(tmp) / "state.sqlite",
                output_dir=Path(tmp) / "output",
            )
            search = mock.Mock(stdout="4242\n")
            clipboard = mock.Mock()
            clipboard.stdin = mock.Mock()
            with mock.patch.object(
                module,
                "serialized_android_clipboard",
                return_value=nullcontext(),
            ), mock.patch.object(
                module,
                "run_checked",
                side_effect=[search, mock.Mock(), mock.Mock()],
            ) as run, mock.patch.object(
                module.subprocess,
                "Popen",
                return_value=clipboard,
            ), mock.patch.object(module.time, "sleep"):
                sender.paste_text("replacement")

        self.assertEqual(
            run.call_args_list[1].args[0][-4:],
            ["key", "--clearmodifiers", "ctrl+a", "BackSpace"],
        )
        self.assertEqual(
            run.call_args_list[2].args[0][-2:],
            ["--clearmodifiers", "ctrl+v"],
        )
        clipboard.stdin.write.assert_called_once_with(b"replacement")

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

    def test_file_component_persists_content_identity_for_echo_suppression(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "returned-video.mp4"
            source.write_bytes(b"exact outbound video bytes")
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "My Devices", "expected_title": "My Devices"},
                task_id="task-video",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )

            component = sender.file_component(source)
            sender.mark_component(component, "sent", {"filename": source.name})

            with sqlite3.connect(sender.state_db) as conn:
                value_hash, details_json = conn.execute(
                    "SELECT value_hash, details_json FROM components WHERE component_key = ?",
                    (component["key"],),
                ).fetchone()
            details = json.loads(details_json)
            identity = details["file_identity"]
            self.assertEqual(identity["name"], source.name)
            self.assertEqual(identity["size_bytes"], source.stat().st_size)
            self.assertEqual(identity["sha256"], value_hash)
            self.assertEqual(len(identity["md5"]), 32)

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
            ) as shell, mock.patch.object(
                sender, "wake_and_launch"
            ), mock.patch.object(sender_module_time(module), "sleep"):
                result = sender.ensure_exact_chat()

            self.assertEqual(result, screen)
            shell.assert_called_once_with(
                ["input", "touchscreen", "-d", "0", "tap", "500", str(match.center_y)],
                check=True,
            )

    def test_ensure_exact_chat_relaunches_after_back_reaches_launcher(self):
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
                task_id="task-relaunch",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            first = root / "chat.png"
            second = root / "list.png"
            match = module.OcrLine("Shares", 150, 620, 430, 700)
            with mock.patch.object(sender, "wake_and_launch"), mock.patch.object(
                sender, "screenshot", side_effect=[first, second, second]
            ), mock.patch.object(
                sender, "current_chat_matches", side_effect=[False, False, True]
            ), mock.patch.object(
                sender, "find_target_line", side_effect=[None, match]
            ), mock.patch.object(
                sender, "open_target_line", return_value=True
            ), mock.patch.object(
                sender, "keyevent"
            ), mock.patch.object(
                sender, "current_package", return_value="com.miui.home"
            ), mock.patch.object(
                sender, "launch_wechat_main"
            ) as launch, mock.patch.object(sender_module_time(module), "sleep"):
                result = sender.ensure_exact_chat()

            self.assertEqual(result, second)
            launch.assert_called_once()

    def test_search_and_open_chat_ignores_query_field_and_verifies_result(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={
                    "name": "Shares鏈接",
                    "query": "Shares鏈接",
                    "expected_title": "Shares鏈接",
                    "expected_title_aliases": ["Shares"],
                    "allow_search": True,
                },
                task_id="task-search",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "screen.png"
            query = module.OcrLine("Shares鏈接", 140, 80, 500, 145)
            result = module.OcrLine("Shares", 180, 430, 430, 500)
            with mock.patch.object(module, "image_size", return_value=(1080, 2160)), mock.patch.object(
                sender, "tap"
            ), mock.patch.object(sender, "paste_text") as paste, mock.patch.object(
                sender, "screenshot", return_value=screen
            ), mock.patch.object(
                module, "ocr_lines", return_value=[query, result]
            ), mock.patch.object(
                sender, "open_target_line", return_value=True
            ) as opened, mock.patch.object(sender_module_time(module), "sleep"):
                found = sender.search_and_open_chat(screen)

            self.assertEqual(found, screen)
            paste.assert_called_once_with("Shares鏈接")
            opened.assert_called_once_with(result)

    def test_search_and_open_chat_retries_current_alias_after_old_query_misses(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={
                    "name": "Shares鏈接",
                    "query": "Shares鏈接",
                    "expected_title": "Shares鏈接",
                    "expected_title_aliases": ["Shares"],
                    "allow_search": True,
                },
                task_id="task-search-renamed",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "screen.png"
            result = module.OcrLine("Shares", 180, 430, 430, 500)
            with mock.patch.object(
                module, "image_size", return_value=(1080, 2160)
            ), mock.patch.object(sender, "tap") as tap, mock.patch.object(
                sender, "paste_text"
            ) as paste, mock.patch.object(
                sender, "screenshot", return_value=screen
            ), mock.patch.object(
                module, "ocr_lines", side_effect=[[], [result]]
            ), mock.patch.object(
                module, "enhanced_ocr_lines", return_value=[]
            ), mock.patch.object(
                sender, "open_target_line", return_value=True
            ) as opened, mock.patch.object(sender_module_time(module), "sleep"):
                found = sender.search_and_open_chat(screen)

            self.assertEqual(found, screen)
            self.assertEqual(
                paste.call_args_list,
                [mock.call("Shares鏈接"), mock.call("Shares")],
            )
            self.assertIn(mock.call(928, 159, check=False), tap.call_args_list)
            opened.assert_called_once_with(result)

    def test_open_target_relocates_row_after_transient_wrong_chat(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "LazyResearch", "expected_title": "LazyResearch"},
                task_id="task-row-refresh",
                state_db=Path(tmp) / "state.sqlite",
                output_dir=Path(tmp) / "output",
            )
            original = module.OcrLine("LazyResearch", 190, 1800, 510, 1860)
            refreshed = module.OcrLine("LazyResearch", 190, 1380, 510, 1440)
            with mock.patch.object(sender, "tap") as tap, mock.patch.object(
                sender, "screenshot", side_effect=[Path("wrong.png"), Path("list.png"), Path("right.png")]
            ), mock.patch.object(
                sender, "current_chat_matches", side_effect=[False, True]
            ), mock.patch.object(
                sender, "find_target_line", return_value=refreshed
            ), mock.patch.object(sender, "keyevent"), mock.patch.object(
                sender_module_time(module), "sleep"
            ):
                matched = sender.open_target_line(original)

            self.assertTrue(matched)
            self.assertEqual(
                tap.call_args_list,
                [mock.call(500, original.center_y), mock.call(500, refreshed.center_y)],
            )

    def test_short_chat_title_uses_exact_centered_header_line(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "lachlanchan", "expected_title": "陈苗"},
                task_id="task-short-header",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            screen = root / "opened.png"
            screen.write_bytes(b"png")
            lines = [
                module.OcrLine("505", 30, 110, 210, 175),
                module.OcrLine("陈 苗", 545, 117, 635, 182),
            ]
            with (
                mock.patch.object(sender, "header_text", return_value="505 陈苗"),
                mock.patch.object(module, "image_size", return_value=(1080, 2160)),
                mock.patch.object(module, "ocr_lines", return_value=lines),
                mock.patch.object(module, "enhanced_header_text") as enhanced,
            ):
                matched = sender.current_chat_matches(screen)

            self.assertTrue(matched)
            enhanced.assert_not_called()

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
            ), mock.patch.object(
                sender, "device_lock_path", return_value=root / "physical.lock"
            ), mock.patch.object(sender, "wake_and_launch"), mock.patch.object(
                sender, "ensure_exact_chat"
            ) as ensure, mock.patch.object(
                sender,
                "send_file_component",
                return_value={"kind": "file", "status": "sent", "key": "file"},
            ), mock.patch.object(sender, "restore_wecom") as restore:
                result = sender.send(messages=[], files=[artifact])

            self.assertTrue(result["ok"])
            self.assertEqual(result["components"][0]["status"], "sent")
            self.assertTrue(result["wecom_restored"])
            self.assertEqual(result["restore_error"], "")
            self.assertEqual(ensure.call_count, 1)
            restore.assert_called_once_with()

    def test_share_picker_waits_for_transition_from_open_chat(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "Shares鏈接", "expected_title": "Shares鏈接"},
                task_id="task-share-wait",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            chat = root / "chat.png"
            picker = root / "picker.png"
            with mock.patch.object(
                sender, "screenshot", side_effect=[chat, picker]
            ), mock.patch.object(
                sender, "share_picker_visible", side_effect=[False, True, True]
            ), mock.patch.object(sender_module_time(module), "sleep"):
                result = sender.wait_for_share_picker(timeout_seconds=1.0)

            self.assertEqual(result, picker)

    def test_share_target_search_retries_allowlisted_aliases(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={
                    "name": "Shares鏈接",
                    "query": "Shares鏈接",
                    "expected_title": "Shares鏈接",
                    "expected_title_aliases": ["Shares", "鏈接"],
                },
                task_id="task-share-alias",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            picker = root / "picker.png"
            result_screen = root / "result.png"
            match = module.OcrLine("Shares", 180, 300, 430, 360)
            with mock.patch.object(
                module, "image_size", return_value=(1080, 2160)
            ), mock.patch.object(
                module, "ocr_lines", return_value=[]
            ), mock.patch.object(
                module, "find_action_line", return_value=None
            ), mock.patch.object(
                sender, "share_picker_visible", return_value=True
            ), mock.patch.object(sender, "tap"), mock.patch.object(
                sender, "paste_text"
            ) as paste, mock.patch.object(
                sender, "screenshot", return_value=result_screen
            ), mock.patch.object(
                sender, "find_share_target_line", side_effect=[None, match]
            ), mock.patch.object(sender_module_time(module), "sleep"):
                result = sender.search_share_target(picker)

            self.assertEqual(result, match)
            self.assertEqual(
                [call.args[0] for call in paste.call_args_list],
                ["Shares鏈接", "Shares"],
            )

    def test_file_share_commit_waits_until_exact_chat_reappears(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "Shares鏈接", "expected_title": "Shares鏈接"},
                task_id="task-file-commit",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            after = root / "after.png"
            component = {"file_identity": {"size_bytes": 1024}}
            with mock.patch.object(
                sender,
                "current_component",
                side_effect=[
                    (
                        module.PACKAGE,
                        "com.tencent.mm.ui.halfscreen.HalfScreenTransparentActivity",
                    ),
                    (module.PACKAGE, "com.tencent.mm.ui.LauncherUI"),
                ],
            ), mock.patch.object(
                sender, "screenshot", return_value=after
            ), mock.patch.object(
                module, "ocr_plain", return_value="Shares鏈接"
            ), mock.patch.object(
                sender, "current_chat_matches", return_value=True
            ), mock.patch.object(sender_module_time(module), "sleep"):
                result = sender.wait_for_file_share_commit(component)

            self.assertEqual(result, after)

    def test_file_share_commit_does_not_accept_open_confirmation_sheet(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "Shares鏈接", "expected_title": "Shares鏈接"},
                task_id="task-file-timeout",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            final = root / "confirmation.png"
            component = {"file_identity": {"size_bytes": 1024}}
            clock = mock.Mock(side_effect=[0.0, 0.0, 999.0])
            with mock.patch.dict(
                module.os.environ,
                {"WECHAT_ANDROID_FILE_COMMIT_TIMEOUT_SECONDS": "0.1"},
            ), mock.patch.object(
                sender, "current_component", return_value=(module.PACKAGE, "ShareImgUI")
            ), mock.patch.object(
                sender, "screenshot", return_value=final
            ), mock.patch.object(
                sender, "share_confirmation_matches_target", return_value=True
            ), mock.patch.object(
                sender_module_time(module), "monotonic", clock
            ), mock.patch.object(sender_module_time(module), "sleep"):
                with self.assertRaisesRegex(
                    module.AndroidWechatError, "confirmation remained open"
                ):
                    sender.wait_for_file_share_commit(component)

    def test_failed_wechat_send_still_restores_wecom(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-failed-send",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            with mock.patch.object(module, "require_tools"), mock.patch.object(
                module, "priority_android_control", return_value=nullcontext()
            ), mock.patch.object(
                sender, "device_lock_path", return_value=root / "physical.lock"
            ), mock.patch.object(
                sender,
                "wake_and_launch",
                side_effect=module.AndroidWechatError("launch failed"),
            ), mock.patch.object(sender, "restore_wecom") as restore:
                with self.assertRaisesRegex(module.AndroidWechatError, "launch failed"):
                    sender.send(messages=["hello"], files=[])

            restore.assert_called_once_with()

    def test_restore_wecom_waits_for_verified_foreground_package(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-restore",
                state_db=root / "state.sqlite",
                output_dir=root / "output",
            )
            with mock.patch.object(sender, "collapse_system_overlays"), mock.patch.object(
                sender, "dual_virtual_display_id", return_value=None
            ), mock.patch.object(
                sender, "shell"
            ) as shell, mock.patch.object(
                sender, "current_package", side_effect=["com.tencent.mm", module.WECOM_PACKAGE]
            ), mock.patch.object(sender_module_time(module), "sleep"):
                sender.restore_wecom()

            self.assertEqual(shell.call_args_list[0].args[0][:4], ["am", "start", "-W", "-f"])
            self.assertTrue(any("monkey" in call.args[0] for call in shell.call_args_list[1:]))

    def test_restore_wecom_preserves_dual_display_layout(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-dual-restore",
                state_db=Path(tmp) / "state.sqlite",
                output_dir=Path(tmp) / "output",
            )
            with mock.patch.object(sender, "collapse_system_overlays"), mock.patch.object(
                sender, "dual_virtual_display_id", return_value=7
            ), mock.patch.object(sender, "shell") as shell, mock.patch.object(
                sender,
                "component_on_display",
                return_value=(module.WECOM_PACKAGE, ".launch.WwMainActivity"),
            ), mock.patch.object(sender_module_time(module), "sleep"):
                sender.restore_wecom()

            command = shell.call_args_list[0].args[0]
            self.assertEqual(
                command[:6],
                ["am", "start", "-W", "--display", "7", "-f"],
            )
            self.assertIn(module.WECOM_MAIN_ACTIVITY, command)

    def test_current_component_uses_physical_display_in_split_mode(self):
        module = load_sender()
        payload = """Display #7 (activities from top to bottom):
    mResumedActivity: ActivityRecord{x u0 com.tencent.wework/.launch.WwMainActivity t2}
Display #0 (activities from top to bottom):
    mResumedActivity: ActivityRecord{y u0 com.tencent.mm/.ui.LauncherUI t1}
"""
        self.assertEqual(
            module.resumed_component_on_display(payload, 0),
            (module.PACKAGE, ".ui.LauncherUI"),
        )
        self.assertEqual(
            module.virtual_display_id_from_stack_list("displayId=0 displayId=7"),
            7,
        )

    def test_dual_display_uses_shared_android_ui_lock(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-dual-lock",
                state_db=Path(tmp) / "state.sqlite",
                output_dir=Path(tmp) / "output",
            )
            with mock.patch.object(
                sender, "dual_virtual_display_id", return_value=18
            ), mock.patch.object(
                sender,
                "component_on_display",
                return_value=(module.WECOM_PACKAGE, ".launch.WwMainActivity"),
            ):
                lock_path = sender.device_lock_path()

            self.assertEqual(lock_path, module.DEFAULT_DEVICE_LOCK)

    def test_physical_display_token_parser_and_screenshot_are_display_bound(self):
        module = load_sender()
        payload = (
            'Display 19260591652815745 (HWC display 0): port=129 '
            'pnpId=QCM displayName="jdi fhd video"\n'
        )
        self.assertEqual(
            module.physical_display_token_from_surface_flinger(payload),
            "19260591652815745",
        )
        with tempfile.TemporaryDirectory() as tmp:
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-physical-screen",
                state_db=Path(tmp) / "state.sqlite",
                output_dir=Path(tmp) / "output",
            )
            with mock.patch.object(
                sender,
                "physical_display_token",
                return_value="19260591652815745",
            ), mock.patch.object(sender, "adb_run") as adb_run:
                adb_run.return_value.stdout = b"png"
                path = sender.screenshot("bound")

            self.assertEqual(path.read_bytes(), b"png")
            adb_run.assert_called_once_with(
                [
                    "exec-out",
                    "screencap",
                    "-d",
                    "19260591652815745",
                    "-p",
                ],
                binary=True,
                timeout=20,
            )

    def test_single_display_keeps_shared_wecom_lock(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-single-lock",
                state_db=Path(tmp) / "state.sqlite",
                output_dir=Path(tmp) / "output",
            )
            with mock.patch.object(sender, "dual_virtual_display_id", return_value=None):
                lock_path = sender.device_lock_path()

            self.assertEqual(lock_path, module.DEFAULT_DEVICE_LOCK)

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

            shell.assert_called_once_with(
                ["input", "touchscreen", "-d", "0", "tap", "700", "693"],
                check=True,
            )

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
            shell.assert_any_call(
                ["input", "touchscreen", "-d", "0", "tap", "55", "132"],
                check=False,
            )

    def test_phone_input_is_explicitly_bound_to_physical_display_zero(self):
        module = load_sender()
        with tempfile.TemporaryDirectory() as tmp:
            sender = module.AndroidWechatSender(
                adb="adb",
                serial="device",
                target={"name": "EchoMind", "expected_title": "EchoMind"},
                task_id="task-display",
                state_db=Path(tmp) / "state.sqlite",
                output_dir=Path(tmp) / "output",
            )
            with mock.patch.object(sender, "shell") as shell:
                sender.keyevent(4, check=False)
                sender.tap(12, 34)
                sender.swipe(1, 2, 3, 4, 500, check=False)

            self.assertEqual(
                shell.call_args_list,
                [
                    mock.call(
                        ["input", "keyboard", "-d", "0", "keyevent", "4"],
                        check=False,
                    ),
                    mock.call(
                        ["input", "touchscreen", "-d", "0", "tap", "12", "34"],
                        check=True,
                    ),
                    mock.call(
                        [
                            "input",
                            "touchscreen",
                            "-d",
                            "0",
                            "swipe",
                            "1",
                            "2",
                            "3",
                            "4",
                            "500",
                        ],
                        check=False,
                    ),
                ],
            )

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

    def test_green_action_center_does_not_merge_selection_handle_with_send_button(self):
        module = load_sender()
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            image = Image.new("RGB", (1080, 2160), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((480, 970, 910, 1060), fill=(149, 236, 105))
            draw.ellipse((650, 1180, 710, 1260), fill=(7, 193, 96))
            draw.rectangle((918, 1232, 1052, 1318), fill=(7, 193, 96))
            path = Path(tmp) / "selected-text-and-send.png"
            image.save(path)

            box = module.green_action_box(path, min_y_ratio=0.45)
            point = module.green_action_center(path, min_y_ratio=0.45)

        self.assertEqual(box, (918, 1232, 1054, 1320))
        self.assertEqual(point, (986, 1276))

    def test_green_coverage_proves_composer_action_cleared(self):
        module = load_sender()
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            typed = Image.new("RGB", (1080, 2160), "white")
            ImageDraw.Draw(typed).rectangle((918, 1232, 1052, 1318), fill=(7, 193, 96))
            typed_path = root / "typed.png"
            typed.save(typed_path)
            sent_path = root / "sent.png"
            Image.new("RGB", (1080, 2160), "white").save(sent_path)
            box = module.green_action_box(typed_path, min_y_ratio=0.45)

            self.assertIsNotNone(box)
            self.assertGreater(module.green_coverage(typed_path, box), 0.90)
            self.assertEqual(module.green_coverage(sent_path, box), 0.0)


def sender_module_time(module):
    return module.time
