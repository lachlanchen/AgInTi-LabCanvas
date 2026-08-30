#!/usr/bin/env python3
"""Bridge exact WeChat Android notifications into existing direct-chat monitors."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from typing import Any

from wechat_android_send import target_aliases, text_matches_alias
from wechat_chat_profiles import profile_aliases


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_TARGETS = PRIVATE / "wechat_send_targets.local.json"
DEFAULT_DB = PRIVATE / "wechat_android_ingress" / "message_999999.db"
DEFAULT_CONFIG_GLOB = "*direct-chatops.local.json"
PACKAGE = "art.lazying.labcanvas.wechatbridge"
LISTENER_COMPONENTS = (
    f"{PACKAGE}/.WechatNotificationListener",
    f"{PACKAGE}/{PACKAGE}.WechatNotificationListener",
)
EVENT_FILE = "files/events.jsonl"
SYNTHETIC_DB_NAME = "message_999999.db"
TABLE_RE = re.compile(r"^Msg_[0-9A-Za-z_]+$")
GENERIC_NOTIFICATION_RE = re.compile(
    r"^(?:微信|WeChat|你收到(?:了)?\s*\d+\s*条消息|\d+\s*条新消息|"
    r"\[?(?:图片|视频|语音|文件|动画表情|表情)\]?)$",
    flags=re.IGNORECASE,
)


class AndroidIngressError(RuntimeError):
    """Raised when the private mobile ingress contract cannot be satisfied."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    parser.add_argument("--configs", default=os.environ.get("WECHAT_DIRECT_CONFIGS", ""))
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument(
        "--replay-existing",
        action="store_true",
        help="Import existing app events on first start instead of seeding them as already seen.",
    )
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    serial = resolve_serial(args.adb, args.serial)
    configs = load_configs(args.configs)
    targets = load_targets(args.targets_file)
    bridge = AndroidWechatIngress(
        adb=args.adb,
        serial=serial,
        configs=configs,
        targets=targets,
        db_path=args.db.expanduser().resolve(),
    )
    if args.status:
        print(json.dumps(bridge.status(), ensure_ascii=False, indent=2))
        return 0

    while True:
        result = bridge.run_once(replay_existing=args.replay_existing)
        if result["imported"] or result["seeded"] or result["skipped_unmapped"]:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.loop:
            return 0
        time.sleep(max(0.25, float(args.interval)))


class AndroidWechatIngress:
    def __init__(
        self,
        *,
        adb: str,
        serial: str,
        configs: list[dict[str, Any]],
        targets: dict[str, Any],
        db_path: Path,
    ) -> None:
        self.adb = adb
        self.serial = serial
        self.configs = configs
        self.targets = targets
        self.db_path = db_path
        self.routes = build_routes(configs, targets)
        self.init_db()

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS Name2Id (user_name TEXT UNIQUE)")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS AndroidIngressSeen ("
                "item_key TEXT PRIMARY KEY, event_sequence INTEGER NOT NULL, "
                "status TEXT NOT NULL, config_id TEXT NOT NULL DEFAULT '', "
                "seen_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS AndroidIngressMeta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            for route in self.routes:
                ensure_message_table(conn, route["message_table"])
        os.chmod(self.db_path, 0o600)

    def run_once(self, *, replay_existing: bool = False) -> dict[str, Any]:
        events = read_device_events(self.adb, self.serial)
        initialized = self.meta("initialized") == "1"
        if not initialized and not replay_existing:
            seeded = self.seed_events(events)
            self.set_meta("initialized", "1")
            return safe_result(events=len(events), seeded=seeded)

        imported = 0
        duplicates = 0
        skipped_unmapped = 0
        skipped_nontext = 0
        for event in events:
            if event.get("kind") != "notification_posted" or event.get("package") != "com.tencent.mm":
                continue
            route = match_route(event, self.routes)
            items = notification_items(event)
            if route is None:
                for item in items:
                    key = notification_item_key(event, item)
                    if self.mark_seen(key, event, "unmapped", ""):
                        skipped_unmapped += 1
                    else:
                        duplicates += 1
                continue
            for item in items:
                key = notification_item_key(event, item)
                content = normalize_text(item.get("text"))
                if not useful_text(content):
                    if self.mark_seen(key, event, "nontext", route["config_id"]):
                        skipped_nontext += 1
                    else:
                        duplicates += 1
                    continue
                sender, content = notification_sender_and_text(event, item, route, content)
                if self.insert_message(key, event, route, sender, content):
                    imported += 1
                else:
                    duplicates += 1
        if not initialized:
            self.set_meta("initialized", "1")
        self.set_meta("last_poll_at", utc_now())
        return safe_result(
            events=len(events),
            imported=imported,
            duplicates=duplicates,
            skipped_unmapped=skipped_unmapped,
            skipped_nontext=skipped_nontext,
        )

    def seed_events(self, events: list[dict[str, Any]]) -> int:
        seeded = 0
        for event in events:
            if event.get("kind") != "notification_posted" or event.get("package") != "com.tencent.mm":
                continue
            for item in notification_items(event):
                if self.mark_seen(notification_item_key(event, item), event, "seeded", ""):
                    seeded += 1
        self.set_meta("last_poll_at", utc_now())
        return seeded

    def insert_message(
        self,
        item_key: str,
        event: dict[str, Any],
        route: dict[str, Any],
        sender: str,
        content: str,
    ) -> bool:
        table = route["message_table"]
        sequence = int(event.get("sequence") or 0)
        create_time = max(1, int((int(event.get("post_time_ms") or event.get("captured_at_ms") or 0)) / 1000))
        server_id = "android-" + item_key[:32]
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM AndroidIngressSeen WHERE item_key = ?", (item_key,)
            ).fetchone():
                return False
            conn.execute("INSERT OR IGNORE INTO Name2Id(user_name) VALUES (?)", (sender,))
            sender_row = conn.execute(
                "SELECT rowid FROM Name2Id WHERE user_name = ?", (sender,)
            ).fetchone()
            next_local = int(
                conn.execute(f"SELECT COALESCE(MAX(local_id), 0) + 1 FROM {table}").fetchone()[0]
            )
            conn.execute(
                f"INSERT INTO {table}(local_id,server_id,local_type,real_sender_id,create_time,status,"
                "message_content,compress_content,WCDB_CT_message_content) VALUES (?,?,?,?,?,?,?,?,?)",
                (next_local, server_id, 1, int(sender_row[0]), create_time, 3, content, None, 0),
            )
            conn.execute(
                "INSERT INTO AndroidIngressSeen(item_key,event_sequence,status,config_id,seen_at) "
                "VALUES(?,?,?,?,?)",
                (item_key, sequence, "imported", route["config_id"], utc_now()),
            )
        return True

    def mark_seen(
        self,
        item_key: str,
        event: dict[str, Any],
        status: str,
        config_id: str,
    ) -> bool:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            before = conn.total_changes
            conn.execute(
                "INSERT OR IGNORE INTO AndroidIngressSeen(item_key,event_sequence,status,config_id,seen_at) "
                "VALUES(?,?,?,?,?)",
                (item_key, int(event.get("sequence") or 0), status, config_id, utc_now()),
            )
            return conn.total_changes > before

    def meta(self, key: str) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM AndroidIngressMeta WHERE key = ?", (key,)
            ).fetchone()
        return str(row[0]) if row else ""

    def set_meta(self, key: str, value: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO AndroidIngressMeta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def status(self) -> dict[str, Any]:
        package_probe = subprocess.run(
            [self.adb, "-s", self.serial, "shell", "pm", "path", PACKAGE],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        package_installed = (
            package_probe.returncode == 0
            and any(
                line.strip().startswith("package:")
                for line in package_probe.stdout.splitlines()
            )
        )
        listener_probe = subprocess.run(
            [
                self.adb,
                "-s",
                self.serial,
                "shell",
                "settings",
                "get",
                "secure",
                "enabled_notification_listeners",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        listener_enabled = (
            listener_probe.returncode == 0
            and any(component in listener_probe.stdout for component in LISTENER_COMPONENTS)
        )
        process_probe = subprocess.run(
            [self.adb, "-s", self.serial, "shell", "pidof", PACKAGE],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        listener_live = (
            process_probe.returncode == 0
            and bool(process_probe.stdout.strip())
        )
        with sqlite3.connect(self.db_path) as conn:
            counts = {
                status: count
                for status, count in conn.execute(
                    "SELECT status, COUNT(*) FROM AndroidIngressSeen GROUP BY status"
                )
            }
        return {
            "ok": package_installed and listener_enabled and listener_live and bool(self.routes),
            "package_installed": package_installed,
            "listener_enabled": listener_enabled,
            "listener_live": listener_live,
            "routes": len(self.routes),
            "initialized": self.meta("initialized") == "1",
            "last_poll_at": self.meta("last_poll_at"),
            "counts": counts,
            "synthetic_db": SYNTHETIC_DB_NAME,
        }


def resolve_serial(adb: str, requested: str) -> str:
    if requested.strip():
        return requested.strip()
    proc = subprocess.run([adb, "devices"], capture_output=True, text=True, check=False, timeout=10)
    devices = [line.split()[0] for line in proc.stdout.splitlines()[1:] if line.strip().endswith("\tdevice")]
    if len(devices) != 1:
        raise AndroidIngressError("set ANDROID_SERIAL when exactly one authorized device is not available")
    return devices[0]


def load_configs(raw: str) -> list[dict[str, Any]]:
    paths = [Path(item.strip()).expanduser() for item in str(raw or "").split(",") if item.strip()]
    if not paths:
        paths = sorted(PRIVATE.glob(DEFAULT_CONFIG_GLOB))
    configs = []
    for path in paths:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        table = str(config.get("message_table") or "")
        if not TABLE_RE.fullmatch(table):
            continue
        config["config_id"] = path.name
        configs.append(config)
    if not configs:
        raise AndroidIngressError("no valid direct-chat config is available")
    return configs


def load_targets(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_routes(configs: list[dict[str, Any]], targets: dict[str, Any]) -> list[dict[str, Any]]:
    routes = []
    for config in configs:
        chat_name = str(config.get("chat_name") or "").strip()
        send_target = str(config.get("send_target") or chat_name).strip()
        target = targets.get(send_target) or targets.get(chat_name) or {"name": chat_name}
        aliases = list(target_aliases(target if isinstance(target, dict) else {"name": chat_name}))
        aliases.extend(profile_aliases(str(config.get("profile_id") or "")))
        unique_aliases = tuple(dict.fromkeys(alias for alias in aliases if str(alias).strip()))
        if chat_name and unique_aliases:
            routes.append(
                {
                    "config_id": str(config["config_id"]),
                    "chat_name": chat_name,
                    "message_table": str(config["message_table"]),
                    "is_group": str(config.get("chatroom_id") or "").endswith("@chatroom"),
                    "aliases": unique_aliases,
                }
            )
    return routes


def read_device_events(adb: str, serial: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [adb, "-s", serial, "exec-out", "run-as", PACKAGE, "cat", EVENT_FILE],
        capture_output=True,
        check=False,
        timeout=15,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").lower()
        if "no such file" in stderr:
            return []
        raise AndroidIngressError("notification companion is unavailable or not debuggable")
    events = []
    for raw_line in proc.stdout.decode("utf-8", errors="replace").splitlines()[-2000:]:
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("schema") == "labcanvas-wechat-notification-v1":
            events.append(event)
    return events


def notification_items(event: dict[str, Any]) -> list[dict[str, Any]]:
    messages = event.get("messages")
    if isinstance(messages, list):
        items = [item for item in messages if isinstance(item, dict) and normalize_text(item.get("text"))]
        if items:
            return items
    lines = event.get("text_lines")
    if isinstance(lines, list):
        items = [{"text": line, "sender": "", "timestamp_ms": 0} for line in lines if normalize_text(line)]
        if items:
            return items
    text = normalize_text(event.get("big_text")) or normalize_text(event.get("text"))
    return [{"text": text, "sender": "", "timestamp_ms": 0}] if text else []


def match_route(event: dict[str, Any], routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        normalize_text(event.get(key))
        for key in ("conversation_title", "title", "sub_text", "summary_text", "info_text")
        if normalize_text(event.get(key))
    ]
    matches = [
        route
        for route in routes
        if any(text_matches_alias(candidate, route["aliases"]) for candidate in candidates)
    ]
    unique = {route["config_id"]: route for route in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None


def notification_sender_and_text(
    event: dict[str, Any],
    item: dict[str, Any],
    route: dict[str, Any],
    content: str,
) -> tuple[str, str]:
    sender = normalize_text(item.get("sender"))
    if route["is_group"]:
        parts = re.split(r"\s*[:：]\s*", content, maxsplit=1)
        prefix, remainder = parts if len(parts) == 2 else ("", "")
        if prefix and 0 < len(prefix) <= 80 and remainder:
            if not sender:
                sender = prefix
            content = remainder
        if not sender:
            title = normalize_text(event.get("title"))
            if title and not text_matches_alias(title, route["aliases"]):
                sender = title
    else:
        sender = sender or normalize_text(event.get("title")) or route["chat_name"]
    return sender or "wechat-notification-user", content


def notification_item_key(event: dict[str, Any], item: dict[str, Any]) -> str:
    identity = json.dumps(
        {
            "key": event.get("notification_key"),
            "post_time_ms": event.get("post_time_ms"),
            "title": event.get("title"),
            "sender": item.get("sender"),
            "text": item.get("text"),
            "timestamp_ms": item.get("timestamp_ms"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def ensure_message_table(conn: sqlite3.Connection, table: str) -> None:
    if not TABLE_RE.fullmatch(table):
        raise AndroidIngressError("invalid direct-chat message table")
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "local_id INTEGER PRIMARY KEY, server_id TEXT UNIQUE, local_type INTEGER, "
        "real_sender_id INTEGER, create_time INTEGER, status INTEGER, "
        "message_content BLOB, compress_content BLOB, WCDB_CT_message_content INTEGER)"
    )


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u0000", " ")).strip()


def useful_text(value: str) -> bool:
    return bool(value and not GENERIC_NOTIFICATION_RE.fullmatch(value))


def safe_result(**values: Any) -> dict[str, Any]:
    defaults = {
        "ok": True,
        "events": 0,
        "seeded": 0,
        "imported": 0,
        "duplicates": 0,
        "skipped_unmapped": 0,
        "skipped_nontext": 0,
        "synthetic_db": SYNTHETIC_DB_NAME,
    }
    defaults.update(values)
    return defaults


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
