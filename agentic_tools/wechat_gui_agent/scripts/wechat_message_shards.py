#!/usr/bin/env python3
"""Shared, bounded helpers for rotated WeChat message databases."""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any


MESSAGE_DB_NAME_RE = re.compile(r"^message_(\d+)\.db$")


def normalize_message_db_name(value: Any) -> str:
    name = Path(str(value or "")).name
    return name if MESSAGE_DB_NAME_RE.fullmatch(name) else ""


def message_db_index(value: Any) -> int:
    match = MESSAGE_DB_NAME_RE.fullmatch(Path(str(value or "")).name)
    return int(match.group(1)) if match else -1


def parse_message_ref(value: Any) -> tuple[str, int]:
    raw_db_name, separator, local_id_text = str(value or "").strip().rpartition(":")
    db_name = normalize_message_db_name(raw_db_name)
    if not separator or not db_name or raw_db_name != db_name:
        raise ValueError("expected message_N.db:local_id")
    try:
        local_id = int(local_id_text)
    except ValueError as exc:
        raise ValueError("local_id must be an integer") from exc
    if local_id <= 0:
        raise ValueError("local_id must be positive")
    return db_name, local_id


def message_db_has_table(path: Path, table: str) -> bool:
    if not table:
        return True
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
                (table,),
            ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def list_message_db_paths(
    directory: Path,
    *,
    names: set[str] | None = None,
    table: str = "",
    newest_first: bool = False,
) -> list[Path]:
    if not directory.is_dir():
        return []
    filter_names = names is not None
    allowed = {
        normalized
        for item in names or set()
        if (normalized := normalize_message_db_name(item))
        and str(item) == normalized
    }
    paths = [
        path
        for path in directory.glob("message_*.db")
        if path.is_file()
        and normalize_message_db_name(path.name)
        and (not filter_names or path.name in allowed)
        and message_db_has_table(path, table)
    ]
    paths.sort(key=lambda path: message_db_index(path.name), reverse=newest_first)
    return paths
