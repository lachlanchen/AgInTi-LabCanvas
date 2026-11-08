#!/usr/bin/env python3
"""Run the exact-chat WeCom GUI relay against the authenticated Tiny11 client."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
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
    now_iso,
    set_runtime,
    find_color_regions,
)
from wecom_tiny11_transport import Tiny11Transport, Tiny11TransportError, ps_quote
from PIL import Image, ImageChops


def native_input_problem(helper: dict[str, Any]) -> tuple[str, str] | None:
    blocker = str(helper.get("input_blocker") or "")
    if blocker:
        if blocker == "app_modal_dialog":
            return "app_modal_blocked", "LABCANVAS_GUI_APP_MODAL_BLOCKED: " + blocker
        return "system_dialog_blocked", "LABCANVAS_GUI_SYSTEM_DIALOG_BLOCKED: " + blocker
    state = str(helper.get("client_state") or "")
    app = "WECHAT" if helper.get("app") == "wechat" else "WECOM"
    if state == "unresponsive":
        return "client_unresponsive", app + "_CLIENT_UNRESPONSIVE: native message loop is not responding"
    if state == "entry_required":
        return "login_required", app + "_ENTRY_REQUIRED: native client is at its login screen"
    if not helper.get("ok") or state in {"window_hidden", "window_unavailable", "client_unavailable"}:
        return "client_unavailable", app + "_WINDOW_UNAVAILABLE: native chat window is unavailable"
    if helper.get("input_ready") is False:
        return "client_input_unavailable", "LABCANVAS_GUI_INPUT_NOT_READY: native input is unavailable"
    return None


class Tiny11WeComGuiBridge(WeComGuiBridge):
    def __init__(self, config: dict[str, Any], *, config_path: Path = DEFAULT_CONFIG) -> None:
        super().__init__(config, config_path=config_path)
        self.tiny11 = Tiny11Transport(config)
        self.remote_staged_files: dict[str, str] = {}
        self._context_menu_cleanup_pending = False

    def status(self) -> dict[str, Any]:
        payload = super().status()
        helper = self.tiny11.health()
        payload.update(
            {
                "transport": "wecom_tiny11_gui",
                "tiny11_helper": {
                    "ok": bool(helper.get("ok")),
                    "client_state": str(helper.get("client_state") or "unknown"),
                    "input_ready": bool(helper.get("input_ready")),
                    "session_id": helper.get("session_id"),
                    "wecom_running": bool(helper.get("wecom_running")),
                    "input_blocker": str(helper.get("input_blocker") or ""),
                },
            }
        )
        payload["capabilities"]["artifact_transport"] = "verified_sftp"
        if payload.get("chat_ready"):
            payload["last_error"] = ""
        problem = native_input_problem(helper)
        if problem and payload.get("enabled", True):
            payload.update(chat_ready=False, closed_loop_state=problem[0], last_error=problem[1])
        return payload

    def health(self) -> dict[str, Any]:
        status = self.status()
        return {
            "ok": (bool(status.get("ok")) and bool(status.get("tiny11_helper", {}).get("ok"))
                   and bool(status.get("tiny11_helper", {}).get("input_ready"))
                   and native_input_problem(status.get("tiny11_helper", {})) is None),
            "api_version": status.get("api_version"),
            "client_visible": status.get("client_visible"),
            "chat_ready": status.get("chat_ready"),
            "closed_loop_state": status.get("closed_loop_state"),
            "transport": status.get("transport"),
            "capabilities": status.get("capabilities"),
            "tiny11_helper": status.get("tiny11_helper"),
        }

    def poll_cycle(self) -> dict[str, Any]:
        if not getattr(self, "config", {}).get("enabled", True):
            return super().poll_cycle()
        helper = self.tiny11.health()
        problem = native_input_problem(helper)
        if problem:
            set_runtime(self.state_db, "last_poll_at", now_iso())
            return {"ok": True, "processed": 0, "skipped": problem[0], "reason": problem[1],
                    "input_ready": False}
        return super().poll_cycle()

    def require_native_input_ready(self) -> None:
        problem = native_input_problem(self.tiny11.health())
        if problem:
            raise RuntimeError(problem[1])

    def find_window(self, *, required: bool = True) -> Window | None:
        helper = self.tiny11.health()
        problem = native_input_problem(helper) if required else None
        if problem:
            raise RuntimeError(problem[1])
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

    def history_surface(self, window: Window) -> tuple[int, int, int, int]:
        left, top, width, _height = self.conversation_surface(window)
        # Native WeCom at the dedicated console's 100% DPI has a fixed-height
        # composer/footer. A percentage crop loses the newest rows in tall windows.
        bottom = window.y + window.height - 160
        return left, top, width, max(180, bottom - top)

    def passive_screen_signature(self, screenshot: Path, window: Window) -> str:
        # The native editor is fixed-height. A Wine percentage crop omits the
        # newest history rows in a tall console and delays them until rescan.
        left, top, width, height = self.history_surface(window)
        with Image.open(screenshot).convert("L") as image:
            observed = image.crop((window.x + 62, window.y + 54,
                                   left + width, top + height))
            observed = observed.resize((128, 96), Image.Resampling.BILINEAR)
            quantized = bytes((value // 16) * 16 for value in observed.tobytes())
        return hashlib.sha256(quantized).hexdigest()

    def extract_inbound_records(
        self,
        screenshot: Path,
        window: Window,
        chat: str,
    ) -> tuple[list[dict[str, str]], Path]:
        surface_left, surface_top, surface_width, surface_height = self.history_surface(window)
        top = surface_top + 8
        height = max(180, surface_height - 8)
        crop_path = self.runtime_dir / f"messages-{safe_label(chat)}.png"
        crop = self.crop(
            screenshot,
            (surface_left, top, surface_width, height),
            crop_path,
        )
        records = self.extract_bubble_records(
            crop,
            chat,
            screen_origin=(surface_left, top),
        )
        with Image.open(crop).convert("RGB") as image:
            regions = find_color_regions(image, (255, 255, 255), tolerance=5)
            regions += find_color_regions(image, (200, 222, 251), tolerance=5)
            size = image.size
        for index, (left, y, right, bottom, area) in enumerate(regions):
            if left > 80 or right - left < 130 or bottom - y < 42 or area < 3000:
                continue
            card_path = self.crop(crop, (left, y, right-left, bottom-y),
                                  self.runtime_dir / f"file-card-{safe_label(chat)}-{index}.png")
            label = self.ocr_scaled(card_path, scale=4, psm=6)
            if not re.search(r"\.(?:pdf|docx|txt|md|csv|xlsx|pptx|zip|rar|7z)\b", label, re.I):
                continue
            sender, fingerprint = self.extract_sender_identity(
                crop, left=left, top=y, image_width=size[0], image_height=size[1],
                label=f"file-{safe_label(chat)}-{index}")
            records.append({
                "text": "[WeCom file] " + " ".join(label.split()),
                "sender_label": sender, "sender_fingerprint": fingerprint,
                "sender_confidence": "visual_fingerprint" if fingerprint else "unresolved",
                "_screen_y": top + y,
                "native_file_card": {"x": surface_left+(left+right)//2,
                                     "y": top+(y+bottom)//2, "label": label},
            })
        return sorted(records, key=lambda item: int(item.get("_screen_y") or 0)), crop_path

    def click_native_menu_item(self, names: tuple[str, ...]) -> None:
        path = self.capture_screen("received-file-menu")
        for name in names:
            match = self.find_ocr_line(path, name, scale=2, full_line_only=True)
            if match is not None:
                self.click(int(match["center_x"]), int(match["center_y"]))
                return
        raise RuntimeError("Exact received-file menu item is unavailable")

    def received_file_info(self, remote: str) -> dict:
        output = self.tiny11.powershell(
            f"if(Test-Path -LiteralPath {ps_quote(remote)}) {{ "
            f"$f=Get-Item -LiteralPath {ps_quote(remote)}; "
            "@{bytes=$f.Length;sha256=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower()} | ConvertTo-Json -Compress }; exit 0")
        return json.loads(output) if output else {}

    def materialize_inbound_attachments(self, chat: str, records: list[dict]) -> list[dict]:
        attachments = []
        for record in records:
            card = record.get("native_file_card")
            if not isinstance(card, dict):
                continue
            identity = hashlib.sha256(json.dumps([chat, record.get("sender_fingerprint"),
                card["label"]], ensure_ascii=False).encode()).hexdigest()[:24]
            folder = self.event_root / "source-media" / safe_label(chat) / identity
            receipt_path = folder / "native-file-export.json"
            if receipt_path.is_file():
                receipt = json.loads(receipt_path.read_text())
                target = folder / str(receipt.get("filename") or "")
                if (target.is_file() and target.parent == folder
                        and receipt.get("source_chat") == chat
                        and filename_matches_ocr(target.name, str(card["label"]))
                        and hashlib.sha256(target.read_bytes()).hexdigest() == receipt.get("sha256")):
                    attachments.append(receipt)
                    continue
            self.right_click(int(card["x"]), int(card["y"]))
            try:
                # Copy can lazily render CF_HDROP on the helper's STA thread,
                # opening a modal Save As during clipboard reads. Open the
                # card's native Save As directly and read its filename instead.
                self.click_native_menu_item(("Save as...", "Save As", "另存为", "另存為"))
                time.sleep(0.5)
                native = self.tiny11.invoke({"action": "received_file_name"})
                filename = str(native.get("filename") or "")
                if native.get("extension_hidden"):
                    extensions = set(re.findall(
                        r"\.(pdf|docx|txt|md|csv|xlsx|pptx|zip|rar|7z)\b", str(card["label"]), re.I))
                    if len(extensions) != 1:
                        raise RuntimeError("Received file card does not expose a unique extension")
                    filename += "." + extensions.pop().lower()
                if (Path(filename).name != filename or "\\" in filename
                        or not filename_matches_ocr(filename, str(card["label"]))):
                    raise RuntimeError("Received file-card identity changed")
                folder.mkdir(mode=0o700, parents=True, exist_ok=True)
                target = folder / filename
                remote = self.tiny11.remote_root + "\\intake\\" + identity + "\\" + filename
                info = self.received_file_info(remote)
                if info:
                    # A crash after native saving but before SFTP must not
                    # overwrite the original or reopen a replacement prompt.
                    self.tiny11.invoke({"action": "cancel_received_file"})
                else:
                    self.tiny11.invoke({"action": "save_received_file", "filename": filename, "path": remote})
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if int(info.get("bytes") or 0) > 0:
                        break
                    time.sleep(1)
                    info = self.received_file_info(remote)
                if not 0 < int(info.get("bytes") or 0) <= 256 * 1024 * 1024:
                    raise RuntimeError("Received file did not finish its bounded native export")
                subprocess.run(["scp", "-q", "-P", str(self.tiny11.ssh_port), "-o", "BatchMode=yes",
                    "-o", "ConnectTimeout=8", f"{self.tiny11.user}@{self.tiny11.host}:{remote.replace(chr(92), '/')}",
                    str(target)], check=True, capture_output=True, timeout=90)
                target.chmod(0o600)
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                if target.stat().st_size != int(info["bytes"]) or digest != info["sha256"]:
                    raise RuntimeError("Received-file SFTP checksum mismatch")
                receipt = {"kind": "file", "filename": filename, "path": str(target.resolve()),
                    "task_copy_path": str(target.resolve()), "size_bytes": target.stat().st_size,
                    "sha256": digest, "source_chat": chat,
                    "capture_kind": "wecom_native_exact_card_save_as", "status": "ready"}
                receipt_path.touch(mode=0o600, exist_ok=True)
                receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
                attachments.append(receipt)
            except Exception:
                try:
                    self.tiny11.invoke({"action": "cancel_received_file"})
                except (RuntimeError, Tiny11TransportError):
                    pass
                raise
            finally:
                # A failed export may leave a modal dialog. Do not mask the
                # original failure by trying to click through the input guard.
                if native_input_problem(self.tiny11.health()) is None:
                    self.dismiss_transient_overlays(self.find_window(required=False))
        return attachments

    def composer_contains_filename(
        self,
        screenshot: Path,
        window: Window,
        filename: str,
        delivery_key: str,
    ) -> bool:
        left, _top, width, _height = self.conversation_surface(window)
        crop = self.crop(
            screenshot,
            (
                left,
                window.y + window.height - 124,
                width,
                90,
            ),
            self.runtime_dir / f"file-composer-{delivery_key}.png",
        )
        return filename_matches_ocr(filename, self.ocr_scaled(crop, scale=3, psm=11))

    def read_chat_history_text(self, screenshot: Path, window: Window, label: str) -> str:
        crop = self.crop(
            screenshot,
            self.history_surface(window),
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
        # A timed-out input may still have opened the menu in the guest.
        self._context_menu_cleanup_pending = True
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
        from pathlib import PureWindowsPath
        if [PureWindowsPath(item) for item in normalized] != [PureWindowsPath(item) for item in remote_paths]:
            raise RuntimeError("WECOM_GUI_FILE_CLIPBOARD_UNVERIFIED: Tiny11 clipboard did not round-trip")
        return normalized

    def scroll_chat_to_bottom(self, window: Window) -> None:
        x = window.x + int(window.width * 0.62)
        y = window.y + int(window.height * 0.52)
        # Wheel events already focus WeCom and position the pointer. Clicking
        # the history first can open a card/file instead of scrolling it.
        actions = [{"action": "wheel", "x": x, "y": y, "delta": -720} for _ in range(4)]
        self.tiny11.invoke({"action": "macro", "actions": actions})
        time.sleep(0.2)

    def composer_keys(self, window: Window, *keys: str) -> None:
        left, _top, width, _height = self.conversation_surface(window)
        x = left + max(80, min(180, int(width * 0.20)))
        y = window.y + window.height - 88
        actions: list[dict[str, Any]] = [{"action": "click", "x": x, "y": y}]
        actions.extend({"action": "key", "keys": normalize_key(value)} for value in keys)
        self.tiny11.invoke({"action": "macro", "actions": actions})

    def composer_is_empty(self, window: Window, delivery_key: str) -> bool:
        if super().composer_is_empty(window, delivery_key):
            return True
        # Native WeCom's global Copy can return a selected history bubble even
        # while the now-empty editor has focus. Independently check the editor,
        # excluding its toolbar, borders and Send footer. Allow only a caret.
        screenshot = self.capture_screen(f"empty-editor-{delivery_key}")
        left = self.content_left(window) + 22
        right = window.x + window.width - 190
        if right - left < 100:
            return False
        with Image.open(screenshot).convert("RGB") as image:
            editor = image.crop((left, window.y + window.height - 122,
                                 right, window.y + window.height - 50))
            ink = ImageChops.difference(editor, Image.new("RGB", editor.size, "white"))
            box = ink.point(lambda value: 255 if value > 12 else 0).getbbox()
        return box is None or (box[2] - box[0] <= 2 and box[3] - box[1] <= 24)

    def dismiss_transient_overlays(self, window: Window) -> None:
        if not getattr(self, "_context_menu_cleanup_pending", False):
            return
        # Native title bars have fixed height. A percentage can hit a message
        # when the window is tall; do not clean up menus we did not open.
        self.click(window.x + int(window.width * 0.58), window.y + 38)
        self._context_menu_cleanup_pending = False
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
                if any(action.get("action") == "right_click" for action in actions):
                    self._context_menu_cleanup_pending = True
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
