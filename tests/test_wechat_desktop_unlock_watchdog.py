from __future__ import annotations

import argparse
import importlib.util
import json
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
    def test_explicit_android_priority_preempts_unlock_watchdog_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            watchdog,
            "read_active_priority",
            return_value={"purpose": "personal_wechat_send:task-1"},
        ):
            lease = watchdog.acquire_android_lease(
                Path(tmp) / "phone.lock",
                timeout_seconds=1,
            )

        self.assertIsNone(lease)

    def test_state_file_is_private_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watchdog.json"
            payload = {
                "ok": True,
                "desktop": {"status": "locked"},
                "started_at": "2026-07-28T07:00:00",
            }
            watchdog.write_state_file(path, payload)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(list(path.parent.glob("watchdog.json.tmp-*")))

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

    def test_entry_required_uses_phone_confirmation_and_restores_wecom(self) -> None:
        lease = mock.MagicMock()
        lock_states = [
            {"ok": True, "status": "entry_required"},
            {"ok": True, "status": "entry_required"},
            {"ok": True, "status": "unlocked"},
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(watchdog, "apply_desktop_keep_awake"),
            mock.patch.object(watchdog, "desktop_lock_state", side_effect=lock_states),
            mock.patch.object(watchdog, "enter_weixin_on_desktop", return_value={"ok": True}),
            mock.patch.object(watchdog, "require_serial", return_value="physical-phone"),
            mock.patch.object(watchdog, "acquire_android_lease", return_value=lease),
            mock.patch.object(
                watchdog,
                "focused_window",
                return_value="mCurrentFocus=Window{ u0 com.tencent.wework/.launch.WwMainActivity}",
            ),
            mock.patch.object(watchdog, "keep_android_awake"),
            mock.patch.object(watchdog, "start_android_package", return_value=True),
            mock.patch.object(watchdog, "restore_android_package") as restore,
            mock.patch.object(watchdog, "release_android_lease") as release,
            mock.patch.object(watchdog.time, "sleep"),
        ):
            result = watchdog.watchdog_once(args(tmp))

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "enter_weixin_and_confirm_phone")
        restore.assert_called_once_with("adb", "physical-phone", "com.tencent.wework")
        release.assert_called_once_with(lease)

    def test_entry_required_uses_mobile_device_page_when_foreground_is_not_enough(self) -> None:
        lease = mock.MagicMock()
        lock_states = [
            {"ok": True, "status": "entry_required"},
            {"ok": True, "status": "entry_required"},
            *({"ok": True, "status": "entry_required"} for _ in range(6)),
            {"ok": True, "status": "unlocked"},
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(watchdog, "apply_desktop_keep_awake"),
            mock.patch.object(watchdog, "desktop_lock_state", side_effect=lock_states),
            mock.patch.object(watchdog, "enter_weixin_on_desktop", return_value={"ok": True}),
            mock.patch.object(watchdog, "require_serial", return_value="physical-phone"),
            mock.patch.object(watchdog, "acquire_android_lease", return_value=lease),
            mock.patch.object(
                watchdog,
                "focused_window",
                return_value="mCurrentFocus=Window{ u0 com.tencent.mm/.ui.LauncherUI}",
            ),
            mock.patch.object(watchdog, "keep_android_awake"),
            mock.patch.object(watchdog, "start_android_package", return_value=True),
            mock.patch.object(
                watchdog,
                "unlock_desktop_from_mobile",
                return_value={"ok": True, "state_before": "locked"},
            ) as unlock,
            mock.patch.object(watchdog, "release_android_lease"),
            mock.patch.object(watchdog.time, "sleep"),
        ):
            result = watchdog.watchdog_once(args(tmp))

        self.assertTrue(result["ok"])
        unlock.assert_called_once()

    def test_missing_mobile_device_banner_backs_off_without_busy_polling(self) -> None:
        lease = mock.MagicMock()
        lock_states = [
            {"ok": True, "status": "entry_required"},
            {"ok": True, "status": "entry_required"},
            *({"ok": True, "status": "entry_required"} for _ in range(6)),
            {"ok": True, "status": "entry_required"},
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(watchdog, "apply_desktop_keep_awake"),
            mock.patch.object(watchdog, "desktop_lock_state", side_effect=lock_states),
            mock.patch.object(watchdog, "enter_weixin_on_desktop", return_value={"ok": True}),
            mock.patch.object(watchdog, "require_serial", return_value="physical-phone"),
            mock.patch.object(watchdog, "acquire_android_lease", return_value=lease),
            mock.patch.object(
                watchdog,
                "focused_window",
                return_value="mCurrentFocus=Window{ u0 com.tencent.mm/.ui.LauncherUI}",
            ),
            mock.patch.object(watchdog, "keep_android_awake"),
            mock.patch.object(watchdog, "start_android_package", return_value=True),
            mock.patch.object(
                watchdog,
                "unlock_desktop_from_mobile",
                return_value={
                    "ok": False,
                    "reason": "mobile_desktop_device_page_not_visible",
                },
            ),
            mock.patch.object(watchdog, "release_android_lease"),
            mock.patch.object(watchdog.time, "sleep"),
        ):
            result = watchdog.watchdog_once(args(tmp))

        self.assertFalse(result["ok"])
        self.assertEqual(result["retry_after_seconds"], 300)
        self.assertEqual(watchdog.watchdog_sleep_seconds(args(tmp), result), 300)

    def test_mobile_device_page_retries_from_open_conversation_once(self) -> None:
        screenshot = Path("/tmp/watchdog-chat-list-recovery.png")
        focuses = [
            "mCurrentFocus=Window{ u0 com.tencent.mm/.ui.LauncherUI}",
            "mCurrentFocus=Window{ u0 com.tencent.mm/.ui.LauncherUI}",
            "mCurrentFocus=Window{ u0 com.tencent.mm/.ui.LauncherUI}",
            "mCurrentFocus=Window{ u0 com.tencent.mm/.plugin.webwx.ui.WebWXLogoutUI}",
            "mCurrentFocus=Window{ u0 com.tencent.mm/.plugin.webwx.ui.WebWXLogoutUI}",
        ]
        with (
            mock.patch.object(watchdog, "keep_android_awake"),
            mock.patch.object(watchdog, "start_android_package"),
            mock.patch.object(watchdog, "focused_window", side_effect=focuses),
            mock.patch.object(watchdog, "mobile_desktop_lock_state", side_effect=["locked", "unlocked"]),
            mock.patch.object(watchdog, "mobile_screenshot", return_value=screenshot),
            mock.patch.object(
                watchdog,
                "adb_shell",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as shell,
            mock.patch.object(watchdog.time, "sleep"),
        ):
            result = watchdog.unlock_desktop_from_mobile(
                "adb",
                "physical-phone",
                (505, 282),
                (540, 690),
                Path("/tmp"),
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["chat_list_recovery"])
        commands = [call.args[2] for call in shell.call_args_list]
        self.assertEqual(commands.count(["input", "keyevent", "4"]), 1)
        self.assertEqual(commands.count(["input", "tap", "505", "282"]), 2)

    def test_phone_unlocked_label_uses_reset_cycle_not_single_lock_tap(self) -> None:
        screenshot = Path("/tmp/watchdog-test.png")
        with (
            mock.patch.object(watchdog, "keep_android_awake"),
            mock.patch.object(watchdog, "start_android_package"),
            mock.patch.object(
                watchdog,
                "focused_window",
                return_value="mCurrentFocus=Window{ u0 com.tencent.mm/.plugin.webwx.ui.WebWXLogoutUI}",
            ),
            mock.patch.object(
                watchdog,
                "mobile_desktop_lock_state",
                side_effect=["unlocked", "locked", "unlocked"],
            ),
            mock.patch.object(
                watchdog,
                "mobile_screenshot",
                return_value=screenshot,
            ),
            mock.patch.object(
                watchdog,
                "adb_shell",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as shell,
            mock.patch.object(watchdog.time, "sleep"),
        ):
            result = watchdog.unlock_desktop_from_mobile(
                "adb",
                "physical-phone",
                (505, 282),
                (540, 690),
                Path("/tmp"),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state_before"], "unlocked")
        self.assertEqual(result["states_after_tap"], ["locked", "unlocked"])
        taps = [
            call
            for call in shell.call_args_list
            if call.args[2][:2] == ["input", "tap"]
        ]
        self.assertEqual(len(taps), 2)

    def test_mobile_lock_state_uses_screenshot_ocr_when_hierarchy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            screenshot = Path(tmp) / "phone.png"
            screenshot.write_bytes(b"image")
            with (
                mock.patch.object(
                    watchdog,
                    "adb_shell",
                    return_value=subprocess.CompletedProcess([], 124, "", "timeout"),
                ),
                mock.patch.object(
                    watchdog,
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess([], 0, "", ""),
                        subprocess.CompletedProcess([], 0, "已锁定\n", ""),
                    ],
                ),
            ):
                state = watchdog.mobile_desktop_lock_state(
                    "adb",
                    "physical-phone",
                    screenshot_path=screenshot,
                )

        self.assertEqual(state, "locked")

    def test_focused_package_parses_android_window_output(self) -> None:
        focus = "mCurrentFocus=Window{abc u0 com.tencent.wework/.launch.WwMainActivity}"
        self.assertEqual(watchdog.focused_package(focus), "com.tencent.wework")

    def test_focused_window_prefers_active_display_over_stale_global_state(self) -> None:
        display_state = (
            "mCurrentFocus=Window{abc u0 com.tencent.mm/.ui.LauncherUI}\n"
            "mFocusedApp=AppWindowToken{ u0 com.tencent.mm/.ui.LauncherUI}\n"
        )
        with mock.patch.object(
            watchdog,
            "adb_shell",
            return_value=subprocess.CompletedProcess([], 0, display_state, ""),
        ) as shell:
            focus = watchdog.focused_window("adb", "physical-phone")

        self.assertEqual(watchdog.focused_package(focus), "com.tencent.mm")
        shell.assert_called_once_with(
            "adb",
            "physical-phone",
            ["dumpsys", "window", "displays"],
            check=False,
        )

    def test_known_android_apps_use_explicit_components(self) -> None:
        with (
            mock.patch.object(
                watchdog,
                "adb_shell",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as shell,
            mock.patch.object(
                watchdog,
                "focused_window",
                return_value="mCurrentFocus=Window{ u0 com.tencent.mm/.ui.LauncherUI}",
            ),
            mock.patch.object(watchdog.time, "sleep"),
        ):
            result = watchdog.start_android_package(
                "adb", "physical-phone", "com.tencent.mm"
            )

        self.assertTrue(result)
        shell.assert_called_once_with(
            "adb",
            "physical-phone",
            ["am", "start", "-n", "com.tencent.mm/.ui.LauncherUI"],
            check=False,
        )

    def test_android_app_start_falls_back_when_component_does_not_focus(self) -> None:
        with (
            mock.patch.object(
                watchdog,
                "adb_shell",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                ],
            ) as shell,
            mock.patch.object(
                watchdog,
                "focused_window",
                side_effect=[
                    "mCurrentFocus=Window{ u0 com.miui.home/.launcher.Launcher}",
                    "mCurrentFocus=Window{ u0 com.tencent.mm/.ui.LauncherUI}",
                ],
            ),
            mock.patch.object(watchdog.time, "sleep"),
        ):
            result = watchdog.start_android_package(
                "adb", "physical-phone", "com.tencent.mm"
            )

        self.assertTrue(result)
        self.assertEqual(shell.call_count, 2)
        self.assertEqual(
            shell.call_args_list[1].args[2],
            ["monkey", "-p", "com.tencent.mm", "-c", "android.intent.category.LAUNCHER", "1"],
        )


if __name__ == "__main__":
    unittest.main()
