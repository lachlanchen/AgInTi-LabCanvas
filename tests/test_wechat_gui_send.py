import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_wechat_gui_send():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"
    spec = importlib.util.spec_from_file_location("wechat_gui_send_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatGuiSendTests(unittest.TestCase):
    def test_target_fallback_clicks_preserve_order_without_duplicates(self):
        module = load_wechat_gui_send()

        target = module.target_from_raw(
            {
                "name": "EchoMind",
                "query": "EchoMind",
                "expected_title": "EchoMind",
                "expected_title_aliases": ["Echo Mind"],
                "allow_title_guard_fallback": True,
                "result_click": [165, 100],
                "fallback_clicks": [[165, 100], [240, 335], [165, 170]],
            }
        )

        self.assertEqual(target.expected_title_aliases, ("Echo Mind",))
        self.assertTrue(target.allow_title_guard_fallback)
        self.assertEqual(target.fallback_clicks, ((165, 100), (240, 335), (165, 170)))
        self.assertEqual(
            module.target_click_candidates(target),
            [
                ("result_click", (165, 100)),
                ("fallback_click_2", (240, 335)),
                ("fallback_click_3", (165, 170)),
            ],
        )

    def test_title_guard_does_not_accept_full_page_left_list_match(self):
        module = load_wechat_gui_send()
        calls = []
        original_run = module.run
        try:
            def fake_run(command, *, env, check=True):
                calls.append(command)
                if command[0] == "tesseract":
                    return subprocess.CompletedProcess(command, 0, "blank right pane", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.verify_opened_title(
                {},
                module.Window("1", 0, 0, 1000, 700),
                Path("/tmp/screen.png"),
                module.TargetSpec(name="EchoMind", query="EchoMind", expected_title="EchoMind"),
                Path("/tmp/title.png"),
                "current",
            )
        finally:
            module.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(sum(1 for call in calls if call[0] == "tesseract"), 1)

    def test_title_guard_accepts_configured_ocr_alias(self):
        module = load_wechat_gui_send()
        original_run = module.run
        try:
            def fake_run(command, *, env, check=True):
                if command[0] == "tesseract":
                    return subprocess.CompletedProcess(command, 0, "SR AEF (5)", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.verify_opened_title(
                {},
                module.Window("1", 0, 0, 1000, 700),
                Path("/tmp/screen.png"),
                module.TargetSpec(
                    name="懒人科研",
                    query="懒人科研",
                    expected_title="懒人科研",
                    expected_title_aliases=("SR AEF", "SRAEF"),
                ),
                Path("/tmp/title.png"),
                "current",
            )
        finally:
            module.run = original_run

        self.assertTrue(result["ok"])

    def test_relaxed_title_guard_does_not_allow_live_send_by_default(self):
        module = load_wechat_gui_send()
        original_focus = module.focus
        original_screenshot = module.screenshot
        original_open_target = module.open_target
        original_record_event = module.record_event
        try:
            module.focus = lambda *_args, **_kwargs: None
            module.screenshot = lambda _env, path: Path(path).write_bytes(b"screen")
            module.open_target = lambda *_args, **_kwargs: {"ok": False, "method": "current", "ocr_text": "鏈接"}
            module.record_event = lambda **_kwargs: None

            with self.assertRaisesRegex(RuntimeError, "Live sends do not allow relaxed title fallback"):
                module.send_one(
                    {},
                    module.Window("1", 0, 0, 1000, 700),
                    module.TargetSpec(
                        name="🍓我的设备",
                        query="我的设备",
                        expected_title="🍓我的设备",
                        expected_title_aliases=("我的设备",),
                        allow_title_guard_fallback=True,
                    ),
                    "reply",
                    True,
                    False,
                    0,
                    False,
                    True,
                    Path("/tmp"),
                    Path("/tmp/wechat-mirror.sqlite"),
                    1,
                )
        finally:
            module.focus = original_focus
            module.screenshot = original_screenshot
            module.open_target = original_open_target
            module.record_event = original_record_event

    def test_relaxed_title_guard_still_allows_dry_open_review(self):
        module = load_wechat_gui_send()
        original_focus = module.focus
        original_screenshot = module.screenshot
        original_open_target = module.open_target
        original_record_event = module.record_event
        try:
            module.focus = lambda *_args, **_kwargs: None
            module.screenshot = lambda _env, path: Path(path).write_bytes(b"screen")
            module.open_target = lambda *_args, **_kwargs: {"ok": False, "method": "current", "ocr_text": "鏈接"}
            module.record_event = lambda **_kwargs: None

            result = module.send_one(
                {},
                module.Window("1", 0, 0, 1000, 700),
                module.TargetSpec(
                    name="🍓我的设备",
                    query="我的设备",
                    expected_title="🍓我的设备",
                    expected_title_aliases=("我的设备",),
                    allow_title_guard_fallback=True,
                ),
                "reply",
                False,
                False,
                0,
                False,
                True,
                Path("/tmp"),
                Path("/tmp/wechat-mirror.sqlite"),
                1,
            )
        finally:
            module.focus = original_focus
            module.screenshot = original_screenshot
            module.open_target = original_open_target
            module.record_event = original_record_event

        self.assertEqual(result["status"], "dry-run-opened")

    def test_same_screenshot_detects_identical_files(self):
        module = load_wechat_gui_send()
        first = Path("/tmp/wechat-gui-send-same-a.png")
        second = Path("/tmp/wechat-gui-send-same-b.png")
        try:
            first.write_bytes(b"same")
            second.write_bytes(b"same")
            self.assertTrue(module.same_screenshot(first, second))
            second.write_bytes(b"different")
            self.assertFalse(module.same_screenshot(first, second))
        finally:
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
