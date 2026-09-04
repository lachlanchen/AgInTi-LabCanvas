#!/usr/bin/env python3
"""Run the exact-chat WeCom GUI relay against the authenticated Tiny11 client."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

from wecom_contract import LABAGENT_GUIDE_VERSION, labagent_welcome_message
from wecom_gui_bridge import (
    DEFAULT_CONFIG,
    Window,
    WeComGuiBridge,
    filename_matches_ocr,
    initialize_config,
    load_config,
)
from wecom_tiny11_transport import Tiny11Transport, Tiny11TransportError


class Tiny11WeComGuiBridge(WeComGuiBridge):
    def __init__(self, config: dict[str, Any], *, config_path: Path = DEFAULT_CONFIG) -> None:
        super().__init__(config, config_path=config_path)
        self.tiny11 = Tiny11Transport(config)
        self.remote_staged_files: dict[str, str] = {}

    def status(self) -> dict[str, Any]:
        payload = super().status()
        helper = self.tiny11.health()
        payload.update(
            {
                "transport": "wecom_tiny11_gui",
                "tiny11_helper": {
                    "ok": bool(helper.get("ok")),
                    "session_id": helper.get("session_id"),
                    "wecom_running": bool(helper.get("wecom_running")),
                },
            }
        )
        payload["capabilities"]["artifact_transport"] = "verified_sftp"
        if payload.get("chat_ready"):
            payload["last_error"] = ""
        return payload

    def health(self) -> dict[str, Any]:
        status = self.status()
        return {
            "ok": bool(status.get("ok")) and bool(status.get("tiny11_helper", {}).get("ok")),
            "api_version": status.get("api_version"),
            "client_visible": status.get("client_visible"),
            "chat_ready": status.get("chat_ready"),
            "closed_loop_state": status.get("closed_loop_state"),
            "transport": status.get("transport"),
            "capabilities": status.get("capabilities"),
            "tiny11_helper": status.get("tiny11_helper"),
        }

    def find_window(self, *, required: bool = True) -> Window | None:
        helper = self.tiny11.health()
        raw = helper.get("window") if isinstance(helper, dict) else None
        if isinstance(raw, dict):
            try:
                window = Window(
                    wid=f"tiny11:{int(raw.get('process_id') or 0)}",
                    x=int(raw["x"]),
                    y=int(raw["y"]),
                    width=int(raw["width"]),
                    height=int(raw["height"]),
                )
            except (KeyError, TypeError, ValueError):
                window = None
            if window is not None and window.width >= 700 and window.height >= 500:
                return window
        if required:
            raise RuntimeError("no logged-in WeCom window is visible in Tiny11")
        return None

    @staticmethod
    def content_left(window: Window) -> int:
        """Return the native WeCom conversation pane's left edge.

        The Windows client keeps its navigation rail and conversation list at
        a fixed logical width when the main window is resized. The Wine relay
        uses a percentage because its synchronized layers scale differently;
        applying that percentage to a fullscreen native window skips the chat
        title and makes the exact-chat guard fail.
        """
        return window.x + min(306, max(250, window.width - 560))

    def current_title_matches(self, window: Window, chat: str) -> bool:
        screenshot = self.capture_screen("title-check")
        left = self.content_left(window) + 8
        width = max(180, min(480, window.x + window.width - left - 12))
        title_crop = self.crop(
            screenshot,
            (
                left,
                window.y + 8,
                width,
                max(46, min(70, int(window.height * 0.09))),
            ),
            self.runtime_dir / "title-check.png",
        )
        return self.find_ocr_line(title_crop, chat, scale=3) is not None

    def conversation_list_box(self, window: Window) -> tuple[int, int, int, int]:
        left = window.x + 62
        right = self.content_left(window)
        return (
            left,
            window.y + 50,
            max(180, right - left),
            max(300, window.height - 58),
        )

    def conversation_surface(self, window: Window) -> tuple[int, int, int, int]:
        left = self.content_left(window) + 10
        # The member pane is a fixed-width native panel in group chats. Keeping
        # it outside OCR avoids confusing member names with messages or files.
        right = max(left + 300, window.x + window.width - 170)
        return left, window.y + 78, right - left, max(300, window.height - 88)

    def extract_inbound_records(
        self,
        screenshot: Path,
        window: Window,
        chat: str,
    ) -> tuple[list[dict[str, str]], Path]:
        surface_left, surface_top, surface_width, surface_height = self.conversation_surface(window)
        top = surface_top + 8
        height = max(180, int(surface_height * 0.70))
        crop_path = self.runtime_dir / f"messages-{safe_label(chat)}.png"
        crop = self.crop(
            screenshot,
            (surface_left, top, surface_width, height),
            crop_path,
        )
        return self.extract_bubble_records(
            crop,
            chat,
            screen_origin=(surface_left, top),
        ), crop_path

    def composer_contains_filename(
        self,
        screenshot: Path,
        window: Window,
        filename: str,
        delivery_key: str,
    ) -> bool:
        left, _top, width, height = self.conversation_surface(window)
        crop = self.crop(
            screenshot,
            (
                left,
                window.y + int(window.height * 0.72),
                width,
                max(100, int(window.height * 0.26)),
            ),
            self.runtime_dir / f"file-composer-{delivery_key}.png",
        )
        return filename_matches_ocr(filename, self.ocr_scaled(crop, scale=3, psm=11))

    def read_chat_history_text(self, screenshot: Path, window: Window, label: str) -> str:
        left, top, width, height = self.conversation_surface(window)
        crop = self.crop(
            screenshot,
            (left, top, width, max(180, int(height * 0.72))),
            self.runtime_dir / f"file-history-{safe_label(label)}.png",
        )
        return self.ocr_scaled(crop, scale=3, psm=11)

    def capture_screen(self, label: str) -> Path:
        path = self.runtime_dir / f"{safe_label(label)}.png"
        path.write_bytes(self.tiny11.screenshot())
        path.chmod(0o600)
        return path

    def click(self, x: int, y: int) -> None:
        self.tiny11.invoke({"action": "click", "x": int(x), "y": int(y)})

    def right_click(self, x: int, y: int) -> None:
        self.tiny11.invoke({"action": "right_click", "x": int(x), "y": int(y)})

    def key(self, keys: str) -> None:
        self.tiny11.invoke({"action": "key", "keys": normalize_key(keys)})

    def set_clipboard(self, text: str) -> None:
        self.tiny11.invoke({"action": "set_clipboard", "text": text})

    def get_clipboard(self) -> str:
        value = self.tiny11.invoke({"action": "get_clipboard"})
        return str(value or "")

    def set_file_clipboard(self, paths: list[Path]) -> list[str]:
        remote_paths: list[str] = []
        for path in paths:
            remote = self.remote_staged_files.get(str(path.resolve()))
            if not remote:
                raise RuntimeError("Tiny11 file was not staged through verified SFTP")
            remote_paths.append(remote)
        observed = self.tiny11.invoke({"action": "set_file_clipboard", "paths": remote_paths})
        # PowerShell's JSON pipeline unwraps a single output item even when the
        # source object is a StringCollection. Normalize that valid one-file
        # response without accidentally iterating it character by character.
        if isinstance(observed, str):
            normalized = [observed]
        else:
            normalized = [str(item) for item in (observed or [])]
        if [item.casefold() for item in normalized] != [item.casefold() for item in remote_paths]:
            raise RuntimeError("WECOM_GUI_FILE_CLIPBOARD_UNVERIFIED: Tiny11 clipboard did not round-trip")
        return normalized

    def scroll_chat_to_bottom(self, window: Window) -> None:
        x = window.x + int(window.width * 0.62)
        y = window.y + int(window.height * 0.52)
        actions: list[dict[str, Any]] = [{"action": "click", "x": x, "y": y}]
        actions.extend({"action": "wheel", "x": x, "y": y, "delta": -720} for _ in range(4))
        self.tiny11.invoke({"action": "macro", "actions": actions})
        time.sleep(0.2)

    def composer_keys(self, window: Window, *keys: str) -> None:
        left, _top, width, _height = self.conversation_surface(window)
        x = left + max(80, min(180, int(width * 0.20)))
        y = window.y + window.height - 88
        actions: list[dict[str, Any]] = [{"action": "click", "x": x, "y": y}]
        actions.extend({"action": "key", "keys": normalize_key(value)} for value in keys)
        self.tiny11.invoke({"action": "macro", "actions": actions})

    def dismiss_transient_overlays(self, window: Window) -> None:
        self.click(window.x + int(window.width * 0.58), window.y + int(window.height * 0.08))
        time.sleep(0.05)

    def close_stale_native_overlays(self) -> None:
        return

    def run_win32_click(self, x: int, y: int) -> None:
        self.click(x, y)

    def run_xdotool(
        self,
        args: list[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            actions = xdotool_actions(args)
            if actions:
                self.tiny11.invoke({"action": "macro", "actions": actions})
            return subprocess.CompletedProcess(args, 0, "", "")
        except (RuntimeError, Tiny11TransportError) as exc:
            if check:
                raise RuntimeError(f"Tiny11 input command failed: {exc}") from exc
            return subprocess.CompletedProcess(args, 1, "", str(exc))

    def find_named_window(self, title: str) -> Window | None:
        return None

    def close_window(self, wid: str) -> None:
        return

    def stage_send_file(self, source: Path, delivery_key: str) -> tuple[Path, Path]:
        staging_dir = self.event_root / "tiny11-send" / delivery_key
        shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        staged = staging_dir / source.name
        try:
            staged.hardlink_to(source)
        except OSError:
            shutil.copy2(source, staged)
        remote = self.tiny11.stage_file(staged, delivery_key)
        self.remote_staged_files[str(staged.resolve())] = remote
        return staged, staging_dir

    def cleanup_staged_file(
        self,
        *,
        staged_file: Path | None,
        staging_dir: Path,
    ) -> None:
        if staged_file is not None:
            remote = self.remote_staged_files.pop(str(staged_file.resolve()), "")
            if remote:
                try:
                    self.tiny11.remove_staged_file(remote)
                except Tiny11TransportError:
                    pass
        super().cleanup_staged_file(staged_file=staged_file, staging_dir=staging_dir)

    def compose_staged_file_with_picker(
        self,
        wecom: Window,
        staged_file: Path,
        staging_dir: Path,
        delivery_key: str,
    ) -> Path:
        staged_files = [path for path in staging_dir.iterdir() if path.is_file()]
        if len(staged_files) != 1 or staged_files[0].resolve() != staged_file.resolve():
            raise RuntimeError("isolated Tiny11 staging folder must contain exactly one file")
        self.set_file_clipboard([staged_file])
        self.composer_keys(wecom, "ctrl+v")
        time.sleep(max(0.5, self.pause))
        return self.capture_screen(f"file-picker-{delivery_key}")


def normalize_key(value: str) -> str:
    normalized = value.strip().casefold()
    aliases = {"ctrl+alt+s": "alt+s", "backspace": "backspace", "return": "return"}
    return aliases.get(normalized, normalized)


def safe_label(value: str) -> str:
    result = "".join(character if character.isalnum() or character in "-_." else "_" for character in value)
    return result.strip("._")[:100] or "screen"


def xdotool_actions(args: list[str]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    index = 0
    mouse_x: int | None = None
    mouse_y: int | None = None
    while index < len(args):
        token = args[index]
        if token == "mousemove" and index + 2 < len(args):
            mouse_x = int(args[index + 1])
            mouse_y = int(args[index + 2])
            index += 3
            continue
        if token == "click" and index + 1 < len(args):
            button = args[index + 1]
            if button == "1":
                if mouse_x is None or mouse_y is None:
                    raise RuntimeError("click requires a preceding mousemove")
                actions.append({"action": "click", "x": mouse_x, "y": mouse_y})
            elif button == "3":
                if mouse_x is None or mouse_y is None:
                    raise RuntimeError("right click requires a preceding mousemove")
                actions.append({"action": "right_click", "x": mouse_x, "y": mouse_y})
            elif button in {"4", "5"}:
                actions.append(
                    {
                        "action": "wheel",
                        "x": mouse_x,
                        "y": mouse_y,
                        "delta": 120 if button == "4" else -120,
                    }
                )
            else:
                raise RuntimeError(f"unsupported Tiny11 mouse button: {button}")
            index += 2
            continue
        if token == "key":
            index += 1
            if index < len(args) and args[index] == "--clearmodifiers":
                index += 1
            while index < len(args) and args[index] not in {"mousemove", "click", "key"}:
                actions.append({"action": "key", "keys": normalize_key(args[index])})
                index += 1
            continue
        raise RuntimeError(f"unsupported Tiny11 xdotool token: {token}")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)
    initialize = subparsers.add_parser("init")
    initialize.add_argument("--chat", action="append", dest="chats", default=[])
    initialize.add_argument("--force", action="store_true")
    search = initialize.add_mutually_exclusive_group()
    search.add_argument("--allow-search-fallback", action="store_true", default=None)
    search.add_argument("--no-search-fallback", action="store_false", dest="allow_search_fallback")
    initialize.add_argument("--json", action="store_true")
    for name in ("status", "once", "loop", "chats"):
        command = subparsers.add_parser(name)
        command.add_argument("--json", action="store_true")
    send = subparsers.add_parser("send")
    send.add_argument("--chat", required=True)
    send.add_argument("--message", default="")
    send.add_argument("--file", action="append", dest="files", type=Path, default=[])
    send.add_argument("--task-id", default="manual")
    send.add_argument("--live", action="store_true")
    send.add_argument("--force-resend", action="store_true")
    send.add_argument("--json", action="store_true")
    messages = subparsers.add_parser("messages")
    messages.add_argument("--chat", required=True)
    messages.add_argument("--after", type=int, default=0)
    messages.add_argument("--limit", type=int, default=100)
    messages.add_argument("--json", action="store_true")
    guide = subparsers.add_parser("guide")
    guide.add_argument("--chat", required=True)
    guide.add_argument("--live", action="store_true")
    guide.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "init":
        payload = initialize_config(
            args.config,
            args.chats,
            force=args.force,
            allow_search_fallback=args.allow_search_fallback,
        )
    else:
        bridge = Tiny11WeComGuiBridge(load_config(args.config), config_path=args.config)
        if args.command == "status":
            payload = bridge.status()
        elif args.command == "once":
            payload = bridge.poll_once()
        elif args.command == "chats":
            payload = bridge.list_chats()
        elif args.command == "messages":
            payload = bridge.read_messages(args.chat, after=args.after, limit=args.limit)
        elif args.command == "guide":
            payload = (
                bridge.send_text(
                    args.chat,
                    labagent_welcome_message(),
                    task_id=f"labagent-guide:{LABAGENT_GUIDE_VERSION}:{args.chat}",
                )
                if args.live
                else {"ok": True, "dry_run": True, "chat": args.chat}
            )
        elif args.command == "send":
            if not args.live:
                payload = {
                    "ok": True,
                    "dry_run": True,
                    "chat": args.chat,
                    "message_bytes": len(args.message.encode("utf-8")),
                    "files": [str(path.expanduser().resolve()) for path in args.files],
                }
            else:
                payload = bridge.send(args.chat, args.message, args.files, task_id=args.task_id)
        else:
            bridge.serve_forever()
            return 0
    import json

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
