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
from urllib import error as urlerror
from urllib import parse, request as urlrequest
from xml.etree import ElementTree as ET
import zlib


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
ANDROID_CONTROL_SCRIPTS = ROOT / "agentic_tools" / "android_device_agent" / "scripts"
if str(ANDROID_CONTROL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ANDROID_CONTROL_SCRIPTS))

from android_control_lease import read_active_priority

DEFAULT_CONFIG = PRIVATE / "wecom_android_bridge.local.json"
DEFAULT_STATE_DB = PRIVATE / "wecom_android_bridge.local.sqlite"
DEFAULT_QUEUE = PRIVATE / "wecom_task_queue.jsonl"
DEFAULT_HISTORY_DB = PRIVATE / "wecom_messages.local.sqlite"
DEFAULT_STAGING = PRIVATE / "android-staging"
DEFAULT_CONTROL_PRIORITY = (
    ROOT
    / "agentic_tools"
    / "android_device_agent"
    / ".private"
    / "android_control_priority.json"
)
DEFAULT_ANDROID_LAYOUT = (
    ROOT / "output" / "android_device_agent" / "android-mix2s.layout"
)
DEFAULT_DUAL_TMUX_TARGET = "labcanvas-android-mix2s:wecom-virtual.0"
PERSONAL_WECHAT_MAIN_ACTIVITY = "com.tencent.mm/.ui.LauncherUI"
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
MAX_RECOVERY_HISTORY_PAGES = 40
DEFAULT_TEXT_CHUNK_CHARS = 1600
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
MESSAGE_ROW_RESOURCE_SUFFIXES = (":id/eyy", ":id/cta")
# Kept for compatibility with callers that import the historical singular
# constant. New code must use the tuple above.
MESSAGE_ROW_RESOURCE_SUFFIX = MESSAGE_ROW_RESOURCE_SUFFIXES[0]
MESSAGE_BODY_RESOURCE_SUFFIXES = (":id/j1l", ":id/ij7")
MESSAGE_AVATAR_RESOURCE_SUFFIXES = (":id/ja3", ":id/isu")
CHAT_TITLE_RESOURCE_SUFFIXES = (":id/n5i", ":id/nsm")
CHAT_LIST_ROW_RESOURCE_SUFFIXES = (":id/iql", ":id/i2e")
COMPOSER_RESOURCE_SUFFIXES = (":id/j28", ":id/iju")
ATTACHMENT_RESOURCE_SUFFIXES = (":id/j1v", ":id/ijh", ":id/hvp")
UNREAD_BADGE_RESOURCE_SUFFIXES = (":id/l07", ":id/l0z")
ARTICLE_CARD_RESOURCE_SUFFIX = ":id/mww"
ARTICLE_CARD_KIND = "wechat_article_card"
MERGED_HISTORY_TITLE_RESOURCE_SUFFIX = ":id/jb2"
MERGED_HISTORY_BODY_RESOURCE_SUFFIX = ":id/jb1"
MERGED_HISTORY_KIND = "merged_chat_history"
IMAGE_BUBBLE_RESOURCE_SUFFIX = ":id/kfb"
IMAGE_KIND = "image"
IMAGE_VIEWER_RESOURCE_SUFFIX = ":id/nxh"
IMAGE_ORIGINAL_LABEL_PREFIXES = ("查看原图", "查看原圖")
IMAGE_ORIGINAL_FAILURE_LABELS = ("原图下载失败", "原圖下載失敗")
IMAGE_SAVE_LABELS = (
    "保存图片",
    "保存圖片",
    "保存图片到手机",
    "保存圖片到手機",
    "保存到手机",
    "儲存到手機",
)
MEDIASTORE_IMAGES_URI = "content://media/external/images/media"
SHIPINHAO_CARD_THUMBNAIL_RESOURCE_SUFFIX = ":id/og2"
SHIPINHAO_CARD_ACCOUNT_RESOURCE_SUFFIX = ":id/og3"
SHIPINHAO_CARD_KIND = "shipinhao_card"
DOCUMENT_FILENAME_RESOURCE_SUFFIXES = (":id/j2k", ":id/ik8")
DOCUMENT_SIZE_RESOURCE_SUFFIXES = (":id/j2g", ":id/ik4")
DOCUMENT_FILENAME_RESOURCE_SUFFIX = DOCUMENT_FILENAME_RESOURCE_SUFFIXES[0]
DOCUMENT_SIZE_RESOURCE_SUFFIX = DOCUMENT_SIZE_RESOURCE_SUFFIXES[0]
DOCUMENT_KIND = "document"
INBOUND_FILECACHE_ROOT = "/sdcard/Android/data/com.tencent.wework/files/filecache"
SAFE_EXTERNAL_LOG_DIRS = tuple(
    f"/sdcard/Android/data/com.tencent.wework/files/{name}"
    for name in (
        "src_log",
        "src_clog",
        "TmLogs",
        "onelog",
        "commonlog",
        "perf",
        "perfUploading",
        "zip_log",
    )
)
SAFE_EXTERNAL_IMAGE_CACHE_DIRS = tuple(
    f"/sdcard/Android/data/com.tencent.wework/files/{name}"
    for name in (
        "tempimagecache",
        "r_flutter_image_cache",
        "imagecache",
    )
)
ANR_MESSAGE_MARKERS = ("没有响应", "isn't responding", "is not responding")
ANR_WAIT_LABELS = {"等待", "Wait", "WAIT"}
LOW_STORAGE_DIALOG_TITLES = {
    "存储空间严重不足",
    "Storage space is critically low",
    "Storage space is running out",
}
LOW_STORAGE_DISMISS_LABELS = {"取消", "Cancel", "CANCEL"}
LOW_STORAGE_CLEANUP_LABELS = {"前往清理", "Clean up", "CLEAN UP"}
CRASH_REPORT_TITLE_MARKERS = (
    "屡次停止运行",
    "屢次停止運行",
    "keeps stopping",
    "has stopped",
    "stopped working",
)
CRASH_REPORT_CANCEL_LABELS = {"取消", "Cancel", "CANCEL"}
CRASH_REPORT_SUBMIT_LABELS = {"报告", "報告", "Report", "REPORT"}
UIAUTOMATOR_BUSY_MARKERS = (
    "already registered",
    "uiautomationservice",
    "uiautomation service",
)
DEFAULT_UI_DUMP_TOTAL_TIMEOUT_SECONDS = 25.0
DEFAULT_UI_DUMP_ATTEMPT_TIMEOUT_SECONDS = 8.0
SECURITY_GATE_LABELS = {
    "登录企业微信",
    "扫码登录",
    "安全验证",
    "设备验证",
    "请完成验证",
    "选择企业进入",
    "创建/加入其他企业",
}
AUTHENTICATION_TEXT_MARKERS = (
    "企业微信申请获得以下权限",
    "使用微信登录企业微信",
    "选择企业进入",
)
AUTHENTICATION_ACTIVITY_MARKERS = (
    "login",
    "oauth",
    "authorize",
    "authorization",
    "permission",
    "security",
    "verify",
    "verification",
    "enterpriseinfoactivity",
    "enterpriselistactivity",
)
SURFACE_ERROR_MARKERS = (
    "chat list is not visible",
    "exact allowlisted wecom chat is not visible",
    "exact chat composer could not be restored",
    "could not read android ui hierarchy",
    "wecom did not reach the foreground",
    "wecom changed chat",
    "wecom authentication is in progress",
    "android /data storage is critically low",
)


class BridgeError(RuntimeError):
    """A fail-closed Android transport error."""


@dataclass(frozen=True)
class RawScreenshot:
    width: int
    height: int
    rgba: bytes


@dataclass(frozen=True)
class MediaStoreImage:
    media_id: int
    path: str
    display_name: str
    size_bytes: int
    width: int
    height: int
    date_added: int
    relative_path: str


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


MEDIASTORE_IMAGE_ROW_RE = re.compile(
    r"^Row:\s+\d+\s+_id=(?P<media_id>\d+),\s+"
    r"_data=(?P<path>.*?),\s+_display_name=(?P<display_name>.*?),\s+"
    r"_size=(?P<size_bytes>\d+),\s+width=(?P<width>-?\d+),\s+"
    r"height=(?P<height>-?\d+),\s+date_added=(?P<date_added>\d+),\s+"
    r"relative_path=(?P<relative_path>.*)$"
)


def parse_media_store_images(payload: str) -> list[MediaStoreImage]:
    """Parse Android MediaStore rows without depending on app-private paths."""
    images: list[MediaStoreImage] = []
    for raw_line in str(payload or "").splitlines():
        match = MEDIASTORE_IMAGE_ROW_RE.match(raw_line.strip())
        if not match:
            continue
        values = match.groupdict()
        images.append(
            MediaStoreImage(
                media_id=int(values["media_id"]),
                path=values["path"],
                display_name=values["display_name"],
                size_bytes=int(values["size_bytes"]),
                width=int(values["width"]),
                height=int(values["height"]),
                date_added=int(values["date_added"]),
                relative_path=values["relative_path"],
            )
        )
    return sorted(images, key=lambda item: item.media_id)


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


def is_low_storage_dialog(root: ET.Element) -> bool:
    texts = hierarchy_visible_texts(root)
    return bool(texts.intersection(LOW_STORAGE_DIALOG_TITLES)) and bool(
        texts.intersection(LOW_STORAGE_DISMISS_LABELS)
    ) and bool(texts.intersection(LOW_STORAGE_CLEANUP_LABELS))


def is_crash_report_dialog(root: ET.Element) -> bool:
    """Recognize Android/MIUI's app-crash report prompt exactly."""
    texts = hierarchy_visible_texts(root)
    has_title = any(
        marker.casefold() in text.casefold()
        for marker in CRASH_REPORT_TITLE_MARKERS
        for text in texts
    )
    return (
        has_title
        and bool(texts.intersection(CRASH_REPORT_CANCEL_LABELS))
        and bool(texts.intersection(CRASH_REPORT_SUBMIT_LABELS))
    )


def is_security_gate(root: ET.Element) -> bool:
    texts = hierarchy_visible_texts(root)
    if texts.intersection(SECURITY_GATE_LABELS):
        return True
    combined = "\n".join(texts)
    return any(marker in combined for marker in AUTHENTICATION_TEXT_MARKERS)


def activity_is_authentication_gate(activity: str) -> bool:
    lowered = normalize_visible_text(activity).casefold()
    return bool(lowered) and any(
        marker in lowered for marker in AUTHENTICATION_ACTIVITY_MARKERS
    )


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


def strip_redundant_leading_mentions(message: str, mentions: list[str]) -> str:
    """Remove plain leading copies of mentions inserted natively by WeCom."""
    original = str(message or "")
    if not original.strip() or not mentions:
        return original
    aliases: set[str] = set()
    for value in mentions:
        mention = normalize_mention_name(value).lstrip("@＠").strip()
        if not mention:
            continue
        external_base = re.sub(r"[@＠]微信$", "", mention).strip()
        aliases.add(external_base or mention)
    if not aliases:
        return original
    ordered = sorted(aliases, key=len, reverse=True)
    cleaned = original
    removed = False
    while True:
        matched = False
        for alias in ordered:
            pattern = re.compile(
                rf"^\s*[@＠]\s*{re.escape(alias)}"
                r"(?:[@＠]微信)?"
                r"(?=$|[\s,，:：;；])[\s,，:：;；]*"
            )
            updated, count = pattern.subn("", cleaned, count=1)
            if count:
                cleaned = updated
                removed = True
                matched = True
                break
        if not matched:
            break
    return cleaned.lstrip() if removed and cleaned.strip() else original


def text_component_value_hash(message: str, mentions: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"message": message, "mentions": mentions},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def chunk_text_for_delivery(text: str, max_chars: int | None = None) -> list[str]:
    """Split a message at readable boundaries without losing its content."""
    value = str(text or "").strip()
    if not value:
        return []
    limit = max(
        240,
        int(
            max_chars
            or os.environ.get(
                "WECOM_ANDROID_TEXT_CHUNK_CHARS",
                str(DEFAULT_TEXT_CHUNK_CHARS),
            )
        ),
    )
    if len(value) <= limit:
        return [value]

    body_limit = max(200, limit - 16)
    raw_parts: list[str] = []
    remainder = value
    while len(remainder) > body_limit:
        floor = max(1, int(body_limit * 0.55))
        cut = -1
        for marker in (
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            ". ",
            "! ",
            "? ",
            "；",
            "; ",
            "，",
            ", ",
        ):
            candidate = remainder.rfind(marker, floor, body_limit + 1)
            if candidate >= floor:
                cut = max(cut, candidate + len(marker))
        if cut < floor:
            cut = body_limit
        part = remainder[:cut].strip()
        if part:
            raw_parts.append(part)
        remainder = remainder[cut:].strip()
    if remainder:
        raw_parts.append(remainder)
    if len(raw_parts) <= 1:
        return raw_parts or [value]
    total = len(raw_parts)
    return [
        f"[{index}/{total}]\n{part}"
        for index, part in enumerate(raw_parts, start=1)
    ]


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


def find_composer_nodes(
    root: ET.Element,
    *,
    package: str = PACKAGE,
) -> list[ET.Element]:
    """Find the bottom chat composer across WeCom's obfuscated resource IDs."""
    known = [
        node
        for node in root.iter("node")
        if str(node.attrib.get("resource-id") or "").startswith(f"{package}:id/")
        and any(
            str(node.attrib.get("resource-id") or "").endswith(suffix)
            for suffix in COMPOSER_RESOURCE_SUFFIXES
        )
        and node.attrib.get("package") in {None, "", package}
    ]
    if known:
        return known

    try:
        screen_bottom = parse_bounds(root.attrib.get("bounds", ""))[3]
    except BridgeError:
        screen_bottom = 0
        for candidate in root.iter("node"):
            try:
                screen_bottom = max(
                    screen_bottom,
                    parse_bounds(candidate.attrib.get("bounds", ""))[3],
                )
            except BridgeError:
                continue
    semantic: list[ET.Element] = []
    for node in root.iter("node"):
        if node.attrib.get("package") != package:
            continue
        if node.attrib.get("class") != "android.widget.EditText":
            continue
        try:
            bounds = parse_bounds(node.attrib.get("bounds", ""))
        except BridgeError:
            continue
        value = normalize_visible_text(node.attrib.get("text"))
        placeholder = value.startswith(("发消息", "Message", "Send a message"))
        near_bottom = bool(screen_bottom and bounds[1] >= int(screen_bottom * 0.70))
        if placeholder or near_bottom:
            semantic.append(node)
    return sorted(
        semantic,
        key=lambda node: bounds_center(node.attrib.get("bounds", ""))[1],
    )


def find_attachment_button_nodes(
    root: ET.Element,
    *,
    package: str = PACKAGE,
    composers: list[ET.Element] | None = None,
) -> list[ET.Element]:
    """Find the rightmost composer-adjacent attachment icon without parent taps."""
    composer_candidates = composers if composers is not None else find_composer_nodes(
        root,
        package=package,
    )
    try:
        composer_bounds = (
            parse_bounds(composer_candidates[-1].attrib.get("bounds", ""))
            if composer_candidates
            else (0, 0, 0, 0)
        )
    except BridgeError:
        composer_bounds = (0, 0, 0, 0)

    def beside_composer(node: ET.Element) -> bool:
        try:
            bounds = parse_bounds(node.attrib.get("bounds", ""))
        except BridgeError:
            return False
        if composer_bounds == (0, 0, 0, 0):
            return True
        vertical_overlap = min(bounds[3], composer_bounds[3]) - max(
            bounds[1], composer_bounds[1]
        )
        return vertical_overlap > 0 and bounds[0] >= composer_bounds[2] - 8

    known = [
        node
        for node in find_nodes_by_resource_suffix(
            root,
            ATTACHMENT_RESOURCE_SUFFIXES,
            package=package,
        )
        if beside_composer(node)
    ]
    candidates = known
    if not candidates and composer_bounds != (0, 0, 0, 0):
        candidates = [
            node
            for node in root.iter("node")
            if node.attrib.get("package") == package
            and node.attrib.get("class") in {
                "android.widget.ImageView",
                "android.widget.ImageButton",
            }
            and beside_composer(node)
        ]
    return sorted(
        candidates,
        key=lambda node: bounds_center(node.attrib.get("bounds", ""))[0],
    )


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
        "android_dual_tmux_target": str(
            existing.get("android_dual_tmux_target") or DEFAULT_DUAL_TMUX_TARGET
        ),
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
        "surface_recovery_cooldown_seconds": bounded_float(
            existing.get("surface_recovery_cooldown_seconds"), 300.0, 30.0, 3600.0
        ),
        "reconcile_seconds": bounded_float(
            existing.get("reconcile_seconds"), 20.0, 5.0, 600.0
        ),
        "history_scan_seconds": bounded_float(
            existing.get("history_scan_seconds"), 180.0, 60.0, 3600.0
        ),
        "history_scan_pages": bounded_int(
            existing.get("history_scan_pages"), 3, 0, 8
        ),
        "inbound_image_original_timeout_seconds": bounded_float(
            existing.get("inbound_image_original_timeout_seconds"),
            180.0,
            10.0,
            1800.0,
        ),
        "inbound_image_save_timeout_seconds": bounded_float(
            existing.get("inbound_image_save_timeout_seconds"),
            45.0,
            5.0,
            300.0,
        ),
        "allow_inbound_image_preview_fallback": bool(
            existing.get("allow_inbound_image_preview_fallback", False)
        ),
        "inbound_media_max_recovery_failures": bounded_int(
            existing.get("inbound_media_max_recovery_failures"), 8, 1, 100
        ),
        "max_send_file_bytes": bounded_int(
            existing.get("max_send_file_bytes"), 100 * 1024 * 1024, 1, 1024 * 1024 * 1024
        ),
        "local_api_host": "127.0.0.1",
        "local_api_port": bounded_int(existing.get("local_api_port"), 19581, 1024, 65535),
        "local_api_token": str(existing.get("local_api_token") or secrets.token_hex(32)),
        "disable_host_media_automount": bool(existing.get("disable_host_media_automount", True)),
        "minimum_free_data_bytes": bounded_int(
            existing.get("minimum_free_data_bytes"),
            768 * 1024 * 1024,
            128 * 1024 * 1024,
            16 * 1024 * 1024 * 1024,
        ),
        "auto_prune_safe_logs": bool(existing.get("auto_prune_safe_logs", True)),
        "auto_prune_safe_image_caches": bool(
            existing.get("auto_prune_safe_image_caches", True)
        ),
        "auto_trim_package_caches": bool(
            existing.get("auto_trim_package_caches", True)
        ),
        "ui_dump_total_timeout_seconds": bounded_float(
            existing.get("ui_dump_total_timeout_seconds"),
            DEFAULT_UI_DUMP_TOTAL_TIMEOUT_SECONDS,
            2.0,
            60.0,
        ),
        "ui_dump_attempt_timeout_seconds": bounded_float(
            existing.get("ui_dump_attempt_timeout_seconds"),
            DEFAULT_UI_DUMP_ATTEMPT_TIMEOUT_SECONDS,
            1.0,
            15.0,
        ),
        "storage_prune_headroom_bytes": bounded_int(
            existing.get("storage_prune_headroom_bytes"),
            256 * 1024 * 1024,
            0,
            2 * 1024 * 1024 * 1024,
        ),
        "dismiss_foreground_conflicts": bool(
            existing.get("dismiss_foreground_conflicts", False)
        ),
        "foreground_conflict_packages": unique_nonempty(
            existing.get("foreground_conflict_packages") or []
        ),
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


def resource_id_has_suffix(
    node: ET.Element,
    suffixes: tuple[str, ...],
    *,
    package: str = PACKAGE,
) -> bool:
    resource_id = str(node.attrib.get("resource-id") or "")
    return node.attrib.get("package") == package and any(
        resource_id.endswith(suffix) for suffix in suffixes
    )


def find_nodes_by_resource_suffix(
    root: ET.Element,
    suffixes: tuple[str, ...],
    *,
    text: str | None = None,
    package: str = PACKAGE,
) -> list[ET.Element]:
    expected = normalize_visible_text(text) if text is not None else None
    return [
        node
        for node in root.iter("node")
        if resource_id_has_suffix(node, suffixes, package=package)
        and (expected is None or node_text(node) == expected)
    ]


def node_resource_has_any_suffix(
    node: ET.Element,
    suffixes: tuple[str, ...],
    *,
    package: str = PACKAGE,
) -> bool:
    """Match an app resource while tolerating sparse test/accessibility dumps."""
    resource_id = str(node.attrib.get("resource-id") or "")
    node_package = str(node.attrib.get("package") or "")
    return (
        node_package in {"", package}
        and resource_id.startswith(f"{package}:id/")
        and any(resource_id.endswith(suffix) for suffix in suffixes)
    )


def find_message_rows(
    root: ET.Element,
    *,
    package: str = PACKAGE,
) -> list[ET.Element]:
    """Find exact chat rows across signed WeCom resource-ID revisions.

    Known IDs are authoritative. The fallback is deliberately limited to
    direct children of a native ``ListView`` so quick actions, the composer,
    and unrelated page text cannot be interpreted as chat messages.
    """
    known = [
        node
        for node in root.iter("node")
        if node_resource_has_any_suffix(
            node,
            MESSAGE_ROW_RESOURCE_SUFFIXES,
            package=package,
        )
    ]
    if known:
        return known

    semantic: list[ET.Element] = []
    for message_list in root.iter("node"):
        if message_list.attrib.get("class") != "android.widget.ListView":
            continue
        if str(message_list.attrib.get("package") or "") not in {"", package}:
            continue
        for row in message_list.findall("node"):
            if str(row.attrib.get("package") or "") not in {"", package}:
                continue
            if row.attrib.get("class") not in {
                "android.widget.FrameLayout",
                "android.widget.LinearLayout",
                "android.widget.RelativeLayout",
            }:
                continue
            try:
                _, top, _, bottom = parse_bounds(row.attrib.get("bounds", ""))
            except BridgeError:
                continue
            if bottom - top <= 8:
                continue
            has_content = any(
                normalize_visible_text(
                    node.attrib.get("text") or node.attrib.get("content-desc")
                )
                or node.attrib.get("class") == "android.widget.ImageView"
                for node in row.iter("node")
                if node is not row
            )
            if has_content:
                semantic.append(row)
    return semantic


_DOCUMENT_FILENAME_RE = re.compile(
    r"\.(?:7z|csv|docx?|epub|gz|json|md|od[st]|pdf|pptx?|rar|rtf|tar|tex|txt|"
    r"xlsx?|xml|zip)$",
    re.IGNORECASE,
)
_DOCUMENT_SIZE_RE = re.compile(r"^\d+(?:\.\d+)?\s*(?:[KMGT]?B|[KMGT])$", re.IGNORECASE)


def find_document_filename_nodes(
    row: ET.Element,
    *,
    package: str = PACKAGE,
) -> list[ET.Element]:
    known = [
        node
        for node in row.iter("node")
        if node_text(node)
        and node_resource_has_any_suffix(
            node,
            DOCUMENT_FILENAME_RESOURCE_SUFFIXES,
            package=package,
        )
    ]
    if known:
        return known
    return [
        node
        for node in row.iter("node")
        if str(node.attrib.get("package") or "") in {"", package}
        and node.attrib.get("class") == "android.widget.TextView"
        and _DOCUMENT_FILENAME_RE.search(normalize_filename_text(node_text(node)))
    ]


def find_document_size_nodes(
    row: ET.Element,
    *,
    package: str = PACKAGE,
) -> list[ET.Element]:
    known = [
        node
        for node in row.iter("node")
        if node_text(node)
        and node_resource_has_any_suffix(
            node,
            DOCUMENT_SIZE_RESOURCE_SUFFIXES,
            package=package,
        )
    ]
    if known:
        return known
    return [
        node
        for node in row.iter("node")
        if str(node.attrib.get("package") or "") in {"", package}
        and node.attrib.get("class") == "android.widget.TextView"
        and _DOCUMENT_SIZE_RE.fullmatch(normalize_visible_text(node_text(node)))
    ]


def find_message_body_nodes(
    row: ET.Element,
    *,
    package: str = PACKAGE,
    semantic_fallback: bool = True,
) -> list[ET.Element]:
    known = [
        node
        for node in row.iter("node")
        if node_text(node)
        and node_resource_has_any_suffix(
            node,
            MESSAGE_BODY_RESOURCE_SUFFIXES,
            package=package,
        )
    ]
    if known or not semantic_fallback:
        return known

    document_nodes = {
        id(node)
        for node in (
            find_document_filename_nodes(row, package=package)
            + find_document_size_nodes(row, package=package)
        )
    }
    candidates: list[ET.Element] = []
    for node in row.iter("node"):
        text = node_text(node)
        resource = str(node.attrib.get("resource-id") or "")
        if (
            not text
            or id(node) in document_nodes
            or text in MESSAGE_CHROME_TEXT
            or MESSAGE_TIME_RE.fullmatch(text)
            or QUOTE_RESOURCE_RE.search(resource)
            or node.attrib.get("class") != "android.widget.TextView"
            or str(node.attrib.get("package") or "") not in {"", package}
        ):
            continue
        candidates.append(node)
    if not candidates:
        return []

    clickable = [node for node in candidates if node.attrib.get("clickable") == "true"]
    if clickable:
        return clickable

    # In old/sparse accessibility trees a sender label is above the message.
    # Prefer the lowest bounded leaf rather than merging every visible label.
    bounded: list[tuple[int, ET.Element]] = []
    for node in candidates:
        try:
            _, top, _, _ = parse_bounds(node.attrib.get("bounds", ""))
        except BridgeError:
            continue
        bounded.append((top, node))
    if bounded:
        lowest_top = max(top for top, _ in bounded)
        return [node for top, node in bounded if top == lowest_top]
    return candidates[-1:]


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
    titles = find_nodes_by_resource_suffix(root, CHAT_TITLE_RESOURCE_SUFFIXES)
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
    body_node_ids = {id(node) for node in body_nodes}
    try:
        row_left, _, row_right, _ = parse_bounds(row.attrib.get("bounds", ""))
    except BridgeError:
        row_left, row_right = 0, 1080
    for node in row.iter("node"):
        resource = node.attrib.get("resource-id", "")
        text = node_text(node)
        bounds = node.attrib.get("bounds", "")
        if not avatar_bounds:
            known_avatar = node_resource_has_any_suffix(
                node,
                MESSAGE_AVATAR_RESOURCE_SUFFIXES,
            )
            geometric_avatar = False
            if node.attrib.get("class") == "android.widget.ImageView":
                try:
                    left, top, right, bottom = parse_bounds(bounds)
                    width = right - left
                    height = bottom - top
                    geometric_avatar = (
                        40 <= width <= 150
                        and 40 <= height <= 150
                        and (
                            right <= row_left + 170
                            or left >= row_right - 170
                        )
                    )
                except BridgeError:
                    pass
            if known_avatar or geometric_avatar:
                avatar_bounds = bounds
        if text in {"＠微信", "@微信"}:
            external_marker = True
            continue
        if (
            not text
            or id(node) in body_node_ids
            or text in MESSAGE_CHROME_TEXT
            or MESSAGE_TIME_RE.fullmatch(text)
            or QUOTE_RESOURCE_RE.search(resource)
            or node_resource_has_any_suffix(
                node,
                MESSAGE_BODY_RESOURCE_SUFFIXES
                + DOCUMENT_FILENAME_RESOURCE_SUFFIXES
                + DOCUMENT_SIZE_RESOURCE_SUFFIXES,
            )
        ):
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
        self.outbound_marker_path = PRIVATE / "wecom_android_outbound.active.json"
        device_key = short_hash(self.serial or "unconfigured", 10)
        self.ui_dump_lock_path = PRIVATE / f"wecom_android_uiautomator_{device_key}.lock"
        self.ui_dump_remote_path = (
            f"/sdcard/labcanvas_wecom_{device_key}_{os.getpid()}.xml"
        )
        self._ui_dump_thread_lock = threading.Lock()
        self.control_priority_path = Path(
            str(config.get("control_priority_path") or DEFAULT_CONTROL_PRIORITY)
        ).expanduser().resolve()
        self.android_layout_path = Path(
            str(config.get("android_layout_path") or DEFAULT_ANDROID_LAYOUT)
        ).expanduser().resolve()
        self.android_dual_tmux_target = str(
            config.get("android_dual_tmux_target") or DEFAULT_DUAL_TMUX_TARGET
        ).strip()
        self._dual_refresh_lock = threading.Lock()
        self._dual_refresh_requested = False
        self._last_dual_refresh_at = 0.0
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
        self._outbound_waiter_lock = threading.Lock()
        self._outbound_waiters = 0
        self._passive_control = threading.local()
        self.device_tuning_timeout_seconds = bounded_float(
            config.get("device_tuning_timeout_seconds"), 3.0, 1.0, 10.0
        )
        self._device_tuning_attempted = False
        self.surface_recovery_cooldown_seconds = bounded_float(
            config.get("surface_recovery_cooldown_seconds"), 300.0, 30.0, 3600.0
        )
        self._next_surface_recovery_at = 0.0
        self.minimum_free_data_bytes = bounded_int(
            config.get("minimum_free_data_bytes"),
            768 * 1024 * 1024,
            128 * 1024 * 1024,
            16 * 1024 * 1024 * 1024,
        )
        self.auto_prune_safe_logs = bool(config.get("auto_prune_safe_logs", True))
        self.auto_prune_safe_image_caches = bool(
            config.get("auto_prune_safe_image_caches", True)
        )
        self.auto_trim_package_caches = bool(
            config.get("auto_trim_package_caches", True)
        )
        self.inbound_media_max_recovery_failures = bounded_int(
            config.get("inbound_media_max_recovery_failures"), 8, 1, 100
        )
        self.storage_prune_headroom_bytes = bounded_int(
            config.get("storage_prune_headroom_bytes"),
            256 * 1024 * 1024,
            0,
            2 * 1024 * 1024 * 1024,
        )
        self._safe_log_prune_attempted = False
        self._last_storage_probe_at = 0.0
        self._storage_status: dict[str, Any] = {
            "available_bytes": None,
            "used_percent": None,
            "checked_at": "",
        }
        self._poll_health: dict[str, Any] = {
            "started_at": now_iso(),
            "last_poll_attempt_at": "",
            "last_poll_success_at": "",
            "last_poll_error": "",
            "poll_in_progress": False,
            "consecutive_poll_failures": 0,
            "last_recovery_at": "",
            "last_recovery_action": "",
            "last_recovery_attempt_at": "",
            "last_recovery_failure_at": "",
            "last_recovery_error": "",
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
            conn.execute(
                "UPDATE observed_messages SET status = 'media_blocked', retry_after = '' "
                "WHERE status = 'pending' AND failure_count >= ?",
                (self.inbound_media_max_recovery_failures,),
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

    def outbound_waiting(self) -> bool:
        with self._outbound_waiter_lock:
            return self._outbound_waiters > 0

    def external_control_priority(self) -> dict[str, Any] | None:
        """Let explicit cross-process device actions preempt passive polling."""
        return read_active_priority(
            self.control_priority_path,
            exclude_pid=os.getpid(),
        )

    def passive_control_deferred(self) -> tuple[bool, str]:
        if self.outbound_waiting():
            return True, "wecom_outbound"
        priority = self.external_control_priority()
        if priority is not None:
            return True, str(priority.get("purpose") or "external_android_control")
        return False, ""

    @contextmanager
    def outbound_serialized(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> Iterator[None]:
        """Prioritize a queued send over the next passive polling segment."""
        with self._outbound_waiter_lock:
            self._outbound_waiters += 1
            if self._outbound_waiters == 1:
                try:
                    write_private_json(
                        self.outbound_marker_path,
                        {
                            "pid": os.getpid(),
                            "started_at": now_iso(),
                        },
                    )
                except OSError:
                    # The GUI lock still protects correctness. The marker only
                    # prevents the external supervisor from hot-reloading a
                    # relay that is waiting to send.
                    pass
        try:
            try:
                with self.serialized(timeout_seconds=timeout_seconds):
                    try:
                        yield
                    finally:
                        self.restore_dual_layout_locked()
            finally:
                self.refresh_dual_mirror_if_needed()
        finally:
            with self._outbound_waiter_lock:
                self._outbound_waiters = max(0, self._outbound_waiters - 1)
                if self._outbound_waiters == 0:
                    try:
                        self.outbound_marker_path.unlink(missing_ok=True)
                    except OSError:
                        pass

    @contextmanager
    def serialized_ui_dump(
        self,
        *,
        timeout_seconds: float = 30.0,
    ) -> Iterator[None]:
        """Permit only one UIAutomator registration per device at a time."""
        timeout = max(0.5, float(timeout_seconds))
        deadline = time.monotonic() + timeout
        acquired = self._ui_dump_thread_lock.acquire(timeout=timeout)
        if not acquired:
            raise BridgeError("Android UI hierarchy capture is busy")
        self.ui_dump_lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with self.ui_dump_lock_path.open("a+", encoding="utf-8") as handle:
                while True:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError as exc:
                        if time.monotonic() >= deadline:
                            raise BridgeError(
                                "Android UI hierarchy capture exceeded its serialization timeout"
                            ) from exc
                        time.sleep(0.1)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            self._ui_dump_thread_lock.release()

    @contextmanager
    def passive_serialized(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> Iterator[None]:
        """Yield passive GUI ownership while allowing explicit work to preempt it."""
        self.assert_passive_control_available()
        try:
            with self.serialized(timeout_seconds=timeout_seconds):
                self.assert_passive_control_available()
                previous = bool(getattr(self._passive_control, "active", False))
                self._passive_control.active = True
                try:
                    yield
                finally:
                    self._passive_control.active = previous
                    self.restore_dual_layout_locked()
        finally:
            self.refresh_dual_mirror_if_needed()

    def dual_layout_requested(self) -> bool:
        try:
            return self.android_layout_path.read_text(encoding="utf-8").strip() == "dual"
        except OSError:
            return False

    def dual_virtual_display_id(self) -> int | None:
        if not self.dual_layout_requested():
            return None
        output = self.adb_shell("am", "stack", "list", timeout=15, check=False)
        display_ids = {
            int(value)
            for value in re.findall(r"\bdisplayId=(\d+)\b", output)
            if int(value) > 0
        }
        return max(display_ids) if display_ids else None

    def dual_virtual_wecom_drawn(self, display_id: int) -> bool:
        output = self.adb_shell(
            "dumpsys", "window", "displays", timeout=15, check=False
        )
        marker = f"Display: mDisplayId={display_id}"
        start = output.find(marker)
        if start < 0:
            return False
        section = output[start + len(marker) :]
        next_display = section.find("Display: mDisplayId=")
        if next_display >= 0:
            section = section[:next_display]
        return self.package in section

    def request_dual_mirror_refresh(self) -> None:
        with self._dual_refresh_lock:
            self._dual_refresh_requested = True

    def refresh_dual_mirror_if_needed(self) -> bool:
        """Restart only a stale virtual mirror after releasing Android control."""
        with self._dual_refresh_lock:
            if not self._dual_refresh_requested:
                return False
            if not self.dual_layout_requested() or not self.android_dual_tmux_target:
                self._dual_refresh_requested = False
                return False
            now = time.monotonic()
            if now - self._last_dual_refresh_at < 3.0:
                return False
            self._dual_refresh_requested = False
            self._last_dual_refresh_at = now
        try:
            process = subprocess.run(
                [
                    "tmux",
                    "respawn-pane",
                    "-k",
                    "-t",
                    self.android_dual_tmux_target,
                ],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            process = None
        if process is None or process.returncode != 0:
            with self._dual_refresh_lock:
                self._dual_refresh_requested = True
            return False
        self.record_recovery("dual_virtual_mirror_refresh")
        return True

    def restore_dual_layout_locked(self) -> bool:
        """Restore both review panes before releasing shared GUI ownership."""
        try:
            virtual_display = self.dual_virtual_display_id()
            if virtual_display is None:
                return False
            self.adb_shell(
                "am",
                "start",
                "--display",
                "0",
                "-f",
                "0x04000000",
                "-n",
                PERSONAL_WECHAT_MAIN_ACTIVITY,
                timeout=25,
                check=False,
            )
            self.adb_shell(
                "am",
                "start",
                "--display",
                str(virtual_display),
                "-f",
                "0x04000000",
                "-n",
                str(
                    self.config.get("launch_component")
                    or f"{self.package}/{WECOM_LAUNCH_COMPONENT}"
                ),
                timeout=25,
                check=False,
            )
            for attempt in range(4):
                if self.dual_virtual_wecom_drawn(virtual_display):
                    break
                if attempt < 3:
                    time.sleep(0.25)
            else:
                # WeCom is single-task on this Android build. A relay restart
                # can migrate the task while leaving the old virtual surface
                # alive but blank. Recreate only that mirror after the shared
                # Android lock is released.
                self.request_dual_mirror_refresh()
            return True
        except (BridgeError, OSError, subprocess.SubprocessError):
            # Display restoration is best-effort evidence/UI hygiene. It must
            # never turn a verified message or artifact send into a failure.
            return False

    def assert_passive_control_available(self) -> None:
        if self.outbound_waiting():
            raise BridgeError("WECOM_ANDROID_PREEMPTED: wecom_outbound")
        priority = self.external_control_priority()
        if priority is None:
            return
        purpose = str(priority.get("purpose") or "external_android_control")
        raise BridgeError(f"WECOM_ANDROID_PREEMPTED: {purpose}")

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
        if bool(getattr(self._passive_control, "active", False)):
            self.assert_passive_control_available()
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

    def device_data_storage_status(self, *, force: bool = False) -> dict[str, Any]:
        """Return a bounded cached `/data` capacity probe for recovery gates."""
        now = time.monotonic()
        if not force and self._storage_status.get("checked_at") and (
            now - self._last_storage_probe_at
        ) < 60.0:
            return dict(self._storage_status)
        output = self.adb_shell("df", "-Pk", "/data", timeout=15, check=False)
        available_bytes: int | None = None
        used_percent: int | None = None
        for line in reversed(output.splitlines()):
            fields = line.split()
            if len(fields) < 6 or not fields[3].isdigit():
                continue
            available_bytes = int(fields[3]) * 1024
            percent = fields[4].rstrip("%")
            used_percent = int(percent) if percent.isdigit() else None
            break
        self._last_storage_probe_at = now
        self._storage_status = {
            "available_bytes": available_bytes,
            "used_percent": used_percent,
            "checked_at": now_iso(),
        }
        return dict(self._storage_status)

    def ensure_device_storage(self) -> dict[str, Any]:
        status = self.device_data_storage_status()
        available = status.get("available_bytes")
        prune_threshold = (
            self.minimum_free_data_bytes + self.storage_prune_headroom_bytes
        )
        if (
            isinstance(available, int)
            and available < prune_threshold
            and (
                self.auto_trim_package_caches
                or self.auto_prune_safe_image_caches
                or self.auto_prune_safe_logs
            )
            and not self._safe_log_prune_attempted
        ):
            self._safe_log_prune_attempted = True
            if self.auto_trim_package_caches:
                self.trim_android_package_caches(prune_threshold)
            if self.auto_prune_safe_image_caches:
                self.prune_safe_external_image_caches()
            if self.auto_prune_safe_logs:
                self.prune_safe_external_logs()
            status = self.device_data_storage_status(force=True)
            available = status.get("available_bytes")
        if isinstance(available, int) and available < self.minimum_free_data_bytes:
            available_mib = available // (1024 * 1024)
            required_mib = self.minimum_free_data_bytes // (1024 * 1024)
            raise BridgeError(
                "Android /data storage is critically low "
                f"({available_mib} MiB free; {required_mib} MiB required); "
                "automated relaunch and navigation are paused"
            )
        return status

    def trim_android_package_caches(self, desired_free_bytes: int) -> None:
        """Ask Android to remove only package-managed, recreatable caches."""

        # Older Android package-manager shells can parse a large bare byte
        # count through a signed integer.  A MiB-suffixed value keeps the
        # request bounded and has the same meaning without overflow risk.
        mib = 1024 * 1024
        desired_mib = max(1, (max(0, int(desired_free_bytes)) + mib - 1) // mib)
        self.adb_shell(
            "pm",
            "trim-caches",
            f"{desired_mib}M",
            timeout=180,
            check=False,
        )
        self.record_recovery("safe_android_package_caches_trimmed")

    def prune_safe_external_logs(self) -> None:
        """Remove only disposable WeCom external logs under a fixed allowlist."""
        self.adb_shell("rm", "-rf", *SAFE_EXTERNAL_LOG_DIRS, timeout=120, check=False)
        self.adb_shell("mkdir", "-p", *SAFE_EXTERNAL_LOG_DIRS, timeout=30, check=False)
        self.record_recovery("safe_wecom_external_logs_pruned")

    def prune_safe_external_image_caches(self) -> None:
        """Remove only recreated WeCom image thumbnails, never attachment files."""
        self.adb_shell(
            "rm",
            "-rf",
            *SAFE_EXTERNAL_IMAGE_CACHE_DIRS,
            timeout=120,
            check=False,
        )
        self.adb_shell(
            "mkdir",
            "-p",
            *SAFE_EXTERNAL_IMAGE_CACHE_DIRS,
            timeout=30,
            check=False,
        )
        self.record_recovery("safe_wecom_external_image_caches_pruned")

    def prepare_device(self) -> None:
        self.disable_host_automount()
        if self.adb("get-state", timeout=10).stdout.strip() != "device":
            raise BridgeError("configured Android device is not authorized")
        packages = self.adb_shell(
            "pm", "list", "packages", self.package, timeout=10
        )
        if f"package:{self.package}" not in packages:
            raise BridgeError("official WeCom package is not installed on the device")
        self.ensure_device_storage()
        keyguard = self.adb_shell("dumpsys", "window", timeout=20, check=False)
        if "isStatusBarKeyguard=true" in keyguard:
            raise BridgeError("Android keyguard is locked")
        if self._device_tuning_attempted:
            return

        # These idempotent settings improve GUI stability but are not chat
        # readiness gates. Apply them once per relay lifetime with a short
        # deadline so a slow Android shell cannot monopolize the exact-chat
        # lock and silence inbound polling or artifact delivery.
        self._device_tuning_attempted = True
        commands = [
            ("settings", "put", "global", "window_animation_scale", "0"),
            ("settings", "put", "global", "transition_animation_scale", "0"),
            ("settings", "put", "global", "animator_duration_scale", "0"),
            ("settings", "put", "system", "accelerometer_rotation", "0"),
            ("settings", "put", "system", "user_rotation", "0"),
            ("svc", "power", "stayon", "true"),
        ]
        for command in commands:
            try:
                self.adb_shell(
                    *command,
                    timeout=self.device_tuning_timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                break

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

    def current_activity(self) -> str:
        output = str(
            self.adb_shell(
                "dumpsys", "activity", "activities", timeout=20, check=False
            )
        )
        for pattern in (
            r"mResumedActivity:.*?\s([A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+)",
            r"topResumedActivity=.*?\s([A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+)",
            r"\* Hist #0: ActivityRecord\{[^}]*\s([A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+)",
        ):
            match = re.search(pattern, output)
            if match:
                return match.group(1)
        return ""

    def authentication_gate_reason(self, root: ET.Element | None = None) -> str:
        if root is not None:
            if is_security_gate(root):
                return "protected login, OAuth, permission, or enterprise-selection surface"
            # A supplied hierarchy is the authoritative snapshot for this
            # navigation decision. Keep this predicate pure so callers and
            # offline tests never issue a second, potentially inconsistent ADB
            # query after already capturing the screen state.
            return ""
        activity = self.current_activity()
        if activity_is_authentication_gate(activity):
            return f"protected activity {activity}"
        return ""

    def ensure_navigation_allowed(self, root: ET.Element | None = None) -> None:
        reason = self.authentication_gate_reason(root)
        if reason:
            raise BridgeError(
                f"WeCom authentication is in progress ({reason}); "
                "automated navigation is paused"
            )

    def wecom_is_foreground(self, root: ET.Element | None = None) -> bool:
        """Use the focused Android activity when UIAutomator metadata is stale."""
        if root is not None and self.package in hierarchy_packages(root):
            return True
        return self.current_package() == self.package

    def dismiss_foreground_conflict(self) -> str:
        """Close only an explicitly configured app that prevents WeCom focus."""
        if not bool(self.config.get("dismiss_foreground_conflicts", False)):
            return ""
        conflicts = set(
            unique_nonempty(self.config.get("foreground_conflict_packages") or [])
        )
        conflicts.discard(self.package)
        focused_package = self.current_package()
        if focused_package not in conflicts:
            return ""
        self.adb_shell("am", "force-stop", focused_package, check=False)
        self.record_recovery(f"foreground_conflict:{focused_package}")
        time.sleep(0.8)
        return focused_package

    def start_wecom_component(self) -> None:
        component = str(
            self.config.get("launch_component")
            or f"{self.package}/{WECOM_LAUNCH_COMPONENT}"
        )
        self.adb_shell("am", "start", "-n", component, timeout=30)

    def launch_wecom(self) -> None:
        self.prepare_device()
        try:
            root = self.dump_hierarchy(attempts=1)
        except BridgeError:
            root = None
        self.ensure_navigation_allowed(root)
        if (
            root is not None
            and self.wecom_is_foreground(root)
            and not is_anr_dialog(root)
            and not is_crash_report_dialog(root)
        ):
            return
        self.start_wecom_component()
        conflict_dismissed = False
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                root = self.dump_hierarchy(attempts=1)
            except BridgeError:
                if self.wecom_is_foreground():
                    return
                time.sleep(0.5)
                continue
            if self.dismiss_crash_report_dialog(root):
                self.start_wecom_component()
                continue
            if is_anr_dialog(root):
                self.dismiss_anr_dialog(root)
                continue
            if self.dismiss_recovered_low_storage_dialog(root):
                continue
            self.ensure_navigation_allowed(root)
            if self.wecom_is_foreground(root):
                return
            if not conflict_dismissed and self.dismiss_foreground_conflict():
                conflict_dismissed = True
                self.start_wecom_component()
            time.sleep(0.5)
        raise BridgeError("WeCom did not reach the foreground")

    def dump_hierarchy(self, *, attempts: int = 5) -> ET.Element:
        last_error = ""
        total_timeout = bounded_float(
            self.config.get("ui_dump_total_timeout_seconds"),
            DEFAULT_UI_DUMP_TOTAL_TIMEOUT_SECONDS,
            2.0,
            60.0,
        )
        attempt_timeout = bounded_float(
            self.config.get("ui_dump_attempt_timeout_seconds"),
            DEFAULT_UI_DUMP_ATTEMPT_TIMEOUT_SECONDS,
            1.0,
            15.0,
        )
        deadline = time.monotonic() + total_timeout

        def remaining(cap: float) -> float:
            return max(0.0, min(cap, deadline - time.monotonic()))

        def bounded_sleep(seconds: float) -> None:
            delay = remaining(seconds)
            if delay > 0:
                time.sleep(delay)

        with self.serialized_ui_dump(timeout_seconds=total_timeout):
            try:
                for attempt in range(max(1, attempts)):
                    if remaining(attempt_timeout) <= 0:
                        last_error = "UI hierarchy capture exceeded its total deadline"
                        break
                    try:
                        self.adb_shell(
                            "rm",
                            "-f",
                            self.ui_dump_remote_path,
                            timeout=max(0.1, remaining(2.0)),
                            check=False,
                        )
                    except subprocess.TimeoutExpired:
                        last_error = "stale UI hierarchy cleanup timed out"
                        bounded_sleep(min(0.5, 0.2 + attempt * 0.1))
                        continue
                    try:
                        process = self.adb(
                            "shell",
                            "uiautomator",
                            "dump",
                            "--compressed",
                            self.ui_dump_remote_path,
                            timeout=max(0.1, remaining(attempt_timeout)),
                            check=False,
                        )
                    except subprocess.TimeoutExpired:
                        last_error = "UIAutomator dump timed out"
                        bounded_sleep(min(1.0, 0.4 + attempt * 0.15))
                        continue
                    diagnostics = "\n".join(
                        part for part in (process.stdout, process.stderr) if part
                    ).casefold()
                    if any(marker in diagnostics for marker in UIAUTOMATOR_BUSY_MARKERS):
                        last_error = "UIAutomator service is still unregistering"
                        bounded_sleep(min(1.0, 0.4 + attempt * 0.15))
                        continue
                    if remaining(3.0) <= 0:
                        last_error = "UI hierarchy capture exceeded its total deadline"
                        break
                    try:
                        payload = self.adb_shell(
                            "cat",
                            self.ui_dump_remote_path,
                            timeout=max(0.1, remaining(3.0)),
                            check=False,
                        )
                    except subprocess.TimeoutExpired:
                        last_error = "UI hierarchy read timed out"
                        bounded_sleep(0.2)
                        continue
                    try:
                        root = ET.fromstring(payload)
                    except ET.ParseError as exc:
                        last_error = str(exc)
                        bounded_sleep(min(0.75, 0.25 + attempt * 0.1))
                        continue
                    if any(True for _ in root.iter("node")):
                        return root
                    last_error = "empty hierarchy"
                    bounded_sleep(min(0.75, 0.25 + attempt * 0.1))
            finally:
                cleanup_timeout = remaining(1.0)
                if cleanup_timeout > 0:
                    try:
                        self.adb_shell(
                            "rm",
                            "-f",
                            self.ui_dump_remote_path,
                            timeout=max(0.1, cleanup_timeout),
                            check=False,
                        )
                    except subprocess.TimeoutExpired:
                        pass
        raise BridgeError(f"could not read Android UI hierarchy: {last_error}")

    def tap_node(self, root: ET.Element, node: ET.Element) -> None:
        target = clickable_ancestor(root, node)
        x, y = bounds_center(target.attrib.get("bounds", ""))
        self.adb_shell("input", "tap", str(x), str(y))

    def press_back(self) -> None:
        self.ensure_navigation_allowed()
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

    def dismiss_crash_report_dialog(self, root: ET.Element) -> bool:
        """Cancel an Android crash report without ever selecting Report."""
        if not is_crash_report_dialog(root):
            return False
        cancel_nodes = [
            node
            for node in root.iter("node")
            if normalize_visible_text(node_text(node)) in CRASH_REPORT_CANCEL_LABELS
            and node.attrib.get("clickable") == "true"
        ]
        report_nodes = [
            node
            for node in root.iter("node")
            if normalize_visible_text(node_text(node)) in CRASH_REPORT_SUBMIT_LABELS
            and node.attrib.get("clickable") == "true"
        ]
        if len(cancel_nodes) != 1 or not report_nodes:
            raise BridgeError(
                "Android crash dialog does not expose one exact Cancel action"
            )
        self.tap_node(root, cancel_nodes[0])
        self.record_recovery("crash_report_cancelled")
        time.sleep(0.5)
        return True

    def dismiss_recovered_low_storage_dialog(self, root: ET.Element) -> bool:
        """Dismiss only MIUI's non-destructive warning after storage recovers."""
        if not is_low_storage_dialog(root):
            return False
        self.ensure_device_storage()
        dismiss_nodes = [
            node
            for node in root.iter("node")
            if normalize_visible_text(node_text(node)) in LOW_STORAGE_DISMISS_LABELS
            and node.attrib.get("clickable") == "true"
        ]
        if len(dismiss_nodes) != 1:
            raise BridgeError(
                "Android low-storage dialog does not expose one exact Cancel action"
            )
        self.tap_node(root, dismiss_nodes[0])
        self.record_recovery("low_storage_warning_dismissed_after_recovery")
        time.sleep(1.0)
        return True

    def restart_wecom_preserving_session(self, *, reason: str) -> ET.Element:
        """Restart only the app process; never clear data or alter the account."""
        try:
            current_root = self.dump_hierarchy(attempts=1)
        except BridgeError:
            current_root = None
        self.ensure_navigation_allowed(current_root)
        self.ensure_device_storage()
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
            if self.dismiss_crash_report_dialog(root):
                self.start_wecom_component()
                continue
            if is_anr_dialog(root):
                self.dismiss_anr_dialog(root)
                continue
            if self.dismiss_recovered_low_storage_dialog(root):
                continue
            self.ensure_navigation_allowed(root)
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
                    "last_recovery_failure_at": "",
                    "last_recovery_error": "",
                }
            )

    def claim_surface_recovery(self) -> tuple[bool, int]:
        """Rate-limit app-level recovery while leaving poll health degraded."""
        now = time.monotonic()
        with self._health_lock:
            remaining = self._next_surface_recovery_at - now
            if remaining > 0:
                return False, max(1, int(remaining) + 1)
            self._next_surface_recovery_at = (
                now + self.surface_recovery_cooldown_seconds
            )
            self._poll_health["last_recovery_attempt_at"] = now_iso()
        return True, 0

    def record_recovery_failure(self, error: str) -> None:
        with self._health_lock:
            self._poll_health.update(
                {
                    "last_recovery_failure_at": now_iso(),
                    "last_recovery_error": normalize_visible_text(error)[:500],
                }
            )

    def poll_health_snapshot(self) -> dict[str, Any]:
        with self._health_lock:
            health = dict(self._poll_health)
        interval = bounded_float(self.config.get("poll_seconds"), 6.0, 2.0, 120.0)
        idle_stale_seconds = max(180.0, interval * 20.0)
        active_stale_seconds = bounded_float(
            self.config.get("poll_in_progress_stale_seconds"),
            900.0,
            idle_stale_seconds,
            3600.0,
        )
        stale_after_seconds = (
            active_stale_seconds
            if health.get("poll_in_progress")
            else idle_stale_seconds
        )
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
            stale = (
                datetime.now() - reference_time
            ).total_seconds() > stale_after_seconds
        failures = int(health.get("consecutive_poll_failures") or 0)
        health["poll_stale_after_seconds"] = int(stale_after_seconds)
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

    def recover_transport_surface_bounded(self, *, reason: str) -> dict[str, Any]:
        claimed, retry_after_seconds = self.claim_surface_recovery()
        if not claimed:
            return {
                "ok": False,
                "skipped": "cooldown",
                "retry_after_seconds": retry_after_seconds,
            }
        try:
            with self.passive_serialized(timeout_seconds=30.0):
                return self.recover_transport_surface(reason=reason)
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {str(exc)[:500]}"
            self.record_recovery_failure(error_text)
            return {"ok": False, "error": error_text}

    def normalize_chat_surface(self, chat: str) -> ET.Element:
        """Return to the exact chat composer from a stale picker or attachment sheet."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android chat")
        exact_chat_loading_polls = 0
        for _ in range(10):
            package = self.current_package()
            if package == DOCUMENTS_PACKAGE:
                self.press_back()
                continue
            root = self.open_chat(chat)
            visible_title = visible_chat_title(root)
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
            composers = find_composer_nodes(root, package=self.package)
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
                    composers = find_composer_nodes(restored, package=self.package)
                    if composers:
                        return restored
                continue
            if chat_title_matches(visible_title, chat):
                # The external-group title appears before the composer on this
                # older phone. Backing out during that interval walks a valid
                # send from the chat to the conversation list.
                exact_chat_loading_polls += 1
                if exact_chat_loading_polls <= 4:
                    time.sleep(0.4)
                    continue
            exact_chat_loading_polls = 0
            self.press_back()
        raise BridgeError("WeCom exact chat composer could not be restored")

    def open_chat(self, chat: str) -> ET.Element:
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android chat")
        for phase in range(2):
            self.launch_wecom()
            for _ in range(8):
                root = self.dump_hierarchy()
                if self.dismiss_crash_report_dialog(root):
                    self.start_wecom_component()
                    continue
                if self.dismiss_anr_dialog(root):
                    continue
                self.ensure_navigation_allowed(root)
                if chat_title_matches(visible_chat_title(root), chat):
                    return root
                rows = find_nodes_by_resource_suffix(
                    root,
                    CHAT_LIST_ROW_RESOURCE_SUFFIXES,
                    text=chat,
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
                        if self.dismiss_crash_report_dialog(opened):
                            self.start_wecom_component()
                            break
                        if self.dismiss_anr_dialog(opened):
                            continue
                        self.ensure_navigation_allowed(opened)
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
        has_message_rows = bool(find_message_rows(root, package=self.package))
        has_composer = bool(find_composer_nodes(root, package=self.package))
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
                if self.dismiss_crash_report_dialog(root):
                    self.start_wecom_component()
                    continue
                if self.dismiss_anr_dialog(root):
                    continue
                self.ensure_navigation_allowed(root)
                title_nodes = find_nodes_by_resource_suffix(
                    root,
                    CHAT_TITLE_RESOURCE_SUFFIXES,
                    text="消息",
                    package=self.package,
                )
                if title_nodes and any(
                    find_nodes_by_resource_suffix(
                        root,
                        CHAT_LIST_ROW_RESOURCE_SUFFIXES,
                        text=target,
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
            nodes = find_nodes_by_resource_suffix(
                root,
                CHAT_LIST_ROW_RESOURCE_SUFFIXES,
                text=chat,
                package=self.package,
            )
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
                resource_id_has_suffix(
                    node,
                    UNREAD_BADGE_RESOURCE_SUFFIXES,
                    package=self.package,
                )
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
        composers = find_composer_nodes(root, package=self.package)
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
        composers = find_composer_nodes(cleared, package=self.package)
        return bool(composers and not composer_text(composers[-1]))

    def mention_picker(self, *, timeout: float = 5.0) -> ET.Element:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            root = self.dump_hierarchy(attempts=2)
            title = find_nodes_by_resource_suffix(
                root,
                CHAT_TITLE_RESOURCE_SUFFIXES,
                text="选择提醒的人",
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
        composers = find_composer_nodes(root, package=self.package)
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
            sent_at = str(self.component_record(key).get("updated_at") or "")
            return {
                "ok": True,
                "duplicate": True,
                "sent_messages": [text],
                "sent_message_times": {text: sent_at} if sent_at else {},
                "sent_files": [],
                "mentioned_users": exact_mentions,
            }

        parts = chunk_text_for_delivery(text)
        if len(parts) <= 1:
            return self._send_text_chunk_locked(
                chat,
                text,
                task_id=task_id,
                mentions=exact_mentions,
            )

        mentioned_users: list[str] = []
        for index, part in enumerate(parts, start=1):
            result = self._send_text_chunk_locked(
                chat,
                part,
                task_id=f"{task_id}:part:{index}-of-{len(parts)}",
                mentions=exact_mentions if index == 1 else [],
            )
            for name in result.get("mentioned_users") or []:
                if name not in mentioned_users:
                    mentioned_users.append(name)

        self.mark_component(
            key,
            task_id=task_id,
            chat=chat,
            kind="text",
            value_hash=value_hash,
            status="sent",
            details={
                "mentioned_users": mentioned_users,
                "part_count": len(parts),
                "delivery_strategy": "numbered_parts",
            },
        )
        sent_at = str(self.component_record(key).get("updated_at") or "")
        return {
            "ok": True,
            "sent_messages": [text],
            "sent_message_times": {text: sent_at} if sent_at else {},
            "sent_files": [],
            "mentioned_users": mentioned_users,
            "errors": [],
            "part_count": len(parts),
        }

    def _send_text_chunk_locked(
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
            sent_at = str(self.component_record(key).get("updated_at") or "")
            return {
                "ok": True,
                "duplicate": True,
                "sent_messages": [text],
                "sent_message_times": {text: sent_at} if sent_at else {},
                "sent_files": [],
                "mentioned_users": exact_mentions,
            }
        root = self.normalize_chat_surface(chat)
        composers = find_composer_nodes(root, package=self.package)
        if not composers:
            raise BridgeError("WeCom composer is not visible")
        draft = composer_text(composers[-1])
        if draft:
            if not self.recover_stale_automation_draft(chat, draft):
                raise BridgeError("refusing to overwrite a non-empty WeCom draft")
            root = self.normalize_chat_surface(chat)
            composers = find_composer_nodes(root, package=self.package)
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
            send_buttons = find_nodes(root, text="发送", package=self.package)
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
            composers = find_composer_nodes(current, package=self.package)
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
                sent_at = str(self.component_record(key).get("updated_at") or "")
                return {
                    "ok": True,
                    "sent_messages": [text],
                    "sent_message_times": {text: sent_at} if sent_at else {},
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
            composers = find_composer_nodes(root, package=self.package)
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
            plus = find_attachment_button_nodes(
                current,
                package=self.package,
            )
            if not plus:
                raise BridgeError("WeCom attachment menu button is unavailable")
            attachment_button = plus[-1]
            if attachment_button.attrib.get("clickable") == "true":
                self.tap_node(current, attachment_button)
            else:
                # Signed WeCom 5.0.10 exposes the plus icon with a stable
                # resource id and bounds but marks it non-clickable. Its broad
                # clickable parent spans the whole composer, so tapping that
                # parent's centre would focus text instead of opening files.
                x, y = bounds_center(attachment_button.attrib.get("bounds", ""))
                self.adb_shell("input", "tap", str(x), str(y))
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
        delivery_message = strip_redundant_leading_mentions(message, exact_mentions)
        sent_messages: list[str] = []
        sent_message_times: dict[str, str] = {}
        pending_messages: list[str] = []
        sent_files: list[str] = []
        pending_files: list[str] = []
        if delivery_message.strip():
            value_hash = text_component_value_hash(delivery_message, exact_mentions)
            key = self.component_key(task_id, chat, "text", value_hash)
            record = self.component_record(key)
            if str(record.get("status") or "") in {"sent", "deduplicated"}:
                sent_messages.append(message)
                sent_at = str(record.get("updated_at") or "")
                if sent_at:
                    sent_message_times[message] = sent_at
            else:
                pending_messages.append(message)
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
            "sent_message_times": sent_message_times,
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
        delivery_message = strip_redundant_leading_mentions(message, exact_mentions)
        if exact_mentions and not delivery_message.strip():
            raise BridgeError("mentions require a text message")
        if not delivery_message.strip() and not files:
            raise BridgeError("send requires a message and/or artifact")
        outbound_timeout = bounded_float(
            self.config.get("outbound_serialization_timeout_seconds"),
            180.0,
            60.0,
            600.0,
        )
        with self.outbound_serialized(timeout_seconds=outbound_timeout):
            sent_messages: list[str] = []
            sent_message_times: dict[str, str] = {}
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
            if delivery_message.strip() and not errors:
                try:
                    result = self.send_text_resilient_locked(
                        chat,
                        delivery_message,
                        task_id=task_id,
                        mentions=exact_mentions,
                    )
                    if result.get("sent_messages"):
                        sent_messages.append(message)
                        result_times = (
                            result.get("sent_message_times")
                            if isinstance(result.get("sent_message_times"), dict)
                            else {}
                        )
                        sent_at = str(result_times.get(delivery_message) or "")
                        if sent_at:
                            sent_message_times[message] = sent_at
                    mentioned_users.extend(result.get("mentioned_users") or [])
                except Exception as exc:
                    errors.append({"kind": "text", "error": f"{type(exc).__name__}: {str(exc)[:500]}"})
            return {
                "ok": not errors,
                "transport": "wecom_android",
                "chat_id": f"gui:{chat}",
                "sent_messages": sent_messages,
                "sent_message_times": sent_message_times,
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
        rows = find_message_rows(root, package=self.package)
        records: list[dict[str, str]] = []
        for row in rows:
            body_nodes = find_message_body_nodes(
                row,
                package=self.package,
                semantic_fallback=False,
            )
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
                card_nodes = [
                    node
                    for node in row.iter("node")
                    if node.attrib.get("package") == self.package
                    and node.attrib.get("class") == "android.widget.ImageView"
                    and node.attrib.get("resource-id", "").endswith(
                        SHIPINHAO_CARD_THUMBNAIL_RESOURCE_SUFFIX
                    )
                    and node.attrib.get("bounds")
                ]
                if card_nodes:
                    source_kind = SHIPINHAO_CARD_KIND
                    body_nodes = card_nodes
                    image_bounds = str(card_nodes[0].attrib.get("bounds") or "")
                    account_nodes = [
                        node
                        for node in row.iter("node")
                        if node_text(node)
                        and node.attrib.get("resource-id", "").endswith(
                            SHIPINHAO_CARD_ACCOUNT_RESOURCE_SUFFIX
                        )
                    ]
                    source_title = " ".join(
                        unique_nonempty(node_text(node) for node in account_nodes)
                    )
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
                document_nodes = find_document_filename_nodes(
                    row,
                    package=self.package,
                )
                if document_nodes:
                    source_kind = DOCUMENT_KIND
                    document_filename = normalize_filename_text(node_text(document_nodes[0]))
                    document_bounds = str(document_nodes[0].attrib.get("bounds") or "")
                    size_nodes = find_document_size_nodes(
                        row,
                        package=self.package,
                    )
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
            if not body_nodes:
                body_nodes = find_message_body_nodes(
                    row,
                    package=self.package,
                    semantic_fallback=True,
                )
            body = "\n".join(unique_nonempty(node_text(node) for node in body_nodes))
            if source_kind == IMAGE_KIND:
                body = "[图片]"
            elif source_kind == SHIPINHAO_CARD_KIND:
                body = "视频号卡片"
                if source_title:
                    body += f"\n<account>{html.escape(source_title)}</account>"
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
            if source_kind in {IMAGE_KIND, SHIPINHAO_CARD_KIND}:
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
        rows = find_message_rows(root, package=self.package)
        for row in rows:
            filename_nodes = [
                node
                for node in find_document_filename_nodes(
                    row,
                    package=self.package,
                )
                if normalize_filename_text(node_text(node))
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
                    for node in find_document_size_nodes(
                        row,
                        package=self.package,
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
        source_kind = str(record.get("source_kind") or "")
        resource_suffix = (
            SHIPINHAO_CARD_THUMBNAIL_RESOURCE_SUFFIX
            if source_kind == SHIPINHAO_CARD_KIND
            else IMAGE_BUBBLE_RESOURCE_SUFFIX
        )
        rows = find_message_rows(root, package=self.package)
        for row in rows:
            image_nodes = [
                node
                for node in row.iter("node")
                if node.attrib.get("package") == self.package
                and node.attrib.get("class") == "android.widget.ImageView"
                and node.attrib.get("resource-id", "").endswith(
                    resource_suffix
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
        label = "Shipinhao card" if source_kind == SHIPINHAO_CARD_KIND else "image bubble"
        raise BridgeError(f"exact inbound WeCom {label} is not uniquely visible")

    def find_image_node_for_record(
        self,
        chat: str,
        record: dict[str, str],
    ) -> tuple[ET.Element, RawScreenshot, ET.Element]:
        """Locate an exact visual image identity in recent same-chat history."""
        root = self.open_chat(chat)
        root = self.move_chat_to_live_tail(chat, root)
        pages = bounded_int(
            self.config.get("inbound_image_search_pages"),
            8,
            0,
            8,
        )
        last_error = ""
        for page in range(pages + 1):
            screenshot = self.capture_raw_screenshot()
            candidate = record if page == 0 else {**record, "image_bounds": ""}
            try:
                node = self.image_node_for_record(root, screenshot, candidate)
                return root, screenshot, node
            except BridgeError as exc:
                last_error = str(exc)
            if page >= pages:
                break
            self.adb_shell("input", "swipe", "520", "350", "520", "1450", "500")
            time.sleep(0.55)
            root = self.dump_hierarchy(attempts=3)
            if not chat_title_matches(visible_chat_title(root), chat):
                raise BridgeError("WeCom changed chat while locating the image bubble")
        raise BridgeError(last_error or "exact inbound WeCom image bubble is not visible")

    def materialize_shipinhao_card_record(
        self,
        chat: str,
        record: dict[str, str],
    ) -> dict[str, str]:
        """Capture an exact same-chat Shipinhao preview without opening the card."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android card source")
        if str(record.get("direction") or "") != "inbound":
            raise BridgeError("refusing to materialize an outbound WeCom card")
        if str(record.get("source_kind") or "") != SHIPINHAO_CARD_KIND:
            return dict(record)
        fingerprint = str(record.get("fingerprint") or "")
        if not fingerprint:
            raise BridgeError("WeCom Shipinhao card is missing its visual fingerprint")
        target = (
            self.staging_dir
            / "inbound-media"
            / short_hash(chat, 16)
            / f"wecom-shipinhao-card-{fingerprint[:32]}.png"
        )
        capture: RawScreenshot | None = None
        if not (
            target.is_file()
            and target.stat().st_size > 64
            and target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        ):
            root = self.open_chat(chat)
            screenshot = self.capture_raw_screenshot()
            node = self.image_node_for_record(root, screenshot, record)
            capture = self.write_shipinhao_card_preview(
                target,
                record,
                screenshot,
                bounds=str(
                    node.attrib.get("bounds") or record.get("image_bounds") or ""
                ),
            )
            restored = self.open_chat(chat)
            if not chat_title_matches(visible_chat_title(restored), chat):
                raise BridgeError("WeCom changed chat while capturing a Shipinhao card")
        result = dict(record)
        result.update(
            {
                "attachment_path": str(target),
                "attachment_filename": target.name,
                "attachment_size_bytes": str(target.stat().st_size),
                "attachment_sha256": sha256_file(target),
                "attachment_width": str(capture.width if capture else ""),
                "attachment_height": str(capture.height if capture else ""),
                "attachment_capture_kind": "wecom_android_exact_shipinhao_card_preview",
            }
        )
        return result

    def write_shipinhao_card_preview(
        self,
        target: Path,
        record: dict[str, str],
        screenshot: RawScreenshot,
        *,
        bounds: str = "",
    ) -> RawScreenshot:
        """Persist one already-visible exact Finder card preview."""
        capture = crop_raw_screenshot(
            screenshot,
            bounds or str(record.get("image_bounds") or ""),
        )
        write_private_bytes(target, encode_rgba_png(capture))
        return capture

    def materialize_visible_shipinhao_card_record(
        self,
        chat: str,
        record: dict[str, str],
        screenshot: RawScreenshot,
    ) -> dict[str, str]:
        """Capture a history card before its viewport is moved away."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android card source")
        if str(record.get("source_kind") or "") != SHIPINHAO_CARD_KIND:
            return dict(record)
        fingerprint = str(record.get("fingerprint") or "")
        if not fingerprint or not str(record.get("image_visual_id") or ""):
            raise BridgeError("historical Shipinhao card lacks exact visual identity")
        target = (
            self.staging_dir
            / "inbound-media"
            / short_hash(chat, 16)
            / f"wecom-shipinhao-card-{fingerprint[:32]}.png"
        )
        capture = self.write_shipinhao_card_preview(target, record, screenshot)
        result = dict(record)
        result.update(
            {
                "attachment_path": str(target),
                "attachment_filename": target.name,
                "attachment_size_bytes": str(target.stat().st_size),
                "attachment_sha256": sha256_file(target),
                "attachment_width": str(capture.width),
                "attachment_height": str(capture.height),
                "attachment_capture_kind": (
                    "wecom_android_exact_shipinhao_card_history_preview"
                ),
            }
        )
        return result

    def persist_visible_image_preview(
        self,
        chat: str,
        record: dict[str, str],
        screenshot: RawScreenshot,
    ) -> dict[str, str]:
        """Persist an exact inbound image crop while its bubble is visible."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android image source")
        if str(record.get("direction") or "") != "inbound":
            raise BridgeError("refusing to preserve an outbound WeCom image")
        if str(record.get("source_kind") or "") != IMAGE_KIND:
            return dict(record)
        fingerprint = str(record.get("fingerprint") or "")
        bounds = str(record.get("image_bounds") or "")
        expected_visual_id = str(record.get("image_visual_id") or "")
        if not fingerprint or not bounds or not expected_visual_id:
            raise BridgeError("visible WeCom image lacks exact visual identity")
        actual_visual_id = screenshot_region_visual_id(screenshot, bounds)
        if actual_visual_id != expected_visual_id:
            raise BridgeError("visible WeCom image identity changed before capture")
        target = (
            self.staging_dir
            / "inbound-media"
            / short_hash(chat, 16)
            / f"wecom-image-preview-{fingerprint[:32]}.png"
        )
        capture = crop_raw_screenshot(screenshot, bounds)
        write_private_bytes(target, encode_rgba_png(capture))
        result = dict(record)
        result.update(
            {
                "exact_preview_path": str(target),
                "exact_preview_size_bytes": str(target.stat().st_size),
                "exact_preview_sha256": sha256_file(target),
                "exact_preview_width": str(capture.width),
                "exact_preview_height": str(capture.height),
                "exact_preview_capture_kind": (
                    "wecom_android_exact_visible_image_preview"
                ),
            }
        )
        return result

    def image_viewer_nodes(self, root: ET.Element) -> list[ET.Element]:
        return [
            node
            for node in root.iter("node")
            if node.attrib.get("package") == self.package
            and node.attrib.get("resource-id", "").endswith(
                IMAGE_VIEWER_RESOURCE_SUFFIX
            )
            and node.attrib.get("bounds")
        ]

    def original_image_action_nodes(self, root: ET.Element) -> list[ET.Element]:
        return [
            node
            for node in root.iter("node")
            if node.attrib.get("package") == self.package
            and any(
                node_text(node).startswith(prefix)
                for prefix in IMAGE_ORIGINAL_LABEL_PREFIXES
            )
            and node.attrib.get("bounds")
        ]

    def wait_for_image_viewer(self, *, timeout_seconds: float = 8.0) -> ET.Element:
        deadline = time.monotonic() + max(1.0, timeout_seconds)
        last_title = ""
        while time.monotonic() < deadline:
            root = self.dump_hierarchy(attempts=2)
            last_title = visible_chat_title(root)
            # UIAutomator can retain the underlying chat title while the native
            # image viewer is visibly on top. The exact viewer node or its
            # original-image control is the stronger post-tap surface proof.
            if self.image_viewer_nodes(root) or self.original_image_action_nodes(root):
                return root
            time.sleep(0.25)
        raise BridgeError(
            f"WeCom image viewer did not open from the exact bubble (visible title: {last_title!r})"
        )

    def request_original_image(self, root: ET.Element) -> bool:
        """Load the sender's native-resolution image before exporting it."""
        actions = self.original_image_action_nodes(root)
        if not actions:
            return False
        if len(actions) != 1:
            raise BridgeError("WeCom image viewer exposes multiple original-image controls")
        self.tap_node(root, actions[0])
        deadline = time.monotonic() + bounded_float(
            self.config.get("inbound_image_original_timeout_seconds"),
            180.0,
            10.0,
            1800.0,
        )
        while time.monotonic() < deadline:
            current = self.dump_hierarchy(attempts=2)
            visible = hierarchy_visible_texts(current)
            if any(label in visible for label in IMAGE_ORIGINAL_FAILURE_LABELS):
                raise BridgeError("WeCom reported that the original image download failed")
            if not self.original_image_action_nodes(current):
                return True
            time.sleep(0.5)
        raise BridgeError("WeCom original image did not finish loading before timeout")

    def media_store_images(self, *, after_id: int = 0) -> list[MediaStoreImage]:
        projection = (
            "_id:_data:_display_name:_size:width:height:date_added:relative_path"
        )
        command = (
            f"content query --uri {shlex.quote(MEDIASTORE_IMAGES_URI)} "
            f"--projection {shlex.quote(projection)}"
        )
        if after_id > 0:
            command += f" --where {shlex.quote(f'_id>{int(after_id)}')}"
        output = self.adb_shell(command, timeout=30, check=False)
        return parse_media_store_images(output)

    def media_store_max_image_id(self) -> int:
        images = self.media_store_images()
        return max((image.media_id for image in images), default=0)

    def wait_for_saved_image(
        self,
        baseline_id: int,
        *,
        started_at: float,
    ) -> MediaStoreImage:
        deadline = time.monotonic() + bounded_float(
            self.config.get("inbound_image_save_timeout_seconds"),
            45.0,
            5.0,
            300.0,
        )
        stable: dict[int, tuple[int, int]] = {}
        while time.monotonic() < deadline:
            candidates = [
                image
                for image in self.media_store_images(after_id=baseline_id)
                if image.path.startswith(("/storage/emulated/0/", "/sdcard/"))
                and image.size_bytes > 0
                and image.width > 0
                and image.height > 0
                and image.date_added >= int(started_at) - 5
            ]
            for image in candidates:
                previous_size, count = stable.get(image.media_id, (0, 0))
                stable[image.media_id] = (
                    image.size_bytes,
                    count + 1 if previous_size == image.size_bytes else 1,
                )
            ready = [
                image
                for image in candidates
                if stable.get(image.media_id, (0, 0))[1] >= 2
            ]
            if len(ready) == 1:
                return ready[0]
            if len(ready) > 1:
                raise BridgeError(
                    "multiple new Android gallery images appeared during exact image export"
                )
            time.sleep(0.5)
        raise BridgeError("WeCom did not export the original image to Android MediaStore")

    def save_image_from_viewer(self, root: ET.Element) -> MediaStoreImage:
        viewer_nodes = self.image_viewer_nodes(root)
        if not viewer_nodes:
            root = self.dump_hierarchy(attempts=3)
            viewer_nodes = self.image_viewer_nodes(root)
        if not viewer_nodes:
            raise BridgeError("WeCom original image viewer has no exact image surface")
        viewer = max(
            viewer_nodes,
            key=lambda node: (
                parse_bounds(node.attrib.get("bounds", ""))[2]
                - parse_bounds(node.attrib.get("bounds", ""))[0]
            )
            * (
                parse_bounds(node.attrib.get("bounds", ""))[3]
                - parse_bounds(node.attrib.get("bounds", ""))[1]
            ),
        )
        x, y = bounds_center(viewer.attrib.get("bounds", ""))
        baseline_id = self.media_store_max_image_id()
        started_at = time.time()
        self.adb_shell(
            "input",
            "swipe",
            str(x),
            str(y),
            str(x),
            str(y),
            "900",
        )
        deadline = time.monotonic() + 8.0
        action_root: ET.Element | None = None
        save_nodes: list[ET.Element] = []
        while time.monotonic() < deadline:
            action_root = self.dump_hierarchy(attempts=2)
            save_nodes = [
                node
                for node in action_root.iter("node")
                if node.attrib.get("package") == self.package
                and node_text(node) in IMAGE_SAVE_LABELS
                and node.attrib.get("bounds")
            ]
            if save_nodes:
                break
            time.sleep(0.25)
        if action_root is None or len(save_nodes) != 1:
            raise BridgeError("WeCom image menu did not expose one exact save-image action")
        self.tap_node(action_root, save_nodes[0])
        return self.wait_for_saved_image(baseline_id, started_at=started_at)

    def pull_saved_image(
        self,
        chat: str,
        fingerprint: str,
        image: MediaStoreImage,
    ) -> Path:
        maximum = bounded_int(
            self.config.get("max_inbound_file_bytes"),
            200 * 1024 * 1024,
            1,
            1024 * 1024 * 1024,
        )
        if image.size_bytes <= 0 or image.size_bytes > maximum:
            raise BridgeError("saved WeCom image exceeds the inbound size contract")
        if not image.path.startswith(("/storage/emulated/0/", "/sdcard/")):
            raise BridgeError("saved WeCom image is outside shared Android storage")
        filename = safe_file_name(Path(image.display_name or image.path))
        target = (
            self.staging_dir
            / "inbound-media"
            / short_hash(chat, 16)
            / fingerprint[:32]
            / filename
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
            self.adb("pull", image.path, str(temporary), timeout=300)
            if temporary.stat().st_size != image.size_bytes:
                raise BridgeError("saved WeCom image size changed during pull")
            signature = temporary.read_bytes()[:16]
            if not (
                signature.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF8"))
                or (signature.startswith(b"RIFF") and signature[8:12] == b"WEBP")
                or signature[4:12] in {b"ftypheic", b"ftypheix", b"ftypmif1"}
            ):
                raise BridgeError("saved WeCom image has an invalid image signature")
            os.chmod(temporary, 0o600)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def materialize_image_record(
        self,
        chat: str,
        record: dict[str, str],
    ) -> dict[str, str]:
        """Export one exact same-chat image at its native transmitted resolution."""
        if chat not in self.target_groups:
            raise BridgeError("refusing non-allowlisted WeCom Android image source")
        if str(record.get("direction") or "") != "inbound":
            raise BridgeError("refusing to materialize an outbound WeCom image")
        if str(record.get("source_kind") or "") != IMAGE_KIND:
            return dict(record)
        fingerprint = str(record.get("fingerprint") or "")
        if not fingerprint:
            raise BridgeError("WeCom image record is missing its visual fingerprint")
        target: Path | None = None
        saved_image: MediaStoreImage | None = None
        original_requested = False
        capture_kind = "wecom_android_original_media_store_export"
        restore_error = ""
        viewer_open = False
        try:
            root, _, node = self.find_image_node_for_record(chat, record)
            self.tap_node(root, node)
            viewer_root = self.wait_for_image_viewer()
            viewer_open = True
            original_requested = self.request_original_image(viewer_root)
            viewer_root = self.wait_for_image_viewer()
            saved_image = self.save_image_from_viewer(viewer_root)
            target = self.pull_saved_image(chat, fingerprint, saved_image)
        except Exception as exc:
            if not bool(self.config.get("allow_inbound_image_preview_fallback", False)):
                raise BridgeError(
                    f"native-resolution WeCom image recovery failed: {str(exc)[:500]}"
                ) from exc
            preview = Path(str(record.get("exact_preview_path") or "")).expanduser()
            if not (
                preview.is_file()
                and preview.stat().st_size > 64
                and preview.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
                and str(record.get("exact_preview_sha256") or "")
                == sha256_file(preview)
            ):
                raise
            target = preview
            capture_kind = "wecom_android_exact_visible_image_preview_fallback"
        finally:
            if viewer_open:
                self.press_back()
            try:
                restored = self.open_chat(chat)
                restored = self.move_chat_to_live_tail(chat, restored)
                if not chat_title_matches(visible_chat_title(restored), chat):
                    raise BridgeError(
                        "WeCom did not return to the exact image source chat"
                    )
            except Exception as exc:
                restore_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        if target is None or not target.is_file() or target.stat().st_size <= 0:
            raise BridgeError("materialized WeCom image is missing after native export")
        result = dict(record)
        result.update(
            {
                "attachment_path": str(target),
                "attachment_filename": (
                    saved_image.display_name if saved_image is not None else target.name
                ),
                "attachment_size_bytes": str(target.stat().st_size),
                "attachment_sha256": sha256_file(target),
                "attachment_width": str(
                    saved_image.width
                    if saved_image is not None
                    else record.get("exact_preview_width") or ""
                ),
                "attachment_height": str(
                    saved_image.height
                    if saved_image is not None
                    else record.get("exact_preview_height") or ""
                ),
                "attachment_capture_kind": capture_kind,
                "attachment_fidelity": (
                    "native_transmitted_original"
                    if saved_image is not None
                    else "degraded_visible_thumbnail"
                ),
                "attachment_original_resolution_verified": (
                    "true" if saved_image is not None else "false"
                ),
                "attachment_original_control_used": (
                    "true" if original_requested else "false"
                ),
                "attachment_restore_error": restore_error,
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
        pages = bounded_int(max_pages, 0, 0, MAX_RECOVERY_HISTORY_PAGES)
        if pages == 0:
            return []
        recovered: list[dict[str, str]] = []
        seen = {record["fingerprint"] for record in current_records}
        long_content_index: dict[tuple[str, str, str], tuple[int, int]] = {}
        for page_index in range(pages):
            # Pull the viewport downward to walk backward through older rows.
            self.adb_shell("input", "swipe", "520", "350", "520", "1450", "500")
            time.sleep(0.55)
            root = self.dump_hierarchy(attempts=3)
            if not chat_title_matches(visible_chat_title(root), chat):
                break
            try:
                screenshot = self.capture_raw_screenshot()
            except Exception:
                screenshot = None
            page_records = self.parse_messages(root, screenshot=screenshot)
            if not page_records:
                break
            for record in page_records:
                # Older media rows are no longer guaranteed to remain visible
                # after this history walk returns to the live tail. Bounds-only
                # identities also change with every viewport, which previously
                # created an endless backlog of phantom image tasks. Current-
                # viewport media is captured by snapshot(); history media is
                # intentionally left for an exact native/file recovery route.
                source_kind = record.get("source_kind")
                if source_kind == SHIPINHAO_CARD_KIND and screenshot is not None:
                    try:
                        record = self.materialize_visible_shipinhao_card_record(
                            chat, record, screenshot
                        )
                    except BridgeError:
                        continue
                elif source_kind in {IMAGE_KIND, DOCUMENT_KIND, SHIPINHAO_CARD_KIND}:
                    continue
                fingerprint = record["fingerprint"]
                if fingerprint in seen:
                    continue
                body = normalize_visible_text(record.get("body"))
                content_key = (
                    str(record.get("source_kind") or ""),
                    body,
                    normalize_visible_text(record.get("quote_text")),
                )
                prior = long_content_index.get(content_key) if len(body) >= 80 else None
                if prior is not None:
                    prior_index, prior_page = prior
                    prior_record = recovered[prior_index]
                    same_bubble_across_adjacent_viewport = (
                        len(recovered) > prior_index
                        and abs(page_index - prior_page) <= 1
                    )
                    compatible_sender = (
                        not prior_record.get("sender")
                        or not record.get("sender")
                        or prior_record.get("sender") == record.get("sender")
                    )
                    if same_bubble_across_adjacent_viewport and compatible_sender:
                        seen.add(fingerprint)
                        if record.get("sender") and not prior_record.get("sender"):
                            recovered[prior_index] = record
                            long_content_index[content_key] = (prior_index, page_index)
                        continue
                seen.add(fingerprint)
                recovered.append(record)
                if len(body) >= 80:
                    long_content_index[content_key] = (len(recovered) - 1, page_index)
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
        if status not in {
            "seeded",
            "observed",
            "pending",
            "ingested",
            "media_blocked",
        }:
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
    ) -> bool:
        """Back off a recoverable native-media failure without losing the row."""
        if not fingerprint:
            return False
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute(
                "SELECT failure_count FROM observed_messages "
                "WHERE chat = ? AND fingerprint = ?",
                (chat, fingerprint),
            ).fetchone()
            count = int(row[0] or 0) if row else 0
            next_count = count + 1
            blocked = next_count >= self.inbound_media_max_recovery_failures
            delay = min(float(max_seconds), float(base_seconds) * (2 ** min(count, 5)))
            retry_after = (
                ""
                if blocked
                else (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)
                ).isoformat(timespec="seconds")
            )
            conn.execute(
                "UPDATE observed_messages SET status = ?, retry_after = ?, failure_count = ?, "
                "last_error = ?, updated_at = ? WHERE chat = ? AND fingerprint = ?",
                (
                    "media_blocked" if blocked else "pending",
                    retry_after,
                    next_count,
                    str(error)[:500],
                    now_iso(),
                    chat,
                    fingerprint,
                ),
            )
        return blocked

    def blocked_media_recovery_count(self) -> int:
        with sqlite3.connect(self.state_db) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM observed_messages WHERE status = 'media_blocked'"
            ).fetchone()
        return int(row[0] or 0) if row else 0

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
        if source_kind in {IMAGE_KIND, DOCUMENT_KIND, SHIPINHAO_CARD_KIND}:
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
                "kind": IMAGE_KIND if source_kind == SHIPINHAO_CARD_KIND else source_kind,
                "filename": str(record.get("attachment_filename") or attachment.name),
                "path": str(attachment),
                "size_bytes": attachment.stat().st_size,
                "sha256": actual_sha256,
                "capture_kind": str(record.get("attachment_capture_kind") or ""),
            }
            if source_kind in {IMAGE_KIND, SHIPINHAO_CARD_KIND}:
                attachment_payload.update(
                    {
                        "width": str(record.get("attachment_width") or ""),
                        "height": str(record.get("attachment_height") or ""),
                        "capture_kind": str(
                            record.get("attachment_capture_kind")
                            or "wecom_android_native_full_view"
                        ),
                        "fidelity": str(record.get("attachment_fidelity") or ""),
                        "original_resolution_verified": str(
                            record.get("attachment_original_resolution_verified") or ""
                        ).lower()
                        == "true",
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
        rich_card_kind = next(
            (
                str(item.get("msgtype") or "")
                for item in events
                if str(item.get("msgtype") or "")
                in {ARTICLE_CARD_KIND, SHIPINHAO_CARD_KIND}
            ),
            "",
        )
        if rich_card_kind:
            event["msgtype"] = rich_card_kind
        else:
            event["msgtype"] = "combined_forward"
        return event

    def invoke_ingest(
        self,
        event: dict[str, Any],
        *,
        reconsider_processed: bool = False,
    ) -> dict[str, Any]:
        runtime = self.staging_dir / "events"
        runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", prefix="event-", dir=runtime, delete=False
        ) as handle:
            json.dump(event, handle, ensure_ascii=False)
            event_path = Path(handle.name)
        os.chmod(event_path, 0o600)
        try:
            command = [
                sys.executable,
                str(INGEST),
                "--event-file",
                str(event_path),
                "--queue",
                str(self.queue),
                "--history-db",
                str(self.history_db),
                "--json",
            ]
            if reconsider_processed:
                command.append("--reconsider-processed")
            process = self.run(
                command,
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
        with self.passive_serialized(timeout_seconds=30.0):
            root = self.open_chat(chat)
            root = self.move_chat_to_live_tail(chat, root)
            current_records = self.parse_messages(root)
            current_screenshot: RawScreenshot | None = None
            if any(
                record.get("source_kind") in {IMAGE_KIND, SHIPINHAO_CARD_KIND}
                for record in current_records
            ):
                current_screenshot = self.capture_raw_screenshot()
                current_records = self.parse_messages(
                    root,
                    screenshot=current_screenshot,
                )
                for index, record in enumerate(current_records):
                    if not (
                        record.get("direction") == "inbound"
                        and record.get("source_kind") == IMAGE_KIND
                    ):
                        continue
                    try:
                        current_records[index] = self.persist_visible_image_preview(
                            chat,
                            record,
                            current_screenshot,
                        )
                    except BridgeError:
                        # Full-view materialization below remains available.
                        # Never weaken exact identity merely to save a preview.
                        pass
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
                if source_kind not in {
                    IMAGE_KIND,
                    DOCUMENT_KIND,
                    SHIPINHAO_CARD_KIND,
                }:
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
                        else (
                            self.materialize_shipinhao_card_record(chat, record)
                            if source_kind == SHIPINHAO_CARD_KIND
                            else self.materialize_document_record(chat, record)
                        )
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
                        record.get("source_kind")
                        in {IMAGE_KIND, DOCUMENT_KIND, SHIPINHAO_CARD_KIND}
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
                with self.outbound_serialized(timeout_seconds=60.0):
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
        deferred, deferred_reason = self.passive_control_deferred()
        if deferred:
            return {
                "ok": True,
                "due_chats": [],
                "unread_chats": [],
                "reconciliation": False,
                "history_scan_chat": "",
                "processed": 0,
                "results": [],
                "restore_error": "",
                "deferred_for_outbound": True,
                "deferred_reason": deferred_reason,
                "deferred_chats": list(self.target_groups),
            }
        now = time.monotonic()
        due = [chat for chat in self.target_groups if self.load_snapshot(chat) is None]
        unread: list[str] = []
        if not due:
            with self.passive_serialized(timeout_seconds=5.0):
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
        deferred_chats: list[str] = []
        deferred_reason = ""
        for index, chat in enumerate(due):
            deferred, current_deferred_reason = self.passive_control_deferred()
            if deferred:
                deferred_chats = due[index:]
                deferred_reason = current_deferred_reason
                self._next_reconcile_at = 0.0
                if history_scan_chat in deferred_chats:
                    self._next_history_scan_at = 0.0
                break
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
        deferred, current_deferred_reason = self.passive_control_deferred()
        if deferred and not deferred_reason:
            deferred_reason = current_deferred_reason
        if due and not deferred:
            try:
                with self.passive_serialized(timeout_seconds=5.0):
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
            "deferred_for_outbound": bool(deferred_chats),
            "deferred_reason": deferred_reason,
            "deferred_chats": deferred_chats,
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
        authentication_reason = ""
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
                if is_crash_report_dialog(root):
                    surface_state = "crash_report"
                elif is_anr_dialog(root):
                    surface_state = "anr"
                elif (authentication_reason := self.authentication_gate_reason(root)):
                    surface_state = "authentication"
                elif title:
                    surface_state = "chat"
                elif package == self.package:
                    surface_state = "wecom_other"
                else:
                    surface_state = "other_app"
            else:
                package = self.current_package()
                if (authentication_reason := self.authentication_gate_reason()):
                    surface_state = "authentication"
                elif package == self.package:
                    surface_state = "wecom_other"
                elif package:
                    surface_state = "other_app"
        healthy = bool(
            authorized
            and health.get("poll_healthy")
            and surface_state not in {"anr", "authentication", "crash_report"}
        )
        storage = self.device_data_storage_status() if authorized else dict(self._storage_status)
        external_priority = self.external_control_priority() if authorized else None
        return {
            "ok": healthy,
            "enabled": bool(self.config.get("enabled", True)),
            "transport": "wecom_android",
            "device_authorized": authorized,
            "wecom_foreground": surface_state in {"chat", "wecom_other", "polling"},
            "visible_chat": title,
            "surface_state": surface_state,
            "authentication_reason": authentication_reason,
            "device_storage": {
                **storage,
                "minimum_free_bytes": self.minimum_free_data_bytes,
                "critically_low": bool(
                    isinstance(storage.get("available_bytes"), int)
                    and int(storage["available_bytes"]) < self.minimum_free_data_bytes
                ),
            },
            "blocked_media_recoveries": self.blocked_media_recovery_count(),
            "external_control_active": external_priority is not None,
            "external_control_purpose": (
                normalize_visible_text(external_priority.get("purpose"))[:160]
                if isinstance(external_priority, dict)
                else ""
            ),
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
                        recovery = self.recover_transport_surface_bounded(
                            reason="poll_exception"
                        )
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
                    recovery = self.recover_transport_surface_bounded(
                        reason="poll_result"
                    )
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
            if self.path not in {"/v1/open", "/v1/send", "/v1/delivery-status"}:
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
                if self.path == "/v1/open":
                    with bridge.outbound_serialized(timeout_seconds=60.0):
                        root = bridge.open_chat(chat)
                    self.write_json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "transport": "wecom_android",
                            "chat": chat,
                            "visible_title": visible_chat_title(root),
                        },
                    )
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


def running_service_request(
    config: dict[str, Any],
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 1.0,
) -> dict[str, Any] | None:
    """Use the persistent relay when it is reachable; return None only offline."""
    port = bounded_int(config.get("local_api_port"), 19581, 1024, 65535)
    token = str(config.get("local_api_token") or "")
    if not token:
        return None
    body = None
    headers = {"Authorization": f"Bearer {token}"}
    method = "GET"
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    service_request = urlrequest.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlrequest.urlopen(
            service_request,
            timeout=max(0.1, float(timeout_seconds)),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        try:
            result = json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError):
            result = {
                "ok": False,
                "error": f"persistent WeCom relay returned HTTP {exc.code}",
            }
    except (OSError, TimeoutError, ValueError, urlerror.URLError):
        return None
    return result if isinstance(result, dict) else {
        "ok": False,
        "error": "persistent WeCom relay returned an invalid response",
    }


def running_service_status(config: dict[str, Any]) -> dict[str, Any] | None:
    """Read health from the persistent relay instead of a fresh bridge object."""
    payload = running_service_request(config, "/v1/status")
    if not isinstance(payload, dict) or payload.get("transport") != "wecom_android":
        return None
    return payload


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
    messages.add_argument("--history-pages", type=int, default=0)
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
            config = load_config(args.config)
            if args.command == "status":
                payload = running_service_status(config)
                if payload is None:
                    payload = AndroidBridge(
                        config, config_path=args.config
                    ).status()
            else:
                bridge = AndroidBridge(config, config_path=args.config)
                if args.command == "chats":
                    payload = bridge.list_chats()
                elif args.command == "open":
                    payload = running_service_request(
                        config,
                        "/v1/open",
                        payload={"chat_id": f"gui:{args.chat}"},
                        timeout_seconds=90.0,
                    )
                    if payload is None:
                        with bridge.outbound_serialized(timeout_seconds=60.0):
                            root = bridge.open_chat(args.chat)
                        payload = {
                            "ok": True,
                            "chat": args.chat,
                            "visible_title": visible_chat_title(root),
                        }
                elif args.command == "messages":
                    payload = bridge.snapshot(
                        args.chat,
                        enqueue=args.enqueue,
                        history_pages=bounded_int(
                            args.history_pages, 0, 0, MAX_RECOVERY_HISTORY_PAGES
                        ),
                    )
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
                            "files": [
                                str(path.expanduser().resolve())
                                for path in args.files
                            ],
                        }
                    else:
                        payload = running_service_request(
                            config,
                            "/v1/send",
                            payload={
                                "chat_id": f"gui:{args.chat}",
                                "message": args.message,
                                "mentions": args.mentions,
                                "files": [
                                    str(path.expanduser().resolve())
                                    for path in args.files
                                ],
                                "task_id": args.task_id,
                                "force_resend": args.force_resend,
                            },
                            timeout_seconds=600.0,
                        )
                        if payload is None:
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
