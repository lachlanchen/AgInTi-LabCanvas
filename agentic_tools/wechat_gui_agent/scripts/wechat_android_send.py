#!/usr/bin/env python3
"""Guarded personal-WeChat outbound transport over an authorized Android device."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
ANDROID_PRIVATE = ROOT / "agentic_tools" / "android_device_agent" / ".private"
ANDROID_SCRIPTS = ROOT / "agentic_tools" / "android_device_agent" / "scripts"
if str(ANDROID_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ANDROID_SCRIPTS))

from android_control_lease import priority_android_control


DEFAULT_TARGETS = PRIVATE / "wechat_send_targets.local.json"
DEFAULT_STATE_DB = PRIVATE / "wechat_android_send.sqlite"
DEFAULT_DEVICE_LOCK = (
    ROOT
    / "agentic_tools"
    / "wecom_agent"
    / ".private"
    / "wecom_android_bridge.lock"
)
DEFAULT_PRIORITY = ANDROID_PRIVATE / "android_control_priority.json"
DEFAULT_OUTPUT = ROOT / "output" / "wechat_android_send"
PACKAGE = "com.tencent.mm"
MAIN_ACTIVITY = "com.tencent.mm/.ui.LauncherUI"
SHARE_ACTIVITY = "com.tencent.mm/.ui.tools.ShareImgUI"
REMOTE_STAGING = "/sdcard/Download"
WEBWX_DEVICE_ACTIVITY_SUFFIX = ".plugin.webwx.ui.WebWXLogoutUI"


class AndroidWechatError(RuntimeError):
    """Raised when exact-target Android delivery cannot be proved."""


@dataclass(frozen=True)
class OcrLine:
    text: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_y(self) -> int:
        return int((self.top + self.bottom) / 2)

    @property
    def center_x(self) -> int:
        return int((self.left + self.right) / 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--message", action="append", default=[])
    parser.add_argument("--file", action="append", type=Path, default=[])
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT / datetime.now().strftime("%F"))
    parser.add_argument("--max-list-pages", type=int, default=5)
    args = parser.parse_args()
    if not args.send:
        raise SystemExit("--send is required; Android WeChat writes are always explicit")
    if not args.message and not args.file:
        raise SystemExit("At least one --message or --file is required")
    target = load_target(args.target, args.targets_file)
    serial = resolve_serial(args.adb, args.serial)
    sender = AndroidWechatSender(
        adb=args.adb,
        serial=serial,
        target=target,
        task_id=args.task_id,
        state_db=args.state_db.expanduser().resolve(),
        output_dir=args.output_dir.expanduser().resolve(),
        max_list_pages=max(1, min(10, args.max_list_pages)),
    )
    result = sender.send(messages=args.message, files=args.file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


class AndroidWechatSender:
    def __init__(
        self,
        *,
        adb: str,
        serial: str,
        target: dict[str, Any],
        task_id: str,
        state_db: Path,
        output_dir: Path,
        max_list_pages: int = 5,
    ) -> None:
        self.adb = adb
        self.serial = serial
        self.target = target
        self.task_id = str(task_id)
        self.state_db = state_db
        self.output_dir = output_dir
        self.max_list_pages = max_list_pages
        self.display = os.environ.get("WECHAT_ANDROID_DISPLAY", ":99")
        self.scrcpy_window = os.environ.get(
            "WECHAT_ANDROID_SCRCPY_WINDOW",
            "LabCanvas Android MIX 2S",
        )
        self.aliases = target_aliases(target)
        self.chat = str(target.get("name") or target.get("target") or "").strip()
        if not self.chat or not self.aliases:
            raise AndroidWechatError("target must have a name and expected title aliases")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.init_state()

    def init_state(self) -> None:
        self.state_db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(self.state_db) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS components ("
                "component_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, chat TEXT NOT NULL, "
                "kind TEXT NOT NULL, value_hash TEXT NOT NULL, status TEXT NOT NULL, "
                "details_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL)"
            )

    def send(self, *, messages: list[str], files: list[Path]) -> dict[str, Any]:
        require_tools(self.adb, "convert", "tesseract", "xclip", "xdotool")
        components = [
            *(self.file_component(path) for path in files),
            *(self.text_component(text) for text in messages if str(text).strip()),
        ]
        if not components:
            raise AndroidWechatError("all outbound components were empty")
        results: list[dict[str, Any]] = []
        purpose = f"personal_wechat_send:{self.task_id[:80]}"
        with priority_android_control(
            lock_path=DEFAULT_DEVICE_LOCK,
            priority_path=DEFAULT_PRIORITY,
            purpose=purpose,
            timeout_seconds=float(os.environ.get("WECHAT_ANDROID_LOCK_TIMEOUT", "120")),
            lease_seconds=float(os.environ.get("WECHAT_ANDROID_LEASE_SECONDS", "420")),
        ):
            self.wake_and_launch()
            self.ensure_exact_chat()
            for component in components:
                status = self.component_status(component["key"])
                if status == "sent":
                    results.append({"key": component["key"], "status": "already_sent"})
                    continue
                if status == "uncertain":
                    raise AndroidWechatError(
                        f"ANDROID_WECHAT_UNCERTAIN: component {component['key']} requires review"
                    )
                if component["kind"] == "file":
                    results.append(self.send_file_component(component))
                else:
                    results.append(self.send_text_component(component))
        return {
            "ok": True,
            "transport": "wechat_android",
            "task_id": self.task_id,
            "chat": self.chat,
            "components": results,
        }

    def text_component(self, text: str) -> dict[str, Any]:
        value = str(text).strip()
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return {
            "kind": "text",
            "value": value,
            "value_hash": digest,
            "key": component_key(self.task_id, self.chat, "text", digest),
        }

    def file_component(self, path: Path) -> dict[str, Any]:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise AndroidWechatError(f"outbound file does not exist: {resolved}")
        digest = sha256_file(resolved)
        return {
            "kind": "file",
            "path": resolved,
            "value_hash": digest,
            "key": component_key(self.task_id, self.chat, "file", digest),
        }

    def component_status(self, key: str) -> str:
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute(
                "SELECT status FROM components WHERE component_key = ?",
                (key,),
            ).fetchone()
        return str(row[0]) if row else ""

    def mark_component(
        self,
        component: dict[str, Any],
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        safe_details = dict(details or {})
        safe_details.pop("message", None)
        with sqlite3.connect(self.state_db) as conn:
            conn.execute(
                "INSERT INTO components(component_key,task_id,chat,kind,value_hash,status,details_json,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(component_key) DO UPDATE SET "
                "status=excluded.status,details_json=excluded.details_json,updated_at=excluded.updated_at",
                (
                    component["key"],
                    self.task_id,
                    self.chat,
                    component["kind"],
                    component["value_hash"],
                    status,
                    json.dumps(safe_details, ensure_ascii=False, separators=(",", ":")),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def adb_run(
        self,
        command: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        binary: bool = False,
    ) -> subprocess.CompletedProcess[Any]:
        proc = subprocess.run(
            [self.adb, "-s", self.serial, *command],
            capture_output=True,
            text=not binary,
            timeout=timeout,
            check=False,
        )
        if check and proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace") if binary else str(proc.stderr or "")
            stdout = proc.stdout.decode(errors="replace") if binary else str(proc.stdout or "")
            raise AndroidWechatError(
                f"adb failed ({proc.returncode}): {' '.join(command)}: {(stderr or stdout)[:400]}"
            )
        return proc

    def shell(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        return self.adb_run(["shell", *command], **kwargs)

    def wake_and_launch(self) -> None:
        self.shell(["input", "keyevent", "224"], check=False)
        self.shell(["wm", "dismiss-keyguard"], check=False)
        self.shell(["svc", "power", "stayon", "true"], check=False)
        self.collapse_system_overlays()
        self.launch_wechat_main()
        for attempt in range(4):
            time.sleep(1.0)
            self.collapse_system_overlays()
            package, activity = self.current_component()
            if package == PACKAGE and not activity.endswith(WEBWX_DEVICE_ACTIVITY_SUFFIX):
                return
            if package == PACKAGE and activity.endswith(WEBWX_DEVICE_ACTIVITY_SUFFIX):
                # WeChat may resume its standalone "logged-in devices" page.
                # Android Back exits the app from this activity; its visible X
                # closes the page, after which LauncherUI can be raised again.
                self.screenshot(f"aux-webwx-device-{attempt}")
                self.shell(["input", "tap", "55", "132"], check=False)
                time.sleep(0.7)
            self.launch_wechat_main()
        package, activity = self.current_component()
        raise AndroidWechatError(
            "personal WeChat did not reach its main surface "
            f"(foreground={package}/{activity})"
        )

    def collapse_system_overlays(self) -> None:
        """Keep notification/quick-settings overlays out of visual title guards."""
        self.shell(["cmd", "statusbar", "collapse"], check=False)
        time.sleep(0.2)

    def launch_wechat_main(self) -> None:
        self.shell(
            ["am", "start", "-W", "-f", "0x04000000", "-n", MAIN_ACTIVITY],
            timeout=25,
        )

    def current_component(self) -> tuple[str, str]:
        proc = self.shell(["dumpsys", "activity", "activities"], timeout=15, check=False)
        match = re.search(
            r"mResumedActivity:.*?\s([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)",
            str(proc.stdout or ""),
        )
        return (match.group(1), match.group(2)) if match else ("", "")

    def current_package(self) -> str:
        return self.current_component()[0]

    def screenshot(self, label: str) -> Path:
        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip("-") or "screen"
        path = self.output_dir / (
            f"{safe_slug(self.task_id)}-{safe_label}-{datetime.now().strftime('%H%M%S%f')}.png"
        )
        proc = self.adb_run(["exec-out", "screencap", "-p"], binary=True, timeout=20)
        path.write_bytes(proc.stdout)
        return path

    def header_text(self, screenshot: Path) -> str:
        crop = screenshot.with_name(f"{screenshot.stem}-header.png")
        run_checked(
            ["convert", str(screenshot), "-crop", "720x170+180+55", str(crop)],
            timeout=20,
        )
        return ocr_plain(crop, psm="6")

    def current_chat_matches(self, screenshot: Path | None = None) -> bool:
        shot = screenshot or self.screenshot("title-guard")
        if text_matches_alias(self.header_text(shot), self.aliases):
            return True
        return text_matches_alias(enhanced_header_text(shot), self.aliases)

    def ensure_exact_chat(self) -> Path:
        current = self.screenshot("current")
        if self.current_chat_matches(current):
            return current
        for _ in range(4):
            match = self.find_target_line(current)
            if match is not None and self.open_target_line(match):
                return self.screenshot("target-open")
            self.shell(["input", "keyevent", "4"], check=False)
            time.sleep(0.7)
            current = self.screenshot("back-to-chat-list")
        self.shell(["input", "swipe", "540", "500", "540", "1750", "450"], check=False)
        time.sleep(0.7)
        for page in range(self.max_list_pages):
            current = self.screenshot(f"chat-list-{page}")
            match = self.find_target_line(current)
            if match is not None and self.open_target_line(match):
                return self.screenshot("target-open")
            self.shell(["input", "swipe", "540", "1750", "540", "500", "450"], check=False)
            time.sleep(0.7)
        raise AndroidWechatError(
            f"ANDROID_WECHAT_TITLE_GUARD: exact target {self.chat!r} was not found"
        )

    def find_target_line(self, screenshot: Path) -> OcrLine | None:
        raw_lines = ocr_lines(screenshot)
        candidates = matching_target_lines(raw_lines, self.aliases)
        if not candidates:
            candidates = matching_target_lines(
                merge_chat_title_fragments(raw_lines), self.aliases
            )
        if not candidates:
            enhanced_lines = enhanced_ocr_lines(screenshot)
            candidates = matching_target_lines(enhanced_lines, self.aliases)
            if not candidates:
                candidates = matching_target_lines(
                    merge_chat_title_fragments(enhanced_lines), self.aliases
                )
        if not candidates:
            return None
        candidates.sort(
            key=lambda line: (
                -max(alias_match_length(line.text, alias) for alias in self.aliases),
                line.top,
            )
        )
        return candidates[0]

    def open_target_line(self, line: OcrLine) -> bool:
        self.shell(["input", "tap", "500", str(line.center_y)])
        time.sleep(1.0)
        shot = self.screenshot("opened-title-guard")
        if self.current_chat_matches(shot):
            return True
        self.shell(["input", "keyevent", "4"], check=False)
        time.sleep(0.5)
        return False

    def send_text_component(self, component: dict[str, Any]) -> dict[str, Any]:
        self.ensure_exact_chat()
        before = self.screenshot("text-before")
        width, height = image_size(before)
        self.shell(["input", "tap", str(int(width * 0.40)), str(int(height * 0.962))])
        time.sleep(0.5)
        self.paste_text(component["value"])
        time.sleep(0.7)
        typed = self.screenshot("text-typed")
        action_point = green_action_center(typed, min_y_ratio=0.45)
        action = find_action_line(ocr_lines(typed), ("发送", "傳送", "Send"))
        self.mark_component(component, "sending", {"typed_screenshot": str(typed)})
        committed = False
        try:
            if action_point is not None:
                self.shell(["input", "tap", str(action_point[0]), str(action_point[1])])
            elif action is not None and action.center_y > int(height * 0.45):
                self.shell(["input", "tap", str(action.right - 5), str(action.center_y)])
            else:
                self.shell(["input", "tap", str(int(width * 0.91)), str(int(height * 0.603))])
            committed = True
            time.sleep(1.3)
            after = self.screenshot("text-sent")
            if not self.current_chat_matches(after):
                raise AndroidWechatError("target title changed after Android text send")
            if image_difference_pixels(typed, after) < 200:
                raise AndroidWechatError("Android text send produced no visible UI change")
            details = {"before": str(before), "typed": str(typed), "after": str(after)}
            self.mark_component(component, "sent", details)
            return {"key": component["key"], "kind": "text", "status": "sent", **details}
        except Exception as exc:
            self.mark_component(
                component,
                "uncertain" if committed else "failed",
                {"error": f"{type(exc).__name__}: {str(exc)[:400]}"},
            )
            raise

    def paste_text(self, text: str) -> None:
        env = {**os.environ, "DISPLAY": self.display}
        search = run_checked(
            ["xdotool", "search", "--name", f"^{re.escape(self.scrcpy_window)}"],
            env=env,
            timeout=10,
        )
        windows = [line.strip() for line in search.stdout.splitlines() if line.strip()]
        if not windows:
            raise AndroidWechatError("scrcpy window unavailable for Unicode clipboard input")
        clipboard = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-loops", "1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        assert clipboard.stdin is not None
        clipboard.stdin.write(text.encode("utf-8"))
        clipboard.stdin.close()
        time.sleep(0.2)
        run_checked(
            [
                "xdotool",
                "windowfocus",
                "--sync",
                windows[-1],
                "key",
                "--clearmodifiers",
                "ctrl+v",
            ],
            env=env,
            timeout=10,
        )
        try:
            clipboard.wait(timeout=5)
        except subprocess.TimeoutExpired:
            clipboard.terminate()
            clipboard.wait(timeout=2)

    def send_file_component(self, component: dict[str, Any]) -> dict[str, Any]:
        path = component["path"]
        remote_name = readable_android_filename(path.name)
        remote_path = f"{REMOTE_STAGING}/{remote_name}"
        self.adb_run(["push", str(path), remote_path], timeout=180)
        self.shell(
            [
                "am",
                "broadcast",
                "-a",
                "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d",
                f"file://{remote_path}",
            ],
            timeout=30,
            check=False,
        )
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        uri = self.media_store_uri(remote_name)
        self.shell(
            [
                "am",
                "start",
                "-W",
                "-a",
                "android.intent.action.SEND",
                "-t",
                mime,
                "-n",
                SHARE_ACTIVITY,
                "-f",
                "0x00000001",
                "--eu",
                "android.intent.extra.STREAM",
                uri,
            ],
            timeout=45,
        )
        time.sleep(1.3)
        chooser = self.screenshot("file-share-targets")
        target_line = self.find_share_target_line(chooser)
        if target_line is None:
            target_line = self.search_share_target(chooser)
        if target_line is None:
            raise AndroidWechatError(f"exact share target {self.chat!r} was not found")
        self.tap_share_target(target_line)
        time.sleep(1.0)
        confirmation = self.screenshot("file-share-confirm")
        if not self.share_confirmation_matches_target(confirmation):
            self.shell(["input", "keyevent", "4"], check=False)
            raise AndroidWechatError("share confirmation did not name the exact target")
        action_point = green_action_center(confirmation, min_y_ratio=0.65)
        action = find_action_line(ocr_lines(confirmation), ("发送", "傳送", "Send"))
        if action_point is None and (
            action is None or action.center_y < int(image_size(confirmation)[1] * 0.65)
        ):
            self.shell(["input", "keyevent", "4"], check=False)
            raise AndroidWechatError("share confirmation action was not visible")
        self.mark_component(
            component,
            "sending",
            {"filename": path.name, "confirmation": str(confirmation)},
        )
        committed = False
        try:
            if action_point is not None:
                self.shell(["input", "tap", str(action_point[0]), str(action_point[1])])
            else:
                assert action is not None
                self.shell(["input", "tap", str(action.right - 5), str(action.center_y)])
            committed = True
            time.sleep(2.5)
            after = self.screenshot("file-shared")
            text = ocr_plain(after, psm="11")
            if any(marker in text for marker in ("发送失败", "傳送失敗", "分享失败", "Share failed")):
                raise AndroidWechatError("WeChat reported a native file-share failure")
            details = {
                "filename": path.name,
                "confirmation": str(confirmation),
                "after": str(after),
            }
            self.mark_component(component, "sent", details)
            return {"key": component["key"], "kind": "file", "status": "sent", **details}
        except Exception as exc:
            self.mark_component(
                component,
                "uncertain" if committed else "failed",
                {"filename": path.name, "error": f"{type(exc).__name__}: {str(exc)[:400]}"},
            )
            raise

    def share_confirmation_matches_target(self, screenshot: Path) -> bool:
        """Verify the selected recipient using full-screen and focused OCR."""
        lines = ocr_lines(screenshot)
        _, height = image_size(screenshot)
        cancel = find_action_line(lines, ("取消", "Cancel"))
        if cancel is None or cancel.center_y < int(height * 0.70):
            return False
        if any(
            line.center_y >= int(height * 0.48)
            and text_matches_alias(line.text, self.aliases)
            for line in lines
        ):
            return True
        width, _ = image_size(screenshot)
        crop = screenshot.with_name(f"{screenshot.stem}-target-title.png")
        run_checked(
            [
                "convert",
                str(screenshot),
                "-crop",
                (
                    f"{int(width * 0.84)}x{int(height * 0.13)}"
                    f"+{int(width * 0.14)}+{int(height * 0.56)}"
                ),
                "+repage",
                "-resize",
                "250%",
                str(crop),
            ],
            timeout=20,
        )
        if any(
            text_matches_alias(line.text, self.aliases)
            for line in ocr_lines(crop)
        ):
            return True
        return any(
            text_matches_alias(ocr_plain(crop, psm=psm), self.aliases)
            for psm in ("7", "6")
        )

    def find_share_target_line(
        self,
        screenshot: Path,
        *,
        search_results: bool = False,
    ) -> OcrLine | None:
        """Find a recipient row without mistaking the search input for a result."""

        lines = ocr_lines(screenshot)
        candidates = matching_target_lines(lines, self.aliases)
        if not candidates:
            candidates = matching_target_lines(
                merge_chat_title_fragments(lines), self.aliases
            )
        if not candidates:
            enhanced = enhanced_ocr_lines(screenshot)
            candidates = matching_target_lines(enhanced, self.aliases)
            if not candidates:
                candidates = matching_target_lines(
                    merge_chat_title_fragments(enhanced), self.aliases
                )
        _, height = image_size(screenshot)
        min_y = int(height * (0.18 if search_results else 0.12))
        max_y = int(height * 0.92)
        candidates = [
            line for line in candidates if min_y <= line.center_y <= max_y
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda line: (
                -max(alias_match_length(line.text, alias) for alias in self.aliases),
                line.top,
            )
        )
        requested_index = max(0, int(self.target.get("share_result_index") or 0))
        return candidates[min(requested_index, len(candidates) - 1)]

    def tap_share_target(self, line: OcrLine) -> None:
        """Tap the matched tile or row instead of a neighboring recent target."""

        self.shell(["input", "tap", str(line.center_x), str(line.center_y)])

    def search_share_target(self, screenshot: Path) -> OcrLine | None:
        lines = ocr_lines(screenshot)
        search = find_action_line(lines, ("搜索", "搜尋", "Search"))
        if search is not None:
            self.shell(["input", "tap", str(search.right - 5), str(search.center_y)])
            time.sleep(0.5)
            self.paste_text(str(self.target.get("query") or self.aliases[0]))
            time.sleep(0.8)
            return self.find_share_target_line(
                self.screenshot("file-share-search"),
                search_results=True,
            )
        for page in range(3):
            self.shell(["input", "swipe", "540", "1750", "540", "550", "400"], check=False)
            time.sleep(0.7)
            match = self.find_share_target_line(
                self.screenshot(f"file-share-scroll-{page}"),
                search_results=True,
            )
            if match is not None:
                return match
        return None

    def media_store_uri(self, remote_name: str) -> str:
        """Resolve the indexed file URI that WeChat can actually read."""
        where = f"_display_name=\\'{remote_name}\\'"
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            result = self.shell(
                [
                    "content",
                    "query",
                    "--uri",
                    "content://media/external/file",
                    "--projection",
                    "_id:_display_name",
                    "--where",
                    where,
                ],
                timeout=20,
                check=False,
            )
            match = re.search(r"_id=(\d+),\s+_display_name=([^\r\n]+)", str(result.stdout or ""))
            if match and match.group(2).strip() == remote_name:
                return f"content://media/external/file/{match.group(1)}"
            time.sleep(0.4)
        raise AndroidWechatError(f"staged file was not indexed by Android MediaStore: {remote_name}")


def load_target(name: str, path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unable to read target registry: {type(exc).__name__}") from exc
    raw = data.get(name) if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        raise SystemExit(f"Target {name!r} is not allowlisted in {path}")
    target = dict(raw)
    target.setdefault("name", name)
    return target


def target_aliases(target: dict[str, Any]) -> tuple[str, ...]:
    raw = [
        target.get("expected_title"),
        *(target.get("expected_title_aliases") or []),
        target.get("name"),
    ]
    aliases: list[str] = []
    for value in raw:
        item = " ".join(str(value or "").split())
        if item and item not in aliases:
            aliases.append(item)
    aliases.sort(key=lambda value: len(normalize_text(value)), reverse=True)
    return tuple(aliases)


def normalize_text(value: str) -> str:
    folded = str(value or "").casefold().translate(
        str.maketrans(
            {
                "鏈": "链",
                "錢": "钱",
                "寫": "写",
                "語": "语",
                "陳": "陈",
                "掙": "挣",
            }
        )
    )
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", folded)


def alias_match_length(text: str, alias: str) -> int:
    candidate = normalize_text(text)
    expected = normalize_text(alias)
    if not candidate or not expected:
        return 0
    if len(expected) <= 2:
        return len(expected) if candidate == expected else 0
    if expected in candidate:
        return len(expected)
    # Tesseract commonly reads a long dash between Chinese title segments as
    # the numeral 一. Only remove it when the authoritative alias itself does
    # not contain 一, preserving exact matching for genuine names that do.
    if "一" not in expected and expected in candidate.replace("一", ""):
        return len(expected)
    compact_candidate = candidate.replace("一", "") if "一" not in expected else candidate
    if (
        len(expected) >= 6
        and abs(len(compact_candidate) - len(expected)) == 1
        and one_deletion_apart(compact_candidate, expected)
    ):
        return len(expected) - 1
    return 0


def one_deletion_apart(first: str, second: str) -> bool:
    """Accept one missing/extra OCR glyph, never a substituted title glyph."""
    shorter, longer = sorted((first, second), key=len)
    if len(longer) - len(shorter) != 1:
        return False
    cursor = 0
    for character in longer:
        if cursor < len(shorter) and shorter[cursor] == character:
            cursor += 1
    return cursor == len(shorter)


def text_matches_alias(text: str, aliases: tuple[str, ...]) -> bool:
    return any(alias_match_length(text, alias) for alias in aliases)


def readable_android_filename(value: str) -> str:
    """Keep the recipient-visible filename meaningful and filesystem-safe."""
    name = Path(str(value or "")).name.strip()
    name = re.sub(r"[^\w.()\[\]-]+", "_", name, flags=re.UNICODE).strip("._")
    if not name:
        return "LabCanvas-artifact"
    suffix = Path(name).suffix
    stem = Path(name).stem
    max_chars = 120
    if len(name) > max_chars:
        stem = stem[: max(16, max_chars - len(suffix) - 1)].rstrip("._-")
        name = f"{stem}{suffix}"
    return name


def parse_ocr_tsv(value: str, *, coordinate_scale: float = 1.0) -> list[OcrLine]:
    if coordinate_scale <= 0:
        raise ValueError("coordinate_scale must be positive")
    groups: dict[tuple[int, int, int], list[tuple[str, int, int, int, int]]] = {}
    for index, raw in enumerate(str(value or "").splitlines()):
        if index == 0:
            continue
        columns = raw.split("\t")
        if len(columns) < 12 or not columns[11].strip():
            continue
        try:
            key = (int(columns[2]), int(columns[3]), int(columns[4]))
            left, top, width, height = map(int, columns[6:10])
        except ValueError:
            continue
        scaled = tuple(
            int(round(item / coordinate_scale))
            for item in (left, top, left + width, top + height)
        )
        groups.setdefault(key, []).append((columns[11].strip(), *scaled))
    result = []
    for words in groups.values():
        words.sort(key=lambda word: word[1])
        result.append(
            OcrLine(
                text=" ".join(word[0] for word in words),
                left=min(word[1] for word in words),
                top=min(word[2] for word in words),
                right=max(word[3] for word in words),
                bottom=max(word[4] for word in words),
            )
        )
    return sorted(result, key=lambda line: (line.top, line.left))


def ocr_lines(path: Path, *, coordinate_scale: float = 1.0) -> list[OcrLine]:
    proc = run_checked(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            os.environ.get("WECHAT_ANDROID_OCR_LANGS", "chi_sim+chi_tra+eng"),
            "--psm",
            "11",
            "tsv",
        ],
        timeout=45,
    )
    return parse_ocr_tsv(proc.stdout, coordinate_scale=coordinate_scale)


def enhanced_ocr_lines(path: Path) -> list[OcrLine]:
    """Retry OCR with conservative preprocessing while preserving tap coordinates."""
    prepared = path.with_name(f"{path.stem}-ocr-enhanced.png")
    try:
        run_checked(
            [
                "convert",
                str(path),
                "-resize",
                "150%",
                "-colorspace",
                "Gray",
                "-contrast-stretch",
                "1%x1%",
                str(prepared),
            ],
            timeout=30,
        )
        return ocr_lines(prepared, coordinate_scale=1.5)
    finally:
        prepared.unlink(missing_ok=True)


def enhanced_header_text(path: Path) -> str:
    width, height = image_size(path)
    crop = path.with_name(f"{path.stem}-header-enhanced.png")
    try:
        run_checked(
            [
                "convert",
                str(path),
                "-crop",
                (
                    f"{int(width * 0.68)}x{int(height * 0.09)}"
                    f"+{int(width * 0.16)}+{int(height * 0.02)}"
                ),
                "+repage",
                "-resize",
                "300%",
                "-colorspace",
                "Gray",
                "-contrast-stretch",
                "1%x1%",
                str(crop),
            ],
            timeout=30,
        )
        return "\n".join(ocr_plain(crop, psm=psm) for psm in ("7", "6"))
    finally:
        crop.unlink(missing_ok=True)


def matching_target_lines(
    lines: list[OcrLine], aliases: tuple[str, ...]
) -> list[OcrLine]:
    return [
        line
        for line in lines
        if 180 <= line.center_y <= 1900 and text_matches_alias(line.text, aliases)
    ]


def merge_chat_title_fragments(lines: list[OcrLine]) -> list[OcrLine]:
    """Rebuild title rows split into separate OCR blocks on the chat list."""
    eligible = [
        line
        for line in lines
        if 180 <= line.center_y <= 1900
        and 170 <= line.left <= 880
        and line.right <= 900
    ]
    rows: list[list[OcrLine]] = []
    for line in sorted(eligible, key=lambda item: (item.center_y, item.left)):
        matching_row = next(
            (
                row
                for row in rows
                if abs(
                    line.center_y
                    - int(sum(item.center_y for item in row) / len(row))
                )
                <= 24
            ),
            None,
        )
        if matching_row is None:
            rows.append([line])
        else:
            matching_row.append(line)
    merged: list[OcrLine] = []
    for row in rows:
        if len(row) < 2:
            continue
        ordered = sorted(row, key=lambda item: item.left)
        merged.append(
            OcrLine(
                text=" ".join(item.text for item in ordered),
                left=min(item.left for item in ordered),
                top=min(item.top for item in ordered),
                right=max(item.right for item in ordered),
                bottom=max(item.bottom for item in ordered),
            )
        )
    return merged


def ocr_plain(path: Path, *, psm: str) -> str:
    return run_checked(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            os.environ.get("WECHAT_ANDROID_OCR_LANGS", "chi_sim+chi_tra+eng"),
            "--psm",
            psm,
        ],
        timeout=45,
    ).stdout.strip()


def find_action_line(lines: list[OcrLine], labels: tuple[str, ...]) -> OcrLine | None:
    normalized = {normalize_text(label) for label in labels}
    candidates = [line for line in lines if normalize_text(line.text) in normalized]
    return max(candidates, key=lambda line: (line.right, line.bottom), default=None)


def green_action_center(path: Path, *, min_y_ratio: float) -> tuple[int, int] | None:
    """Find WeChat's lower-right green commit control, never a text heading."""
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        left = int(width * 0.45)
        top = int(height * min_y_ratio)
        points: list[tuple[int, int]] = []
        for y in range(top, int(height * 0.95), 4):
            for x in range(left, int(width * 0.96), 4):
                red, green, blue = image.getpixel((x, y))
                if green >= 135 and green - red >= 35 and green - blue >= 25:
                    points.append((x, y))
    if len(points) < 120:
        return None
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    if max_x - min_x < width * 0.12 or max_y - min_y < height * 0.025:
        return None
    return int((min_x + max_x) / 2), int((min_y + max_y) / 2)


def run_checked(
    command: list[str],
    *,
    timeout: float,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        raise AndroidWechatError(
            f"command failed ({proc.returncode}): {' '.join(command)}: "
            f"{(proc.stderr or proc.stdout)[:400]}"
        )
    return proc


def image_size(path: Path) -> tuple[int, int]:
    proc = run_checked(
        ["identify", "-format", "%w %h", str(path)],
        timeout=20,
    )
    width, height = proc.stdout.split()
    return int(width), int(height)


def image_difference_pixels(before: Path, after: Path) -> int:
    proc = subprocess.run(
        ["compare", "-metric", "AE", str(before), str(after), "null:"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    raw = (proc.stderr or proc.stdout or "0").strip().splitlines()[-1]
    try:
        return int(float(raw))
    except ValueError:
        return 0


def component_key(task_id: str, chat: str, kind: str, value_hash: str) -> str:
    payload = f"{task_id}\0{chat}\0{kind}\0{value_hash}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_serial(adb: str, requested: str) -> str:
    if requested:
        proc = subprocess.run(
            [adb, "-s", requested, "get-state"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip() == "device":
            return requested
        raise SystemExit(f"Android device {requested} is not authorized")
    proc = subprocess.run([adb, "devices"], capture_output=True, text=True, check=False)
    devices = [
        line.split()[0]
        for line in proc.stdout.splitlines()[1:]
        if len(line.split()) >= 2 and line.split()[1] == "device"
    ]
    if len(devices) != 1:
        raise SystemExit("Exactly one authorized Android device is required")
    return devices[0]


def require_tools(*tools: str) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise SystemExit(f"Missing Android WeChat transport tools: {', '.join(missing)}")


def safe_slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", str(value)).strip("-") or "task"


if __name__ == "__main__":
    raise SystemExit(main())
