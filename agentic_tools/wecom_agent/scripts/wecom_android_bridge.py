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
# WeCom's Android document picker indexes the top-level Download provider
# reliably, but can omit files staged under nested application directories.
# The local hash directory still prevents collisions and preserves isolation.
REMOTE_STAGING = "/sdcard/Download"
MAX_API_BODY = 2 * 1024 * 1024
MAX_MENTIONS = 4
# WeCom exposes the same rich mention span with or without a literal leading
# `@` depending on keyboard/composer state.
MENTION_TOKEN_RE = re.compile(r"@?\ufff3[^\ufff0]+\ufff0")
MESSAGE_TIME_RE = re.compile(
    r"^(?:\d{1,2}:\d{2}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}:\d{2})?|"
    r"(?:(?:今天|昨天|星期[一二三四五六日天]|周[一二三四五六日天])\s*)?"
    r"(?:凌晨|早上|上午|中午|下午|傍晚|晚上)?\s*\d{1,2}:\d{2})$"
)
MESSAGE_CHROME_TEXT = {
    "＠微信",
    "@微信",
    "已读",
    "未读",
    "发送中",
    "重新发送",
    "撤回",
}


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


def filename_display_matches(value: Any, filename: str) -> bool:
    """Match a WeCom file card even when Android ellipsizes its middle."""
    visible = normalize_filename_text(value)
    expected = normalize_filename_text(filename)
    if not visible or not expected:
        return False
    if expected == visible or expected in visible:
        return True
    for marker in ("...", "\u2026"):
        if marker not in visible:
            continue
        prefix, suffix = visible.split(marker, 1)
        prefix = prefix.removeprefix("[文件]")
        suffix = re.split(r"(?:\(|\s)\d+(?:\.\d+)?\s*(?:[KMG]?B|[KMG])", suffix, maxsplit=1)[0]
        if len(prefix) >= 8 and len(suffix) >= 4 and expected.startswith(prefix) and expected.endswith(suffix):
            return True
    return False


def visible_file_card_matches(root: ET.Element, filename: str) -> bool:
    return any(
        node.attrib.get("package") == PACKAGE
        and filename_display_matches(node_text(node), filename)
        for node in root.iter("node")
    )


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


def text_component_value_hash(message: str, mentions: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"message": message, "mentions": mentions},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def recoverable_native_mention_error(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return any(
        marker in text
        for marker in (
            "mention picker",
            "mention search",
            "native mention",
            "exact wecom member",
            "native mentions were not reproduced exactly",
        )
    )


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
    target_ok = any(chat_title_matches(text, chat) for text in texts)
    expected = normalize_filename_text(filename)
    file_ok = any(expected in normalize_filename_text(text) for text in texts)
    send_ok = bool(find_nodes(root, text="发送", package=PACKAGE))
    return target_ok and file_ok and send_ok


def exact_document_file_nodes(root: ET.Element, filename: str) -> list[ET.Element]:
    """Return real DocumentsUI file rows, never the filename search field."""
    expected = normalize_filename_text(filename)
    matches: list[ET.Element] = []
    for node in root.iter("node"):
        if node.attrib.get("package") != DOCUMENTS_PACKAGE:
            continue
        if normalize_filename_text(node_text(node)) != expected:
            continue
        resource_id = node.attrib.get("resource-id", "").lower()
        if node.attrib.get("class") == "android.widget.EditText" or "search" in resource_id:
            continue
        matches.append(node)
    return matches


def picker_safe_filename(filename: str, digest: str, *, max_chars: int = 36) -> str:
    """Keep Android/WeCom file-card names short enough for exact verification."""
    name = safe_file_name(Path(filename))
    if len(name) <= max_chars:
        return name
    suffix = Path(name).suffix[:12]
    stem_limit = max(8, max_chars - len(suffix) - 9)
    stem = Path(name).stem[:stem_limit].rstrip(" ._-") or "artifact"
    return f"{stem}-{digest[:8]}{suffix}"


def quoted_message_text(
    row: ET.Element,
    *,
    sender: str,
    body_nodes: list[ET.Element],
) -> str:
    """Recover visible quote-preview text without guessing from chat history.

    WeCom renders the current message in ``j1l`` and quote previews as other
    TextView descendants in the same message row. Resource IDs vary between
    Android releases, so this intentionally relies on that stable structural
    boundary while excluding sender, timestamps, read receipts, and the main
    message body.
    """
    body_texts = {node_text(node) for node in body_nodes if node_text(node)}
    skipped_unresourced_sender = False
    candidates: list[str] = []
    for node in row.iter("node"):
        text = node_text(node)
        if not text or text in body_texts or text in MESSAGE_CHROME_TEXT:
            continue
        resource = node.attrib.get("resource-id", "")
        if not resource and not skipped_unresourced_sender and text == sender:
            skipped_unresourced_sender = True
            continue
        if text == sender or MESSAGE_TIME_RE.fullmatch(text):
            continue
        if node.attrib.get("class", "") not in {"", "android.widget.TextView"}:
            continue
        candidates.append(text)
    return "\n".join(unique_nonempty(candidates))[:4000]


def message_row_sender(
    row: ET.Element,
    body_nodes: list[ET.Element],
) -> tuple[str, dict[str, str]]:
    """Resolve one message row's author without borrowing an adjacent label."""
    body_tops: list[int] = []
    for node in body_nodes:
        try:
            _, top, _, _ = parse_bounds(node.attrib.get("bounds", ""))
        except BridgeError:
            continue
        body_tops.append(top)
    body_top = min(body_tops) if body_tops else None
    candidates: list[tuple[str, str]] = []
    external_marker = False
    avatar_bounds = ""
    for node in row.iter("node"):
        resource = node.attrib.get("resource-id", "")
        text = node_text(node)
        bounds = node.attrib.get("bounds", "")
        if resource.endswith(":id/ja3") and not avatar_bounds:
            avatar_bounds = bounds
        if text in {"＠微信", "@微信"}:
            external_marker = True
            continue
        if not text or resource or text in MESSAGE_CHROME_TEXT or MESSAGE_TIME_RE.fullmatch(text):
            continue
        if node.attrib.get("class", "") not in {"", "android.widget.TextView"}:
            continue
        try:
            _, _, _, bottom = parse_bounds(bounds)
        except BridgeError:
            # Some older accessibility dumps omit bounds entirely. A label is
            # still safe when every body node in this exact row is likewise
            # unbounded; never accept an unbounded label beside bounded body
            # content because its geometric ownership cannot be proved.
            if body_top is not None:
                continue
        else:
            if body_top is not None and bottom > body_top + 2:
                continue
        candidate = (text, bounds)
        if candidate not in candidates:
            candidates.append(candidate)
    unique_labels = unique_nonempty(label for label, _ in candidates)
    sender = unique_labels[0] if len(unique_labels) == 1 else ""
    sender_bounds = next((bounds for label, bounds in candidates if label == sender), "")
    evidence = {
        "sender_identity_confidence": "visible_row_label" if sender else "unattributed_row",
        "sender_label_bounds": sender_bounds,
        "sender_avatar_bounds": avatar_bounds,
        "sender_external_marker": "true" if external_marker else "false",
        "sender_candidate_count": str(len(unique_labels)),
    }
    return sender, evidence


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
            conn.execute(
                "CREATE TABLE IF NOT EXISTS observed_messages ("
                "chat TEXT NOT NULL, fingerprint TEXT NOT NULL, direction TEXT NOT NULL, "
                "status TEXT NOT NULL, record_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL, "
                "PRIMARY KEY(chat, fingerprint))"
            )
            observed_columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(observed_messages)")
            }
            if "record_json" not in observed_columns:
                conn.execute(
                    "ALTER TABLE observed_messages ADD COLUMN "
                    "record_json TEXT NOT NULL DEFAULT '{}'"
                )

    @contextmanager
    def serialized(self, *, timeout_seconds: float | None = None) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        timeout = max(
            0.1,
            float(
                timeout_seconds
                if timeout_seconds is not None
                else self.config.get("serialization_timeout_seconds", 30.0)
            ),
        )
        deadline = time.monotonic() + timeout
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise BridgeError(
                            f"WECOM_ANDROID_BUSY: serialized GUI control exceeded {timeout:.1f}s"
                        ) from exc
                    time.sleep(0.1)
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

    def normalize_chat_surface(self, chat: str) -> ET.Element:
        """Return to the exact chat composer from a stale picker or attachment sheet."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android chat")
        for _ in range(6):
            package = self.current_package()
            if package == DOCUMENTS_PACKAGE:
                self.press_back()
                continue
            root = self.open_chat(chat)
            visible = {
                normalize_visible_text(node_text(node))
                for node in root.iter("node")
                if normalize_visible_text(node_text(node))
            }
            local_choice_open = "从本地文件选择" in visible or "从微盘选择" in visible
            confirmation_open = "发送给：" in visible and "发送" in visible
            attachment_sheet_open = (
                "文件" in visible
                and len(visible.intersection({"图片", "拍摄", "文档", "文件"})) >= 2
            )
            if local_choice_open or confirmation_open or attachment_sheet_open:
                self.press_back()
                continue
            composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
            if composers:
                return root
            self.press_back()
        raise BridgeError("WeCom exact chat composer could not be restored")

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

    def exact_mention_rows(
        self,
        root: ET.Element,
        mention: str,
        *,
        prefer_exact_decoration: bool = True,
    ) -> list[ET.Element]:
        matches = [
            node
            for node in root.iter("node")
            if node.attrib.get("package") == self.package
            and node.attrib.get("resource-id") == f"{self.package}:id/ic1"
            and mention_row_matches(node.attrib.get("text"), mention)
        ]
        if prefer_exact_decoration and len(matches) > 1:
            requested = normalize_mention_name(mention)
            exact = [
                node
                for node in matches
                if normalize_mention_name(node.attrib.get("text")) == requested
            ]
            if exact:
                return exact
        return matches

    def select_native_mention(
        self,
        chat: str,
        mention: str,
        *,
        expected_count: int,
        prefer_exact_decoration: bool = True,
    ) -> None:
        self.adb_shell("input", "text", "@")
        picker = self.mention_picker()
        matches = self.exact_mention_rows(
            picker,
            mention,
            prefer_exact_decoration=prefer_exact_decoration,
        )
        if len(matches) != 1:
            search = find_nodes(picker, resource_id=f"{self.package}:id/g7i", package=self.package)
            if not search:
                raise BridgeError("WeCom mention search is unavailable")
            self.tap_node(picker, search[-1])
            self.paste_text(mention)
            time.sleep(0.7)
            picker = self.mention_picker()
            matches = self.exact_mention_rows(
                picker,
                mention,
                prefer_exact_decoration=prefer_exact_decoration,
            )
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
        return self.component_record(key).get("status") in {"sent", "deduplicated"}

    def sent_file_content_record(
        self,
        chat: str,
        digest: str,
        *,
        exclude_key: str = "",
    ) -> dict[str, Any]:
        """Find an already delivered copy of the same bytes in one chat."""
        query = (
            "SELECT component_key, task_id, value_hash, details_json, updated_at "
            "FROM components WHERE chat = ? AND kind = 'file' AND status = 'sent' "
            "AND value_hash LIKE ?"
        )
        params: list[str] = [chat, f"{digest}:%"]
        if exclude_key:
            query += " AND component_key != ?"
            params.append(exclude_key)
        query += " ORDER BY updated_at DESC LIMIT 1"
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute(query, params).fetchone()
        if not row:
            return {}
        try:
            details = json.loads(str(row[3] or "{}"))
        except json.JSONDecodeError:
            details = {}
        return {
            "component_key": str(row[0] or ""),
            "task_id": str(row[1] or ""),
            "value_hash": str(row[2] or ""),
            "details": details if isinstance(details, dict) else {},
            "updated_at": str(row[4] or ""),
        }

    def component_record(self, key: str) -> dict[str, Any]:
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute(
                "SELECT status, details_json, updated_at FROM components WHERE component_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return {}
        try:
            details = json.loads(str(row[1] or "{}"))
        except json.JSONDecodeError:
            details = {}
        return {
            "status": str(row[0] or ""),
            "details": details if isinstance(details, dict) else {},
            "updated_at": str(row[2] or ""),
        }

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
        value_hash = text_component_value_hash(text, exact_mentions)
        key = self.component_key(task_id, chat, "text", value_hash)
        if self.component_sent(key):
            return {
                "ok": True,
                "duplicate": True,
                "sent_messages": [text],
                "sent_files": [],
                "mentioned_users": exact_mentions,
            }
        root = self.normalize_chat_surface(chat)
        composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
        if not composers:
            raise BridgeError("WeCom composer is not visible")
        if composer_text(composers[-1]):
            raise BridgeError("refusing to overwrite a non-empty WeCom draft")
        self.tap_node(root, composers[-1])
        try:
            time.sleep(0.4)
            selected_mentions: list[str] = []
            for index, mention in enumerate(exact_mentions):
                try:
                    self.select_native_mention(
                        chat,
                        mention,
                        expected_count=len(selected_mentions) + 1,
                        # The first name is the exact current sender. Context
                        # mentions without a transport decoration are optional
                        # and must remain ambiguous rather than tag the wrong
                        # internal/external identity.
                        prefer_exact_decoration=index == 0 or mention.endswith("@微信"),
                    )
                except BridgeError:
                    if index == 0:
                        raise
                    self.press_back()
                    self.ensure_chat_identity(chat)
                    continue
                selected_mentions.append(mention)
            self.paste_text((" " if selected_mentions else "") + text)
            root = self.wait_for_composer_message(
                chat,
                text,
                mention_count=len(selected_mentions),
            )
            if root is None:
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
                    details={"mentioned_users": selected_mentions},
                )
                return {
                    "ok": True,
                    "sent_messages": [text],
                    "sent_files": [],
                    "mentioned_users": selected_mentions,
                    "errors": [],
                }
        raise BridgeError("WeCom did not expose the sent text after commit")

    def send_text_resilient_locked(
        self,
        chat: str,
        text: str,
        *,
        task_id: str,
        mentions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Deliver text even when WeCom's native mention UI is temporarily brittle.

        The exact current sender is always attempted first. Optional secondary
        mentions are dropped before the primary mention, and plain text is the
        final fallback. Only failures proven to occur before send commit are
        eligible, preventing an uncertain post-commit retry from duplicating a
        message.
        """
        requested = validate_mentions(mentions or [])
        attempts: list[list[str]] = [requested]
        if len(requested) > 1:
            attempts.append(requested[:1])
        if requested:
            attempts.append([])
        unique_attempts: list[list[str]] = []
        for candidate in attempts:
            if candidate not in unique_attempts:
                unique_attempts.append(candidate)

        warnings: list[str] = []
        for candidate in unique_attempts:
            try:
                result = self.send_text_locked(
                    chat,
                    text,
                    task_id=task_id,
                    mentions=candidate,
                )
            except BridgeError as exc:
                if not candidate or not recoverable_native_mention_error(exc):
                    raise
                warnings.append(f"{type(exc).__name__}: {str(exc)[:300]}")
                continue
            if candidate != requested:
                requested_hash = text_component_value_hash(text, requested)
                requested_key = self.component_key(task_id, chat, "text", requested_hash)
                self.mark_component(
                    requested_key,
                    task_id=task_id,
                    chat=chat,
                    kind="text",
                    value_hash=requested_hash,
                    status="sent",
                    details={
                        "mentioned_users": candidate,
                        "requested_mentions": requested,
                        "mention_fallback": True,
                        "mention_warnings": warnings,
                    },
                )
            result["mention_warnings"] = warnings
            result["requested_mentions"] = requested
            return result
        raise BridgeError("WeCom text delivery exhausted native-mention fallbacks")

    def wait_for_composer_message(
        self,
        chat: str,
        text: str,
        *,
        mention_count: int = 0,
        timeout: float = 3.0,
    ) -> ET.Element | None:
        """Wait until accessibility exposes the exact Unicode clipboard paste."""
        deadline = time.monotonic() + max(0.1, timeout)
        while time.monotonic() < deadline:
            root = self.ensure_chat_identity(chat)
            composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
            if composers and composer_matches_message(
                composer_text(composers[-1]),
                text,
                mention_count=mention_count,
            ):
                return root
            time.sleep(0.2)
        return None

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
        # DocumentsUI search does not reliably index nested directories on
        # this device. Keep the picker-visible copy at the Download root;
        # the local hash directory remains the collision/deduplication guard.
        remote_name = picker_safe_filename(name, digest)
        remote_path = f"{REMOTE_STAGING}/{remote_name}"
        self.adb("push", str(local_copy), remote_path, timeout=180)
        self.adb_shell(
            "am",
            "broadcast",
            "-a",
            "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d",
            f"file://{remote_path}",
            timeout=20,
            check=False,
        )
        return resolved, digest, remote_path

    def wait_for_document_file(self, filename: str, *, timeout: float = 20.0) -> ET.Element:
        """Wait for DocumentsUI indexing, then use exact-name search as fallback."""
        deadline = time.monotonic() + timeout
        search_started = False
        while time.monotonic() < deadline:
            root = self.dump_hierarchy(attempts=2)
            matches = exact_document_file_nodes(root, filename)
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise BridgeError(f"expected one exact file in Android Download, found {len(matches)}")
            if not search_started and time.monotonic() + 3 < deadline:
                search_nodes = [
                    node
                    for node in root.iter("node")
                    if node.attrib.get("package") == DOCUMENTS_PACKAGE
                    and (
                        normalize_visible_text(node.attrib.get("content-desc")) in {"搜索", "Search"}
                        or "menu_search" in node.attrib.get("resource-id", "")
                    )
                ]
                if search_nodes:
                    self.tap_node(root, search_nodes[-1])
                    time.sleep(0.4)
                    search_root = self.dump_hierarchy(attempts=2)
                    editors = [
                        node
                        for node in search_root.iter("node")
                        if node.attrib.get("package") == DOCUMENTS_PACKAGE
                        and node.attrib.get("class") == "android.widget.EditText"
                    ]
                    if editors:
                        self.tap_node(search_root, editors[-1])
                        self.paste_text(filename)
                        search_started = True
            time.sleep(1.0)
        raise BridgeError("exact artifact did not appear in Android DocumentsUI after indexing/search")

    def wait_for_package(self, package: str, *, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.current_package() == package:
                return
            time.sleep(0.4)
        raise BridgeError(f"Android package did not become active: {package}")

    def send_file_locked(
        self,
        chat: str,
        path: Path,
        *,
        task_id: str,
        allow_visible_recovery: bool = False,
        force_resend: bool = False,
    ) -> dict[str, Any]:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise BridgeError(f"artifact does not exist: {resolved}")
        digest = sha256_file(resolved)
        original_filename = resolved.name
        key = self.component_key(task_id, chat, "file", f"{digest}:{original_filename}")
        if not force_resend and self.component_sent(key):
            return {"ok": True, "duplicate": True, "sent_messages": [], "sent_files": [str(resolved)]}
        prior = self.sent_file_content_record(chat, digest, exclude_key=key)
        if prior and not force_resend:
            self.mark_component(
                key,
                task_id=task_id,
                chat=chat,
                kind="file",
                value_hash=f"{digest}:{original_filename}",
                status="deduplicated",
                details={
                    "sha256": digest,
                    "size_bytes": resolved.stat().st_size,
                    "deduplicated_from_component": prior["component_key"],
                    "deduplicated_from_task": prior["task_id"],
                },
            )
            return {
                "ok": True,
                "duplicate": True,
                "deduplicated": True,
                "sent_messages": [],
                "sent_files": [str(resolved)],
                "errors": [],
            }
        resolved, digest, remote_path = self.stage_file(path)
        filename = Path(remote_path).name
        root = self.normalize_chat_surface(chat)
        component = self.component_record(key)
        if (
            component.get("status") == "committing" or allow_visible_recovery
        ) and (
            visible_file_card_matches(root, filename)
            or visible_file_card_matches(root, original_filename)
        ):
            self.mark_component(
                key,
                task_id=task_id,
                chat=chat,
                kind="file",
                value_hash=f"{digest}:{original_filename}",
                status="sent",
                details={
                    "size_bytes": resolved.stat().st_size,
                    "sha256": digest,
                    "display_name": filename,
                    "recovered_from_visible_card": True,
                    "legacy_display_name_checked": original_filename,
                },
            )
            return {
                "ok": True,
                "duplicate": True,
                "recovered": True,
                "sent_messages": [],
                "sent_files": [str(resolved)],
                "errors": [],
            }
        plus: list[ET.Element] = []
        # Prefer the right-side attachment control. Some builds reuse ``hvp``
        # for the left-side voice/keyboard toggle while ``j1v`` remains the
        # actual attachment button, so only use ``hvp`` as a true fallback.
        for resource_name in ("j1v", "hvp"):
            candidates = [
                node
                for node in find_nodes(
                    root,
                    resource_id=f"{self.package}:id/{resource_name}",
                    package=self.package,
                )
                if node.attrib.get("clickable") == "true"
            ]
            if candidates:
                plus = candidates
                break
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
        roots = [
            node
            for node in picker.iter("node")
            if node.attrib.get("package") == DOCUMENTS_PACKAGE
            and node.attrib.get("content-desc") == "显示根目录"
        ]
        if not roots:
            raise BridgeError("Android document root menu is unavailable")
        self.tap_node(picker, roots[-1])
        time.sleep(0.5)
        drawer = self.dump_hierarchy()
        downloads = find_nodes(drawer, text="下载内容", package=DOCUMENTS_PACKAGE)
        if len(downloads) != 1:
            raise BridgeError("Android Download root is unavailable or ambiguous")
        self.tap_node(drawer, downloads[0])
        time.sleep(0.8)
        self.wait_for_document_file(filename)
        current = self.dump_hierarchy(attempts=2)
        matches = exact_document_file_nodes(current, filename)
        if len(matches) != 1:
            raise BridgeError("exact artifact changed before picker commit")
        self.tap_node(current, matches[0])
        self.wait_for_package(self.package)
        time.sleep(1.0)
        confirmation = self.dump_hierarchy()
        if not validate_file_confirmation(confirmation, chat, filename):
            raise BridgeError("WeCom file confirmation did not match exact chat and artifact")
        send = find_nodes(confirmation, text="发送", package=self.package)
        self.mark_component(
            key,
            task_id=task_id,
            chat=chat,
            kind="file",
            value_hash=f"{digest}:{original_filename}",
            status="committing",
            details={
                "size_bytes": resolved.stat().st_size,
                "sha256": digest,
                "display_name": filename,
            },
        )
        self.tap_node(confirmation, send[-1])
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            time.sleep(1.0)
            current = self.ensure_chat_identity(chat)
            if visible_file_card_matches(current, filename):
                # A card appears before the upload has necessarily left the
                # local client. Require a short stable second observation and
                # reject visible retry/failure states before recording delivery.
                time.sleep(3.0)
                current = self.ensure_chat_identity(chat)
                visible = [normalize_visible_text(node.attrib.get("text")) for node in current.iter("node")]
                if not visible_file_card_matches(current, filename):
                    continue
                if any(marker in value for value in visible for marker in ("发送失败", "上传失败", "重试")):
                    raise BridgeError("WeCom reported an artifact upload failure")
                self.mark_component(
                    key,
                    task_id=task_id,
                    chat=chat,
                    kind="file",
                    value_hash=f"{digest}:{original_filename}",
                    status="sent",
                    details={
                        "size_bytes": resolved.stat().st_size,
                        "sha256": digest,
                        "display_name": filename,
                    },
                )
                return {"ok": True, "sent_messages": [], "sent_files": [str(resolved)], "errors": []}
        raise BridgeError("WeCom did not expose the uploaded artifact after commit")

    def delivery_status(
        self,
        chat: str,
        message: str,
        files: list[Path],
        *,
        task_id: str,
        mentions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Read the durable component ledger without touching the WeCom GUI."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android target")
        exact_mentions = validate_mentions(mentions or [])
        sent_messages: list[str] = []
        pending_messages: list[str] = []
        sent_files: list[str] = []
        pending_files: list[str] = []
        if message.strip():
            value_hash = text_component_value_hash(message, exact_mentions)
            key = self.component_key(task_id, chat, "text", value_hash)
            (sent_messages if self.component_sent(key) else pending_messages).append(message)
        for path in files:
            resolved = path.expanduser().resolve()
            if not resolved.is_file():
                pending_files.append(str(resolved))
                continue
            digest = sha256_file(resolved)
            key = self.component_key(task_id, chat, "file", f"{digest}:{resolved.name}")
            delivered = self.component_sent(key) or bool(
                self.sent_file_content_record(chat, digest, exclude_key=key)
            )
            (sent_files if delivered else pending_files).append(str(resolved))
        return {
            "ok": not pending_messages and not pending_files,
            "complete": not pending_messages and not pending_files,
            "transport": "wecom_android",
            "chat_id": f"gui:{chat}",
            "sent_messages": sent_messages,
            "pending_messages": pending_messages,
            "sent_files": sent_files,
            "pending_files": pending_files,
            "mentioned_users": exact_mentions if sent_messages else [],
        }

    def send(
        self,
        chat: str,
        message: str,
        files: list[Path],
        *,
        task_id: str,
        mentions: list[str] | None = None,
        allow_visible_file_recovery: bool = False,
        force_resend: bool = False,
    ) -> dict[str, Any]:
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android target")
        exact_mentions = validate_mentions(mentions or [])
        if exact_mentions and not message.strip():
            raise BridgeError("mentions require a text message")
        if not message.strip() and not files:
            raise BridgeError("send requires a message and/or artifact")
        with self.serialized(timeout_seconds=60.0):
            sent_messages: list[str] = []
            sent_files: list[str] = []
            mentioned_users: list[str] = []
            errors: list[dict[str, str]] = []
            if message.strip():
                try:
                    result = self.send_text_resilient_locked(
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
                    result = self.send_file_locked(
                        chat,
                        path,
                        task_id=task_id,
                        allow_visible_recovery=allow_visible_file_recovery,
                        force_resend=force_resend,
                    )
                    sent_files.extend(result.get("sent_files") or [])
                except Exception as exc:
                    errors.append(
                        {"kind": "file", "path": str(path), "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
                    )
                    try:
                        self.normalize_chat_surface(chat)
                    except Exception:
                        pass
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
            body_nodes: list[ET.Element] = []
            for node in row.iter("node"):
                text = node_text(node)
                if not text:
                    continue
                resource = node.attrib.get("resource-id", "")
                if resource.endswith(":id/j1l"):
                    body_nodes.append(node)
            body = "\n".join(unique_nonempty(node_text(node) for node in body_nodes))
            if not body:
                continue
            sender, sender_evidence = message_row_sender(row, body_nodes)
            sender_is_wechat = sender_evidence["sender_external_marker"] == "true"
            quote_text = quoted_message_text(row, sender=sender, body_nodes=body_nodes)
            avatar_bounds = sender_evidence.get("sender_avatar_bounds", "")
            avatar_on_left = False
            try:
                left, _, right, _ = parse_bounds(avatar_bounds)
                avatar_on_left = (left + right) // 2 < 540
            except BridgeError:
                pass
            direction = "inbound" if sender or avatar_on_left else "outbound"
            fingerprint = short_hash(f"{direction}\0{sender}\0{body}\0{quote_text}", 64)
            records.append(
                {
                    "fingerprint": fingerprint,
                    "direction": direction,
                    "sender": sender,
                    "mention_name": f"{sender}@微信" if sender and sender_is_wechat else sender,
                    "body": body,
                    "quote_text": quote_text,
                    **sender_evidence,
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

    def observed_message_statuses(self, chat: str) -> dict[str, str]:
        with sqlite3.connect(self.state_db) as conn:
            rows = conn.execute(
                "SELECT fingerprint, status FROM observed_messages WHERE chat = ?",
                (chat,),
            ).fetchall()
        return {str(fingerprint): str(status) for fingerprint, status in rows}

    def mark_observed_message(self, chat: str, record: dict[str, str], status: str) -> None:
        if status not in {"seeded", "observed", "pending", "ingested"}:
            raise BridgeError(f"invalid observed-message status: {status}")
        fingerprint = str(record.get("fingerprint") or "")
        if not fingerprint:
            raise BridgeError("observed message is missing a fingerprint")
        with sqlite3.connect(self.state_db) as conn:
            conn.execute(
                "INSERT INTO observed_messages("
                "chat, fingerprint, direction, status, record_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(chat, fingerprint) DO UPDATE SET "
                "direction = excluded.direction, "
                "status = CASE WHEN observed_messages.status = 'ingested' "
                "THEN 'ingested' ELSE excluded.status END, "
                "record_json = CASE WHEN excluded.record_json = '{}' "
                "THEN observed_messages.record_json ELSE excluded.record_json END, "
                "updated_at = excluded.updated_at",
                (
                    chat,
                    fingerprint,
                    str(record.get("direction") or "unknown"),
                    status,
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    now_iso(),
                ),
            )

    def seed_observed_fingerprints(self, chat: str, fingerprints: list[str]) -> None:
        timestamp = now_iso()
        with sqlite3.connect(self.state_db) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO observed_messages("
                "chat, fingerprint, direction, status, record_json, updated_at) "
                "VALUES (?, ?, 'unknown', 'seeded', '{}', ?)",
                [(chat, fingerprint, timestamp) for fingerprint in fingerprints if fingerprint],
            )

    def pending_observed_records(self, chat: str) -> list[dict[str, str]]:
        with sqlite3.connect(self.state_db) as conn:
            rows = conn.execute(
                "SELECT fingerprint, record_json FROM observed_messages "
                "WHERE chat = ? AND status = 'pending' ORDER BY updated_at, rowid",
                (chat,),
            ).fetchall()
        result: list[dict[str, str]] = []
        for fingerprint, raw_record in rows:
            try:
                record = json.loads(str(raw_record or "{}"))
            except json.JSONDecodeError:
                record = {}
            if not isinstance(record, dict) or not str(record.get("body") or "").strip():
                record = self.recover_pending_record_from_history(chat, str(fingerprint)) or {}
            if not isinstance(record, dict) or not str(record.get("body") or "").strip():
                continue
            record["fingerprint"] = str(fingerprint)
            result.append({str(key): str(value) for key, value in record.items()})
        return result

    def recover_pending_record_from_history(
        self, chat: str, fingerprint: str
    ) -> dict[str, str] | None:
        if not self.history_db.is_file():
            return None
        account = str(self.config.get("account_id") or "external-gui").strip() or "external-gui"
        canonical_chat = f"wecom:{account}:group:{short_hash(f'gui:{chat}', 12)}"
        try:
            with sqlite3.connect(self.history_db) as conn:
                rows = conn.execute(
                    "SELECT sender_display, body FROM messages WHERE chat = ? "
                    "AND direction = 'inbound' AND processed_at IS NULL ORDER BY id",
                    (canonical_chat,),
                ).fetchall()
        except sqlite3.Error:
            return None
        separator = "\n\nQuoted message:\n"
        for sender_value, request_value in rows:
            sender = str(sender_value or "").strip()
            request = str(request_value or "").strip()
            body, separator_found, quote = request.partition(separator)
            quote_text = quote if separator_found else ""
            candidate = short_hash(f"inbound\0{sender}\0{body}\0{quote_text}", 64)
            if candidate != fingerprint:
                continue
            return {
                "fingerprint": fingerprint,
                "direction": "inbound",
                "sender": sender,
                "mention_name": sender,
                "body": body,
                "quote_text": quote_text,
            }
        return None

    def record_exists_in_history(self, chat: str, record: dict[str, str]) -> bool:
        if not self.history_db.is_file():
            return False
        body = str(record.get("body") or "").strip()
        quote = str(record.get("quote_text") or "").strip()
        request = f"{body}\n\nQuoted message:\n{quote}" if quote else body
        sender = str(record.get("sender") or "").strip()
        account = str(self.config.get("account_id") or "external-gui").strip() or "external-gui"
        canonical_chat = f"wecom:{account}:group:{short_hash(f'gui:{chat}', 12)}"
        try:
            with sqlite3.connect(self.history_db) as conn:
                row = conn.execute(
                    "SELECT 1 FROM messages WHERE chat = ? AND direction = 'inbound' "
                    "AND sender_display = ? AND body = ? AND processed_at IS NOT NULL LIMIT 1",
                    (canonical_chat, sender, request),
                ).fetchone()
        except sqlite3.Error:
            return False
        return bool(row)

    def build_event(self, chat: str, record: dict[str, str]) -> dict[str, Any]:
        # Stable IDs let pending ingress retry without creating a second task.
        event_key = short_hash(f"{chat}\0{record.get('fingerprint')}", 24)
        sender = str(record.get("sender") or "unknown")
        sender_confidence = str(record.get("sender_identity_confidence") or "unknown")
        sender_identity = sender if sender_confidence == "visible_row_label" else f"unattributed:{event_key}"
        return {
            "transport": "wecom",
            "transport_channel": "wecom_android",
            "account_id": str(self.config.get("account_id") or "external-gui"),
            "message_id": f"android:{event_key}",
            "chat_id": f"gui:{chat}",
            "chat_type": "group",
            "sender_userid": f"android-member:{short_hash(sender_identity, 24)}",
            "sender_display": sender,
            "sender_mention": (
                str(record.get("mention_name") or sender)
                if sender_confidence == "visible_row_label"
                else ""
            ),
            "sender_identity_confidence": sender_confidence,
            "sender_evidence": {
                key: str(record.get(key) or "")
                for key in (
                    "sender_label_bounds",
                    "sender_avatar_bounds",
                    "sender_external_marker",
                    "sender_candidate_count",
                )
            },
            "create_time": int(time.time()),
            "msgtype": "text",
            "text": str(record.get("body") or ""),
            "quote_text": str(record.get("quote_text") or ""),
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
        with self.serialized(timeout_seconds=30.0):
            root = self.open_chat(chat)
            records = self.parse_messages(root)
            sequence = [record["fingerprint"] for record in records]
            previous = self.load_snapshot(chat)
            if previous is None:
                for record in records:
                    self.mark_observed_message(chat, record, "seeded")
                self.save_snapshot(chat, sequence)
                return {"ok": True, "chat": chat, "seeded": len(sequence), "messages": [], "processed": 0}

            statuses = self.observed_message_statuses(chat)
            migrating = not statuses and bool(previous)
            if migrating:
                self.seed_observed_fingerprints(chat, previous)
                statuses = self.observed_message_statuses(chat)
                # Sequence-only versions could checkpoint a changed viewport
                # before enqueueing it. Recover only exact inbound rows absent
                # from the durable history database.
                for record in records:
                    fingerprint = str(record.get("fingerprint") or "")
                    if record.get("direction") != "inbound" or fingerprint not in statuses:
                        continue
                    status = "ingested" if self.record_exists_in_history(chat, record) else "pending"
                    self.mark_observed_message(chat, record, status)
                    statuses[fingerprint] = status
            delta, overlap = sequence_delta(previous, sequence)
            for record in records:
                fingerprint = str(record.get("fingerprint") or "")
                if fingerprint in statuses:
                    continue
                status = "pending" if record.get("direction") == "inbound" else "observed"
                self.mark_observed_message(chat, record, status)
                statuses[fingerprint] = status
            pending_by_fingerprint = {
                str(record.get("fingerprint") or ""): record
                for record in self.pending_observed_records(chat)
            }
            # Prefer the fresh UI record when it is still visible because it
            # carries the exact native mention spelling. Persisted records keep
            # the message actionable after overlapping rows scroll off-screen.
            for record in records:
                fingerprint = str(record.get("fingerprint") or "")
                if (
                    record.get("direction") == "inbound"
                    and statuses.get(fingerprint) == "pending"
                ):
                    pending_by_fingerprint[fingerprint] = record
            pending_inbound = list(pending_by_fingerprint.values())
            ingested: list[dict[str, Any]] = []
            pending_replies: list[tuple[str, list[str], str]] = []
            if enqueue:
                for record in pending_inbound:
                    event = self.build_event(chat, record)
                    result = self.invoke_ingest(event)
                    ingested.append(result)
                    self.mark_observed_message(chat, record, "ingested")
                    statuses[str(record.get("fingerprint") or "")] = "ingested"
                    response = str(result.get("reply") or result.get("ack") or "").strip()
                    if response:
                        reply_mentions = result.get("reply_mentions")
                        if not isinstance(reply_mentions, list):
                            fallback_mention = str(
                                record.get("mention_name") or record.get("sender") or ""
                            )
                            reply_mentions = [fallback_mention] if fallback_mention else []
                        pending_replies.append(
                            (
                                response,
                                [str(value) for value in reply_mentions if str(value).strip()],
                                f"ingress:{event['message_id']}",
                            )
                        )
            # Checkpoint ingress before any write. An uncertain reply send must
            # never replay the original request after restart.
            self.save_snapshot(chat, sequence)
            sent_replies: list[str] = []
            reply_errors: list[dict[str, str]] = []
            for response, mentions, task_id in pending_replies:
                try:
                    sent = self.send_text_resilient_locked(
                        chat,
                        response,
                        task_id=task_id,
                        mentions=mentions,
                    )
                    sent_replies.extend(sent.get("sent_messages") or [])
                except Exception as exc:
                    reply_errors.append(
                        {
                            "sender": ", ".join(mentions),
                            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                        }
                    )
            return {
                "ok": not reply_errors,
                "chat": chat,
                "overlap": overlap,
                "viewport_changed_without_overlap": bool(overlap == 0 and previous and sequence),
                "processed": len(ingested),
                "pending": 0 if enqueue else len(pending_inbound),
                "messages": pending_inbound,
                "ingested": ingested,
                "replied": len(sent_replies),
                "reply_errors": reply_errors,
            }

    def poll_cycle(self) -> dict[str, Any]:
        now = time.monotonic()
        due = [chat for chat in self.target_groups if self.load_snapshot(chat) is None]
        unread: list[str] = []
        if not due:
            with self.serialized(timeout_seconds=5.0):
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
                with self.serialized(timeout_seconds=5.0):
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
            if self.path not in {"/v1/send", "/v1/delivery-status"}:
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
                if self.path == "/v1/delivery-status":
                    result = bridge.delivery_status(
                        chat,
                        str(payload.get("message") or ""),
                        [Path(str(item)) for item in raw_files],
                        task_id=str(payload.get("task_id") or "api")[:256] or "api",
                        mentions=mentions,
                    )
                else:
                    result = bridge.send(
                        chat,
                        str(payload.get("message") or ""),
                        [Path(str(item)) for item in raw_files],
                        task_id=str(payload.get("task_id") or "api")[:256] or "api",
                        mentions=mentions,
                        allow_visible_file_recovery=bool(payload.get("allow_visible_file_recovery")),
                        force_resend=bool(payload.get("force_resend")),
                    )
                # A partial send is a valid transport response. The caller uses
                # the component ledger to retry only missing components.
                self.write_json(HTTPStatus.OK, result)
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
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

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
    send.add_argument(
        "--force-resend",
        action="store_true",
        help="Deliberately resend identical file bytes already delivered to this chat.",
    )
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
                        force_resend=args.force_resend,
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
