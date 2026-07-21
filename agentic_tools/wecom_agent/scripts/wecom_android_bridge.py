#!/usr/bin/env python3
"""Guarded WeCom transport over an authorized Android device.

The Android client is a transport, not an agent runtime.  It forwards exact
allowlisted chat messages and artifacts to the same LabCanvas worker used by
the official WeCom transports.  Every write verifies the visible chat title
immediately before committing the action.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterator
from urllib import parse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_CONFIG = PRIVATE / "wecom_android_bridge.local.json"
DEFAULT_STATE_DB = PRIVATE / "wecom_android_bridge.local.sqlite"
DEFAULT_QUEUE = PRIVATE / "wecom_task_queue.jsonl"
DEFAULT_HISTORY_DB = PRIVATE / "wecom_messages.local.sqlite"
DEFAULT_STAGING = PRIVATE / "android-staging"
INGEST = TOOL_ROOT / "scripts" / "wecom_ingest.py"
PACKAGE = "com.tencent.wework"
DOCUMENTS_PACKAGE = "com.google.android.documentsui"
REMOTE_STAGING = "/sdcard/Download/LabCanvas"
MAX_API_BODY = 2 * 1024 * 1024
MAX_MENTIONS = 4
# WeCom exposes the same rich mention span with or without a literal leading
# `@` depending on keyboard/composer state.
MENTION_TOKEN_RE = re.compile(r"@?\ufff3[^\ufff0]+\ufff0")


class BridgeError(RuntimeError):
    """A fail-closed Android transport error."""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def unique_nonempty(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def short_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:length]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bounds(value: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(value or ""))
    if not match:
        raise BridgeError(f"invalid UI bounds: {value!r}")
    x1, y1, x2, y2 = (int(item) for item in match.groups())
    if x2 <= x1 or y2 <= y1:
        raise BridgeError(f"empty UI bounds: {value!r}")
    return x1, y1, x2, y2


def bounds_center(value: str) -> tuple[int, int]:
    x1, y1, x2, y2 = parse_bounds(value)
    return (x1 + x2) // 2, (y1 + y2) // 2


def normalize_visible_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_filename_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("\u200b", "")


def normalize_mention_name(value: Any) -> str:
    return normalize_visible_text(value).replace("\ufffc", "").strip()


def mention_row_matches(row_text: Any, requested_name: str) -> bool:
    candidate = normalize_mention_name(row_text)
    requested = normalize_mention_name(requested_name)
    return candidate == requested or candidate == f"{requested}@微信"


def validate_mentions(values: Any) -> list[str]:
    if values in (None, []):
        return []
    if not isinstance(values, list):
        raise BridgeError("mentions must be a list of exact visible member names")
    if len(values) > MAX_MENTIONS:
        raise BridgeError(f"mentions must contain at most {MAX_MENTIONS} names")
    mentions: list[str] = []
    for value in values:
        mention = normalize_mention_name(value)
        if not mention or len(mention) > 80 or any(ord(character) < 32 for character in mention):
            raise BridgeError("mention name is empty, too long, or contains control characters")
        if mention in {"所有人", "@所有人"}:
            raise BridgeError("broadcast mentions are not allowed")
        if mention not in mentions:
            mentions.append(mention)
    return mentions


def mention_token_count(value: Any) -> int:
    return len(MENTION_TOKEN_RE.findall(str(value or "")))


def composer_matches_message(value: Any, message: str, *, mention_count: int = 0) -> bool:
    raw = str(value or "")
    if mention_count <= 0:
        return normalize_visible_text(raw) == normalize_visible_text(message)
    if mention_token_count(raw) != mention_count:
        return False
    without_mentions = MENTION_TOKEN_RE.sub(" ", raw)
    return normalize_visible_text(without_mentions) == normalize_visible_text(message)


def composer_text(node: ET.Element) -> str:
    value = str(node.attrib.get("text") or "")
    if normalize_visible_text(value).startswith("发消息或按住"):
        return ""
    return value


def chat_title_matches(title: str, chat: str) -> bool:
    return bool(re.fullmatch(re.escape(chat) + r"(?:\(\d+\))?", normalize_visible_text(title)))


def sequence_delta(previous: list[str], current: list[str]) -> tuple[list[str], int]:
    """Return items appended after the largest old-suffix/new-prefix overlap."""
    maximum = min(len(previous), len(current))
    for overlap in range(maximum, 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:], overlap
    return current, 0


def safe_file_name(path: Path) -> str:
    name = path.name.strip()
    if not name or name in {".", ".."} or len(name.encode("utf-8")) > 240:
        raise BridgeError("artifact filename is empty or too long")
    if any(character in name for character in ("/", "\\", "\x00", "\n", "\r")):
        raise BridgeError("artifact filename contains unsafe characters")
    return name


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BridgeError(f"Android bridge is not configured: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError(f"Android bridge config is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise BridgeError("Android bridge config must be a JSON object")
    return payload


def initialize_config(
    path: Path,
    chats: list[str],
    *,
    serial: str = "",
    force: bool = False,
) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if path.is_file() and not force:
        existing = load_config(path)
    target_groups = unique_nonempty([*(existing.get("target_groups") or []), *chats])
    if not target_groups:
        target_groups = ["LabAgent", "AgentTest"]
    payload = {
        "schema_version": 1,
        "enabled": True,
        "preferred_for_gui_send": bool(existing.get("preferred_for_gui_send", True)),
        "serial": str(serial or existing.get("serial") or "").strip(),
        "package": PACKAGE,
        "target_groups": target_groups,
        "account_id": str(existing.get("account_id") or "external-gui"),
        "display": str(existing.get("display") or ":99"),
        "scrcpy_window_name": str(existing.get("scrcpy_window_name") or "LabCanvas Android MIX 2S"),
        "novnc_url": str(
            existing.get("novnc_url")
            or "http://127.0.0.1:6129/vnc.html?host=127.0.0.1&port=6129&autoconnect=1&resize=scale"
        ),
        "state_db": str(existing.get("state_db") or DEFAULT_STATE_DB),
        "queue": str(existing.get("queue") or DEFAULT_QUEUE),
        "history_db": str(existing.get("history_db") or DEFAULT_HISTORY_DB),
        "staging_dir": str(existing.get("staging_dir") or DEFAULT_STAGING),
        "initial_backfill": "seed",
        "poll_seconds": bounded_float(existing.get("poll_seconds"), 6.0, 2.0, 120.0),
        "reconcile_seconds": bounded_float(
            existing.get("reconcile_seconds"), 20.0, 5.0, 600.0
        ),
        "max_send_file_bytes": bounded_int(
            existing.get("max_send_file_bytes"), 100 * 1024 * 1024, 1, 1024 * 1024 * 1024
        ),
        "local_api_host": "127.0.0.1",
        "local_api_port": bounded_int(existing.get("local_api_port"), 19581, 1024, 65535),
        "local_api_token": str(existing.get("local_api_token") or secrets.token_hex(32)),
        "disable_host_media_automount": bool(existing.get("disable_host_media_automount", True)),
    }
    write_private_json(path, payload)
    return {
        "ok": True,
        "config_path": str(path),
        "serial_configured": bool(payload["serial"]),
        "target_groups": target_groups,
        "local_api_url": f"http://127.0.0.1:{payload['local_api_port']}",
        "novnc_url": payload["novnc_url"],
    }


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def node_text(node: ET.Element) -> str:
    return normalize_visible_text(node.attrib.get("text"))


def find_nodes(
    root: ET.Element,
    *,
    text: str | None = None,
    resource_id: str | None = None,
    package: str | None = None,
) -> list[ET.Element]:
    matches: list[ET.Element] = []
    for node in root.iter("node"):
        if text is not None and node_text(node) != normalize_visible_text(text):
            continue
        if resource_id is not None and node.attrib.get("resource-id") != resource_id:
            continue
        if package is not None and node.attrib.get("package") != package:
            continue
        matches.append(node)
    return matches


def clickable_ancestor(root: ET.Element, node: ET.Element) -> ET.Element:
    parents = parent_map(root)
    current = node
    for _ in range(8):
        if current.attrib.get("clickable") == "true" and current.attrib.get("bounds"):
            return current
        current = parents.get(current)  # type: ignore[assignment]
        if current is None:
            break
    return node


def visible_chat_title(root: ET.Element) -> str:
    titles = find_nodes(root, resource_id=f"{PACKAGE}:id/n5i", package=PACKAGE)
    for node in titles:
        title = node_text(node)
        if title and title != "消息":
            return title
    return ""


def validate_file_confirmation(root: ET.Element, chat: str, filename: str) -> bool:
    texts = [node_text(node) for node in root.iter("node") if node_text(node)]
    target_ok = chat in texts
    expected = normalize_filename_text(filename)
    file_ok = any(expected in normalize_filename_text(text) for text in texts)
    send_ok = bool(find_nodes(root, text="发送", package=PACKAGE))
    return target_ok and file_ok and send_ok


class AndroidBridge:
    def __init__(self, config: dict[str, Any], *, config_path: Path = DEFAULT_CONFIG) -> None:
        self.config = config
        self.config_path = config_path.resolve()
        self.serial = str(config.get("serial") or "").strip()
        self.package = str(config.get("package") or PACKAGE)
        self.target_groups = unique_nonempty(config.get("target_groups") or [])
        self.display = str(config.get("display") or ":99")
        self.scrcpy_window_name = str(config.get("scrcpy_window_name") or "LabCanvas Android MIX 2S")
        self.state_db = Path(str(config.get("state_db") or DEFAULT_STATE_DB)).expanduser().resolve()
        self.queue = Path(str(config.get("queue") or DEFAULT_QUEUE)).expanduser().resolve()
        self.history_db = Path(str(config.get("history_db") or DEFAULT_HISTORY_DB)).expanduser().resolve()
        self.staging_dir = Path(str(config.get("staging_dir") or DEFAULT_STAGING)).expanduser().resolve()
        self.lock_path = PRIVATE / "wecom_android_bridge.lock"
        self.reconcile_seconds = bounded_float(
            config.get("reconcile_seconds"), 20.0, 5.0, 600.0
        )
        self._next_reconcile_at = 0.0
        self._stop = threading.Event()
        self.init_state()

    def init_state(self) -> None:
        self.state_db.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.staging_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(self.state_db) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS components ("
                "component_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, chat TEXT NOT NULL, "
                "kind TEXT NOT NULL, value_hash TEXT NOT NULL, status TEXT NOT NULL, "
                "details_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS snapshots ("
                "chat TEXT PRIMARY KEY, sequence_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )

    @contextmanager
    def serialized(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.lock_path.open("w", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def run(
        self,
        command: list[str],
        *,
        timeout: float = 30,
        check: bool = True,
        text: bool = True,
        input_data: str | bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[Any]:
        process = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
            env=env,
        )
        if check and process.returncode != 0:
            stderr = process.stderr if text else process.stderr.decode("utf-8", errors="replace")
            raise BridgeError(f"command failed ({command[0]}): {str(stderr)[-500:]}")
        return process

    def adb(self, *args: str, timeout: float = 30, check: bool = True) -> subprocess.CompletedProcess[str]:
        if not self.serial:
            raise BridgeError("Android serial is not configured")
        return self.run(["adb", "-s", self.serial, *args], timeout=timeout, check=check)

    def adb_shell(self, *args: str, timeout: float = 30, check: bool = True) -> str:
        return self.adb("shell", *args, timeout=timeout, check=check).stdout

    def disable_host_automount(self) -> None:
        if not bool(self.config.get("disable_host_media_automount", True)):
            return
        for key in ("automount", "automount-open"):
            self.run(
                ["gsettings", "set", "org.gnome.desktop.media-handling", key, "false"],
                timeout=10,
                check=False,
            )

    def prepare_device(self) -> None:
        self.disable_host_automount()
        if self.adb("get-state", timeout=10).stdout.strip() != "device":
            raise BridgeError("configured Android device is not authorized")
        packages = self.adb_shell("pm", "list", "packages", self.package)
        if f"package:{self.package}" not in packages:
            raise BridgeError("official WeCom package is not installed on the device")
        keyguard = self.adb_shell("dumpsys", "window", timeout=20, check=False)
        if "isStatusBarKeyguard=true" in keyguard:
            raise BridgeError("Android keyguard is locked")
        for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
            self.adb_shell("settings", "put", "global", key, "0", check=False)
        # Keep hierarchy bounds stable even when the physical phone is moved.
        self.adb_shell("settings", "put", "system", "accelerometer_rotation", "0", check=False)
        self.adb_shell("settings", "put", "system", "user_rotation", "0", check=False)
        self.adb_shell("svc", "power", "stayon", "true", check=False)

    def current_package(self) -> str:
        output = self.adb_shell("dumpsys", "window", "windows", timeout=20, check=False)
        match = re.search(r"mCurrentFocus=.*?\s([A-Za-z0-9_.]+)/", output)
        if not match:
            match = re.search(r"mFocusedApp=.*?\s([A-Za-z0-9_.]+)/", output)
        if not match:
            activities = self.adb_shell("dumpsys", "activity", "activities", timeout=20, check=False)
            match = re.search(r"mResumedActivity:.*?\s([A-Za-z0-9_.]+)/", activities)
            if not match:
                match = re.search(r"topResumedActivity=.*?\s([A-Za-z0-9_.]+)/", activities)
        return match.group(1) if match else ""

    def launch_wecom(self) -> None:
        self.prepare_device()
        if self.current_package() == self.package:
            return
        self.adb_shell(
            "monkey", "-p", self.package, "-c", "android.intent.category.LAUNCHER", "1", timeout=30
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.current_package() == self.package:
                return
            time.sleep(0.5)
        raise BridgeError("WeCom did not reach the foreground")

    def dump_hierarchy(self, *, attempts: int = 5) -> ET.Element:
        last_error = ""
        for _ in range(max(1, attempts)):
            self.adb_shell(
                "uiautomator", "dump", "--compressed", "/sdcard/labcanvas_wecom.xml", timeout=20, check=False
            )
            payload = self.adb_shell("cat", "/sdcard/labcanvas_wecom.xml", timeout=10, check=False)
            try:
                root = ET.fromstring(payload)
            except ET.ParseError as exc:
                last_error = str(exc)
                time.sleep(0.4)
                continue
            if any(True for _ in root.iter("node")):
                return root
            last_error = "empty hierarchy"
            time.sleep(0.4)
        raise BridgeError(f"could not read Android UI hierarchy: {last_error}")

    def tap_node(self, root: ET.Element, node: ET.Element) -> None:
        target = clickable_ancestor(root, node)
        x, y = bounds_center(target.attrib.get("bounds", ""))
        self.adb_shell("input", "tap", str(x), str(y))

    def press_back(self) -> None:
        self.adb_shell("input", "keyevent", "4", check=False)
        time.sleep(0.6)

    def open_chat(self, chat: str) -> ET.Element:
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android chat")
        self.launch_wecom()
        for _ in range(6):
            root = self.dump_hierarchy()
            if chat_title_matches(visible_chat_title(root), chat):
                return root
            rows = find_nodes(root, text=chat, resource_id=f"{self.package}:id/iql", package=self.package)
            if rows:
                self.tap_node(root, rows[0])
                time.sleep(1.0)
                opened = self.dump_hierarchy()
                if chat_title_matches(visible_chat_title(opened), chat):
                    return opened
                raise BridgeError(f"visible WeCom chat title did not match {chat!r}")
            if self.current_package() != self.package:
                self.press_back()
                self.launch_wecom()
            else:
                self.press_back()
        raise BridgeError(f"exact allowlisted WeCom chat is not visible: {chat}")

    def open_chat_list(self) -> ET.Element:
        self.launch_wecom()
        for _ in range(6):
            root = self.dump_hierarchy()
            title_nodes = find_nodes(
                root,
                text="消息",
                resource_id=f"{self.package}:id/n5i",
                package=self.package,
            )
            if title_nodes and any(
                find_nodes(root, text=chat, resource_id=f"{self.package}:id/iql", package=self.package)
                for chat in self.target_groups
            ):
                return root
            self.press_back()
        raise BridgeError("WeCom chat list is not visible")

    def unread_target_chats(self, root: ET.Element) -> list[str]:
        parents = parent_map(root)
        result: list[str] = []
        for chat in self.target_groups:
            nodes = find_nodes(root, text=chat, resource_id=f"{self.package}:id/iql", package=self.package)
            if not nodes:
                continue
            row = nodes[0]
            for _ in range(5):
                parent = parents.get(row)
                if parent is None:
                    break
                row = parent
                if row.attrib.get("clickable") == "true":
                    break
            unread = any(
                node.attrib.get("resource-id") == f"{self.package}:id/l07"
                and node_text(node).isdigit()
                and int(node_text(node)) > 0
                for node in row.iter("node")
            )
            if unread:
                result.append(chat)
        return result

    def ensure_chat_identity(self, chat: str) -> ET.Element:
        root = self.dump_hierarchy()
        title = visible_chat_title(root)
        if not chat_title_matches(title, chat):
            raise BridgeError(f"visible WeCom chat changed before write: {title!r}")
        return root

    def scrcpy_window_id(self) -> tuple[dict[str, str], str]:
        env = {**os.environ, "DISPLAY": self.display}
        search = self.run(
            ["xdotool", "search", "--name", f"^{re.escape(self.scrcpy_window_name)}"],
            timeout=10,
            env=env,
        )
        windows = [line.strip() for line in search.stdout.splitlines() if line.strip()]
        if not windows:
            raise BridgeError("scrcpy mirror window is unavailable for Unicode clipboard input")
        return env, windows[-1]

    def paste_text(self, text: str) -> None:
        if not text:
            return
        env, window = self.scrcpy_window_id()
        process = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-loops", "1"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        assert process.stdin is not None
        process.stdin.write(text.encode("utf-8"))
        process.stdin.close()
        time.sleep(0.2)
        self.run(
            ["xdotool", "windowfocus", "--sync", window, "key", "--clearmodifiers", "ctrl+v"],
            timeout=10,
            env=env,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=2)

    def clear_automation_draft(self, chat: str) -> None:
        """Leave the chat with an empty composer after our own failed write."""
        for _ in range(4):
            root = self.dump_hierarchy()
            if chat_title_matches(visible_chat_title(root), chat):
                break
            self.press_back()
        else:
            return
        composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
        if not composers or not composer_text(composers[-1]):
            return
        self.tap_node(root, composers[-1])
        env, window = self.scrcpy_window_id()
        self.run(
            [
                "xdotool",
                "windowfocus",
                "--sync",
                window,
                "key",
                "--clearmodifiers",
                "ctrl+a",
                "BackSpace",
            ],
            timeout=10,
            env=env,
        )
        time.sleep(0.4)

    def mention_picker(self, *, timeout: float = 5.0) -> ET.Element:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            root = self.dump_hierarchy(attempts=2)
            title = find_nodes(
                root,
                text="选择提醒的人",
                resource_id=f"{self.package}:id/n5i",
                package=self.package,
            )
            search = find_nodes(root, resource_id=f"{self.package}:id/g7i", package=self.package)
            if title and search:
                return root
            time.sleep(0.25)
        raise BridgeError("WeCom native mention picker did not open")

    def exact_mention_rows(self, root: ET.Element, mention: str) -> list[ET.Element]:
        return [
            node
            for node in root.iter("node")
            if node.attrib.get("package") == self.package
            and node.attrib.get("resource-id") == f"{self.package}:id/ic1"
            and mention_row_matches(node.attrib.get("text"), mention)
        ]

    def select_native_mention(self, chat: str, mention: str, *, expected_count: int) -> None:
        self.adb_shell("input", "text", "@")
        picker = self.mention_picker()
        matches = self.exact_mention_rows(picker, mention)
        if len(matches) != 1:
            search = find_nodes(picker, resource_id=f"{self.package}:id/g7i", package=self.package)
            if not search:
                raise BridgeError("WeCom mention search is unavailable")
            self.tap_node(picker, search[-1])
            self.paste_text(mention)
            time.sleep(0.7)
            picker = self.mention_picker()
            matches = self.exact_mention_rows(picker, mention)
        if len(matches) != 1:
            raise BridgeError(f"expected one exact WeCom member named {mention!r}, found {len(matches)}")
        self.tap_node(picker, matches[0])
        time.sleep(0.5)
        root = self.ensure_chat_identity(chat)
        composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
        if not composers or mention_token_count(composer_text(composers[-1])) != expected_count:
            raise BridgeError(f"WeCom did not create a native mention for {mention!r}")

    def component_key(self, task_id: str, chat: str, kind: str, value_hash: str) -> str:
        return short_hash(f"{task_id}\0{chat}\0{kind}\0{value_hash}", 64)

    def component_sent(self, key: str) -> bool:
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute("SELECT status FROM components WHERE component_key = ?", (key,)).fetchone()
        return bool(row and row[0] == "sent")

    def mark_component(
        self,
        key: str,
        *,
        task_id: str,
        chat: str,
        kind: str,
        value_hash: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with sqlite3.connect(self.state_db) as conn:
            conn.execute(
                "INSERT INTO components("
                "component_key, task_id, chat, kind, value_hash, status, details_json, updated_at"
                ") "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(component_key) DO UPDATE SET "
                "status = excluded.status, details_json = excluded.details_json, updated_at = excluded.updated_at",
                (
                    key,
                    task_id,
                    chat,
                    kind,
                    value_hash,
                    status,
                    json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                    now_iso(),
                ),
            )

    def send_text_locked(
        self,
        chat: str,
        text: str,
        *,
        task_id: str,
        mentions: list[str] | None = None,
    ) -> dict[str, Any]:
        exact_mentions = validate_mentions(mentions or [])
        value_hash = hashlib.sha256(
            json.dumps(
                {"message": text, "mentions": exact_mentions},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        key = self.component_key(task_id, chat, "text", value_hash)
        if self.component_sent(key):
            return {
                "ok": True,
                "duplicate": True,
                "sent_messages": [text],
                "sent_files": [],
                "mentioned_users": exact_mentions,
            }
        root = self.open_chat(chat)
        composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
        if not composers:
            raise BridgeError("WeCom composer is not visible")
        if composer_text(composers[-1]):
            raise BridgeError("refusing to overwrite a non-empty WeCom draft")
        self.tap_node(root, composers[-1])
        try:
            time.sleep(0.4)
            for index, mention in enumerate(exact_mentions, start=1):
                self.select_native_mention(chat, mention, expected_count=index)
            self.paste_text((" " if exact_mentions else "") + text)
            time.sleep(0.5)
            root = self.ensure_chat_identity(chat)
            composer = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
            if not composer or not composer_matches_message(
                composer_text(composer[-1]),
                text,
                mention_count=len(exact_mentions),
            ):
                raise BridgeError("text and native mentions were not reproduced exactly in the WeCom composer")
            send_buttons = find_nodes(root, text="发送", resource_id=f"{self.package}:id/j24", package=self.package)
            if not send_buttons:
                raise BridgeError("WeCom text send button is unavailable")
            self.tap_node(root, send_buttons[-1])
        except Exception:
            self.clear_automation_draft(chat)
            raise
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            time.sleep(0.7)
            current = self.ensure_chat_identity(chat)
            composers = find_nodes(current, resource_id=f"{self.package}:id/j28", package=self.package)
            body_visible = any(
                normalize_visible_text(text) in node_text(node)
                for node in current.iter("node")
                if normalize_visible_text(text)
            )
            if body_visible and composers and not composer_text(composers[-1]):
                self.mark_component(
                    key,
                    task_id=task_id,
                    chat=chat,
                    kind="text",
                    value_hash=value_hash,
                    status="sent",
                    details={"mentioned_users": exact_mentions},
                )
                return {
                    "ok": True,
                    "sent_messages": [text],
                    "sent_files": [],
                    "mentioned_users": exact_mentions,
                    "errors": [],
                }
        raise BridgeError("WeCom did not expose the sent text after commit")

    def stage_file(self, path: Path) -> tuple[Path, str, str]:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise BridgeError(f"artifact does not exist: {resolved}")
        maximum = bounded_int(
            self.config.get("max_send_file_bytes"), 100 * 1024 * 1024, 1, 1024 * 1024 * 1024
        )
        if resolved.stat().st_size <= 0 or resolved.stat().st_size > maximum:
            raise BridgeError(f"artifact size is outside the configured limit: {resolved}")
        name = safe_file_name(resolved)
        digest = sha256_file(resolved)
        local_copy = self.staging_dir / digest[:16] / name
        local_copy.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not local_copy.is_file() or sha256_file(local_copy) != digest:
            local_copy.write_bytes(resolved.read_bytes())
            os.chmod(local_copy, 0o600)
        remote_dir = f"{REMOTE_STAGING}/{digest[:16]}"
        remote_path = f"{remote_dir}/{name}"
        self.adb_shell("mkdir", "-p", remote_dir)
        self.adb("push", str(local_copy), remote_path, timeout=180)
        return resolved, digest, remote_path

    def wait_for_package(self, package: str, *, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.current_package() == package:
                return
            time.sleep(0.4)
        raise BridgeError(f"Android package did not become active: {package}")

    def send_file_locked(self, chat: str, path: Path, *, task_id: str) -> dict[str, Any]:
        resolved, digest, _remote_path = self.stage_file(path)
        filename = resolved.name
        key = self.component_key(task_id, chat, "file", f"{digest}:{filename}")
        if self.component_sent(key):
            return {"ok": True, "duplicate": True, "sent_messages": [], "sent_files": [str(resolved)]}
        root = self.open_chat(chat)
        plus = find_nodes(root, resource_id=f"{self.package}:id/j1v", package=self.package)
        if not plus:
            raise BridgeError("WeCom attachment menu button is unavailable")
        self.tap_node(root, plus[-1])
        time.sleep(0.7)
        menu = self.ensure_chat_identity(chat)
        file_nodes = find_nodes(menu, text="文件", package=self.package)
        if not file_nodes:
            raise BridgeError("WeCom file action is unavailable")
        self.tap_node(menu, file_nodes[-1])
        time.sleep(0.7)
        choice = self.dump_hierarchy()
        local = find_nodes(choice, text="从本地文件选择", package=self.package)
        if not local:
            raise BridgeError("WeCom local-file picker action is unavailable")
        self.tap_node(choice, local[-1])
        self.wait_for_package(DOCUMENTS_PACKAGE)
        picker = self.dump_hierarchy()
        search = find_nodes(
            picker,
            resource_id=f"{DOCUMENTS_PACKAGE}:id/option_menu_search",
            package=DOCUMENTS_PACKAGE,
        )
        if not search:
            raise BridgeError("Android document search is unavailable")
        self.tap_node(picker, search[-1])
        time.sleep(0.4)
        self.paste_text(filename)
        self.adb_shell("input", "keyevent", "66")
        time.sleep(1.2)
        results = self.dump_hierarchy()
        matches = find_nodes(results, text=filename, resource_id="android:id/title", package=DOCUMENTS_PACKAGE)
        if len(matches) != 1:
            raise BridgeError(f"expected one exact staged file result, found {len(matches)}")
        self.tap_node(results, matches[0])
        self.wait_for_package(self.package)
        time.sleep(1.0)
        confirmation = self.dump_hierarchy()
        if not validate_file_confirmation(confirmation, chat, filename):
            raise BridgeError("WeCom file confirmation did not match exact chat and artifact")
        send = find_nodes(confirmation, text="发送", package=self.package)
        self.tap_node(confirmation, send[-1])
        deadline = time.monotonic() + 120
        expected = normalize_filename_text(filename)
        while time.monotonic() < deadline:
            time.sleep(1.0)
            current = self.ensure_chat_identity(chat)
            texts = [normalize_filename_text(node.attrib.get("text")) for node in current.iter("node")]
            if any(expected == value or expected in value for value in texts):
                # A card appears before the upload has necessarily left the
                # local client. Require a short stable second observation and
                # reject visible retry/failure states before recording delivery.
                time.sleep(3.0)
                current = self.ensure_chat_identity(chat)
                visible = [normalize_visible_text(node.attrib.get("text")) for node in current.iter("node")]
                normalized = [normalize_filename_text(value) for value in visible]
                if not any(expected == value or expected in value for value in normalized):
                    continue
                if any(marker in value for value in visible for marker in ("发送失败", "上传失败", "重试")):
                    raise BridgeError("WeCom reported an artifact upload failure")
                self.mark_component(
                    key,
                    task_id=task_id,
                    chat=chat,
                    kind="file",
                    value_hash=f"{digest}:{filename}",
                    status="sent",
                    details={"size_bytes": resolved.stat().st_size, "sha256": digest},
                )
                return {"ok": True, "sent_messages": [], "sent_files": [str(resolved)], "errors": []}
        raise BridgeError("WeCom did not expose the uploaded artifact after commit")

    def send(
        self,
        chat: str,
        message: str,
        files: list[Path],
        *,
        task_id: str,
        mentions: list[str] | None = None,
    ) -> dict[str, Any]:
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android target")
        exact_mentions = validate_mentions(mentions or [])
        if exact_mentions and not message.strip():
            raise BridgeError("mentions require a text message")
        if not message.strip() and not files:
            raise BridgeError("send requires a message and/or artifact")
        with self.serialized():
            sent_messages: list[str] = []
            sent_files: list[str] = []
            mentioned_users: list[str] = []
            errors: list[dict[str, str]] = []
            if message.strip():
                try:
                    result = self.send_text_locked(
                        chat,
                        message,
                        task_id=task_id,
                        mentions=exact_mentions,
                    )
                    sent_messages.extend(result.get("sent_messages") or [])
                    mentioned_users.extend(result.get("mentioned_users") or [])
                except Exception as exc:
                    errors.append({"kind": "text", "error": f"{type(exc).__name__}: {str(exc)[:500]}"})
            for path in files:
                try:
                    result = self.send_file_locked(chat, path, task_id=task_id)
                    sent_files.extend(result.get("sent_files") or [])
                except Exception as exc:
                    errors.append(
                        {"kind": "file", "path": str(path), "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
                    )
                    break
            return {
                "ok": not errors,
                "transport": "wecom_android",
                "chat_id": f"gui:{chat}",
                "sent_messages": sent_messages,
                "sent_files": sent_files,
                "mentioned_users": unique_nonempty(mentioned_users),
                "errors": errors,
            }

    def parse_messages(self, root: ET.Element) -> list[dict[str, str]]:
        rows = find_nodes(root, resource_id=f"{self.package}:id/eyy", package=self.package)
        records: list[dict[str, str]] = []
        for row in rows:
            sender = ""
            sender_is_wechat = False
            bodies: list[str] = []
            for node in row.iter("node"):
                text = node_text(node)
                if not text:
                    continue
                resource = node.attrib.get("resource-id", "")
                if text in {"＠微信", "@微信"}:
                    sender_is_wechat = True
                    continue
                if not resource and not sender:
                    sender = text
                if resource.endswith(":id/j1l"):
                    bodies.append(text)
            body = "\n".join(unique_nonempty(bodies))
            if not body:
                continue
            direction = "inbound" if sender else "outbound"
            fingerprint = short_hash(f"{direction}\0{sender}\0{body}", 64)
            records.append(
                {
                    "fingerprint": fingerprint,
                    "direction": direction,
                    "sender": sender,
                    "mention_name": f"{sender}@微信" if sender and sender_is_wechat else sender,
                    "body": body,
                }
            )
        return records

    def load_snapshot(self, chat: str) -> list[str] | None:
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute("SELECT sequence_json FROM snapshots WHERE chat = ?", (chat,)).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return [str(item) for item in payload] if isinstance(payload, list) else None

    def save_snapshot(self, chat: str, sequence: list[str]) -> None:
        with sqlite3.connect(self.state_db) as conn:
            conn.execute(
                "INSERT INTO snapshots(chat, sequence_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(chat) DO UPDATE SET "
                "sequence_json = excluded.sequence_json, updated_at = excluded.updated_at",
                (chat, json.dumps(sequence), now_iso()),
            )

    def build_event(self, chat: str, record: dict[str, str]) -> dict[str, Any]:
        event_key = short_hash(
            f"{chat}\0{record.get('sender')}\0{record.get('body')}\0{time.time_ns()}", 24
        )
        sender = str(record.get("sender") or "unknown")
        return {
            "transport": "wecom",
            "transport_channel": "wecom_android",
            "account_id": str(self.config.get("account_id") or "external-gui"),
            "message_id": f"android:{event_key}",
            "chat_id": f"gui:{chat}",
            "chat_type": "group",
            "sender_userid": f"android-member:{short_hash(sender, 24)}",
            "sender_display": sender,
            "sender_mention": str(record.get("mention_name") or sender),
            "create_time": int(time.time()),
            "msgtype": "text",
            "text": str(record.get("body") or ""),
            "quote_text": "",
            "attachments": [],
        }

    def invoke_ingest(self, event: dict[str, Any]) -> dict[str, Any]:
        runtime = self.staging_dir / "events"
        runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", prefix="event-", dir=runtime, delete=False
        ) as handle:
            json.dump(event, handle, ensure_ascii=False)
            event_path = Path(handle.name)
        os.chmod(event_path, 0o600)
        try:
            process = self.run(
                [
                    sys.executable,
                    str(INGEST),
                    "--event-file",
                    str(event_path),
                    "--queue",
                    str(self.queue),
                    "--history-db",
                    str(self.history_db),
                    "--json",
                ],
                timeout=600,
                check=False,
            )
            try:
                payload = json.loads(process.stdout)
            except json.JSONDecodeError as exc:
                raise BridgeError("WeCom ingest returned invalid JSON") from exc
            if process.returncode != 0 or not payload.get("ok"):
                raise BridgeError(str(payload.get("error") or process.stderr[-500:]))
            return payload
        finally:
            event_path.unlink(missing_ok=True)

    def snapshot(self, chat: str, *, enqueue: bool = False) -> dict[str, Any]:
        with self.serialized():
            root = self.open_chat(chat)
            records = self.parse_messages(root)
            sequence = [record["fingerprint"] for record in records]
            previous = self.load_snapshot(chat)
            if previous is None:
                self.save_snapshot(chat, sequence)
                return {"ok": True, "chat": chat, "seeded": len(sequence), "messages": [], "processed": 0}
            delta, overlap = sequence_delta(previous, sequence)
            if overlap == 0 and previous and sequence:
                self.save_snapshot(chat, sequence)
                return {
                    "ok": True,
                    "chat": chat,
                    "seeded": len(sequence),
                    "messages": [],
                    "processed": 0,
                    "reason": "viewport_changed_without_overlap",
                }
            new_records = records[-len(delta) :] if delta else []
            inbound = [record for record in new_records if record.get("direction") == "inbound"]
            ingested: list[dict[str, Any]] = []
            pending_replies: list[tuple[str, str, str]] = []
            if enqueue:
                for record in inbound:
                    event = self.build_event(chat, record)
                    result = self.invoke_ingest(event)
                    ingested.append(result)
                    response = str(result.get("reply") or result.get("ack") or "").strip()
                    if response:
                        pending_replies.append(
                            (
                                response,
                                str(record.get("mention_name") or record.get("sender") or ""),
                                f"ingress:{event['message_id']}",
                            )
                        )
            # Checkpoint ingress before any write. An uncertain reply send must
            # never replay the original request after restart.
            self.save_snapshot(chat, sequence)
            sent_replies: list[str] = []
            reply_errors: list[dict[str, str]] = []
            for response, sender, task_id in pending_replies:
                try:
                    sent = self.send_text_locked(
                        chat,
                        response,
                        task_id=task_id,
                        mentions=[sender] if sender else [],
                    )
                    sent_replies.extend(sent.get("sent_messages") or [])
                except Exception as exc:
                    reply_errors.append(
                        {
                            "sender": sender,
                            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                        }
                    )
            return {
                "ok": not reply_errors,
                "chat": chat,
                "overlap": overlap,
                "processed": len(inbound),
                "messages": inbound,
                "ingested": ingested,
                "replied": len(sent_replies),
                "reply_errors": reply_errors,
            }

    def poll_cycle(self) -> dict[str, Any]:
        now = time.monotonic()
        due = [chat for chat in self.target_groups if self.load_snapshot(chat) is None]
        unread: list[str] = []
        if not due:
            with self.serialized():
                chat_list = self.open_chat_list()
                unread = self.unread_target_chats(chat_list)
            due = list(unread)
        reconciliation = now >= self._next_reconcile_at
        if reconciliation:
            # Opening a chat manually or for diagnostics clears WeCom's unread
            # badge. Periodic exact-chat reconciliation makes that badge a
            # latency hint rather than the sole source of ingress truth.
            due = unique_nonempty([*due, *self.target_groups])
            self._next_reconcile_at = now + self.reconcile_seconds
        results: list[dict[str, Any]] = []
        for chat in due:
            try:
                results.append(self.snapshot(chat, enqueue=True))
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "chat": chat,
                        "processed": 0,
                        "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                    }
                )
        restore_error = ""
        if due:
            try:
                with self.serialized():
                    self.open_chat_list()
            except Exception as exc:
                restore_error = f"{type(exc).__name__}: {str(exc)[:500]}"
        return {
            "ok": all(result.get("ok") for result in results) and not restore_error,
            "due_chats": due,
            "unread_chats": unread,
            "reconciliation": reconciliation,
            "processed": sum(int(result.get("processed") or 0) for result in results),
            "results": results,
            "restore_error": restore_error,
        }

    def list_chats(self) -> dict[str, Any]:
        return {
            "ok": True,
            "transport": "wecom_android",
            "chats": [
                {"chat_id": f"gui:{chat}", "chat_name": chat, "chat_type": "group"}
                for chat in self.target_groups
            ],
        }

    def status(self) -> dict[str, Any]:
        device = self.run(["adb", "devices"], timeout=10, check=False).stdout
        authorized = bool(self.serial and re.search(rf"^{re.escape(self.serial)}\s+device$", device, re.M))
        package = ""
        title = ""
        if authorized:
            package = self.current_package()
            try:
                title = visible_chat_title(self.dump_hierarchy(attempts=2)) if package == self.package else ""
            except BridgeError:
                title = ""
        return {
            "ok": authorized,
            "enabled": bool(self.config.get("enabled", True)),
            "transport": "wecom_android",
            "device_authorized": authorized,
            "wecom_foreground": package == self.package,
            "visible_chat": title,
            "target_groups": self.target_groups,
            "novnc_url": str(self.config.get("novnc_url") or ""),
            "local_api_url": f"http://127.0.0.1:{bounded_int(self.config.get('local_api_port'), 19581, 1024, 65535)}",
        }

    def serve_forever(self) -> None:
        host = "127.0.0.1"
        port = bounded_int(self.config.get("local_api_port"), 19581, 1024, 65535)
        server = ThreadingHTTPServer((host, port), make_api_handler(self))
        server.daemon_threads = True
        print(json.dumps({"ok": True, "event": "started", "transport": "wecom_android", "port": port}), flush=True)
        interval = bounded_float(self.config.get("poll_seconds"), 6.0, 2.0, 120.0)

        def monitor() -> None:
            while not self._stop.wait(interval):
                try:
                    result = self.poll_cycle()
                except Exception as exc:
                    print(
                        json.dumps(
                            {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"},
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    continue
                if result.get("processed"):
                    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)

        thread = threading.Thread(target=monitor, name="wecom-android-monitor", daemon=True)
        thread.start()
        try:
            server.serve_forever()
        finally:
            self._stop.set()
            server.server_close()


def make_api_handler(bridge: AndroidBridge):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LabCanvasWeComAndroid/1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = parse.urlparse(self.path)
            if parsed.path == "/health":
                self.write_json(HTTPStatus.OK, bridge.status())
                return
            if not self.authorized():
                self.write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
                return
            if parsed.path == "/v1/status":
                self.write_json(HTTPStatus.OK, bridge.status())
                return
            if parsed.path == "/v1/chats":
                self.write_json(HTTPStatus.OK, bridge.list_chats())
                return
            if parsed.path == "/v1/messages":
                query = parse.parse_qs(parsed.query)
                chat_id = str((query.get("chat_id") or [""])[0])
                chat = self.resolve_chat(chat_id)
                if not chat:
                    self.write_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "chat is not allowlisted"})
                    return
                try:
                    self.write_json(HTTPStatus.OK, bridge.snapshot(chat, enqueue=False))
                except Exception as exc:
                    self.write_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"},
                    )
                return
            self.write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/send":
                self.write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
                return
            if not self.authorized():
                self.write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_API_BODY:
                    self.write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "invalid body size"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                chat = self.resolve_chat(str(payload.get("chat_id") or ""))
                if not chat:
                    self.write_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "chat is not allowlisted"})
                    return
                raw_files = payload.get("files") or []
                if not isinstance(raw_files, list) or len(raw_files) > 16:
                    self.write_json(
                        HTTPStatus.BAD_REQUEST,
                        {"ok": False, "error": "files must contain at most 16 paths"},
                    )
                    return
                try:
                    mentions = validate_mentions(payload.get("mentions") or [])
                except BridgeError as exc:
                    self.write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                result = bridge.send(
                    chat,
                    str(payload.get("message") or ""),
                    [Path(str(item)) for item in raw_files],
                    task_id=str(payload.get("task_id") or "api")[:256] or "api",
                    mentions=mentions,
                )
                self.write_json(HTTPStatus.OK if result.get("ok") else HTTPStatus.INTERNAL_SERVER_ERROR, result)
            except Exception as exc:
                self.write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"},
                )

        def resolve_chat(self, chat_id: str) -> str:
            chat = chat_id.removeprefix("gui:") if chat_id.startswith("gui:") else ""
            expected = f"gui:{chat}"
            return chat if chat in bridge.target_groups and secrets.compare_digest(chat_id, expected) else ""

        def authorized(self) -> bool:
            expected = f"Bearer {bridge.config.get('local_api_token') or ''}"
            return secrets.compare_digest(str(self.headers.get("Authorization") or ""), expected)

        def write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init")
    initialize.add_argument("--chat", action="append", dest="chats", default=[])
    initialize.add_argument("--serial", default="")
    initialize.add_argument("--force", action="store_true")
    initialize.add_argument("--json", action="store_true")

    for name in ("status", "chats", "serve"):
        command = subparsers.add_parser(name)
        command.add_argument("--json", action="store_true")

    open_chat = subparsers.add_parser("open")
    open_chat.add_argument("--chat", required=True)
    open_chat.add_argument("--json", action="store_true")

    messages = subparsers.add_parser("messages")
    messages.add_argument("--chat", required=True)
    messages.add_argument("--enqueue", action="store_true")
    messages.add_argument("--json", action="store_true")

    send = subparsers.add_parser("send")
    send.add_argument("--chat", required=True)
    send.add_argument("--message", default="")
    send.add_argument("--mention", action="append", dest="mentions", default=[])
    send.add_argument("--file", action="append", dest="files", type=Path, default=[])
    send.add_argument("--task-id", default="manual")
    send.add_argument("--live", action="store_true")
    send.add_argument("--json", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "init":
            payload = initialize_config(
                args.config,
                args.chats,
                serial=args.serial,
                force=args.force,
            )
        else:
            bridge = AndroidBridge(load_config(args.config), config_path=args.config)
            if args.command == "status":
                payload = bridge.status()
            elif args.command == "chats":
                payload = bridge.list_chats()
            elif args.command == "open":
                with bridge.serialized():
                    root = bridge.open_chat(args.chat)
                payload = {"ok": True, "chat": args.chat, "visible_title": visible_chat_title(root)}
            elif args.command == "messages":
                payload = bridge.snapshot(args.chat, enqueue=args.enqueue)
            elif args.command == "send":
                if not args.message.strip() and not args.files:
                    raise BridgeError("send requires --message and/or --file")
                if not args.live:
                    payload = {
                        "ok": True,
                        "dry_run": True,
                        "chat": args.chat,
                        "message_bytes": len(args.message.encode("utf-8")),
                        "mentions": validate_mentions(args.mentions),
                        "files": [str(path.expanduser().resolve()) for path in args.files],
                    }
                else:
                    payload = bridge.send(
                        args.chat,
                        args.message,
                        args.files,
                        task_id=args.task_id,
                        mentions=args.mentions,
                    )
            else:
                bridge.serve_forever()
                return 0
    except Exception as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
