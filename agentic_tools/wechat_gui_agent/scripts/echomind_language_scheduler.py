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
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
if str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"))

import wechat_direct_chatops as direct  # noqa: E402
from wechat_agent_backend import run_agent_session  # noqa: E402
from wechat_task_worker import send_file  # noqa: E402

CONFIG = PRIVATE / "echomind-direct-chatops.local.json"
STATE = PRIVATE / "echomind-language-schedule.state.json"
DAILY_PDF_LOCK = PRIVATE / "echomind-language-daily-pdf.lock"
INTERVAL = 3 * 60 * 60
LOCAL_TZ = ZoneInfo("Asia/Hong_Kong")
QUIET_START = 20
QUIET_END = 8
DAILY_PDF_HOUR = 8
DAILY_PDF_RETRY_SECONDS = 30 * 60
SCHEDULER_POLL_SECONDS = 5 * 60
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
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def quiet_seconds() -> float:
    """Return remaining quiet-hours time, or zero during allowed hours."""
    now = datetime.now(LOCAL_TZ)
    if QUIET_END <= now.hour < QUIET_START:
        return 0.0
    wake = (now + timedelta(days=1)).replace(hour=QUIET_END, minute=0, second=0, microsecond=0)
    return max(60.0, (wake - now).total_seconds())


def daily_pdf_target_date(now: datetime | None = None) -> str:
    current = now or datetime.now(LOCAL_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=LOCAL_TZ)
    return (current.astimezone(LOCAL_TZ) - timedelta(days=1)).date().isoformat()


def daily_pdf_due(state: dict, *, now: datetime | None = None, force: bool = False) -> bool:
    """Return whether the previous-day PDF is due, with catch-up after 08:00."""
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
    result = run_agent_session(prompt, backend="codex", chat_name="EchoMind", role="daily_language_pdf", model="gpt-5.6-sol", reasoning_effort="low", sandbox="read-only", timeout_seconds=900, reuse=True, backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})})
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
    if deliver:
        send_file(pdf, config["chat_name"], CONFIG, target=config.get("send_target"))
    state["last_daily_pdf_date"] = yesterday
    state["last_daily_pdf"] = str(pdf)
    state.pop("last_daily_pdf_error", None)
    return {"date": yesterday, "pdf": str(pdf), "status": "sent_verified" if deliver else "generated"}


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
    context = direct.read_recent_history(config, 10**18, limit=int(config.get("history_limit", 24)))
    history = "\n".join(f"{item.get('sender_display', 'member')}: {direct.visible_message_text(item)}" for item in context[-24:])
    state = load_state()
    topic_index = int(state.get("topic_index", 0)) % len(TOPICS)
    topic = TOPICS[topic_index]
    previous = state.get("last_message", "")
    prompt = f"""You are EchoMind, a patient language teacher. This is an internal scheduled lesson, not a status check.
Today's required domain is: **{topic}**. Teach a broad, practical lesson in this domain rather than reacting to the group chat. Do not switch back to the previous domain merely because it appears in the history.

The recent chat is only a weak personalization signal. Use at most one short example from it when helpful; otherwise ignore it. Do not summarize the chat, make its latest message the topic, or keep dwelling on one recurring subject. Avoid repeating the previous lesson and vary the everyday domain from recent lessons.

Give a complete, balanced Chinese/English/Japanese mini-lesson. Do not make Chinese the main answer with token translations. For the same example, give:
- Chinese: natural sentence, pinyin, meaning, usage and grammar;
- English: natural sentence, IPA or clear pronunciation, meaning, usage and grammar;
- Japanese: natural sentence, kanji plus kana/furigana, romaji, pronunciation, meaning, usage and grammar.
Then add useful vocabulary, one cross-language comparison, one common mistake, and one short exercise. Give substantive detail in all three languages, while avoiding a rigid repetitive essay template. Write like a helpful friend. Do not say NO_REPLY.

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
        model="gpt-5.6-sol",
        reasoning_effort="low",
        sandbox="read-only",
        timeout_seconds=900,
        reuse=True,
        backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})},
    )
    message = str(result.get("message") or "").strip()
    if not message:
        raise RuntimeError("EchoMind language teacher returned no lesson")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    delivery: dict[str, object] = {"requested": deliver, "status": "internal_only"}
    if deliver:
        screenshot = direct.send_gui_message(config, message)
        if not screenshot or not Path(screenshot).is_file():
            raise RuntimeError(f"EchoMind lesson send was not verified: {screenshot or 'no screenshot'}")
        delivery = {"requested": True, "status": "sent_verified", "screenshot": screenshot}
    state.update({
        "last_run_at": now,
        "last_message": message,
        "interval_seconds": interval_seconds,
        "last_agent": result.get("backend", "codex"),
        "last_delivery": delivery,
        "topic": topic,
        "topic_index": (topic_index + 1) % len(TOPICS),
    })
    save_state(state)
    return {"ok": True, "chat": config["chat_name"], "sent_at": now, "message": message, "delivery": delivery, "daily_pdf": None}


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
        try:
            daily_pdf = run_daily_pdf_if_due(deliver=not args.no_send)
            if daily_pdf:
                print(json.dumps({"ok": True, "daily_pdf": daily_pdf}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "daily_pdf_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        quiet = quiet_seconds()
        if quiet:
            print(json.dumps({"ok": True, "status": "quiet_hours", "resume_in_seconds": int(quiet)}, ensure_ascii=False), flush=True)
            if not args.loop:
                return 0
            time.sleep(quiet)
            continue
        if args.loop:
            remaining = seconds_until_due(load_state(), interval)
            if remaining:
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
