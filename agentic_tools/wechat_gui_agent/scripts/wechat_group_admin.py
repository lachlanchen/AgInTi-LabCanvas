#!/usr/bin/env python3
"""Best-effort group administration helpers for the visible Linux WeChat GUI."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import os
import shutil
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
    parser.add_argument("--my-alias", help="Set this account's display name inside the visible group.")
    parser.add_argument("--dry-run", action="store_true", help="Open the target settings row and capture screenshots without typing.")
    parser.add_argument("--skip-ocr-guard", action="store_true", help="Allow confirmation even if row OCR cannot verify the target text.")
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
        result = edit_settings_row(
            env,
            window,
            "group_name",
            args.rename,
            args.output_dir,
            dry_run=args.dry_run,
            skip_ocr_guard=args.skip_ocr_guard,
        )
        record_event(
            chat_name=args.chat,
            action="rename_group",
            status=result["status"],
            db_path=args.mirror_db,
            screenshot_path=result["screenshot"],
            metadata=result,
        )
        print(result)
    if args.my_alias:
        result = edit_settings_row(
            env,
            window,
            "my_alias",
            args.my_alias,
            args.output_dir,
            dry_run=args.dry_run,
            skip_ocr_guard=args.skip_ocr_guard,
        )
        record_event(
            chat_name=args.chat,
            action="set_my_alias",
            status=result["status"],
            db_path=args.mirror_db,
            screenshot_path=result["screenshot"],
            metadata=result,
        )
        print(result)
    return 0


ROW_SPECS = {
    "group_name": {
        "action": "rename_group",
        "label": "Group Name",
        "click_offset": (805, 326),
        "crop_offset": (760, 286, 245, 78),
        "note": "Edited the Group Name row.",
    },
    "my_alias": {
        "action": "set_my_alias",
        "label": "My Alias in Group",
        "click_offset": (805, 531),
        "crop_offset": (760, 492, 245, 78),
        "note": "Edited the My Alias in Group row.",
    },
}


def edit_settings_row(
    env: dict[str, str],
    window,
    row_key: str,
    value: str,
    out_dir: Path,
    *,
    dry_run: bool,
    skip_ocr_guard: bool,
) -> dict[str, str]:
    spec = ROW_SPECS[row_key]
    run_dir = out_dir / f"{datetime.now().strftime('%H%M%S')}-{spec['action']}"
    run_dir.mkdir(parents=True, exist_ok=True)

    ensure_settings_drawer_open(env, window, run_dir)
    screenshot(env, run_dir / "01-settings.png")

    click_x = window.x + int(spec["click_offset"][0])
    click_y = window.y + int(spec["click_offset"][1])
    run_gui(["xdotool", "mousemove", str(click_x), str(click_y), "click", "1"], env=env, check=False)
    time.sleep(0.4)
    field_path = run_dir / "02-field-focused.png"
    screenshot(env, field_path)
    if dry_run:
        return {
            "status": "dry-run",
            "row": row_key,
            "requested_value": value,
            "screenshot": str(field_path),
            "run_dir": str(run_dir),
            "note": f"Captured {spec['label']} field location without typing.",
        }

    replace_focused_text(env, value)
    time.sleep(0.8)
    pasted_path = run_dir / "03-pasted-value.png"
    screenshot(env, pasted_path)
    verified_text = row_crop_text(env, window, pasted_path, run_dir / "03-pasted-row.png", spec)
    if value.lower() not in verified_text.lower() and not skip_ocr_guard:
        return {
            "status": "blocked-unverified-row",
            "row": row_key,
            "requested_value": value,
            "screenshot": str(pasted_path),
            "row_screenshot": str(run_dir / "03-pasted-row.png"),
            "run_dir": str(run_dir),
            "ocr_text": verified_text,
            "note": "Target text was not verified inside the settings row; no confirmation was sent.",
        }

    run_gui(["xdotool", "key", "Return"], env=env, check=False)
    time.sleep(1.0)
    confirm_path = run_dir / "04-confirm-dialog.png"
    screenshot(env, confirm_path)
    if not confirmation_dialog_visible(env, confirm_path) and not skip_ocr_guard:
        return {
            "status": "blocked-no-confirm-dialog",
            "row": row_key,
            "requested_value": value,
            "screenshot": str(confirm_path),
            "run_dir": str(run_dir),
            "note": "WeChat confirmation dialog was not detected; no Modify click was sent.",
        }
    click_modify_confirmation(env, window)
    time.sleep(1.4)
    after_path = run_dir / "05-after-confirm.png"
    screenshot(env, after_path)

    return {
        "status": "submitted",
        "row": row_key,
        "requested_value": value,
        "screenshot": str(after_path),
        "run_dir": str(run_dir),
        "note": str(spec["note"]),
    }


def replace_focused_text(env: dict[str, str], value: str) -> None:
    # In Linux WeChat settings rows, Ctrl+A is inconsistent. End followed by a
    # generous Backspace run clears the value while staying inside the focused
    # row; Delete clears any remaining suffix after the paste.
    run_gui(["xdotool", "key", "End"], env=env, check=False)
    run_gui(["xdotool", "key", "--repeat", "40", "--delay", "12", "BackSpace"], env=env, check=False)
    paste_text(env, value)
    run_gui(["xdotool", "key", "--repeat", "8", "--delay", "12", "Delete"], env=env, check=False)


def ensure_settings_drawer_open(env: dict[str, str], window, run_dir: Path) -> None:
    before = run_dir / "00-before-settings.png"
    screenshot(env, before)
    if settings_drawer_visible(before):
        return
    run_gui(["xdotool", "mousemove", str(window.x + window.width - 32), str(window.y + 51), "click", "1"], env=env)
    time.sleep(0.8)
    after = run_dir / "00-after-open-settings.png"
    screenshot(env, after)
    if not settings_drawer_visible(after):
        raise SystemExit(f"Settings drawer was not detected after clicking menu. Screenshot: {after}")


def settings_drawer_visible(path: Path) -> bool:
    text = ocr_image(path)
    markers = ("My Alias", "Group Name", "Search Chat History", "Mute Notifications")
    return any(marker.lower() in text.lower() for marker in markers)


def open_settings_drawer(env: dict[str, str], window) -> None:
    # Open right-side group settings drawer if it is closed. If the drawer is
    # already open, this click still keeps focus inside the main WeChat window;
    # callers verify with screenshots before typing.
    run_gui(["xdotool", "mousemove", str(window.x + window.width - 32), str(window.y + 51), "click", "1"], env=env)
    time.sleep(0.8)


def row_crop_text(env: dict[str, str], window, source: Path, crop_path: Path, spec: dict[str, object]) -> str:
    x_off, y_off, width, height = spec["crop_offset"]
    crop_geometry = f"{width}x{height}+{window.x + int(x_off)}+{window.y + int(y_off)}"
    if shutil.which("convert"):
        run_gui(["convert", str(source), "-crop", crop_geometry, str(crop_path)], env=env, check=False)
        return ocr_image(crop_path)
    return ocr_image(source)


def confirmation_dialog_visible(env: dict[str, str], path: Path) -> bool:
    text = ocr_image(path)
    return "modify" in text.lower() or "edit my alias" in text.lower() or "edit group name" in text.lower()


def ocr_image(path: Path) -> str:
    if not shutil.which("tesseract"):
        return ""
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "eng", "--psm", "6"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "") + "\n" + (proc.stderr or "")


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
