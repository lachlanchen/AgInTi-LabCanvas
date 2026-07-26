from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / "scripts"
    / "wechat_desktop_unlock_watchdog.py"
)
SPEC = importlib.util.spec_from_file_location("wechat_desktop_unlock_watchdog", SCRIPT)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)


def args(tmp: str) -> argparse.Namespace:
    root = Path(tmp)
    return argparse.Namespace(
        display=":97",
        serial="physical-phone",
        adb="adb",
        dry_run=False,
        flush_deferred=False,
        output_dir=root / "desktop",
        android_output_dir=root / "android",
        banner_tap="505,282",
        lock_tap="540,690",
        android_lock=root / "phone.lock",
        protected_package=list(watchdog.DEFAULT_PROTECTED_PACKAGES),
    )


class WeChatDesktopUnlockWatchdogTests(unittest.TestCase):
    def test_healthy_desktop_does_not_touch_phone(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(watchdog, "apply_desktop_keep_awake"),
            mock.patch.object(
                watchdog,
                "desktop_lock_state",
                return_value={"ok": True, "status": "unlocked"},
            ),
            mock.patch.object(watchdog, "require_serial") as require_serial,
            mock.patch.object(watchdog, "keep_android_awake") as keep_awake,
        ):
            result = watchdog.watchdog_once(args(tmp))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "noop")
        require_serial.assert_not_called()
        keep_awake.assert_not_called()

    def test_busy_wecom_relay_defers_without_switching_apps(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(watchdog, "apply_desktop_keep_awake"),
            mock.patch.object(
                watchdog,
                "desktop_lock_state",
                return_value={"ok": True, "status": "locked"},
            ),
            mock.patch.object(watchdog, "require_serial", return_value="physical-phone"),
            mock.patch.object(watchdog, "acquire_android_lease", return_value=None),
            mock.patch.object(watchdog, "unlock_desktop_from_mobile") as unlock,
        ):
            result = watchdog.watchdog_once(args(tmp))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "deferred_android_busy")
        unlock.assert_not_called()

    def test_echo_app_foreground_is_never_disrupted(self) -> None:
        lease = mock.MagicMock()
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(watchdog, "apply_desktop_keep_awake"),
            mock.patch.object(
                watchdog,
                "desktop_lock_state",
                return_value={"ok": True, "status": "locked"},
            ),
            mock.patch.object(watchdog, "require_serial", return_value="physical-phone"),
            mock.patch.object(watchdog, "acquire_android_lease", return_value=lease),
            mock.patch.object(
                watchdog,
                "focused_window",
                return_value="mCurrentFocus=Window{ u0 art.lazying.echomind/.MainActivity}",
            ),
            mock.patch.object(watchdog, "release_android_lease") as release,
            mock.patch.object(watchdog, "unlock_desktop_from_mobile") as unlock,
        ):
            result = watchdog.watchdog_once(args(tmp))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "deferred_protected_app_in_use")
        unlock.assert_not_called()
        release.assert_called_once_with(lease)

    def test_wecom_foreground_is_restored_after_unlock(self) -> None:
        lease = mock.MagicMock()
        lock_states = [
            {"ok": True, "status": "locked"},
            {"ok": True, "status": "unlocked"},
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(watchdog, "apply_desktop_keep_awake"),
            mock.patch.object(watchdog, "desktop_lock_state", side_effect=lock_states),
            mock.patch.object(watchdog, "require_serial", return_value="physical-phone"),
            mock.patch.object(watchdog, "acquire_android_lease", return_value=lease),
            mock.patch.object(
                watchdog,
                "focused_window",
                return_value="mCurrentFocus=Window{ u0 com.tencent.wework/.launch.WwMainActivity}",
            ),
            mock.patch.object(
                watchdog,
                "unlock_desktop_from_mobile",
                return_value={"ok": True},
            ),
            mock.patch.object(watchdog, "restore_android_package") as restore,
            mock.patch.object(watchdog, "release_android_lease"),
        ):
            result = watchdog.watchdog_once(args(tmp))

        self.assertTrue(result["ok"])
        restore.assert_called_once_with("adb", "physical-phone", "com.tencent.wework")

    def test_focused_package_parses_android_window_output(self) -> None:
        focus = "mCurrentFocus=Window{abc u0 com.tencent.wework/.launch.WwMainActivity}"
        self.assertEqual(watchdog.focused_package(focus), "com.tencent.wework")

    def test_known_android_apps_use_explicit_components(self) -> None:
        with mock.patch.object(
            watchdog,
            "adb_shell",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as shell:
            watchdog.start_android_package("adb", "physical-phone", "com.tencent.mm")

        shell.assert_called_once_with(
            "adb",
            "physical-phone",
            ["am", "start", "-n", "com.tencent.mm/.ui.LauncherUI"],
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
