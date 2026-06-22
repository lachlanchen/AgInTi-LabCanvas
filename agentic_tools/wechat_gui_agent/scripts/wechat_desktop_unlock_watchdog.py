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
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

from wechat_gui_send import detect_wechat_locked, find_wechat_window, screenshot


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F")
DEFAULT_ANDROID_OUTPUT = ROOT / "output" / "android_device_agent" / datetime.now().strftime("%F")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", default=os.environ.get("WECHAT_DISPLAY", ":97"))
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("WECHAT_UNLOCK_INTERVAL", "20")))
    parser.add_argument("--loop", action="store_true", help="Run forever and unlock whenever the desktop is locked.")
    parser.add_argument("--dry-run", action="store_true", help="Report the lock state without tapping the phone.")
    parser.add_argument("--flush-deferred", action="store_true", help="Flush one deferred WeChat outbox item after a successful unlock.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--android-output-dir", type=Path, default=DEFAULT_ANDROID_OUTPUT)
    parser.add_argument("--banner-tap", default="505,282", help="MIX 2S chat-list desktop-lock banner tap point.")
    parser.add_argument("--lock-tap", default="540,690", help="MIX 2S logged-in-device lock control tap point.")
    args = parser.parse_args()

    require_tools("import", "convert", "tesseract", args.adb)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.android_output_dir.mkdir(parents=True, exist_ok=True)

    while True:
        event = watchdog_once(args)
        print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True)
        if not args.loop:
            return 0 if event.get("ok", False) else 1
        time.sleep(max(args.interval, 5.0))


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
        keep_android_awake(args.adb, args.serial)
        entered = enter_weixin_on_desktop(args.display, lock_state)
        time.sleep(3.0)
        after = desktop_lock_state(args.display, args.output_dir)
        payload.update({"action": "enter_weixin", "entry": entered, "after": after})
        payload["ok"] = bool(entered.get("ok")) and after.get("status") not in {"locked", "entry_required", "no_window"}
        if payload["ok"] and args.flush_deferred:
            payload["flush_deferred"] = flush_deferred_once()
        return payload
    if lock_state.get("status") != "locked":
        keep_android_awake(args.adb, args.serial)
        return payload
    if args.dry_run:
        payload["action"] = "would_unlock"
        return payload

    serial = require_serial(args.adb, args.serial)
    unlock = unlock_desktop_from_mobile(
        args.adb,
        serial,
        parse_point(args.banner_tap),
        parse_point(args.lock_tap),
        args.android_output_dir,
    )
    time.sleep(2.0)
    after = desktop_lock_state(args.display, args.output_dir)
    payload.update({"action": "unlock", "serial": redact_serial(serial), "mobile": unlock, "after": after})
    payload["ok"] = bool(unlock.get("ok")) and after.get("status") != "locked"
    if payload["ok"] and args.flush_deferred:
        payload["flush_deferred"] = flush_deferred_once()
    return payload


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
    adb_shell(adb, serial, ["monkey", "-p", "com.tencent.mm", "-c", "android.intent.category.LAUNCHER", "1"], check=False)
    time.sleep(1.0)
    before = mobile_screenshot(adb, serial, output_dir, "before")
    focus_before = focused_window(adb, serial)
    if "WebWXLogoutUI" not in focus_before:
        adb_shell(adb, serial, ["input", "tap", str(banner_tap[0]), str(banner_tap[1])])
        time.sleep(1.0)
    focus_device_page = focused_window(adb, serial)
    if "WebWXLogoutUI" not in focus_device_page:
        return {
            "ok": False,
            "reason": "mobile_desktop_device_page_not_visible",
            "focus_before": focus_before,
            "focus_after_banner": focus_device_page,
            "before_screenshot": str(before),
        }
    adb_shell(adb, serial, ["input", "tap", str(lock_tap[0]), str(lock_tap[1])])
    time.sleep(1.0)
    after = mobile_screenshot(adb, serial, output_dir, "after")
    return {
        "ok": True,
        "focus_before": focus_before,
        "focus_after_banner": focus_device_page,
        "after_focus": focused_window(adb, serial),
        "before_screenshot": str(before),
        "after_screenshot": str(after),
    }


def mobile_screenshot(adb: str, serial: str, output_dir: Path, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"wechat-mobile-unlock-{label}-{stamp}.png"
    proc = run([adb, "-s", serial, "exec-out", "screencap", "-p"], capture_bytes=True)
    path.write_bytes(proc.stdout)
    return path


def focused_window(adb: str, serial: str) -> str:
    proc = adb_shell(adb, serial, ["dumpsys", "window"], check=False)
    lines = [line.strip() for line in proc.stdout.splitlines() if "mCurrentFocus" in line or "mFocusedApp" in line]
    return " | ".join(lines)[:1000]


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


def adb_shell(adb: str, serial: str, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([adb, "-s", serial, "shell", *command], check=check)


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
) -> subprocess.CompletedProcess:
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=not capture_bytes, check=False)
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
