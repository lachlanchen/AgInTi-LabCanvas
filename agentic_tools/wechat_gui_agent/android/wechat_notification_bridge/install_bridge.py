#!/usr/bin/env python3
"""Install the private WeChat notification bridge through MIUI's USB gate."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET


MIUI_INSTALL_ACTIVITY = (
    "com.miui.securitycenter/com.miui.permcenter.install.AdbInstallActivity"
)
MIUI_INSTALL_PACKAGE = "com.miui.securitycenter"
CONTINUE_BUTTON_ID = "android:id/button2"
REMOTE_HIERARCHY = "/sdcard/labcanvas_wechat_bridge_install.xml"


class InstallError(RuntimeError):
    """Raised when installation cannot be verified safely."""


def run_adb(
    adb: str,
    serial: str,
    *args: str,
    timeout: float = 10.0,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [adb, "-s", serial, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and process.returncode != 0:
        detail = (process.stderr or process.stdout).strip()
        raise InstallError(detail or f"ADB command failed: {' '.join(args)}")
    return process


def bounds_center(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value.strip())
    if match is None:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    if right <= left or bottom <= top:
        return None
    return ((left + right) // 2, (top + bottom) // 2)


def miui_continue_point(payload: str, expected_label: str) -> tuple[int, int] | None:
    """Return a click point only for the exact expected MIUI install dialog."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    labels = {
        str(node.attrib.get("text") or "").strip()
        for node in root.iter("node")
    }
    if expected_label not in labels:
        return None
    candidates = [
        node
        for node in root.iter("node")
        if node.attrib.get("package") == MIUI_INSTALL_PACKAGE
        and node.attrib.get("resource-id") == CONTINUE_BUTTON_ID
        and node.attrib.get("class") == "android.widget.Button"
        and node.attrib.get("clickable") == "true"
        and node.attrib.get("enabled") == "true"
    ]
    if len(candidates) != 1:
        return None
    return bounds_center(str(candidates[0].attrib.get("bounds") or ""))


def current_activity(adb: str, serial: str) -> str:
    process = run_adb(
        adb,
        serial,
        "shell",
        "dumpsys",
        "activity",
        "activities",
        timeout=8,
    )
    for line in process.stdout.splitlines():
        if "mResumedActivity:" in line and MIUI_INSTALL_ACTIVITY in line:
            return MIUI_INSTALL_ACTIVITY
    return ""


def capture_hierarchy(adb: str, serial: str) -> str:
    dumped = run_adb(
        adb,
        serial,
        "shell",
        "uiautomator",
        "dump",
        "--compressed",
        REMOTE_HIERARCHY,
        timeout=5,
    )
    if dumped.returncode != 0:
        return ""
    pulled = run_adb(
        adb,
        serial,
        "exec-out",
        "cat",
        REMOTE_HIERARCHY,
        timeout=5,
    )
    return pulled.stdout if pulled.returncode == 0 else ""


def install_apk(
    *,
    adb: str,
    serial: str,
    apk: Path,
    expected_label: str,
    timeout_seconds: float = 35.0,
) -> dict[str, object]:
    if not apk.is_file():
        raise InstallError(f"APK does not exist: {apk}")
    process = subprocess.Popen(
        [adb, "-s", serial, "install", "-r", "-t", str(apk)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + timeout_seconds
    confirmation_clicked = False
    while process.poll() is None and time.monotonic() < deadline:
        if not confirmation_clicked and current_activity(adb, serial) == MIUI_INSTALL_ACTIVITY:
            point = miui_continue_point(capture_hierarchy(adb, serial), expected_label)
            if point is not None:
                run_adb(
                    adb,
                    serial,
                    "shell",
                    "input",
                    "tap",
                    str(point[0]),
                    str(point[1]),
                    timeout=5,
                    check=True,
                )
                confirmation_clicked = True
        time.sleep(0.1)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        raise InstallError("ADB install exceeded its bounded deadline")
    stdout, stderr = process.communicate()
    output = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    if process.returncode != 0:
        raise InstallError(output or f"ADB install failed with exit {process.returncode}")
    return {
        "ok": True,
        "confirmation_clicked": confirmation_clicked,
        "output": output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--label", default="LabCanvas WeChat Bridge")
    args = parser.parse_args()
    result = install_apk(
        adb=args.adb,
        serial=args.serial,
        apk=args.apk.expanduser().resolve(),
        expected_label=args.label,
    )
    print(
        "installed=true confirmation_clicked="
        + ("true" if result["confirmation_clicked"] else "false")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
