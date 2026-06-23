import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_wechat_chatops_bridge():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"
    spec = importlib.util.spec_from_file_location("wechat_chatops_bridge_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WeChatChatOpsBridgeTests(unittest.TestCase):
    def test_send_file_rejects_locked_preflight_before_file_picker(self) -> None:
        module = load_wechat_chatops_bridge()
        calls: list[list[str]] = []
        original_run_gui = module.run_gui
        original_focus = module.focus
        original_detect = module.detect_wechat_locked
        original_sleep = module.time.sleep
        try:
            def fake_run_gui(command, *, env, check=True):
                calls.append(command)
                if command and command[0] == "import":
                    Path(command[-1]).write_bytes(b"png")
                return subprocess.CompletedProcess(command, 0, "", "")

            module.run_gui = fake_run_gui
            module.focus = lambda _env, _window: None
            module.time.sleep = lambda _seconds: None
            module.detect_wechat_locked = lambda _env, _window, _screenshot, crop: {
                "locked": True,
                "ocr_text": "Weixin for Linux is locked",
                "lock_crop": str(crop),
            }
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                file_path = tmp_path / "artifact.mp4"
                file_path.write_bytes(b"video")
                window = types.SimpleNamespace(x=0, y=0, width=1000, height=700)
                with self.assertRaises(SystemExit) as error:
                    module.send_file_current_chat({}, window, file_path, tmp_path, "manual-file")
        finally:
            module.run_gui = original_run_gui
            module.focus = original_focus
            module.detect_wechat_locked = original_detect
            module.time.sleep = original_sleep

        self.assertIn("WECHAT_LOCKED", str(error.exception))
        self.assertFalse(any(call[:2] == ["xdotool", "mousemove"] for call in calls))

    def test_send_file_rejects_locked_post_send_surface(self) -> None:
        module = load_wechat_chatops_bridge()
        calls: list[list[str]] = []
        lock_checks: list[str] = []
        original_run_gui = module.run_gui
        original_focus = module.focus
        original_paste = module.paste_text
        original_detect = module.detect_wechat_locked
        original_sleep = module.time.sleep
        try:
            def fake_run_gui(command, *, env, check=True):
                calls.append(command)
                if command and command[0] == "import":
                    Path(command[-1]).write_bytes(b"png")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_detect(_env, _window, screenshot, crop):
                lock_checks.append(Path(screenshot).name)
                locked = Path(screenshot).name.endswith("-sent.png")
                return {
                    "locked": locked,
                    "ocr_text": "Unlock on phone" if locked else "",
                    "lock_crop": str(crop),
                }

            module.run_gui = fake_run_gui
            module.focus = lambda _env, _window: None
            module.paste_text = lambda _env, _text: None
            module.time.sleep = lambda _seconds: None
            module.detect_wechat_locked = fake_detect
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                file_path = tmp_path / "artifact.mp4"
                file_path.write_bytes(b"video")
                window = types.SimpleNamespace(x=0, y=0, width=1000, height=700)
                with self.assertRaises(SystemExit) as error:
                    module.send_file_current_chat({}, window, file_path, tmp_path, "manual-file")
        finally:
            module.run_gui = original_run_gui
            module.focus = original_focus
            module.paste_text = original_paste
            module.detect_wechat_locked = original_detect
            module.time.sleep = original_sleep

        self.assertIn("WECHAT_LOCKED", str(error.exception))
        self.assertIn("manual-file-preflight.png", lock_checks)
        self.assertIn("manual-file-sent.png", lock_checks)
        self.assertTrue(any(call[:2] == ["xdotool", "key"] and call[2] == "Return" for call in calls))
        self.assertTrue(any(call[:2] == ["xdotool", "key"] and call[2] == "Escape" for call in calls))
        self.assertTrue(
            any(
                call[:2] == ["xdotool", "mousemove"]
                and call[2:5] == ["942", "666", "click"]
                for call in calls
            )
        )


if __name__ == "__main__":
    unittest.main()
