#!/usr/bin/env python3
"""Run EchoMind's independent language-learning schedule and deliver lessons."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
if str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"))

import wechat_direct_chatops as direct  # noqa: E402
from wechat_agent_backend import run_agent_session  # noqa: E402
from wechat_message_policy import (  # noqa: E402
    file_transport_identity,
    recorded_outbound_echo,
    recorded_outbound_file_identity,
)
from wechat_mirror import DEFAULT_DB  # noqa: E402
from wechat_task_worker import send_file  # noqa: E402

CONFIG = PRIVATE / "echomind-direct-chatops.local.json"
STATE = PRIVATE / "echomind-language-schedule.state.json"
DAILY_PDF_LOCK = PRIVATE / "echomind-language-daily-pdf.lock"
INTERVAL = 3 * 60 * 60
LOCAL_TZ = ZoneInfo("Asia/Hong_Kong")
QUIET_START = 20
QUIET_END = 8
DAILY_PDF_HOUR = 6
DAILY_PDF_RETRY_SECONDS = 30 * 60
SCHEDULER_POLL_SECONDS = 5 * 60
PERIODIC_MAX_CHARS = int(os.environ.get("ECHOMIND_LANGUAGE_MAX_CHARS", "1400"))
PERIODIC_MODEL = os.environ.get("ECHOMIND_LANGUAGE_MODEL", "gpt-5.3-codex-spark")
PERIODIC_EFFORT = os.environ.get("ECHOMIND_LANGUAGE_EFFORT", "low")
TOPICS = (
    "food, cooking, and ordering at a restaurant",
    "clothes, shopping, sizes, and prices",
    "hotels, reservations, and travel arrangements",
    "directions, public transport, and commuting",
    "school, study, and asking for clarification",
    "work, meetings, deadlines, and polite requests",
    "home life, chores, and daily routines",
    "weather, seasons, and outdoor plans",
    "health, appointments, and describing symptoms",
    "social plans, invitations, and making arrangements",
    "feelings, opinions, and supportive conversation",
    "pronunciation, listening, and a useful sound contrast",
    "grammar in practical conversation",
    "writing a clear short message or email",
    "politeness, register, and cultural nuance",
)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{STATE.name}.",
        suffix=".tmp",
        dir=STATE.parent,
        delete=False,
    ) as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(STATE)


def scheduler_heartbeat(state: dict, phase: str, **fields: object) -> None:
    state["last_loop_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["scheduler_phase"] = phase
    state.update(fields)
    save_state(state)


def seconds_until_due(state: dict, interval_seconds: int, *, now: datetime | None = None) -> float:
    """Return the remaining interval without duplicating a lesson after restart."""
    raw = str(state.get("last_run_at") or "").strip()
    if not raw:
        return 0.0
    try:
        last_run = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    due_at = last_run.astimezone(timezone.utc) + timedelta(seconds=interval_seconds)
    return max(0.0, (due_at - current.astimezone(timezone.utc)).total_seconds())


def quiet_seconds(*, now: datetime | None = None) -> float:
    """Return the next quiet-hours wake without sleeping past the 06:00 PDF."""
    now = now or datetime.now(LOCAL_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=LOCAL_TZ)
    now = now.astimezone(LOCAL_TZ)
    if QUIET_END <= now.hour < QUIET_START:
        return 0.0
    if now.hour >= QUIET_START:
        wake = (now + timedelta(days=1)).replace(
            hour=DAILY_PDF_HOUR,
            minute=0,
            second=0,
            microsecond=0,
        )
    elif now.hour < DAILY_PDF_HOUR:
        wake = now.replace(hour=DAILY_PDF_HOUR, minute=0, second=0, microsecond=0)
    else:
        wake = now.replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
        return min(SCHEDULER_POLL_SECONDS, max(60.0, (wake - now).total_seconds()))
    return max(60.0, (wake - now).total_seconds())


def daily_pdf_target_date(now: datetime | None = None) -> str:
    current = now or datetime.now(LOCAL_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    return (current.astimezone(LOCAL_TZ) - timedelta(days=1)).date().isoformat()


def daily_pdf_due(state: dict, *, now: datetime | None = None, force: bool = False) -> bool:
    """Return whether the previous-day PDF is due, with catch-up after 06:00."""
    current = now or datetime.now(LOCAL_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    current = current.astimezone(LOCAL_TZ)
    target_date = daily_pdf_target_date(current)
    if state.get("last_daily_pdf_date") == target_date:
        return False
    if not force and current.hour < DAILY_PDF_HOUR:
        return False
    if force:
        return True
    if state.get("last_daily_pdf_attempt_date") != target_date:
        return True
    try:
        attempted = datetime.fromisoformat(str(state.get("last_daily_pdf_attempt_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return True
    if attempted.tzinfo is None:
        attempted = attempted.replace(tzinfo=LOCAL_TZ)
    return (current - attempted.astimezone(LOCAL_TZ)).total_seconds() >= DAILY_PDF_RETRY_SECONDS


def normalize_latex_body(raw: str) -> str:
    """Remove common Markdown/full-document wrappers from an agent LaTeX body."""
    body = raw.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    if "\\begin{document}" in body and "\\end{document}" in body:
        body = body.split("\\begin{document}", 1)[1].rsplit("\\end{document}", 1)[0].strip()
    return body


def daily_pdf_document(report_date: str, body: str) -> str:
    return r"""\documentclass[11pt]{article}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{ruby}
\usepackage{tipa}
\usepackage[a4paper,margin=19mm]{geometry}
\usepackage{xcolor}
\usepackage{hyperref}
\setmainfont{Noto Serif}
\setCJKmainfont{Noto Serif CJK SC}
\title{EchoMind Daily Language Review}
\date{%s}
\begin{document}
\maketitle
\small
%s
\end{document}
""" % (report_date, body)


def run_daily_pdf(
    config: dict,
    state: dict,
    *,
    now: datetime | None = None,
    force: bool = False,
    deliver: bool = True,
) -> dict | None:
    """Create and deliver one previous-day EchoMind teaching PDF independently."""
    current = now or datetime.now(LOCAL_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    current = current.astimezone(LOCAL_TZ)
    if not daily_pdf_due(state, now=current, force=force):
        return None
    yesterday = daily_pdf_target_date(current)
    pending = state.get("pending_daily_pdf")
    if isinstance(pending, dict) and str(pending.get("date") or "") == yesterday:
        pending_pdf = Path(str(pending.get("pdf") or "")).expanduser()
        if pending_pdf.is_file() and pending_pdf.stat().st_size > 0:
            already_delivered = daily_pdf_delivery_recorded(config, pending_pdf)
            if deliver and not already_delivered:
                send_file(pending_pdf, config["chat_name"], CONFIG, target=config.get("send_target"))
            state["last_daily_pdf_date"] = yesterday
            state["last_daily_pdf"] = str(pending_pdf)
            state["last_daily_pdf_delivery"] = {
                "date": yesterday,
                "pdf": str(pending_pdf),
                "status": (
                    "sent_verified_recovered"
                    if already_delivered
                    else "sent_verified"
                    if deliver
                    else "generated"
                ),
            }
            state.pop("pending_daily_pdf", None)
            state.pop("last_daily_pdf_error", None)
            save_state(state)
            return dict(state["last_daily_pdf_delivery"])
    state["last_daily_pdf_attempt_date"] = yesterday
    state["last_daily_pdf_attempt_at"] = current.isoformat(timespec="seconds")
    save_state(state)
    context = direct.read_recent_history(config, 10**18, limit=240)
    history = "\n".join(f"{item.get('sender_display', 'member')}: {direct.visible_message_text(item)}" for item in context)
    prompt = f"""Create a beautiful previous-day EchoMind language tutorial for {yesterday}.
Use the source messages and previous lessons below as evidence, but do not invent dialogue or claim content that is absent.
Return ONLY the LaTeX body, not a preamble. Use \\ruby{{漢字}}{{かな}} for Japanese furigana where useful.
The report must be substantial and study-ready, with sections for Chinese, English, and Japanese. For every important example include natural wording, meaning, pinyin, pronunciation, Japanese kanji plus furigana and romaji, grammar, vocabulary, common mistakes, and exercises. Compare how the same idea is expressed across the three languages. Include a short review and practice section. Do not write a shallow chat summary.
Use Unicode IPA directly. Do not use \\textipa, Markdown code fences, a document preamble, or any undeclared LaTeX command.

Previous-day EchoMind source material:
{history}
"""
    result = run_agent_session(prompt, backend="codex", chat_name="EchoMind", role="daily_language_pdf", model="gpt-5.6-sol", reasoning_effort="medium", sandbox="read-only", timeout_seconds=900, reuse=True, backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})})
    body = normalize_latex_body(str(result.get("message") or ""))
    if not body:
        raise RuntimeError("daily EchoMind PDF agent returned no LaTeX body")
    out_dir = ROOT / "output" / "wechat_gui_agent" / "echomind_daily" / yesterday
    out_dir.mkdir(parents=True, exist_ok=True)
    tex = out_dir / f"echomind-language-review-{yesterday}.tex"
    pdf = out_dir / f"echomind-language-review-{yesterday}.pdf"
    tex.write_text(daily_pdf_document(yesterday, body), encoding="utf-8")
    pdf.unlink(missing_ok=True)
    engine = os.environ.get("ECHOMIND_LATEX_ENGINE", "xelatex")
    proc = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", tex.name], cwd=out_dir, capture_output=True, text=True, timeout=240, check=False)
    if proc.returncode != 0 or not pdf.is_file() or pdf.stat().st_size <= 0:
        diagnostics = "\n".join([proc.stdout or "", proc.stderr or ""]).strip()
        raise RuntimeError(f"daily EchoMind PDF compilation failed: {diagnostics[-1600:]}")
    state["pending_daily_pdf"] = {
        "date": yesterday,
        "pdf": str(pdf),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_state(state)
    already_delivered = daily_pdf_delivery_recorded(config, pdf)
    if deliver and not already_delivered:
        send_file(pdf, config["chat_name"], CONFIG, target=config.get("send_target"))
    state["last_daily_pdf_date"] = yesterday
    state["last_daily_pdf"] = str(pdf)
    state.pop("pending_daily_pdf", None)
    state.pop("last_daily_pdf_error", None)
    return {
        "date": yesterday,
        "pdf": str(pdf),
        "status": (
            "sent_verified_recovered"
            if already_delivered
            else "sent_verified"
            if deliver
            else "generated"
        ),
    }


def daily_pdf_delivery_recorded(config: dict, pdf: Path) -> bool:
    return recorded_outbound_file_identity(
        DEFAULT_DB,
        str(config.get("chat_name") or "EchoMind"),
        file_transport_identity(pdf),
        window_seconds=48 * 60 * 60,
    )


def run_daily_pdf_if_due(*, deliver: bool = True, force: bool = False, now: datetime | None = None) -> dict | None:
    """Run and persist the independent daily PDF transaction."""
    DAILY_PDF_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with DAILY_PDF_LOCK.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        config = direct.load_config(CONFIG)
        state = load_state()
        try:
            result = run_daily_pdf(config, state, now=now, force=force, deliver=deliver)
        except Exception as exc:
            state["last_daily_pdf_error"] = f"{type(exc).__name__}: {exc}"
            state["last_daily_pdf_error_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_state(state)
            raise
        if result:
            state["last_daily_pdf_delivery"] = result
            save_state(state)
        return result


def build_row() -> dict:
    now = int(time.time())
    return {
        "local_id": 0,
        "server_id": f"scheduled-echomind-{now}",
        "sender": "echomind-language-scheduler",
        "sender_display": "EchoMind language scheduler",
        "sender_userid": "echomind-language-scheduler",
        "is_self": False,
        "is_bot": False,
        "kind": "text",
        "text": (
            "@LazyingArt 请根据 EchoMind 最近的完整聊天上下文，上一节实用的中文、日文、英文语言学习小课。"
            "主题可以广泛选择：日常交流、工作、研究、写作、旅行、文化、情绪表达、发音、语法，"
            "以及群成员反复出现的错误。选择一个群里真实出现过、或最适合当前学习方向的表达；不要重复最近课程。"
            "完整给出自然改写、中文含义、英文表达、日文表达、日文假名、发音提示、语法重点、"
            "常见误用和一个简短练习。像正常朋友聊天，内容有实质，不要机械模板。"
        ),
        "content": "",
        "create_time": now,
    }


def run_once(*, deliver: bool = True, interval_seconds: int = INTERVAL) -> dict:
    config = direct.load_config(CONFIG)
    state = load_state()
    pending = state.get("pending_lesson")
    if isinstance(pending, dict) and str(pending.get("message") or "").strip():
        return deliver_pending_lesson(
            config,
            state,
            pending,
            deliver=deliver,
            interval_seconds=interval_seconds,
        )
    context = direct.read_recent_history(config, 10**18, limit=int(config.get("history_limit", 24)))
    history = "\n".join(f"{item.get('sender_display', 'member')}: {direct.visible_message_text(item)}" for item in context[-24:])
    topic_index = int(state.get("topic_index", 0)) % len(TOPICS)
    topic = TOPICS[topic_index]
    previous = state.get("last_message", "")
    prompt = f"""You are EchoMind, a patient language teacher. This is an internal scheduled lesson, not a status check.
Today's required domain is: **{topic}**. Teach a broad, practical lesson in this domain rather than reacting to the group chat. Do not switch back to the previous domain merely because it appears in the history.

The recent chat is only a weak personalization signal. Use at most one short example from it when helpful; otherwise ignore it. Do not summarize the chat, make its latest message the topic, or keep dwelling on one recurring subject. Avoid repeating the previous lesson and vary the everyday domain from recent lessons.

Write one compact, useful lesson suitable for a single chat message, about 650-1100 characters total. Use one practical situation and no more than three core example sentences. Balance Chinese, English, and Japanese for the same examples: include concise pinyin, English pronunciation only where useful, Japanese kanji/kana plus romaji, one grammar contrast, one common mistake, and one tiny exercise. Do not produce a report, PDF, long essay, status log, repeated greeting, or multiple topic sections. Write like a helpful language teacher, not a rigid template. Do not say NO_REPLY.

Recent EchoMind history:
{history}

Previous scheduled lesson (avoid repeating its topic):
{previous}
"""
    result = run_agent_session(
        prompt,
        backend="codex",
        chat_name="EchoMind",
        role="scheduled_language_teacher",
        model=PERIODIC_MODEL,
        reasoning_effort=PERIODIC_EFFORT,
        sandbox="read-only",
        timeout_seconds=900,
        reuse=True,
        backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})},
    )
    message = compact_periodic_lesson(str(result.get("message") or ""))
    if not message:
        raise RuntimeError("EchoMind language teacher returned no lesson")
    pending = {
        "message": message,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": result.get("backend", "codex"),
        "model": result.get("model", PERIODIC_MODEL),
        "topic": topic,
        "next_topic_index": (topic_index + 1) % len(TOPICS),
    }
    state["pending_lesson"] = pending
    scheduler_heartbeat(state, "lesson_pending_delivery")
    return deliver_pending_lesson(
        config,
        state,
        pending,
        deliver=deliver,
        interval_seconds=interval_seconds,
    )


def compact_periodic_lesson(message: str, *, max_chars: int = PERIODIC_MAX_CHARS) -> str:
    """Keep the periodic lesson useful without allowing a chat flood."""
    value = str(message or "").strip()
    limit = max(500, int(max_chars))
    if len(value) <= limit:
        return value
    clipped = value[:limit]
    boundary = max(
        clipped.rfind("\n\n"),
        clipped.rfind("。"),
        clipped.rfind("."),
        clipped.rfind("！"),
        clipped.rfind("？"),
    )
    if boundary >= int(limit * 0.65):
        clipped = clipped[: boundary + 1]
    return clipped.rstrip()


def deliver_pending_lesson(
    config: dict,
    state: dict,
    pending: dict,
    *,
    deliver: bool,
    interval_seconds: int,
) -> dict:
    message = str(pending.get("message") or "").strip()
    if not message:
        raise RuntimeError("pending EchoMind lesson has no message")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    delivery: dict[str, object] = {"requested": deliver, "status": "internal_only"}
    if deliver:
        state["last_delivery_attempt_at"] = now
        scheduler_heartbeat(state, "lesson_delivery_attempt")
        try:
            if periodic_lesson_delivery_recorded(config, pending):
                delivery = {"requested": True, "status": "sent_verified_recovered"}
            else:
                screenshot = direct.send_gui_message(config, message)
                if not screenshot or not Path(screenshot).is_file():
                    raise RuntimeError(f"EchoMind lesson send was not verified: {screenshot or 'no screenshot'}")
                delivery = {"requested": True, "status": "sent_verified", "screenshot": screenshot}
        except Exception as exc:
            state["last_delivery_error"] = f"{type(exc).__name__}: {exc}"
            scheduler_heartbeat(state, "lesson_delivery_deferred")
            raise
    state.update({
        "last_run_at": now,
        "last_message": message,
        "interval_seconds": interval_seconds,
        "last_agent": pending.get("agent", "codex"),
        "last_model": pending.get("model", PERIODIC_MODEL),
        "last_delivery": delivery,
        "topic": pending.get("topic", ""),
        "topic_index": int(pending.get("next_topic_index") or 0) % len(TOPICS),
        "scheduler_phase": "waiting",
    })
    state.pop("pending_lesson", None)
    state.pop("last_delivery_error", None)
    save_state(state)
    return {"ok": True, "chat": config["chat_name"], "sent_at": now, "message": message, "delivery": delivery, "daily_pdf": None}


def periodic_lesson_delivery_recorded(config: dict, pending: dict) -> bool:
    generated_at = str(pending.get("generated_at") or "").strip()
    try:
        source_epoch = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        source_epoch = 0
    return recorded_outbound_echo(
        DEFAULT_DB,
        str(config.get("chat_name") or "EchoMind"),
        str(pending.get("message") or ""),
        source_epoch=source_epoch,
        window_seconds=6 * 60 * 60,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run immediately once.")
    parser.add_argument("--loop", action="store_true", help="Resume the durable schedule, then run every three hours.")
    parser.add_argument("--daily-pdf-now", action="store_true", help="Generate and deliver the due previous-day PDF now.")
    parser.add_argument("--no-send", action="store_true", help="Keep the lesson internal instead of sending it to EchoMind.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=int(os.environ.get("ECHOMIND_LANGUAGE_INTERVAL_SECONDS", str(INTERVAL))),
    )
    args = parser.parse_args()
    interval = max(300, args.interval_seconds)
    if not args.once and not args.loop and not args.daily_pdf_now:
        parser.error("use --once, --loop, or --daily-pdf-now")
    if args.daily_pdf_now:
        try:
            result = run_daily_pdf_if_due(deliver=not args.no_send, force=True)
            print(json.dumps({"ok": True, "daily_pdf": result, "already_done": result is None}, ensure_ascii=False), flush=True)
            return 0
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
            return 1
    state = load_state()
    if state.get("interval_seconds") != interval:
        state["interval_seconds"] = interval
        save_state(state)
    while True:
        state = load_state()
        scheduler_heartbeat(state, "loop")
        try:
            daily_pdf = run_daily_pdf_if_due(deliver=not args.no_send)
            if daily_pdf:
                print(json.dumps({"ok": True, "daily_pdf": daily_pdf}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "daily_pdf_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        quiet = quiet_seconds()
        if quiet:
            scheduler_heartbeat(load_state(), "quiet_hours", resume_in_seconds=int(quiet))
            print(json.dumps({"ok": True, "status": "quiet_hours", "resume_in_seconds": int(quiet)}, ensure_ascii=False), flush=True)
            if not args.loop:
                return 0
            time.sleep(quiet)
            continue
        if args.loop:
            remaining = seconds_until_due(load_state(), interval)
            if remaining:
                scheduler_heartbeat(load_state(), "waiting", resume_in_seconds=int(remaining))
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "status": "waiting_for_three_hour_interval",
                            "interval_seconds": interval,
                            "resume_in_seconds": int(remaining),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                time.sleep(min(remaining, SCHEDULER_POLL_SECONDS))
                continue
        try:
            print(
                json.dumps(
                    run_once(deliver=not args.no_send, interval_seconds=interval),
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
            if not args.loop:
                return 1
            time.sleep(min(interval, 300))
        if not args.loop:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
