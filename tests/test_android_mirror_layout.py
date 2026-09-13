import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools/android_device_agent/scripts/android_device_desktop.sh"


class AndroidMirrorLayoutTests(unittest.TestCase):
    def run_fit(self, *, dual=False, saved_serial=True, geometry="1440 2400",
                window_geometry="X=0\nY=0\nWIDTH=672\nHEIGHT=1344"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "calls.jsonl"
            if saved_serial:
                (root / "android-mix2s.serial").write_text("test-phone\n")
            executable = root / "xdotool"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "with open(os.environ['CALL_LOG'], 'a') as f:\n"
                "    f.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')\n"
                "if Path(sys.argv[0]).name != 'xdotool':\n"
                "    sys.exit(99)\n"
                "if sys.argv[1] == 'search':\n"
                "    if 'WeCom Virtual' in sys.argv[-1]:\n"
                "        if os.environ['DUAL'] == '1': print('222')\n"
                "        else: sys.exit(1)\n"
                "    else: print('111')\n"
                "elif sys.argv[1] == 'getdisplaygeometry':\n"
                "    print(os.environ['GEOMETRY'])\n"
                "elif sys.argv[1] == 'getwindowgeometry':\n"
                "    print(os.environ['WINDOW_GEOMETRY'])\n"
            )
            executable.chmod(0o755)
            for name in ("adb", "tmux", "scrcpy"):
                (root / name).symlink_to(executable)
            env = {
                **os.environ,
                "PATH": f"{root}:{os.environ['PATH']}",
                "ANDROID_SERIAL": "",
                "ANDROID_DEVICE_STATE_DIR": str(root),
                "ANDROID_DEVICE_DESKTOP_NAME": "android-mix2s",
                "CALL_LOG": str(log),
                "DUAL": "1" if dual else "0",
                "GEOMETRY": geometry,
                "WINDOW_GEOMETRY": window_geometry,
            }
            result = subprocess.run(
                ["bash", str(SCRIPT), "fit"], env=env,
                text=True, capture_output=True, timeout=5,
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            self.assertTrue(all(call[0] == "xdotool" for call in calls))
            return result, calls

    def test_fit_uses_live_canvas_and_never_controls_phone(self):
        result, calls = self.run_fit(geometry="1920 1080")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1920x1080", result.stdout)
        self.assertEqual(calls[-1], [
            "xdotool", "windowmove", "111", "0", "0",
            "windowsize", "111", "1920", "1080",
        ])

    def test_correct_geometry_does_not_resize_or_steal_focus(self):
        result, calls = self.run_fit(window_geometry="X=0\nY=0\nWIDTH=1440\nHEIGHT=2400")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already fits", result.stdout)
        self.assertFalse(any("windowmove" in call or "windowsize" in call for call in calls))

    def test_correct_size_with_wrong_position_is_recentered(self):
        result, calls = self.run_fit(window_geometry="X=200\nY=120\nWIDTH=1440\nHEIGHT=2400")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windowmove", calls[-1])

    def test_guard_is_host_only_and_skips_dual_layout(self):
        source = SCRIPT.read_text()
        guard = source.split("watch_single_fit() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('[[ "$(stored_layout)" != dual ]]', guard)
        self.assertIn('fit_single_window >/dev/null 2>&1', guard)
        self.assertNotIn('adb', guard)
        self.assertNotIn('launch_physical_app', guard)
        start = source.split("start_session() {", 1)[1].split('case "$ACTION"', 1)[0]
        self.assertEqual(start.count('ensure_fit_guard'), 2)

    def test_fit_preserves_dual_layout(self):
        result, calls = self.run_fit(dual=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("side-by-side layout unchanged", result.stderr)
        self.assertFalse(any("windowsize" in call for call in calls))

    def test_missing_identity_does_not_discover_phone(self):
        result, calls = self.run_fit(saved_serial=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("specify --serial", result.stderr)
        self.assertEqual(calls, [])

    def test_invalid_canvas_does_not_resize(self):
        result, calls = self.run_fit(geometry="0 0")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("windowsize" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
