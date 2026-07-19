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


DEFAULT_QUEUE = PRIVATE / "wecom_task_queue.jsonl"
DEFAULT_STATE_DB = PRIVATE / "wecom_messages.local.sqlite"
DEFAULT_API_URL = "http://127.0.0.1:19578"
DEFAULT_CLI_CONFIG = PRIVATE / "wecom_cli_bridge.local.json"
DEFAULT_GUI_CONFIG = PRIVATE / "wecom_gui_bridge.local.json"
DAILY_PREFIX = re.compile(r"^\s*#daily(?:\s+|$)(.*)$", re.IGNORECASE | re.DOTALL)
DAILY_SUFFIX = re.compile(r"^(.*?)\s*#daily\s*$", re.IGNORECASE | re.DOTALL)
STATUS_WORDS = {"status", "show", "list", "状态", "狀態", "查看", "列表"}
OFF_WORDS = {"off", "clear", "remove", "取消", "清除", "关闭", "關閉"}
PAUSE_WORDS = {"pause", "disable", "stop", "暂停", "暫停", "停用"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run one due-check cycle.")
    add_common_arguments(run)
    run.add_argument("--force", action="store_true", help="Ignore the configured clock, while retaining daily deduplication.")

    loop = subparsers.add_parser("loop", help="Run the durable daily scheduler loop.")
    add_common_arguments(loop)
    loop.add_argument("--poll-seconds", type=float, default=float(os.environ.get("WECOM_DAILY_POLL_SECONDS", "30")))

    status = subparsers.add_parser("status", help="Show enrolled chats and daily topics without raw chat IDs.")
    status.add_argument("--state-db", type=Path, default=Path(os.environ.get("WECOM_DAILY_STATE_DB", DEFAULT_STATE_DB)))
    status.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "status":
        payload = daily_status(args.state_db)
        print_result(payload, args.json)
        return 0

    if args.command == "run":
        payload = run_due_cycle(
            state_db=args.state_db,
            history_db=args.history_db,
            queue=args.queue,
            force=args.force,
        )
        print_result(payload, args.json)
        return 0 if payload.get("ok") else 1

    interval = max(5.0, min(3600.0, float(args.poll_seconds)))
    while True:
        try:
            payload = run_due_cycle(state_db=args.state_db, history_db=args.history_db, queue=args.queue)
            if payload.get("actions"):
                print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
        except Exception as exc:  # Keep the scheduler alive across transient API/DB failures.
            print(
                json.dumps({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}, ensure_ascii=False),
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
            f"你目前累计 {len(interests)} 项兴趣；每天只生成一个合并任务。"
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
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT topic, topics_json FROM daily_preferences "
            "WHERE chat = ? AND enabled = 1 ORDER BY updated_at, sender_hash",
            (chat,),
        ).fetchall()
    result: list[str] = []
    seen: set[str] = set()
    for topic, topics_json in rows:
        for value in preference_interests(topic, topics_json):
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
    return result


def daily_status(path: Path) -> dict[str, Any]:
    init_daily_state(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT chat, enabled, first_seen_at, last_seen_at FROM daily_chats ORDER BY last_seen_at DESC"
        ).fetchall()
    chats = [
        {
            "chat": chat,
            "enabled": bool(enabled),
            "topics": active_topics(path, chat),
            "first_seen_at": first_seen,
            "last_seen_at": last_seen,
        }
        for chat, enabled, first_seen, last_seen in rows
    ]
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
    report_time = parse_clock(os.environ.get("WECOM_DAILY_RESEARCH_TIME", "09:00"))
    prompt_time = parse_clock(os.environ.get("WECOM_DAILY_TOPIC_PROMPT_TIME", "08:45"))
    date_key = current.date().isoformat()
    actions: list[dict[str, Any]] = []
    append = append_func or append_task_once
    with sqlite3.connect(state_db) as conn:
        chats = conn.execute(
            "SELECT chat, account_id, chat_id, chat_type, transport_channel FROM daily_chats WHERE enabled = 1 ORDER BY chat"
        ).fetchall()

    for chat, account_id, chat_id, chat_type, transport_channel in chats:
        topics = active_topics(state_db, chat)
        if topics:
            if not force and current.time().replace(tzinfo=None) < report_time:
                continue
            if daily_run_exists(state_db, chat, date_key, "report"):
                continue
            context = recent_group_context(history_db, chat, limit=20)
            task = build_daily_research_task(
                chat=chat,
                account_id=account_id,
                chat_id=chat_id,
                chat_type=chat_type,
                transport_channel=transport_channel,
                topics=topics,
                context=context,
                report_date=date_key,
                queue=queue,
                now=current,
            )
            appended = append(queue, task)
            record_daily_run(state_db, chat, date_key, "report", "queued" if appended else "already_queued", task["id"])
            actions.append({"kind": "report", "chat": chat, "task_id": task["id"], "queued": appended})
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
) -> dict[str, Any]:
    topic_text = "\n".join(f"- {topic}" for topic in topics)
    context_text = "\n".join(
        f"- {item.get('direction', 'inbound')}: {str(item.get('content') or '')[:800]}" for item in context[-12:]
    ) or "- No additional recent discussion."
    request_text = f"""Prepare the {report_date} daily research briefing for this exact WeCom research group.

Persistent #daily topics:
{topic_text}

Recent same-group discussion:
{context_text}

Requirements:
- Use current web and scholarly research, prioritizing recent primary papers, preprints, datasets, and official project repositories. Verify publication dates and distinguish peer-reviewed work from preprints.
- Synthesize the topics with the group's recent questions instead of producing a generic news list.
- Return a concise Chinese chat digest with the most important findings, why they matter, limitations, and concrete next research steps.
- Create a source-grounded Markdown report and compile a readable PDF through LaTeX as a restrained Nature-style research paper with citations/DOIs/links. Include both files in the result so the transport sends them to this group.
- When an explanatory paper figure materially helps, create an editable source (SVG/TeX or a LabCanvas atomic figure manifest) plus a preview; do not use a generated bitmap as the sole source of truth.
- Download requested or directly relevant papers only from lawful open-access sources. Do not bypass paywalls or access controls.
- Never fabricate a paper, citation, benchmark, or claim. State evidence gaps plainly.
- This scheduled research task does not authorize public posting, payment, purchases, deletion, or credential changes.
""".strip()
    source_id = f"daily:{report_date}:{short_hash(chat)}"
    task = {
        "id": f"wecom-daily-{report_date.replace('-', '')}-{short_hash(chat)}",
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
            "kind": "scheduled_daily_research",
            "authorization_role": "system_safe_read_only",
        },
        "context": context[-20:],
        "daily_research": {"report_date": report_date, "topics": topics, "timezone": str(now.tzinfo)},
        "transport_preflight": {},
        "queue_path": str(queue),
    }
    daily_ttl_seconds = int(os.environ.get("WECOM_DAILY_TASK_TTL_SECONDS", "0"))
    if daily_ttl_seconds > 0:
        task["expires_at"] = (now + timedelta(seconds=daily_ttl_seconds)).isoformat(timespec="seconds")
    ensure_task_routine_contract(task)
    if isinstance(task.get("routine"), dict):
        task["routine"]["default_effort"] = "high"
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
        return datetime.strptime("09:00", "%H:%M").time()


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
