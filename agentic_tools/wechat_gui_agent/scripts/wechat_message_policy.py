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
        ),
        "size_bytes": (
            r"(?im)^\s*(?:size_bytes|filesize|size)\s*[:：]\s*(\d+)\s*$",
            r"(?i)\b(?:size_bytes|filesize|totallen|length)\s*=\s*[\"']?(\d+)",
        ),
        "md5": (
            r"(?im)^\s*(?:md5|filemd5|rawmd5|newmd5)\s*[:：]\s*([0-9a-f]{32})\s*$",
            r"(?i)\b(?:md5|filemd5|rawmd5|newmd5)\s*=\s*[\"']([0-9a-f]{32})[\"']",
            r"(?i)<(?:md5|filemd5|rawmd5|newmd5)>\s*([0-9a-f]{32})\s*</",
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
    return identity


def file_identities_match(left: dict[str, object], right: dict[str, object]) -> bool:
    """Require a strong content hash, or an exact name-and-size fallback."""
    for key in ("sha256", "md5"):
        first = str(left.get(key) or "").lower()
        second = str(right.get(key) or "").lower()
        if first and second and first == second:
            return True
    first_name = Path(str(left.get("name") or "")).name
    second_name = Path(str(right.get("name") or "")).name
    try:
        first_size = int(left.get("size_bytes") or 0)
        second_size = int(right.get("size_bytes") or 0)
    except (TypeError, ValueError):
        return False
    return bool(first_name and first_name == second_name and first_size > 0 and first_size == second_size)


def recorded_outbound_file_identity(
    db_path: Path,
    chat_name: str,
    identity: dict[str, object],
    *,
    source_epoch: int | float = 0,
    window_seconds: int = 7200,
    limit: int = 240,
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
        if not isinstance(candidate, dict) or not file_identities_match(identity, candidate):
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
    return recorded_outbound_file_identity(
        db_path,
        chat_name,
        attachment_transport_identity(text),
        source_epoch=source_epoch,
        window_seconds=window_seconds,
        limit=limit,
    )
