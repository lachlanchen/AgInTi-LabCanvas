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
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_DISPLAY = ":97"
DEFAULT_NOVNC_PORT = 6107


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="about:blank", help="URL to open for manual login/download help.")
    parser.add_argument("--display", default=DEFAULT_DISPLAY, help="X display for the isolated virtual desktop.")
    parser.add_argument("--browser", help="Browser command. Defaults to WECHAT_BROWSER_COMMAND or an installed browser.")
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="Seconds to wait after launch before capture/close.")
    parser.add_argument("--capture", action="store_true", help="Capture visible browser text and screenshot into the private assist folder.")
    parser.add_argument("--close-after", action="store_true", help="Close the browser window after the optional wait/capture.")
    parser.add_argument("--output-dir", type=Path, help="Private output directory for captures. Defaults under .private/browser_assist/captures.")
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
        "wait_seconds": args.wait_seconds,
        "capture": bool(args.capture),
        "close_after": bool(args.close_after),
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
    if args.wait_seconds > 0 or args.capture or args.close_after:
        time.sleep(max(0.0, args.wait_seconds))
        env_window = dict(env)
        window = find_browser_window(browser, env_window)
        if window:
            payload["window"] = {"id": window["id"], "x": window["x"], "y": window["y"], "width": window["width"], "height": window["height"]}
            if args.url and args.url != "about:blank":
                payload["load_probe"] = ensure_browser_url_loaded(window, env_window)
        else:
            payload["window"] = None
            payload["window_warning"] = "No visible browser window found for capture/close."
        if args.capture and window:
            capture_dir = args.output_dir or (PRIVATE / "browser_assist" / "captures")
            payload["artifacts"] = capture_browser_window(window, env_window, capture_dir, url=args.url)
        if args.close_after:
            payload["close"] = close_browser_window(window, proc, env_window)
    print_payload(payload, args.json)
    return 0


def resolve_browser(raw: str | None) -> str:
    if raw:
        return raw
    if os.environ.get("WECHAT_BROWSER_COMMAND"):
        return os.environ["WECHAT_BROWSER_COMMAND"]
    for name in ("google-chrome", "chromium", "chromium-browser", "brave-browser", "firefox"):
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


def browser_window_classes(browser: str) -> list[str]:
    name = Path(shlex.split(browser)[0]).name.lower()
    if "firefox" in name:
        return ["firefox"]
    if "chrome" in name:
        return ["google-chrome", "chrome"]
    if "chromium" in name:
        return ["chromium", "chromium-browser"]
    if "brave" in name:
        return ["brave-browser", "brave"]
    return [name]


def find_browser_window(browser: str, env: dict[str, str]) -> dict[str, int | str] | None:
    best: dict[str, int | str] | None = None
    best_area = 0
    seen: set[str] = set()
    for window_class in browser_window_classes(browser):
        proc = run(["xdotool", "search", "--onlyvisible", "--class", window_class], env=env, check=False)
        for wid in proc.stdout.split():
            if wid in seen:
                continue
            seen.add(wid)
            window = window_geometry(wid, env)
            if not window:
                continue
            area = int(window["width"]) * int(window["height"])
            if area > best_area:
                best = window
                best_area = area
    return best


def window_geometry(wid: str, env: dict[str, str]) -> dict[str, int | str] | None:
    title = run(["xdotool", "getwindowname", wid], env=env, check=False).stdout.strip()
    if title.lower().startswith("close "):
        return None
    geom = run(["xdotool", "getwindowgeometry", "--shell", wid], env=env, check=False).stdout
    values = dict(line.split("=", 1) for line in geom.splitlines() if "=" in line)
    try:
        width = int(values.get("WIDTH", "0"))
        height = int(values.get("HEIGHT", "0"))
        if width < 200 or height < 200:
            return None
        return {
            "id": wid,
            "title": title,
            "x": int(values.get("X", "0")),
            "y": int(values.get("Y", "0")),
            "width": width,
            "height": height,
        }
    except ValueError:
        return None


def capture_browser_window(window: dict[str, int | str], env: dict[str, str], output_dir: Path, *, url: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_dir / f"browser_assist_{stamp}_{safe_file_token(url)}"
    screenshot = base.with_suffix(".png")
    text_path = base.with_suffix(".txt")
    metadata_path = base.with_suffix(".json")
    artifacts: dict[str, Any] = {"output_dir": redacted_path(output_dir)}
    wid = str(window["id"])
    try:
        run(["xdotool", "windowactivate", "--sync", wid], env=env, check=False)
        run(["xdotool", "key", "--clearmodifiers", "Escape"], env=env, check=False)
        time.sleep(0.2)
        click_x = int(window["x"]) + max(10, int(window["width"]) // 2)
        click_y = int(window["y"]) + max(80, int(window["height"]) // 2)
        run(["xdotool", "mousemove", str(click_x), str(click_y), "click", "1"], env=env, check=False)
        time.sleep(0.2)
        if shutil.which("import"):
            proc = run(["import", "-window", wid, str(screenshot)], env=env, check=False)
            if proc.returncode == 0 and screenshot.is_file():
                artifacts["screenshot"] = str(screenshot)
            else:
                artifacts["screenshot_error"] = (proc.stderr or proc.stdout or "").strip()[:500]
        run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], env=env, check=False)
        time.sleep(0.1)
        run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], env=env, check=False)
        time.sleep(0.2)
        clip = run(["xclip", "-selection", "clipboard", "-o"], env=env, check=False)
        text = (clip.stdout or "").strip()
        if text:
            text_path.write_text(text[:200000], encoding="utf-8", errors="replace")
            artifacts["text"] = str(text_path)
            artifacts["text_chars"] = len(text)
        else:
            artifacts["text_warning"] = "No selectable browser text was captured."
    except Exception as exc:
        artifacts["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    metadata = {
        "url": url,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "window": window,
        "artifacts": artifacts,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifacts["metadata"] = str(metadata_path)
    return artifacts


def ensure_browser_url_loaded(window: dict[str, int | str], env: dict[str, str]) -> dict[str, Any]:
    wid = str(window["id"])
    payload: dict[str, Any] = {"attempted": True}
    try:
        run(["xdotool", "windowactivate", "--sync", wid], env=env, check=False)
        run(["xdotool", "key", "--clearmodifiers", "Return"], env=env, check=False)
        time.sleep(float(os.environ.get("WECHAT_BROWSER_ASSIST_LOAD_AFTER_ENTER_SECONDS", "2")))
        run(["xdotool", "key", "--clearmodifiers", "Escape"], env=env, check=False)
        payload["ok"] = True
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return payload


def close_browser_window(window: dict[str, int | str] | None, proc: subprocess.Popen, env: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"requested": True}
    if window:
        wid = str(window["id"])
        result = run(["xdotool", "windowclose", wid], env=env, check=False)
        payload["window_id"] = wid
        payload["windowclose_returncode"] = result.returncode
    time.sleep(0.5)
    if proc.poll() is None:
        proc.terminate()
        payload["process_terminated"] = True
    else:
        payload["process_returncode"] = proc.returncode
    return payload


def run(command: list[str], *, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        check=check,
        timeout=float(os.environ.get("WECHAT_BROWSER_ASSIST_COMMAND_TIMEOUT", "10")),
    )


def safe_file_token(value: str) -> str:
    token = "".join(char if char.isalnum() else "-" for char in value.lower())
    token = "-".join(part for part in token.split("-") if part)
    return token[:64] or "page"


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
