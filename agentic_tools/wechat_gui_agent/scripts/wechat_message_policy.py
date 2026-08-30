#!/usr/bin/env python3
"""Shared transport-level text policy for WeChat automation."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata


NO_REPLY_RE = re.compile(
    r"^(?:(?:chat|ack)\s*[:：]\s*)?no[\s_-]*reply(?:\b|_)",
    flags=re.IGNORECASE,
)
SUCCESSFUL_OUTBOUND_STATUSES = {
    "sent",
    "done-sent",
    "waiting-confirmation-sent",
}
IN_FLIGHT_OUTBOUND_FILE_STATUS = "sending"
IN_FLIGHT_OUTBOUND_FILE_WINDOW_SECONDS = 600
TRANSCODED_VIDEO_ECHO_WINDOW_SECONDS = 120


def normalize_transport_text(text: str) -> str:
    """Normalize text for comparing a sent message with its WeChat DB echo."""
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.replace("\ufeff", "").replace("\u200b", "").replace("\u2060", "")
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


def is_no_reply_control(text: str) -> bool:
    """Return true when an agent output starts with the internal no-reply token."""
    value = normalize_transport_text(text).strip()
    if not value:
        return False
    if value.startswith("```"):
        value = re.sub(r"^```(?:text|markdown|md)?\s*", "", value, count=1, flags=re.IGNORECASE)
    value = value.lstrip("`*_#>•- \t\r\n")
    return bool(NO_REPLY_RE.match(value))


def has_explicit_video_generation_intent(text: str) -> bool:
    """Match creation of the video itself, not metadata or subtitle work.

    A message such as ``publish this video and generate concise metadata``
    contains both ``video`` and ``generate`` but is not a video-generation
    request. Keep the action and its video object coupled in the same phrase.
    """
    value = normalize_transport_text(text).casefold()
    if not value:
        return False
    if any(marker in value for marker in ("xiaoyunque", "seedance", "xyq", "小云雀")):
        return True
    if re.search(
        r"\b(?:text|image|audio|music)[ -]to[ -](?:video|film|animation)\b",
        value,
    ):
        return True
    video = r"(?:video|movie|film|animation|clip)"
    action = r"(?:generate|create|make|produce|animate|regenerate)"
    if re.search(
        rf"\b{action}\b(?:\s+[\w'-]+){{0,5}}\s+\b{video}\b",
        value,
    ):
        return True
    if re.search(
        rf"\b{video}\b(?:\s+[\w'-]+){{0,3}}\s+\b(?:generation|creation|regeneration)\b",
        value,
    ):
        return True
    chinese_video = r"(?:视频|視頻|影片|短片|动画|動畫)"
    chinese_action = r"(?:生成|制作|製作|创作|創作|重做|重新生成|做)"
    if re.search(rf"{chinese_action}[^,;:，；：。！？\n]{{0,10}}{chinese_video}", value):
        return True
    if re.search(rf"{chinese_video}[^,;:，；：。！？\n]{{0,6}}(?:生成|制作|製作|创作|創作|重做)", value):
        return True
    return False


def recorded_outbound_echo(
    db_path: Path,
    chat_name: str,
    text: str,
    *,
    source_epoch: int | float = 0,
    window_seconds: int = 1800,
    limit: int = 240,
) -> bool:
    """Match a self-authored DB row to a recent successful local outbound send.

    Rows recorded with status ``synced`` are deliberately excluded: the direct
    monitor writes those while ingesting the row, so accepting them as evidence
    would suppress legitimate same-account commands.
    """
    needle = normalize_transport_text(text)
    if not needle or not chat_name or not db_path.exists():
        return False
    placeholders = ",".join("?" for _ in SUCCESSFUL_OUTBOUND_STATUSES)
    params = [chat_name, *sorted(SUCCESSFUL_OUTBOUND_STATUSES), max(1, int(limit))]
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT messages.body, messages.created_at
                FROM messages
                JOIN chats ON chats.id = messages.chat_id
                WHERE chats.name = ?
                  AND messages.direction = 'outbound'
                  AND messages.status IN ({placeholders})
                ORDER BY messages.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
    except sqlite3.Error:
        return False
    source_time = float(source_epoch or 0)
    max_delta = max(1, int(window_seconds))
    for body, created_at in rows:
        if normalize_transport_text(body) != needle:
            continue
        if source_time <= 0:
            return True
        try:
            sent_time = datetime.fromisoformat(str(created_at)).timestamp()
        except (TypeError, ValueError):
            continue
        if abs(source_time - sent_time) <= max_delta:
            return True
    return False


def recorded_android_outbound_echo(
    state_db: Path,
    chat_name: str,
    text: str,
    *,
    source_epoch: int | float = 0,
    window_seconds: int = 1800,
    limit: int = 240,
) -> bool:
    """Match text against the native Android sender's verified component ledger.

    This closes the crash window between a verified phone send and the parent
    worker recording that delivery in the shared WeChat mirror.
    """
    raw = str(text or "").strip()
    normalized = normalize_transport_text(raw)
    if not raw or not chat_name or not state_db.exists():
        return False
    hashes = {
        hashlib.sha256(value.encode("utf-8")).hexdigest()
        for value in (raw, normalized)
        if value
    }
    placeholders = ",".join("?" for _ in hashes)
    params = [chat_name, *sorted(hashes), max(1, int(limit))]
    try:
        with sqlite3.connect(state_db) as conn:
            rows = conn.execute(
                f"""
                SELECT updated_at
                FROM components
                WHERE chat = ?
                  AND kind = 'text'
                  AND status = 'sent'
                  AND value_hash IN ({placeholders})
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
    except sqlite3.Error:
        return False
    source_time = float(source_epoch or 0)
    max_delta = max(1, int(window_seconds))
    for (updated_at,) in rows:
        if source_time <= 0:
            return True
        try:
            sent_time = datetime.fromisoformat(str(updated_at)).timestamp()
        except (TypeError, ValueError):
            continue
        if abs(source_time - sent_time) <= max_delta:
            return True
    return False


def file_transport_identity(path: Path) -> dict[str, object]:
    """Build a private, content-based identity for one outbound file."""
    resolved = path.expanduser().resolve()
    stat = resolved.stat()
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return {
        "name": resolved.name,
        "size_bytes": int(stat.st_size),
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def attachment_transport_identity(text: str) -> dict[str, object]:
    """Extract stable file identity fields from a normalized WeChat row."""
    source = str(text or "")
    identity: dict[str, object] = {}
    patterns = {
        "name": (
            r"(?im)^\s*(?:title|filename|file_name|name)\s*[:：]\s*(.+?)\s*$",
            r"(?i)\b(?:title|filename|file_name)\s*=\s*[\"']([^\"']+)[\"']",
            r"(?is)<title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>",
        ),
        "size_bytes": (
            r"(?im)^\s*(?:size_bytes|filesize|size)\s*[:：]\s*(\d+)\s*$",
            r"(?i)\b(?:size_bytes|filesize|totallen|length)\s*=\s*[\"']?(\d+)",
        ),
        "md5": (
            r"(?im)^\s*(?:originsourcemd5|md5|filemd5|rawmd5|newmd5)\s*[:：]\s*([0-9a-f]{32})\s*$",
            r"(?i)\b(?:originsourcemd5|md5|filemd5|rawmd5|newmd5)\s*=\s*[\"']([0-9a-f]{32})[\"']",
            r"(?i)<(?:originsourcemd5|md5|filemd5|rawmd5|newmd5)>\s*([0-9a-f]{32})\s*</",
        ),
        "sha256": (
            r"(?im)^\s*sha-?256\s*[:：]\s*([0-9a-f]{64})\s*$",
            r"(?i)\bsha-?256\s*=\s*[\"']([0-9a-f]{64})[\"']",
        ),
    }
    for key, candidates in patterns.items():
        for pattern in candidates:
            match = re.search(pattern, source)
            if not match:
                continue
            value = match.group(1).strip()
            identity[key] = int(value) if key == "size_bytes" else value.lower() if key in {"md5", "sha256"} else value
            break
    md5_values = {
        match.lower()
        for match in re.findall(
            r"(?i)(?:originsourcemd5|md5|filemd5|rawmd5|newmd5)"
            r"(?:\s*[:：=]\s*[\"']?|>\s*)([0-9a-f]{32})",
            source,
        )
    }
    if md5_values:
        identity["md5_values"] = sorted(md5_values)
    return identity


def identity_hash_values(identity: dict[str, object], key: str) -> set[str]:
    values: set[str] = set()
    scalar = str(identity.get(key) or "").strip().lower()
    if scalar:
        values.add(scalar)
    plural = identity.get(f"{key}_values")
    if isinstance(plural, (list, tuple, set)):
        values.update(str(value).strip().lower() for value in plural if str(value).strip())
    return values


def file_identities_match(left: dict[str, object], right: dict[str, object]) -> bool:
    """Require a strong content hash, or an exact name-and-size fallback."""
    for key in ("sha256", "md5"):
        first = identity_hash_values(left, key)
        second = identity_hash_values(right, key)
        if first and second and first.intersection(second):
            return True
    first_name = Path(str(left.get("name") or "")).name
    second_name = Path(str(right.get("name") or "")).name
    try:
        first_size = int(left.get("size_bytes") or 0)
        second_size = int(right.get("size_bytes") or 0)
    except (TypeError, ValueError):
        return False
    return bool(first_name and first_name == second_name and first_size > 0 and first_size == second_size)


def transcoded_video_identities_match(
    left: dict[str, object],
    right: dict[str, object],
) -> bool:
    """Match a WeChat video echo whose local cache bytes were transcoded.

    The Linux client may rewrite the sent MP4 and expose a different ``rawmd5``
    in the message row. Its ``videomsg length`` still carries the exact size of
    the submitted source file, so an exact size match is safe only inside a
    narrow same-chat outbound-send window.
    """
    try:
        left_size = int(left.get("size_bytes") or 0)
        right_size = int(right.get("size_bytes") or 0)
    except (TypeError, ValueError):
        return False
    return left_size > 0 and left_size == right_size


def recorded_outbound_file_identity(
    db_path: Path,
    chat_name: str,
    identity: dict[str, object],
    *,
    source_epoch: int | float = 0,
    window_seconds: int = 7200,
    limit: int = 240,
    allow_transcoded_video_size_match: bool = False,
) -> bool:
    """Match an attachment to a recent successful file delivery event."""
    if not identity or not chat_name or not db_path.exists():
        return False
    placeholders = ",".join("?" for _ in SUCCESSFUL_OUTBOUND_STATUSES)
    params = [chat_name, *sorted(SUCCESSFUL_OUTBOUND_STATUSES), max(1, int(limit))]
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT events.metadata_json, events.created_at
                FROM events
                JOIN chats ON chats.id = events.chat_id
                WHERE chats.name = ?
                  AND events.direction = 'outbound'
                  AND events.status IN ({placeholders})
                ORDER BY events.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
    except sqlite3.Error:
        return False
    source_time = float(source_epoch or 0)
    max_delta = max(1, int(window_seconds))
    for metadata_json, created_at in rows:
        try:
            metadata = json.loads(str(metadata_json or "{}"))
        except json.JSONDecodeError:
            continue
        candidate = metadata.get("file_identity") if isinstance(metadata, dict) else {}
        if not isinstance(candidate, dict):
            continue
        try:
            sent_time = datetime.fromisoformat(str(created_at)).timestamp()
        except (TypeError, ValueError):
            continue
        delta = abs(source_time - sent_time) if source_time > 0 else 0
        if file_identities_match(identity, candidate) and (
            source_time <= 0 or delta <= max_delta
        ):
            return True
        if (
            allow_transcoded_video_size_match
            and source_time > 0
            and delta <= min(max_delta, TRANSCODED_VIDEO_ECHO_WINDOW_SECONDS)
            and transcoded_video_identities_match(identity, candidate)
        ):
            return True
    if source_time <= 0:
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT events.metadata_json, events.created_at
                FROM events
                JOIN chats ON chats.id = events.chat_id
                WHERE chats.name = ?
                  AND events.action = 'file_send_intent'
                  AND events.direction = 'outbound'
                  AND events.status = ?
                ORDER BY events.id DESC
                LIMIT ?
                """,
                (
                    chat_name,
                    IN_FLIGHT_OUTBOUND_FILE_STATUS,
                    max(1, int(limit)),
                ),
            ).fetchall()
    except sqlite3.Error:
        return False
    intent_window = min(max_delta, IN_FLIGHT_OUTBOUND_FILE_WINDOW_SECONDS)
    for metadata_json, created_at in rows:
        try:
            metadata = json.loads(str(metadata_json or "{}"))
        except json.JSONDecodeError:
            continue
        candidate = metadata.get("file_identity") if isinstance(metadata, dict) else {}
        if not isinstance(candidate, dict):
            continue
        try:
            sent_time = datetime.fromisoformat(str(created_at)).timestamp()
        except (TypeError, ValueError):
            continue
        delta = abs(source_time - sent_time)
        if file_identities_match(identity, candidate) and delta <= intent_window:
            return True
        if (
            allow_transcoded_video_size_match
            and delta <= min(intent_window, TRANSCODED_VIDEO_ECHO_WINDOW_SECONDS)
            and transcoded_video_identities_match(identity, candidate)
        ):
            return True
    return False


def recorded_outbound_file_echo(
    db_path: Path,
    chat_name: str,
    text: str,
    *,
    source_epoch: int | float = 0,
    window_seconds: int = 7200,
    limit: int = 240,
) -> bool:
    """Return true when an inbound attachment is a recent local file send."""
    source = str(text or "").casefold()
    return recorded_outbound_file_identity(
        db_path,
        chat_name,
        attachment_transport_identity(text),
        source_epoch=source_epoch,
        window_seconds=window_seconds,
        limit=limit,
        allow_transcoded_video_size_match="<videomsg" in source,
    )


def recorded_android_outbound_file_echo(
    state_db: Path,
    chat_name: str,
    text: str,
    *,
    source_epoch: int | float = 0,
    window_seconds: int = 7200,
    limit: int = 240,
) -> bool:
    """Match a self-authored attachment to Android's verified send ledger.

    Android delivery can reach WeChat before the parent worker records the
    outbound mirror event. WeChat may transcode a video, but its XML preserves
    the submitted file hash as ``originsourcemd5``; matching that hash closes
    the crash window without treating unrelated same-sized media as an echo.
    """
    identity = attachment_transport_identity(text)
    if not identity or not chat_name or not state_db.exists():
        return False
    try:
        with sqlite3.connect(state_db) as conn:
            rows = conn.execute(
                """
                SELECT value_hash, details_json, updated_at
                FROM components
                WHERE chat = ?
                  AND kind = 'file'
                  AND status = 'sent'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (chat_name, max(1, int(limit))),
            ).fetchall()
    except sqlite3.Error:
        return False
    source_time = float(source_epoch or 0)
    max_delta = max(1, int(window_seconds))
    for value_hash, details_json, updated_at in rows:
        try:
            details = json.loads(str(details_json or "{}"))
        except json.JSONDecodeError:
            details = {}
        candidate = details.get("file_identity") if isinstance(details, dict) else {}
        if not isinstance(candidate, dict):
            candidate = {}
        candidate = dict(candidate)
        if value_hash and not candidate.get("sha256"):
            candidate["sha256"] = str(value_hash).strip().lower()
        if not file_identities_match(identity, candidate):
            continue
        if source_time <= 0:
            return True
        try:
            sent_time = datetime.fromisoformat(str(updated_at)).timestamp()
        except (TypeError, ValueError):
            continue
        if abs(source_time - sent_time) <= max_delta:
            return True
    return False
