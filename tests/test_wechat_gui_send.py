import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_wechat_gui_send():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"
    spec = importlib.util.spec_from_file_location("wechat_gui_send_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
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
        self.assertFalse(target.allow_search)
        self.assertEqual(target.fallback_clicks, ((165, 100), (240, 335), (165, 170)))
        candidates = module.target_click_candidates(target)
        self.assertEqual(candidates[:4], [
            ("result_click", (165, 100)),
            ("result_click_row_center", (165, 74)),
            ("result_click_title_offset", (200, 74)),
            ("result_click_preview_offset", (200, 100)),
        ])
        self.assertIn(("fallback_click_2", (240, 335)), candidates)
        self.assertIn(("fallback_click_3", (165, 170)), candidates)

    def test_explicit_click_candidates_try_fallback_before_derived_points(self):
        module = load_wechat_gui_send()
        target = module.TargetSpec(
            name="EchoMind",
            query="EchoMind",
            expected_title="EchoMind",
            result_click=(165, 100),
            fallback_clicks=((165, 170),),
        )

        candidates = module.target_explicit_click_candidates(target)

        self.assertEqual(candidates[0], ("result_click", (165, 100)))
        self.assertEqual(candidates[1], ("fallback_click_1", (165, 170)))
        self.assertIn(("result_click_row_center", (165, 74)), candidates[2:])

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
        self.assertEqual(sum(1 for call in calls if call[0] == "tesseract"), 2)

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
        self.assertEqual(result["compose_window"]["width"], 1000)

    def test_title_guard_accepts_popup_chat_window(self):
        module = load_wechat_gui_send()
        original_run = module.run
        crops = []
        try:
            def fake_run(command, *, env, check=True):
                if command[0] == "convert":
                    crops.append(command[3])
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command[0] == "tesseract":
                    return subprocess.CompletedProcess(command, 0, "🍓我的设备 (4)", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.verify_opened_title(
                {},
                module.Window("popup", 649, 206, 623, 666),
                Path("/tmp/screen.png"),
                module.TargetSpec(
                    name="🍓我的设备",
                    query="我的设备",
                    expected_title="🍓我的设备",
                    expected_title_aliases=("我的设备",),
                ),
                Path("/tmp/title.png"),
                "result_click_double",
            )
        finally:
            module.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["compose_window"]["wid"], "popup")
        self.assertTrue(crops)
        self.assertIn("+667+241", crops[0])

    def test_title_guard_prefers_native_window_title(self):
        module = load_wechat_gui_send()
        original_run = module.run
        calls = []
        try:
            def fake_run(command, *, env, check=True):
                calls.append(command)
                if command[:2] == ["xdotool", "getwindowname"]:
                    return subprocess.CompletedProcess(command, 0, "🍓我的设备\n", "")
                if command[0] == "tesseract":
                    return subprocess.CompletedProcess(command, 0, "bad ocr", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.verify_opened_title(
                {},
                module.Window("popup", 649, 206, 623, 666),
                Path("/tmp/screen.png"),
                module.TargetSpec(
                    name="🍓我的设备",
                    query="我的设备",
                    expected_title="🍓我的设备",
                    expected_title_aliases=("我的设备",),
                ),
                Path("/tmp/title.png"),
                "result_click_double",
            )
        finally:
            module.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["window_title"], "🍓我的设备")
        self.assertTrue(any(call[0] == "tesseract" for call in calls))

    def test_title_guard_rejects_ai_search_native_window_title(self):
        module = load_wechat_gui_send()
        original_run = module.run
        calls = []
        try:
            def fake_run(command, *, env, check=True):
                calls.append(command)
                if command[:2] == ["xdotool", "getwindowname"]:
                    return subprocess.CompletedProcess(command, 0, "AI Search - 我的设备\n", "")
                if command[0] == "tesseract":
                    return subprocess.CompletedProcess(command, 0, "AI Search - 我的设备", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.verify_opened_title(
                {},
                module.Window("popup", 649, 206, 623, 666),
                Path("/tmp/screen.png"),
                module.TargetSpec(
                    name="🍓我的设备",
                    query="我的设备",
                    expected_title="🍓我的设备",
                    expected_title_aliases=("我的设备",),
                ),
                Path("/tmp/title.png"),
                "result_click_double",
            )
        finally:
            module.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(result["surface_reject_reason"], "ai-search")
        self.assertTrue(any(call[0] == "tesseract" for call in calls))

    def test_title_guard_rejects_ai_search_ocr_match(self):
        module = load_wechat_gui_send()
        original_run = module.run
        try:
            def fake_run(command, *, env, check=True):
                if command[:2] == ["xdotool", "getwindowname"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command[0] == "tesseract":
                    return subprocess.CompletedProcess(command, 0, "我的设备 - Search\nAsk a follow-up...\n问AI", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.verify_opened_title(
                {},
                module.Window("popup", 649, 206, 623, 666),
                Path("/tmp/screen.png"),
                module.TargetSpec(
                    name="🍓我的设备",
                    query="我的设备",
                    expected_title="🍓我的设备",
                    expected_title_aliases=("我的设备",),
                ),
                Path("/tmp/title.png"),
                "result_click_double",
            )
        finally:
            module.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(result["surface_reject_reason"], "search-webview")

    def test_title_guard_rejects_matching_title_with_ai_search_surface(self):
        module = load_wechat_gui_send()
        original_run = module.run
        try:
            def fake_run(command, *, env, check=True):
                if command[:2] == ["xdotool", "getwindowname"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command[0] == "tesseract":
                    path = str(command[1])
                    if "-surface-" in path:
                        return subprocess.CompletedProcess(command, 0, "AI Search - 我的设备\nAsk a follow-up...\n问AI", "")
                    return subprocess.CompletedProcess(command, 0, "🍓我的设备", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.verify_opened_title(
                {},
                module.Window("main", 489, 193, 1020, 739),
                Path("/tmp/screen.png"),
                module.TargetSpec(
                    name="🍓我的设备",
                    query="我的设备",
                    expected_title="🍓我的设备",
                    expected_title_aliases=("我的设备",),
                ),
                Path("/tmp/title.png"),
                "result_click_double",
            )
        finally:
            module.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(result["surface_reject_reason"], "ai-search")
        self.assertIn("AI Search", result["surface_ocr_text"])

    def test_detect_wechat_locked_from_visible_screen(self):
        module = load_wechat_gui_send()
        original_run = module.run
        try:
            def fake_run(command, *, env, check=True):
                if command[0] == "tesseract":
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        "Weixin for Linux is locked. Unlock on Phone",
                        "",
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            result = module.detect_wechat_locked(
                {},
                module.Window("1", 0, 0, 1000, 700),
                Path("/tmp/screen.png"),
                Path("/tmp/locked.png"),
            )
        finally:
            module.run = original_run

        self.assertTrue(result["locked"])
        self.assertIn("Weixin for Linux is locked", result["ocr_text"])

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

    def test_run_check_false_handles_missing_gui_tool(self):
        module = load_wechat_gui_send()
        with mock.patch.object(module.subprocess, "run", side_effect=FileNotFoundError("missing")):
            result = module.run(["xdotool", "search", "--class", "wechat"], env={}, check=False)

        self.assertEqual(result.returncode, 127)
        self.assertIn("missing", result.stderr)

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

    def test_open_target_falls_back_after_failed_open_click(self):
        module = load_wechat_gui_send()
        target = module.TargetSpec(
            name="🍓我的设备",
            query="我的设备",
            expected_title="🍓我的设备",
            expected_title_aliases=("我的设备",),
            open_click=(135, 166),
            result_click=(165, 125),
        )
        original_click = module.click
        original_double_click = module.double_click
        original_screenshot = module.screenshot
        original_verify = module.verify_opened_title
        original_title_candidates = module.title_window_candidates
        original_sleep = module.time.sleep
        original_monotonic = module.time.monotonic
        calls = []
        clock = {"value": 0.0}
        try:
            module.click = lambda _env, x, y: calls.append(("click", x, y))
            module.double_click = lambda _env, x, y: calls.append(("double", x, y))
            module.screenshot = lambda _env, _path: None
            module.title_window_candidates = lambda _env, window: [window]
            module.time.sleep = lambda _seconds: None

            def fake_monotonic():
                clock["value"] += 10.0
                return clock["value"]

            def fake_verify(_env, window, _screenshot, _target, _crop, method):
                calls.append(("verify", method))
                return {
                    "ok": method == "result_click_direct_double",
                    "method": method,
                    "ocr_text": "🍓我的设备" if method == "result_click_direct_double" else "File Transfer",
                    "compose_window": module.window_to_dict(window),
                }

            module.time.monotonic = fake_monotonic
            module.verify_opened_title = fake_verify
            result = module.open_target(
                {},
                module.Window("1", 100, 200, 1000, 700),
                target,
                0,
                Path("/tmp"),
                "wechat-open-target-test",
                False,
                False,
            )
        finally:
            module.click = original_click
            module.double_click = original_double_click
            module.screenshot = original_screenshot
            module.verify_opened_title = original_verify
            module.title_window_candidates = original_title_candidates
            module.time.sleep = original_sleep
            module.time.monotonic = original_monotonic

        self.assertTrue(result["ok"])
        self.assertIn(("verify", "open_click"), calls)
        self.assertIn(("verify", "open_click_double"), calls)
        self.assertIn(("verify", "result_click_direct_double"), calls)

    def test_open_target_no_search_never_opens_search_box(self):
        module = load_wechat_gui_send()
        target = module.TargetSpec(
            name="🍓我的设备",
            query="我的设备",
            expected_title="🍓我的设备",
            expected_title_aliases=("我的设备",),
        )
        original_search = module.search_for_target
        original_key = module.key
        original_screenshot = module.screenshot
        original_verify = module.verify_opened_title
        original_title_candidates = module.title_window_candidates
        original_sleep = module.time.sleep
        original_monotonic = module.time.monotonic
        clock = {"value": 0.0}
        try:
            module.search_for_target = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search should not open"))  # type: ignore[assignment]
            module.key = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Return should not select search result"))  # type: ignore[assignment]
            module.screenshot = lambda _env, _path: None
            module.title_window_candidates = lambda _env, window: [window]
            module.time.sleep = lambda _seconds: None

            def fake_monotonic():
                clock["value"] += 10.0
                return clock["value"]

            def fake_verify(_env, window, _screenshot, _target, _crop, method):
                return {
                    "ok": False,
                    "method": method,
                    "ocr_text": "鏈接",
                    "compose_window": module.window_to_dict(window),
                }

            module.time.monotonic = fake_monotonic
            module.verify_opened_title = fake_verify
            result = module.open_target(
                {},
                module.Window("1", 100, 200, 1000, 700),
                target,
                0,
                Path("/tmp"),
                "wechat-open-no-search-test",
                False,
                True,
                False,
            )
        finally:
            module.search_for_target = original_search
            module.key = original_key
            module.screenshot = original_screenshot
            module.verify_opened_title = original_verify
            module.title_window_candidates = original_title_candidates
            module.time.sleep = original_sleep
            module.time.monotonic = original_monotonic

        self.assertFalse(result["ok"])
        self.assertTrue(result["search_disabled"])
        self.assertEqual(result["method"], "current")

    def test_target_search_requires_explicit_opt_in(self):
        module = load_wechat_gui_send()

        default_target = module.target_from_raw({"name": "EchoMind", "query": "EchoMind"})
        allowed_target = module.target_from_raw({"name": "EchoMind", "query": "EchoMind", "allow_search": True})
        blocked_target = module.target_from_raw({"name": "EchoMind", "query": "EchoMind", "allow_search": True, "no_search": True})

        self.assertFalse(default_target.allow_search)
        self.assertTrue(allowed_target.allow_search)
        self.assertFalse(blocked_target.allow_search)

    def test_close_non_target_wechat_windows_keeps_target_popup(self):
        module = load_wechat_gui_send()
        original_run = module.run
        closed = []
        try:
            def fake_run(command, *, env, check=True):
                if command[:3] == ["xdotool", "search", "--onlyvisible"]:
                    return subprocess.CompletedProcess(command, 0, "main\nfile\nmine\n", "")
                if command[:2] == ["xdotool", "getwindowgeometry"]:
                    wid = command[-1]
                    if wid == "main":
                        return subprocess.CompletedProcess(command, 0, "X=0\nY=0\nWIDTH=1000\nHEIGHT=700\n", "")
                    return subprocess.CompletedProcess(command, 0, "X=100\nY=100\nWIDTH=600\nHEIGHT=500\n", "")
                if command[:2] == ["xdotool", "getwindowname"]:
                    return subprocess.CompletedProcess(command, 0, "🍓我的设备\n" if command[-1] == "mine" else "File Transfer\n", "")
                if command[:2] == ["xdotool", "windowclose"]:
                    closed.append(command[-1])
                    return subprocess.CompletedProcess(command, 0, "", "")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run = fake_run
            module.close_non_target_wechat_windows(
                {},
                module.Window("main", 0, 0, 1000, 700),
                module.TargetSpec(
                    name="🍓我的设备",
                    query="我的设备",
                    expected_title="🍓我的设备",
                    expected_title_aliases=("我的设备",),
                ),
            )
        finally:
            module.run = original_run

        self.assertEqual(closed, ["file"])

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
