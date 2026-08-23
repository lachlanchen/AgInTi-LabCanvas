#!/usr/bin/env python3
"""Daily private career, writing, and money strategy agent for WeChat."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid

from file_lock import fcntl_compat as fcntl
from wechat_agent_backend import (
    agent_context_model,
    run_agent_session,
    select_agent_backend,
)
from wechat_chat_profiles import preferred_chat_title, profile_aliases, profile_for_chat
from wechat_message_policy import (
    attachment_transport_identity,
    file_identities_match,
    file_transport_identity,
)
from wechat_task_worker import (
    ensure_markdown_pdf_companions,
    send_file,
    send_message,
)
from wechat_history_rag import (
    build_history_context,
    estimate_tokens,
    lexical_terms,
    resolve_memory_budget,
)


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
OUTPUT = ROOT / "output" / "wechat_strategy"
DEFAULT_MEMORY_DB = PRIVATE / "wechat_memory.sqlite"
DEFAULT_SEND_TARGETS = PRIVATE / "wechat_send_targets.local.json"
GUI_SEND_PRIORITY = Path(os.environ.get("WECHAT_GUI_SEND_PRIORITY_PATH", str(PRIVATE / "wechat_gui_send_priority.json")))
DEFAULT_CHATS = [
    *profile_aliases("writing_money"),
    *profile_aliases("personal_dm"),
    *profile_aliases("shares"),
    *profile_aliases("my_devices"),
]
DEFAULT_ORGANIZER_CHAT = preferred_chat_title("writing_money")
ORGANIZER_STATE = PRIVATE / "output" / "career_daily" / "organizer-delivery.json"
SCHEDULER_STATE = PRIVATE / "output" / "career_daily" / "scheduler-state.json"
ORGANIZER_DELIVERY_VERSION = "v3"
DELIVERY_RETRY_BASE_SECONDS = int(os.environ.get("WECHAT_DAILY_DELIVERY_RETRY_SECONDS", "1800"))
DELIVERY_RETRY_MAX_SECONDS = int(os.environ.get("WECHAT_DAILY_DELIVERY_RETRY_MAX_SECONDS", "14400"))
SCHEDULER_OVERDUE_GRACE_SECONDS = int(
    os.environ.get("WECHAT_DAILY_OVERDUE_GRACE_SECONDS", "5400")
)
CAREER_HISTORY_QUERY = """
writing author story language research career work talent strength opportunity
income money wealth freedom happiness product service open source publishing
reader audience customer investment company project experiment evidence shipped
写作 作者 故事 外语 研究 职业 工作 天赋 优势 机会 收入 挣钱 财富 自由
幸福 产品 服务 开源 发布 读者 用户 投资 公司 项目 实验 证据 完成 长期 目标
"""
ORGANIZER_HISTORY_QUERY = """
memo todo reminder calendar grocery item resource project idea writing language
career money question decision status completed open next action
备忘 待办 提醒 日历 采购 物品 资源 项目 想法 写作 外语 职业 挣钱
问题 决定 状态 已完成 未完成 下一步
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["run", "loop", "organize", "retry", "catch-up"],
        nargs="?",
        default="run",
    )
    parser.add_argument("--chat", action="append", default=[], help="Memory chat to include. Repeatable.")
    parser.add_argument("--send-chat", default="lachlanchan", help="WeChat chat/DM to receive the daily note.")
    parser.add_argument("--send", action="store_true", help="Send the concise result and shareable report to WeChat.")
    parser.add_argument("--attach-report", action="store_true", help="Attach the shareable Markdown report when sending.")
    parser.add_argument(
        "--organize-report",
        action="store_true",
        help="Also create the daily recent-items PDF for the organizer chat.",
    )
    parser.add_argument("--organize-chat", default=DEFAULT_ORGANIZER_CHAT)
    parser.add_argument("--force-organize", action="store_true")
    parser.add_argument("--date", default="", help="Artifact-only retry date in YYYY-MM-DD form.")
    parser.add_argument("--memory-db", type=Path, default=DEFAULT_MEMORY_DB)
    parser.add_argument("--send-targets", type=Path, default=DEFAULT_SEND_TARGETS)
    parser.add_argument("--morning-time", default="08:30", help="Loop run time in HH:MM local time.")
    parser.add_argument("--loop-sleep", type=float, default=60.0)
    parser.add_argument("--model", default=os.environ.get("WECHAT_CAREER_AGENT_MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning-effort", default=os.environ.get("WECHAT_CAREER_AGENT_EFFORT", "medium"))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.environ.get("WECHAT_CAREER_AGENT_TIMEOUT", "900")))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.action == "loop":
        return loop_daily(args)
    if args.action == "retry":
        payload = retry_existing_career_delivery(
            args,
            args.date or datetime.now().strftime("%Y-%m-%d"),
            force=True,
        )
        if payload is None:
            payload = {"ok": False, "status": "missing_generated_report"}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(payload.get("status") or "done")
        return 0 if payload.get("ok") else 1
    if args.action == "catch-up":
        payload = run_catch_up(args)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(payload.get("status") or "done")
        return 0 if payload.get("ok") else 1
    payload = (
        run_organizer(args, force=bool(args.force_organize))
        if args.action == "organize"
        else run_daily(args)
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload.get("summary") or payload.get("status") or "done")
    return 0 if payload.get("ok") else 1


def loop_daily(args: argparse.Namespace) -> int:
    last_run_key = ""
    organizer_done_key = ""
    career_retry_at: datetime | None = None
    organizer_retry_at: datetime | None = None
    career_status = "waiting"
    organizer_status = "waiting"
    while True:
        now = datetime.now()
        run_at = scheduled_run_time(now, args.morning_time)
        run_key = run_at.strftime("%Y-%m-%d")
        due = now >= run_at
        career_complete = career_delivery_complete_for_date(
            run_key,
            require_send=bool(args.send),
        )
        organizer_complete = (
            not bool(getattr(args, "organize_report", False))
            or organizer_delivery_complete_for_date(
                run_key,
                str(getattr(args, "organize_chat", DEFAULT_ORGANIZER_CHAT)),
                require_send=bool(args.send),
            )
        )
        if career_complete:
            last_run_key = run_key
            career_status = "delivered" if args.send else "generated"
            career_retry_at = None
        if organizer_complete:
            organizer_done_key = run_key
            organizer_status = "delivered" if args.send else "generated"
            organizer_retry_at = None
        write_scheduler_heartbeat(
            args,
            now=now,
            run_at=run_at,
            phase="due" if due else "waiting",
            career_complete=career_complete,
            organizer_complete=organizer_complete,
            career_status=career_status,
            organizer_status=organizer_status,
            career_retry_at=career_retry_at,
            organizer_retry_at=organizer_retry_at,
        )
        if now >= run_at:
            if (
                last_run_key != run_key
                and (career_retry_at is None or now >= career_retry_at)
            ):
                write_scheduler_heartbeat(
                    args,
                    now=now,
                    run_at=run_at,
                    phase="career_running",
                    career_complete=False,
                    organizer_complete=organizer_complete,
                    career_status="running",
                    organizer_status=organizer_status,
                    career_retry_at=career_retry_at,
                    organizer_retry_at=organizer_retry_at,
                )
                payload = safe_daily_call(
                    lambda: run_with_daily_operation_lock(
                        "career",
                        lambda: run_career_for_date(args, run_key),
                    )
                )
                if payload.get("status") != "delivery_deferred":
                    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
                career_status = str(payload.get("status") or "failed")
                if payload.get("ok"):
                    last_run_key = run_key
                    career_retry_at = None
                else:
                    career_retry_at = payload_retry_at(payload, now)
            if (
                bool(getattr(args, "organize_report", False))
                and organizer_done_key != run_key
                and (organizer_retry_at is None or now >= organizer_retry_at)
            ):
                write_scheduler_heartbeat(
                    args,
                    now=datetime.now(),
                    run_at=run_at,
                    phase="organizer_running",
                    career_complete=last_run_key == run_key,
                    organizer_complete=False,
                    career_status=career_status,
                    organizer_status="running",
                    career_retry_at=career_retry_at,
                    organizer_retry_at=organizer_retry_at,
                )
                payload = safe_daily_call(
                    lambda: run_with_daily_operation_lock(
                        "organizer",
                        lambda: run_organizer(args),
                    )
                )
                if payload.get("status") != "delivery_deferred":
                    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
                organizer_status = str(payload.get("status") or "failed")
                if payload.get("ok"):
                    organizer_done_key = run_key
                    organizer_retry_at = None
                else:
                    organizer_retry_at = payload_retry_at(payload, now)
        current = datetime.now()
        career_complete = career_delivery_complete_for_date(
            run_key,
            require_send=bool(args.send),
        )
        organizer_complete = (
            not bool(getattr(args, "organize_report", False))
            or organizer_delivery_complete_for_date(
                run_key,
                str(getattr(args, "organize_chat", DEFAULT_ORGANIZER_CHAT)),
                require_send=bool(args.send),
            )
        )
        write_scheduler_heartbeat(
            args,
            now=current,
            run_at=run_at,
            phase="complete" if career_complete and organizer_complete else ("retry_wait" if due else "waiting"),
            career_complete=career_complete,
            organizer_complete=organizer_complete,
            career_status=career_status,
            organizer_status=organizer_status,
            career_retry_at=career_retry_at,
            organizer_retry_at=organizer_retry_at,
        )
        sleep_until = next_run_time(datetime.now(), args.morning_time)
        delay = min(max(5.0, (sleep_until - datetime.now()).total_seconds()), max(5.0, args.loop_sleep))
        time.sleep(delay)


def run_catch_up(args: argparse.Namespace) -> dict[str, Any]:
    """Run today's two daily outputs once without duplicating delivered work."""

    stamp = datetime.now().strftime("%Y-%m-%d")
    career = safe_daily_call(
        lambda: run_with_daily_operation_lock(
            "career",
            lambda: run_career_for_date(args, stamp, force_delivery=True),
        )
    )
    organizer: dict[str, Any] = {
        "ok": True,
        "status": "disabled",
    }
    if bool(getattr(args, "organize_report", False)):
        organizer = safe_daily_call(
            lambda: run_with_daily_operation_lock(
                "organizer",
                lambda: run_organizer(args, force_delivery=True),
            )
        )
    ok = bool(career.get("ok")) and bool(organizer.get("ok"))
    return {
        "ok": ok,
        "status": "done" if ok else "incomplete",
        "date": stamp,
        "career": career,
        "organizer": organizer,
    }


def run_career_for_date(
    args: argparse.Namespace,
    stamp: str,
    *,
    force_delivery: bool = False,
) -> dict[str, Any]:
    if career_delivery_complete_for_date(stamp, require_send=bool(args.send)):
        return {"ok": True, "status": "already_delivered", "date": stamp}
    payload = retry_existing_career_delivery(
        args,
        stamp,
        force=force_delivery,
    )
    return payload if payload is not None else run_daily(args)


def safe_daily_call(callback: Any) -> dict[str, Any]:
    try:
        payload = callback()
    except Exception as exc:  # noqa: BLE001 - keep the scheduler alive and retry later.
        return {
            "ok": False,
            "status": "scheduler_error",
            "error": f"{type(exc).__name__}: {exc}"[:600],
        }
    return payload if isinstance(payload, dict) else {
        "ok": False,
        "status": "invalid_result",
    }


def run_with_daily_operation_lock(name: str, callback: Any) -> dict[str, Any]:
    lock_path = (
        PRIVATE
        / "output"
        / "career_daily"
        / f"{re.sub(r'[^a-z0-9_-]+', '-', name.lower()).strip('-') or 'daily'}.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {
                "ok": False,
                "status": "already_running",
                "next_delivery_attempt_at": (
                    datetime.now() + timedelta(minutes=5)
                ).isoformat(timespec="seconds"),
            }
        try:
            return callback()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def payload_retry_at(payload: dict[str, Any], now: datetime) -> datetime:
    raw = str(payload.get("next_delivery_attempt_at") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return max(now + timedelta(seconds=60), parsed)
    return now + timedelta(seconds=max(300, DELIVERY_RETRY_BASE_SECONDS))


def organizer_delivery_complete_for_date(
    stamp: str,
    chat: str,
    *,
    require_send: bool,
) -> bool:
    state = read_json_file(organizer_state_path())
    pdf = OUTPUT / f"{stamp}-recent-items.zh.pdf"
    if not require_send:
        return bool(
            state.get("date") == stamp
            and state.get("chat") == chat
            and organizer_quality_accepted(state)
            and pdf.is_file()
            and pdf.stat().st_size > 0
        )
    return organizer_delivery_matches(state, stamp, chat, pdf)


def scheduler_state_path() -> Path:
    if PRIVATE == ROOT / "agentic_tools" / "wechat_gui_agent" / ".private":
        return SCHEDULER_STATE
    return PRIVATE / "output" / "career_daily" / "scheduler-state.json"


def write_scheduler_heartbeat(
    args: argparse.Namespace,
    *,
    now: datetime,
    run_at: datetime,
    phase: str,
    career_complete: bool,
    organizer_complete: bool,
    career_status: str,
    organizer_status: str,
    career_retry_at: datetime | None,
    organizer_retry_at: datetime | None,
) -> None:
    overdue_at = run_at + timedelta(seconds=max(300, SCHEDULER_OVERDUE_GRACE_SECONDS))
    organizer_required = bool(getattr(args, "organize_report", False))
    state = {
        "schema": "labcanvas.wechat.career_daily.scheduler.v1",
        "date": run_at.strftime("%Y-%m-%d"),
        "morning_time": str(getattr(args, "morning_time", "08:30")),
        "last_loop_at": now.astimezone().isoformat(timespec="seconds"),
        "phase": phase,
        "send_chat": str(getattr(args, "send_chat", "lachlanchan")),
        "organize_chat": str(getattr(args, "organize_chat", DEFAULT_ORGANIZER_CHAT)),
        "career_complete": bool(career_complete),
        "career_status": career_status,
        "organizer_required": organizer_required,
        "organizer_complete": bool(organizer_complete),
        "organizer_status": organizer_status,
        "career_overdue": bool(now >= overdue_at and not career_complete),
        "organizer_overdue": bool(
            organizer_required and now >= overdue_at and not organizer_complete
        ),
        "career_next_attempt_at": (
            career_retry_at.astimezone().isoformat(timespec="seconds")
            if career_retry_at is not None
            else ""
        ),
        "organizer_next_attempt_at": (
            organizer_retry_at.astimezone().isoformat(timespec="seconds")
            if organizer_retry_at is not None
            else ""
        ),
    }
    write_json_file(scheduler_state_path(), state)


def next_run_time(now: datetime, hhmm: str) -> datetime:
    candidate = scheduled_run_time(now, hhmm)
    if now > candidate:
        candidate += timedelta(days=1)
    return candidate


def scheduled_run_time(now: datetime, hhmm: str) -> datetime:
    try:
        hour, minute = [int(part) for part in hhmm.split(":", 1)]
    except (ValueError, TypeError):
        hour, minute = 8, 30
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def run_daily(args: argparse.Namespace) -> dict[str, Any]:
    chats = args.chat or list(DEFAULT_CHATS)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    private_dir = PRIVATE / "output" / "career_daily"
    private_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d")
    run_id = now.strftime("%Y-%m-%d-%H%M%S")
    trace_dir = private_dir / "runs" / run_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    evidence = collect_evidence(chats, args.memory_db, model=args.model)
    prompt = build_prompt(evidence)
    (trace_dir / "agent_prompt.md").write_text(prompt, encoding="utf-8")
    write_evidence_artifacts(trace_dir, evidence)
    result = run_agent_session(
        prompt,
        backend=select_agent_backend({}),
        chat_name="career-daily-agent",
        role="career_research",
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        sandbox="read-only",
        timeout_seconds=args.timeout_seconds,
        workdir=ROOT,
        reuse=True,
    )
    body = str(result.get("message") or "").strip()
    agent_ok = bool(result.get("ok")) and bool(body)
    if not agent_ok:
        body = (
            "# Daily Career Strategy Agent Failed\n\n"
            f"- ok: {result.get('ok')}\n"
            f"- returncode: {result.get('returncode')}\n"
            f"- stderr_tail: {result.get('stderr_tail')}\n"
        )
    private_report = private_dir / f"{stamp}-career-strategy-private.md"
    share_report = OUTPUT / f"{stamp}-career-strategy.md"
    private_report.write_text(body + "\n", encoding="utf-8")
    shareable = sanitize_shareable_report(body)
    share_report.write_text(shareable + "\n", encoding="utf-8")
    trace_private_report = trace_dir / "private_report.md"
    trace_share_report = trace_dir / "share_report.md"
    trace_private_report.write_text(body + "\n", encoding="utf-8")
    trace_share_report.write_text(shareable + "\n", encoding="utf-8")
    agent_result = sanitize_agent_result(result)
    (trace_dir / "agent_result.json").write_text(
        json.dumps(agent_result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    send_status: dict[str, Any] = {"attempted": False}
    if args.send and agent_ok:
        send_status = send_daily_result(args, share_report, body)
    manifest = build_trace_manifest(
        args=args,
        chats=chats,
        trace_dir=trace_dir,
        private_report=private_report,
        share_report=share_report,
        trace_private_report=trace_private_report,
        trace_share_report=trace_share_report,
        result=result,
        send_status=send_status,
        run_id=run_id,
    )
    update_delivery_retry_state(manifest, send_status)
    (trace_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    delivery_ok = not args.send or bool(send_status.get("complete"))
    return {
        "ok": agent_ok and delivery_ok,
        "status": "done" if agent_ok and delivery_ok else ("delivery_failed" if agent_ok else "agent_failed"),
        "run_id": run_id,
        "trace_dir": str(trace_dir),
        "manifest": str(trace_dir / "manifest.json"),
        "private_report": str(private_report),
        "share_report": str(share_report),
        "send": send_status,
        "next_delivery_attempt_at": manifest.get("next_delivery_attempt_at", ""),
        "summary": extract_daily_chat_summary(body),
        "agent": {
            "backend": result.get("backend", "codex"),
            "thread_id": result.get("thread_id"),
            "resumed": result.get("resumed"),
            "complete": bool(result.get("ok")) and bool(str(result.get("message") or "").strip()),
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
        },
    }


def career_delivery_complete_for_date(stamp: str, *, require_send: bool) -> bool:
    runs_dir = PRIVATE / "output" / "career_daily" / "runs"
    if not runs_dir.is_dir():
        return False
    for manifest_path in sorted(runs_dir.glob(f"{stamp}-*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
        report = Path(str(outputs.get("share_report_latest") or ""))
        if not report.is_file():
            continue
        if not require_send:
            return True
        send = manifest.get("send") if isinstance(manifest.get("send"), dict) else {}
        if bool(send.get("complete")):
            return True
    return False


def latest_career_manifest(stamp: str) -> tuple[Path, dict[str, Any]] | None:
    runs_dir = PRIVATE / "output" / "career_daily" / "runs"
    if not runs_dir.is_dir():
        return None
    for manifest_path in sorted(runs_dir.glob(f"{stamp}-*/manifest.json"), reverse=True):
        manifest = read_json_file(manifest_path)
        outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
        report = Path(str(outputs.get("share_report_latest") or ""))
        private_report = Path(str(outputs.get("private_report_latest") or ""))
        agent = manifest.get("agent") if isinstance(manifest.get("agent"), dict) else {}
        if agent.get("complete") is False:
            continue
        agent_result_path = Path(str(outputs.get("agent_result") or ""))
        agent_result = read_json_file(agent_result_path) if agent_result_path.is_file() else {}
        if agent_result and agent_result.get("ok") is False:
            continue
        if report.is_file() and private_report.is_file():
            return manifest_path, manifest
    return None


def retry_existing_career_delivery(
    args: argparse.Namespace,
    stamp: str,
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    """Retry one generated career report without another model invocation."""

    located = latest_career_manifest(stamp)
    if located is None:
        return None
    manifest_path, manifest = located
    if bool((manifest.get("send") or {}).get("complete")):
        return {"ok": True, "status": "already_delivered", "manifest": str(manifest_path)}
    if not force and not delivery_retry_due(manifest):
        return {
            "ok": False,
            "status": "delivery_deferred",
            "manifest": str(manifest_path),
            "next_delivery_attempt_at": manifest.get("next_delivery_attempt_at"),
        }
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    report = Path(str(outputs.get("share_report_latest") or ""))
    private_report = Path(str(outputs.get("private_report_latest") or ""))
    body = private_report.read_text(encoding="utf-8", errors="replace")
    previous_send = manifest.get("send") if isinstance(manifest.get("send"), dict) else {}
    known_companions = [
        Path(str(path))
        for path in previous_send.get("pdf_companions") or []
        if Path(str(path)).is_file()
    ]
    observed_files = observed_outbound_files(
        str(getattr(args, "send_chat", "lachlanchan") or "lachlanchan"),
        known_companions,
        not_before=str(manifest.get("created_at") or ""),
    )
    send_status = send_daily_result(
        args,
        report,
        body,
        already_sent_files={
            *[str(path) for path in previous_send.get("files_sent") or []],
            *observed_files,
        },
        message_already_sent=bool(previous_send.get("message_sent")),
    )
    manifest["send"] = send_status
    update_delivery_retry_state(manifest, send_status)
    write_json_file(manifest_path, manifest)
    return {
        "ok": bool(send_status.get("complete")),
        "status": "done" if send_status.get("complete") else "delivery_failed",
        "manifest": str(manifest_path),
        "send": send_status,
        "next_delivery_attempt_at": manifest.get("next_delivery_attempt_at", ""),
    }


def delivery_retry_due(state: dict[str, Any], *, now: datetime | None = None) -> bool:
    raw = str(state.get("next_delivery_attempt_at") or "").strip()
    if not raw:
        return True
    try:
        due = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    if due.tzinfo is None:
        due = due.replace(tzinfo=current.tzinfo)
    return current >= due.astimezone(current.tzinfo)


def update_delivery_retry_state(state: dict[str, Any], send_status: dict[str, Any]) -> None:
    if not send_status.get("attempted"):
        return
    now = datetime.now().astimezone()
    state["last_delivery_attempt_at"] = now.isoformat(timespec="seconds")
    if send_status.get("complete"):
        state["delivery_attempts"] = 0
        state.pop("next_delivery_attempt_at", None)
        return
    attempts = int(state.get("delivery_attempts") or 0) + 1
    delay = min(
        max(60, DELIVERY_RETRY_BASE_SECONDS) * (2 ** min(attempts - 1, 4)),
        max(60, DELIVERY_RETRY_MAX_SECONDS),
    )
    state["delivery_attempts"] = attempts
    state["next_delivery_attempt_at"] = (now + timedelta(seconds=delay)).isoformat(timespec="seconds")


def run_organizer(
    args: argparse.Namespace,
    *,
    force: bool = False,
    force_delivery: bool = False,
) -> dict[str, Any]:
    chat = str(getattr(args, "organize_chat", DEFAULT_ORGANIZER_CHAT) or DEFAULT_ORGANIZER_CHAT)
    stamp = datetime.now().strftime("%Y-%m-%d")
    state_path = organizer_state_path()
    state = read_json_file(state_path)
    report = OUTPUT / f"{stamp}-recent-items.zh.md"
    pdf = OUTPUT / f"{stamp}-recent-items.zh.pdf"

    if (
        state.get("date") == stamp
        and state.get("chat") == chat
        and organizer_quality_accepted(state)
        and pdf.is_file()
        and (
            observed_outbound_file(
                chat,
                pdf,
                not_before=str(state.get("generated_at") or ""),
            )
            or observed_outbound_filename(
                chat,
                pdf.name,
                not_before=str(state.get("generated_at") or ""),
            )
        )
    ):
        resolved_pdf = str(pdf.expanduser().resolve())
        state.update(
            {
                "status": "delivered",
                "send": {
                    "attempted": True,
                    "complete": True,
                    "file_sent": True,
                    "files_sent": [resolved_pdf],
                    "errors": [],
                    "reconciled_from_outbound_echo": True,
                },
                "delivery_attempts": 0,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        state.pop("next_delivery_attempt_at", None)
        write_json_file(state_path, state)

    if not force and organizer_delivery_matches(state, stamp, chat, pdf):
        return {
            "ok": True,
            "status": "already_delivered",
            "chat": chat,
            "report": str(report),
            "pdf": str(pdf),
            "send": state.get("send") or {},
        }

    generated = bool(
        not force
        and state.get("date") == stamp
        and state.get("chat") == chat
        and organizer_quality_accepted(state)
        and state.get("status") in {"ready", "generated", "delivery_failed"}
        and report.is_file()
        and pdf.is_file()
        and pdf.stat().st_size > 0
    )
    if (
        generated
        and bool(args.send)
        and not force
        and not force_delivery
        and not delivery_retry_due(state)
    ):
        return {
            "ok": False,
            "status": "delivery_deferred",
            "chat": chat,
            "report": str(report),
            "pdf": str(pdf),
            "generated": False,
            "next_delivery_attempt_at": state.get("next_delivery_attempt_at"),
        }
    result: dict[str, Any] = {}
    if not generated:
        memory_db = getattr(args, "memory_db", DEFAULT_MEMORY_DB)
        memory_chats = organizer_memory_chats(chat)
        backend = select_agent_backend({})
        context_model = agent_context_model(backend, args.model)
        context_budget = resolve_memory_budget(model=context_model, role="daily")
        available_tokens = int(context_budget["available_input_tokens"])
        recent_token_budget = min(7000, max(2800, int(available_tokens * 0.27)))
        history_token_budget = min(
            int(context_budget["memory_token_budget"]),
            max(2400, int(available_tokens * 0.43)),
        )
        snapshot = life_memo_snapshot(
            memory_db,
            memory_chats,
            limit=200,
            token_budget=recent_token_budget,
        )
        history = build_history_context(
            memory_db,
            memory_chats,
            ORGANIZER_HISTORY_QUERY,
            token_budget=history_token_budget,
            model=context_model,
            role="daily",
        )
        prompt = build_organizer_prompt(
            chat,
            snapshot,
            history_context=str(history.get("snapshot") or ""),
        )
        trace_dir = organizer_trace_dir(stamp)
        trace_dir.mkdir(parents=True, exist_ok=True)
        (trace_dir / "recent-evidence.md").write_text(snapshot.rstrip() + "\n", encoding="utf-8")
        (trace_dir / "lifetime-context.md").write_text(
            str(history.get("snapshot") or "").rstrip() + "\n",
            encoding="utf-8",
        )
        (trace_dir / "agent-prompt.md").write_text(prompt.rstrip() + "\n", encoding="utf-8")
        write_json_file(trace_dir / "context-manifest.json", {
            "backend": backend,
            "requested_model": args.model,
            "context_model": context_model,
            "recent_token_budget": recent_token_budget,
            "recent_estimated_tokens": estimate_tokens(snapshot),
            "history_token_budget": history_token_budget,
            "prompt_estimated_tokens": estimate_tokens(prompt),
            "history_retrieval": history.get("manifest") or {},
        })
        result = run_agent_session(
            prompt,
            backend=backend,
            chat_name=chat,
            role="daily_organizer",
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            sandbox="read-only",
            timeout_seconds=args.timeout_seconds,
            workdir=ROOT,
            reuse=True,
        )
        raw_body = str(result.get("message") or "").strip()
        (trace_dir / "agent-output-1.txt").write_text(raw_body.rstrip() + "\n", encoding="utf-8")
        body = normalize_organizer_output(raw_body)
        quality = organizer_output_quality(
            body,
            snapshot,
            history_context=str(history.get("snapshot") or ""),
        )
        quality_attempts = 1
        if result.get("ok") and body and not quality.get("accepted"):
            repair_prompt = build_organizer_repair_prompt(body, quality)
            (trace_dir / "repair-prompt.md").write_text(
                repair_prompt.rstrip() + "\n",
                encoding="utf-8",
            )
            repaired = run_agent_session(
                repair_prompt,
                backend=backend,
                chat_name=chat,
                role="daily_organizer",
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                sandbox="read-only",
                timeout_seconds=args.timeout_seconds,
                workdir=ROOT,
                reuse=True,
            )
            quality_attempts += 1
            repaired_raw = str(repaired.get("message") or "").strip()
            (trace_dir / "agent-output-2.txt").write_text(
                repaired_raw.rstrip() + "\n",
                encoding="utf-8",
            )
            repaired_body = normalize_organizer_output(repaired_raw)
            repaired_quality = organizer_output_quality(
                repaired_body,
                snapshot,
                history_context=str(history.get("snapshot") or ""),
            )
            if repaired.get("ok"):
                result = repaired
                body = repaired_body
                quality = repaired_quality
        if not result.get("ok") or not body:
            return {
                "ok": False,
                "status": "agent_failed",
                "chat": chat,
                "agent": sanitize_agent_result(result),
                "trace_dir": str(trace_dir),
            }
        quality["attempts"] = quality_attempts
        write_json_file(trace_dir / "quality.json", quality)
        if not quality.get("accepted"):
            state = {
                "schema": "labcanvas.wechat.daily_organizer.v3",
                "date": stamp,
                "chat": chat,
                "status": "quality_failed",
                "quality": quality,
                "trace_dir": str(trace_dir),
                "agent": {
                    "backend": result.get("backend"),
                    "provider": result.get("provider"),
                    "thread_id": result.get("thread_id"),
                    "resumed": result.get("resumed"),
                    "model": args.model,
                    "reasoning_effort": args.reasoning_effort,
                },
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            write_json_file(state_path, state)
            return {
                "ok": False,
                "status": "quality_failed",
                "chat": chat,
                "quality": quality,
                "trace_dir": str(trace_dir),
            }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        report.write_text(body.rstrip() + "\n", encoding="utf-8")
        rendered = render_interactive_organizer_pdf(report, pdf)
        if rendered is None or not pdf.is_file() or pdf.stat().st_size <= 0:
            return {
                "ok": False,
                "status": "pdf_failed",
                "chat": chat,
                "report": str(report),
            }
        state = {
            "schema": "labcanvas.wechat.daily_organizer.v3",
            "date": stamp,
            "chat": chat,
            "status": "ready",
            "report": str(report),
            "pdf": str(pdf),
            "agent": {
                "backend": result.get("backend"),
                "provider": result.get("provider"),
                "thread_id": result.get("thread_id"),
                "resumed": result.get("resumed"),
                "model": args.model,
                "reasoning_effort": args.reasoning_effort,
            },
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "history_retrieval": history.get("manifest") or {},
            "context_model": context_model,
            "quality": quality,
            "trace_dir": str(trace_dir),
        }
        write_json_file(state_path, state)

    send_status: dict[str, Any] = {"attempted": False, "complete": not bool(args.send)}
    if args.send:
        send_status = send_organizer_pdf(args, pdf, chat)
    final_status = (
        "delivered"
        if bool(args.send) and send_status.get("complete")
        else ("delivery_failed" if bool(args.send) else "generated")
    )
    state.update(
        {
            "date": stamp,
            "chat": chat,
            "report": str(report),
            "pdf": str(pdf),
            "status": final_status,
            "send": send_status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    if args.send:
        update_delivery_retry_state(state, send_status)
    write_json_file(state_path, state)
    return {
        "ok": bool(send_status.get("complete")),
        "status": state["status"],
        "chat": chat,
        "report": str(report),
        "pdf": str(pdf),
        "generated": not generated,
        "send": send_status,
        "agent": state.get("agent") or {},
        "next_delivery_attempt_at": state.get("next_delivery_attempt_at", ""),
    }


def organizer_delivery_matches(state: dict[str, Any], stamp: str, chat: str, pdf: Path) -> bool:
    return bool(
        state.get("date") == stamp
        and state.get("chat") == chat
        and organizer_quality_accepted(state)
        and state.get("status") == "delivered"
        and (state.get("send") or {}).get("complete")
        and pdf.is_file()
        and pdf.stat().st_size > 0
    )


def organizer_quality_accepted(state: dict[str, Any]) -> bool:
    quality = state.get("quality") if isinstance(state, dict) else None
    return bool(isinstance(quality, dict) and quality.get("accepted") is True)


def organizer_trace_dir(stamp: str) -> Path:
    run_id = datetime.now().strftime(f"{stamp}-%H%M%S-%f")
    return PRIVATE / "output" / "career_daily" / "organizer-runs" / run_id


def organizer_state_path() -> Path:
    if PRIVATE == ROOT / "agentic_tools" / "wechat_gui_agent" / ".private":
        return ORGANIZER_STATE
    return PRIVATE / "output" / "career_daily" / "organizer-delivery.json"


def organizer_memory_chats(chat: str) -> list[str]:
    profile = profile_for_chat(chat)
    candidates = profile_aliases("writing_money") if profile.get("id") == "writing_money" else [chat]
    result: list[str] = []
    for candidate in [chat, *candidates]:
        value = str(candidate or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def send_organizer_pdf(args: argparse.Namespace, pdf: Path, chat: str) -> dict[str, Any]:
    delivery_task_id = organizer_delivery_task_id(pdf)
    status: dict[str, Any] = {
        "attempted": True,
        "complete": False,
        "file_sent": False,
        "files_sent": [],
        "errors": [],
        "delivery_task_id": delivery_task_id,
    }
    with reserve_gui_send_priority("daily_organizer", chat):
        try:
            send_daily_with_busy_retry(
                send_file,
                pdf,
                chat,
                args.send_targets,
                task={"id": delivery_task_id},
            )
        except Exception as exc:  # noqa: BLE001
            status["errors"].append(f"file {pdf}: {exc}")
            return status
    status["file_sent"] = True
    status["files_sent"] = [str(pdf)]
    status["complete"] = True
    return status


def organizer_delivery_task_id(pdf: Path) -> str:
    """Return the stable idempotency scope for one dated organizer report."""

    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-recent-items\.zh\.pdf", pdf.name)
    if match is None:
        raise ValueError(f"Unexpected organizer PDF name: {pdf.name}")
    return f"daily-organizer-{match.group(1)}-{ORGANIZER_DELIVERY_VERSION}"


def build_organizer_prompt(
    chat: str,
    snapshot: str,
    *,
    history_context: str = "",
) -> str:
    return f"""You organize one private WeChat group's recent notes into a useful daily memo.

Exact chat: {chat}

Return only polished Chinese Markdown for a mobile-readable PDF. Do not mention
the automation, database, classifiers, local paths, model, or prompt.
Do not wrap the Markdown in JSON, a `response` field, or a code fence. This is
direct synthesis from supplied evidence and needs no tool call or file access.

Use only the evidence below. Deduplicate repeated classifications of the same
message. Do not invent dates, deadlines, completion states, groceries, calendar
events, or commitments. A question or request is not automatically a real todo.

This is the full daily organization, not a narrow highlight and not a raw chat
dump. Cover every distinct concrete action, reminder, idea,
writing/language/career/money signal, and unresolved question in the bounded
evidence. Merge duplicate classifier rows and closely related fragments, but do
not silently drop a concrete item just because it does not fit one preferred
narrative. Full coverage means preserving meaning and continuity, not copying
source lines one by one.

Write two complementary layers:

1. Start with a contextual reading of the day. In several substantial prose
   paragraphs, explain what is newly active, what changed, which fragments form
   one larger thread, what remains uncertain, and what earlier context clarifies.
   This should feel like a thoughtful person who has followed the whole
   conversation, not a database export.
2. Follow with a complete organized reference section. Group all concrete items
   under natural headings, preserve important names and exact lists where they
   matter, and annotate status or relationship briefly. This layer may use
   bullets, but it must not replace the contextual reading.

The organized reference is thematic, not an audit trail. Never append a
source-by-source or message-by-message evidence ledger, a numbered restatement
of the input, a coverage count, or a section arranged "by source order". Do not
narrate how the report was generated or claim that source rows were audited.
Do not expose media duration, byte counts, file metadata, source IDs, or ASR
diagnostics. A voice note contributes only its cleaned meaning.

Include a clear unresolved-questions/decisions section when the evidence has
them. End with at most three high-leverage actions. Use at least four
substantial non-list paragraphs across the report. Do not expose timestamps,
classifier labels, transport metadata, quoted-message wrappers, ASR wrappers,
or raw transcript fragments. Rewrite spoken fragments into clear notes while
preserving their meaning.

Organize naturally rather than forcing empty sections. Before synthesis, sort
items into the lowest valid category and do not inflate ordinary notes into
life direction:
- 待办 / To-do: concrete open actions for today or this week;
- 物品和资源: objects, parts, books, purchases, tools, and inventory;
- 小事和日常备忘: factual reminders, errands, explicit dates, and daily notes;
- 想做的项目和作品: later ideas, experiments, writing, product, repo, video,
  CAD/PCB, language, career, and money projects;
- 人生方向 / 长期战略: only signals explicitly framed by the user as life-level
  intent or corroborated by GitHub, website, local repos, finished artifacts,
  repeated output, or other strong project evidence.

Items in 物品和资源 or 小事和日常备忘 are logistics by default. Do not turn them
into symbolism, personality analysis, hidden motivation, a "main bet", or
life-planning signal unless the evidence explicitly justifies that move. Keep
the full organization separate from any short direction synthesis.

Be comprehensive, condensed, and substantive. For a large evidence packet,
write a genuinely full multi-page report rather than stopping after two pages.
Preserve important technical names and quoted intent. Explain useful
connections and changes, and end with at most three high-leverage next actions.
Do not add generic productivity advice.
Write every concrete open action and every final next action as a Markdown task
line beginning exactly with `- [ ]`. Use ordinary bullets for evidence, ideas,
and non-action observations. These task lines become clickable checkboxes in the
delivered PDF.

Recent exact-chat evidence:
{snapshot}

Relevance-ranked longitudinal context from the complete authorized history:
{history_context or '(no additional longitudinal context found)'}

Use longitudinal context only to resolve names, continuity, repeated projects,
and explicit prior decisions. It is not today's inbox: never revive a completed
task or list an old note unless the recent organized evidence makes it current.
"""


ORGANIZER_OUTPUT_KEYS = (
    "report_markdown",
    "markdown",
    "response",
    "message",
    "content",
    "result",
    "output",
)
ORGANIZER_GENERIC_FAILURE_RE = re.compile(
    r"(?:no\s+(?:dedicated\s+)?(?:tool|memo-writing)|"
    r"no\s+tool\s+exists|"
    r"无法(?:执行文件|调用外部工具|完成|生成)|"
    r"请提供具体(?:需要|内容)|"
    r"当前环境为只读|"
    r"blocker\s*:|"
    r"manually\s+format)",
    flags=re.IGNORECASE,
)
ORGANIZER_TERM_STOPWORDS = {
    "active",
    "body",
    "chat",
    "http",
    "https",
    "inbox",
    "memo",
    "open",
    "quoted",
    "request",
    "source",
    "status",
    "title",
    "wechat",
    "今天",
    "任务",
    "内容",
    "备忘",
    "外语",
    "想法",
    "挣钱",
    "整理",
    "项目",
}


def normalize_organizer_output(value: Any) -> str:
    """Unwrap common agent envelopes while preserving ordinary Markdown."""

    text = strip_markdown_fence(str(value or "").strip())
    for _ in range(4):
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            break
        if isinstance(payload, str):
            candidate = payload
        elif isinstance(payload, dict):
            candidate = next(
                (
                    payload[key]
                    for key in ORGANIZER_OUTPUT_KEYS
                    if key in payload and isinstance(payload[key], str)
                ),
                None,
            )
            if candidate is None:
                break
        else:
            break
        text = strip_markdown_fence(str(candidate).strip())
    return text.strip()


def organizer_evidence_bodies(snapshot: str) -> list[str]:
    bodies: list[str] = []
    for raw in str(snapshot or "").splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        body = line.split(": ", 1)[-1].strip()
        body = re.sub(r"https?://\S+", " ", body)
        body = " ".join(body.split())
        if body:
            bodies.append(body)
    return bodies


def organizer_grounding_metrics(body: str, snapshot: str) -> dict[str, Any]:
    evidence = organizer_evidence_bodies(snapshot)
    term_sets: list[set[str]] = []
    frequencies: dict[str, int] = {}
    for item in evidence:
        terms = {
            term.casefold()
            for term in lexical_terms(item)
            if len(term) >= 3
            and term.casefold() not in ORGANIZER_TERM_STOPWORDS
            and not term.casefold().startswith(("http", "www"))
        }
        term_sets.append(terms)
        for term in terms:
            frequencies[term] = frequencies.get(term, 0) + 1
    folded = str(body or "").casefold()
    matched: list[int] = []
    missing: list[str] = []
    frequency_ceiling = max(2, len(evidence) // 7)
    for index, (item, terms) in enumerate(zip(evidence, term_sets)):
        distinctive = sorted(
            (term for term in terms if frequencies.get(term, 0) <= frequency_ceiling),
            key=lambda term: (frequencies.get(term, 0), -len(term), term),
        )[:16]
        if any(term in folded for term in distinctive):
            matched.append(index)
        elif len(missing) < 8:
            missing.append(item[:140])
    return {
        "evidence_items": len(evidence),
        "grounded_items": len(matched),
        "missing_examples": missing,
    }


def organizer_prose_metrics(body: str) -> dict[str, Any]:
    """Measure whether a memo interprets evidence instead of only listing it."""

    prose: list[str] = []
    bullet_chars = 0
    for raw in str(body or "").splitlines():
        line = raw.strip()
        if not line or re.match(r"^#{1,4}\s+", line):
            continue
        if re.match(r"^(?:[-*+] |\d+[.)、]\s+)", line):
            bullet_chars += len(line)
            continue
        if line.startswith((">", "|")):
            continue
        cleaned = clean_markdown_inline(line)
        if len(cleaned) >= 32:
            prose.append(cleaned)
    prose_chars = sum(len(item) for item in prose)
    content_chars = prose_chars + bullet_chars
    return {
        "prose_paragraphs": len(prose),
        "prose_characters": prose_chars,
        "bullet_characters": bullet_chars,
        "bullet_character_ratio": (
            round(bullet_chars / content_chars, 4) if content_chars else 0.0
        ),
    }


def organizer_output_quality(
    body: str,
    snapshot: str,
    *,
    history_context: str = "",
) -> dict[str, Any]:
    text = str(body or "").strip()
    grounding = organizer_grounding_metrics(text, snapshot)
    prose = organizer_prose_metrics(text)
    evidence_items = int(grounding["evidence_items"])
    min_chars = min(7600, max(900, evidence_items * 76))
    min_headings = 5 if evidence_items >= 20 else (4 if evidence_items >= 8 else 2)
    min_bullets = min(20, max(6, evidence_items // 4))
    min_grounded = min(18, max(5, evidence_items // 4))
    min_prose_paragraphs = 4 if evidence_items >= 12 else 2
    min_prose_chars = min(1800, max(420, evidence_items * 20))
    heading_count = len(re.findall(r"(?m)^#{1,4}\s+\S", text))
    bullet_count = len(re.findall(r"(?m)^\s*(?:[-*+] |\d+[.)、]\s+)", text))
    task_count = len(re.findall(r"(?m)^\s*[-*+]\s+\[\s*\]\s+", text))
    reasons: list[str] = []
    if not text:
        reasons.append("empty_output")
    if text.startswith(("{", "[")) or "\\n" in text:
        reasons.append("raw_structured_envelope")
    if ORGANIZER_GENERIC_FAILURE_RE.search(text):
        reasons.append("generic_refusal_or_tool_excuse")
    if len(text) < min_chars:
        reasons.append("too_short_for_evidence")
    if heading_count < min_headings:
        reasons.append("insufficient_structure")
    if bullet_count < min_bullets:
        reasons.append("insufficient_item_coverage")
    if int(grounding["grounded_items"]) < min_grounded:
        reasons.append("insufficient_evidence_grounding")
    if int(prose["prose_paragraphs"]) < min_prose_paragraphs:
        reasons.append("insufficient_contextual_synthesis")
    if int(prose["prose_characters"]) < min_prose_chars:
        reasons.append("insufficient_contextual_explanation")
    if evidence_items >= 12 and float(prose["bullet_character_ratio"]) > 0.82:
        reasons.append("raw_list_dominance")
    if re.search(
        r"(?m)^\s*(?:[-*+]\s+)?(?:inbox|memo|request|web_clip|money|writing)\s*\|\s*20\d{2}-",
        text,
        flags=re.IGNORECASE,
    ):
        reasons.append("raw_evidence_metadata")
    if re.search(
        r"(?:证据.{0,8}(?:逐条|清单|按来源)|逐条.{0,8}(?:转述|复述)|"
        r"按来源顺序|便于回查与审计|以上.{0,20}条.{0,20}(?:底稿|证据))",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        reasons.append("source_by_source_evidence_dump")
    if re.search(
        r"(?:微信语音|voice|audio).{0,80}(?:时长|duration).{0,80}(?:字节|bytes)|"
        r"(?:时长|duration).{0,40}\d+(?:\.\d+)?\s*(?:秒|s).{0,80}(?:字节|bytes)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        reasons.append("private_media_metadata_exposed")
    return {
        "accepted": not reasons,
        "reasons": reasons,
        "characters": len(text),
        "headings": heading_count,
        "bullets": bullet_count,
        "tasks": task_count,
        "minimum_characters": min_chars,
        "minimum_headings": min_headings,
        "minimum_bullets": min_bullets,
        "minimum_grounded_items": min_grounded,
        "minimum_prose_paragraphs": min_prose_paragraphs,
        "minimum_prose_characters": min_prose_chars,
        "history_context_available": bool(str(history_context or "").strip()),
        **prose,
        **grounding,
    }


def build_organizer_repair_prompt(body: str, quality: dict[str, Any]) -> str:
    missing = quality.get("missing_examples") if isinstance(quality, dict) else []
    missing = missing if isinstance(missing, list) else []
    examples = "\n".join(f"- {item}" for item in missing[:6]) or "- Re-read the supplied evidence ledger."
    return f"""Your previous Memo draft failed the host's content-quality audit and must not be delivered.

Failure reasons: {', '.join(str(item) for item in quality.get('reasons') or [])}
Observed: {quality.get('characters', 0)} characters, {quality.get('headings', 0)} headings,
{quality.get('bullets', 0)} bullets, {quality.get('prose_paragraphs', 0)} substantial prose paragraphs,
and {quality.get('grounded_items', 0)} grounded evidence items.

Rewrite it now from the complete recent-evidence and lifetime-context packet in
the immediately preceding request. Preserve actual names, books, devices,
articles, projects, decisions, and open questions. Group related fragments, but
do not replace them with generic business, translation, productivity, or
language-service advice. Distinguish current logistics from projects and from
long-term direction. Open with an interpreted contextual overview and explain
changes, connections, decisions, and unresolved questions in at least
{quality.get('minimum_prose_paragraphs', 4)} substantial non-list paragraphs.
Then provide the complete grouped reference ledger. Use at least
{quality.get('minimum_headings', 3)} Markdown headings,
{quality.get('minimum_bullets', 8)} concrete bullets, and about
{quality.get('minimum_characters', 1200)} or more Chinese characters when the
evidence supports it. Do not merely expand, reorder, or paraphrase the source
rows one by one. Do not add a source-by-source evidence appendix, input coverage
count, generation-process narration, voice duration, byte count, source ID, or
ASR diagnostics. Keep actionable items as `- [ ]` task lines.

Representative evidence missed by the previous draft:
{examples}

Return only the finished Chinese Markdown. Do not return JSON, a code fence,
an apology, a tool limitation, or commentary about this audit.

Rejected draft for reference:
{body[:1800]}
"""


def render_interactive_organizer_pdf(source: Path, output: Path) -> Path | None:
    """Render a Chinese organizer report with real AcroForm checkboxes."""

    try:
        markdown = source.read_text(encoding="utf-8")
    except OSError:
        return None
    body, checkbox_count = organizer_markdown_to_latex(markdown)
    if checkbox_count <= 0:
        body += "\n" + organizer_checkbox_latex("确认今天最重要的一项行动", checkbox_count + 1)
        checkbox_count += 1
    stamp = datetime.now().strftime("%Y-%m-%d")
    document = rf"""\documentclass[10.5pt]{{article}}
\usepackage[a4paper,top=17mm,bottom=18mm,left=18mm,right=18mm]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\usepackage{{xcolor}}
\usepackage{{enumitem}}
\usepackage{{microtype}}
\usepackage{{titlesec}}
\usepackage{{fancyhdr}}
\usepackage[most]{{tcolorbox}}
\usepackage[unicode,colorlinks=true,linkcolor=black,urlcolor=blue]{{hyperref}}
\setmainfont{{Noto Sans}}
\setCJKmainfont{{Noto Sans CJK SC}}
\definecolor{{LabInk}}{{HTML}}{{1E293B}}
\definecolor{{LabBlue}}{{HTML}}{{0B7285}}
\definecolor{{LabGold}}{{HTML}}{{C58A24}}
\definecolor{{LabLine}}{{HTML}}{{CBD5E1}}
\definecolor{{LabPale}}{{HTML}}{{F2F8F8}}
\definecolor{{LabSoft}}{{HTML}}{{F8FAFC}}
\hypersetup{{pdftitle={{写作・外语・挣钱 每日整理 {stamp}}},pdfauthor={{AgInTi LabCanvas}}}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{6pt}}
\linespread{{1.08}}
\setlist[itemize]{{leftmargin=1.45em,itemsep=3pt,topsep=3pt,parsep=0pt}}
\titleformat{{\section}}{{\Large\bfseries\color{{LabInk}}}}{{}}{{0pt}}{{}}[\vspace{{1pt}}\color{{LabLine}}\titlerule]
\titleformat{{\subsection}}{{\large\bfseries\color{{LabBlue}}}}{{}}{{0pt}}{{}}
\titlespacing*{{\section}}{{0pt}}{{15pt}}{{7pt}}
\titlespacing*{{\subsection}}{{0pt}}{{10pt}}{{4pt}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[L]{{\small\color{{LabBlue}} 写作・外语・挣钱}}
\fancyhead[R]{{\small\color{{LabInk}} {stamp}}}
\fancyfoot[C]{{\small\color{{LabInk}} \thepage}}
\renewcommand{{\headrulewidth}}{{0.3pt}}
\renewcommand{{\headrule}}{{\hbox to\headwidth{{\color{{LabLine}}\leaders\hrule height \headrulewidth\hfill}}}}
\raggedbottom
\begin{{document}}
\begin{{Form}}
\begin{{tcolorbox}}[
  enhanced,
  colback=LabPale,
  colframe=LabPale,
  boxrule=0pt,
  arc=1.5mm,
  left=7mm,right=7mm,top=5mm,bottom=5mm,
  borderline west={{2.2pt}}{{0pt}}{{LabBlue}}
]
{{\LARGE\bfseries\color{{LabInk}} 写作・外语・挣钱}}\par
\vspace{{2pt}}{{\large\color{{LabBlue}} 每日脉络与行动整理}}\par
\vspace{{5pt}}{{\small\color{{LabInk}} {stamp} \quad 完整上下文整理 \quad 可勾选行动项}}
\end{{tcolorbox}}
\vspace{{3pt}}
{body}
\end{{Form}}
\end{{document}}
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    tex_output = output.with_suffix(".interactive.tex")
    tex_output.write_text(document, encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory(prefix="labcanvas-organizer-") as tmp:
            temp_dir = Path(tmp)
            tex = temp_dir / "organizer.tex"
            tex.write_text(document, encoding="utf-8")
            for _ in range(2):
                proc = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "-halt-on-error", tex.name],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=240,
                    check=False,
                )
                if proc.returncode != 0:
                    return None
            compiled = temp_dir / "organizer.pdf"
            if not compiled.is_file() or compiled.stat().st_size <= 0:
                return None
            output.write_bytes(compiled.read_bytes())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return output if pdf_has_interactive_form(output) else None


def organizer_markdown_to_latex(markdown: str) -> tuple[str, int]:
    lines: list[str] = []
    checkbox_count = 0
    action_section = False
    itemize_open = False
    first_heading_seen = False

    def close_itemize() -> None:
        nonlocal itemize_open
        if itemize_open:
            lines.append(r"\end{itemize}")
            itemize_open = False

    for raw in str(markdown or "").splitlines():
        value = raw.strip()
        if not value:
            close_itemize()
            lines.append(r"\par")
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", value)
        if heading:
            close_itemize()
            level = len(heading.group(1))
            if level == 1 and not first_heading_seen:
                first_heading_seen = True
                continue
            first_heading_seen = True
            title = clean_markdown_inline(heading.group(2))
            action_section = any(
                marker in title
                for marker in ("可推进", "行动", "下一步", "待办", "需要澄清")
            )
            command = "section*" if level <= 2 else "subsection*"
            lines.append(rf"\{command}{{{latex_escape(title)}}}")
            continue
        task = re.match(r"^(?:[-*+]|\d+[.)、])\s+(?:\[\s*\]\s*)?(.+)$", value)
        if task:
            explicit_task = bool(re.match(r"^(?:[-*+]|\d+[.)、])\s+\[\s*\]", value))
            text = re.sub(r"\s{2,}", " ", task.group(1).strip())
            if explicit_task or action_section:
                close_itemize()
                checkbox_count += 1
                lines.append(organizer_checkbox_latex(text, checkbox_count))
            else:
                if not itemize_open:
                    lines.append(r"\begin{itemize}")
                    itemize_open = True
                lines.append(rf"\item {markdown_inline_to_latex(text)}")
            continue
        close_itemize()
        lines.append(markdown_inline_to_latex(value) + r"\par")
    close_itemize()
    return "\n".join(lines), checkbox_count


def organizer_checkbox_latex(text: str, index: int) -> str:
    return (
        rf"\noindent\CheckBox[name=task-{index},width=1.7ex,height=1.7ex,"
        rf"bordercolor={{0.05 0.45 0.52}}]{{}}\hspace{{0.6em}}"
        rf"\parbox[t]{{0.91\linewidth}}{{{markdown_inline_to_latex(text)}}}\par\vspace{{4pt}}"
    )


def clean_markdown_inline(value: str) -> str:
    text = re.sub(r"^\[\s*\]\s*", "", str(value or "").strip())
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s{2,}", " ", text).strip()


def markdown_inline_to_latex(value: str) -> str:
    """Keep simple emphasis while escaping arbitrary memo text for XeLaTeX."""

    text = re.sub(r"^\[\s*\]\s*", "", str(value or "").strip())
    parts = re.split(r"(\*\*.*?\*\*|__.*?__|`.*?`)", text)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if (part.startswith("**") and part.endswith("**")) or (
            part.startswith("__") and part.endswith("__")
        ):
            rendered.append(rf"\textbf{{{latex_escape(part[2:-2])}}}")
        elif part.startswith("`") and part.endswith("`"):
            rendered.append(rf"\texttt{{{latex_escape(part[1:-1])}}}")
        else:
            rendered.append(latex_escape(part))
    return "".join(rendered)


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "→": r"$\rightarrow$",
        "←": r"$\leftarrow$",
        "↔": r"$\leftrightarrow$",
        "⇒": r"$\Rightarrow$",
    }
    return "".join(replacements.get(char, char) for char in str(value or ""))


def pdf_has_interactive_form(path: Path) -> bool:
    try:
        proc = subprocess.run(
            ["pdfinfo", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode == 0:
            return bool(re.search(r"^Form:\s+(?!none\b)\S+", proc.stdout, flags=re.MULTILINE | re.IGNORECASE))
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        payload = path.read_bytes()
    except OSError:
        return False
    return b"/AcroForm" in payload


def strip_markdown_fence(text: str) -> str:
    match = re.fullmatch(
        r"\s*```(?:markdown|md)?\s*\n(.*?)\n```\s*",
        str(text or ""),
        flags=re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else str(text or "").strip()


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_json_file(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def observed_outbound_files(
    chat: str,
    files: list[Path],
    *,
    not_before: str = "",
) -> set[str]:
    return {
        str(path.expanduser().resolve())
        for path in files
        if path.is_file() and observed_outbound_file(chat, path, not_before=not_before)
    }


def observed_outbound_file(chat: str, file_path: Path, *, not_before: str = "") -> bool:
    """Reconcile an uncertain GUI send from the exact outbound DB echo."""

    if not file_path.is_file():
        return False
    mirror_db = PRIVATE / "wechat_mirror.sqlite"
    if not mirror_db.is_file():
        return False
    identity = file_transport_identity(file_path)
    query = """
        SELECT events.message
        FROM events
        JOIN chats ON chats.id = events.chat_id
        WHERE chats.name = ?
          AND events.action = 'direct_message'
          AND events.direction = 'outbound'
          AND events.status = 'synced'
    """
    params: list[Any] = [chat]
    if not_before:
        query += " AND events.created_at >= ?"
        params.append(not_before)
    query += " ORDER BY events.id DESC LIMIT 80"
    try:
        with sqlite3.connect(mirror_db) as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.Error:
        return False
    return any(
        file_identities_match(identity, attachment_transport_identity(str(message or "")))
        for (message,) in rows
    )


def observed_outbound_filename(chat: str, filename: str, *, not_before: str) -> bool:
    """Match one dated scheduler artifact by exact chat and attachment title."""

    expected = Path(str(filename or "")).name
    if not expected or not not_before:
        return False
    mirror_db = PRIVATE / "wechat_mirror.sqlite"
    if not mirror_db.is_file():
        return False
    query = """
        SELECT events.message
        FROM events
        JOIN chats ON chats.id = events.chat_id
        WHERE chats.name = ?
          AND events.action = 'direct_message'
          AND events.direction = 'outbound'
          AND events.status = 'synced'
          AND events.created_at >= ?
        ORDER BY events.id DESC
        LIMIT 80
    """
    try:
        with sqlite3.connect(mirror_db) as conn:
            rows = conn.execute(query, [chat, not_before]).fetchall()
    except sqlite3.Error:
        return False
    return any(
        Path(
            str(attachment_transport_identity(str(message or "")).get("name") or "")
        ).name
        == expected
        for (message,) in rows
    )


def prior_strategy_snapshot(*, char_budget: int | None = None) -> str:
    """Carry durable decisions forward without replaying every prior report."""

    budget = max(
        2000,
        int(
            char_budget
            or os.environ.get("WECHAT_CAREER_PRIOR_STRATEGY_CHAR_BUDGET", "14000")
        ),
    )
    if not OUTPUT.is_dir():
        return "(no prior daily strategy reports found)"
    lines: list[str] = []
    used = 0
    for path in sorted(OUTPUT.glob("*-career-strategy.md"), reverse=True):
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        summary = extract_daily_chat_summary(body) or compact(body, 1200)
        summary = " ".join(summary.split())
        if not summary:
            continue
        line = f"- {path.stem}: {summary}"
        if used + len(line) + 1 > budget:
            continue
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines) if lines else "(no readable prior strategy decisions found)"


def collect_evidence(
    chats: list[str], memory_db: Path, *, model: str = "gpt-5.6-sol"
) -> dict[str, Any]:
    history = build_history_context(
        memory_db,
        chats,
        CAREER_HISTORY_QUERY,
        model=model,
        role="daily",
    )
    return {
        "memory_snapshot": memory_snapshot(memory_db, chats),
        "life_memo_snapshot": life_memo_snapshot(memory_db, profile_aliases("writing_money")),
        "full_history_context": str(history.get("snapshot") or ""),
        "full_history_manifest": history.get("manifest") or {},
        "prior_strategy_snapshot": prior_strategy_snapshot(),
        "project_surface": project_surface(),
        "lazyinvestment_snapshot": repo_readme_snapshot(Path("/home/lachlan/ProjectsLFS/LazyInvestment")),
        "voidabyss_snapshot": voidabyss_snapshot(),
        "identity_surface": identity_surface(),
        "public_profile_surface": public_profile_surface(),
    }


def build_prompt(evidence: dict[str, Any]) -> str:
    return f"""You are the daily career, writing, and opportunity strategy agent for Lachlan.

Goal: give one deep, useful morning note for wealth, freedom, and happiness.
The user prefers substance over format. Do not write a shallow checklist.

Use the evidence below:
- WeChat memory summary, especially writing/language/money and lachlanchan.
- The deduplicated life memo from the writing/language/money group, only as
  weak context unless it is explicitly tied to a project, repeated action,
  concrete output, or stated goal.
- A model-budgeted lifetime-memory hierarchy to which every authorized history
  row contributed, followed by purpose-ranked raw excerpts for exact wording.
- Prior daily strategy decisions, so today's note can update or challenge them
  instead of mechanically repeating a stable profile.
- Local repo/project surface.
- LazyInvestment/LazyEdit/LabCanvas/LazySkills/LALACHAN/voidabyss evidence when present.
- Public profile evidence from GitHub, lazying.art, and the exact Google Scholar
  profile. Verify current facts before recommending companies or stocks and do
  not merge similarly named authors.
- Use live web/deep research when a recommendation depends on current markets,
  companies, publications, policies, products, or opportunities. Prefer primary
  and official sources, retain direct URLs, distinguish publication dates from
  page-update dates, and state evidence gaps. Do not browse merely to decorate a
  private reflection that is already supported by local evidence.

Important:
- Write the main report in Chinese. English terms are fine when they are the natural name of a concept/company/product.
- Use an evidence hierarchy. Strong evidence is public/project evidence
  (GitHub, lazying.art, local repos, finished artifacts, shipped workflows,
  explicit current requests, and repeated work with outputs). Weak evidence is
  ordinary memo/todo/inbox/grocery/hardware-list material. Do not treat weak
  evidence as life-planning signal unless it is corroborated by strong evidence
  or the user explicitly frames it as a goal.
- If a daily item is merely a reminder, inventory note, purchase note, or life
  errand, say it is not strategically relevant today or ignore it. Do not turn
  it into symbolism, personality analysis, hidden motivation, or a "main bet".
- Use the user's GitHub, website, local repos, and explicitly stated projects
  as the anchor for career/money/product analysis. Life memo evidence may
  suggest logistics, but it must not override project evidence.
- If a point is not supported by the evidence, do not include it. If evidence is
  ambiguous, state the uncertainty instead of filling the gap with a narrative.
- Do not pad. Do not produce generic self-help, generic startup advice, or generic investment themes.
- Avoid a rigid mechanical template. Use natural memo-style headings only where they help the argument.
- Read consecutive messages as one unfolding thought when their context supports
  that interpretation. Do not focus only on the final fragment or silently drop
  an earlier requirement.
- Treat compacted lifetime memory as evidence, not destiny. Distinguish Lachlan's own
  statements from other participants, identify what changed, and avoid repeating
  yesterday's advice unless new evidence strengthens or overturns it.
- Give fewer, sharper ideas. Each recommendation should say why it fits this user specifically and what proof would validate it.
- This is educational analysis, not financial advice. For investments, provide a watchlist/rationale/risk framework, not certainty.
- Do not expose raw private chat logs. Summarize patterns and evidence.
- Do not claim the user's fate is fixed. Discuss recurring strengths and likely compounding lanes.
- Prefer concrete experiments and repeatable actions over broad life advice.

The report should answer, in a natural order:
- What Lachlan seems to be trying to write or become.
- What his visible talents are, based on concrete evidence.
- Which opportunity or money-making lane is most realistic now.
- What to ignore or stop doing because it dilutes the signal.
- What one primary bet deserves today's energy.
- What to do today.

Before the final questions, include one compact paragraph beginning exactly
with `微信摘要：`. Write 2-4 natural Chinese sentences that name the strongest
new evidence, the primary bet, and the concrete action for today. This paragraph
is sent directly to WeChat, so make it independently useful and avoid generic
completion language.

End with exactly three self-discovery questions. They must be specific to
today's evidence, not generic journaling prompts. Each question should be
answerable in 10-15 minutes, a little uncomfortable but kind, and capable of
changing tomorrow's plan if answered honestly. Format them as `Q1: ...?`,
`Q2: ...?`, and `Q3: ...?`, each followed by one short `为什么重要：...`
sentence.

WeChat memory snapshot:
{evidence.get('memory_snapshot', '')}

Deduplicated life/todo/memo snapshot:
{evidence.get('life_memo_snapshot', '')}

Full-history compaction and task-relevant exact excerpts:
{evidence.get('full_history_context', '')}

Prior daily strategy decisions:
{evidence.get('prior_strategy_snapshot', '')}

Local project surface:
{evidence.get('project_surface', '')}

LazyInvestment snapshot:
{evidence.get('lazyinvestment_snapshot', '')}

voidabyss snapshot:
{evidence.get('voidabyss_snapshot', '')}

lazying.art/local web identity hints:
{evidence.get('identity_surface', '')}

Public profile surface:
{evidence.get('public_profile_surface', '')}
"""


def write_evidence_artifacts(trace_dir: Path, evidence: dict[str, Any]) -> None:
    filenames = {
        "memory_snapshot": "memory_snapshot.md",
        "life_memo_snapshot": "life_memo_snapshot.md",
        "full_history_context": "full_history_context.md",
        "prior_strategy_snapshot": "prior_strategy_snapshot.md",
        "project_surface": "project_surface.md",
        "lazyinvestment_snapshot": "lazyinvestment_snapshot.md",
        "voidabyss_snapshot": "voidabyss_snapshot.md",
        "identity_surface": "identity_surface.md",
        "public_profile_surface": "public_profile_surface.md",
    }
    for key, filename in filenames.items():
        (trace_dir / filename).write_text(str(evidence.get(key) or "").rstrip() + "\n", encoding="utf-8")
    (trace_dir / "full_history_retrieval.json").write_text(
        json.dumps(
            evidence.get("full_history_manifest") or {},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def sanitize_agent_result(result: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in result.items():
        if key == "message":
            safe[key] = sanitize_shareable_report(str(value or ""))
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = sanitize_shareable_report(value) if isinstance(value, str) else value
        elif key in {"thread_id", "backend", "returncode", "resumed", "model", "reasoning_effort", "stderr_tail"}:
            safe[key] = value
    return safe


def build_trace_manifest(
    *,
    args: argparse.Namespace,
    chats: list[str],
    trace_dir: Path,
    private_report: Path,
    share_report: Path,
    trace_private_report: Path,
    trace_share_report: Path,
    result: dict[str, Any],
    send_status: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    return {
        "schema": "labcanvas.wechat.career_daily.trace.v1",
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "Traceable daily self-analysis for writing, career, money, opportunities, and personal direction.",
        "chats": chats,
        "agent": {
            "backend": result.get("backend", "codex"),
            "thread_id": result.get("thread_id"),
            "resumed": result.get("resumed"),
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "timeout_seconds": args.timeout_seconds,
            "sandbox": "read-only",
        },
        "inputs": {
            "memory_db": str(args.memory_db),
            "evidence_files": {
                "prompt": str(trace_dir / "agent_prompt.md"),
                "memory_snapshot": str(trace_dir / "memory_snapshot.md"),
                "life_memo_snapshot": str(trace_dir / "life_memo_snapshot.md"),
                "full_history_context": str(trace_dir / "full_history_context.md"),
                "full_history_retrieval": str(trace_dir / "full_history_retrieval.json"),
                "prior_strategy_snapshot": str(trace_dir / "prior_strategy_snapshot.md"),
                "project_surface": str(trace_dir / "project_surface.md"),
                "lazyinvestment_snapshot": str(trace_dir / "lazyinvestment_snapshot.md"),
                "voidabyss_snapshot": str(trace_dir / "voidabyss_snapshot.md"),
                "identity_surface": str(trace_dir / "identity_surface.md"),
                "public_profile_surface": str(trace_dir / "public_profile_surface.md"),
            },
        },
        "outputs": {
            "private_report_latest": str(private_report),
            "share_report_latest": str(share_report),
            "private_report_trace": str(trace_private_report),
            "share_report_trace": str(trace_share_report),
            "agent_result": str(trace_dir / "agent_result.json"),
        },
        "send": send_status,
        "git": {
            "agenticapp_head": run_short(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], timeout=1.5),
            "agenticapp_status_short": run_short(["git", "-C", str(ROOT), "status", "--short"], timeout=1.5),
        },
        "privacy": {
            "trace_dir_private": True,
            "private_evidence_may_include_chat_memory_summaries": True,
            "wechat_attachment_uses_sanitized_share_report": True,
        },
    }


def memory_snapshot(db: Path, chats: list[str], *, limit: int = 80) -> str:
    if not db.exists():
        return "(memory database not found)"
    try:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" for _ in chats)
            rows = conn.execute(
                f"""
                SELECT chat_name, category, title, body, created_at
                FROM memory_items
                WHERE chat_name IN ({placeholders})
                ORDER BY id DESC
                LIMIT ?
                """,
                [*chats, limit],
            ).fetchall()
    except sqlite3.Error as exc:
        return f"(memory read failed: {exc})"
    if not rows:
        return "(no memory rows found)"
    return "\n".join(
        f"- {row['chat_name']} / {row['category']} / {row['created_at']}: {compact(row['body'], 240)}"
        for row in rows
    )


def life_memo_snapshot(
    db: Path,
    chat: str | list[str],
    *,
    limit: int = 100,
    token_budget: int | None = None,
) -> str:
    if not db.exists():
        return "(memory database not found)"
    allowed = {
        "calendar",
        "grocery",
        "idea",
        "inbox",
        "language",
        "memo",
        "money",
        "request",
        "todo",
        "web_clip",
        "writing",
    }
    try:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            chats = [chat] if isinstance(chat, str) else list(dict.fromkeys(chat))
            placeholders = ",".join("?" for _ in chats)
            rows = conn.execute(
                f"""
                SELECT source_message_id, category, title, body, status, due_at,
                       created_at
                FROM memory_items
                WHERE chat_name IN ({placeholders})
                ORDER BY id DESC
                LIMIT ?
                """,
                (*chats, limit * 4),
            ).fetchall()
    except sqlite3.Error as exc:
        return f"(memory read failed: {exc})"
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        category = str(row["category"] or "")
        if category not in allowed:
            continue
        body = " ".join(str(row["body"] or "").split())
        if not body:
            continue
        key = (int(row["source_message_id"]), body)
        item = grouped.setdefault(
            key,
            {
                "body": body,
                "created_at": str(row["created_at"] or ""),
                "status": str(row["status"] or "open"),
                "due_at": str(row["due_at"] or ""),
                "categories": set(),
            },
        )
        item["categories"].add(category)
    items = sorted(grouped.values(), key=lambda item: item["created_at"], reverse=True)[:limit]
    if not items:
        return "(no organized items found)"
    lines: list[str] = []
    for item in items:
        metadata = ["/".join(sorted(item["categories"])), item["created_at"]]
        if item["status"] and item["status"] != "open":
            metadata.append(f"status={item['status']}")
        if item["due_at"]:
            metadata.append(f"explicit_due={item['due_at']}")
        line = f"- {' | '.join(metadata)}: {compact(item['body'], 360)}"
        candidate = "\n".join([*lines, line])
        if token_budget is not None and lines and estimate_tokens(candidate) > token_budget:
            break
        lines.append(line)
    coverage = (
        f"[Recent evidence coverage: {len(lines)} of {len(items)} newest distinct "
        "organized items; older continuity remains in the lifetime context.]"
    )
    return "\n".join([coverage, *lines])


def project_surface(*, limit: int = 48) -> str:
    roots = [Path("/home/lachlan/ProjectsLFS"), Path("/home/lachlan/DiskMech/Projects")]
    repos: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in ("*/.git", "*/*/.git"):
            for git_dir in root.glob(pattern):
                repos.append(git_dir.parent)
                if len(repos) >= limit:
                    break
            if len(repos) >= limit:
                break
    lines = []
    seen: set[str] = set()
    for repo in repos:
        if str(repo) in seen:
            continue
        seen.add(str(repo))
        remote = run_short(["git", "-C", str(repo), "config", "--get", "remote.origin.url"], timeout=1.5)
        readme = first_readme_line(repo)
        detail = "; ".join(item for item in [remote, readme] if item)
        lines.append(f"- {repo.name}: {detail}" if detail else f"- {repo.name}")
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else "(no local git project surface found)"


def repo_readme_snapshot(repo: Path) -> str:
    if not repo.exists():
        return f"({repo} not found)"
    lines = [f"Repo: {repo}"]
    remote = run_short(["git", "-C", str(repo), "config", "--get", "remote.origin.url"], timeout=1.5)
    if remote:
        lines.append(f"Remote: {remote}")
    for name in ("README.md", "readme.md", "AGENTS.md"):
        path = repo / name
        if path.exists():
            lines.append(f"{name} excerpt:\n{compact(path.read_text(encoding='utf-8', errors='replace'), 2000)}")
            break
    return "\n".join(lines)


def voidabyss_snapshot() -> str:
    candidates = []
    for root in (Path("/home/lachlan/ProjectsLFS"), Path("/home/lachlan/DiskMech/Projects")):
        if root.exists():
            candidates.extend(path for path in root.glob("*void*abyss*"))
            candidates.extend(path for path in root.glob("*Void*Abyss*"))
    if not candidates:
        return "(voidabyss folder not found by shallow scan)"
    return "\n\n".join(repo_readme_snapshot(path) for path in candidates[:4])


def identity_surface() -> str:
    candidates = [
        Path("/home/lachlan/ProjectsLFS/lazying.art"),
        Path("/home/lachlan/ProjectsLFS/lazying.art"),
        Path("/home/lachlan/ProjectsLFS/BLOG"),
        Path("/home/lachlan/ProjectsLFS/Documentations"),
        Path("/home/lachlan/ProjectsLFS/LazySkills"),
    ]
    lines = []
    for path in candidates:
        if not path.exists():
            continue
        lines.append(repo_readme_snapshot(path))
    return "\n\n".join(lines[:6]) if lines else "(no local lazying.art identity surface found)"


def public_profile_surface() -> str:
    lines = [
        "GitHub profile: https://github.com/lachlanchen",
        "Website: https://lazying.art",
        "Google Scholar: https://scholar.google.com/citations?user=Kdqr_AcAAAAJ&hl=en",
    ]
    github = run_short(["gh", "api", "users/lachlanchen"], timeout=4.0, limit=8000)
    if github:
        try:
            profile = json.loads(github)
        except json.JSONDecodeError:
            profile = {}
        if isinstance(profile, dict):
            safe_fields = {
                key: profile.get(key)
                for key in ("name", "company", "bio", "blog", "location", "public_repos")
                if profile.get(key) not in (None, "")
            }
            if safe_fields:
                lines.append("Current GitHub API profile: " + json.dumps(safe_fields, ensure_ascii=False))
    profile_repo = Path("/home/lachlan/ProjectsLFS/lachlanchen")
    if profile_repo.exists():
        lines.append(repo_readme_snapshot(profile_repo))
    return "\n".join(lines)


def first_readme_line(repo: Path) -> str:
    for name in ("README.md", "readme.md"):
        path = repo / name
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                clean = line.strip(" #\t")
                if clean:
                    return f"README: {compact(clean, 180)}"
        except OSError:
            return ""
    return ""


def run_short(command: list[str], *, timeout: float = 2.0, limit: int = 220) -> str:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return compact(proc.stdout, limit)


def sanitize_shareable_report(text: str) -> str:
    sanitized = str(text or "")
    replacements = [
        (str(PRIVATE), "<private-wechat-workspace>"),
        ("/home/lachlan/Documents/xwechat_files", "<wechat-profile>"),
    ]
    for raw, replacement in replacements:
        sanitized = sanitized.replace(raw, replacement)
    return sanitized


def send_daily_result(
    args: argparse.Namespace,
    report: Path,
    body: str,
    *,
    already_sent_files: set[str] | None = None,
    message_already_sent: bool = False,
) -> dict[str, Any]:
    with reserve_gui_send_priority("career_daily", args.send_chat):
        return send_daily_result_reserved(
            args,
            report,
            body,
            already_sent_files=already_sent_files,
            message_already_sent=message_already_sent,
        )


def send_daily_result_reserved(
    args: argparse.Namespace,
    report: Path,
    body: str,
    *,
    already_sent_files: set[str] | None = None,
    message_already_sent: bool = False,
) -> dict[str, Any]:
    summary = extract_daily_chat_summary(body)
    message = summary
    questions = extract_self_discovery_questions(body)
    if questions:
        question_lines = [f"{index}. {question}" for index, question in enumerate(questions, start=1)]
        message += "\n\n今天值得认真回答的三个问题：\n" + "\n".join(question_lines)
    status: dict[str, Any] = {
        "attempted": True,
        "complete": False,
        "message_sent": bool(message_already_sent),
        "file_sent": False,
        "files_sent": sorted(already_sent_files or set()),
        "errors": [],
    }
    if args.attach_report:
        companions = ensure_markdown_pdf_companions(report)
        status["pdf_companions"] = [str(path) for path in companions]
        status["pdf_required"] = True
        required_languages = {"zh", "en"}
        available_languages = {
            path.name.rsplit(".", 2)[-2]
            for path in companions
            if path.name.count(".") >= 2 and path.suffix.lower() == ".pdf"
        }
        missing_languages = sorted(required_languages - available_languages)
        if missing_languages:
            status["errors"].append(
                "pdf: required bilingual companions were not generated: " + ", ".join(missing_languages)
            )
            return status
        status["pdf_companion"] = str(companions[0])
        for report_file in companions:
            resolved_report = str(report_file.expanduser().resolve())
            if resolved_report in set(status["files_sent"]):
                continue
            try:
                send_daily_with_busy_retry(send_file, report_file, args.send_chat, args.send_targets)
                status["files_sent"].append(resolved_report)
            except Exception as exc:  # noqa: BLE001
                status["errors"].append(f"file {report_file}: {exc}")
                return status
        expected = {str(path.expanduser().resolve()) for path in companions}
        status["file_sent"] = expected.issubset(set(status["files_sent"]))
    if not status["message_sent"]:
        try:
            send_daily_with_busy_retry(send_message, message, args.send_chat, args.send_targets)
            status["message_sent"] = True
        except Exception as exc:  # noqa: BLE001 - preserve send blocker for operator.
            status["errors"].append(f"message: {exc}")
            return status
    status["complete"] = status["message_sent"] and (not args.attach_report or status["file_sent"])
    return status


@contextmanager
def reserve_gui_send_priority(owner: str, chat: str):
    token = f"{owner}-{os.getpid()}-{uuid.uuid4().hex[:10]}"
    ttl = max(60.0, float(os.environ.get("WECHAT_GUI_SEND_PRIORITY_TTL", "600")))
    payload = {
        "token": token,
        "owner": owner,
        "chat": chat,
        "pid": os.getpid(),
        "created_at": time.time(),
        "expires_at": time.time() + ttl,
    }
    GUI_SEND_PRIORITY.parent.mkdir(parents=True, exist_ok=True)
    temporary = GUI_SEND_PRIORITY.with_name(f"{GUI_SEND_PRIORITY.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(GUI_SEND_PRIORITY)
    try:
        yield
    finally:
        try:
            current = json.loads(GUI_SEND_PRIORITY.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        if current.get("token") == token:
            GUI_SEND_PRIORITY.unlink(missing_ok=True)


def send_daily_with_busy_retry(sender: Any, *args: Any, **kwargs: Any) -> None:
    attempts = max(1, int(os.environ.get("WECHAT_DAILY_SEND_ATTEMPTS", "6")))
    delay = max(0.0, float(os.environ.get("WECHAT_DAILY_SEND_RETRY_DELAY", "5")))
    for attempt in range(1, attempts + 1):
        try:
            sender(*args, **kwargs)
            return
        except Exception as exc:
            text = str(exc).lower()
            retryable = any(
                marker in text
                for marker in (
                    "wechat_send_busy",
                    "serialized gui sender is already sending",
                    "wechat_send_timeout",
                    "opened chat title guard failed",
                    "wechat_file_target_changed",
                )
            )
            if not retryable or attempt >= attempts:
                raise
            if delay:
                time.sleep(delay)


def extract_self_discovery_questions(text: str, *, limit: int = 3) -> list[str]:
    lines = str(text or "").splitlines()
    start = -1
    for index, line in enumerate(lines):
        lower = line.lower()
        if "self-discovery" in lower or "self discovery" in lower:
            start = index + 1
            break
        if "3 self" in lower and "question" in lower:
            start = index + 1
            break
        if "自我" in line and ("问题" in line or "提问" in line or "发现" in line):
            start = index + 1
            break
    if start < 0:
        for index, line in enumerate(lines):
            if re.match(r"^\s*(?:[-*]\s*)?(?:Q|Question|问题)\s*1\s*[:：.)、]", line, flags=re.I):
                start = index
                break
    if start < 0:
        return []
    questions: list[str] = []
    for raw_line in lines[start:]:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and questions:
            break
        if stripped.startswith("#"):
            continue
        clean = re.sub(r"^[-*]\s+", "", stripped)
        clean = re.sub(r"^\d+[.)、]\s+", "", clean)
        clean = clean.replace("**", "").strip()
        clean = re.sub(r"^(?:Q|Question|问题)\s*\d*\s*[:：]\s*", "", clean, flags=re.I).strip()
        if not clean:
            continue
        if "why it matters" in clean.lower() or clean.startswith("Why:") or clean.startswith("Why it matters:"):
            continue
        if "?" not in clean and "？" not in clean:
            continue
        questions.append(sanitize_shareable_report(compact(clean, 220)))
        if len(questions) >= limit:
            break
    return questions


def one_line_summary(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip(" #\t-*")
        if clean.lower() in {"today's thesis", "today’s thesis"}:
            continue
        if len(clean) > 2 and clean[0].isdigit() and clean[1] in {".", "、"}:
            continue
        if len(clean) >= 12:
            return compact(clean, 240)
    return "已生成今日方向、写作、职业和机会分析。"


def extract_daily_chat_summary(text: str) -> str:
    for line in str(text or "").splitlines():
        match = re.match(r"^\s*(?:[-*]\s*)?微信摘要\s*[:：]\s*(.+?)\s*$", line)
        if match:
            return sanitize_shareable_report(compact(match.group(1), 520))
    before_questions = re.split(
        r"(?im)^\s*#{1,6}\s+.*(?:self[- ]discovery|自我.*(?:问题|提问|发现)).*$",
        str(text or ""),
        maxsplit=1,
    )[0]
    for paragraph in re.split(r"\n\s*\n", before_questions):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        clean = re.sub(r"[*_`]", "", " ".join(lines)).strip()
        if len(clean) >= 40:
            return sanitize_shareable_report(compact(clean, 520))
    return sanitize_shareable_report(one_line_summary(text))


def compact(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[: max(0, limit - 1)] + ("…" if len(text) > limit else "")


if __name__ == "__main__":
    raise SystemExit(main())
