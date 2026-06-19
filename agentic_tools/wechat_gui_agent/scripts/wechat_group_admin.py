#!/usr/bin/env python3
"""Best-effort group administration helpers for the visible Linux WeChat GUI."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import os
import subprocess
import time

from wechat_gui_send import find_wechat_window, focus, paste_text, run as run_gui
from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", default=":97")
    parser.add_argument("--chat", default="wechat-chat")
    parser.add_argument("--rename")
    parser.add_argument("--dry-run", action="store_true", help="Capture the rename path without typing or confirming.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F"))
    parser.add_argument("--mirror-db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    env = os.environ.copy()
    env["DISPLAY"] = args.display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    window = find_wechat_window(env)
    if not window:
        raise SystemExit(f"No visible WeChat window on {args.display}")
    focus(env, window)

    if args.rename:
        result = rename_group_best_effort(env, window, args.rename, args.output_dir, dry_run=args.dry_run)
        record_event(
            chat_name=args.chat,
            action="rename_group",
            status=result["status"],
            db_path=args.mirror_db,
            screenshot_path=result["screenshot"],
            metadata=result,
        )
        print(result)
    return 0


def rename_group_best_effort(env: dict[str, str], window, new_name: str, out_dir: Path, *, dry_run: bool) -> dict[str, str]:
    run_dir = out_dir / f"{datetime.now().strftime('%H%M%S')}-group-rename"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Open right-side group settings drawer.
    run_gui(["xdotool", "mousemove", str(window.x + window.width - 32), str(window.y + 51), "click", "1"], env=env)
    time.sleep(0.8)
    screenshot(env, run_dir / "01-settings.png")

    # Known Linux WeChat 4.x locations. The blank row under Group Name becomes
    # an input field after clicking; pasting is safe only after that row has
    # focus. Dry-run captures the path without typing.
    group_name_input = (window.x + window.width - 140, window.y + 328)
    run_gui(["xdotool", "mousemove", str(group_name_input[0]), str(group_name_input[1]), "click", "1"], env=env, check=False)
    time.sleep(0.4)
    screenshot(env, run_dir / "02-group-name-field.png")
    if dry_run:
        return {
            "status": "dry-run",
            "requested_name": new_name,
            "screenshot": str(run_dir / "02-group-name-field.png"),
            "run_dir": str(run_dir),
            "note": "Captured group-name field location without typing.",
        }

    paste_text(env, new_name)
    time.sleep(0.8)
    screenshot(env, run_dir / "03-pasted-name.png")
    run_gui(["xdotool", "key", "Return"], env=env, check=False)
    time.sleep(1.0)
    screenshot(env, run_dir / "04-confirm-dialog.png")
    click_modify_confirmation(env, window)
    time.sleep(1.4)
    screenshot(env, run_dir / "05-after-confirm.png")

    return {
        "status": "submitted",
        "requested_name": new_name,
        "screenshot": str(run_dir / "05-after-confirm.png"),
        "run_dir": str(run_dir),
        "note": "Pasted into Group Name, confirmed with Enter, and clicked Modify.",
    }


def rename_group_evidence_only(env: dict[str, str], window, new_name: str, run_dir: Path) -> dict[str, str]:
    attempts = [
        ("group-name-label", window.x + int(window.width * 0.78), window.y + 300),
        ("group-name-row-center", window.x + int(window.width * 0.88), window.y + 328),
        ("group-name-row-right", window.x + window.width - 36, window.y + 328),
        ("header-title", window.x + int(window.width * 0.52), window.y + 46),
    ]
    for index, (name, x, y) in enumerate(attempts, start=2):
        run_gui(["xdotool", "mousemove", str(x), str(y), "click", "--repeat", "2", "--delay", "140", "1"], env=env, check=False)
        time.sleep(0.5)
        screenshot(env, run_dir / f"{index:02d}-{name}.png")
        # If an edit field did open, paste the name and press Return. If it did
        # not open, this can otherwise paste into chat, so only type after an
        # operator has confirmed an edit field in the screenshot. The automated
        # safe default is evidence-only.

    return {
        "status": "editor-not-confirmed",
        "requested_name": new_name,
        "screenshot": str(run_dir / "01-settings.png"),
        "run_dir": str(run_dir),
        "note": "Linux WeChat did not expose a confirmed editable group-name field. Rename needs manual UI confirmation or a supported API path.",
    }


def click_modify_confirmation(env: dict[str, str], window) -> None:
    # The Linux WeChat confirmation dialog is centered in the chat pane. These
    # relative coordinates target the green Modify button after Enter opens it.
    run_gui(
        [
            "xdotool",
            "mousemove",
            str(window.x + int(window.width * 0.44)),
            str(window.y + int(window.height * 0.535)),
            "click",
            "1",
        ],
        env=env,
        check=False,
    )


def screenshot(env: dict[str, str], path: Path) -> None:
    run_gui(["import", "-window", "root", str(path)], env=env, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
