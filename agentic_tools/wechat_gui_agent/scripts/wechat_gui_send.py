#!/usr/bin/env python3
"""Send small explicit messages through native Linux WeChat GUI automation.

This script is intentionally conservative: it only sends when --send is passed,
uses the visible GUI, and stores screenshots for review.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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

from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"


@dataclass(frozen=True)
class Window:
    wid: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class TargetSpec:
    name: str
    query: str
    expected_title: str
    result_click: tuple[int, int] | None = None
    fallback_clicks: tuple[tuple[int, int], ...] = ()
    open_click: tuple[int, int] | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", default=":97", help="X display running WeChat. Default: :97.")
    parser.add_argument("--target", action="append", default=[], help="Chat/group/contact name. Repeatable.")
    parser.add_argument("--targets-file", type=Path, help="JSON file with a target list or {targets,message}.")
    parser.add_argument("--message", default="test", help="Message text. Default: test.")
    parser.add_argument("--send", action="store_true", help="Actually press Enter in the message composer.")
    parser.add_argument(
        "--compose-dry-run",
        action="store_true",
        help="In dry-run mode, paste the message into the composer for screenshot review.",
    )
    parser.add_argument("--pause", type=float, default=1.2, help="Pause between GUI actions.")
    parser.add_argument("--skip-title-guard", action="store_true", help="Do not OCR-check the opened chat title before composing.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F"))
    parser.add_argument("--mirror-db", type=Path, default=DEFAULT_DB, help="SQLite mirror database path.")
    args = parser.parse_args()

    targets, message = load_targets(args.target, args.targets_file, args.message)
    if not targets:
        raise SystemExit("No targets supplied. Use --target or --targets-file.")
    args.message = message

    required = ["xdotool", "xclip", "import"]
    if not args.skip_title_guard:
        required.extend(["convert", "tesseract"])
    require_tools(*required)
    env = os.environ.copy()
    env["DISPLAY"] = args.display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    window = find_wechat_window(env)
    if not window:
        raise SystemExit(f"No visible WeChat window found on DISPLAY={args.display}. Log in first.")
    close_secondary_wechat_windows(env, window)
    if window.width < 500 or window.height < 500:
        screenshot(env, args.output_dir / "login_or_small_window.png")
        raise SystemExit("WeChat is visible but not in the main chat UI; approve login on phone first.")

    PRIVATE.mkdir(parents=True, exist_ok=True)
    lock_path = PRIVATE / "wechat_gui_send.lock"
    results = []
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for index, target in enumerate(targets, start=1):
            result = send_one(
                env,
                window,
                target,
                args.message,
                args.send,
                args.compose_dry_run,
                args.pause,
                args.skip_title_guard,
                args.output_dir,
                args.mirror_db,
                index,
            )
            results.append(result)
        fcntl.flock(lock, fcntl.LOCK_UN)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "display": args.display,
        "send": args.send,
        "compose_dry_run": args.compose_dry_run,
        "message": args.message,
        "results": results,
    }
    manifest_path = args.output_dir / "send_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def load_targets(cli_targets: list[str], targets_file: Path | None, default_message: str) -> tuple[list[TargetSpec], str]:
    raw_targets: list[Any] = list(cli_targets)
    message = default_message
    if targets_file:
        raw = json.loads(targets_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            raw_targets.extend(raw)
        elif isinstance(raw, dict):
            if "message" in raw:
                message = str(raw["message"])
            file_targets = raw.get("targets", [])
            if not isinstance(file_targets, list):
                raise SystemExit(f"{targets_file} field 'targets' must be a list")
            raw_targets.extend(file_targets)
        else:
            raise SystemExit(f"{targets_file} must be a JSON list or object")
    targets = [target_from_raw(item) for item in raw_targets]
    return targets, message


def target_from_raw(raw: Any) -> TargetSpec:
    if isinstance(raw, str):
        return TargetSpec(name=raw, query=raw, expected_title=raw)
    if not isinstance(raw, dict):
        raise SystemExit(f"Target must be a string or object, got {type(raw).__name__}")
    name = str(raw.get("name") or raw.get("target") or raw.get("query") or "").strip()
    query = str(raw.get("query") or name).strip()
    expected_title = str(raw.get("expected_title") or raw.get("title") or name).strip()
    if not name or not query:
        raise SystemExit("Target object requires name/target and query")
    return TargetSpec(
        name=name,
        query=query,
        expected_title=expected_title or name,
        result_click=point_from_raw(raw.get("result_click")),
        fallback_clicks=points_from_raw(raw.get("fallback_clicks")),
        open_click=point_from_raw(raw.get("open_click")),
    )


def point_from_raw(raw: Any) -> tuple[int, int] | None:
    if raw is None:
        return None
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        raise SystemExit("Click point must be [x_offset, y_offset]")
    return int(raw[0]), int(raw[1])


def points_from_raw(raw: Any) -> tuple[tuple[int, int], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise SystemExit("fallback_clicks must be a list of [x_offset, y_offset] points")
    points = []
    for item in raw:
        point = point_from_raw(item)
        if point is not None:
            points.append(point)
    return tuple(points)


def send_one(
    env: dict[str, str],
    window: Window,
    target: TargetSpec,
    message: str,
    do_send: bool,
    compose_dry_run: bool,
    pause: float,
    skip_title_guard: bool,
    out_dir: Path,
    mirror_db: Path,
    index: int,
) -> dict[str, str]:
    focus(env, window)
    shot_prefix = f"{index:02d}-{safe_name(target.name)}"
    screenshot(env, out_dir / f"{shot_prefix}-before.png")

    guard = open_target(env, window, target, pause, out_dir, shot_prefix, skip_title_guard)
    opened_path = out_dir / f"{shot_prefix}-opened.png"
    if not guard["ok"]:
        record_event(
            chat_name=target.name,
            query=target.query,
            action="open",
            status="title-guard-failed",
            db_path=mirror_db,
            screenshot_path=str(opened_path),
            metadata={"target": target.__dict__, "guard": guard},
        )
        raise RuntimeError(f"Opened chat title guard failed for {target.name}: OCR={guard.get('ocr_text', '')!r}")

    if not do_send and not compose_dry_run:
        record_event(
            chat_name=target.name,
            query=target.query,
            action="open",
            status="dry-run-opened",
            db_path=mirror_db,
            screenshot_path=str(opened_path),
            metadata={"target": target.__dict__, "guard": guard},
        )
        return {"target": target.name, "status": "dry-run-opened", "screenshot_prefix": shot_prefix}

    # Click the message composer. This is deliberately biased toward the lower
    # right pane so it does not send from the search box.
    click(env, window.x + int(window.width * 0.66), window.y + window.height - 80)
    time.sleep(pause)
    hotkey(env, "ctrl+a")
    time.sleep(0.2)
    key(env, "BackSpace")
    time.sleep(0.2)
    paste_text(env, message)
    time.sleep(pause)
    screenshot(env, out_dir / f"{shot_prefix}-composed.png")
    if do_send:
        key(env, "Return")
        time.sleep(pause)
        screenshot(env, out_dir / f"{shot_prefix}-sent.png")
        status = "sent"
        evidence_path = out_dir / f"{shot_prefix}-sent.png"
    else:
        status = "dry-run-composed"
        evidence_path = out_dir / f"{shot_prefix}-composed.png"
    record_event(
        chat_name=target.name,
        query=target.query,
        action="send",
        direction="outbound",
        message=message,
        status=status,
        db_path=mirror_db,
        screenshot_path=str(evidence_path),
        metadata={"target": target.__dict__, "guard": guard},
    )
    return {"target": target.name, "status": status, "screenshot_prefix": shot_prefix}


def open_target(
    env: dict[str, str],
    window: Window,
    target: TargetSpec,
    pause: float,
    out_dir: Path,
    shot_prefix: str,
    skip_title_guard: bool,
) -> dict[str, Any]:
    def verify(label: str) -> dict[str, Any]:
        time.sleep(max(pause, 3.2))
        opened = out_dir / f"{shot_prefix}-opened.png"
        screenshot(env, opened)
        if skip_title_guard:
            return {"ok": True, "method": label, "ocr_text": ""}
        return verify_opened_title(env, window, opened, target, out_dir / f"{shot_prefix}-title.png", label)

    if target.open_click:
        click(env, window.x + target.open_click[0], window.y + target.open_click[1])
        return verify("open_click")

    search_for_target(env, window, target.query, pause)
    screenshot(env, out_dir / f"{shot_prefix}-search.png")
    attempts: list[dict[str, Any]] = []
    for label, point in target_click_candidates(target):
        click(env, window.x + point[0], window.y + point[1])
        guard = verify(label)
        attempts.append(guard)
        if guard["ok"]:
            return guard
        close_secondary_wechat_windows(env, window)
        search_for_target(env, window, target.query, pause)

    key(env, "Return")
    guard = verify("return")
    if attempts:
        guard = {**guard, "attempts": attempts}
    return guard


def target_click_candidates(target: TargetSpec) -> list[tuple[str, tuple[int, int]]]:
    """Return explicit click candidates while preserving the first configured point."""
    candidates: list[tuple[str, tuple[int, int]]] = []
    seen: set[tuple[int, int]] = set()
    if target.result_click:
        candidates.append(("result_click", target.result_click))
        seen.add(target.result_click)
    for index, point in enumerate(target.fallback_clicks, start=1):
        if point in seen:
            continue
        candidates.append((f"fallback_click_{index}", point))
        seen.add(point)
    return candidates


def search_for_target(env: dict[str, str], window: Window, query: str, pause: float) -> None:
    click(env, window.x + 118, window.y + 46)
    time.sleep(pause)
    hotkey(env, "ctrl+a")
    key(env, "BackSpace")
    paste_text(env, query)
    time.sleep(max(pause, 1.6))


def verify_opened_title(
    env: dict[str, str],
    window: Window,
    screenshot_path: Path,
    target: TargetSpec,
    crop_path: Path,
    method: str,
) -> dict[str, Any]:
    left = window.x + 260
    top = window.y
    width = max(300, window.width - 260)
    height = 92
    run(
        [
            "convert",
            str(screenshot_path),
            "-crop",
            f"{width}x{height}+{left}+{top}",
            "-colorspace",
            "Gray",
            "-resize",
            "200%",
            str(crop_path),
        ],
        env=env,
    )
    proc = run(["tesseract", str(crop_path), "stdout", "-l", "chi_sim+chi_tra+eng", "--psm", "6"], env=env, check=False)
    ocr_text = proc.stdout.strip()
    expected = normalize_title(target.expected_title)
    observed = normalize_title(ocr_text)
    return {
        "ok": bool(expected and expected in observed),
        "method": method,
        "expected_title": target.expected_title,
        "ocr_text": ocr_text,
        "title_crop": str(crop_path),
    }


def normalize_title(text: str) -> str:
    return "".join(ch.lower() for ch in str(text or "") if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def find_wechat_window(env: dict[str, str]) -> Window | None:
    ids = run(["xdotool", "search", "--onlyvisible", "--class", "wechat"], env=env, check=False).stdout.split()
    candidates: list[Window] = []
    for wid in ids:
        geom = run(["xdotool", "getwindowgeometry", "--shell", wid], env=env, check=False).stdout
        values: dict[str, int] = {}
        for line in geom.splitlines():
            if "=" not in line:
                continue
            key_name, raw = line.split("=", 1)
            try:
                values[key_name] = int(raw)
            except ValueError:
                pass
        if {"X", "Y", "WIDTH", "HEIGHT"} <= values.keys():
            candidates.append(Window(wid, values["X"], values["Y"], values["WIDTH"], values["HEIGHT"]))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.width * item.height)


def close_secondary_wechat_windows(env: dict[str, str], main: Window) -> None:
    ids = run(["xdotool", "search", "--onlyvisible", "--class", "wechat"], env=env, check=False).stdout.split()
    main_area = main.width * main.height
    for wid in ids:
        if wid == main.wid:
            continue
        geom = run(["xdotool", "getwindowgeometry", "--shell", wid], env=env, check=False).stdout
        values: dict[str, int] = {}
        for line in geom.splitlines():
            if "=" not in line:
                continue
            key_name, raw = line.split("=", 1)
            try:
                values[key_name] = int(raw)
            except ValueError:
                pass
        area = values.get("WIDTH", 0) * values.get("HEIGHT", 0)
        if 20_000 <= area < main_area:
            run(["xdotool", "windowclose", wid], env=env, check=False)
    time.sleep(0.5)


def focus(env: dict[str, str], window: Window) -> None:
    run(["xdotool", "windowfocus", window.wid], env=env, check=False)
    run(["xdotool", "windowraise", window.wid], env=env, check=False)
    time.sleep(0.2)


def click(env: dict[str, str], x: int, y: int) -> None:
    run(["xdotool", "mousemove", str(x), str(y), "click", "1"], env=env)


def key(env: dict[str, str], name: str) -> None:
    run(["xdotool", "key", name], env=env)


def hotkey(env: dict[str, str], name: str) -> None:
    run(["xdotool", "key", name], env=env)


def paste_text(env: dict[str, str], text: str) -> None:
    proc = subprocess.Popen(
        ["xclip", "-selection", "clipboard"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdin is not None
    proc.stdin.write(text)
    proc.stdin.close()
    time.sleep(0.2)
    run(["xdotool", "key", "ctrl+v"], env=env)
    time.sleep(0.2)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    if proc.returncode not in (0, -15, None):
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"xclip failed to set clipboard: {stderr.strip()}")


def screenshot(env: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run(["import", "-window", "root", str(path)], env=env, check=False)


def require_tools(*names: str) -> None:
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"Missing required tool(s): {', '.join(missing)}")


def run(command: list[str], *, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {proc.stderr.strip()}")
    return proc


def safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value).strip("-")
    return cleaned[:48] or "target"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
