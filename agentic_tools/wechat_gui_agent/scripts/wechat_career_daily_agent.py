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
import time
from typing import Any
import uuid

from wechat_agent_backend import run_agent_session, select_agent_backend
from wechat_task_worker import (
    ensure_markdown_pdf_companions,
    render_markdown_pdf,
    send_file,
    send_message,
)


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
OUTPUT = ROOT / "output" / "wechat_strategy"
DEFAULT_MEMORY_DB = PRIVATE / "wechat_memory.sqlite"
DEFAULT_SEND_TARGETS = PRIVATE / "wechat_send_targets.local.json"
GUI_SEND_PRIORITY = Path(os.environ.get("WECHAT_GUI_SEND_PRIORITY_PATH", str(PRIVATE / "wechat_gui_send_priority.json")))
DEFAULT_CHATS = ["写作 外语 挣钱", "lachlanchan", "鏈接", "🍓我的设备"]
DEFAULT_ORGANIZER_CHAT = "写作 外语 挣钱"
ORGANIZER_STATE = PRIVATE / "output" / "career_daily" / "organizer-delivery.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "loop", "organize"], nargs="?", default="run")
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
    while True:
        now = datetime.now()
        run_at = scheduled_run_time(now, args.morning_time)
        run_key = run_at.strftime("%Y-%m-%d")
        if now >= run_at:
            if last_run_key != run_key:
                if career_delivery_complete_for_date(run_key, require_send=bool(args.send)):
                    last_run_key = run_key
                else:
                    payload = run_daily(args)
                    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
                    last_run_key = run_key
            if bool(getattr(args, "organize_report", False)) and organizer_done_key != run_key:
                payload = run_organizer(args)
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
                if payload.get("ok"):
                    organizer_done_key = run_key
        sleep_until = next_run_time(datetime.now(), args.morning_time)
        delay = min(max(5.0, (sleep_until - datetime.now()).total_seconds()), max(5.0, args.loop_sleep))
        time.sleep(delay)


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
    evidence = collect_evidence(chats, args.memory_db)
    prompt = build_prompt(evidence)
    (trace_dir / "agent_prompt.md").write_text(prompt, encoding="utf-8")
    write_evidence_artifacts(trace_dir, evidence)
    result = run_agent_session(
        prompt,
        backend=select_agent_backend({}),
        chat_name="career-daily-agent",
        role="career_daily",
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
        "summary": extract_daily_chat_summary(body),
        "agent": {
            "backend": result.get("backend", "codex"),
            "thread_id": result.get("thread_id"),
            "resumed": result.get("resumed"),
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


def run_organizer(args: argparse.Namespace, *, force: bool = False) -> dict[str, Any]:
    chat = str(getattr(args, "organize_chat", DEFAULT_ORGANIZER_CHAT) or DEFAULT_ORGANIZER_CHAT)
    stamp = datetime.now().strftime("%Y-%m-%d")
    state_path = organizer_state_path()
    state = read_json_file(state_path)
    report = OUTPUT / f"{stamp}-recent-items.zh.md"
    pdf = OUTPUT / f"{stamp}-recent-items.zh.pdf"

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
        and report.is_file()
        and pdf.is_file()
        and pdf.stat().st_size > 0
    )
    result: dict[str, Any] = {}
    if not generated:
        snapshot = life_memo_snapshot(getattr(args, "memory_db", DEFAULT_MEMORY_DB), chat)
        prompt = build_organizer_prompt(chat, snapshot)
        result = run_agent_session(
            prompt,
            backend=select_agent_backend({}),
            chat_name=chat,
            role="daily_organizer",
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            sandbox="read-only",
            timeout_seconds=args.timeout_seconds,
            workdir=ROOT,
            reuse=True,
        )
        body = strip_markdown_fence(str(result.get("message") or "").strip())
        if not result.get("ok") or not body:
            return {
                "ok": False,
                "status": "agent_failed",
                "chat": chat,
                "agent": sanitize_agent_result(result),
            }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        report.write_text(body.rstrip() + "\n", encoding="utf-8")
        rendered = render_markdown_pdf(report, pdf)
        if rendered is None or not pdf.is_file() or pdf.stat().st_size <= 0:
            return {
                "ok": False,
                "status": "pdf_failed",
                "chat": chat,
                "report": str(report),
            }
        state = {
            "schema": "labcanvas.wechat.daily_organizer.v1",
            "date": stamp,
            "chat": chat,
            "status": "ready",
            "report": str(report),
            "pdf": str(pdf),
            "agent": {
                "backend": result.get("backend"),
                "thread_id": result.get("thread_id"),
                "resumed": result.get("resumed"),
                "model": args.model,
                "reasoning_effort": args.reasoning_effort,
            },
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
        write_json_file(state_path, state)

    send_status: dict[str, Any] = {"attempted": False, "complete": not bool(args.send)}
    if args.send:
        send_status = send_organizer_pdf(args, pdf, chat)
    state.update(
        {
            "date": stamp,
            "chat": chat,
            "report": str(report),
            "pdf": str(pdf),
            "status": "delivered" if send_status.get("complete") else "delivery_failed",
            "send": send_status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
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
    }


def organizer_delivery_matches(state: dict[str, Any], stamp: str, chat: str, pdf: Path) -> bool:
    return bool(
        state.get("date") == stamp
        and state.get("chat") == chat
        and state.get("status") == "delivered"
        and (state.get("send") or {}).get("complete")
        and pdf.is_file()
        and pdf.stat().st_size > 0
    )


def organizer_state_path() -> Path:
    if PRIVATE == ROOT / "agentic_tools" / "wechat_gui_agent" / ".private":
        return ORGANIZER_STATE
    return PRIVATE / "output" / "career_daily" / "organizer-delivery.json"


def send_organizer_pdf(args: argparse.Namespace, pdf: Path, chat: str) -> dict[str, Any]:
    status: dict[str, Any] = {
        "attempted": True,
        "complete": False,
        "file_sent": False,
        "files_sent": [],
        "errors": [],
    }
    with reserve_gui_send_priority("daily_organizer", chat):
        try:
            send_daily_with_busy_retry(send_file, pdf, chat, args.send_targets)
        except Exception as exc:  # noqa: BLE001
            status["errors"].append(f"file {pdf}: {exc}")
            return status
    status["file_sent"] = True
    status["files_sent"] = [str(pdf)]
    status["complete"] = True
    return status


def build_organizer_prompt(chat: str, snapshot: str) -> str:
    return f"""You organize one private WeChat group's recent notes into a useful daily memo.

Exact chat: {chat}

Return only polished Chinese Markdown for a mobile-readable PDF. Do not mention
the automation, database, classifiers, local paths, model, or prompt.

Use only the evidence below. Deduplicate repeated classifications of the same
message. Do not invent dates, deadlines, completion states, groceries, calendar
events, or commitments. A question or request is not automatically a real todo.

Organize naturally rather than forcing empty sections. Distinguish:
- concrete open actions for today or this week;
- later ideas and experiments;
- writing, language, career, and money signals;
- factual reminders and explicit dates, only when present;
- items that need clarification before they become actions.

Be selective and substantive. Preserve important technical names and quoted
intent. Merge related fragments, explain the connection briefly, and end with
at most three high-leverage next actions. Do not add generic productivity advice.

Recent exact-chat evidence:
{snapshot}
"""


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


def collect_evidence(chats: list[str], memory_db: Path) -> dict[str, str]:
    return {
        "memory_snapshot": memory_snapshot(memory_db, chats),
        "life_memo_snapshot": life_memo_snapshot(memory_db, "写作 外语 挣钱"),
        "project_surface": project_surface(),
        "lazyinvestment_snapshot": repo_readme_snapshot(Path("/home/lachlan/ProjectsLFS/LazyInvestment")),
        "voidabyss_snapshot": voidabyss_snapshot(),
        "identity_surface": identity_surface(),
        "public_profile_surface": public_profile_surface(),
    }


def build_prompt(evidence: dict[str, str]) -> str:
    return f"""You are the daily career, writing, and opportunity strategy agent for Lachlan.

Goal: give one deep, useful morning note for wealth, freedom, and happiness.
The user prefers substance over format. Do not write a shallow checklist.

Use the evidence below:
- WeChat memory summary, especially writing/language/money and lachlanchan.
- The deduplicated life memo from the writing/language/money group.
- Local repo/project surface.
- LazyInvestment/LazyEdit/LabCanvas/LazySkills/LALACHAN/voidabyss evidence when present.
- Public profile evidence from GitHub, lazying.art, and the exact Google Scholar
  profile. Verify current facts before recommending companies or stocks and do
  not merge similarly named authors.

Important:
- Write the main report in Chinese. English terms are fine when they are the natural name of a concept/company/product.
- Use the strongest evidence. If a point is not supported by the evidence, do not include it.
- Do not pad. Do not produce generic self-help, generic startup advice, or generic investment themes.
- Avoid a rigid mechanical template. Use natural memo-style headings only where they help the argument.
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


def write_evidence_artifacts(trace_dir: Path, evidence: dict[str, str]) -> None:
    filenames = {
        "memory_snapshot": "memory_snapshot.md",
        "life_memo_snapshot": "life_memo_snapshot.md",
        "project_surface": "project_surface.md",
        "lazyinvestment_snapshot": "lazyinvestment_snapshot.md",
        "voidabyss_snapshot": "voidabyss_snapshot.md",
        "identity_surface": "identity_surface.md",
        "public_profile_surface": "public_profile_surface.md",
    }
    for key, filename in filenames.items():
        (trace_dir / filename).write_text(str(evidence.get(key) or "").rstrip() + "\n", encoding="utf-8")


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


def life_memo_snapshot(db: Path, chat: str, *, limit: int = 100) -> str:
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
            rows = conn.execute(
                """
                SELECT source_message_id, category, title, body, status, due_at,
                       created_at
                FROM memory_items
                WHERE chat_name = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat, limit * 4),
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
    lines = []
    for item in items:
        metadata = ["/".join(sorted(item["categories"])), item["created_at"]]
        if item["status"] and item["status"] != "open":
            metadata.append(f"status={item['status']}")
        if item["due_at"]:
            metadata.append(f"explicit_due={item['due_at']}")
        lines.append(f"- {' | '.join(metadata)}: {compact(item['body'], 360)}")
    return "\n".join(lines)


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


def send_daily_result(args: argparse.Namespace, report: Path, body: str) -> dict[str, Any]:
    with reserve_gui_send_priority("career_daily", args.send_chat):
        return send_daily_result_reserved(args, report, body)


def send_daily_result_reserved(args: argparse.Namespace, report: Path, body: str) -> dict[str, Any]:
    summary = extract_daily_chat_summary(body)
    message = summary
    questions = extract_self_discovery_questions(body)
    if questions:
        question_lines = [f"{index}. {question}" for index, question in enumerate(questions, start=1)]
        message += "\n\n今天值得认真回答的三个问题：\n" + "\n".join(question_lines)
    status: dict[str, Any] = {
        "attempted": True,
        "complete": False,
        "message_sent": False,
        "file_sent": False,
        "files_sent": [],
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
            try:
                send_daily_with_busy_retry(send_file, report_file, args.send_chat, args.send_targets)
                status["files_sent"].append(str(report_file))
            except Exception as exc:  # noqa: BLE001
                status["errors"].append(f"file {report_file}: {exc}")
                return status
        status["file_sent"] = len(status["files_sent"]) == len(companions)
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


def send_daily_with_busy_retry(sender: Any, *args: Any) -> None:
    attempts = max(1, int(os.environ.get("WECHAT_DAILY_SEND_ATTEMPTS", "6")))
    delay = max(0.0, float(os.environ.get("WECHAT_DAILY_SEND_RETRY_DELAY", "5")))
    for attempt in range(1, attempts + 1):
        try:
            sender(*args)
            return
        except Exception as exc:
            text = str(exc).lower()
            retryable = "wechat_send_busy" in text or "serialized gui sender is already sending" in text
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
