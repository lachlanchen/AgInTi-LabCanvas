#!/usr/bin/env python3
"""Open a human-assist browser inside the isolated WeChat virtual desktop."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_DISPLAY = ":97"
DEFAULT_NOVNC_PORT = 6107


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="about:blank", help="URL to open for manual login/download help.")
    parser.add_argument("--display", default=DEFAULT_DISPLAY, help="X display for the isolated virtual desktop.")
    parser.add_argument("--browser", help="Browser command. Defaults to WECHAT_BROWSER_COMMAND or an installed browser.")
    parser.add_argument("--dry-run", action="store_true", help="Print the launch plan without opening a browser.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    browser = resolve_browser(args.browser)
    if not browser:
        payload = {
            "ok": False,
            "status": "browser-missing",
            "display": args.display,
            "url": args.url,
            "novnc_url": novnc_url(),
            "message": "Install firefox, chromium, or set WECHAT_BROWSER_COMMAND.",
        }
        print_payload(payload, args.json)
        return 1

    profile_dir = PRIVATE / "browser_assist" / browser_profile_name(browser)
    command = browser_command(browser, args.url, profile_dir)
    payload = {
        "ok": True,
        "status": "dry-run" if args.dry_run else "launched",
        "display": args.display,
        "url": args.url,
        "browser": browser,
        "profile_dir": redacted_path(profile_dir),
        "command": " ".join(shlex.quote(part) for part in command),
        "novnc_url": novnc_url(),
        "manual_required": True,
        "message": "Open the noVNC URL and complete login, CAPTCHA, download confirmation, or file save manually.",
    }
    if args.dry_run:
        print_payload(payload, args.json)
        return 0

    profile_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DISPLAY"] = args.display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    proc = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    payload["pid"] = proc.pid
    payload["launched_at"] = datetime.now().isoformat(timespec="seconds")
    print_payload(payload, args.json)
    return 0


def resolve_browser(raw: str | None) -> str:
    if raw:
        return raw
    if os.environ.get("WECHAT_BROWSER_COMMAND"):
        return os.environ["WECHAT_BROWSER_COMMAND"]
    for name in ("firefox", "google-chrome", "chromium", "chromium-browser", "brave-browser"):
        path = shutil.which(name)
        if path:
            return path
    return ""


def browser_profile_name(browser: str) -> str:
    name = Path(shlex.split(browser)[0]).name.lower()
    if "firefox" in name:
        return "firefox-profile"
    if "chrome" in name or "chromium" in name or "brave" in name:
        return "chromium-profile"
    return "browser-profile"


def browser_command(browser: str, url: str, profile_dir: Path) -> list[str]:
    parts = shlex.split(browser)
    name = Path(parts[0]).name.lower()
    if "firefox" in name:
        return parts + ["--no-remote", "--profile", str(profile_dir), "--new-window", url]
    if "chrome" in name or "chromium" in name or "brave" in name:
        return parts + [f"--user-data-dir={profile_dir}", "--new-window", url]
    return parts + [url]


def novnc_url() -> str:
    return f"http://127.0.0.1:{DEFAULT_NOVNC_PORT}/vnc_lite.html?host=127.0.0.1&port={DEFAULT_NOVNC_PORT}&autoconnect=1&resize=remote"


def redacted_path(path: Path) -> str:
    text = str(path)
    root = str(ROOT)
    if text.startswith(root):
        return "<repo>" + text[len(root) :]
    home = str(Path.home())
    if text.startswith(home):
        return "~" + text[len(home) :]
    return text


def print_payload(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(payload["message"])
    print(f"noVNC: {payload['novnc_url']}")
    if payload.get("command"):
        print(f"command: {payload['command']}")


if __name__ == "__main__":
    raise SystemExit(main())
