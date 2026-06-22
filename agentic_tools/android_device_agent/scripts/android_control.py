#!/usr/bin/env python3
"""Small ADB wrapper for deterministic Android device control."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "output" / "android_device_agent"


KEY_ALIASES = {
    "BACK": "KEYCODE_BACK",
    "HOME": "KEYCODE_HOME",
    "APP_SWITCH": "KEYCODE_APP_SWITCH",
    "ENTER": "KEYCODE_ENTER",
    "POWER": "KEYCODE_POWER",
    "WAKEUP": "KEYCODE_WAKEUP",
    "MENU": "KEYCODE_MENU",
    "DEL": "KEYCODE_DEL",
    "VOLUME_UP": "KEYCODE_VOLUME_UP",
    "VOLUME_DOWN": "KEYCODE_VOLUME_DOWN",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    sub = parser.add_subparsers(dest="command", required=True)

    devices = sub.add_parser("devices")
    add_device_options(devices)
    status = sub.add_parser("status")
    add_device_options(status)

    shot = sub.add_parser("screenshot")
    add_device_options(shot)
    shot.add_argument("--output", type=Path)

    tap = sub.add_parser("tap")
    add_device_options(tap)
    tap.add_argument("x", type=int)
    tap.add_argument("y", type=int)

    swipe = sub.add_parser("swipe")
    add_device_options(swipe)
    swipe.add_argument("x1", type=int)
    swipe.add_argument("y1", type=int)
    swipe.add_argument("x2", type=int)
    swipe.add_argument("y2", type=int)
    swipe.add_argument("--duration", type=int, default=300)

    text = sub.add_parser("text")
    add_device_options(text)
    text.add_argument("value")

    key = sub.add_parser("key")
    add_device_options(key)
    key.add_argument("value")

    url = sub.add_parser("url")
    add_device_options(url)
    url.add_argument("value")

    start = sub.add_parser("start")
    add_device_options(start)
    start.add_argument("--package", required=True)
    start.add_argument("--activity", default="")

    push = sub.add_parser("push")
    add_device_options(push)
    push.add_argument("source", type=Path)
    push.add_argument("target")

    pull = sub.add_parser("pull")
    add_device_options(pull)
    pull.add_argument("source")
    pull.add_argument("target", type=Path)

    args = parser.parse_args()
    if args.command == "devices":
        print(run([args.adb, "devices", "-l"]).stdout, end="")
        return 0

    serial = require_serial(args.adb, args.serial)
    if args.command == "status":
        print(json.dumps(device_status(args.adb, serial), ensure_ascii=False, indent=2))
        return 0
    if args.command == "screenshot":
        output = args.output or screenshot_path(serial)
        output.parent.mkdir(parents=True, exist_ok=True)
        proc = run([args.adb, "-s", serial, "exec-out", "screencap", "-p"], capture_bytes=True)
        output.write_bytes(proc.stdout)
        print(json.dumps({"ok": True, "serial": serial, "output": str(output)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "tap":
        adb_shell(args.adb, serial, ["input", "tap", str(args.x), str(args.y)])
        return print_ok(serial, "tap", {"x": args.x, "y": args.y})
    if args.command == "swipe":
        adb_shell(args.adb, serial, ["input", "swipe", str(args.x1), str(args.y1), str(args.x2), str(args.y2), str(args.duration)])
        return print_ok(serial, "swipe", vars(args))
    if args.command == "text":
        adb_shell(args.adb, serial, ["input", "text", escape_input_text(args.value)])
        return print_ok(serial, "text", {"length": len(args.value)})
    if args.command == "key":
        value = KEY_ALIASES.get(args.value.upper(), args.value)
        adb_shell(args.adb, serial, ["input", "keyevent", value])
        return print_ok(serial, "key", {"value": value})
    if args.command == "url":
        adb_shell(args.adb, serial, ["am", "start", "-a", "android.intent.action.VIEW", "-d", args.value])
        return print_ok(serial, "url", {"value": args.value})
    if args.command == "start":
        if args.activity:
            adb_shell(args.adb, serial, ["am", "start", "-n", f"{args.package}/{args.activity}"])
        else:
            adb_shell(args.adb, serial, ["monkey", "-p", args.package, "-c", "android.intent.category.LAUNCHER", "1"])
        return print_ok(serial, "start", {"package": args.package, "activity": args.activity})
    if args.command == "push":
        run([args.adb, "-s", serial, "push", str(args.source), args.target])
        return print_ok(serial, "push", {"source": str(args.source), "target": args.target})
    if args.command == "pull":
        args.target.parent.mkdir(parents=True, exist_ok=True)
        run([args.adb, "-s", serial, "pull", args.source, str(args.target)])
        return print_ok(serial, "pull", {"source": args.source, "target": str(args.target)})
    return 0


def add_device_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--serial", default=argparse.SUPPRESS)
    parser.add_argument("--adb", default=argparse.SUPPRESS)


def require_serial(adb: str, serial: str) -> str:
    if serial:
        return serial
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
    raise SystemExit(f"Multiple Android devices found; pass --serial. Devices: {', '.join(devices)}")


def device_status(adb: str, serial: str) -> dict[str, object]:
    props = {
        "model": shell_text(adb, serial, ["getprop", "ro.product.model"]),
        "device": shell_text(adb, serial, ["getprop", "ro.product.device"]),
        "android": shell_text(adb, serial, ["getprop", "ro.build.version.release"]),
        "sdk": shell_text(adb, serial, ["getprop", "ro.build.version.sdk"]),
        "screen": shell_text(adb, serial, ["wm", "size"]),
        "density": shell_text(adb, serial, ["wm", "density"]),
        "power": shell_text(adb, serial, ["dumpsys", "power"]),
    }
    return {
        "ok": True,
        "serial": serial,
        "model": props["model"],
        "device": props["device"],
        "android": props["android"],
        "sdk": props["sdk"],
        "screen": props["screen"].replace("Physical size: ", ""),
        "density": props["density"].replace("Physical density: ", ""),
        "awake": "mWakefulness=Awake" in props["power"],
    }


def screenshot_path(serial: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_serial = re.sub(r"[^A-Za-z0-9_.-]+", "_", serial)
    return DEFAULT_OUTPUT / f"{safe_serial}-screenshot-{stamp}.png"


def escape_input_text(value: str) -> str:
    # Android `input text` uses %s for spaces and treats some shell characters
    # specially. subprocess passes this as one shell token, so minimal Android
    # escaping is enough for short deterministic text.
    return value.replace("%", "%25").replace(" ", "%s")


def adb_shell(adb: str, serial: str, command: list[str]) -> subprocess.CompletedProcess[str]:
    return run([adb, "-s", serial, "shell", *command])


def shell_text(adb: str, serial: str, command: list[str]) -> str:
    return adb_shell(adb, serial, command).stdout.strip()


def run(command: list[str], *, capture_bytes: bool = False) -> subprocess.CompletedProcess:
    proc = subprocess.run(command, capture_output=True, text=not capture_bytes, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace") if capture_bytes and isinstance(proc.stderr, bytes) else proc.stderr
        stdout = proc.stdout.decode(errors="replace") if capture_bytes and isinstance(proc.stdout, bytes) else proc.stdout
        raise SystemExit(f"Command failed ({proc.returncode}): {' '.join(command)}\n{stderr or stdout}")
    return proc


def print_ok(serial: str, action: str, extra: dict[str, object]) -> int:
    print(json.dumps({"ok": True, "serial": serial, "action": action, **extra}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
