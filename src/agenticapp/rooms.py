from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Any, Callable

from .workspace_agent import AgentTaskStore, create_agent_task


ROOM_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
FINAL_TASK_STATES = {"canceled", "completed", "failed", "waiting_confirmation"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_room_id(value: str) -> str:
    room_id = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().casefold()).strip("-")
    if not ROOM_ID_PATTERN.fullmatch(room_id):
        raise ValueError("Room id must contain 1-64 lowercase letters, numbers, dashes, or underscores")
    return room_id


def clean_display_name(value: str, fallback: str) -> str:
    name = " ".join(str(value or "").split())[:80]
    return name or fallback


class RoomStore:
    def __init__(self, storage_dir: str | Path, *, project_root: str | Path | None = None):
        self.storage_dir = Path(storage_dir).resolve()
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.root = self.storage_dir / "rooms"
        self.db_path = self.root / "rooms.sqlite3"
        self.root.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS rooms (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    sender_id TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    task_id TEXT NOT NULL DEFAULT '',
                    artifacts_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_room_cursor
                    ON messages(room_id, id);
                CREATE UNIQUE INDEX IF NOT EXISTS messages_task_reply
                    ON messages(task_id, role)
                    WHERE task_id <> '' AND role = 'assistant';
                CREATE TABLE IF NOT EXISTS task_links (
                    task_id TEXT PRIMARY KEY,
                    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    user_message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    assistant_message_id INTEGER,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS room_invites (
                    id TEXT PRIMARY KEY,
                    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS room_invites_room
                    ON room_invites(room_id, expires_at);
                """
            )

    def ensure_room(self, room_id: str, name: str = "") -> dict[str, Any]:
        normalized = normalize_room_id(room_id)
        supplied_name = " ".join(str(name or "").split())[:80]
        display_name = supplied_name or normalized
        timestamp = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO rooms(id, name, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = CASE WHEN ? <> '' THEN ? ELSE rooms.name END",
                (normalized, display_name, timestamp, timestamp, supplied_name, supplied_name),
            )
            row = connection.execute("SELECT * FROM rooms WHERE id = ?", (normalized,)).fetchone()
        return self.public_room(row)

    def create_invite(self, room_id: str, *, label: str = "WeChat invite", expires_hours: int = 168) -> dict[str, Any]:
        normalized = normalize_room_id(room_id)
        self.ensure_room(normalized)
        lifetime = min(24 * 30, max(1, int(expires_hours)))
        created = datetime.now(timezone.utc)
        expires = created + timedelta(hours=lifetime)
        raw_token = secrets.token_urlsafe(32)
        invite_id = secrets.token_urlsafe(9)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO room_invites(id, room_id, token_hash, label, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    invite_id,
                    normalized,
                    self.invite_token_hash(raw_token),
                    clean_display_name(label, "WeChat invite"),
                    self.format_time(created),
                    self.format_time(expires),
                ),
            )
            row = connection.execute("SELECT * FROM room_invites WHERE id = ?", (invite_id,)).fetchone()
        return {**self.public_invite(row), "token": raw_token}

    def list_invites(self, room_id: str) -> list[dict[str, Any]]:
        normalized = normalize_room_id(room_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM room_invites WHERE room_id = ? ORDER BY created_at DESC",
                (normalized,),
            ).fetchall()
        return [self.public_invite(row) for row in rows]

    def validate_invite(self, room_id: str, token: str) -> dict[str, Any] | None:
        normalized = normalize_room_id(room_id)
        supplied = str(token or "").strip()
        if not supplied or len(supplied) > 256:
            return None
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM room_invites WHERE room_id = ? AND token_hash = ? "
                "AND revoked_at = '' AND expires_at > ?",
                (normalized, self.invite_token_hash(supplied), now),
            ).fetchone()
        return self.public_invite(row) if row is not None else None

    def revoke_invite(self, room_id: str, invite_id: str) -> bool:
        normalized = normalize_room_id(room_id)
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE room_invites SET revoked_at = ? WHERE room_id = ? AND id = ? AND revoked_at = ''",
                (utc_now(), normalized, str(invite_id or "").strip()),
            )
        return bool(cursor.rowcount)

    def seed_default_rooms(self) -> None:
        self.ensure_room("labagent", "LabAgent")
        self.ensure_room("agenttest", "AgentTest")

    def list_rooms(self) -> list[dict[str, Any]]:
        self.seed_default_rooms()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT rooms.*, COUNT(messages.id) AS message_count,
                       MAX(messages.id) AS last_message_id
                FROM rooms
                LEFT JOIN messages ON messages.room_id = rooms.id
                GROUP BY rooms.id
                ORDER BY rooms.updated_at DESC, rooms.name ASC
                """
            ).fetchall()
        return [self.public_room(row) for row in rows]

    def list_messages(self, room_id: str, *, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        normalized = normalize_room_id(room_id)
        self.ensure_room(normalized)
        bounded_limit = min(500, max(1, int(limit)))
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM messages WHERE room_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
                (normalized, max(0, int(after)), bounded_limit),
            ).fetchall()
        return [self.public_message(row) for row in rows]

    def recent_context(self, room_id: str, limit: int = 24) -> list[dict[str, str]]:
        normalized = normalize_room_id(room_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT role, sender_name, content FROM messages WHERE room_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (normalized, min(50, max(1, int(limit)))),
            ).fetchall()
        return [
            {"role": str(row["role"]), "sender": str(row["sender_name"]), "content": str(row["content"])}
            for row in reversed(rows)
        ]

    def post_user_message(
        self,
        room_id: str,
        content: str,
        *,
        sender_id: str = "local-owner",
        sender_name: str = "Owner",
        agent_options: dict[str, Any] | None = None,
        task_creator: Callable[..., dict[str, Any]] = create_agent_task,
    ) -> dict[str, Any]:
        normalized = normalize_room_id(room_id)
        text = str(content or "").strip()
        if not text:
            raise ValueError("Message cannot be empty")
        if len(text.encode("utf-8")) > 128 * 1024:
            raise ValueError("Message exceeds the 128 KiB room limit")
        room = self.ensure_room(normalized)
        context = self.recent_context(normalized)
        timestamp = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO messages(room_id, role, sender_id, sender_name, content, created_at) "
                "VALUES (?, 'user', ?, ?, ?, ?)",
                (
                    normalized,
                    clean_display_name(sender_id, "local-owner"),
                    clean_display_name(sender_name, "Owner"),
                    text,
                    timestamp,
                ),
            )
            message_id = int(cursor.lastrowid)
            connection.execute("UPDATE rooms SET updated_at = ? WHERE id = ?", (timestamp, normalized))

        options = dict(agent_options or {})
        access_role = str(options.pop("_room_access_role", "owner") or "owner")
        options.update(
            {
                "message": text,
                "conversation_id": f"room-{normalized}",
                "context": {
                    "transport": "labcanvas_rooms",
                    "room": room,
                    "sender": {"id": sender_id, "name": sender_name},
                    "recent_messages": context,
                    "access_role": access_role,
                    "access_contract": (
                        "Invited participants are read-only planning users. Do not inspect private files, "
                        "edit the workspace, operate applications, publish, purchase, or change external state."
                        if access_role == "participant"
                        else "The local room owner may use normal LabCanvas capabilities subject to confirmation gates."
                    ),
                },
            }
        )
        task_result = task_creator(options, self.storage_dir, root=self.project_root, launch=True)
        task = task_result.get("task") if isinstance(task_result, dict) else None
        if not isinstance(task, dict) or not task.get("id"):
            raise RuntimeError("Workspace agent did not create a durable room task")
        task_id = str(task["id"])
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO task_links(task_id, room_id, user_message_id, status, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_id, normalized, message_id, str(task.get("status") or "queued"), utc_now()),
            )
        return {
            "ok": True,
            "room": room,
            "message": self.message_by_id(message_id),
            "task": task,
        }

    def sync_tasks(
        self,
        room_id: str,
        *,
        task_reader: Callable[[str], dict[str, Any]] | None = None,
    ) -> int:
        normalized = normalize_room_id(room_id)
        reader = task_reader or AgentTaskStore(self.storage_dir).read
        with self.connect() as connection:
            links = connection.execute(
                "SELECT * FROM task_links WHERE room_id = ? AND assistant_message_id IS NULL",
                (normalized,),
            ).fetchall()
        synced = 0
        for link in links:
            try:
                task = reader(str(link["task_id"]))
            except (KeyError, OSError, ValueError):
                continue
            status = str(task.get("status") or "queued")
            if status not in FINAL_TASK_STATES:
                with self.connect() as connection:
                    connection.execute(
                        "UPDATE task_links SET status = ?, updated_at = ? WHERE task_id = ?",
                        (status, utc_now(), str(link["task_id"])),
                    )
                continue
            content = str(task.get("reply") or "").strip()
            if not content:
                content = (
                    f"Task failed: {str(task.get('error') or 'no agent response')[:600]}"
                    if status == "failed"
                    else f"Task {status}."
                )
            artifacts = task.get("artifacts") if isinstance(task.get("artifacts"), list) else []
            timestamp = utc_now()
            with self.connect() as connection:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO messages("
                    "room_id, role, sender_id, sender_name, content, task_id, artifacts_json, created_at"
                    ") VALUES (?, 'assistant', 'labcanvas-agent', 'LabCanvas', ?, ?, ?, ?)",
                    (normalized, content, str(link["task_id"]), json.dumps(artifacts), timestamp),
                )
                if cursor.rowcount:
                    assistant_id = int(cursor.lastrowid)
                    synced += 1
                else:
                    existing = connection.execute(
                        "SELECT id FROM messages WHERE task_id = ? AND role = 'assistant'",
                        (str(link["task_id"]),),
                    ).fetchone()
                    assistant_id = int(existing["id"]) if existing else 0
                connection.execute(
                    "UPDATE task_links SET assistant_message_id = ?, status = ?, updated_at = ? "
                    "WHERE task_id = ?",
                    (assistant_id or None, status, timestamp, str(link["task_id"])),
                )
                connection.execute("UPDATE rooms SET updated_at = ? WHERE id = ?", (timestamp, normalized))
        return synced

    def artifact_for_message(self, room_id: str, message_id: int, artifact_index: int) -> dict[str, Any]:
        normalized = normalize_room_id(room_id)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT artifacts_json FROM messages WHERE room_id = ? AND id = ? AND role = 'assistant'",
                (normalized, int(message_id)),
            ).fetchone()
        if row is None:
            raise KeyError("Unknown room artifact message")
        try:
            artifacts = json.loads(str(row["artifacts_json"] or "[]"))
        except json.JSONDecodeError as exc:
            raise KeyError("Room artifact manifest is invalid") from exc
        if not isinstance(artifacts, list) or artifact_index < 0 or artifact_index >= len(artifacts):
            raise KeyError("Unknown room artifact")
        artifact = artifacts[artifact_index]
        if not isinstance(artifact, dict) or not str(artifact.get("path") or "").strip():
            raise KeyError("Room artifact has no readable path")
        return artifact

    def message_by_id(self, message_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM messages WHERE id = ?", (int(message_id),)).fetchone()
        if row is None:
            raise KeyError(f"Unknown room message: {message_id}")
        return self.public_message(row)

    @staticmethod
    def public_room(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise KeyError("Room does not exist")
        keys = set(row.keys())
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "message_count": int(row["message_count"] or 0) if "message_count" in keys else 0,
            "last_message_id": int(row["last_message_id"] or 0) if "last_message_id" in keys else 0,
        }

    @staticmethod
    def public_message(row: sqlite3.Row) -> dict[str, Any]:
        try:
            artifacts = json.loads(str(row["artifacts_json"] or "[]"))
        except json.JSONDecodeError:
            artifacts = []
        return {
            "id": int(row["id"]),
            "room_id": str(row["room_id"]),
            "role": str(row["role"]),
            "sender_id": str(row["sender_id"]),
            "sender_name": str(row["sender_name"]),
            "content": str(row["content"]),
            "task_id": str(row["task_id"]),
            "artifacts": artifacts if isinstance(artifacts, list) else [],
            "created_at": str(row["created_at"]),
        }

    @staticmethod
    def public_invite(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise KeyError("Room invite does not exist")
        return {
            "id": str(row["id"]),
            "room_id": str(row["room_id"]),
            "label": str(row["label"]),
            "created_at": str(row["created_at"]),
            "expires_at": str(row["expires_at"]),
            "revoked": bool(str(row["revoked_at"] or "")),
        }

    @staticmethod
    def invite_token_hash(token: str) -> str:
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    @staticmethod
    def format_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
