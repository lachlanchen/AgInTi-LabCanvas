#!/usr/bin/env python3
"""Read-only visible capture helper for WeChat Channels / Shipinhao pages."""

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


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_DISPLAY = ":97"
DEFAULT_LANG = "chi_sim+chi_tra+eng"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", default=DEFAULT_DISPLAY)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scrolls", type=int, default=2, help="Number of read-only PageDown captures after the first screenshot.")
    parser.add_argument("--interval", type=float, default=0.8)
    parser.add_argument("--lang", default=os.environ.get("WECHAT_OCR_LANG", DEFAULT_LANG))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or default_output_dir()
    payload = build_plan(output_dir=output_dir, display=args.display, scrolls=args.scrolls, lang=args.lang)
    if args.dry_run:
        payload["status"] = "dry-run"
        print_payload(payload, args.json)
        return 0

    missing = [name for name in ("xdotool", "import") if not shutil.which(name)]
    if missing:
        payload.update({"ok": False, "status": "missing-tools", "missing": missing})
        print_payload(payload, args.json)
        return 1

    env = os.environ.copy()
    env["DISPLAY"] = args.display
    window = find_wechat_window(env)
    if not window:
        payload.update({"ok": False, "status": "wechat-window-not-found"})
        print_payload(payload, args.json)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    payload["status"] = "capturing"
    payload["window"] = window
    captures: list[dict[str, Any]] = []
    for index in range(max(0, args.scrolls) + 1):
        if index > 0:
            activate_window(window["id"], env)
            run(["xdotool", "key", "--clearmodifiers", "Page_Down"], env=env, check=False)
            time.sleep(max(0.0, args.interval))
        screenshot_path = output_dir / f"shipinhao-visible-{index:02d}.png"
        text_path = output_dir / f"shipinhao-visible-{index:02d}.ocr.txt"
        shot = capture_window(window["id"], screenshot_path, env)
        ocr = ocr_image(screenshot_path, text_path, args.lang) if shot.get("ok") else {"ok": False, "text": "", "error": shot.get("error", "")}
        captures.append(
            {
                "index": index,
                "screenshot": str(screenshot_path),
                "ocr_text": str(text_path) if text_path.exists() else "",
                "screenshot_ok": bool(shot.get("ok")),
                "ocr_ok": bool(ocr.get("ok")),
                "text_preview": collapse_text(str(ocr.get("text") or ""), 500),
                "error": shot.get("error") or ocr.get("error") or "",
            }
        )

    combined_text = "\n\n".join(Path(item["ocr_text"]).read_text(encoding="utf-8", errors="replace") for item in captures if item.get("ocr_text"))
    combined_path = output_dir / "shipinhao-visible-comments.md"
    combined_path.write_text(render_markdown(captures, combined_text), encoding="utf-8")
    payload.update(
        {
            "ok": True,
            "status": "captured",
            "captures": captures,
            "combined_markdown": str(combined_path),
            "text_preview": collapse_text(combined_text, 1200),
        }
    )
    manifest_path = output_dir / "manifest.json"
    payload["manifest_json"] = str(manifest_path)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print_payload(payload, args.json)
    return 0


def default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return PRIVATE / "shipinhao_native_capture" / stamp


def build_plan(*, output_dir: Path, display: str, scrolls: int, lang: str) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "planned",
        "read_only": True,
        "public_actions": False,
        "display": display,
        "output_dir": str(output_dir),
        "scrolls": max(0, scrolls),
        "ocr_lang": lang,
        "purpose": "Capture visible WeChat Channels title/comments/transcript evidence from the native WeChat GUI.",
        "steps": [
            "Open the Shipinhao/Finder card in the official WeChat client or leave the detail page visible.",
            "Capture the visible WeChat window.",
            "OCR the screenshot for title, description, visible comments, Yuanbao/transcript requests, and quoted lines.",
            "PageDown the visible page/comment pane and repeat only read-only captures.",
            "Write screenshots, OCR text, and a manifest under the private output directory.",
        ],
        "non_goals": [
            "No likes, follows, reposts, comments, or Yuanbao prompts.",
            "No external browser for mp.weixin verification.",
            "No claim that the video was watched unless media/transcript/visible text was actually captured.",
        ],
    }


def find_wechat_window(env: dict[str, str]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for window_class in ("wechat", "WeChat", "wechat.exe"):
        proc = run(["xdotool", "search", "--onlyvisible", "--class", window_class], env=env, check=False)
        for wid in proc.stdout.split():
            geom = window_geometry(wid, env)
            if geom:
                candidates.append(geom)
    if not candidates:
        return None
    candidates.sort(key=lambda item: int(item.get("width", 0)) * int(item.get("height", 0)), reverse=True)
    return candidates[0]


def window_geometry(wid: str, env: dict[str, str]) -> dict[str, Any] | None:
    proc = run(["xdotool", "getwindowgeometry", "--shell", wid], env=env, check=False)
    if proc.returncode != 0:
        return None
    values: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        try:
            values[key.lower()] = int(raw)
        except ValueError:
            pass
    if not values.get("width") or not values.get("height"):
        return None
    title = run(["xdotool", "getwindowname", wid], env=env, check=False).stdout.strip()
    return {"id": wid, "title": title, **values}


def activate_window(wid: str, env: dict[str, str]) -> None:
    run(["xdotool", "windowactivate", "--sync", wid], env=env, check=False)


def capture_window(wid: str, path: Path, env: dict[str, str]) -> dict[str, Any]:
    activate_window(wid, env)
    path.parent.mkdir(parents=True, exist_ok=True)
    proc = run(["import", "-window", wid, str(path)], env=env, check=False)
    return {"ok": proc.returncode == 0 and path.is_file(), "error": collapse_text(proc.stderr or proc.stdout, 500)}


def ocr_image(image_path: Path, text_path: Path, lang: str) -> dict[str, Any]:
    if not shutil.which("tesseract"):
        return {"ok": False, "text": "", "error": "tesseract not installed"}
    proc = run(["tesseract", str(image_path), "stdout", "-l", lang, "--psm", "6"], check=False)
    text = proc.stdout.strip()
    text_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return {"ok": proc.returncode == 0, "text": text, "error": collapse_text(proc.stderr, 500)}


def render_markdown(captures: list[dict[str, Any]], combined_text: str) -> str:
    lines = ["# Shipinhao Native Visible Capture", "", "Read-only OCR capture from the native WeChat/Channels GUI.", ""]
    lines.extend(["## Captures", ""])
    for item in captures:
        lines.append(f"- {item['index']}: screenshot=`{item.get('screenshot')}` ocr=`{item.get('ocr_text')}`")
    lines.extend(["", "## OCR Text", "", "```text", combined_text.strip(), "```", ""])
    return "\n".join(lines)


def run(command: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, capture_output=True, text=True, check=check)


def collapse_text(text: str, limit: int) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized if len(normalized) <= limit else normalized[:limit] + "..."


def print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload.get("status", ""))
        for step in payload.get("steps") or []:
            print(f"- {step}")


if __name__ == "__main__":
    raise SystemExit(main())
