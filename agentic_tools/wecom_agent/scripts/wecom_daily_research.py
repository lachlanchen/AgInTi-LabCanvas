#!/usr/bin/env python3
"""Manage per-group #daily topics and enqueue idempotent WeCom research briefings."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Callable
from urllib import error, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
SHARED_AGENT_SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
if str(SHARED_AGENT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_AGENT_SCRIPTS))

from wechat_routines import ensure_task_routine_contract  # noqa: E402
from wecom_member_knowledge import knowledge_db_for_history, member_context  # noqa: E402


DEFAULT_QUEUE = PRIVATE / "wecom_task_queue.jsonl"
DEFAULT_STATE_DB = PRIVATE / "wecom_messages.local.sqlite"
DEFAULT_HEALTH_PATH = PRIVATE / "wecom_daily_research.health.json"
DEFAULT_API_URL = "http://127.0.0.1:19578"
DEFAULT_CLI_CONFIG = PRIVATE / "wecom_cli_bridge.local.json"
DEFAULT_GUI_CONFIG = PRIVATE / "wecom_gui_bridge.local.json"
DAILY_PREFIX = re.compile(r"^\s*#daily(?:\s+|$)(.*)$", re.IGNORECASE | re.DOTALL)
DAILY_SUFFIX = re.compile(r"^(.*?)\s*#daily\s*$", re.IGNORECASE | re.DOTALL)
INTEREST_PREFIX = re.compile(r"^\s*#(?:interest|inspire)(?:\s+|$)(.*)$", re.IGNORECASE | re.DOTALL)
INTEREST_SUFFIX = re.compile(r"^(.*?)\s*#(?:interest|inspire)\s*$", re.IGNORECASE | re.DOTALL)
STATUS_WORDS = {"status", "show", "list", "状态", "狀態", "查看", "列表"}
OFF_WORDS = {"off", "clear", "remove", "取消", "清除", "关闭", "關閉"}
PAUSE_WORDS = {"pause", "disable", "stop", "暂停", "暫停", "停用"}
ON_WORDS = {"on", "enable", "start", "开启", "開啟", "启用", "啟用"}
INSPIRATION_FINAL_STATUSES = {
    "done",
    "failed",
    "worker_failed",
    "send_failed",
    "send_expired",
    "cancelled",
    "canceled",
    "canceled_superseded",
    "expired",
    "expired_stale",
    "rejected",
}
CHAT_BUSY_STATUSES = {
    "pending",
    "in_progress",
    "generation_waiting",
    "generation_poststage_pending",
    "publish_poststage_pending",
    "send_deferred_artifact",
    "send_deferred_locked",
    "send_retrying",
    "waiting_confirmation",
}
QUIET_START_HOUR = 20
QUIET_END_HOUR = 8


def in_scheduled_quiet_hours(now: datetime | None = None) -> bool:
    """Keep only periodic LabAgent inspiration quiet overnight in HKT."""
    timezone = configured_timezone()
    current = now.astimezone(timezone) if now and now.tzinfo else (now.replace(tzinfo=timezone) if now else datetime.now(timezone))
    hour = current.hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


def write_scheduler_heartbeat(
    path: Path,
    *,
    status: str,
    payload: dict[str, Any] | None = None,
    error_text: str = "",
) -> None:
    """Publish transport-safe liveness without chat content or raw identifiers."""
    body = payload if isinstance(payload, dict) else {}
    heartbeat = {
        "checked_at": datetime.now(configured_timezone()).isoformat(timespec="seconds"),
        "status": status,
        "daily_checked": int(body.get("checked_chats") or body.get("checked") or 0),
        "inspiration_checked": int((body.get("inspiration") or {}).get("checked") or 0),
        "action_count": len(body.get("actions") or []),
        "inspiration_action_count": len((body.get("inspiration") or {}).get("actions") or []),
        "busy_chat_count": len((body.get("inspiration") or {}).get("busy_chats") or []),
        "error": error_text[:500],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(heartbeat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run one due-check cycle.")
    add_common_arguments(run)
    run.add_argument("--force", action="store_true", help="Ignore the configured clock, while retaining daily deduplication.")

    loop = subparsers.add_parser("loop", help="Run the durable daily scheduler loop.")
    add_common_arguments(loop)
    loop.add_argument("--poll-seconds", type=float, default=float(os.environ.get("WECOM_DAILY_POLL_SECONDS", "30")))
    loop.add_argument(
        "--health-path",
        type=Path,
        default=Path(os.environ.get("WECOM_DAILY_HEALTH_PATH", DEFAULT_HEALTH_PATH)),
    )

    status = subparsers.add_parser("status", help="Show enrolled chats and daily topics without raw chat IDs.")
    status.add_argument("--state-db", type=Path, default=Path(os.environ.get("WECOM_DAILY_STATE_DB", DEFAULT_STATE_DB)))
    status.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "status":
        payload = daily_status(args.state_db)
        print_result(payload, args.json)
        return 0

    if args.command == "run":
        quiet = in_scheduled_quiet_hours()
        payload = run_scheduler_cycle(
            state_db=args.state_db,
            history_db=args.history_db,
            queue=args.queue,
            force=args.force,
            include_inspiration=not quiet,
        )
        print_result(payload, args.json)
        return 0 if payload.get("ok") else 1

    interval = max(5.0, min(3600.0, float(args.poll_seconds)))
    while True:
        try:
            quiet = in_scheduled_quiet_hours()
            payload = run_scheduler_cycle(
                state_db=args.state_db,
                history_db=args.history_db,
                queue=args.queue,
                include_inspiration=not quiet,
            )
            status = "quiet_hours_periodic_only" if quiet else "ok"
            write_scheduler_heartbeat(args.health_path, status=status, payload=payload)
            if payload.get("actions"):
                print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
        except Exception as exc:  # Keep the scheduler alive across transient API/DB failures.
            error_text = f"{type(exc).__name__}: {str(exc)[:500]}"
            write_scheduler_heartbeat(args.health_path, status="error", error_text=error_text)
            print(
                json.dumps({"ok": False, "error": error_text}, ensure_ascii=False),
                file=sys.stderr,
                flush=True,
            )
        time.sleep(interval)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-db", type=Path, default=Path(os.environ.get("WECOM_DAILY_STATE_DB", DEFAULT_STATE_DB)))
    parser.add_argument("--history-db", type=Path, default=Path(os.environ.get("WECOM_HISTORY_DB", DEFAULT_STATE_DB)))
    parser.add_argument("--queue", type=Path, default=Path(os.environ.get("WECOM_TASK_QUEUE", DEFAULT_QUEUE)))
    parser.add_argument("--json", action="store_true")


def init_daily_state(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_chats (
                chat TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_chats)")}
        if "transport_channel" not in columns:
            conn.execute(
                "ALTER TABLE daily_chats ADD COLUMN transport_channel "
                "TEXT NOT NULL DEFAULT 'wecom_bot_websocket'"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_preferences (
                chat TEXT NOT NULL,
                sender_hash TEXT NOT NULL,
                topic TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(chat, sender_hash)
            )
            """
        )
        preference_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(daily_preferences)")
        }
        if "topics_json" not in preference_columns:
            conn.execute(
                "ALTER TABLE daily_preferences ADD COLUMN topics_json "
                "TEXT NOT NULL DEFAULT '[]'"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_runs (
                chat TEXT NOT NULL,
                run_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                task_id TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(chat, run_date, kind)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inspiration_settings (
                chat TEXT PRIMARY KEY,
                topics_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                interval_seconds INTEGER NOT NULL DEFAULT 10800,
                last_enqueued_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inspiration_settings_enabled "
            "ON inspiration_settings(enabled, updated_at)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_preferences_chat ON daily_preferences(chat, enabled)")


def register_group(path: Path, event: dict[str, Any], chat: str) -> bool:
    if str(event.get("chat_type") or "") != "group":
        return False
    init_daily_state(path)
    now = datetime.now().isoformat(timespec="seconds")
    auto_enroll = 0 if os.environ.get("WECOM_DAILY_AUTO_ENROLL", "1") == "0" else 1
    with sqlite3.connect(path) as conn:
        existed = bool(conn.execute("SELECT 1 FROM daily_chats WHERE chat = ?", (chat,)).fetchone())
        conn.execute(
            """
            INSERT INTO daily_chats(chat, account_id, chat_id, chat_type, transport_channel, enabled, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, 'group', ?, ?, ?, ?)
            ON CONFLICT(chat) DO UPDATE SET
                account_id = excluded.account_id,
                chat_id = excluded.chat_id,
                chat_type = excluded.chat_type,
                transport_channel = excluded.transport_channel,
                last_seen_at = excluded.last_seen_at
            """,
            (
                chat,
                str(event.get("account_id") or "default"),
                str(event.get("chat_id") or ""),
                str(event.get("transport_channel") or "wecom_bot_websocket"),
                auto_enroll,
                now,
                now,
            ),
        )
    return not existed


def mark_inline_topic_prompt(path: Path, chat: str, *, now: datetime | None = None) -> None:
    timezone = configured_timezone()
    current = now.astimezone(timezone) if now and now.tzinfo else (now.replace(tzinfo=timezone) if now else datetime.now(timezone))
    record_daily_run(
        path,
        chat,
        current.date().isoformat(),
        "topic_prompt",
        "sent_inline_welcome",
        f"wecom-daily-welcome-{current.date().isoformat()}-{short_hash(chat)}",
    )


def handle_daily_directive(path: Path, event: dict[str, Any], chat: str) -> str | None:
    result = handle_daily_directive_result(path, event, chat)
    return str(result.get("reply") or "") if result is not None else None


def handle_daily_directive_result(
    path: Path,
    event: dict[str, Any],
    chat: str,
) -> dict[str, Any] | None:
    command = parse_daily_directive(str(event.get("text") or ""))
    if command is None:
        return None
    if str(event.get("chat_type") or "") != "group":
        return {
            "action": "wrong_chat_type",
            "reply": "#daily 用于研究群。请在目标群里发送“你的研究兴趣 #daily”。",
        }
    if (
        str(event.get("transport_channel") or "") == "wecom_gui"
        and str(event.get("sender_identity_confidence") or "") == "unresolved"
    ):
        return {
            "action": "sender_unresolved",
            "reply": "未能稳定识别这条消息的发送者，未保存 #daily 兴趣。请稍后重新发送一次。",
        }

    register_group(path, event, chat)
    command_key = command.casefold()
    sender_hash = short_hash(event.get("sender_userid"))
    role = str(event.get("authorization_role") or "")

    if not command:
        set_group_enabled(path, chat, True)
        topics = active_topics(path, chat)
        if topics:
            reply = "当前每日研究兴趣：\n" + "\n".join(f"- {topic}" for topic in topics) + "\n发送“新兴趣 #daily”可加入你的每日任务。"
        else:
            reply = "今天想让 LabAgent 跟踪什么研究主题？请发送：你的研究兴趣 #daily"
        return {"action": "show_or_prompt", "reply": reply}

    if command_key in STATUS_WORDS:
        topics = active_topics(path, chat)
        if not topics:
            reply = "这个群还没有每日研究兴趣。发送“你的研究兴趣 #daily”即可设置。"
        else:
            reply = "当前每日研究兴趣：\n" + "\n".join(f"- {topic}" for topic in topics)
        return {"action": "status", "reply": reply}

    if command_key in OFF_WORDS:
        disable_sender_preference(path, chat, sender_hash)
        topics = active_topics(path, chat)
        if not topics:
            set_group_enabled(path, chat, False)
        suffix = "当前已没有主题，每日研究已暂停。" if not topics else "其他成员的主题仍会保留。"
        return {"action": "off", "reply": f"已关闭你的 #daily 每日任务。{suffix}"}

    if command_key in PAUSE_WORDS:
        if role not in {"owner", "allowlisted"}:
            return {
                "action": "pause_refused",
                "reply": "只有已配对的所有者或允许名单成员可以暂停整个群的每日研究。",
            }
        set_group_enabled(path, chat, False)
        return {
            "action": "pause",
            "reply": "已暂停这个群的每日研究；已有兴趣仍保留。发送“新兴趣 #daily”可重新启用。",
        }

    topic = re.sub(r"^(?:topic|主题|主題)\s*[:：]?\s*", "", command, flags=re.IGNORECASE).strip()
    topic = " ".join(topic.split())[:1000]
    if not topic:
        return {
            "action": "invalid_topic",
            "reply": "请把 #daily 放在研究兴趣末尾，例如：event camera reconstruction #daily",
        }
    interests, added = set_preference_with_status(path, chat, sender_hash, topic)
    set_group_enabled(path, chat, True)
    if added:
        reply = (
            f"已加入你的每日研究兴趣：{topic}\n"
            f"你目前累计 {len(interests)} 项兴趣；你的兴趣每天合并为一个任务，不同成员分别排队。"
        )
    else:
        reply = (
            f"这项每日研究兴趣已经记录：{topic}\n"
            f"未重复创建任务；你目前累计 {len(interests)} 项兴趣。"
        )
    return {
        "action": "topic_added" if added else "topic_existing",
        "reply": reply,
        "topic": topic,
        "interests": interests,
        "topic_added": added,
    }


def parse_daily_directive(text: str) -> str | None:
    value = str(text or "")
    prefix = DAILY_PREFIX.match(value)
    if prefix:
        return prefix.group(1).strip()
    suffix = DAILY_SUFFIX.match(value)
    if suffix:
        return suffix.group(1).strip()
    return None


def parse_inspiration_directive(text: str) -> str | None:
    value = str(text or "")
    prefix = INTEREST_PREFIX.match(value)
    if prefix:
        return prefix.group(1).strip()
    suffix = INTEREST_SUFFIX.match(value)
    if suffix:
        return suffix.group(1).strip()
    return None


def split_inspiration_topics(value: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in re.split(r"[\n;；]+", str(value or "")):
        topic = " ".join(item.split()).strip(" ,，、")[:300]
        key = topic.casefold()
        if topic and key not in seen:
            seen.add(key)
            result.append(topic)
    return result[:12]


def group_inspiration_settings(path: Path, chat: str) -> dict[str, Any]:
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT topics_json, enabled, interval_seconds, last_enqueued_at, updated_at "
            "FROM inspiration_settings WHERE chat = ?",
            (chat,),
        ).fetchone()
    if not row:
        return {
            "chat": chat,
            "topics": [],
            "enabled": False,
            "interval_seconds": int(os.environ.get("WECOM_INSPIRATION_INTERVAL_SECONDS", "10800")),
            "last_enqueued_at": "",
            "updated_at": "",
        }
    try:
        raw_topics = json.loads(str(row[0] or "[]"))
    except json.JSONDecodeError:
        raw_topics = []
    topics = split_inspiration_topics("\n".join(str(item) for item in raw_topics if item)) if isinstance(raw_topics, list) else []
    try:
        interval = max(900, min(604800, int(row[2] or 10800)))
    except (TypeError, ValueError):
        interval = 10800
    return {
        "chat": chat,
        "topics": topics,
        "enabled": bool(row[1]),
        "interval_seconds": interval,
        "last_enqueued_at": str(row[3] or ""),
        "updated_at": str(row[4] or ""),
    }


def update_group_inspiration(
    path: Path,
    chat: str,
    topics: list[str] | None = None,
    *,
    mode: str = "add",
    enabled: bool = True,
    interval_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    init_daily_state(path)
    current = group_inspiration_settings(path, chat)
    incoming = split_inspiration_topics("\n".join(topics or []))
    if mode == "replace":
        merged = incoming
    elif mode == "remove":
        remove_keys = {item.casefold() for item in incoming}
        merged = [item for item in current["topics"] if item.casefold() not in remove_keys]
    else:
        merged = split_inspiration_topics("\n".join([*current["topics"], *incoming]))
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    try:
        interval = max(
            900,
            min(
                604800,
                int(interval_seconds or os.environ.get("WECOM_INSPIRATION_INTERVAL_SECONDS", "10800")),
            ),
        )
    except (TypeError, ValueError):
        interval = 10800
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO inspiration_settings(chat, topics_json, enabled, interval_seconds, last_enqueued_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chat) DO UPDATE SET topics_json=excluded.topics_json, enabled=excluded.enabled, "
            "interval_seconds=excluded.interval_seconds, updated_at=excluded.updated_at",
            (chat, json.dumps(merged, ensure_ascii=False), 1 if enabled else 0, interval, "", stamp),
        )
    return group_inspiration_settings(path, chat)


def handle_inspiration_interest_directive_result(
    path: Path,
    event: dict[str, Any],
    chat: str,
) -> dict[str, Any] | None:
    command = parse_inspiration_directive(str(event.get("text") or ""))
    if command is None:
        return None
    if str(event.get("chat_type") or "") != "group":
        return {"action": "wrong_chat_type", "reply": "#interest 只用于群聊。"}
    register_group(path, event, chat)
    value = command.strip()
    if not value or value.casefold() in STATUS_WORDS:
        settings = group_inspiration_settings(path, chat)
        topics = "；".join(settings["topics"]) or "暂未设置，将依据群内近期讨论和 #daily 兴趣生成。"
        state = "已开启" if settings["enabled"] else "已关闭"
        return {"action": "status", "reply": f"群组灵感提示：{state}；当前关注：{topics}"}
    if value.casefold() in OFF_WORDS or value.casefold() in PAUSE_WORDS:
        settings = update_group_inspiration(path, chat, [], mode="add", enabled=False)
        return {"action": "off", "reply": f"已暂停群组灵感提示；已保留关注：{'；'.join(settings['topics']) or '无'}"}
    if value.casefold() in ON_WORDS:
        settings = update_group_inspiration(path, chat, [], mode="add", enabled=True)
        return {"action": "on", "reply": f"已恢复群组灵感提示，每 {settings['interval_seconds'] // 3600} 小时最多一条。"}
    mode = "add"
    lowered = value.casefold()
    for prefix, candidate in (("replace", "replace"), ("update", "replace"), ("替换", "replace"), ("更新", "replace"), ("add", "add"), ("增加", "add"), ("加入", "add"), ("remove", "remove"), ("移除", "remove")):
        if lowered.startswith(prefix.casefold() + " ") or value.startswith(prefix + " "):
            mode = candidate
            value = value[len(prefix):].strip(" ：:，,;")
            break
    topics = split_inspiration_topics(value)
    if not topics:
        return {"action": "invalid", "reply": "请发送：#interest 研究兴趣；也可用 #interest replace 新兴趣。"}
    settings = update_group_inspiration(path, chat, topics, mode=mode, enabled=True)
    return {
        "action": "updated",
        "topics": settings["topics"],
        "reply": f"已更新群组灵感关注：{'；'.join(settings['topics'])}。群组安静满三小时后，我会基于群内完整上下文发送一条启发点。",
    }


def set_preference(path: Path, chat: str, sender_hash: str, topic: str) -> list[str]:
    interests, _added = set_preference_with_status(path, chat, sender_hash, topic)
    return interests


def set_preference_with_status(
    path: Path,
    chat: str,
    sender_hash: str,
    topic: str,
) -> tuple[list[str], bool]:
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT topic, topics_json FROM daily_preferences WHERE chat = ? AND sender_hash = ?",
            (chat, sender_hash),
        ).fetchone()
        interests = preference_interests(row[0], row[1]) if row else []
        normalized = " ".join(str(topic or "").split())[:1000]
        added = bool(normalized) and normalized.casefold() not in {
            item.casefold() for item in interests
        }
        if added:
            interests.append(normalized)
        conn.execute(
            """
            INSERT INTO daily_preferences(chat, sender_hash, topic, topics_json, enabled, updated_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(chat, sender_hash) DO UPDATE SET
                topic = excluded.topic,
                topics_json = excluded.topics_json,
                enabled = 1,
                updated_at = excluded.updated_at
            """,
            (
                chat,
                sender_hash,
                normalized,
                json.dumps(interests, ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
    return interests, added


def preference_interests(topic: Any, topics_json: Any) -> list[str]:
    values: list[str] = []
    try:
        parsed = json.loads(str(topics_json or "[]"))
    except json.JSONDecodeError:
        parsed = []
    if isinstance(parsed, list):
        values.extend(str(item or "").strip() for item in parsed)
    fallback = str(topic or "").strip()
    if fallback and not values:
        values.append(fallback)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split())[:1000]
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def disable_sender_preference(path: Path, chat: str, sender_hash: str) -> None:
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE daily_preferences SET enabled = 0, updated_at = ? WHERE chat = ? AND sender_hash = ?",
            (datetime.now().isoformat(timespec="seconds"), chat, sender_hash),
        )


def set_group_enabled(path: Path, chat: str, enabled: bool) -> None:
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE daily_chats SET enabled = ? WHERE chat = ?", (1 if enabled else 0, chat))


def active_topics(path: Path, chat: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for job in active_daily_jobs(path, chat):
        for value in job["topics"]:
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
    return result


def active_daily_jobs(path: Path, chat: str) -> list[dict[str, Any]]:
    """Return one stable scheduled job per member preference row."""
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT sender_hash, topic, topics_json FROM daily_preferences "
            "WHERE chat = ? AND enabled = 1 ORDER BY updated_at, sender_hash",
            (chat,),
        ).fetchall()
    jobs: list[dict[str, Any]] = []
    for sender_hash, topic, topics_json in rows:
        topics = preference_interests(topic, topics_json)
        if not topics:
            continue
        jobs.append(
            {
                "job_key": short_hash(f"{chat}:{sender_hash}"),
                "member_key": short_hash(sender_hash),
                "topics": topics,
            }
        )
    return jobs


def daily_status(path: Path) -> dict[str, Any]:
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT chat, enabled, first_seen_at, last_seen_at FROM daily_chats ORDER BY last_seen_at DESC"
        ).fetchall()
    chats: list[dict[str, Any]] = []
    for chat, enabled, first_seen, last_seen in rows:
        jobs = active_daily_jobs(path, chat)
        chats.append(
            {
                "chat": chat,
                "enabled": bool(enabled),
                "topics": [topic for job in jobs for topic in job["topics"]],
                "jobs": jobs,
                "job_count": len(jobs),
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
            }
        )
    return {"ok": True, "chat_count": len(chats), "enabled_count": sum(item["enabled"] for item in chats), "chats": chats}


def run_due_cycle(
    *,
    state_db: Path = DEFAULT_STATE_DB,
    history_db: Path = DEFAULT_STATE_DB,
    queue: Path = DEFAULT_QUEUE,
    now: datetime | None = None,
    force: bool = False,
    append_func: Callable[[Path, dict[str, Any]], bool] | None = None,
    send_func: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    init_daily_state(state_db)
    timezone = configured_timezone()
    current = now.astimezone(timezone) if now and now.tzinfo else (now.replace(tzinfo=timezone) if now else datetime.now(timezone))
    report_time = parse_clock(os.environ.get("WECOM_DAILY_RESEARCH_TIME", "06:00"))
    prompt_time = parse_clock(os.environ.get("WECOM_DAILY_TOPIC_PROMPT_TIME", "06:00"))
    date_key = current.date().isoformat()
    actions: list[dict[str, Any]] = []
    append = append_func or append_task_once
    with sqlite3.connect(state_db) as conn:
        chats = conn.execute(
            "SELECT chat, account_id, chat_id, chat_type, transport_channel FROM daily_chats WHERE enabled = 1 ORDER BY chat"
        ).fetchall()

    for chat, account_id, chat_id, chat_type, transport_channel in chats:
        jobs = active_daily_jobs(state_db, chat)
        if jobs:
            if not force and current.time().replace(tzinfo=None) < report_time:
                continue
            # Preserve the old one-report-per-group ledger for the day on which
            # member-scoped scheduling is first deployed. New dates use one
            # run key per member job.
            if daily_run_exists(state_db, chat, date_key, "report"):
                continue
            context = recent_group_context(history_db, chat, limit=20)
            for sequence_index, job in enumerate(jobs, start=1):
                run_kind = f"report:{job['job_key']}"
                if daily_run_exists(state_db, chat, date_key, run_kind):
                    continue
                task = build_daily_research_task(
                    chat=chat,
                    account_id=account_id,
                    chat_id=chat_id,
                    chat_type=chat_type,
                    transport_channel=transport_channel,
                    topics=job["topics"],
                    context=context,
                    report_date=date_key,
                    queue=queue,
                    now=current,
                    daily_job_key=job["job_key"],
                    daily_member_key=job["member_key"],
                    member_memory=member_context(
                        knowledge_db_for_history(history_db),
                        chat,
                        job["member_key"],
                        limit=16,
                    ),
                    sequence_index=sequence_index,
                    sequence_total=len(jobs),
                )
                appended = append(queue, task)
                record_daily_run(
                    state_db,
                    chat,
                    date_key,
                    run_kind,
                    "queued" if appended else "already_queued",
                    task["id"],
                )
                actions.append(
                    {
                        "kind": "report",
                        "chat": chat,
                        "task_id": task["id"],
                        "job_key": job["job_key"],
                        "sequence_index": sequence_index,
                        "sequence_total": len(jobs),
                        "queued": appended,
                    }
                )
            continue

        if not force and current.time().replace(tzinfo=None) < prompt_time:
            continue
        if daily_run_exists(state_db, chat, date_key, "topic_prompt"):
            continue
        task_id = f"wecom-daily-topic-{date_key}-{short_hash(chat)}"
        message = "今天想让 LabAgent 跟踪什么研究主题？请发送：你的研究兴趣 #daily"
        if send_func is None:
            result = send_topic_prompt(
                chat_id,
                message,
                task_id,
                transport_channel=transport_channel,
            )
        else:
            result = send_func(chat_id, message, task_id)
        if result.get("ok"):
            record_daily_run(state_db, chat, date_key, "topic_prompt", "sent", task_id)
        actions.append({"kind": "topic_prompt", "chat": chat, "task_id": task_id, "sent": bool(result.get("ok")), "error": result.get("error", "")})

    return {
        "ok": True,
        "date": date_key,
        "timezone": str(timezone),
        "checked_chats": len(chats),
        "actions": actions,
    }


def run_scheduler_cycle(
    *,
    state_db: Path = DEFAULT_STATE_DB,
    history_db: Path = DEFAULT_STATE_DB,
    queue: Path = DEFAULT_QUEUE,
    now: datetime | None = None,
    force: bool = False,
    include_inspiration: bool = True,
    append_func: Callable[[Path, dict[str, Any]], bool] | None = None,
    send_func: Callable[[str, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    daily = run_due_cycle(
        state_db=state_db,
        history_db=history_db,
        queue=queue,
        now=now,
        force=force,
        append_func=append_func,
        send_func=send_func,
    )
    if include_inspiration:
        inspiration = run_inspiration_cycle(
            state_db=state_db,
            history_db=history_db,
            queue=queue,
            now=now,
            force=force,
            append_func=append_func,
        )
    else:
        inspiration = {
            "ok": True,
            "status": "quiet_hours",
            "checked": 0,
            "actions": [],
            "busy_chats": [],
        }
    return {
        **daily,
        "actions": [*(daily.get("actions") or []), *(inspiration.get("actions") or [])],
        "inspiration": inspiration,
    }


def parse_task_datetime(value: str, timezone: ZoneInfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)


def last_group_human_activity(path: Path, chat: str, timezone: ZoneInfo) -> datetime | None:
    if not path.is_file():
        return None
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT created_at FROM messages WHERE chat = ? AND direction = 'inbound' "
                "ORDER BY id DESC LIMIT 1",
                (chat,),
            ).fetchone()
    except sqlite3.Error:
        return None
    return parse_task_datetime(str(row[0] or ""), timezone) if row else None


def active_inspiration_task(queue: Path, chat: str) -> bool:
    if not queue.is_file():
        return False
    try:
        rows = queue.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in rows:
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            continue
        source = task.get("source") if isinstance(task.get("source"), dict) else {}
        if str(task.get("chat") or "") != chat:
            continue
        if str(source.get("local_type") or "") != "scheduled_group_inspiration":
            continue
        if str(task.get("status") or "pending") not in INSPIRATION_FINAL_STATUSES:
            return True
    return False


def active_chat_work_task(queue: Path, chat: str) -> bool:
    """Return whether normal work is active for this exact group.

    Scheduled inspiration is opportunistic. It must not compete with a live
    question, report, artifact delivery, confirmation, or long-running task.
    Failed/finished work does not block the next quiet-period attempt.
    """
    if not queue.is_file():
        return False
    try:
        rows = queue.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in rows:
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(task.get("chat") or "") != chat:
            continue
        source = task.get("source") if isinstance(task.get("source"), dict) else {}
        if str(source.get("local_type") or "") == "scheduled_group_inspiration":
            continue
        if str(task.get("status") or "pending") in CHAT_BUSY_STATUSES:
            return True
    return False


def previous_inspiration_outputs(queue: Path, chat: str, *, limit: int = 5) -> list[str]:
    if not queue.is_file():
        return []
    outputs: list[str] = []
    try:
        rows = queue.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in rows:
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            continue
        source = task.get("source") if isinstance(task.get("source"), dict) else {}
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        if str(task.get("chat") or "") != chat or str(source.get("local_type") or "") != "scheduled_group_inspiration":
            continue
        text = str(result.get("message") or "").strip()
        if text:
            outputs.append(text[:900])
    return outputs[-limit:]


def previous_group_research_outputs(queue: Path, chat: str, *, limit: int = 6) -> list[str]:
    """Return bounded prior research results as leads for the next inspiration turn."""
    if not queue.is_file():
        return []
    outputs: list[str] = []
    try:
        rows = queue.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in rows:
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            continue
        source = task.get("source") if isinstance(task.get("source"), dict) else {}
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        if str(task.get("chat") or "") != chat:
            continue
        if str(source.get("local_type") or "") not in {"scheduled_daily_research", "immediate_daily_research"}:
            continue
        text = str(result.get("message") or "").strip()
        if text:
            outputs.append(text[:1400])
    return outputs[-limit:]


def build_group_inspiration_task(
    *,
    chat: str,
    account_id: str,
    chat_id: str,
    chat_type: str,
    transport_channel: str,
    topics: list[str],
    context: list[dict[str, Any]],
    previous: list[str],
    prior_research: list[str],
    now: datetime,
    queue: Path,
    interval_seconds: int,
    source_suffix: str = "",
) -> dict[str, Any]:
    topic_text = "；".join(topics) or "未指定；从群内长期讨论、问题、研究兴趣和近期方向中发现连接"
    context_text = "\n".join(
        f"- {item.get('direction', 'inbound')}: {str(item.get('content') or '')[:900]}"
        for item in context[-60:]
    ) or "- 群内还没有足够的历史讨论。"
    previous_text = "\n".join(f"- {item}" for item in previous) or "- 暂无历史灵感提示。"
    research_text = "\n".join(f"- {item}" for item in prior_research) or "- 暂无历史研究结果。"
    slot = now.strftime("%Y%m%d%H%M")
    source_id = f"inspiration:{slot}:{short_hash(chat)}{':' + source_suffix if source_suffix else ''}"
    task_id = f"wecom-inspiration-{slot}-{short_hash(chat)}{('-' + short_hash(source_suffix) if source_suffix else '')}"
    request_text = f"""Create one concise, genuinely useful inspiration point for this WeCom group after a quiet period.

Group steering interests:
{topic_text}

Recent and accumulated public group context (use all relevant threads, not only the last line):
{context_text}

Previous inspiration points; avoid repeating them:
{previous_text}

Prior group research results and paper leads:
{research_text}

Requirements:
- Respond as a thoughtful human collaborator, not a template or status report.
- Find one meaningful connection, question, experiment, design direction, writing angle, or research opportunity that could inspire this group.
- Explore adjacent topics when they illuminate the group's direction, but explain the connection instead of drifting into a generic news list.
- Base it on the group context and interests. When a paper, report, or source has already appeared, inspect its substantive content when available: identify the actual result, method or evidence, limitation, and an unresolved question. Do not merely repeat its title or abstract.
- If a current factual claim is needed, verify it with reliable sources and include at most two compact links; do not invent citations.
- Keep it concise enough for a group message, but include why it matters and one possible next step.
- Clearly separate a sourced fact from your own proposed idea.
- Do not create a PDF, image, or other artifact unless the group has explicitly requested one.
- Do not publish publicly, spend money, change credentials, or take irreversible actions.
""".strip()
    task = {
        "id": task_id,
        "chat": chat,
        "request": request_text,
        "original_request": request_text,
        "route_plan": "Use the persistent LabCanvas worker to synthesize one non-repetitive group inspiration point.",
        "status": "pending",
        "created_at": now.isoformat(timespec="seconds"),
        "agent_backend": os.environ.get("WECOM_AGENT_BACKEND", "codex"),
        "agent_backend_config": {
            "agent_fallbacks": {
                "enabled": True,
                "quota_fallback_model": "gpt-5.6-sol",
                "quota_fallback_reasoning_effort": "low",
                "fallback_to_aginti": True,
                "fallback_on_timeout": True,
            }
        },
        "agent_bridge_mode": True,
        "route": {"chat": chat, "transport": "wecom", "transport_channel": transport_channel, "account_id": account_id},
        "route_decision": {
            "route_kind": "research_or_summary",
            "worker_needed": True,
            "public_publish_allowed": False,
            "transport": "wecom",
            "transport_channel": transport_channel,
            "scheduled_group_inspiration": True,
            "no_fixed_deadline": True,
        },
        "instruction_contract": {
            "current_request_authoritative": True,
            "same_chat_source_isolation": True,
            "no_keyword_shrink": True,
            "use_agent_reasoning": "resume_exact_chat_route_and_worker_sessions",
            "irreversible_actions_require_current_message_intent": True,
        },
        "execution_contract": {
            "transport_role": "message_transport_only",
            "transport": transport_channel,
            "worker_entrypoint": "wechat_task_worker.run_task_orchestrator",
            "agent_entrypoint": "wechat_agent_backend.run_agent_session",
            "session": {"chat": chat, "role": "worker", "reuse": True},
            "required_artifacts": [],
            "queue_mode": "single_worker_sequential",
        },
        "source": {
            "transport": "wecom",
            "wecom_transport_channel": transport_channel,
            "chat": chat,
            "wecom_chat_id": chat_id,
            "wecom_chat_type": chat_type,
            "wecom_account_id": account_id,
            "server_id": source_id,
            "local_id": int(short_hash(source_id), 16),
            "local_type": "scheduled_group_inspiration",
            "create_time": int(now.timestamp()),
            "sender": "labcanvas-inspiration-scheduler",
            "sender_display": "LabAgent group inspiration",
            "kind": "scheduled_group_inspiration",
            "authorization_role": "system_safe_read_only",
        },
        "context": context[-60:],
        "group_inspiration": {
            "topics": topics,
            "interval_seconds": interval_seconds,
            "previous_outputs": previous,
            "prior_research_outputs": prior_research,
            "source_context_count": len(context),
        },
        "transport_preflight": {},
        "queue_path": str(queue),
    }
    ensure_task_routine_contract(task)
    if isinstance(task.get("routine"), dict):
        task["routine"]["default_effort"] = "medium"
    return task


def enqueue_initial_group_inspiration(
    *,
    state_db: Path,
    history_db: Path,
    queue: Path,
    event: dict[str, Any],
    chat: str,
    now: datetime | None = None,
    append_func: Callable[[Path, dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Queue one immediate inspiration after the group explicitly changes focus."""
    init_daily_state(state_db)
    settings = group_inspiration_settings(state_db, chat)
    if not settings["enabled"] or active_inspiration_task(queue, chat):
        return {"queued": False, "already_queued": True, "task_id": ""}
    timezone = configured_timezone()
    current = now.astimezone(timezone) if now and now.tzinfo else (now.replace(tzinfo=timezone) if now else datetime.now(timezone))
    topics = split_inspiration_topics("\n".join([*settings["topics"], *active_topics(state_db, chat)]))
    task = build_group_inspiration_task(
        chat=chat,
        account_id=str(event.get("account_id") or "default"),
        chat_id=str(event.get("chat_id") or ""),
        chat_type=str(event.get("chat_type") or "group"),
        transport_channel=str(event.get("transport_channel") or "wecom_bot_websocket"),
        topics=topics,
        context=recent_group_context(history_db, chat, limit=60),
        previous=previous_inspiration_outputs(queue, chat),
        prior_research=previous_group_research_outputs(queue, chat),
        now=current,
        queue=queue,
        interval_seconds=settings["interval_seconds"],
        source_suffix=f"immediate:{short_hash(event.get('message_id'))}",
    )
    appended = (append_func or append_task_once)(queue, task)
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            "UPDATE inspiration_settings SET last_enqueued_at = ? WHERE chat = ?",
            (current.isoformat(timespec="seconds"), chat),
        )
    return {"queued": appended, "already_queued": not appended, "task_id": task["id"]}


def run_inspiration_cycle(
    *,
    state_db: Path = DEFAULT_STATE_DB,
    history_db: Path = DEFAULT_STATE_DB,
    queue: Path = DEFAULT_QUEUE,
    now: datetime | None = None,
    force: bool = False,
    append_func: Callable[[Path, dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    init_daily_state(state_db)
    timezone = configured_timezone()
    current = now.astimezone(timezone) if now and now.tzinfo else (now.replace(tzinfo=timezone) if now else datetime.now(timezone))
    append = append_func or append_task_once
    actions: list[dict[str, Any]] = []
    busy_chats: list[str] = []
    with sqlite3.connect(state_db) as conn:
        settings_rows = conn.execute(
            "SELECT s.chat, c.account_id, c.chat_id, c.chat_type, c.transport_channel, s.topics_json, "
            "s.enabled, s.interval_seconds, s.last_enqueued_at, s.updated_at "
            "FROM inspiration_settings s JOIN daily_chats c ON c.chat = s.chat "
            "WHERE s.enabled = 1 ORDER BY s.chat"
        ).fetchall()
    for chat, account_id, chat_id, chat_type, transport_channel, raw_topics, enabled, interval, last_enqueued, updated_at in settings_rows:
        try:
            parsed_topics = json.loads(str(raw_topics or "[]"))
        except json.JSONDecodeError:
            parsed_topics = []
        topics = split_inspiration_topics("\n".join(str(item) for item in parsed_topics if item)) if isinstance(parsed_topics, list) else []
        topics = split_inspiration_topics("\n".join([*topics, *active_topics(state_db, chat)]))
        try:
            interval_seconds = max(900, min(604800, int(interval or 10800)))
        except (TypeError, ValueError):
            interval_seconds = 10800
        last_activity = last_group_human_activity(history_db, chat, timezone)
        baseline_values = [item for item in [last_activity, parse_task_datetime(updated_at, timezone), parse_task_datetime(last_enqueued, timezone)] if item]
        baseline = max(baseline_values) if baseline_values else current
        idle_seconds = max(0.0, (current - baseline).total_seconds())
        if not force and idle_seconds < interval_seconds:
            continue
        if active_inspiration_task(queue, chat):
            actions.append({"kind": "inspiration_waiting", "chat": chat, "reason": "previous_inspiration_still_active"})
            continue
        if active_chat_work_task(queue, chat):
            busy_chats.append(chat)
            continue
        context = recent_group_context(history_db, chat, limit=60)
        previous = previous_inspiration_outputs(queue, chat)
        prior_research = previous_group_research_outputs(queue, chat)
        task = build_group_inspiration_task(
            chat=chat,
            account_id=account_id,
            chat_id=chat_id,
            chat_type=chat_type,
            transport_channel=transport_channel,
            topics=topics,
            context=context,
            previous=previous,
            prior_research=prior_research,
            now=current,
            queue=queue,
            interval_seconds=interval_seconds,
        )
        appended = append(queue, task)
        stamp = current.isoformat(timespec="seconds")
        with sqlite3.connect(state_db) as conn:
            conn.execute(
                "UPDATE inspiration_settings SET last_enqueued_at = ? WHERE chat = ?",
                (stamp, chat),
            )
        actions.append({"kind": "inspiration", "chat": chat, "task_id": task["id"], "queued": appended, "idle_seconds": int(idle_seconds)})
    return {
        "ok": True,
        "checked": len(settings_rows),
        "actions": actions,
        "busy_chats": busy_chats,
    }


def build_daily_research_task(
    *,
    chat: str,
    account_id: str,
    chat_id: str,
    chat_type: str,
    topics: list[str],
    context: list[dict[str, Any]],
    report_date: str,
    queue: Path,
    now: datetime,
    transport_channel: str = "wecom_bot_websocket",
    daily_job_key: str = "",
    daily_member_key: str = "",
    member_memory: dict[str, Any] | None = None,
    sequence_index: int = 1,
    sequence_total: int = 1,
) -> dict[str, Any]:
    topic_text = "\n".join(f"- {topic}" for topic in topics)
    context_text = "\n".join(
        f"- {item.get('direction', 'inbound')}: {str(item.get('content') or '')[:800]}" for item in context[-12:]
    ) or "- No additional recent discussion."
    request_text = f"""Prepare the {report_date} daily research briefing for one exact member-scoped job in this WeCom research group.

Persistent #daily topics for this job only:
{topic_text}

Recent same-group discussion:
{context_text}

Requirements:
- Use current web and scholarly research, prioritizing recent primary papers, preprints, datasets, and official project repositories. Verify publication dates and distinguish peer-reviewed work from preprints.
- Keep this job separate from other members' daily topics. Same-group context is supporting evidence, not permission to merge another job into this report.
- Synthesize the topics with the group's recent questions instead of producing a generic news list.
- Return a substantial but readable Chinese group explanation, not a teaser or status line. Explain the important findings, essential terms, evidence, limitations, and concrete next research steps clearly enough that members can understand the result without opening the attachment; keep the PDF for the full analysis and references.
- If a topic includes science-fiction ideas, develop the strongest idea in useful detail: scientific anchor, premise, conflict, human stakes, originality, uncertainty, and a plausible story or research direction. Do not return only titles or disconnected knowledge points.
- Create a source-grounded Markdown report and a polished LaTeX source, then compile a restrained Nature-style research PDF with clear hierarchy, citations/DOIs/links, embedded fonts, and no clipped or overflowing content. Render and inspect the compiled pages. Keep Markdown, TeX, evidence papers, and render audits in the private task directory; return the polished PDF for group delivery unless the current request explicitly asks for source files.
- When an explanatory paper figure materially helps, create an editable source (SVG/TeX or a LabCanvas atomic figure manifest) plus a preview; do not use a generated bitmap as the sole source of truth.
- Download requested or directly relevant papers only from lawful open-access sources. Do not bypass paywalls or access controls.
- Never fabricate a paper, citation, benchmark, or claim. State evidence gaps plainly.
- This scheduled research task does not authorize public posting, payment, purchases, deletion, or credential changes.
""".strip()
    job_suffix = f":{daily_job_key}" if daily_job_key else ""
    source_id = f"daily:{report_date}:{short_hash(chat)}{job_suffix}"
    task_suffix = f"-{daily_job_key}" if daily_job_key else ""
    task = {
        "id": f"wecom-daily-{report_date.replace('-', '')}-{short_hash(chat)}{task_suffix}",
        "chat": chat,
        "request": request_text,
        "status": "pending",
        "created_at": now.isoformat(timespec="seconds"),
        "agent_backend": os.environ.get("WECOM_AGENT_BACKEND", "codex"),
        "agent_backend_config": {
            "agent_fallbacks": {
                "enabled": True,
                "quota_fallback_model": "gpt-5.6-sol",
                "quota_fallback_reasoning_effort": "low",
                "fallback_to_aginti": True,
                "fallback_on_timeout": False,
            }
        },
        "agent_bridge_mode": True,
        "route": {
            "chat": chat,
            "transport": "wecom",
            "transport_channel": transport_channel,
            "account_id": account_id,
        },
        "route_decision": {
            "route_kind": "research_or_summary",
            "worker_needed": True,
            "public_publish_allowed": False,
            "transport": "wecom",
            "transport_channel": transport_channel,
            "scheduled_daily_research": True,
            "no_fixed_deadline": True,
            "serialized_daily_job": True,
        },
        "instruction_contract": {
            "current_request_authoritative": True,
            "same_chat_interruptions_authoritative": True,
            "no_keyword_shrink": True,
            "use_agent_reasoning": "resume_exact_chat_route_and_worker_sessions",
            "same_chat_source_isolation": True,
            "irreversible_actions_require_current_message_intent": True,
        },
        "execution_contract": {
            "transport_role": "message_transport_only",
            "transport": transport_channel,
            "worker_entrypoint": "wechat_task_worker.run_task_orchestrator",
            "agent_entrypoint": "wechat_agent_backend.run_agent_session",
            "session": {"chat": chat, "role": "worker", "reuse": True},
            "required_artifacts": ["markdown_report", "compiled_pdf"],
            "queue_mode": "single_worker_sequential",
        },
        "source": {
            "transport": "wecom",
            "wecom_transport_channel": transport_channel,
            "chat": chat,
            "wecom_chat_id": chat_id,
            "wecom_chat_type": chat_type,
            "wecom_account_id": account_id,
            "server_id": source_id,
            "local_id": int(short_hash(source_id), 16),
            "local_type": "scheduled_daily_research",
            "create_time": int(now.timestamp()),
            "sender": "labcanvas-daily-scheduler",
            "sender_display": "LabAgent daily research",
            "member_key": daily_member_key,
            "kind": "scheduled_daily_research",
            "authorization_role": "system_safe_read_only",
        },
        "context": context[-20:],
        "member_memory": member_memory or {},
        "daily_research": {
            "report_date": report_date,
            "topics": topics,
            "timezone": str(now.tzinfo),
            "job_key": daily_job_key,
            "member_key": daily_member_key,
            "sequence_index": sequence_index,
            "sequence_total": sequence_total,
            "serialized": True,
        },
        "transport_preflight": {},
        "queue_path": str(queue),
    }
    daily_ttl_seconds = int(os.environ.get("WECOM_DAILY_TASK_TTL_SECONDS", "0"))
    if daily_ttl_seconds > 0:
        task["expires_at"] = (now + timedelta(seconds=daily_ttl_seconds)).isoformat(timespec="seconds")
    ensure_task_routine_contract(task)
    if isinstance(task.get("routine"), dict):
        task["routine"]["default_effort"] = "medium"
    return task


def enqueue_initial_daily_research(
    *,
    state_db: Path,
    history_db: Path,
    queue: Path,
    event: dict[str, Any],
    chat: str,
    topic: str,
    now: datetime | None = None,
    append_func: Callable[[Path, dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Queue one immediate first briefing for a newly registered interest."""
    init_daily_state(state_db)
    timezone = configured_timezone()
    current = (
        now.astimezone(timezone)
        if now and now.tzinfo
        else now.replace(tzinfo=timezone)
        if now
        else datetime.now(timezone)
    )
    normalized_topic = " ".join(str(topic or "").split())[:1000]
    if not normalized_topic:
        raise ValueError("initial daily research requires a topic")

    source_fingerprint = short_hash(
        json.dumps(
            {
                "message": str(event.get("message_id") or ""),
                "sender": short_hash(event.get("sender_userid")),
                "topic": normalized_topic.casefold(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    source_id = f"daily-initial:{source_fingerprint}"
    task_id = f"wecom-daily-initial-{source_fingerprint}"
    task = build_daily_research_task(
        chat=chat,
        account_id=str(event.get("account_id") or "default"),
        chat_id=str(event.get("chat_id") or ""),
        chat_type=str(event.get("chat_type") or "group"),
        transport_channel=str(event.get("transport_channel") or "wecom_bot_websocket"),
        topics=[normalized_topic],
        context=recent_group_context(history_db, chat, limit=20),
        report_date=current.date().isoformat(),
        queue=queue,
        now=current,
        daily_member_key=short_hash(event.get("sender_userid")),
        member_memory=member_context(
            knowledge_db_for_history(history_db),
            chat,
            short_hash(event.get("sender_userid")),
            limit=16,
        ),
    )
    _first_line, separator, remainder = task["request"].partition("\n")
    task["request"] = (
        "Prepare an immediate first research briefing for this newly registered "
        "#daily interest in the exact WeCom research group."
        + (separator + remainder if separator else "")
    )
    task["id"] = task_id
    task["route_decision"]["scheduled_daily_research"] = False
    task["route_decision"]["immediate_daily_research"] = True
    task["source"].update(
        {
            "server_id": source_id,
            "local_id": int(short_hash(source_id), 16),
            "local_type": "immediate_daily_research",
            "sender": "labcanvas-daily-registration",
            "sender_display": "LabAgent immediate daily research",
            "kind": "immediate_daily_research",
        }
    )
    task["daily_research"].update(
        {
            "initial_run": True,
            "trigger_topic": normalized_topic,
            "trigger_message_hash": short_hash(event.get("message_id")),
        }
    )
    ensure_task_routine_contract(task)
    appended = (append_func or append_task_once)(queue, task)
    return {
        "ok": True,
        "queued": appended,
        "already_queued": not appended,
        "task_id": task_id,
        "source_id": source_id,
    }


def append_task_once(queue: Path, task: dict[str, Any]) -> bool:
    queue.parent.mkdir(parents=True, exist_ok=True)
    lock_path = queue.with_suffix(queue.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        server_id = str(task.get("source", {}).get("server_id") or "")
        if queue.exists():
            for line in queue.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(existing.get("source", {}).get("server_id") or "") == server_id:
                    return False
        with queue.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return True


def recent_group_context(path: Path, chat: str, *, limit: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT direction, body, create_time FROM messages WHERE chat = ? ORDER BY id DESC LIMIT ?",
                (chat, limit),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [
        {"direction": direction, "content": body, "create_time": create_time or 0, "kind": "text"}
        for direction, body, create_time in reversed(rows)
    ]


def daily_run_exists(path: Path, chat: str, run_date: str, kind: str) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT 1 FROM daily_runs WHERE chat = ? AND run_date = ? AND kind = ?",
            (chat, run_date, kind),
        ).fetchone()
    return bool(row)


def record_daily_run(path: Path, chat: str, run_date: str, kind: str, status: str, task_id: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_runs(chat, run_date, kind, status, task_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chat, run_date, kind, status, task_id, datetime.now().isoformat(timespec="seconds")),
        )


def send_topic_prompt(
    chat_id: str,
    message: str,
    task_id: str,
    *,
    transport_channel: str = "wecom_bot_websocket",
) -> dict[str, Any]:
    if transport_channel == "wecom_cli":
        try:
            config = json.loads(DEFAULT_CLI_CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"WeCom CLI delivery config unavailable: {type(exc).__name__}"}
        api_url = f"http://127.0.0.1:{int(config.get('local_api_port') or 19579)}"
        token = str(config.get("local_api_token") or "").strip()
    elif transport_channel == "wecom_gui":
        try:
            config = json.loads(DEFAULT_GUI_CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"WeCom GUI delivery config unavailable: {type(exc).__name__}"}
        api_url = f"http://127.0.0.1:{int(config.get('local_api_port') or 19580)}"
        token = str(config.get("local_api_token") or "").strip()
    elif transport_channel == "wecom_bot_websocket":
        api_url = os.environ.get("WECOM_LOCAL_API_URL", DEFAULT_API_URL).rstrip("/")
        token = os.environ.get("WECOM_LOCAL_API_TOKEN", "").strip()
    else:
        return {"ok": False, "error": f"unsupported WeCom transport channel: {transport_channel}"}
    if not token:
        return {"ok": False, "error": "WECOM_LOCAL_API_TOKEN is not configured"}
    if not (api_url.startswith("http://127.0.0.1:") or api_url.startswith("http://localhost:")):
        return {"ok": False, "error": "non-local WeCom API URL refused"}
    body = json.dumps({"chat_id": chat_id, "task_id": task_id, "message": message, "files": []}).encode("utf-8")
    http_request = request.Request(
        api_url + "/v1/send",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    return payload if isinstance(payload, dict) else {"ok": False, "error": "invalid local API response"}


def configured_timezone() -> ZoneInfo:
    value = os.environ.get("WECOM_DAILY_TIMEZONE", "Asia/Hong_Kong")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def parse_clock(value: str):
    try:
        return datetime.strptime(str(value).strip(), "%H:%M").time()
    except ValueError:
        return datetime.strptime("06:00", "%H:%M").time()


def short_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def print_result(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if payload.get("actions"):
        for action in payload["actions"]:
            print(f"{action.get('kind')}: {action.get('chat')} task={action.get('task_id')}")
        return
    print(f"Daily research: {payload.get('enabled_count', 0)} enabled chat(s), no due action.")


if __name__ == "__main__":
    raise SystemExit(main())
