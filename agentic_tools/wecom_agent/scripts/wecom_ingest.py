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
from wecom_daily_research import (  # noqa: E402
    enqueue_initial_group_inspiration,
    enqueue_initial_daily_research,
    handle_inspiration_interest_directive_result,
    handle_daily_directive_result,
    mark_inline_topic_prompt,
    register_group,
    update_group_inspiration,
    set_group_enabled,
    set_preference,
)
from wecom_contract import labagent_welcome_message  # noqa: E402
from wecom_member_knowledge import (  # noqa: E402
    knowledge_db_for_history,
    member_context,
    normalize_memory_items,
    record_incoming_event,
    record_knowledge_items,
    task_source_member_key,
)


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
    if transport_channel in {"wecom_gui", "wecom_android"} and recent_equivalent_gui_inbound(
        history_db,
        chat,
        request,
    ):
        # OCR sender labels can vary between adjacent captures of the same
        # bubble. Exact same-chat text inside a short window is a transport
        # duplicate even when its derived sender fingerprint changed.
        record_history_message(history_db, event, chat, request, direction="inbound")
        mark_message_processed(history_db, str(event["message_id"]))
        return {
            "duplicate": True,
            "queued": False,
            "chat": chat,
            "reply": "",
            "ack": "",
            "suppressed": "recent_exact_wecom_gui_duplicate",
        }
    record_history_message(history_db, event, chat, request, direction="inbound")
    knowledge_db = knowledge_db_for_history(history_db)
    member_key = task_source_member_key(event)
    record_incoming_event(
        knowledge_db,
        event,
        chat,
        request,
        attachments=normalized_attachments(event),
    )
    first_group_event = register_group(history_db, event, chat)
    inspiration_result = handle_inspiration_interest_directive_result(history_db, event, chat)
    if inspiration_result is not None:
        if inspiration_result.get("action") in {"updated", "on"}:
            immediate = enqueue_initial_group_inspiration(
                state_db=history_db,
                history_db=history_db,
                queue=queue,
                event=event,
                chat=chat,
            )
            if immediate.get("queued"):
                inspiration_result["reply"] = (
                    str(inspiration_result.get("reply") or "").rstrip()
                    + "\n已立即安排一条基于当前群内上下文的灵感提示；以后群组安静满三小时再自动更新。"
                )
            elif immediate.get("already_queued"):
                inspiration_result["reply"] = (
                    str(inspiration_result.get("reply") or "").rstrip()
                    + "\n当前已有一条灵感任务在处理中，不重复创建。"
                )
        return complete_direct_reply(
            history_db,
            event,
            chat,
            inspiration_result.get("reply") or "已更新群组灵感设置。",
            action="wecom_inspiration_interest",
        )
    daily_result = handle_daily_directive_result(history_db, event, chat)
    if daily_result is not None:
        immediate: dict[str, Any] | None = None
        daily_reply = str(daily_result.get("reply") or "")
        if daily_result.get("action") == "topic_added":
            record_knowledge_items(
                knowledge_db,
                member_key=member_key,
                chat=chat,
                items=[
                    {
                        "kind": "interest",
                        "title": "Daily research interest",
                        "content": str(daily_result.get("topic") or ""),
                        "tags": ["daily", "research"],
                    }
                ],
                source_type="daily_preference",
                source_id=short_hash(event.get("message_id")),
            )
            immediate = enqueue_initial_daily_research(
                state_db=history_db,
                history_db=history_db,
                queue=queue,
                event=event,
                chat=chat,
                topic=str(daily_result.get("topic") or ""),
            )
            if immediate.get("queued"):
                daily_reply += "\n首次研究已立即进入队列，完成后会把摘要和报告发回本群。"
            else:
                daily_reply += "\n首次研究任务已在队列中，未重复创建。"
        result = complete_direct_reply(
            history_db,
            event,
            chat,
            daily_reply,
            action="wecom_daily_command",
        )
        if immediate is not None:
            result.update(
                {
                    "queued": True,
                    "task_id": immediate["task_id"],
                    "immediate_daily_research": True,
                    "new_queue_entry": bool(immediate.get("queued")),
                }
            )
        return result
    context = recent_history(history_db, chat, limit=12)
    memory_context = member_context(knowledge_db, chat, member_key, limit=12)
    route = (
        route_event(event, request, context, memory_context=memory_context)
        if route_with_agent
        else fallback_route(event, request)
    )
    record_knowledge_items(
        knowledge_db,
        member_key=member_key,
        chat=chat,
        items=normalize_memory_items(route.get("memory_items")),
        source_type="route_memory",
        source_id=short_hash(event.get("message_id")),
    )
    daily_topic = str(route.get("daily_topic") or "").strip()[:1000]
    if daily_topic and str(event.get("chat_type") or "") == "group":
        set_preference(history_db, chat, short_hash(event.get("sender_userid")), daily_topic)
        set_group_enabled(history_db, chat, True)
    inspiration_interest = str(route.get("inspiration_interest") or "").strip()[:1000]
    inspiration_mode = str(route.get("inspiration_interest_mode") or "none").strip().casefold()
    inspiration_note = ""
    if inspiration_mode != "none" and str(event.get("chat_type") or "") == "group":
        if inspiration_mode == "disable":
            settings = update_group_inspiration(history_db, chat, [], enabled=False)
            inspiration_note = "已暂停群组灵感提示。"
        elif inspiration_interest:
            settings = update_group_inspiration(
                history_db,
                chat,
                [inspiration_interest],
                mode=inspiration_mode,
                enabled=True,
            )
            inspiration_note = f"已更新群组灵感关注：{'；'.join(settings['topics'])}。"

    if not bool(route.get("worker_needed")) and str(route.get("response") or "").strip():
        response = str(route["response"])
        if daily_topic:
            response = f"已设置每日研究主题：{daily_topic}\n\n{response}"
        if inspiration_note:
            response = f"{inspiration_note}\n\n{response}"
        if first_group_event:
            response = f"{response.rstrip()}\n\n{labagent_welcome_message()}"
            mark_inline_topic_prompt(history_db, chat)
        return complete_direct_reply(history_db, event, chat, response)

    task = build_task(
        event,
        chat,
        request,
        context,
        route,
        queue,
        member_memory=memory_context,
    )
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
    if daily_topic:
        ack = f"已设置每日研究主题：{daily_topic}\n{ack}"
    if inspiration_note:
        ack = f"{inspiration_note}\n{ack}"
    if first_group_event:
        ack = "当前请求已进入 LabCanvas 队列。\n\n" + labagent_welcome_message()
        if daily_topic:
            ack = f"已设置每日研究主题：{daily_topic}\n\n{ack}"
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
    if value not in {"wecom_bot_websocket", "wecom_cli", "wecom_gui", "wecom_android"}:
        raise ValueError(f"unsupported WeCom transport channel: {value}")
    return value


def event_reply_mentions(event: dict[str, Any]) -> list[str]:
    if str(event.get("chat_type") or "") != "group":
        return []
    display = " ".join(
        str(event.get("sender_mention") or event.get("sender_display") or "").split()
    )
    if not display or display in {"unknown", "所有人", "MaLabAgent", "LabAgent"}:
        return []
    return [display]


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


def route_event(
    event: dict[str, Any],
    request: str,
    context: list[dict[str, Any]],
    *,
    memory_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = f"""You route one WeCom message into the persistent LabCanvas agent runtime.
WeCom is message transport only. Decide whether a quick conversational response is sufficient or the durable worker must execute tools/research/files.

Return one strict JSON object and no prose:
{{
  "worker_needed": true,
  "route_kind": "other_worker",
  "response": "natural direct reply only when worker_needed is false",
  "task": "complete worker instruction when worker_needed is true",
  "ack": "short natural acknowledgement for queued work",
  "daily_topic": "persistent topic only when the current message explicitly requests recurring daily research, otherwise empty",
  "inspiration_interest": "group-scoped inspiration interest only when the current message explicitly sets or updates it, otherwise empty",
  "inspiration_interest_mode": "none|add|replace|remove|disable",
  "memory_items": [{{"kind": "idea|insight|intuition|interest|hypothesis|decision|preference|question|note", "title": "short title", "content": "durable user-authored knowledge", "tags": ["optional"]}}],
  "public_publish_allowed": false
}}

Allowed route_kind values:
{', '.join(sorted(ROUTE_KINDS))}

Rules:
- LabAgent focuses on normal research, literature, research proposals, lawful paper downloads, Markdown/TeX/PDF reports, editable paper figures, scientific drawing, CAD/PCB/Blender design, and related artifact work.
- Attachments, links requiring reading, research, file operations, figures, CAD/PCB/Blender, generation, editing, or multi-step design work need the worker.
- Simple greetings, ordinary questions answerable without tools, and short conversational follow-ups may be answered directly.
- Decide naturally whether to reply from the full recent conversation. Always answer direct questions, requests, mentions, and useful follow-ups. It is valid to stay silent when people are talking to each other and an AI reply would interrupt or add no value. Never emit a mechanical acknowledgement merely to prove receipt.
- Reply to several consecutive messages from the same sender as one coherent turn using all of them; do not emit one mechanical response per fragment.
- Do not claim an attachment was read in the acknowledgement.
- Soft-filter dangerous or clearly out-of-scope requests with a concise natural refusal or a safer research/design alternative. Do not mechanically refuse ordinary scientific work.
- LabAgent does not perform video publication or other public posting. Set public_publish_allowed to false.
- Do not authorize payment, purchase, deletion, credential changes, device takeover, bypassing access controls, or another irreversible action from group context.
- Preserve existing explicit approval gates for any sensitive action that remains within scope.
- Preserve the whole current request; do not shrink it to one keyword.
- The task field is advisory planning only. Never replace the user's wording with a new factual assumption, a mandatory clarification, or a refusal to investigate an uncertain name. The worker receives the exact message and owns evidence gathering.
- When a scientific name or identifier may contain OCR, speech, capitalization, or character ambiguity, route it to research. Tell the worker to search plausible candidates and authoritative sources before asking the user to clarify.
- Set daily_topic only for an explicit recurring/daily research request. Extract a concise durable topic rather than the whole command.
- Set inspiration_interest only when the current message explicitly asks the group to set, update, add, remove, or disable its three-hour inspiration focus. Do not infer it from an ordinary research question.
- Put only durable user-authored knowledge in memory_items: ideas, insights, intuitions, hypotheses, decisions, preferences, research interests, and questions worth retaining. Do not store greetings, acknowledgements, secrets, credentials, or content merely quoted from an attachment as the user's belief.
- Use the private member memory only as same-user context. Never mention another member's records or infer that two member keys are the same person.
- Make the direct response natural and concise, not a fixed template.

Sender authorization role: {event.get('authorization_role') or 'unknown'}
Current message:
{request[:9000]}

Recent same-chat context:
{json.dumps(context[-8:], ensure_ascii=False)[:9000]}

Private same-member knowledge context:
{json.dumps(memory_context or {}, ensure_ascii=False)[:7000]}
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
    daily_topic = " ".join(str(payload.get("daily_topic") or "").split())[:1000]
    inspiration_interest = " ".join(str(payload.get("inspiration_interest") or "").split())[:1000]
    inspiration_interest_mode = str(payload.get("inspiration_interest_mode") or "none").strip().casefold()
    if inspiration_interest_mode not in {"none", "add", "replace", "remove", "disable"}:
        inspiration_interest_mode = "none"
    return {
        "worker_needed": worker_needed,
        "route_kind": route_kind,
        "response": response,
        "task": task_text,
        "ack": sanitize_chat_response(payload.get("ack")),
        "daily_topic": daily_topic,
        "inspiration_interest": inspiration_interest,
        "inspiration_interest_mode": inspiration_interest_mode,
        "memory_items": normalize_memory_items(payload.get("memory_items")),
        "public_publish_allowed": False,
    }


def fallback_route(event: dict[str, Any], request: str) -> dict[str, Any]:
    return {
        "worker_needed": True,
        "route_kind": "file_intake" if normalized_attachments(event) else "other_worker",
        "response": "",
        "task": request,
        "ack": "任务已进入 LabCanvas 队列，完成后会把结果发回这个会话。",
        "daily_topic": "",
        "inspiration_interest": "",
        "inspiration_interest_mode": "none",
        "memory_items": [],
        "public_publish_allowed": False,
    }


def build_task(
    event: dict[str, Any],
    chat: str,
    request: str,
    context: list[dict[str, Any]],
    route: dict[str, Any],
    queue: Path,
    *,
    member_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now()
    message_id = str(event["message_id"])
    transport_channel = event_transport_channel(event)
    task = {
        "id": f"wecom-{now.strftime('%Y%m%d%H%M%S')}-{short_hash(message_id)}",
        "chat": chat,
        # The exact transport message remains authoritative. Router prose is
        # useful as an advisory plan, but must never silently replace intent.
        "request": request.strip(),
        "original_request": request.strip(),
        "route_plan": str(route.get("task") or "").strip(),
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
            "daily_topic": str(route.get("daily_topic") or ""),
            "inspiration_interest": str(route.get("inspiration_interest") or ""),
            "inspiration_interest_mode": str(route.get("inspiration_interest_mode") or "none"),
            "worker_plan": str(route.get("task") or "").strip(),
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
            "router_plan_is_advisory": True,
            "resolve_uncertain_entities_with_evidence_before_clarifying": True,
            "research_requests_use_live_web_search": True,
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
            "sender_display": str(event.get("sender_display") or event["sender_userid"]),
            "wecom_sender_display": str(event.get("sender_display") or event["sender_userid"]),
            "reply_mentions": event_reply_mentions(event),
            "member_key": task_source_member_key(event),
            "sender_identity_confidence": str(
                event.get("sender_identity_confidence") or "transport_userid"
            ),
            "kind": str(event.get("msgtype") or "text"),
            "authorization_role": str(event.get("authorization_role") or "unknown"),
            "irreversible_actions_allowed": bool(event.get("irreversible_actions_allowed")),
        },
        "context": context[-12:],
        "member_memory": member_memory or {},
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
                sender_display TEXT,
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
        if "sender_display" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN sender_display TEXT")
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


def recent_equivalent_gui_inbound(
    path: Path,
    chat: str,
    body: str,
    *,
    window_seconds: int = 90,
) -> bool:
    normalized = str(body or "").strip()
    if not normalized:
        return False
    cutoff = (datetime.now() - timedelta(seconds=max(1, window_seconds))).isoformat(
        timespec="seconds"
    )
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE chat = ? AND direction = 'inbound' "
            "AND body = ? AND created_at >= ? ORDER BY id DESC LIMIT 1",
            (chat, normalized, cutoff),
        ).fetchone()
    return bool(row)


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
            INSERT OR IGNORE INTO messages(
                message_id, chat, direction, sender, sender_display, body, create_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.get("message_id") or ""),
                chat,
                direction,
                str(event.get("sender_userid") or ""),
                (
                    str(event.get("sender_display") or event.get("sender_userid") or "")
                    if direction == "inbound"
                    else "LabAgent"
                ),
                body,
                int(event.get("create_time") or 0),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def recent_history(path: Path, chat: str, *, limit: int) -> list[dict[str, Any]]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT id, direction, sender, sender_display, body, create_time "
            "FROM messages WHERE chat = ? ORDER BY id DESC LIMIT ?",
            (chat, limit),
        ).fetchall()
    result = []
    for row_id, direction, sender, sender_display, body, create_time in reversed(rows):
        result.append(
            {
                "local_id": row_id,
                "server_id": f"history:{row_id}",
                "sender": sender or "",
                "sender_display": sender_display or sender or "",
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
