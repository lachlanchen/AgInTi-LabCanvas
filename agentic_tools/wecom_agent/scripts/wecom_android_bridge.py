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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterator
from urllib import parse
from xml.etree import ElementTree as ET
import zlib


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
WECOM_LAUNCH_COMPONENT = ".launch.LaunchSplashActivity"
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
QUOTE_RESOURCE_RE = re.compile(r"(?:quote|reply|refer|引用|回复)", re.IGNORECASE)
MESSAGE_CHROME_TEXT = {
    "＠微信",
    "@微信",
    "已读",
    "未读",
    "发送中",
    "重新发送",
    "撤回",
}
MESSAGE_ROW_RESOURCE_SUFFIX = ":id/eyy"
ARTICLE_CARD_RESOURCE_SUFFIX = ":id/mww"
ARTICLE_CARD_KIND = "wechat_article_card"
MERGED_HISTORY_TITLE_RESOURCE_SUFFIX = ":id/jb2"
MERGED_HISTORY_BODY_RESOURCE_SUFFIX = ":id/jb1"
MERGED_HISTORY_KIND = "merged_chat_history"
IMAGE_BUBBLE_RESOURCE_SUFFIX = ":id/kfb"
IMAGE_KIND = "image"
IMAGE_VIEWER_RESOURCE_SUFFIX = ":id/nxh"
DOCUMENT_FILENAME_RESOURCE_SUFFIX = ":id/j2k"
DOCUMENT_SIZE_RESOURCE_SUFFIX = ":id/j2g"
DOCUMENT_KIND = "document"
INBOUND_FILECACHE_ROOT = "/sdcard/Android/data/com.tencent.wework/files/filecache"
ANR_MESSAGE_MARKERS = ("没有响应", "isn't responding", "is not responding")
ANR_WAIT_LABELS = {"等待", "Wait", "WAIT"}
SECURITY_GATE_LABELS = {
    "登录企业微信",
    "扫码登录",
    "安全验证",
    "设备验证",
    "请完成验证",
}
SURFACE_ERROR_MARKERS = (
    "chat list is not visible",
    "exact allowlisted wecom chat is not visible",
    "exact chat composer could not be restored",
    "could not read android ui hierarchy",
    "wecom did not reach the foreground",
    "wecom changed chat",
)


class BridgeError(RuntimeError):
    """A fail-closed Android transport error."""


@dataclass(frozen=True)
class RawScreenshot:
    width: int
    height: int
    rgba: bytes


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


def parse_raw_screencap(payload: bytes) -> RawScreenshot:
    """Decode Android's dependency-free raw RGBA screencap format."""
    if len(payload) < 12:
        raise BridgeError("Android raw screenshot is truncated")
    width, height, pixel_format = struct.unpack_from("<III", payload, 0)
    if width <= 0 or height <= 0 or width > 10000 or height > 10000:
        raise BridgeError("Android raw screenshot dimensions are invalid")
    if pixel_format not in {1, 2}:
        raise BridgeError(f"unsupported Android screenshot pixel format: {pixel_format}")
    pixel_bytes = width * height * 4
    if len(payload) == pixel_bytes + 12:
        header_bytes = 12
    elif len(payload) == pixel_bytes + 16:
        # Newer Android builds add a four-byte color-space field.
        header_bytes = 16
    else:
        raise BridgeError(
            f"Android raw screenshot has unexpected size: {len(payload)} for {width}x{height}"
        )
    return RawScreenshot(width=width, height=height, rgba=payload[header_bytes:])


def crop_raw_screenshot(
    screenshot: RawScreenshot,
    bounds: str | tuple[int, int, int, int],
) -> RawScreenshot:
    x1, y1, x2, y2 = parse_bounds(bounds) if isinstance(bounds, str) else bounds
    x1 = max(0, min(screenshot.width, x1))
    x2 = max(0, min(screenshot.width, x2))
    y1 = max(0, min(screenshot.height, y1))
    y2 = max(0, min(screenshot.height, y2))
    if x2 <= x1 or y2 <= y1:
        raise BridgeError("image bubble lies outside the Android screenshot")
    row_bytes = screenshot.width * 4
    cropped_row_bytes = (x2 - x1) * 4
    rows = []
    for y in range(y1, y2):
        start = y * row_bytes + x1 * 4
        rows.append(screenshot.rgba[start : start + cropped_row_bytes])
    return RawScreenshot(width=x2 - x1, height=y2 - y1, rgba=b"".join(rows))


def screenshot_region_sha256(screenshot: RawScreenshot, bounds: str) -> str:
    cropped = crop_raw_screenshot(screenshot, bounds)
    digest = hashlib.sha256()
    digest.update(struct.pack("<II", cropped.width, cropped.height))
    digest.update(cropped.rgba)
    return digest.hexdigest()


def screenshot_region_visual_id(screenshot: RawScreenshot, bounds: str) -> str:
    """Return a compact visual identity tolerant of viewport repositioning."""
    cropped = crop_raw_screenshot(screenshot, bounds)
    columns = 17
    rows = 16
    luminance: list[list[int]] = []
    coarse_color = bytearray()
    for row in range(rows):
        y = min(cropped.height - 1, ((row * 2 + 1) * cropped.height) // (rows * 2))
        values: list[int] = []
        for column in range(columns):
            x = min(
                cropped.width - 1,
                ((column * 2 + 1) * cropped.width) // (columns * 2),
            )
            offset = (y * cropped.width + x) * 4
            red, green, blue = cropped.rgba[offset : offset + 3]
            values.append((299 * red + 587 * green + 114 * blue) // 1000)
            coarse_color.extend((red >> 4, green >> 4, blue >> 4))
        luminance.append(values)
    bits = [
        luminance[row][column] > luminance[row][column + 1]
        for row in range(rows)
        for column in range(columns - 1)
    ]
    packed = bytearray()
    for offset in range(0, len(bits), 8):
        value = 0
        for bit_index, enabled in enumerate(bits[offset : offset + 8]):
            if enabled:
                value |= 1 << (7 - bit_index)
        packed.append(value)
    color_digest = hashlib.sha256(bytes(coarse_color)).hexdigest()[:16]
    return f"{packed.hex()}-{color_digest}"


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def encode_rgba_png(screenshot: RawScreenshot) -> bytes:
    row_bytes = screenshot.width * 4
    scanlines = b"".join(
        b"\x00" + screenshot.rgba[offset : offset + row_bytes]
        for offset in range(0, len(screenshot.rgba), row_bytes)
    )
    header = struct.pack(">IIBBBBB", screenshot.width, screenshot.height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, 6))
        + _png_chunk(b"IEND", b"")
    )


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


def hierarchy_visible_texts(root: ET.Element) -> set[str]:
    return {
        text
        for node in root.iter("node")
        if (text := normalize_visible_text(node_text(node)))
    }


def hierarchy_packages(root: ET.Element) -> set[str]:
    return {
        package
        for node in root.iter("node")
        if (package := str(node.attrib.get("package") or "").strip())
    }


def is_anr_dialog(root: ET.Element) -> bool:
    texts = hierarchy_visible_texts(root)
    return any(
        marker.casefold() in text.casefold()
        for marker in ANR_MESSAGE_MARKERS
        for text in texts
    ) and bool(texts.intersection(ANR_WAIT_LABELS))


def is_security_gate(root: ET.Element) -> bool:
    return bool(hierarchy_visible_texts(root).intersection(SECURITY_GATE_LABELS))


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


def incomplete_native_mention_draft(value: Any) -> bool:
    """Return whether a composer contains only interrupted native mentions.

    WeCom exposes selected mentions as private marker tokens. If the process is
    interrupted while opening the next mention picker, the composer can be
    left as ``<mention-token>@``. That residue is automation-owned structure,
    not human prose, and is safe to clear on the next guarded send.
    """
    raw = str(value or "")
    if not MENTION_TOKEN_RE.search(raw):
        return False
    residue = MENTION_TOKEN_RE.sub("", raw)
    return bool(re.fullmatch(r"[\s@＠,，、:：;；]*", residue))


def chat_title_matches(title: str, chat: str) -> bool:
    return bool(re.fullmatch(re.escape(chat) + r"(?:\(\d+\))?", normalize_visible_text(title)))


def sequence_delta(previous: list[str], current: list[str]) -> tuple[list[str], int]:
    """Return items appended after the largest old-suffix/new-prefix overlap."""
    maximum = min(len(previous), len(current))
    for overlap in range(maximum, 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:], overlap
    return current, 0


def coalesce_sender_records(
    records: list[dict[str, str]],
) -> list[list[dict[str, str]]]:
    """Keep a contiguous same-sender burst in one ordered agent turn."""
    batches: list[list[dict[str, str]]] = []
    for record in records:
        sender = str(record.get("sender") or "").strip()
        if batches:
            previous_sender = str(batches[-1][-1].get("sender") or "").strip()
            if (
                sender
                and sender == previous_sender
                and len(batches[-1]) < 8
            ):
                batches[-1].append(record)
                continue
        batches.append([record])
    return batches


def safe_file_name(path: Path) -> str:
    name = path.name.strip()
    if not name or name in {".", ".."} or len(name.encode("utf-8")) > 240:
        raise BridgeError("artifact filename is empty or too long")
    if any(character in name for character in ("/", "\\", "\x00", "\n", "\r")):
        raise BridgeError("artifact filename contains unsafe characters")
    return name


def approximate_display_size_bytes(value: Any) -> int | None:
    """Convert a compact native file-card size such as ``5.7M`` to bytes."""
    text = normalize_visible_text(value).upper().replace("IB", "B")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGT]?)(?:B)?", text)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {
        "": 1,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
    }[match.group(2)]
    return int(number * multiplier)


def display_size_matches(actual_bytes: int, displayed: Any) -> bool:
    expected = approximate_display_size_bytes(displayed)
    if expected is None:
        return True
    # Native cards round aggressively (for example 5.7M for 5,948,623 bytes).
    tolerance = max(64 * 1024, int(expected * 0.12))
    return abs(int(actual_bytes) - expected) <= tolerance


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def write_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
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
        "history_scan_seconds": bounded_float(
            existing.get("history_scan_seconds"), 180.0, 60.0, 3600.0
        ),
        "history_scan_pages": bounded_int(
            existing.get("history_scan_pages"), 3, 0, 8
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

    def visible_text(node: ET.Element) -> str:
        # Some WeCom builds expose the quote preview through content-desc
        # instead of text, especially after a quoted card is collapsed.
        return normalize_visible_text(
            node.attrib.get("text") or node.attrib.get("content-desc")
        )

    def usable(text: str) -> bool:
        return bool(
            text
            and text not in body_texts
            and text not in MESSAGE_CHROME_TEXT
            and text != sender
            and not MESSAGE_TIME_RE.fullmatch(text)
        )

    # Prefer explicitly marked quote/reply subtrees. This prevents a
    # collapsed quote from being mistaken for unrelated row chrome and keeps
    # the author/content order emitted by the native client.
    explicit: list[str] = []
    for node in row.iter("node"):
        resource = node.attrib.get("resource-id", "")
        if not QUOTE_RESOURCE_RE.search(resource):
            continue
        text = visible_text(node)
        if usable(text):
            explicit.append(text)
        for child in node.iter("node"):
            child_text = visible_text(child)
            if usable(child_text):
                explicit.append(child_text)
    if explicit:
        return "\n".join(unique_nonempty(explicit))[:4000]

    skipped_unresourced_sender = False
    candidates: list[str] = []
    for node in row.iter("node"):
        text = visible_text(node)
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
        self.history_scan_seconds = bounded_float(
            config.get("history_scan_seconds"), 180.0, 60.0, 3600.0
        )
        self.history_scan_pages = bounded_int(
            config.get("history_scan_pages"), 3, 0, 8
        )
        self._next_reconcile_at = 0.0
        # Reconcile both chat tails immediately, but defer the more expensive
        # multi-page history walk so a restart becomes responsive quickly.
        self._next_history_scan_at = time.monotonic() + self.history_scan_seconds
        self._history_scan_cursor = 0
        self._stop = threading.Event()
        self._health_lock = threading.Lock()
        self._poll_health: dict[str, Any] = {
            "started_at": now_iso(),
            "last_poll_attempt_at": "",
            "last_poll_success_at": "",
            "last_poll_error": "",
            "poll_in_progress": False,
            "consecutive_poll_failures": 0,
            "last_recovery_at": "",
            "last_recovery_action": "",
        }
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
                "retry_after TEXT NOT NULL DEFAULT '', failure_count INTEGER NOT NULL DEFAULT 0, "
                "last_error TEXT NOT NULL DEFAULT '', "
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
            if "retry_after" not in observed_columns:
                conn.execute(
                    "ALTER TABLE observed_messages ADD COLUMN "
                    "retry_after TEXT NOT NULL DEFAULT ''"
                )
            if "failure_count" not in observed_columns:
                conn.execute(
                    "ALTER TABLE observed_messages ADD COLUMN "
                    "failure_count INTEGER NOT NULL DEFAULT 0"
                )
            if "last_error" not in observed_columns:
                conn.execute(
                    "ALTER TABLE observed_messages ADD COLUMN "
                    "last_error TEXT NOT NULL DEFAULT ''"
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

    def capture_raw_screenshot(self) -> RawScreenshot:
        process = self.run(
            ["adb", "-s", self.serial, "exec-out", "screencap"],
            timeout=30,
            check=True,
            text=False,
        )
        return parse_raw_screencap(bytes(process.stdout))

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
        try:
            root = self.dump_hierarchy(attempts=1)
        except BridgeError:
            root = None
        if root is not None and self.package in hierarchy_packages(root) and not is_anr_dialog(root):
            return
        component = str(
            self.config.get("launch_component")
            or f"{self.package}/{WECOM_LAUNCH_COMPONENT}"
        )
        self.adb_shell("am", "start", "-n", component, timeout=30)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                root = self.dump_hierarchy(attempts=1)
            except BridgeError:
                time.sleep(0.5)
                continue
            if is_anr_dialog(root):
                self.dismiss_anr_dialog(root)
                continue
            if self.package in hierarchy_packages(root):
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

    def dismiss_anr_dialog(self, root: ET.Element) -> bool:
        """Choose Android's non-destructive Wait action for a WeCom ANR."""
        if not is_anr_dialog(root):
            return False
        wait_nodes = [
            node
            for node in root.iter("node")
            if normalize_visible_text(node_text(node)) in ANR_WAIT_LABELS
            and node.attrib.get("clickable") == "true"
        ]
        if len(wait_nodes) != 1:
            raise BridgeError("WeCom ANR dialog does not expose one exact Wait action")
        self.tap_node(root, wait_nodes[0])
        self.record_recovery("anr_wait")
        time.sleep(2.0)
        return True

    def restart_wecom_preserving_session(self, *, reason: str) -> ET.Element:
        """Restart only the app process; never clear data or alter the account."""
        self.adb_shell("am", "force-stop", self.package, check=False)
        time.sleep(1.0)
        component = str(
            self.config.get("launch_component")
            or f"{self.package}/{WECOM_LAUNCH_COMPONENT}"
        )
        self.adb_shell("am", "start", "-n", component, timeout=30)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                root = self.dump_hierarchy(attempts=1)
            except BridgeError:
                time.sleep(0.6)
                continue
            if is_anr_dialog(root):
                self.dismiss_anr_dialog(root)
                continue
            if is_security_gate(root):
                raise BridgeError("WeCom restart reached a login or security-verification gate")
            if self.package in hierarchy_packages(root):
                self.record_recovery(f"app_restart:{reason}")
                return root
            time.sleep(0.6)
        raise BridgeError("WeCom app restart did not restore a readable native surface")

    def record_poll_attempt(self) -> None:
        with self._health_lock:
            self._poll_health.update(
                {
                    "last_poll_attempt_at": now_iso(),
                    "poll_in_progress": True,
                }
            )

    def record_poll_success(self) -> None:
        with self._health_lock:
            self._poll_health.update(
                {
                    "last_poll_attempt_at": now_iso(),
                    "last_poll_success_at": now_iso(),
                    "last_poll_error": "",
                    "poll_in_progress": False,
                    "consecutive_poll_failures": 0,
                }
            )

    def record_poll_failure(self, error: str) -> None:
        with self._health_lock:
            self._poll_health.update(
                {
                    "last_poll_attempt_at": now_iso(),
                    "last_poll_error": normalize_visible_text(error)[:500],
                    "poll_in_progress": False,
                    "consecutive_poll_failures": int(
                        self._poll_health.get("consecutive_poll_failures") or 0
                    )
                    + 1,
                }
            )

    def record_recovery(self, action: str) -> None:
        with self._health_lock:
            self._poll_health.update(
                {
                    "last_recovery_at": now_iso(),
                    "last_recovery_action": normalize_visible_text(action)[:160],
                }
            )

    def poll_health_snapshot(self) -> dict[str, Any]:
        with self._health_lock:
            health = dict(self._poll_health)
        interval = bounded_float(self.config.get("poll_seconds"), 6.0, 2.0, 120.0)
        reference = (
            health.get("last_poll_attempt_at")
            or health.get("started_at")
            or ""
        )
        stale = False
        try:
            reference_time = datetime.fromisoformat(str(reference))
        except ValueError:
            reference_time = None
        if reference_time is not None:
            stale = (datetime.now() - reference_time).total_seconds() > max(
                180.0,
                interval * 20.0,
            )
        failures = int(health.get("consecutive_poll_failures") or 0)
        health["poll_stale"] = stale
        health["poll_healthy"] = failures < 2 and not stale
        return health

    @staticmethod
    def surface_failure_text(payload: Any) -> str:
        text = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False, sort_keys=True)
        )
        lowered = text.casefold()
        return (
            text
            if any(marker.casefold() in lowered for marker in SURFACE_ERROR_MARKERS)
            else ""
        )

    def recover_transport_surface(self, *, reason: str) -> dict[str, Any]:
        """Return to the chat list, restarting WeCom once if navigation is wedged."""
        try:
            root = self.open_chat_list(allow_restart=False)
            self.record_recovery(f"navigation:{reason}")
            return {"ok": True, "action": "navigation", "visible_chat": visible_chat_title(root)}
        except BridgeError as first_error:
            self.restart_wecom_preserving_session(reason=reason)
            root = self.open_chat_list(allow_restart=False)
            return {
                "ok": True,
                "action": "app_restart",
                "first_error": str(first_error)[:300],
                "visible_chat": visible_chat_title(root),
            }

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
            voice_prompts = find_nodes(
                root,
                resource_id=f"{self.package}:id/j26",
                package=self.package,
            )
            voice_toggles = [
                node
                for node in find_nodes(
                    root,
                    resource_id=f"{self.package}:id/hvp",
                    package=self.package,
                )
                if node.attrib.get("clickable") == "true"
            ]
            if voice_prompts and voice_toggles:
                # A valid chat can reopen in voice-input mode. Switch the same
                # exact chat back to its text composer instead of backing out to
                # the conversation list and losing the attachment target.
                self.tap_node(root, voice_toggles[-1])
                deadline = time.monotonic() + 4.0
                while time.monotonic() < deadline:
                    time.sleep(0.25)
                    restored = self.dump_hierarchy(attempts=2)
                    if not chat_title_matches(visible_chat_title(restored), chat):
                        break
                    composers = find_nodes(
                        restored,
                        resource_id=f"{self.package}:id/j28",
                        package=self.package,
                    )
                    if composers:
                        return restored
                continue
            self.press_back()
        raise BridgeError("WeCom exact chat composer could not be restored")

    def open_chat(self, chat: str) -> ET.Element:
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android chat")
        for phase in range(2):
            self.launch_wecom()
            for _ in range(8):
                root = self.dump_hierarchy()
                if self.dismiss_anr_dialog(root):
                    continue
                if is_security_gate(root):
                    raise BridgeError("WeCom is waiting at a login or security-verification gate")
                if chat_title_matches(visible_chat_title(root), chat):
                    return root
                rows = find_nodes(
                    root,
                    text=chat,
                    resource_id=f"{self.package}:id/iql",
                    package=self.package,
                )
                if rows:
                    self.tap_node(root, rows[0])
                    # External-group chats can take several seconds to replace
                    # the message list on older Android devices.
                    deadline = time.monotonic() + 6.0
                    while time.monotonic() < deadline:
                        time.sleep(0.4)
                        opened = self.dump_hierarchy(attempts=2)
                        if self.dismiss_anr_dialog(opened):
                            continue
                        if is_security_gate(opened):
                            raise BridgeError(
                                "WeCom is waiting at a login or security-verification gate"
                            )
                        if chat_title_matches(visible_chat_title(opened), chat):
                            return opened
                        if self.package not in hierarchy_packages(opened):
                            break
                    # Fail closed on a genuinely wrong chat, but return to the
                    # list and retry rather than abandoning the whole send.
                    self.press_back()
                    continue
                if DOCUMENTS_PACKAGE in hierarchy_packages(root):
                    self.press_back()
                    continue
                if self.package not in hierarchy_packages(root):
                    self.launch_wecom()
                else:
                    # This also closes the native article/document viewer.
                    self.press_back()
            if phase == 0:
                self.restart_wecom_preserving_session(reason=f"open_chat:{chat}")
        raise BridgeError(f"exact allowlisted WeCom chat is not visible: {chat}")

    def move_chat_to_live_tail(
        self,
        chat: str,
        root: ET.Element,
        *,
        max_swipes: int = 4,
    ) -> ET.Element:
        """Move an exact chat to its newest viewport before reading messages."""
        has_message_rows = any(
            node.attrib.get("resource-id", "").endswith(MESSAGE_ROW_RESOURCE_SUFFIX)
            for node in root.iter("node")
        )
        has_composer = any(
            node.attrib.get("resource-id") == f"{self.package}:id/j28"
            for node in root.iter("node")
        )
        if not has_message_rows or not has_composer:
            return root
        previous = ET.tostring(root, encoding="unicode")
        for _ in range(max(1, max_swipes)):
            # Swipe the viewport upward to advance toward newer rows. Keep
            # both endpoints inside the message surface (jcp).
            self.adb_shell("input", "swipe", "520", "1600", "520", "400", "280")
            time.sleep(0.35)
            current = self.dump_hierarchy(attempts=3)
            if not chat_title_matches(visible_chat_title(current), chat):
                raise BridgeError("WeCom changed chat while moving to the live tail")
            serialized = ET.tostring(current, encoding="unicode")
            root = current
            if serialized == previous:
                break
            previous = serialized
        return root

    def open_chat_list(self, *, allow_restart: bool = True) -> ET.Element:
        phases = 2 if allow_restart else 1
        for phase in range(phases):
            self.launch_wecom()
            for _ in range(8):
                root = self.dump_hierarchy()
                if self.dismiss_anr_dialog(root):
                    continue
                if is_security_gate(root):
                    raise BridgeError("WeCom is waiting at a login or security-verification gate")
                title_nodes = find_nodes(
                    root,
                    text="消息",
                    resource_id=f"{self.package}:id/n5i",
                    package=self.package,
                )
                if title_nodes and any(
                    find_nodes(
                        root,
                        text=target,
                        resource_id=f"{self.package}:id/iql",
                        package=self.package,
                    )
                    for target in self.target_groups
                ):
                    return root
                self.press_back()
            if allow_restart and phase == 0:
                self.restart_wecom_preserving_session(reason="open_chat_list")
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

    def clear_automation_draft(self, chat: str) -> bool:
        """Leave the chat with an empty composer after our own failed write."""
        for _ in range(4):
            root = self.dump_hierarchy()
            if chat_title_matches(visible_chat_title(root), chat):
                break
            self.press_back()
        else:
            return False
        composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
        if not composers or not composer_text(composers[-1]):
            return True
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
        try:
            cleared = self.ensure_chat_identity(chat)
        except BridgeError:
            return False
        composers = find_nodes(cleared, resource_id=f"{self.package}:id/j28", package=self.package)
        return bool(composers and not composer_text(composers[-1]))

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

    def composing_text_components(self, chat: str) -> list[dict[str, Any]]:
        """Return interrupted bridge-owned composer records for one chat."""
        with sqlite3.connect(self.state_db) as conn:
            rows = conn.execute(
                "SELECT component_key, task_id, details_json, updated_at FROM components "
                "WHERE chat = ? AND kind = 'text' AND status = 'composing' "
                "ORDER BY updated_at DESC",
                (chat,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for component_key, task_id, details_json, updated_at in rows:
            try:
                details = json.loads(str(details_json or "{}"))
            except json.JSONDecodeError:
                details = {}
            result.append(
                {
                    "component_key": str(component_key or ""),
                    "task_id": str(task_id or ""),
                    "details": details if isinstance(details, dict) else {},
                    "updated_at": str(updated_at or ""),
                }
            )
        return result

    def abandon_composing_text_components(self, chat: str, *, reason: str) -> None:
        """Close stale draft ownership after the composer is proven empty."""
        with sqlite3.connect(self.state_db) as conn:
            rows = conn.execute(
                "SELECT component_key, details_json FROM components "
                "WHERE chat = ? AND kind = 'text' AND status = 'composing'",
                (chat,),
            ).fetchall()
            for component_key, details_json in rows:
                try:
                    details = json.loads(str(details_json or "{}"))
                except json.JSONDecodeError:
                    details = {}
                if not isinstance(details, dict):
                    details = {}
                details.update({"abandoned_reason": reason, "abandoned_at": now_iso()})
                conn.execute(
                    "UPDATE components SET status = 'abandoned', details_json = ?, updated_at = ? "
                    "WHERE component_key = ?",
                    (json.dumps(details, ensure_ascii=False, sort_keys=True), now_iso(), component_key),
                )

    def recover_stale_automation_draft(self, chat: str, draft: str) -> bool:
        """Clear only a ledger-owned or unambiguous interrupted mention draft."""
        owned = bool(self.composing_text_components(chat))
        legacy_mention_residue = incomplete_native_mention_draft(draft)
        if not owned and not legacy_mention_residue:
            return False
        if not self.clear_automation_draft(chat):
            raise BridgeError("WeCom stale automation draft could not be cleared safely")
        self.abandon_composing_text_components(
            chat,
            reason="recovered_owned_draft" if owned else "recovered_legacy_mention_residue",
        )
        return True

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
        draft = composer_text(composers[-1])
        if draft:
            if not self.recover_stale_automation_draft(chat, draft):
                raise BridgeError("refusing to overwrite a non-empty WeCom draft")
            root = self.normalize_chat_surface(chat)
            composers = find_nodes(root, resource_id=f"{self.package}:id/j28", package=self.package)
            if not composers or composer_text(composers[-1]):
                raise BridgeError("WeCom composer remained non-empty after automation-draft recovery")
        self.mark_component(
            key,
            task_id=task_id,
            chat=chat,
            kind="text",
            value_hash=value_hash,
            status="composing",
            details={"draft_owner": "wecom_android_bridge", "mentioned_users": exact_mentions},
        )
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
        except Exception as exc:
            try:
                cleared = self.clear_automation_draft(chat)
            except Exception:
                cleared = False
            self.mark_component(
                key,
                task_id=task_id,
                chat=chat,
                kind="text",
                value_hash=value_hash,
                status="retryable" if cleared else "composing",
                details={
                    "draft_owner": "wecom_android_bridge",
                    "mentioned_users": exact_mentions,
                    "last_error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "composer_cleared": cleared,
                },
            )
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

    def open_file_action(
        self,
        chat: str,
        root: ET.Element,
        *,
        attempts: int = 2,
        polls_per_attempt: int = 16,
    ) -> tuple[ET.Element, ET.Element]:
        """Open the attachment sheet and return its exact File action.

        On the authorized older Android client, the first attachment tap can
        only dismiss the soft keyboard. Keep the exact-chat title guard while
        waiting, then retry the same attachment control once if needed.
        """
        current = root
        for _ in range(max(1, attempts)):
            plus: list[ET.Element] = []
            # ``j1v`` is the attachment control. ``hvp`` is retained only for
            # older layouts where it genuinely served that role.
            for resource_name in ("j1v", "hvp"):
                candidates = [
                    node
                    for node in find_nodes(
                        current,
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
            self.tap_node(current, plus[-1])
            for _ in range(max(1, polls_per_attempt)):
                time.sleep(0.25)
                current = self.ensure_chat_identity(chat)
                file_nodes = find_nodes(current, text="文件", package=self.package)
                if file_nodes:
                    return current, file_nodes[-1]
        raise BridgeError("WeCom file action is unavailable after attachment-menu retry")

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
        menu, file_action = self.open_file_action(chat, root)
        self.tap_node(menu, file_action)
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
            # Artifacts are the durable result. Deliver them before optional
            # completion text so a brittle native mention picker cannot move
            # the client away from the exact chat and starve file delivery.
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
            if message.strip() and not errors:
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
            return {
                "ok": not errors,
                "transport": "wecom_android",
                "chat_id": f"gui:{chat}",
                "sent_messages": sent_messages,
                "sent_files": sent_files,
                "mentioned_users": unique_nonempty(mentioned_users),
                "errors": errors,
            }

    def parse_messages(
        self,
        root: ET.Element,
        *,
        screenshot: RawScreenshot | None = None,
    ) -> list[dict[str, str]]:
        rows = find_nodes(root, resource_id=f"{self.package}:id/eyy", package=self.package)
        records: list[dict[str, str]] = []
        for row in rows:
            body_nodes = [
                node
                for node in row.iter("node")
                if node_text(node) and node.attrib.get("resource-id", "").endswith(":id/j1l")
            ]
            source_kind = "text"
            source_title = ""
            image_bounds = ""
            image_preview_sha256 = ""
            image_visual_id = ""
            document_filename = ""
            document_size_text = ""
            document_bounds = ""
            if not body_nodes:
                merged_title_nodes = [
                    node
                    for node in row.iter("node")
                    if node_text(node)
                    and node.attrib.get("resource-id", "").endswith(
                        MERGED_HISTORY_TITLE_RESOURCE_SUFFIX
                    )
                ]
                merged_body_nodes = [
                    node
                    for node in row.iter("node")
                    if node_text(node)
                    and node.attrib.get("resource-id", "").endswith(
                        MERGED_HISTORY_BODY_RESOURCE_SUFFIX
                    )
                ]
                if merged_body_nodes:
                    source_kind = MERGED_HISTORY_KIND
                    source_title = " ".join(
                        unique_nonempty(node_text(node) for node in merged_title_nodes)
                    )
                    body_nodes = [*merged_title_nodes, *merged_body_nodes]
            if not body_nodes:
                body_nodes = [
                    node
                    for node in row.iter("node")
                    if node_text(node)
                    and node.attrib.get("resource-id", "").endswith(ARTICLE_CARD_RESOURCE_SUFFIX)
                ]
                if body_nodes:
                    source_kind = ARTICLE_CARD_KIND
                    source_title = " ".join(unique_nonempty(node_text(node) for node in body_nodes))
            if not body_nodes:
                document_nodes = [
                    node
                    for node in row.iter("node")
                    if node_text(node)
                    and node.attrib.get("resource-id", "").endswith(
                        DOCUMENT_FILENAME_RESOURCE_SUFFIX
                    )
                ]
                if document_nodes:
                    source_kind = DOCUMENT_KIND
                    document_filename = normalize_filename_text(node_text(document_nodes[0]))
                    document_bounds = str(document_nodes[0].attrib.get("bounds") or "")
                    size_nodes = [
                        node
                        for node in row.iter("node")
                        if node_text(node)
                        and node.attrib.get("resource-id", "").endswith(
                            DOCUMENT_SIZE_RESOURCE_SUFFIX
                        )
                    ]
                    body_nodes = [*document_nodes, *size_nodes]
                    document_size_text = (
                        normalize_visible_text(node_text(size_nodes[0])) if size_nodes else ""
                    )
                    source_title = document_filename
            if not body_nodes:
                body_nodes = [
                    node
                    for node in row.iter("node")
                    if node.attrib.get("package") == self.package
                    and node.attrib.get("class") == "android.widget.ImageView"
                    and node.attrib.get("resource-id", "").endswith(
                        IMAGE_BUBBLE_RESOURCE_SUFFIX
                    )
                    and node.attrib.get("bounds")
                ]
                if body_nodes:
                    source_kind = IMAGE_KIND
                    image_bounds = str(body_nodes[0].attrib.get("bounds") or "")
                    if screenshot is not None:
                        try:
                            image_preview_sha256 = screenshot_region_sha256(
                                screenshot, image_bounds
                            )
                            image_visual_id = screenshot_region_visual_id(
                                screenshot, image_bounds
                            )
                        except BridgeError:
                            image_preview_sha256 = ""
                            image_visual_id = ""
            body = "\n".join(unique_nonempty(node_text(node) for node in body_nodes))
            if source_kind == IMAGE_KIND:
                body = "[图片]"
            elif source_kind == DOCUMENT_KIND:
                body = f"[文件] {document_filename}"
                if document_size_text:
                    body += f" ({document_size_text})"
            elif not body:
                continue
            if source_kind == MERGED_HISTORY_KIND:
                merged_lines = "\n".join(
                    unique_nonempty(
                        node_text(node)
                        for node in body_nodes
                        if node.attrib.get("resource-id", "").endswith(
                            MERGED_HISTORY_BODY_RESOURCE_SUFFIX
                        )
                    )
                )
                body = (
                    "合并转发的聊天记录\n"
                    f"<title>{html.escape(source_title)}</title>\n"
                    f"{merged_lines}"
                )
            elif source_kind == ARTICLE_CARD_KIND:
                body = f"公众号文章卡片\n<title>{html.escape(source_title)}</title>"
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
            if source_kind == IMAGE_KIND:
                image_identity = image_visual_id or image_preview_sha256 or image_bounds
                fingerprint_material = (
                    f"{direction}\0{sender}\0{source_kind}\0{image_identity}\0{quote_text}"
                )
            else:
                fingerprint_material = (
                    f"{direction}\0{sender}\0{source_kind}\0{body}\0{quote_text}"
                )
            fingerprint = short_hash(fingerprint_material, 64)
            records.append(
                {
                    "fingerprint": fingerprint,
                    "direction": direction,
                    "sender": sender,
                    "mention_name": f"{sender}@微信" if sender and sender_is_wechat else sender,
                    "body": body,
                    "quote_text": quote_text,
                    "source_kind": source_kind,
                    "source_title": source_title,
                    "row_bounds": str(row.attrib.get("bounds") or ""),
                    "image_bounds": image_bounds,
                    "image_preview_sha256": image_preview_sha256,
                    "image_visual_id": image_visual_id,
                    "document_filename": document_filename,
                    "document_size_text": document_size_text,
                    "document_bounds": document_bounds,
                    **sender_evidence,
                }
            )
        return records

    def document_node_for_record(
        self,
        root: ET.Element,
        record: dict[str, str],
    ) -> ET.Element:
        expected_sender = str(record.get("sender") or "")
        expected_filename = str(record.get("document_filename") or "")
        expected_size = normalize_visible_text(record.get("document_size_text"))
        expected_bounds = str(record.get("document_bounds") or "")
        matches: list[ET.Element] = []
        rows = find_nodes(
            root,
            resource_id=f"{self.package}:id/eyy",
            package=self.package,
        )
        for row in rows:
            filename_nodes = [
                node
                for node in row.iter("node")
                if node_text(node)
                and node.attrib.get("resource-id", "").endswith(
                    DOCUMENT_FILENAME_RESOURCE_SUFFIX
                )
                and normalize_filename_text(node_text(node))
                == normalize_filename_text(expected_filename)
            ]
            if len(filename_nodes) != 1:
                continue
            sender, _ = message_row_sender(row, filename_nodes)
            if expected_sender and sender != expected_sender:
                continue
            if expected_size:
                size_values = {
                    normalize_visible_text(node_text(node))
                    for node in row.iter("node")
                    if node_text(node)
                    and node.attrib.get("resource-id", "").endswith(
                        DOCUMENT_SIZE_RESOURCE_SUFFIX
                    )
                }
                if expected_size not in size_values:
                    continue
            node = filename_nodes[0]
            bounds = str(node.attrib.get("bounds") or "")
            if expected_bounds and bounds == expected_bounds:
                return node
            matches.append(node)
        if len(matches) == 1:
            return matches[0]
        raise BridgeError("exact inbound WeCom document bubble is not uniquely visible")

    def find_document_node_for_record(
        self,
        chat: str,
        record: dict[str, str],
    ) -> tuple[ET.Element, ET.Element]:
        root = self.open_chat(chat)
        root = self.move_chat_to_live_tail(chat, root)
        pages = bounded_int(
            self.config.get("inbound_document_search_pages"),
            8,
            0,
            8,
        )
        last_error = ""
        for page in range(pages + 1):
            try:
                return root, self.document_node_for_record(root, record)
            except BridgeError as exc:
                last_error = str(exc)
            if page >= pages:
                break
            self.adb_shell("input", "swipe", "520", "350", "520", "1450", "500")
            time.sleep(0.55)
            root = self.dump_hierarchy(attempts=3)
            if not chat_title_matches(visible_chat_title(root), chat):
                raise BridgeError("WeCom changed chat while locating the document bubble")
        raise BridgeError(last_error or "exact inbound WeCom document bubble is not visible")

    def remote_document_candidates(self, filename: str) -> list[str]:
        safe_name = safe_file_name(Path(filename))
        command = (
            f"find {shlex.quote(INBOUND_FILECACHE_ROOT)} -type f "
            f"-name {shlex.quote(safe_name)} 2>/dev/null"
        )
        output = self.adb_shell(command, timeout=30, check=False)
        prefix = INBOUND_FILECACHE_ROOT.rstrip("/") + "/"
        return unique_nonempty(
            line
            for line in output.splitlines()
            if line.startswith(prefix) and Path(line).name == safe_name
        )[:8]

    def remote_file_size(self, path: str) -> int:
        output = self.adb_shell(
            f"wc -c < {shlex.quote(path)} 2>/dev/null",
            timeout=30,
            check=False,
        ).strip()
        try:
            return int(output)
        except ValueError:
            return 0

    def wait_for_exact_document_surface(
        self,
        filename: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> ET.Element:
        deadline = time.monotonic() + max(1.0, timeout_seconds)
        while time.monotonic() < deadline:
            root = self.dump_hierarchy(attempts=2)
            if any(
                filename_display_matches(node_text(node), filename)
                for node in root.iter("node")
                if node_text(node)
            ):
                return root
            time.sleep(0.25)
        raise BridgeError("WeCom did not open the exact native document surface")

    def wait_for_document_download(
        self,
        filename: str,
        displayed_size: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, int]:
        deadline = time.monotonic() + max(5.0, timeout_seconds)
        stable: dict[str, tuple[int, int]] = {}
        maximum = bounded_int(
            self.config.get("max_inbound_file_bytes"),
            200 * 1024 * 1024,
            1,
            1024 * 1024 * 1024,
        )
        while time.monotonic() < deadline:
            for remote_path in self.remote_document_candidates(filename):
                size = self.remote_file_size(remote_path)
                if size <= 0 or size > maximum or not display_size_matches(size, displayed_size):
                    continue
                previous_size, count = stable.get(remote_path, (0, 0))
                stable[remote_path] = (
                    size,
                    count + 1 if previous_size == size else 1,
                )
            ready = [
                (path, size)
                for path, (size, count) in stable.items()
                if count >= 2
            ]
            if ready:
                # Multiple exact-name entries are resolved after pull by content
                # checksum. Return one here only when the cache identity is unique.
                if len(ready) == 1:
                    return ready[0]
                sizes = {size for _, size in ready}
                if len(sizes) == 1:
                    return ready[-1]
                raise BridgeError(
                    "multiple different exact-name WeCom document cache entries are visible"
                )
            time.sleep(0.75)
        raise BridgeError("WeCom document download did not complete before the configured timeout")

    def materialize_document_record(
        self,
        chat: str,
        record: dict[str, str],
    ) -> dict[str, str]:
        """Download one exact same-chat native document card into private staging."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android document source")
        if str(record.get("direction") or "") != "inbound":
            raise BridgeError("refusing to materialize an outbound WeCom document")
        if str(record.get("source_kind") or "") != DOCUMENT_KIND:
            return dict(record)
        filename = safe_file_name(Path(str(record.get("document_filename") or "")))
        fingerprint = str(record.get("fingerprint") or "")
        if not fingerprint:
            raise BridgeError("WeCom document record is missing its fingerprint")
        target = (
            self.staging_dir
            / "inbound-media"
            / short_hash(chat, 16)
            / fingerprint[:32]
            / filename
        )
        if not target.is_file():
            root, node = self.find_document_node_for_record(chat, record)
            opened = False
            try:
                self.tap_node(root, node)
                self.wait_for_exact_document_surface(filename)
                opened = True
                remote_path, expected_bytes = self.wait_for_document_download(
                    filename,
                    str(record.get("document_size_text") or ""),
                    timeout_seconds=bounded_float(
                        self.config.get("inbound_document_download_timeout_seconds"),
                        180.0,
                        10.0,
                        1800.0,
                    ),
                )
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tempfile.NamedTemporaryFile(
                    prefix=f".{target.name}.",
                    suffix=".tmp",
                    dir=target.parent,
                    delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                try:
                    self.adb("pull", remote_path, str(temporary), timeout=300)
                    if temporary.stat().st_size != expected_bytes:
                        raise BridgeError("downloaded WeCom document size changed during pull")
                    if filename.lower().endswith(".pdf"):
                        with temporary.open("rb") as handle:
                            if handle.read(5) != b"%PDF-":
                                raise BridgeError("native WeCom PDF has an invalid signature")
                    os.chmod(temporary, 0o600)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            finally:
                if opened:
                    self.press_back()
                restored = self.open_chat(chat)
                restored = self.move_chat_to_live_tail(chat, restored)
                if not chat_title_matches(visible_chat_title(restored), chat):
                    raise BridgeError("WeCom did not return to the exact document source chat")
        if (
            not target.is_file()
            or target.stat().st_size <= 0
            or not display_size_matches(
                target.stat().st_size,
                record.get("document_size_text"),
            )
        ):
            raise BridgeError("materialized WeCom document failed its identity checks")
        if filename.lower().endswith(".pdf"):
            with target.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise BridgeError("materialized WeCom PDF signature is invalid")
        result = dict(record)
        result.update(
            {
                "attachment_path": str(target),
                "attachment_filename": filename,
                "attachment_size_bytes": str(target.stat().st_size),
                "attachment_sha256": sha256_file(target),
                "attachment_capture_kind": "wecom_android_native_document_card",
            }
        )
        return result

    def image_node_for_record(
        self,
        root: ET.Element,
        screenshot: RawScreenshot,
        record: dict[str, str],
    ) -> ET.Element:
        expected_sender = str(record.get("sender") or "")
        expected_visual_id = str(record.get("image_visual_id") or "")
        expected_bounds = str(record.get("image_bounds") or "")
        visual_matches: list[ET.Element] = []
        bounds_matches: list[ET.Element] = []
        rows = find_nodes(root, resource_id=f"{self.package}:id/eyy", package=self.package)
        for row in rows:
            image_nodes = [
                node
                for node in row.iter("node")
                if node.attrib.get("package") == self.package
                and node.attrib.get("class") == "android.widget.ImageView"
                and node.attrib.get("resource-id", "").endswith(
                    IMAGE_BUBBLE_RESOURCE_SUFFIX
                )
                and node.attrib.get("bounds")
            ]
            if len(image_nodes) != 1:
                continue
            node = image_nodes[0]
            sender, _ = message_row_sender(row, image_nodes)
            if expected_sender and sender != expected_sender:
                continue
            bounds = str(node.attrib.get("bounds") or "")
            try:
                visual_id = screenshot_region_visual_id(screenshot, bounds)
            except BridgeError:
                visual_id = ""
            if expected_visual_id and visual_id == expected_visual_id:
                visual_matches.append(node)
            if expected_bounds and bounds == expected_bounds:
                bounds_matches.append(node)
        if len(visual_matches) == 1:
            return visual_matches[0]
        if len(bounds_matches) == 1:
            return bounds_matches[0]
        raise BridgeError("exact inbound WeCom image bubble is not uniquely visible")

    def wait_for_image_viewer(self, *, timeout_seconds: float = 8.0) -> ET.Element:
        deadline = time.monotonic() + max(1.0, timeout_seconds)
        last_title = ""
        while time.monotonic() < deadline:
            root = self.dump_hierarchy(attempts=2)
            last_title = visible_chat_title(root)
            viewer_nodes = [
                node
                for node in root.iter("node")
                if node.attrib.get("package") == self.package
                and node.attrib.get("resource-id", "").endswith(
                    IMAGE_VIEWER_RESOURCE_SUFFIX
                )
            ]
            if viewer_nodes and not last_title:
                return root
            time.sleep(0.25)
        raise BridgeError(
            f"WeCom image viewer did not open from the exact bubble (visible title: {last_title!r})"
        )

    def materialize_image_record(
        self,
        chat: str,
        record: dict[str, str],
    ) -> dict[str, str]:
        """Capture one exact same-chat image through WeCom's native full viewer."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android image source")
        if str(record.get("direction") or "") != "inbound":
            raise BridgeError("refusing to materialize an outbound WeCom image")
        if str(record.get("source_kind") or "") != IMAGE_KIND:
            return dict(record)
        fingerprint = str(record.get("fingerprint") or "")
        if not fingerprint:
            raise BridgeError("WeCom image record is missing its visual fingerprint")
        target = (
            self.staging_dir
            / "inbound-media"
            / short_hash(chat, 16)
            / f"wecom-image-{fingerprint[:32]}.png"
        )
        capture: RawScreenshot | None = None
        if not (target.is_file() and target.stat().st_size > 64 and target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"):
            root = self.open_chat(chat)
            chat_screenshot = self.capture_raw_screenshot()
            node = self.image_node_for_record(root, chat_screenshot, record)
            viewer_open = False
            try:
                self.tap_node(root, node)
                self.wait_for_image_viewer()
                viewer_open = True
                time.sleep(
                    bounded_float(
                        self.config.get("inbound_image_capture_wait_seconds"),
                        1.25,
                        0.25,
                        5.0,
                    )
                )
                capture = self.capture_raw_screenshot()
                write_private_bytes(target, encode_rgba_png(capture))
            finally:
                if viewer_open:
                    self.press_back()
                restored = self.open_chat(chat)
                if not chat_title_matches(visible_chat_title(restored), chat):
                    raise BridgeError("WeCom did not return to the exact image source chat")
        result = dict(record)
        result.update(
            {
                "attachment_path": str(target),
                "attachment_filename": target.name,
                "attachment_size_bytes": str(target.stat().st_size),
                "attachment_sha256": sha256_file(target),
                "attachment_width": str(capture.width if capture else ""),
                "attachment_height": str(capture.height if capture else ""),
                "attachment_capture_kind": "wecom_android_native_full_view",
            }
        )
        return result

    def scan_older_message_records(
        self,
        chat: str,
        current_records: list[dict[str, str]],
        *,
        max_pages: int,
    ) -> list[dict[str, str]]:
        """Read a bounded number of older viewports without changing task semantics."""
        pages = bounded_int(max_pages, 0, 0, 8)
        if pages == 0:
            return []
        recovered: list[dict[str, str]] = []
        seen = {record["fingerprint"] for record in current_records}
        for _ in range(pages):
            # Pull the viewport downward to walk backward through older rows.
            self.adb_shell("input", "swipe", "520", "350", "520", "1450", "500")
            time.sleep(0.55)
            root = self.dump_hierarchy(attempts=3)
            if not chat_title_matches(visible_chat_title(root), chat):
                break
            page_records = self.parse_messages(root)
            if not page_records:
                break
            for record in page_records:
                fingerprint = record["fingerprint"]
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                recovered.append(record)
        return recovered

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
                "retry_after = CASE WHEN excluded.status = 'pending' "
                "THEN '' ELSE observed_messages.retry_after END, "
                "failure_count = CASE WHEN excluded.status = 'pending' "
                "THEN 0 ELSE observed_messages.failure_count END, "
                "last_error = CASE WHEN excluded.status = 'pending' "
                "THEN '' ELSE observed_messages.last_error END, "
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

    def defer_observed_message(
        self,
        chat: str,
        fingerprint: str,
        error: str,
        *,
        base_seconds: float = 30.0,
        max_seconds: float = 900.0,
    ) -> None:
        """Back off a recoverable native-media failure without losing the row."""
        if not fingerprint:
            return
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute(
                "SELECT failure_count FROM observed_messages "
                "WHERE chat = ? AND fingerprint = ?",
                (chat, fingerprint),
            ).fetchone()
            count = int(row[0] or 0) if row else 0
            next_count = count + 1
            delay = min(float(max_seconds), float(base_seconds) * (2 ** min(count, 5)))
            retry_after = datetime.now(timezone.utc) + timedelta(seconds=delay)
            conn.execute(
                "UPDATE observed_messages SET retry_after = ?, failure_count = ?, "
                "last_error = ?, updated_at = ? WHERE chat = ? AND fingerprint = ?",
                (
                    retry_after.isoformat(timespec="seconds"),
                    next_count,
                    str(error)[:500],
                    now_iso(),
                    chat,
                    fingerprint,
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
                "SELECT fingerprint, record_json, retry_after FROM observed_messages "
                "WHERE chat = ? AND status = 'pending' ORDER BY updated_at, rowid",
                (chat,),
            ).fetchall()
        result: list[dict[str, str]] = []
        current_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for fingerprint, raw_record, retry_after in rows:
            if str(retry_after or "") and str(retry_after) > current_time:
                continue
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
        source_kind = str(record.get("source_kind") or "text")
        attachments: list[dict[str, Any]] = []
        if source_kind in {IMAGE_KIND, DOCUMENT_KIND}:
            attachment = Path(
                str(record.get("attachment_path") or "")
            ).expanduser().resolve()
            if not attachment.is_file():
                raise BridgeError(
                    f"inbound WeCom {source_kind} has not been materialized"
                )
            expected_sha256 = str(record.get("attachment_sha256") or "")
            actual_sha256 = sha256_file(attachment)
            if expected_sha256 and expected_sha256 != actual_sha256:
                raise BridgeError(
                    f"inbound WeCom {source_kind} checksum changed before ingest"
                )
            attachment_payload = {
                "kind": source_kind,
                "filename": str(record.get("attachment_filename") or attachment.name),
                "path": str(attachment),
                "size_bytes": attachment.stat().st_size,
                "sha256": actual_sha256,
                "capture_kind": str(record.get("attachment_capture_kind") or ""),
            }
            if source_kind == IMAGE_KIND:
                attachment_payload.update(
                    {
                        "width": str(record.get("attachment_width") or ""),
                        "height": str(record.get("attachment_height") or ""),
                        "capture_kind": str(
                            record.get("attachment_capture_kind")
                            or "wecom_android_native_full_view"
                        ),
                    }
                )
            attachments.append(attachment_payload)
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
            "msgtype": source_kind,
            "text": str(record.get("body") or ""),
            "quote_text": str(record.get("quote_text") or ""),
            "source_metadata": {
                "kind": source_kind,
                "title": str(record.get("source_title") or ""),
                "image_preview_sha256": str(
                    record.get("image_preview_sha256") or ""
                ),
                "image_visual_id": str(record.get("image_visual_id") or ""),
                "document_filename": str(record.get("document_filename") or ""),
                "document_size_text": str(record.get("document_size_text") or ""),
            },
            "attachments": attachments,
        }

    def build_event_batch(
        self,
        chat: str,
        records: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Build one source-preserving event from a contiguous sender burst."""
        if not records:
            raise BridgeError("cannot build an event from an empty message batch")
        events = [self.build_event(chat, record) for record in records]
        if len(events) == 1:
            return events[0]
        senders = {
            str(record.get("sender") or "").strip()
            for record in records
        }
        if len(senders) != 1:
            raise BridgeError("combined WeCom messages must have one exact sender")
        event = dict(events[-1])
        fingerprints = [
            str(record.get("fingerprint") or "") for record in records
        ]
        event["message_id"] = (
            "android:"
            + short_hash(f"{chat}\0" + "\0".join(fingerprints), 24)
        )
        event["text"] = "\n\n".join(
            str(item.get("text") or "").strip()
            for item in events
            if str(item.get("text") or "").strip()
        )
        event["quote_text"] = "\n\n".join(
            str(item.get("quote_text") or "").strip()
            for item in events
            if str(item.get("quote_text") or "").strip()
        )
        event["attachments"] = [
            attachment
            for item in events
            for attachment in item.get("attachments") or []
        ]
        source_components = [
            item.get("source_metadata")
            for item in events
            if isinstance(item.get("source_metadata"), dict)
        ]
        event["source_metadata"] = {
            "kind": "combined_forward",
            "components": source_components,
            "message_count": len(events),
        }
        if any(str(item.get("msgtype") or "") == "wechat_article_card" for item in events):
            event["msgtype"] = "wechat_article_card"
        else:
            event["msgtype"] = "combined_forward"
        return event

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

    def snapshot(
        self,
        chat: str,
        *,
        enqueue: bool = False,
        history_pages: int = 0,
    ) -> dict[str, Any]:
        # Hold the GUI lock only while reading or writing the official client.
        # Routing/ingest may invoke an agent and must never block unrelated
        # artifact delivery for the duration of that backend turn.
        media_materialization_errors: list[dict[str, str]] = []
        with self.serialized(timeout_seconds=30.0):
            root = self.open_chat(chat)
            root = self.move_chat_to_live_tail(chat, root)
            current_records = self.parse_messages(root)
            if any(
                record.get("source_kind") == IMAGE_KIND for record in current_records
            ):
                current_records = self.parse_messages(
                    root,
                    screenshot=self.capture_raw_screenshot(),
                )
            sequence = [record["fingerprint"] for record in current_records]
            history_records: list[dict[str, str]] = []
            if history_pages:
                try:
                    history_records = self.scan_older_message_records(
                        chat,
                        current_records,
                        max_pages=history_pages,
                    )
                finally:
                    # Re-entering through the conversation list reliably lands
                    # at the newest viewport after a bounded backward scan.
                    self.open_chat_list()
                    restored = self.open_chat(chat)
                    self.move_chat_to_live_tail(chat, restored)
            records = [*current_records, *history_records]
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
                    and fingerprint in pending_by_fingerprint
                ):
                    pending_by_fingerprint[fingerprint] = record
            pending_inbound = list(pending_by_fingerprint.values())
            for index, record in enumerate(pending_inbound):
                source_kind = record.get("source_kind")
                if source_kind not in {IMAGE_KIND, DOCUMENT_KIND}:
                    continue
                attachment_path = Path(
                    str(record.get("attachment_path") or "")
                ).expanduser()
                if attachment_path.is_file():
                    continue
                try:
                    materialized = (
                        self.materialize_image_record(chat, record)
                        if source_kind == IMAGE_KIND
                        else self.materialize_document_record(chat, record)
                    )
                except Exception as exc:
                    self.defer_observed_message(
                        chat,
                        str(record.get("fingerprint") or ""),
                        f"{type(exc).__name__}: {str(exc)[:500]}",
                    )
                    media_materialization_errors.append(
                        {
                            "fingerprint": str(record.get("fingerprint") or "")[:16],
                            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                        }
                    )
                    continue
                pending_inbound[index] = materialized
                self.mark_observed_message(chat, materialized, "pending")
            # Checkpoint the observed viewport before releasing GUI ownership.
            # Pending rows remain durable and are retried if ingest itself fails.
            self.save_snapshot(chat, sequence)

        ingested: list[dict[str, Any]] = []
        pending_replies: list[tuple[str, list[str], str]] = []
        if enqueue:
            for batch in coalesce_sender_records(pending_inbound):
                ready_records = [
                    record
                    for record in batch
                    if not (
                        record.get("source_kind") in {IMAGE_KIND, DOCUMENT_KIND}
                        and not Path(
                            str(record.get("attachment_path") or "")
                        ).is_file()
                    )
                ]
                if not ready_records:
                    continue
                event = self.build_event_batch(chat, ready_records)
                result = self.invoke_ingest(event)
                ingested.append(result)
                for record in ready_records:
                    self.mark_observed_message(chat, record, "ingested")
                response = str(result.get("reply") or result.get("ack") or "").strip()
                if response:
                    reply_mentions = result.get("reply_mentions")
                    if not isinstance(reply_mentions, list):
                        fallback_mention = str(
                            ready_records[-1].get("mention_name")
                            or ready_records[-1].get("sender")
                            or ""
                        )
                        reply_mentions = [fallback_mention] if fallback_mention else []
                    pending_replies.append(
                        (
                            response,
                            [str(value) for value in reply_mentions if str(value).strip()],
                            f"ingress:{event['message_id']}",
                        )
                    )

        sent_replies: list[str] = []
        reply_errors: list[dict[str, str]] = []
        for response, mentions, task_id in pending_replies:
            try:
                with self.serialized(timeout_seconds=30.0):
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
            "ok": not reply_errors and not media_materialization_errors,
            "chat": chat,
            "overlap": overlap,
            "viewport_changed_without_overlap": bool(overlap == 0 and previous and sequence),
            "processed": len(ingested),
            "pending": (
                len(media_materialization_errors)
                if enqueue
                else len(pending_inbound)
            ),
            "messages": pending_inbound,
            "ingested": ingested,
            "replied": len(sent_replies),
            "reply_errors": reply_errors,
            "media_materialization_errors": media_materialization_errors,
            "history_pages": int(history_pages),
            "history_records": len(history_records),
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
        history_scan_chat = ""
        if (
            self.history_scan_pages > 0
            and self.target_groups
            and now >= self._next_history_scan_at
        ):
            history_scan_chat = self.target_groups[
                self._history_scan_cursor % len(self.target_groups)
            ]
            self._history_scan_cursor += 1
            self._next_history_scan_at = now + self.history_scan_seconds
            due = unique_nonempty([*due, history_scan_chat])
        results: list[dict[str, Any]] = []
        for chat in due:
            try:
                results.append(
                    self.snapshot(
                        chat,
                        enqueue=True,
                        history_pages=(
                            self.history_scan_pages if chat == history_scan_chat else 0
                        ),
                    )
                )
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
            "history_scan_chat": history_scan_chat,
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
        health = self.poll_health_snapshot()
        package = ""
        title = ""
        surface_state = "unavailable"
        if authorized and health.get("poll_in_progress"):
            # Health probes must not race UIAutomator against the active poll.
            package = self.package
            surface_state = "polling"
        elif authorized:
            try:
                with self.serialized(timeout_seconds=0.2):
                    root = self.dump_hierarchy(attempts=2)
            except (BridgeError, OSError):
                root = None
            if root is not None:
                packages = hierarchy_packages(root)
                package = self.package if self.package in packages else self.current_package()
                title = visible_chat_title(root) if self.package in packages else ""
                if is_anr_dialog(root):
                    surface_state = "anr"
                elif title:
                    surface_state = "chat"
                elif self.package in packages:
                    surface_state = "wecom_other"
                else:
                    surface_state = "other_app"
            else:
                package = self.current_package()
        healthy = bool(
            authorized
            and health.get("poll_healthy")
            and surface_state != "anr"
        )
        return {
            "ok": healthy,
            "enabled": bool(self.config.get("enabled", True)),
            "transport": "wecom_android",
            "device_authorized": authorized,
            "wecom_foreground": surface_state in {"chat", "wecom_other", "polling"},
            "visible_chat": title,
            "surface_state": surface_state,
            **health,
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
                self.record_poll_attempt()
                try:
                    result = self.poll_cycle()
                except Exception as exc:
                    error_text = f"{type(exc).__name__}: {str(exc)[:500]}"
                    self.record_poll_failure(error_text)
                    recovery: dict[str, Any] | None = None
                    if self.surface_failure_text(error_text):
                        try:
                            with self.serialized(timeout_seconds=30.0):
                                recovery = self.recover_transport_surface(reason="poll_exception")
                        except Exception as recovery_exc:
                            recovery = {
                                "ok": False,
                                "error": (
                                    f"{type(recovery_exc).__name__}: "
                                    f"{str(recovery_exc)[:500]}"
                                ),
                            }
                    print(
                        json.dumps(
                            {"ok": False, "error": error_text, "recovery": recovery},
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    continue
                surface_error = self.surface_failure_text(result)
                if surface_error:
                    self.record_poll_failure(surface_error)
                    try:
                        with self.serialized(timeout_seconds=30.0):
                            recovery = self.recover_transport_surface(reason="poll_result")
                    except Exception as recovery_exc:
                        recovery = {
                            "ok": False,
                            "error": (
                                f"{type(recovery_exc).__name__}: "
                                f"{str(recovery_exc)[:500]}"
                            ),
                        }
                    print(
                        json.dumps(
                            {"ok": False, "result": result, "recovery": recovery},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        flush=True,
                    )
                    continue
                self.record_poll_success()
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
