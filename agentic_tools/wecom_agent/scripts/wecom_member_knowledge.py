#!/usr/bin/env python3
"""Maintain a private, provenance-aware knowledge archive for each WeCom member."""

from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_DB = Path(os.environ.get("WECOM_MEMBER_KNOWLEDGE_DB", PRIVATE / "wecom_member_knowledge.sqlite"))
DEFAULT_HISTORY_DB = Path(os.environ.get("WECOM_HISTORY_DB", PRIVATE / "wecom_messages.local.sqlite"))
DEFAULT_QUEUE = Path(os.environ.get("WECOM_TASK_QUEUE", PRIVATE / "wecom_task_queue.jsonl"))
DEFAULT_ARCHIVE_ROOT = Path(
    os.environ.get("WECOM_MEMBER_ARCHIVE_ROOT", ROOT / "output" / "wecom" / "member_knowledge")
)

KNOWLEDGE_KINDS = {
    "idea",
    "insight",
    "intuition",
    "interest",
    "hypothesis",
    "decision",
    "preference",
    "question",
    "note",
    "agent_summary",
}
REPORT_TERMS = {
    "analysis",
    "brief",
    "briefing",
    "digest",
    "report",
    "review",
    "roadmap",
    "summary",
    "分析",
    "简报",
    "簡報",
    "报告",
    "報告",
    "总结",
    "總結",
}
EXPLICIT_MEMORY_MARKERS = {
    "idea": ("#idea", "#想法", "#创意", "#創意"),
    "insight": ("#insight", "#洞见", "#洞見", "#启发", "#啟發"),
    "intuition": ("#intuition", "#直觉", "#直覺"),
    "interest": ("#interest", "#兴趣", "#興趣"),
    "hypothesis": ("#hypothesis", "#假设", "#假設"),
    "note": ("#note", "#笔记", "#筆記"),
}
NONTERMINAL_TASK_STATUSES = {
    "pending",
    "queued",
    "in_progress",
    "running",
    "generation_waiting",
    "generation_stale_paused",
    "generation_poststage_pending",
    "publish_poststage_pending",
}
PDF_REPORT_REQUEST_RE = re.compile(
    r"(?:"
    r"(?:生成|制作|创建|建立|输出|导出|整理|编译|写|给我|发我|发送|提供)"
    r".{0,24}(?:pdf|PDF)"
    r"|"
    r"\b(?:generate|create|make|write|compile|export|send|provide|deliver)"
    r"\b.{0,32}\bpdf\b"
    r"|^\s*pdf\s*$"
    r")",
    re.IGNORECASE | re.DOTALL,
)
PDF_REPORT_NEGATION_RE = re.compile(
    r"(?:不要|不用|无需|不需要|\b(?:no|without|do\s+not|don't|dont)\b)"
    r".{0,20}(?:pdf|PDF)",
    re.IGNORECASE | re.DOTALL,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Index current message history and completed tasks once.")
    add_paths(sync)
    sync.add_argument("--json", action="store_true")

    loop = subparsers.add_parser("loop", help="Continuously index messages and completed tasks.")
    add_paths(loop)
    loop.add_argument("--poll-seconds", type=float, default=float(os.environ.get("WECOM_KNOWLEDGE_POLL_SECONDS", "5")))

    status = subparsers.add_parser("status", help="Show per-member counts without raw transport IDs.")
    status.add_argument("--db", type=Path, default=DEFAULT_DB)
    status.add_argument("--json", action="store_true")

    search = subparsers.add_parser("search", help="Search one member's private knowledge and file index.")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--member-key", default="")
    search.add_argument("--chat", default="")
    search.add_argument("--kind", default="")
    search.add_argument("--limit", type=int, default=25)
    search.add_argument("--db", type=Path, default=DEFAULT_DB)
    search.add_argument("--json", action="store_true")

    export = subparsers.add_parser("export", help="Export one member's archive index to JSON and Markdown.")
    export.add_argument("--member-key", required=True)
    export.add_argument("--output-dir", type=Path)
    export.add_argument("--db", type=Path, default=DEFAULT_DB)
    export.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "sync":
        payload = sync_once(args.db, args.history_db, args.queue, args.archive_root)
        print_result(payload, args.json)
        return 0
    if args.command == "loop":
        interval = max(1.0, min(3600.0, args.poll_seconds))
        while True:
            try:
                payload = sync_once(args.db, args.history_db, args.queue, args.archive_root)
                if payload["new_events"] or payload["indexed_tasks"]:
                    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
            except Exception as exc:
                print(
                    json.dumps({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}, ensure_ascii=False),
                    flush=True,
                )
            time.sleep(interval)
    if args.command == "status":
        payload = knowledge_status(args.db)
        print_result(payload, args.json)
        return 0
    if args.command == "search":
        payload = search_knowledge(
            args.db,
            query=args.query,
            member_key=args.member_key,
            chat=args.chat,
            kind=args.kind,
            limit=max(1, min(200, args.limit)),
        )
        print_result(payload, args.json)
        return 0
    payload = export_member(args.db, args.member_key, args.output_dir)
    print_result(payload, args.json)
    return 0


def add_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--history-db", type=Path, default=DEFAULT_HISTORY_DB)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS members (
                member_key TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                identity_confidence TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS member_chats (
                member_key TEXT NOT NULL,
                chat TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY(member_key, chat)
            );
            CREATE TABLE IF NOT EXISTS member_events (
                event_key TEXT PRIMARY KEY,
                member_key TEXT NOT NULL,
                chat TEXT NOT NULL,
                direction TEXT NOT NULL,
                body TEXT NOT NULL,
                source_message_hash TEXT NOT NULL,
                create_time INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_items (
                id TEXT PRIMARY KEY,
                member_key TEXT NOT NULL,
                chat TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_task_id TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS member_files (
                id TEXT PRIMARY KEY,
                member_key TEXT NOT NULL,
                chat TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL,
                suffix TEXT NOT NULL DEFAULT '',
                mime TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT NOT NULL DEFAULT '',
                original_path TEXT NOT NULL DEFAULT '',
                archive_path TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_task_id TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS indexed_tasks (
                task_id TEXT PRIMARY KEY,
                member_key TEXT NOT NULL,
                chat TEXT NOT NULL,
                status TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sync_state (
                source_key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_member_events_owner ON member_events(member_key, chat, created_at);
            CREATE INDEX IF NOT EXISTS idx_knowledge_owner ON knowledge_items(member_key, chat, kind, updated_at);
            CREATE INDEX IF NOT EXISTS idx_member_files_owner ON member_files(member_key, chat, category, created_at);
            CREATE VIEW IF NOT EXISTS member_papers AS
                SELECT * FROM member_files WHERE category = 'paper';
            """
        )


def knowledge_db_for_history(history_db: Path) -> Path:
    configured = os.environ.get("WECOM_MEMBER_KNOWLEDGE_DB", "").strip()
    return Path(configured).expanduser().resolve() if configured else history_db.with_name("wecom_member_knowledge.sqlite")


def member_key_for_event(event: dict[str, Any]) -> str:
    explicit = str(event.get("member_key") or "").strip()
    if explicit:
        return explicit[:64]
    sender = str(event.get("sender_userid") or event.get("sender") or "").strip()
    return short_hash(sender) if sender else ""


def upsert_member(
    db: Path,
    member_key: str,
    chat: str,
    *,
    display_name: str = "",
    identity_confidence: str = "",
    at: str | None = None,
) -> None:
    if not member_key:
        return
    init_db(db)
    now = at or datetime.now().isoformat(timespec="seconds")
    safe_display = collapse_text(display_name, 200)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO members(member_key, display_name, identity_confidence, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(member_key) DO UPDATE SET
                display_name = CASE WHEN excluded.display_name != '' THEN excluded.display_name ELSE members.display_name END,
                identity_confidence = CASE WHEN excluded.identity_confidence != '' THEN excluded.identity_confidence ELSE members.identity_confidence END,
                last_seen_at = excluded.last_seen_at
            """,
            (member_key, safe_display, identity_confidence[:80], now, now),
        )
        conn.execute(
            """
            INSERT INTO member_chats(member_key, chat, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(member_key, chat) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (member_key, chat, now, now),
        )


def record_incoming_event(
    db: Path,
    event: dict[str, Any],
    chat: str,
    body: str,
    *,
    attachments: Iterable[dict[str, Any]] = (),
    archive_root: Path | None = None,
) -> dict[str, Any]:
    member_key = member_key_for_event(event)
    if not member_key:
        return {"member_key": "", "recorded": False, "files": 0}
    upsert_member(
        db,
        member_key,
        chat,
        display_name=str(event.get("sender_display") or ""),
        identity_confidence=str(event.get("sender_identity_confidence") or "transport_userid"),
    )
    message_hash = short_hash(event.get("message_id"))
    event_key = stable_id("event", member_key, chat, message_hash)
    metadata = {
        "msgtype": str(event.get("msgtype") or "text"),
        "transport_channel": str(event.get("transport_channel") or "wecom_bot_websocket"),
        "authorization_role": str(event.get("authorization_role") or "unknown"),
    }
    with sqlite3.connect(db) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO member_events(
                event_key, member_key, chat, direction, body, source_message_hash,
                create_time, metadata_json, created_at
            ) VALUES (?, ?, ?, 'inbound', ?, ?, ?, ?, ?)
            """,
            (
                event_key,
                member_key,
                chat,
                str(body or ""),
                message_hash,
                int(event.get("create_time") or 0),
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        recorded = cursor.rowcount > 0
    for item in explicit_memory_items(body):
        record_knowledge_item(
            db,
            member_key=member_key,
            chat=chat,
            item=item,
            source_type="user_message",
            source_id=message_hash,
        )
    file_count = 0
    resolved_archive_root = archive_root or archive_root_for_db(db)
    for attachment in attachments:
        path = Path(str(attachment.get("path") or attachment.get("task_copy_path") or "")).expanduser()
        if not path.is_file():
            continue
        record_member_file(
            db,
            member_key=member_key,
            chat=chat,
            path=path,
            source_type="inbound_attachment",
            source_id=message_hash,
            archive_root=resolved_archive_root,
            metadata={"attachment_kind": str(attachment.get("kind") or "file")},
        )
        file_count += 1
    return {"member_key": member_key, "recorded": recorded, "files": file_count}


def record_knowledge_items(
    db: Path,
    *,
    member_key: str,
    chat: str,
    items: Iterable[dict[str, Any]],
    source_type: str,
    source_id: str,
    source_task_id: str = "",
) -> int:
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if record_knowledge_item(
            db,
            member_key=member_key,
            chat=chat,
            item=item,
            source_type=source_type,
            source_id=source_id,
            source_task_id=source_task_id,
        ):
            count += 1
    return count


def record_knowledge_item(
    db: Path,
    *,
    member_key: str,
    chat: str,
    item: dict[str, Any],
    source_type: str,
    source_id: str,
    source_task_id: str = "",
) -> bool:
    kind = str(item.get("kind") or "note").strip().casefold().replace("-", "_")
    if kind not in KNOWLEDGE_KINDS:
        kind = "note"
    content = collapse_text(item.get("content") or item.get("text"), 12000)
    if not member_key or not content:
        return False
    title = collapse_text(item.get("title"), 300) or derive_title(content)
    tags = normalize_tags(item.get("tags"))
    now = datetime.now().isoformat(timespec="seconds")
    item_id = stable_id("knowledge", member_key, chat, kind, source_type, source_id, title, content)
    init_db(db)
    with sqlite3.connect(db) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_items(
                id, member_key, chat, kind, title, content, tags_json,
                source_type, source_id, source_task_id, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                member_key,
                chat,
                kind,
                title,
                content,
                json.dumps(tags, ensure_ascii=False),
                source_type,
                source_id,
                source_task_id,
                json.dumps(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}, ensure_ascii=False),
                now,
                now,
            ),
        )
    return cursor.rowcount > 0


def record_member_file(
    db: Path,
    *,
    member_key: str,
    chat: str,
    path: Path,
    source_type: str,
    source_id: str,
    archive_root: Path,
    source_task_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    path = path.expanduser().resolve()
    if not member_key or not path.is_file():
        return None
    size = path.stat().st_size
    max_bytes = int(os.environ.get("WECOM_MEMBER_ARCHIVE_MAX_FILE_BYTES", str(1024 * 1024 * 1024)))
    digest = sha256_file(path) if size <= max_bytes else ""
    category = classify_file(path)
    archive_path = archive_member_file(path, archive_root, member_key, category, digest) if digest else None
    suffix = path.suffix.casefold()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    file_id = stable_id("file", member_key, chat, source_type, source_id, digest or str(path))
    now = datetime.now().isoformat(timespec="seconds")
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO member_files(
                id, member_key, chat, category, title, filename, suffix, mime,
                size_bytes, sha256, original_path, archive_path, source_type,
                source_id, source_task_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                archive_path = excluded.archive_path,
                metadata_json = excluded.metadata_json
            """,
            (
                file_id,
                member_key,
                chat,
                category,
                humanize_stem(path.stem),
                path.name,
                suffix,
                mime,
                size,
                digest,
                str(path),
                str(archive_path or ""),
                source_type,
                source_id,
                source_task_id,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
    return {"id": file_id, "category": category, "archive_path": str(archive_path or ""), "sha256": digest}


def member_context(db: Path, chat: str, member_key: str, *, limit: int = 12) -> dict[str, Any]:
    if not member_key or not db.exists():
        return {}
    init_db(db)
    bounded = max(1, min(50, limit))
    with sqlite3.connect(db) as conn:
        items = conn.execute(
            """
            SELECT kind, title, content, tags_json, updated_at
            FROM knowledge_items WHERE member_key = ? AND chat = ?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (member_key, chat, bounded),
        ).fetchall()
        files = conn.execute(
            """
            SELECT category, title, archive_path, created_at
            FROM member_files WHERE member_key = ? AND chat = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (member_key, chat, min(10, bounded)),
        ).fetchall()
        event_bodies = conn.execute(
            """
            SELECT body FROM member_events
            WHERE member_key = ? AND chat = ? AND direction = 'inbound'
            ORDER BY created_at DESC LIMIT 100
            """,
            (member_key, chat),
        ).fetchall()
        report_pdf_count = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM member_files
                WHERE member_key = ? AND chat = ? AND category = 'report'
                  AND lower(suffix) = '.pdf'
                """,
                (member_key, chat),
            ).fetchone()[0]
        )
    explicit_pdf_requests = sum(
        1
        for row in event_bodies
        if pdf_report_requested(str(row[0] or ""))
    )
    pdf_report_preferred = explicit_pdf_requests >= 2 or (
        explicit_pdf_requests >= 1 and report_pdf_count >= 2
    )
    return {
        "scope": "exact_member_and_chat",
        "preferences": {
            "pdf_reports": {
                "preferred_for_substantial_research": pdf_report_preferred,
                "explicit_request_count": explicit_pdf_requests,
                "completed_report_count": report_pdf_count,
                "rule": "Apply to substantial research/report work only; ordinary chat remains concise.",
            }
        },
        "knowledge": [
            {
                "kind": row[0],
                "title": row[1],
                "content": collapse_text(row[2], 1000),
                "tags": json_loads(row[3], []),
                "updated_at": row[4],
            }
            for row in items
        ],
        "files": [
            {"category": row[0], "title": row[1], "path": row[2], "created_at": row[3]}
            for row in files
        ],
    }


def pdf_report_requested(text: str) -> bool:
    value = str(text or "").strip()
    if not value or PDF_REPORT_NEGATION_RE.search(value):
        return False
    return bool(PDF_REPORT_REQUEST_RE.search(value))


def sync_once(db: Path, history_db: Path, queue: Path, archive_root: Path) -> dict[str, Any]:
    init_db(db)
    new_events = backfill_history(db, history_db)
    indexed_tasks = 0
    queue_signature = file_signature(queue)
    queue_state_key = f"queue:{resolved_source_key(queue)}"
    if queue_signature and sync_state_value(db, queue_state_key) != queue_signature:
        indexed_tasks = index_queue_tasks(db, queue, archive_root)
        set_sync_state(db, queue_state_key, queue_signature)
    return {
        "ok": True,
        "db": str(db),
        "archive_root": str(archive_root),
        "new_events": new_events,
        "indexed_tasks": indexed_tasks,
    }


def backfill_history(db: Path, history_db: Path) -> int:
    if not history_db.is_file():
        return 0
    state_key = f"history-row:{resolved_source_key(history_db)}"
    try:
        last_id = int(sync_state_value(db, state_key) or 0)
    except ValueError:
        last_id = 0
    with sqlite3.connect(history_db) as conn:
        rows = conn.execute(
            "SELECT id, message_id, chat, sender, body, create_time, created_at "
            "FROM messages WHERE direction = 'inbound' AND id > ? ORDER BY id",
            (last_id,),
        ).fetchall()
    count = 0
    high_water = last_id
    for row_id, message_id, chat, sender, body, create_time, created_at in rows:
        high_water = max(high_water, int(row_id or 0))
        if not sender:
            continue
        member_key = short_hash(sender)
        upsert_member(db, member_key, chat, display_name="", identity_confidence="history", at=created_at)
        event_key = stable_id("event", member_key, chat, short_hash(message_id))
        with sqlite3.connect(db) as conn:
            duplicate = None
            if ":external-gui:" in str(chat):
                duplicate = conn.execute(
                    "SELECT 1 FROM member_events WHERE chat = ? AND body = ? "
                    "AND ABS(create_time - ?) <= 90 LIMIT 1",
                    (chat, body or "", int(create_time or 0)),
                ).fetchone()
            if duplicate:
                continue
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO member_events(
                    event_key, member_key, chat, direction, body, source_message_hash,
                    create_time, metadata_json, created_at
                ) VALUES (?, ?, ?, 'inbound', ?, ?, ?, '{}', ?)
                """,
                (event_key, member_key, chat, body or "", short_hash(message_id), int(create_time or 0), created_at),
            )
        inserted = max(0, cursor.rowcount)
        count += inserted
        if inserted:
            for item in explicit_memory_items(body or ""):
                record_knowledge_item(
                    db,
                    member_key=member_key,
                    chat=chat,
                    item=item,
                    source_type="history_message",
                    source_id=short_hash(message_id),
                )
    if high_water > last_id:
        set_sync_state(db, state_key, str(high_water))
    return count


def index_queue_tasks(db: Path, queue: Path, archive_root: Path) -> int:
    tasks = read_queue(queue)
    count = 0
    for task in tasks:
        result = task.get("result") if isinstance(task.get("result"), dict) else None
        if not result:
            continue
        if str(task.get("status") or "").casefold() in NONTERMINAL_TASK_STATUSES:
            continue
        member_key = task_member_key(task)
        chat = str(task.get("chat") or "")
        task_id = str(task.get("id") or "")
        if not member_key or not chat or not task_id:
            continue
        fingerprint = stable_id(
            "task-fingerprint",
            str(task.get("status") or ""),
            json.dumps(result, ensure_ascii=False, sort_keys=True, default=str),
            json.dumps(task.get("sent_file_paths") or [], ensure_ascii=False, sort_keys=True),
        )
        with sqlite3.connect(db) as conn:
            row = conn.execute("SELECT fingerprint FROM indexed_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row and row[0] == fingerprint:
            continue
        source = task.get("source") if isinstance(task.get("source"), dict) else {}
        upsert_member(
            db,
            member_key,
            chat,
            display_name=str(source.get("sender_display") or ""),
            identity_confidence=str(source.get("sender_identity_confidence") or "task"),
        )
        source_id = short_hash(source.get("server_id") or task_id)
        message = collapse_text(result.get("message"), 20000)
        if message:
            record_knowledge_item(
                db,
                member_key=member_key,
                chat=chat,
                item={"kind": "agent_summary", "title": derive_task_title(task), "content": message},
                source_type="worker_result",
                source_id=source_id,
                source_task_id=task_id,
            )
        record_knowledge_items(
            db,
            member_key=member_key,
            chat=chat,
            items=result_memory_items(result),
            source_type="worker_result",
            source_id=source_id,
            source_task_id=task_id,
        )
        for file_path in result.get("files") or []:
            path = Path(str(file_path)).expanduser()
            if path.is_file():
                record_member_file(
                    db,
                    member_key=member_key,
                    chat=chat,
                    path=path,
                    source_type="worker_result",
                    source_id=source_id,
                    source_task_id=task_id,
                    archive_root=archive_root,
                    metadata={"task_status": str(task.get("status") or "")},
                )
        for attachment in task_source_files(task):
            path = Path(str(attachment.get("task_copy_path") or attachment.get("path") or "")).expanduser()
            if path.is_file():
                record_member_file(
                    db,
                    member_key=member_key,
                    chat=chat,
                    path=path,
                    source_type="task_source_file",
                    source_id=source_id,
                    source_task_id=task_id,
                    archive_root=archive_root,
                    metadata={"attachment_kind": str(attachment.get("kind") or "file")},
                )
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(db) as conn:
            conn.execute(
                """
                INSERT INTO indexed_tasks(task_id, member_key, chat, status, fingerprint, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    fingerprint = excluded.fingerprint,
                    indexed_at = excluded.indexed_at
                """,
                (task_id, member_key, chat, str(task.get("status") or ""), fingerprint, now),
            )
        count += 1
    return count


def task_member_key(task: dict[str, Any]) -> str:
    daily = task.get("daily_research") if isinstance(task.get("daily_research"), dict) else {}
    if daily.get("member_key"):
        return str(daily["member_key"])
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    if source.get("member_key"):
        return str(source["member_key"])
    sender = str(source.get("sender") or "")
    if sender and not sender.startswith("labcanvas-"):
        return short_hash(sender)
    return ""


def task_source_files(task: dict[str, Any]) -> list[dict[str, Any]]:
    preflight = task.get("transport_preflight") if isinstance(task.get("transport_preflight"), dict) else {}
    media = preflight.get("wecom_media") if isinstance(preflight.get("wecom_media"), dict) else {}
    return [item for item in media.get("copied") or [] if isinstance(item, dict)]


def result_memory_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    values = data.get("knowledge_items") or nested.get("knowledge_items") or []
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def knowledge_status(db: Path) -> dict[str, Any]:
    init_db(db)
    with sqlite3.connect(db) as conn:
        members = conn.execute(
            """
            SELECT m.member_key, m.display_name, m.identity_confidence, m.last_seen_at,
                   (SELECT COUNT(*) FROM member_events e WHERE e.member_key = m.member_key),
                   (SELECT COUNT(*) FROM knowledge_items k WHERE k.member_key = m.member_key),
                   (SELECT COUNT(*) FROM member_files f WHERE f.member_key = m.member_key),
                   (SELECT COUNT(*) FROM member_files f WHERE f.member_key = m.member_key AND f.category = 'paper')
            FROM members m ORDER BY m.last_seen_at DESC
            """
        ).fetchall()
    return {
        "ok": True,
        "db": str(db),
        "member_count": len(members),
        "members": [
            {
                "member_key": row[0],
                "display_name": row[1],
                "identity_confidence": row[2],
                "last_seen_at": row[3],
                "event_count": row[4],
                "knowledge_count": row[5],
                "file_count": row[6],
                "paper_count": row[7],
            }
            for row in members
        ],
    }


def search_knowledge(
    db: Path,
    *,
    query: str,
    member_key: str,
    chat: str,
    kind: str,
    limit: int,
) -> dict[str, Any]:
    init_db(db)
    clauses = ["1 = 1"]
    params: list[Any] = []
    if member_key:
        clauses.append("member_key = ?")
        params.append(member_key)
    if chat:
        clauses.append("chat = ?")
        params.append(chat)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if query:
        clauses.append("(title LIKE ? OR content LIKE ? OR tags_json LIKE ?)")
        needle = f"%{query}%"
        params.extend([needle, needle, needle])
    where = " AND ".join(clauses)
    with sqlite3.connect(db) as conn:
        items = conn.execute(
            f"SELECT id, member_key, chat, kind, title, content, tags_json, source_type, source_task_id, updated_at "
            f"FROM knowledge_items WHERE {where} ORDER BY updated_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        file_clauses = [clause.replace("kind = ?", "category = ?") for clause in clauses if "title LIKE" not in clause]
        file_params = params[:-3] if query else list(params)
        if query:
            file_clauses.append("(title LIKE ? OR filename LIKE ?)")
            needle = f"%{query}%"
            file_params.extend([needle, needle])
        files = conn.execute(
            f"SELECT id, member_key, chat, category, title, filename, archive_path, sha256, source_task_id, created_at "
            f"FROM member_files WHERE {' AND '.join(file_clauses)} ORDER BY created_at DESC LIMIT ?",
            (*file_params, limit),
        ).fetchall()
    return {
        "ok": True,
        "items": [
            {
                "id": row[0], "member_key": row[1], "chat": row[2], "kind": row[3],
                "title": row[4], "content": row[5], "tags": json_loads(row[6], []),
                "source_type": row[7], "source_task_id": row[8], "updated_at": row[9],
            }
            for row in items
        ],
        "files": [
            {
                "id": row[0], "member_key": row[1], "chat": row[2], "category": row[3],
                "title": row[4], "filename": row[5], "archive_path": row[6], "sha256": row[7],
                "source_task_id": row[8], "created_at": row[9],
            }
            for row in files
        ],
    }


def export_member(db: Path, member_key: str, output_dir: Path | None) -> dict[str, Any]:
    payload = search_knowledge(db, query="", member_key=member_key, chat="", kind="", limit=10000)
    output = (output_dir or DEFAULT_ARCHIVE_ROOT / "exports" / member_key).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "knowledge.json"
    md_path = output / "knowledge.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# Member Knowledge {member_key}", "", "## Knowledge", ""]
    for item in payload["items"]:
        lines.extend([f"### {item['title']}", "", f"- Kind: `{item['kind']}`", f"- Updated: {item['updated_at']}", "", item["content"], ""])
    lines.extend(["## Files", ""])
    for item in payload["files"]:
        lines.append(f"- `{item['category']}` {item['title']}: `{item['archive_path']}`")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"ok": True, "member_key": member_key, "json": str(json_path), "markdown": str(md_path)}


def read_queue(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tasks = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            tasks.append(payload)
    return tasks


def sync_state_value(db: Path, source_key: str) -> str:
    init_db(db)
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT value FROM sync_state WHERE source_key = ?",
            (source_key,),
        ).fetchone()
    return str(row[0]) if row else ""


def set_sync_state(db: Path, source_key: str, value: str) -> None:
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO sync_state(source_key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (source_key, value, datetime.now().isoformat(timespec="seconds")),
        )


def resolved_source_key(path: Path) -> str:
    try:
        return short_hash(path.expanduser().resolve())
    except OSError:
        return short_hash(path.expanduser())


def file_signature(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return ""
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def explicit_memory_items(text: str) -> list[dict[str, Any]]:
    value = str(text or "").strip()
    lowered = value.casefold()
    result = []
    for kind, markers in EXPLICIT_MEMORY_MARKERS.items():
        marker = next((item for item in markers if item.casefold() in lowered), "")
        if not marker:
            continue
        content = re.sub(re.escape(marker), "", value, count=1, flags=re.I).strip(" :-：")
        if content:
            result.append({"kind": kind, "title": derive_title(content), "content": content})
    return result


def classify_file(path: Path) -> str:
    suffix = path.suffix.casefold()
    stem = path.stem.casefold()
    if suffix == ".pdf":
        return "report" if any(term in stem for term in REPORT_TERMS) else "paper"
    if suffix in {".bib", ".ris", ".enw"}:
        return "paper_metadata"
    if suffix in {".md", ".tex", ".txt", ".doc", ".docx", ".odt"}:
        return "report" if any(term in stem for term in REPORT_TERMS) else "document"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".tif", ".tiff"}:
        return "figure"
    if suffix in {".step", ".stp", ".stl", ".3mf", ".obj", ".blend", ".scad", ".fcstd"}:
        return "cad"
    if suffix in {".kicad_pcb", ".kicad_sch", ".kicad_pro", ".gbr", ".zip"}:
        return "pcb_or_archive"
    if suffix in {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}:
        return "media"
    return "file"


def archive_member_file(path: Path, root: Path, member_key: str, category: str, digest: str) -> Path:
    date = datetime.fromtimestamp(path.stat().st_mtime)
    target_dir = root.expanduser().resolve() / member_key / category / date.strftime("%Y") / date.strftime("%m")
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(path.name)
    target = target_dir / f"{digest[:12]}-{filename}"
    mode = os.environ.get("WECOM_MEMBER_ARCHIVE_MODE", "copy").strip().casefold()
    if target.exists():
        if mode != "hardlink" and target.stat().st_nlink > 1:
            copy_snapshot(target, target)
        return target
    if mode == "hardlink":
        try:
            os.link(path, target)
            return target
        except OSError:
            pass
    copy_snapshot(path, target)
    return target


def copy_snapshot(source: Path, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def archive_root_for_db(db: Path) -> Path:
    configured = os.environ.get("WECOM_MEMBER_ARCHIVE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    try:
        if db.expanduser().resolve().parent == PRIVATE.resolve():
            return DEFAULT_ARCHIVE_ROOT
    except OSError:
        pass
    return db.expanduser().resolve().parent / "member_knowledge_files"


def normalize_memory_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        content = collapse_text(item.get("content") or item.get("text"), 4000)
        if not content:
            continue
        kind = str(item.get("kind") or "note").casefold().replace("-", "_")
        result.append(
            {
                "kind": kind if kind in KNOWLEDGE_KINDS else "note",
                "title": collapse_text(item.get("title"), 300) or derive_title(content),
                "content": content,
                "tags": normalize_tags(item.get("tags")),
            }
        )
    return result


def task_source_member_key(event: dict[str, Any]) -> str:
    return member_key_for_event(event)


def derive_task_title(task: dict[str, Any]) -> str:
    daily = task.get("daily_research") if isinstance(task.get("daily_research"), dict) else {}
    topics = daily.get("topics") if isinstance(daily.get("topics"), list) else []
    if topics:
        return collapse_text("; ".join(str(item) for item in topics), 300)
    return derive_title(str(task.get("original_request") or task.get("request") or "Agent result"))


def derive_title(content: Any) -> str:
    text = collapse_text(content, 300)
    first = re.split(r"[\n。！？.!?]", text, maxsplit=1)[0].strip()
    return first[:120] or "Untitled"


def normalize_tags(value: Any) -> list[str]:
    source = value if isinstance(value, list) else re.split(r"[,，;；]", str(value or ""))
    result = []
    for item in source:
        tag = collapse_text(item, 80).casefold()
        if tag and tag not in result:
            result.append(tag)
    return result[:20]


def collapse_text(value: Any, max_len: int) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", str(value or "")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_len]


def humanize_stem(value: str) -> str:
    return re.sub(r"[_-]+", " ", value).strip()[:300]


def safe_filename(value: str) -> str:
    name = re.sub(r"[^0-9A-Za-z._()\-\u4e00-\u9fff]+", "-", value).strip("-.")
    return (name or "artifact")[:180]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def short_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def stable_id(*values: Any) -> str:
    payload = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def print_result(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
