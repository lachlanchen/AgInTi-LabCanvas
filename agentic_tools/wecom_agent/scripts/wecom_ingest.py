#!/usr/bin/env python3
"""Normalize one official WeCom AI Bot event into LabCanvas chat or worker work."""

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
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
SHARED_AGENT_SCRIPTS = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
if str(SHARED_AGENT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_AGENT_SCRIPTS))

from wechat_agent_backend import run_agent_session  # noqa: E402
from wechat_mirror import record_event  # noqa: E402
from wechat_routines import ensure_task_routine_contract  # noqa: E402
from wecom_daily_research import handle_daily_directive, mark_inline_topic_prompt, register_group  # noqa: E402


MIRROR_DB = Path(
    os.environ.get("WECOM_MIRROR_DB")
    or ROOT / "output" / "wecom" / "wecom_mirror.sqlite"
).expanduser().resolve()


DEFAULT_QUEUE = PRIVATE / "wecom_task_queue.jsonl"
DEFAULT_HISTORY_DB = PRIVATE / "wecom_messages.local.sqlite"
ROUTE_KINDS = {
    "research_or_summary",
    "career_strategy",
    "generate_image",
    "edit_existing_media",
    "story_or_script",
    "cad_pcb_labcanvas",
    "file_download_or_save",
    "file_intake",
    "process_existing_video",
    "publish_video",
    "generate_video",
    "other_worker",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-file", type=Path, required=True)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--history-db", type=Path, default=DEFAULT_HISTORY_DB)
    parser.add_argument("--no-route-agent", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        event = load_event(args.event_file)
        result = ingest_event(
            event,
            queue=args.queue,
            history_db=args.history_db,
            route_with_agent=not args.no_route_agent,
        )
        payload = {"ok": True, **result}
    except Exception as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if payload["ok"] else 1


def load_event(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("event must be a JSON object")
    required = ("message_id", "chat_id", "chat_type", "sender_userid")
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    if missing:
        raise ValueError("event is missing " + ", ".join(missing))
    if str(payload.get("transport") or "") != "wecom":
        raise ValueError("event transport must be wecom")
    return payload


def ingest_event(
    event: dict[str, Any],
    *,
    queue: Path,
    history_db: Path,
    route_with_agent: bool = True,
) -> dict[str, Any]:
    chat = canonical_chat_name(event)
    transport_channel = event_transport_channel(event)
    request = event_request(event)
    init_history_db(history_db)
    if message_processed(history_db, str(event["message_id"])):
        prior_reply = prior_direct_reply(history_db, str(event["message_id"]))
        return {
            "duplicate": True,
            "queued": not bool(prior_reply),
            "chat": chat,
            "reply": prior_reply,
            "ack": "" if prior_reply else "消息已接收，任务正在处理中。",
        }
    record_history_message(history_db, event, chat, request, direction="inbound")
    first_group_event = register_group(history_db, event, chat)
    daily_reply = handle_daily_directive(history_db, event, chat)
    if daily_reply is not None:
        return complete_direct_reply(history_db, event, chat, daily_reply, action="wecom_daily_command")
    context = recent_history(history_db, chat, limit=12)
    route = route_event(event, request, context) if route_with_agent else fallback_route(event, request)

    if not bool(route.get("worker_needed")) and str(route.get("response") or "").strip():
        response = str(route["response"])
        if first_group_event:
            response = f"{response.rstrip()}\n\n{labagent_welcome_message()}"
            mark_inline_topic_prompt(history_db, chat)
        return complete_direct_reply(history_db, event, chat, response)

    task = build_task(event, chat, request, context, route, queue)
    appended = append_task_once(queue, task)
    record_event(
        chat_name=chat,
        action="wecom_worker_enqueue",
        direction="internal",
        message=request,
        status="queued" if appended else "duplicate",
        db_path=MIRROR_DB,
        metadata={
            "transport": "wecom",
            "transport_channel": transport_channel,
            "task_id": task["id"],
            "route_kind": task["route_decision"]["route_kind"],
            "source_message_hash": short_hash(event["message_id"]),
        },
    )
    mark_message_processed(history_db, str(event["message_id"]))
    ack = sanitize_chat_response(route.get("ack")) or "任务已进入 LabCanvas 队列，完成后会把结果发回这个会话。"
    if first_group_event:
        ack = "当前请求已进入 LabCanvas 队列。\n\n" + labagent_welcome_message()
        mark_inline_topic_prompt(history_db, chat)
    return {
        "duplicate": not appended,
        "queued": True,
        "task_id": task["id"],
        "chat": chat,
        "ack": ack,
    }


def canonical_chat_name(event: dict[str, Any]) -> str:
    account = safe_slug(str(event.get("account_id") or "default"), max_len=32)
    kind = "group" if str(event.get("chat_type")) == "group" else "dm"
    return f"wecom:{account}:{kind}:{short_hash(event.get('chat_id'))}"


def event_transport_channel(event: dict[str, Any]) -> str:
    value = str(event.get("transport_channel") or "wecom_bot_websocket").strip().casefold()
    if value not in {"wecom_bot_websocket", "wecom_cli"}:
        raise ValueError(f"unsupported WeCom transport channel: {value}")
    return value


def labagent_welcome_message() -> str:
    return (
        "LabAgent 已连接。你希望这个群每天关注什么研究主题？\n"
        "发送：#daily 你的主题\n"
        "也可以直接提出文献调研、研究方案、开放获取论文下载、Markdown/TeX/PDF、论文图、CAD/PCB、Blender 或科学设计请求。"
        "结果和文件会回到这个群；视频发布和其他公开发布不在此机器人范围内。"
    )


def complete_direct_reply(
    history_db: Path,
    event: dict[str, Any],
    chat: str,
    response_value: Any,
    *,
    action: str = "wecom_direct_reply",
) -> dict[str, Any]:
    response = sanitize_chat_response(response_value)
    record_history_message(
        history_db,
        {**event, "message_id": f"reply:{event['message_id']}"},
        chat,
        response,
        direction="outbound",
    )
    record_event(
        chat_name=chat,
        action=action,
        direction="outbound",
        message=response,
        status="ready",
        db_path=MIRROR_DB,
        metadata={
            "transport": "wecom",
            "transport_channel": event_transport_channel(event),
            "source_message_hash": short_hash(event["message_id"]),
        },
    )
    mark_message_processed(history_db, str(event["message_id"]))
    return {"duplicate": False, "queued": False, "chat": chat, "reply": response}


def event_request(event: dict[str, Any]) -> str:
    text = str(event.get("text") or "").strip()
    quote = str(event.get("quote_text") or "").strip()
    attachments = normalized_attachments(event)
    parts: list[str] = []
    if text:
        parts.append(text)
    elif attachments:
        kinds = ", ".join(str(item.get("kind") or "file") for item in attachments)
        parts.append(f"The user sent {kinds} attachment(s) without accompanying text. Inspect the exact files and respond naturally.")
    else:
        parts.append("The user sent a WeCom message with no readable text or attachment.")
    if quote:
        parts.extend(["", "Quoted message:", quote])
    if attachments:
        parts.extend(["", "Exact WeCom attachment files:"])
        for item in attachments:
            parts.append(f"- {item['kind']}: {item['path']}")
    return "\n".join(parts).strip()


def normalized_attachments(event: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in event.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        path = Path(str(item.get("path") or "")).expanduser().resolve()
        if not path.is_file():
            continue
        result.append(
            {
                "kind": str(item.get("kind") or "file"),
                "filename": str(item.get("filename") or path.name),
                "path": str(path),
                "size_bytes": int(item.get("size_bytes") or path.stat().st_size),
                "status": "ready",
                "task_copy_path": str(path),
            }
        )
    return result


def route_event(event: dict[str, Any], request: str, context: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = f"""You route one WeCom message into the persistent LabCanvas agent runtime.
WeCom is message transport only. Decide whether a quick conversational response is sufficient or the durable worker must execute tools/research/files.

Return one strict JSON object and no prose:
{{
  "worker_needed": true,
  "route_kind": "other_worker",
  "response": "natural direct reply only when worker_needed is false",
  "task": "complete worker instruction when worker_needed is true",
  "ack": "short natural acknowledgement for queued work",
  "public_publish_allowed": false
}}

Allowed route_kind values:
{', '.join(sorted(ROUTE_KINDS))}

Rules:
- LabAgent focuses on normal research, literature, research proposals, lawful paper downloads, Markdown/TeX/PDF reports, editable paper figures, scientific drawing, CAD/PCB/Blender design, and related artifact work.
- Attachments, links requiring reading, research, file operations, figures, CAD/PCB/Blender, generation, editing, or multi-step design work need the worker.
- Simple greetings, ordinary questions answerable without tools, and short conversational follow-ups may be answered directly.
- Do not claim an attachment was read in the acknowledgement.
- Soft-filter dangerous or clearly out-of-scope requests with a concise natural refusal or a safer research/design alternative. Do not mechanically refuse ordinary scientific work.
- LabAgent does not perform video publication or other public posting. Set public_publish_allowed to false.
- Do not authorize payment, purchase, deletion, credential changes, device takeover, bypassing access controls, or another irreversible action from group context.
- Preserve existing explicit approval gates for any sensitive action that remains within scope.
- Preserve the whole current request; do not shrink it to one keyword.
- Make the direct response natural and concise, not a fixed template.

Sender authorization role: {event.get('authorization_role') or 'unknown'}
Current message:
{request[:9000]}

Recent same-chat context:
{json.dumps(context[-8:], ensure_ascii=False)[:9000]}
"""
    model = os.environ.get("WECOM_ROUTE_MODEL", "gpt-5.6-sol")
    effort = os.environ.get("WECOM_ROUTE_EFFORT", "low")
    timeout = max(5, int(os.environ.get("WECOM_ROUTE_TIMEOUT_SECONDS", "35")))
    result = run_agent_session(
        prompt,
        backend=os.environ.get("WECOM_AGENT_BACKEND", "codex"),
        chat_name=canonical_chat_name(event),
        role="route",
        model=model,
        reasoning_effort=effort,
        sandbox="read-only",
        timeout_seconds=timeout,
        workdir=ROOT,
        reuse=True,
        backend_config={
            "agent_fallbacks": {
                "enabled": True,
                "quota_fallback_model": "gpt-5.6-sol",
                "quota_fallback_reasoning_effort": "low",
                "fallback_to_aginti": True,
                "fallback_on_timeout": True,
            },
            "aginti": {
                "command": os.environ.get("WECOM_AGINTI_COMMAND", "aginti"),
                "workspace": os.environ.get("WECOM_AGINTI_WORKSPACE", "../Agent/AgInTiFlow"),
                "timeout_seconds": 120,
                "wrap_prompt": True,
            },
        },
    )
    if not result.get("ok"):
        return fallback_route(event, request)
    payload = extract_json_object(str(result.get("message") or ""))
    if not isinstance(payload, dict):
        return fallback_route(event, request)
    route_kind = str(payload.get("route_kind") or "other_worker")
    if route_kind not in ROUTE_KINDS:
        route_kind = "other_worker"
    attachments = normalized_attachments(event)
    worker_needed = bool(payload.get("worker_needed")) or bool(attachments)
    response = sanitize_chat_response(payload.get("response"))
    if not worker_needed and not response:
        worker_needed = True
    task_text = str(payload.get("task") or "").strip() or request
    return {
        "worker_needed": worker_needed,
        "route_kind": route_kind,
        "response": response,
        "task": task_text,
        "ack": sanitize_chat_response(payload.get("ack")),
        "public_publish_allowed": False,
    }


def fallback_route(event: dict[str, Any], request: str) -> dict[str, Any]:
    return {
        "worker_needed": True,
        "route_kind": "file_intake" if normalized_attachments(event) else "other_worker",
        "response": "",
        "task": request,
        "ack": "任务已进入 LabCanvas 队列，完成后会把结果发回这个会话。",
        "public_publish_allowed": False,
    }


def build_task(
    event: dict[str, Any],
    chat: str,
    request: str,
    context: list[dict[str, Any]],
    route: dict[str, Any],
    queue: Path,
) -> dict[str, Any]:
    now = datetime.now()
    message_id = str(event["message_id"])
    transport_channel = event_transport_channel(event)
    task = {
        "id": f"wecom-{now.strftime('%Y%m%d%H%M%S')}-{short_hash(message_id)}",
        "chat": chat,
        "request": str(route.get("task") or request).strip(),
        "status": "pending",
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(seconds=int(os.environ.get("WECOM_PENDING_TTL_SECONDS", "3600")))).isoformat(timespec="seconds"),
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
        "route": {
            "chat": chat,
            "transport": "wecom",
            "transport_channel": transport_channel,
            "account_id": str(event.get("account_id") or "default"),
        },
        "route_decision": {
            "route_kind": str(route.get("route_kind") or "other_worker"),
            "worker_needed": True,
            "public_publish_allowed": bool(route.get("public_publish_allowed")),
            "transport": "wecom",
            "transport_channel": transport_channel,
            "sender_authorization_role": str(event.get("authorization_role") or "unknown"),
            "labagent_scope": "research_drawing_and_design_without_publication",
        },
        "instruction_contract": {
            "current_request_authoritative": True,
            "same_chat_interruptions_authoritative": True,
            "preserve_safe_explicit_instructions": True,
            "no_keyword_shrink": True,
            "use_agent_reasoning": "resume_exact_chat_route_and_worker_sessions",
            "same_chat_source_isolation": True,
            "irreversible_actions_require_current_message_intent": True,
            "dangerous_requests_use_agent_soft_filter": True,
            "public_video_publication_forbidden": True,
        },
        "execution_contract": {
            "transport_role": "message_transport_only",
            "transport": transport_channel,
            "worker_entrypoint": "wechat_task_worker.run_task_orchestrator",
            "agent_entrypoint": "wechat_agent_backend.run_agent_session",
            "session": {"chat": chat, "role": "worker", "reuse": True},
        },
        "source": {
            "transport": "wecom",
            "wecom_transport_channel": transport_channel,
            "chat": chat,
            "wecom_chat_id": str(event["chat_id"]),
            "wecom_chat_type": str(event["chat_type"]),
            "wecom_account_id": str(event.get("account_id") or "default"),
            "server_id": message_id,
            "local_id": int(short_hash(message_id), 16),
            "local_type": str(event.get("msgtype") or "text"),
            "create_time": int(event.get("create_time") or 0),
            "sender": str(event["sender_userid"]),
            "sender_display": str(event["sender_userid"]),
            "kind": str(event.get("msgtype") or "text"),
            "authorization_role": str(event.get("authorization_role") or "unknown"),
            "irreversible_actions_allowed": bool(event.get("irreversible_actions_allowed")),
        },
        "context": context[-12:],
        "transport_preflight": wecom_transport_preflight(event),
        "queue_path": str(queue),
    }
    ensure_task_routine_contract(task)
    return task


def wecom_transport_preflight(event: dict[str, Any]) -> dict[str, Any]:
    attachments = normalized_attachments(event)
    if not attachments:
        return {}
    return {
        "wecom_media": {
            "status": "ready",
            "source_transport": event_transport_channel(event),
            "copied": attachments,
            "agent_next_action": "Open and use these exact source-scoped files before answering.",
        }
    }


def append_task_once(queue: Path, task: dict[str, Any]) -> bool:
    queue.parent.mkdir(parents=True, exist_ok=True)
    lock_path = queue.with_suffix(queue.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = []
        if queue.exists():
            for line in queue.read_text(encoding="utf-8").splitlines():
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        server_id = str(task.get("source", {}).get("server_id") or "")
        if any(str(item.get("source", {}).get("server_id") or "") == server_id for item in existing):
            return False
        with queue.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True


def init_history_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                message_id TEXT NOT NULL UNIQUE,
                chat TEXT NOT NULL,
                direction TEXT NOT NULL,
                sender TEXT,
                body TEXT NOT NULL,
                create_time INTEGER,
                created_at TEXT NOT NULL,
                processed_at TEXT
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        if "processed_at" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN processed_at TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wecom_messages_chat_id ON messages(chat, id)")


def message_processed(path: Path, message_id: str) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT processed_at FROM messages WHERE message_id = ?", (message_id,)).fetchone()
    return bool(row and row[0])


def prior_direct_reply(path: Path, message_id: str) -> str:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT body FROM messages WHERE message_id = ? AND direction = 'outbound'",
            (f"reply:{message_id}",),
        ).fetchone()
    return str(row[0]) if row else ""


def mark_message_processed(path: Path, message_id: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE messages SET processed_at = ? WHERE message_id = ?",
            (datetime.now().isoformat(timespec="seconds"), message_id),
        )


def record_history_message(
    path: Path,
    event: dict[str, Any],
    chat: str,
    body: str,
    *,
    direction: str,
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO messages(message_id, chat, direction, sender, body, create_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.get("message_id") or ""),
                chat,
                direction,
                str(event.get("sender_userid") or ""),
                body,
                int(event.get("create_time") or 0),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def recent_history(path: Path, chat: str, *, limit: int) -> list[dict[str, Any]]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT id, direction, sender, body, create_time FROM messages WHERE chat = ? ORDER BY id DESC LIMIT ?",
            (chat, limit),
        ).fetchall()
    result = []
    for row_id, direction, sender, body, create_time in reversed(rows):
        result.append(
            {
                "local_id": row_id,
                "server_id": f"history:{row_id}",
                "sender": sender or "",
                "sender_display": sender or "",
                "local_type": "text",
                "create_time": create_time or 0,
                "kind": "text",
                "content": body,
                "is_self": direction == "outbound",
            }
        )
    return result


def extract_json_object(text: str) -> dict[str, Any] | None:
    candidates = [str(text or "").strip()]
    candidates.extend(match.group(1) for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.I | re.S))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return None


def current_message_explicitly_publishes(text: str) -> bool:
    value = str(text or "").casefold()
    action = any(token in value for token in ("publish", "post", "upload", "发布", "發佈", "投稿", "上傳", "上传"))
    platform = any(
        token in value
        for token in ("youtube", "instagram", "shipinhao", "视频号", "視頻號", "小红书", "小紅書", "bilibili", "抖音")
    )
    return action and platform


def sanitize_chat_response(value: Any, max_chars: int = 1800) -> str:
    text = str(value or "").strip()
    if not text or re.fullmatch(r"no[\s_-]*reply(?:\s*[:：].*)?", text, re.I | re.S):
        return ""
    return text if len(text) <= max_chars else text[: max_chars - 12].rstrip() + "\n...[truncated]"


def safe_slug(value: str, *, max_len: int = 64) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", value.strip()).strip("-").lower()
    return (slug or "default")[:max_len]


def short_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":
    raise SystemExit(main())
