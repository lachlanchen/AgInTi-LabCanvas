#!/usr/bin/env python3
"""Shared transport-level text policy for WeChat automation."""

from __future__ import annotations

from datetime import datetime
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
