from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "agentic_tools" / "virtual_desktop" / "launch_virtual_desktop.sh"
WECHAT = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_virtual_desktop.sh"


class VirtualDesktopLifecycleTests(unittest.TestCase):
    def test_scripts_are_valid_bash(self) -> None:
        for script in (LAUNCHER, WECHAT):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    ["bash", "-n", str(script)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_shared_launcher_requires_explicit_stale_recovery(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('--recover-stale-display) RECOVER_STALE_DISPLAY="1"', source)
        self.assertIn('[[ "$RECOVER_STALE_DISPLAY" == "1" ]]', source)
        self.assertIn('stop_exact_processes "Xvfb display $DISPLAY_ID"', source)
        self.assertIn('stop_exact_processes "x11vnc relay for $DISPLAY_ID"', source)

    def test_all_status_probes_are_bounded(self) -> None:
        launcher = LAUNCHER.read_text(encoding="utf-8")
        wechat = WECHAT.read_text(encoding="utf-8")
        self.assertIn('timeout "${PROBE_TIMEOUT_SECONDS}s" env DISPLAY="$DISPLAY_ID"', launcher)
        self.assertIsNone(
            re.search(
                r'^\s*DISPLAY="\$DISPLAY_ID" XAUTHORITY= xwininfo -root -tree',
                launcher,
                re.MULTILINE,
            )
        )
        self.assertIn('timeout "${X11_PROBE_TIMEOUT_SECONDS}s" env DISPLAY="$DISPLAY_ID"', wechat)
        self.assertIsNone(
            re.search(
                r'^\s*DISPLAY="\$DISPLAY_ID" XAUTHORITY= xdotool (search|getwindowgeometry)',
                wechat,
                re.MULTILINE,
            )
        )

    def test_wechat_stops_only_its_client_before_opted_in_display_recovery(self) -> None:
        source = WECHAT.read_text(encoding="utf-8")
        stale_probe_index = source.index(
            'if ! timeout "${X11_PROBE_TIMEOUT_SECONDS}s" env DISPLAY="$DISPLAY_ID"'
        )
        stop_index = source.index("if ! stop_stale_wechat", stale_probe_index)
        launch_index = source.index('"$ROOT/agentic_tools/virtual_desktop/launch_virtual_desktop.sh"')
        self.assertLess(stale_probe_index, stop_index)
        self.assertLess(stop_index, launch_index)
        self.assertIn("--recover-stale-display", source)
        self.assertIn("wechat_pids_on_display", source)

    def test_wechat_does_not_leak_lifecycle_lock_to_display_children(self) -> None:
        source = WECHAT.read_text(encoding="utf-8")
        self.assertIn('-- /bin/true 9>&- >"$LAUNCH_LOG"', source)

    def test_wechat_preserves_small_visible_login_window(self) -> None:
        source = WECHAT.read_text(encoding="utf-8")
        self.assertIn("wechat_visible_window()", source)
        self.assertIn(
            '[[ -z "$main_window" && -z "$visible_window" && "$AUTO_RECOVER_UNMAPPED" == "1" ]]',
            source,
        )
        self.assertIn("WeChat entry/login window healthy", source)


if __name__ == "__main__":
    unittest.main()
