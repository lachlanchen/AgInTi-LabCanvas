#!/usr/bin/env python3
"""Keep official desktop WeChat unlocked through the owner's Android WeChat UI.

The script does not bypass phone credentials or private WeChat protocols. It
checks the visible Linux WeChat window for the official locked screen, then uses
an already-authorized Android device to tap the normal mobile WeChat controls
that unlock the logged-in desktop session.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
ANDROID_SCRIPTS_DIR = ROOT / "agentic_tools" / "android_device_agent" / "scripts"
if str(ANDROID_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(ANDROID_SCRIPTS_DIR))

from android_control_lease import read_active_priority
from wechat_gui_send import detect_wechat_locked, find_wechat_window, screenshot


DEFAULT_OUTPUT = ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F")
DEFAULT_ANDROID_OUTPUT = ROOT / "output" / "android_device_agent" / datetime.now().strftime("%F")
DEFAULT_ANDROID_LOCK = (
    ROOT / "agentic_tools" / "wecom_agent" / ".private" / "wecom_android_bridge.lock"
)
DEFAULT_ANDROID_PRIORITY = (
    ROOT
    / "agentic_tools"
    / "android_device_agent"
    / ".private"
    / "android_control_priority.json"
)
DEFAULT_STATE_FILE = (
    ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / ".private"
    / "wechat_desktop_unlock_watchdog.state.json"
)
DEFAULT_PROTECTED_PACKAGES = (
    "art.lazying.echomind",
    "art.lazying.aimemo",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", default=os.environ.get("WECHAT_DISPLAY", ":97"))
    parser.add_argument(
        "--serial",
        default=os.environ.get("WECHAT_UNLOCK_ADB_SERIAL", os.environ.get("ANDROID_SERIAL", "")),
    )
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("WECHAT_UNLOCK_INTERVAL", "20")))
    parser.add_argument("--loop", action="store_true", help="Run forever and unlock whenever the desktop is locked.")
    parser.add_argument("--dry-run", action="store_true", help="Report the lock state without tapping the phone.")
    parser.add_argument("--flush-deferred", action="store_true", help="Flush one deferred WeChat outbox item after a successful unlock.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--android-output-dir", type=Path, default=DEFAULT_ANDROID_OUTPUT)
    parser.add_argument("--banner-tap", default="505,282", help="MIX 2S chat-list desktop-lock banner tap point.")
    parser.add_argument("--lock-tap", default="540,690", help="MIX 2S logged-in-device lock control tap point.")
    parser.add_argument(
        "--android-lock",
        type=Path,
        default=Path(os.environ.get("WECHAT_UNLOCK_ANDROID_LOCK", str(DEFAULT_ANDROID_LOCK))),
        help="Shared phone lease used by the WeCom Android relay.",
    )
    parser.add_argument(
        "--android-lock-timeout",
        type=float,
        default=float(os.environ.get("WECHAT_UNLOCK_ANDROID_LOCK_TIMEOUT", "30")),
        help="Bounded wait for the shared phone lease before deferring.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(
            os.environ.get("WECHAT_UNLOCK_STATE_FILE", str(DEFAULT_STATE_FILE))
        ),
        help="Ignored current-state snapshot consumed by health/status probes.",
    )
    parser.add_argument(
        "--protected-package",
        action="append",
        default=[],
        help="Do not touch the phone while this package is foreground. Repeatable.",
    )
    args = parser.parse_args()
    configured_packages = [
        item.strip()
        for item in os.environ.get("WECHAT_UNLOCK_PROTECTED_PACKAGES", "").split(",")
        if item.strip()
    ]
    args.protected_package = sorted(
        set(DEFAULT_PROTECTED_PACKAGES + tuple(configured_packages) + tuple(args.protected_package))
    )

    require_tools("import", "convert", "tesseract", args.adb)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.android_output_dir.mkdir(parents=True, exist_ok=True)

    while True:
        event = watchdog_once(args)
        write_state_file(args.state_file, event)
        print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)
        if not args.loop:
            return 0 if event.get("ok", False) else 1
        time.sleep(watchdog_sleep_seconds(args, event))


def watchdog_sleep_seconds(args: argparse.Namespace, event: dict[str, Any]) -> float:
    try:
        retry_after = float(event.get("retry_after_seconds") or 0.0)
    except (TypeError, ValueError):
        retry_after = 0.0
    return max(float(getattr(args, "interval", 20.0)), retry_after, 5.0)


def watchdog_once(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    apply_desktop_keep_awake(args.display)
    lock_state = desktop_lock_state(args.display, args.output_dir)
    payload: dict[str, Any] = {
        "ok": True,
        "started_at": started_at,
        "display": args.display,
        "desktop": lock_state,
        "action": "noop",
    }
    if lock_state.get("status") == "entry_required":
        if args.dry_run:
            payload["action"] = "would_enter_weixin"
            return payload
        entered = enter_weixin_on_desktop(args.display, lock_state)
        time.sleep(3.0)
        after = desktop_lock_state(args.display, args.output_dir)
        mobile_confirmation: dict[str, Any] | None = None
        if after.get("status") in {"locked", "entry_required"}:
            mobile_confirmation = confirm_desktop_entry_from_mobile(args)
            confirmed_after = mobile_confirmation.get("after")
            if isinstance(confirmed_after, dict):
                after = confirmed_after
        payload.update({"action": "enter_weixin", "entry": entered, "after": after})
        if mobile_confirmation is not None:
            payload["action"] = "enter_weixin_and_confirm_phone"
            payload["mobile_confirmation"] = mobile_confirmation
            if mobile_confirmation.get("retry_after_seconds"):
                payload["retry_after_seconds"] = mobile_confirmation["retry_after_seconds"]
        payload["ok"] = bool(entered.get("ok")) and after.get("status") not in {"locked", "entry_required", "no_window"}
        if payload["ok"] and args.flush_deferred:
            payload["flush_deferred"] = flush_deferred_once()
        return payload
    if lock_state.get("status") != "locked":
        return payload
    if args.dry_run:
        payload["action"] = "would_unlock"
        return payload

    serial = require_serial(args.adb, args.serial)
    lease = acquire_android_lease(
        args.android_lock,
        timeout_seconds=max(0.0, float(getattr(args, "android_lock_timeout", 5.0))),
    )
    if lease is None:
        payload["action"] = "deferred_android_busy"
        payload["serial"] = redact_serial(serial)
        return payload
    try:
        focus_before = focused_window(args.adb, serial)
        package_before = focused_package(focus_before)
        if package_before in set(args.protected_package):
            payload.update(
                {
                    "action": "deferred_protected_app_in_use",
                    "serial": redact_serial(serial),
                    "protected_package": package_before,
                }
            )
            return payload
        unlock = unlock_desktop_from_mobile(
            args.adb,
            serial,
            parse_point(args.banner_tap),
            parse_point(args.lock_tap),
            args.android_output_dir,
        )
        if package_before == "com.tencent.wework":
            restore_android_package(args.adb, serial, package_before)
            unlock["restored_package"] = package_before
    finally:
        release_android_lease(lease)
    time.sleep(2.0)
    after = desktop_lock_state(args.display, args.output_dir)
    payload.update({"action": "unlock", "serial": redact_serial(serial), "mobile": unlock, "after": after})
    payload["ok"] = bool(unlock.get("ok")) and after.get("status") != "locked"
    if payload["ok"] and args.flush_deferred:
        payload["flush_deferred"] = flush_deferred_once()
    return payload


def confirm_desktop_entry_from_mobile(args: argparse.Namespace) -> dict[str, Any]:
    """Foreground the owner's phone WeChat so its normal desktop approval can complete."""
    serial = require_serial(args.adb, args.serial)
    lease = acquire_android_lease(
        args.android_lock,
        timeout_seconds=max(
            0.0,
            float(getattr(args, "android_lock_timeout", 30.0)),
        ),
    )
    if lease is None:
        return {
            "ok": False,
            "deferred": True,
            "reason": "android_busy",
            "serial": redact_serial(serial),
        }
    package_before = ""
    try:
        focus_before = focused_window(args.adb, serial)
        package_before = focused_package(focus_before)
        if package_before in set(args.protected_package):
            return {
                "ok": False,
                "deferred": True,
                "reason": "protected_app_in_use",
                "protected_package": package_before,
                "serial": redact_serial(serial),
            }
        keep_android_awake(args.adb, serial)
        foregrounded = start_android_package(args.adb, serial, "com.tencent.mm")
        after: dict[str, Any] = {"ok": False, "status": "entry_required"}
        if foregrounded:
            for _ in range(6):
                after = desktop_lock_state(args.display, args.output_dir)
                if after.get("status") not in {"entry_required", "no_window"}:
                    break
                time.sleep(2.0)
        mobile_unlock: dict[str, Any] | None = None
        if after.get("status") in {"locked", "entry_required"}:
            mobile_unlock = unlock_desktop_from_mobile(
                args.adb,
                serial,
                parse_point(args.banner_tap),
                parse_point(args.lock_tap),
                args.android_output_dir,
            )
            time.sleep(2.0)
            after = desktop_lock_state(args.display, args.output_dir)
        retry_after_seconds = 0
        if (
            isinstance(mobile_unlock, dict)
            and mobile_unlock.get("reason") == "mobile_desktop_device_page_not_visible"
            and after.get("status") == "entry_required"
        ):
            retry_after_seconds = max(
                60,
                int(os.environ.get("WECHAT_UNLOCK_ENROLLMENT_RETRY_SECONDS", "300")),
            )
        result = {
            "ok": bool(foregrounded)
            and after.get("status") not in {"locked", "entry_required", "no_window"},
            "serial": redact_serial(serial),
            "foregrounded": bool(foregrounded),
            "package_before": package_before,
            "mobile_unlock": mobile_unlock,
            "after": after,
        }
        if retry_after_seconds:
            result["retry_after_seconds"] = retry_after_seconds
        return result
    finally:
        if package_before == "com.tencent.wework":
            restore_android_package(args.adb, serial, package_before)
        release_android_lease(lease)


def desktop_lock_state(display: str, output_dir: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    window = find_wechat_window(env)
    if not window:
        return {"ok": False, "status": "no_window"}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shot = output_dir / "unlock-watchdog-desktop-current.png"
    crop = output_dir / "unlock-watchdog-desktop-current-lock-crop.png"
    try:
        screenshot(env, shot)
        lock = detect_wechat_locked(env, window, shot, crop)
    except Exception as exc:
        return {"ok": False, "status": "detect_failed", "error": str(exc)[:500]}
    if window.width < 500 or window.height < 500:
        return {
            "ok": True,
            "status": "entry_required",
            "window": {"x": window.x, "y": window.y, "width": window.width, "height": window.height},
            "screenshot": str(shot),
            "lock_crop": str(crop),
            "ocr_text": "",
        }
    status = "locked" if lock.get("locked") else "unlocked"
    evidence_shot = shot
    evidence_crop = Path(str(lock.get("lock_crop") or crop))
    ocr_text = ""
    if status == "locked":
        evidence_shot = output_dir / f"unlock-watchdog-desktop-locked-{stamp}.png"
        evidence_crop = output_dir / f"unlock-watchdog-desktop-locked-{stamp}-lock-crop.png"
        shutil.copy2(shot, evidence_shot)
        if Path(str(lock.get("lock_crop") or crop)).exists():
            shutil.copy2(Path(str(lock.get("lock_crop") or crop)), evidence_crop)
        ocr_text = str(lock.get("ocr_text", ""))[:500]
    return {
        "ok": True,
        "status": status,
        "window": {"x": window.x, "y": window.y, "width": window.width, "height": window.height},
        "screenshot": str(evidence_shot),
        "lock_crop": str(evidence_crop),
        "ocr_text": ocr_text,
    }


def enter_weixin_on_desktop(display: str, lock_state: dict[str, Any]) -> dict[str, Any]:
    window = lock_state.get("window") if isinstance(lock_state.get("window"), dict) else {}
    try:
        x = int(window.get("x", 0))
        y = int(window.get("y", 0))
        width = int(window.get("width", 0))
        height = int(window.get("height", 0))
    except (TypeError, ValueError):
        return {"ok": False, "reason": "invalid_window_geometry", "window": window}
    if width <= 0 or height <= 0:
        return {"ok": False, "reason": "invalid_window_geometry", "window": window}
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    click_x = x + width // 2
    click_y = y + int(height * 0.76)
    run(["xdotool", "mousemove", str(click_x), str(click_y), "click", "1"], env=env, check=False)
    return {"ok": True, "click": [click_x, click_y], "window": window}


def apply_desktop_keep_awake(display: str) -> None:
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    for command in (["xset", "s", "off"], ["xset", "s", "noblank"], ["xset", "s", "reset"]):
        run(command, env=env, check=False)
    query = run(["xset", "q"], env=env, check=False)
    if "DPMS is" in query.stdout:
        run(["xset", "-dpms"], env=env, check=False)


def keep_android_awake(adb: str, serial: str) -> None:
    try:
        resolved = require_serial(adb, serial)
    except SystemExit:
        return
    adb_shell(adb, resolved, ["input", "keyevent", "224"], check=False)
    adb_shell(adb, resolved, ["wm", "dismiss-keyguard"], check=False)
    adb_shell(adb, resolved, ["svc", "power", "stayon", "true"], check=False)


def unlock_desktop_from_mobile(
    adb: str,
    serial: str,
    banner_tap: tuple[int, int],
    lock_tap: tuple[int, int],
    output_dir: Path,
) -> dict[str, Any]:
    keep_android_awake(adb, serial)
    start_android_package(adb, serial, "com.tencent.mm")
    time.sleep(1.0)
    before = mobile_screenshot(adb, serial, output_dir, "before")
    focus_before = focused_window(adb, serial)
    if "WebWXLogoutUI" not in focus_before:
        adb_shell(adb, serial, ["input", "tap", str(banner_tap[0]), str(banner_tap[1])])
        time.sleep(1.0)
    focus_device_page = focused_window(adb, serial)
    chat_list_recovery = False
    if "WebWXLogoutUI" not in focus_device_page and "com.tencent.mm" in focus_device_page:
        # LauncherUI is shared by the chat list and an open conversation. One
        # bounded Back returns an open conversation to the list so the desktop
        # device banner has a stable tap target.
        adb_shell(adb, serial, ["input", "keyevent", "4"], check=False)
        time.sleep(1.0)
        focus_after_back = focused_window(adb, serial)
        if "com.tencent.mm" in focus_after_back:
            chat_list_recovery = True
            adb_shell(
                adb,
                serial,
                ["input", "tap", str(banner_tap[0]), str(banner_tap[1])],
                check=False,
            )
            time.sleep(1.0)
            focus_device_page = focused_window(adb, serial)
    if "WebWXLogoutUI" not in focus_device_page:
        return {
            "ok": False,
            "reason": "mobile_desktop_device_page_not_visible",
            "focus_before": focus_before,
            "focus_after_banner": focus_device_page,
            "chat_list_recovery": chat_list_recovery,
            "before_screenshot": str(before),
        }
    device_page_screenshot = mobile_screenshot(adb, serial, output_dir, "device-page")
    state_before = mobile_desktop_lock_state(
        adb,
        serial,
        screenshot_path=device_page_screenshot,
    )
    if state_before == "locked":
        tap_count = 1
    elif state_before == "unlocked":
        # The Linux lock screen and phone label can temporarily disagree.
        # Reset the toggle through locked -> unlocked instead of blindly
        # changing an already-unlocked phone label into a persistent lock.
        tap_count = 2
    else:
        return {
            "ok": False,
            "reason": "mobile_desktop_lock_state_unknown",
            "focus_before": focus_before,
            "focus_after_banner": focus_device_page,
            "before_screenshot": str(before),
        }
    states_after_tap: list[str] = []
    after = before
    for index in range(tap_count):
        adb_shell(
            adb,
            serial,
            ["input", "tap", str(lock_tap[0]), str(lock_tap[1])],
        )
        time.sleep(1.0)
        after = mobile_screenshot(adb, serial, output_dir, f"after-{index + 1}")
        states_after_tap.append(
            mobile_desktop_lock_state(adb, serial, screenshot_path=after)
        )
    final_state = states_after_tap[-1] if states_after_tap else state_before
    return {
        "ok": final_state == "unlocked",
        "focus_before": focus_before,
        "focus_after_banner": focus_device_page,
        "chat_list_recovery": chat_list_recovery,
        "after_focus": focused_window(adb, serial),
        "state_before": state_before,
        "states_after_tap": states_after_tap,
        "before_screenshot": str(before),
        "device_page_screenshot": str(device_page_screenshot),
        "after_screenshot": str(after),
    }


def mobile_desktop_lock_state(
    adb: str,
    serial: str,
    *,
    screenshot_path: Path | None = None,
) -> str:
    remote = "/sdcard/labcanvas_wechat_desktop_state.xml"
    dumped = adb_shell(
        adb,
        serial,
        ["uiautomator", "dump", "--compressed", remote],
        check=False,
        timeout=20,
    )
    if dumped.returncode != 0:
        if screenshot_path and screenshot_path.is_file():
            return mobile_desktop_lock_state_from_screenshot(screenshot_path)
        return "unknown"
    payload = adb_shell(
        adb,
        serial,
        ["cat", remote],
        check=False,
        timeout=10,
    ).stdout
    if 'text="已锁定"' in payload:
        return "locked"
    if 'text="未锁定"' in payload:
        return "unlocked"
    if screenshot_path and screenshot_path.is_file():
        return mobile_desktop_lock_state_from_screenshot(screenshot_path)
    return "unknown"


def mobile_desktop_lock_state_from_screenshot(path: Path) -> str:
    crop = path.with_name(f"{path.stem}-lock-state.png")
    converted = run(
        [
            "convert",
            str(path),
            "-crop",
            "600x400+250+450",
            "-resize",
            "200%",
            "-colorspace",
            "Gray",
            "-contrast-stretch",
            "2%x2%",
            str(crop),
        ],
        check=False,
        timeout=15,
    )
    if converted.returncode != 0:
        return "unknown"
    ocr = run(
        [
            "tesseract",
            str(crop),
            "stdout",
            "-l",
            "chi_sim+eng",
            "--psm",
            "11",
        ],
        check=False,
        timeout=15,
    ).stdout.replace(" ", "")
    if "已锁定" in ocr:
        return "locked"
    if "未锁定" in ocr:
        return "unlocked"
    return "unknown"


def mobile_screenshot(adb: str, serial: str, output_dir: Path, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"wechat-mobile-unlock-{label}-{stamp}.png"
    proc = run([adb, "-s", serial, "exec-out", "screencap", "-p"], capture_bytes=True)
    path.write_bytes(proc.stdout)
    return path


def focused_window(adb: str, serial: str) -> str:
    proc = adb_shell(adb, serial, ["dumpsys", "window", "displays"], check=False)
    lines = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "mCurrentFocus" in line or "mFocusedApp" in line
    ]
    if not lines:
        proc = adb_shell(adb, serial, ["dumpsys", "window"], check=False)
        lines = [
            line.strip()
            for line in proc.stdout.splitlines()
            if "mCurrentFocus" in line or "mFocusedApp" in line
        ]
    return " | ".join(lines)[:1000]


def focused_package(focus: str) -> str:
    for marker in ("u0 ", "u10 "):
        if marker in focus:
            candidate = focus.split(marker, 1)[1].split("/", 1)[0].strip()
            if candidate:
                return candidate
    for token in focus.replace("}", " ").split():
        if "/" in token:
            candidate = token.split("/", 1)[0].strip()
            if "." in candidate:
                return candidate
    return ""


def acquire_android_lease(path: Path, *, timeout_seconds: float = 5.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        if read_active_priority(DEFAULT_ANDROID_PRIORITY) is not None:
            handle.close()
            return None
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Close the race where an explicit sender publishes priority after
            # this watchdog checked but before it acquired the shared lock.
            if read_active_priority(DEFAULT_ANDROID_PRIORITY) is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
                return None
            return handle
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                return None
            time.sleep(0.2)


def release_android_lease(handle) -> None:
    fcntl.flock(handle, fcntl.LOCK_UN)
    handle.close()


def write_state_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def restore_android_package(adb: str, serial: str, package: str) -> None:
    start_android_package(adb, serial, package)


def start_android_package(adb: str, serial: str, package: str) -> bool:
    components = {
        "com.tencent.mm": "com.tencent.mm/.ui.LauncherUI",
        "com.tencent.wework": "com.tencent.wework/.launch.WwMainActivity",
    }
    component = components.get(package)
    if component:
        proc = adb_shell(adb, serial, ["am", "start", "-n", component], check=False)
        if proc.returncode == 0:
            time.sleep(0.5)
            if focused_package(focused_window(adb, serial)) == package:
                return True
    adb_shell(
        adb,
        serial,
        ["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
        check=False,
    )
    time.sleep(0.5)
    return focused_package(focused_window(adb, serial)) == package


def flush_deferred_once() -> dict[str, Any]:
    proc = run(
        [sys.executable, "agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py", "--flush-deferred"],
        cwd=ROOT,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }


def parse_point(raw: str) -> tuple[int, int]:
    parts = [part.strip() for part in raw.split(",", 1)]
    if len(parts) != 2:
        raise SystemExit(f"Point must be X,Y: {raw}")
    return int(parts[0]), int(parts[1])


def require_serial(adb: str, serial: str) -> str:
    if serial:
        state = run([adb, "-s", serial, "get-state"], check=False)
        if state.returncode == 0:
            return serial
        raise SystemExit(f"Android device is not reachable: {redact_serial(serial)}")
    proc = run([adb, "devices"])
    devices = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise SystemExit("No authorized Android device found.")
    raise SystemExit("Multiple Android devices found; pass --serial.")


def adb_shell(
    adb: str,
    serial: str,
    command: list[str],
    *,
    check: bool = True,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    return run(
        [adb, "-s", serial, "shell", *command],
        check=check,
        timeout=timeout,
    )


def require_tools(*commands: str) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise SystemExit(f"Missing required commands: {', '.join(missing)}")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_bytes: bool = False,
    timeout: float = 30,
) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=not capture_bytes,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or (b"" if capture_bytes else "")
        stderr = exc.stderr or (b"" if capture_bytes else "")
        proc = subprocess.CompletedProcess(command, 124, stdout, stderr)
    if check and proc.returncode != 0:
        stdout = proc.stdout.decode(errors="replace") if isinstance(proc.stdout, bytes) else proc.stdout
        stderr = proc.stderr.decode(errors="replace") if isinstance(proc.stderr, bytes) else proc.stderr
        raise SystemExit(f"Command failed ({proc.returncode}): {' '.join(command)}\n{stderr or stdout}")
    return proc


def redact_serial(serial: str) -> str:
    if len(serial) <= 4:
        return "<adb-serial>"
    return f"{serial[:2]}...{serial[-2:]}"


if __name__ == "__main__":
    raise SystemExit(main())
