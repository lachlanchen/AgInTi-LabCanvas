#!/usr/bin/env python3
"""Open or execute the native WeChat group creation flow through the GUI."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", default=":97")
    parser.add_argument("--plan", type=Path, help="JSON plan with member checkbox offsets.")
    parser.add_argument("--member-query", action="append", default=[], help="Search query/alias for a contact to add. Repeatable.")
    parser.add_argument("--search-box", default=None, help="Picker search box offset as x,y. Default comes from plan or Linux WeChat 4.x.")
    parser.add_argument("--search-result-checkbox", default=None, help="First search result checkbox offset as x,y.")
    parser.add_argument("--create", action="store_true", help="Click member checkboxes and Finish.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F"))
    parser.add_argument("--mirror-db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    plan = load_plan(args.plan)
    if args.member_query:
        plan["member_queries"] = args.member_query
    if args.search_box:
        plan["search_box"] = point_string(args.search_box)
    if args.search_result_checkbox:
        plan["search_result_checkbox"] = point_string(args.search_result_checkbox)
    env = os.environ.copy()
    env["DISPLAY"] = args.display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    window = find_window(env)
    open_picker(env, window)
    picker_path = args.output_dir / "group-create-picker.png"
    screenshot(env, picker_path)

    if not args.create:
        record_event(
            chat_name=plan["group_name"],
            action="create_group",
            status="dry-run-picker-opened",
            db_path=args.mirror_db,
            screenshot_path=str(picker_path),
            metadata=plan,
        )
        print(json.dumps({"status": "dry-run-picker-opened", "screenshot": str(picker_path)}, ensure_ascii=False, indent=2))
        return 0

    if plan.get("member_queries"):
        for query in plan["member_queries"]:
            select_member_by_search(env, window, plan, str(query), args.output_dir)
    else:
        for member in plan["members"]:
            x_off, y_off = point(member["checkbox"])
            click(env, window["x"] + x_off, window["y"] + y_off)
            time.sleep(0.4)
    selected_path = args.output_dir / "group-create-selected.png"
    screenshot(env, selected_path)
    finish_x, finish_y = point(plan["finish_click"])
    click(env, window["x"] + finish_x, window["y"] + finish_y)
    time.sleep(2.0)
    created_path = args.output_dir / "group-create-after-finish.png"
    screenshot(env, created_path)
    record_event(
        chat_name=plan["group_name"],
        action="create_group",
        status="created-clicked-finish",
        db_path=args.mirror_db,
        screenshot_path=str(created_path),
        metadata=plan,
    )
    print(json.dumps({"status": "created-clicked-finish", "screenshot": str(created_path)}, ensure_ascii=False, indent=2))
    return 0


def load_plan(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "group_name": "dry-run-group",
            "members": [],
            "member_queries": [],
            "search_box": [261, 120],
            "search_result_checkbox": [177, 209],
            "finish_click": [585, 606],
        }
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.setdefault("group_name", "wechat-group")
    raw.setdefault("members", [])
    raw.setdefault("member_queries", [])
    raw.setdefault("search_box", [261, 120])
    raw.setdefault("search_result_checkbox", [177, 209])
    raw.setdefault("finish_click", [585, 606])
    return raw


def open_picker(env: dict[str, str], window: dict[str, int | str]) -> None:
    focus(env, str(window["wid"]))
    click(env, int(window["x"]) + 339, int(window["y"]) + 43)
    time.sleep(0.4)
    click(env, int(window["x"]) + 346, int(window["y"]) + 83)
    time.sleep(1.5)


def select_member_by_search(env: dict[str, str], window: dict[str, int | str], plan: dict[str, Any], query: str, out_dir: Path) -> None:
    search_x, search_y = point(plan.get("search_box", [261, 120]))
    checkbox_x, checkbox_y = point(plan.get("search_result_checkbox", [177, 209]))
    click(env, int(window["x"]) + search_x, int(window["y"]) + search_y)
    time.sleep(0.2)
    key(env, "ctrl+a")
    key(env, "BackSpace")
    paste_text(env, query)
    time.sleep(0.8)
    screenshot(env, out_dir / f"group-create-search-{safe_name(query)}.png")
    click(env, int(window["x"]) + checkbox_x, int(window["y"]) + checkbox_y)
    time.sleep(0.5)
    screenshot(env, out_dir / f"group-create-selected-{safe_name(query)}.png")


def find_window(env: dict[str, str]) -> dict[str, int | str]:
    ids = run(["xdotool", "search", "--onlyvisible", "--class", "wechat"], env).stdout.split()
    best: dict[str, int | str] | None = None
    best_area = 0
    for wid in ids:
        geom = run(["xdotool", "getwindowgeometry", "--shell", wid], env).stdout
        vals: dict[str, int | str] = {"wid": wid}
        for line in geom.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            try:
                vals[key.lower()] = int(value)
            except ValueError:
                pass
        area = int(vals.get("width", 0)) * int(vals.get("height", 0))
        if area > best_area:
            best = vals
            best_area = area
    if not best:
        raise SystemExit("No visible WeChat window found")
    return best


def focus(env: dict[str, str], wid: str) -> None:
    run(["xdotool", "windowfocus", wid], env, check=False)
    run(["xdotool", "windowraise", wid], env, check=False)


def click(env: dict[str, str], x: int, y: int) -> None:
    run(["xdotool", "mousemove", str(x), str(y), "click", "1"], env)


def key(env: dict[str, str], name: str) -> None:
    run(["xdotool", "key", name], env)


def paste_text(env: dict[str, str], text: str) -> None:
    proc = subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError("xclip failed to set clipboard")
    key(env, "ctrl+v")


def screenshot(env: dict[str, str], path: Path) -> None:
    run(["import", "-window", "root", str(path)], env, check=False)


def point(value: Any) -> tuple[int, int]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise SystemExit("Expected point [x_offset, y_offset]")
    return int(value[0]), int(value[1])


def point_string(value: str) -> list[int]:
    pieces = [piece.strip() for piece in value.split(",")]
    if len(pieces) != 2:
        raise SystemExit("Expected point as x,y")
    return [int(pieces[0]), int(pieces[1])]


def safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value).strip("-")
    return cleaned[:48] or "query"


def run(command: list[str], env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {proc.stderr.strip()}")
    return proc


if __name__ == "__main__":
    raise SystemExit(main())
