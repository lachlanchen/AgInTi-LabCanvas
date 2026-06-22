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
import hashlib
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
    expected_title_aliases: tuple[str, ...] = ()
    allow_title_guard_fallback: bool = False
    allow_live_title_guard_fallback: bool = False
    result_click: tuple[int, int] | None = None
    fallback_clicks: tuple[tuple[int, int], ...] = ()
    open_click: tuple[int, int] | None = None


class WeChatLockedError(RuntimeError):
    """Raised when the official WeChat client requires phone unlock."""


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
    parser.add_argument("--prefer-current", action="store_true", help="If the visible chat title already matches, send there without searching first.")
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
                args.prefer_current,
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
    expected_title_aliases = strings_from_raw(raw.get("expected_title_aliases") or raw.get("title_aliases"))
    if not name or not query:
        raise SystemExit("Target object requires name/target and query")
    return TargetSpec(
        name=name,
        query=query,
        expected_title=expected_title or name,
        expected_title_aliases=expected_title_aliases,
        allow_title_guard_fallback=bool(raw.get("allow_title_guard_fallback") or raw.get("relaxed_title_guard")),
        allow_live_title_guard_fallback=bool(raw.get("allow_live_title_guard_fallback")),
        result_click=point_from_raw(raw.get("result_click")),
        fallback_clicks=points_from_raw(raw.get("fallback_clicks")),
        open_click=point_from_raw(raw.get("open_click")),
    )


def strings_from_raw(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if not isinstance(raw, list | tuple):
        raise SystemExit("title aliases must be a string or list of strings")
    return tuple(str(item).strip() for item in raw if str(item).strip())


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
    prefer_current: bool,
    out_dir: Path,
    mirror_db: Path,
    index: int,
) -> dict[str, str]:
    focus(env, window)
    shot_prefix = f"{index:02d}-{safe_name(target.name)}"
    before_path = out_dir / f"{shot_prefix}-before.png"
    screenshot(env, before_path)
    if not skip_title_guard:
        locked = detect_wechat_locked(env, window, before_path, out_dir / f"{shot_prefix}-locked.png")
        if locked["locked"]:
            record_event(
                chat_name=target.name,
                query=target.query,
                action="open",
                status="wechat-locked",
                db_path=mirror_db,
                screenshot_path=str(before_path),
                metadata={"target": target.__dict__, "lock": locked},
            )
            raise WeChatLockedError(
                "WECHAT_LOCKED: Weixin for Linux is locked and requires normal phone-side unlock before GUI sends."
            )

    guard = open_target(env, window, target, pause, out_dir, shot_prefix, skip_title_guard, prefer_current)
    opened_path = out_dir / f"{shot_prefix}-opened.png"
    if not guard["ok"]:
        fallback_allowed = target.allow_title_guard_fallback and (not do_send or target.allow_live_title_guard_fallback)
        if fallback_allowed:
            guard = {**guard, "ok": True, "relaxed_title_guard": True}
        else:
            record_event(
                chat_name=target.name,
                query=target.query,
                action="open",
                status="title-guard-failed",
                db_path=mirror_db,
                screenshot_path=str(opened_path),
                metadata={"target": target.__dict__, "guard": guard},
            )
            live_note = " Live sends do not allow relaxed title fallback." if do_send and target.allow_title_guard_fallback else ""
            raise RuntimeError(f"Opened chat title guard failed for {target.name}: OCR={guard.get('ocr_text', '')!r}.{live_note}")
    if guard.get("relaxed_title_guard"):
        record_event(
            chat_name=target.name,
            query=target.query,
            action="open",
            status="title-guard-relaxed",
            db_path=mirror_db,
            screenshot_path=str(opened_path),
            metadata={"target": target.__dict__, "guard": guard},
        )

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

    compose_window = window_from_guard(guard) or window
    focus(env, compose_window)

    # Click the message composer. This is deliberately biased toward the lower
    # right pane so it does not send from the search box.
    click(env, compose_window.x + int(compose_window.width * 0.66), compose_window.y + compose_window.height - 80)
    time.sleep(pause)
    hotkey(env, "ctrl+a")
    time.sleep(0.2)
    key(env, "BackSpace")
    time.sleep(0.2)
    paste_text(env, message)
    time.sleep(pause)
    composed_path = out_dir / f"{shot_prefix}-composed.png"
    screenshot(env, composed_path)
    if same_screenshot(opened_path, composed_path):
        raise RuntimeError(f"Message compose did not visibly change the WeChat window for {target.name}")
    if do_send:
        key(env, "Return")
        time.sleep(pause)
        sent_path = out_dir / f"{shot_prefix}-sent.png"
        screenshot(env, sent_path)
        if same_screenshot(composed_path, sent_path):
            raise RuntimeError(f"Message send did not visibly change the WeChat window for {target.name}")
        status = "sent"
        evidence_path = sent_path
    else:
        status = "dry-run-composed"
        evidence_path = composed_path
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
    prefer_current: bool = False,
) -> dict[str, Any]:
    def verify(label: str) -> dict[str, Any]:
        time.sleep(max(pause, float(os.environ.get("WECHAT_INITIAL_TITLE_WAIT", "1.2"))))
        deadline = time.monotonic() + max(max(pause, 1.8), float(os.environ.get("WECHAT_TITLE_RETRY_SECONDS", "3.5")))
        last_guard: dict[str, Any] = {"ok": False, "method": label, "ocr_text": ""}
        while True:
            opened = out_dir / f"{shot_prefix}-opened.png"
            screenshot(env, opened)
            if skip_title_guard:
                compose_window = focused_window(env) or window
                return {
                    "ok": True,
                    "method": label,
                    "ocr_text": "",
                    "compose_window": window_to_dict(compose_window),
                }
            for candidate in title_window_candidates(env, window):
                suffix = "title" if candidate.wid == window.wid else f"title-{safe_name(candidate.wid)}"
                guard = verify_opened_title(env, candidate, opened, target, out_dir / f"{shot_prefix}-{suffix}.png", label)
                if guard["ok"]:
                    return guard
                last_guard = guard
            if time.monotonic() >= deadline:
                return last_guard
            time.sleep(max(pause, 1.0))

    if prefer_current:
        current_guard = verify("current")
        if current_guard["ok"]:
            return current_guard

    if target.open_click:
        click(env, window.x + target.open_click[0], window.y + target.open_click[1])
        return verify("open_click")

    search_for_target(env, window, target.query, pause)
    screenshot(env, out_dir / f"{shot_prefix}-search.png")
    attempts: list[dict[str, Any]] = []
    for label, point in target_click_candidates(target):
        double_click(env, window.x + point[0], window.y + point[1])
        guard = verify(f"{label}_double")
        attempts.append(guard)
        if guard["ok"]:
            return guard
        search_for_target(env, window, target.query, pause)

    key(env, "Return")
    guard = verify("return")
    if attempts:
        guard = {**guard, "attempts": attempts}
    return guard


def target_click_candidates(target: TargetSpec) -> list[tuple[str, tuple[int, int]]]:
    """Return result click candidates while preserving configured points first."""
    candidates: list[tuple[str, tuple[int, int]]] = []
    seen: set[tuple[int, int]] = set()

    def add(label: str, point: tuple[int, int]) -> None:
        if point in seen:
            return
        candidates.append((label, point))
        seen.add(point)

    if target.result_click:
        x, y = target.result_click
        add("result_click", target.result_click)
        for label, point in (
            ("result_click_row_center", (x, max(70, y - 26))),
            ("result_click_title_offset", (x + 35, max(70, y - 26))),
            ("result_click_preview_offset", (x + 35, y)),
        ):
            add(label, point)
    for index, point in enumerate(target.fallback_clicks, start=1):
        add(f"fallback_click_{index}", point)
    for index, point in enumerate(((165, 100), (205, 100), (165, 125), (205, 125), (165, 155)), start=1):
        add(f"default_search_row_{index}", point)
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
    expected_titles = [target.expected_title, *target.expected_title_aliases]
    expected = [normalize_title(item) for item in expected_titles if normalize_title(item)]
    window_title = run(["xdotool", "getwindowname", window.wid], env=env, check=False).stdout.strip()
    window_reject_reason = chat_surface_reject_reason(window_title)
    window_title_ok = (
        bool(window_title)
        and not window_reject_reason
        and any(item in normalize_title(window_title) for item in expected)
    )
    if window_title_ok:
        return {
            "ok": True,
            "method": method,
            "expected_title": target.expected_title,
            "expected_title_aliases": list(target.expected_title_aliases),
            "ocr_text": window_title,
            "title_crop": "",
            "title_crops": [],
            "window_title": window_title,
            "compose_window": window_to_dict(window),
        }
    ocr_texts: list[str] = []
    crop_paths: list[str] = []
    ok = False
    for region in title_crop_regions(window):
        region_crop = crop_path.with_name(f"{crop_path.stem}-{region['label']}{crop_path.suffix}")
        run(
            [
                "convert",
                str(screenshot_path),
                "-crop",
                f"{region['width']}x{region['height']}+{region['left']}+{region['top']}",
                "-colorspace",
                "Gray",
                "-resize",
                "200%",
                str(region_crop),
            ],
            env=env,
        )
        proc = run(["tesseract", str(region_crop), "stdout", "-l", "chi_sim+chi_tra+eng", "--psm", "6"], env=env, check=False)
        text = proc.stdout.strip()
        ocr_texts.append(text)
        crop_paths.append(str(region_crop))
        reject_reason = chat_surface_reject_reason(text)
        if reject_reason:
            return {
                "ok": False,
                "method": method,
                "expected_title": target.expected_title,
                "expected_title_aliases": list(target.expected_title_aliases),
                "ocr_text": "\n".join(text for text in ocr_texts if text).strip(),
                "title_crop": str(region_crop),
                "title_crops": crop_paths,
                "window_title": window_title,
                "compose_window": window_to_dict(window),
                "surface_reject_reason": reject_reason,
            }
        observed = normalize_title(text)
        if any(item in observed for item in expected):
            ok = True
            crop_path = region_crop
            break
    return {
        "ok": ok,
        "method": method,
        "expected_title": target.expected_title,
        "expected_title_aliases": list(target.expected_title_aliases),
        "ocr_text": "\n".join(text for text in ocr_texts if text).strip(),
        "title_crop": str(crop_path),
        "title_crops": crop_paths,
        "window_title": window_title,
        "compose_window": window_to_dict(window),
        "surface_reject_reason": window_reject_reason,
    }


def normalize_title(text: str) -> str:
    return "".join(ch.lower() for ch in str(text or "") if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def chat_surface_reject_reason(text: str) -> str:
    lowered = str(text or "").lower()
    normalized = normalize_title(text)
    raw_markers = {
        "ai search": "ai-search",
        " - search": "search-webview",
        "- search": "search-webview",
        "ask a follow-up": "ai-search",
    }
    normalized_markers = {
        "aisearch": "ai-search",
        "问ai": "ai-search",
        "問ai": "ai-search",
        "快速回答": "ai-search",
        "askafollowup": "ai-search",
    }
    for marker, reason in raw_markers.items():
        if marker in lowered:
            return reason
    for marker, reason in normalized_markers.items():
        if marker in normalized:
            return reason
    return ""


def detect_wechat_locked(env: dict[str, str], window: Window, screenshot_path: Path, crop_path: Path) -> dict[str, Any]:
    try:
        run(
            [
                "convert",
                str(screenshot_path),
                "-crop",
                f"{window.width}x{window.height}+{window.x}+{window.y}",
                "-colorspace",
                "Gray",
                "-resize",
                "160%",
                str(crop_path),
            ],
            env=env,
        )
    except Exception as exc:
        return {"locked": False, "ocr_text": "", "lock_crop": str(crop_path), "error": str(exc)[:500]}
    proc = run(["tesseract", str(crop_path), "stdout", "-l", "chi_sim+chi_tra+eng", "--psm", "6"], env=env, check=False)
    ocr_text = proc.stdout.strip()
    observed = normalize_title(ocr_text)
    locked = any(
        marker in observed
        for marker in (
            "weixinforlinuxislocked",
            "unlockonphone",
            "手机微信聊天列表顶部的状态栏解锁",
            "微信聊天列表顶部的状态栏解锁",
        )
    )
    return {
        "locked": locked,
        "ocr_text": ocr_text,
        "lock_crop": str(crop_path),
    }


def title_crop_regions(window: Window) -> list[dict[str, int | str]]:
    """OCR regions that avoid the left chat list but cover main and popup chats."""
    regions: list[dict[str, int | str]] = []
    if window.width < 760:
        regions.append(
            {
                "label": "popup_header",
                "left": window.x + 18,
                "top": window.y + 35,
                "width": max(260, window.width - 70),
                "height": 78,
            }
        )
    else:
        regions.append(
            {
                "label": "main_right_header",
                "left": window.x + 360,
                "top": window.y + 32,
                "width": max(300, window.width - 390),
                "height": 78,
            }
        )
        regions.append(
            {
                "label": "main_right_header_high",
                "left": window.x + 360,
                "top": window.y,
                "width": max(300, window.width - 390),
                "height": 96,
            }
        )
    return regions


def window_to_dict(window: Window) -> dict[str, int | str]:
    return {
        "wid": window.wid,
        "x": window.x,
        "y": window.y,
        "width": window.width,
        "height": window.height,
    }


def window_from_guard(guard: dict[str, Any]) -> Window | None:
    raw = guard.get("compose_window")
    if not isinstance(raw, dict):
        return None
    try:
        return Window(
            wid=str(raw.get("wid") or ""),
            x=int(raw["x"]),
            y=int(raw["y"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def title_window_candidates(env: dict[str, str], main: Window) -> list[Window]:
    candidates: list[Window] = []
    focused = focused_window(env)
    if focused and focused.width >= 480 and focused.height >= 420:
        candidates.append(focused)
    candidates.append(main)
    seen: set[str] = set()
    unique: list[Window] = []
    for candidate in candidates:
        if candidate.wid in seen:
            continue
        unique.append(candidate)
        seen.add(candidate.wid)
    return unique


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


def focused_window(env: dict[str, str]) -> Window | None:
    geom = run(["xdotool", "getwindowfocus", "getwindowgeometry", "--shell"], env=env, check=False).stdout
    values: dict[str, int | str] = {}
    for line in geom.splitlines():
        if "=" not in line:
            continue
        key_name, raw = line.split("=", 1)
        if key_name == "WINDOW":
            values[key_name] = raw
            continue
        try:
            values[key_name] = int(raw)
        except ValueError:
            pass
    if {"WINDOW", "X", "Y", "WIDTH", "HEIGHT"} <= values.keys():
        return Window(
            str(values["WINDOW"]),
            int(values["X"]),
            int(values["Y"]),
            int(values["WIDTH"]),
            int(values["HEIGHT"]),
        )
    return None


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
        if 20_000 <= area < min(main_area, int(main_area * 0.25)):
            run(["xdotool", "windowclose", wid], env=env, check=False)
    time.sleep(0.5)


def focus(env: dict[str, str], window: Window) -> None:
    run(["xdotool", "windowfocus", window.wid], env=env, check=False)
    run(["xdotool", "windowraise", window.wid], env=env, check=False)
    time.sleep(0.2)


def click(env: dict[str, str], x: int, y: int) -> None:
    run(["xdotool", "mousemove", str(x), str(y), "click", "1"], env=env)


def double_click(env: dict[str, str], x: int, y: int) -> None:
    run(["xdotool", "mousemove", str(x), str(y), "click", "--repeat", "2", "--delay", "80", "1"], env=env)


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


def same_screenshot(first: Path, second: Path) -> bool:
    if not first.exists() or not second.exists():
        return False
    if first.stat().st_size != second.stat().st_size:
        return False
    return hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()


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
