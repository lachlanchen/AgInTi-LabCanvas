#!/usr/bin/env python3
"""Run EchoMind's independent language-learning schedule and deliver lessons."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
if str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"))

import wechat_direct_chatops as direct  # noqa: E402
from wechat_agent_backend import run_agent_session, select_agent_backend  # noqa: E402
from wechat_history_rag import (  # noqa: E402
    build_context_from_messages,
    deduplicate_history,
    lexical_terms,
    load_history,
    load_wechat_mirror_history,
)
from wechat_message_policy import (  # noqa: E402
    file_transport_identity,
    recorded_outbound_echo,
    recorded_outbound_file_identity,
)
from wechat_mirror import DEFAULT_DB as MIRROR_DB  # noqa: E402
from wechat_task_worker import send_file  # noqa: E402

CONFIG = PRIVATE / "echomind-direct-chatops.local.json"
STATE = PRIVATE / "echomind-language-schedule.state.json"
DAILY_PDF_LOCK = PRIVATE / "echomind-language-daily-pdf.lock"
MEMORY_DB = Path(
    os.environ.get("WECHAT_MEMORY_DB", str(PRIVATE / "wechat_memory.sqlite"))
)
GUI_SEND_PRIORITY = Path(
    os.environ.get(
        "WECHAT_GUI_SEND_PRIORITY_PATH",
        str(PRIVATE / "wechat_gui_send_priority.json"),
    )
)
INTERVAL = 6 * 60 * 60
LOCAL_TZ = ZoneInfo("Asia/Hong_Kong")
QUIET_START = 20
QUIET_END = 8
DAILY_PDF_HOUR = 6
DAILY_PDF_RETRY_SECONDS = 30 * 60
LESSON_RETRY_BASE_SECONDS = 30 * 60
LESSON_RETRY_MAX_SECONDS = 4 * 60 * 60
SCHEDULER_POLL_SECONDS = 5 * 60
PERIODIC_MAX_CHARS = int(os.environ.get("ECHOMIND_LANGUAGE_MAX_CHARS", "1100"))
PERIODIC_MODEL = os.environ.get("ECHOMIND_LANGUAGE_MODEL", "gpt-5.3-codex-spark")
PERIODIC_EFFORT = os.environ.get("ECHOMIND_LANGUAGE_EFFORT", "low")
PERIODIC_EDITOR_MODEL = os.environ.get("ECHOMIND_LANGUAGE_EDITOR_MODEL", "gpt-5.6-sol")
DAILY_PDF_MODEL = os.environ.get("ECHOMIND_DAILY_PDF_MODEL", "gpt-5.6-sol")
DAILY_PDF_EFFORT = os.environ.get("ECHOMIND_DAILY_PDF_EFFORT", "high")
DAILY_PDF_EDITOR_MODEL = os.environ.get(
    "ECHOMIND_DAILY_PDF_EDITOR_MODEL", DAILY_PDF_MODEL
)
DAILY_PDF_MIN_BODY_CHARS = int(
    os.environ.get("ECHOMIND_DAILY_PDF_MIN_BODY_CHARS", "5000")
)
DAILY_PDF_QUALITY_BACKEND = os.environ.get(
    "ECHOMIND_DAILY_PDF_QUALITY_BACKEND", ""
).strip()
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


def long_term_language_context(
    config: dict,
    topic: str,
    *,
    char_budget: int | None = None,
    model: str = "",
    role: str = "chat",
) -> str:
    """Compact every exact-chat row, then add topic-relevant raw excerpts."""

    chat = str(config.get("chat_name") or "EchoMind")
    query = " ".join(
        (
            topic,
            "language learning pronunciation grammar vocabulary correction preference difficulty",
            "Chinese English Japanese pinyin furigana romaji 中文 英文 日文 拼音 假名 语法 发音",
        )
    )
    payload = build_context_from_messages(
        exact_chat_language_history(config),
        query,
        char_budget=char_budget,
        model=model,
        role=role,
    )
    return str(payload.get("snapshot") or "")


def exact_chat_language_history(config: dict) -> list:
    """Return readable full EchoMind history from the strongest local ledger."""

    chat = str(config.get("chat_name") or "EchoMind")
    mirror_messages = load_wechat_mirror_history(
        MIRROR_DB,
        [chat],
        naive_timezone=LOCAL_TZ,
    )
    if mirror_messages:
        return mirror_messages
    return deduplicate_history(load_history(MEMORY_DB, [chat]))


def previous_day_language_messages(config: dict, report_date: str) -> list:
    """Select readable rows from the exact prior local calendar day."""

    try:
        target = datetime.fromisoformat(report_date).date()
    except ValueError:
        return []
    return [
        message
        for message in exact_chat_language_history(config)
        if message.created_at.astimezone(LOCAL_TZ).date() == target
    ]


def previous_day_language_context(
    config: dict,
    report_date: str,
    *,
    char_budget: int | None = None,
    model: str = "gpt-5.6-sol",
) -> str:
    """Select the actual previous local calendar day rather than a recent-row cap."""

    messages = previous_day_language_messages(config, report_date)
    payload = build_context_from_messages(
        messages,
        (
            "language lesson sentence correction pronunciation grammar vocabulary "
            "Chinese English Japanese pinyin furigana romaji 中文 英文 日文 拼音 假名 语法 发音"
        ),
        char_budget=char_budget,
        model=model,
        role="daily",
    )
    return str(payload.get("snapshot") or "")


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


@contextmanager
def reserve_gui_send_priority(owner: str, chat: str):
    """Yield the GUI lane from passive chat sync while a schedule delivers."""
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
    temporary = GUI_SEND_PRIORITY.with_name(
        f"{GUI_SEND_PRIORITY.name}.{os.getpid()}.tmp"
    )
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


def send_with_busy_retry(sender: Any, *args: Any, **kwargs: Any) -> Any:
    """Wait out an already-running sender after reserving future GUI cycles."""
    # A passive chat-sync cycle can already own the GUI lane when a scheduled
    # delivery becomes due.  Reserving priority prevents another cycle from
    # starting, while this bounded wait lets the current one finish.
    attempts = max(1, int(os.environ.get("WECHAT_DAILY_SEND_ATTEMPTS", "24")))
    delay = max(0.0, float(os.environ.get("WECHAT_DAILY_SEND_RETRY_DELAY", "5")))
    for attempt in range(1, attempts + 1):
        try:
            return sender(*args, **kwargs)
        except Exception as exc:
            message = str(exc).lower()
            retryable = any(
                marker in message
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
    raise RuntimeError("unreachable scheduled send retry state")


def send_scheduled_file(pdf: Path, config: dict) -> None:
    with reserve_gui_send_priority("echomind_daily_pdf", config["chat_name"]):
        send_with_busy_retry(
            send_file,
            pdf,
            config["chat_name"],
            CONFIG,
            target=config.get("send_target"),
        )


def send_scheduled_message(config: dict, message: str) -> str:
    with reserve_gui_send_priority("echomind_periodic_lesson", config["chat_name"]):
        return str(send_with_busy_retry(direct.send_gui_message, config, message) or "")


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


def pending_lesson_retry_seconds(
    pending: dict, *, now: datetime | None = None
) -> float:
    raw = str(pending.get("next_attempt_at") or "").strip()
    if not raw:
        return 0.0
    try:
        retry_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - current.astimezone(timezone.utc)).total_seconds())


def schedule_pending_lesson_retry(
    state: dict, pending: dict, *, now: datetime | None = None
) -> float:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    attempts = int(pending.get("delivery_attempts") or 0) + 1
    delay = min(
        LESSON_RETRY_MAX_SECONDS,
        LESSON_RETRY_BASE_SECONDS * (2 ** max(0, attempts - 1)),
    )
    pending["delivery_attempts"] = attempts
    pending["last_attempt_at"] = current.isoformat(timespec="seconds")
    pending["next_attempt_at"] = (
        current + timedelta(seconds=delay)
    ).isoformat(timespec="seconds")
    state["pending_lesson"] = pending
    state["last_delivery_error_at"] = current.isoformat(timespec="seconds")
    scheduler_heartbeat(
        state,
        "lesson_retry_wait",
        lesson_retry_in_seconds=int(delay),
    )
    return float(delay)


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


def daily_pdf_quality_backend(config: dict) -> str:
    """Use an explicitly configured specialist editor without changing the writer."""

    return str(
        config.get("daily_pdf_quality_backend")
        or DAILY_PDF_QUALITY_BACKEND
        or select_agent_backend(config)
    ).strip()


def daily_pdf_quality_model(config: dict) -> str:
    return str(config.get("daily_pdf_quality_model") or DAILY_PDF_EDITOR_MODEL).strip()


def daily_pdf_quality_effort(config: dict) -> str:
    return str(config.get("daily_pdf_quality_effort") or DAILY_PDF_EFFORT).strip()


def _source_lesson_anchors(body: str) -> dict[str, str]:
    """Extract the authored trilingual examples that a review must preserve."""

    text = " ".join(str(body or "").split())
    patterns = {
        "chinese": r"中文：(.*?)\s+拼音：",
        "pinyin": r"拼音：(.*?)\s+English:",
        "english": r"English:\s*(.*?)(?=\s+\([^()]*/[^()]*\)\s+日本語：|\s+日本語：)",
        "japanese": r"日本語：(.*?)\s+Romaji:",
        "romaji": r"Romaji:\s*(.*?)\s+对照：",
    }
    anchors: dict[str, str] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            anchors[name] = match.group(1).strip()
    return anchors


def _plain_anchor_text(value: str, *, japanese: bool = False) -> str:
    """Normalize source and LaTeX ruby notation for strict semantic anchoring."""

    text = re.sub(r"\\ruby\{([^{}]+)\}\{[^{}]+\}", r"\1", str(value or ""))
    if japanese:
        text = re.sub(
            r"([一-龯々〆ヵヶ]+)[（(][ぁ-ゖァ-ヺー]+[）)]",
            r"\1",
            text,
        )
    text = re.sub(r"\\textcolor\{[^{}]*\}", "", text)
    text = re.sub(r"\\(?:textbf|textit|emph)\{", "", text)
    return re.sub(
        r"[{}\s，。！？、,.!?;:：；'’\"“”「」『』（）()—–-]+",
        "",
        text,
    ).casefold()


def _source_anchor_issues(value: str, source_messages: list) -> list[str]:
    normalized_body = _plain_anchor_text(value)
    normalized_japanese_body = _plain_anchor_text(value, japanese=True)
    issues: list[str] = []
    for index, message in enumerate(source_messages, start=1):
        anchors = _source_lesson_anchors(str(message.body or ""))
        for name, anchor in anchors.items():
            normalized_anchor = _plain_anchor_text(
                anchor,
                japanese=name == "japanese",
            )
            haystack = normalized_japanese_body if name == "japanese" else normalized_body
            if len(normalized_anchor) >= 5 and normalized_anchor not in haystack:
                issues.append(f"source_{index}_missing_{name}_anchor")
    return issues


def daily_pdf_contract_issues(
    body: str,
    *,
    source_messages: list | None = None,
) -> list[str]:
    """Reject shallow, linguistically incomplete, or ungrounded tutorial bodies."""

    value = normalize_latex_body(body)
    issues: list[str] = []
    if len(value) < DAILY_PDF_MIN_BODY_CHARS:
        issues.append("too_shallow")
    required_concepts = {
        "chinese_section": ("Chinese", "中文"),
        "english_section": ("English", "英语", "英文"),
        "japanese_section": ("Japanese", "日本語", "日语", "日文"),
        "grammar": ("Grammar", "语法", "文法"),
        "vocabulary": ("Vocabulary", "词汇", "語彙"),
        "mistakes": ("Common mistake", "易错", "常见错误", "よくある間違"),
        "practice": ("Practice", "Exercise", "练习", "練習"),
        "romaji": ("Romaji", "ローマ字"),
    }
    for issue, markers in required_concepts.items():
        if not any(marker.casefold() in value.casefold() for marker in markers):
            issues.append(f"missing_{issue}")
    ruby_count = value.count("\\ruby{")
    if ruby_count == 0:
        issues.append("missing_japanese_ruby")
    elif source_messages and ruby_count < max(4, len(source_messages) * 2):
        issues.append("insufficient_japanese_ruby")
    if not re.search(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]", value, re.IGNORECASE):
        issues.append("missing_tone_marked_pinyin")
    if "\\begin{document}" in value or "\\documentclass" in value:
        issues.append("contains_full_document_wrapper")
    if re.search(
        r"(?:no recorded conversation|no source (?:messages|logs)|source logs contain no|"
        r"没有(?:聊天|来源|消息)记录|无(?:聊天|来源|消息)记录)",
        value,
        flags=re.IGNORECASE,
    ):
        issues.append("student_facing_source_process_note")
    if re.search(r"(?:起きき|行きき|飲みみ|食べべ|見み)ます", value) or re.search(
        r"\\ruby\{[^{}]*([ぁ-ん])\}\{[^{}]+\}\1",
        value,
    ):
        issues.append("suspected_japanese_inflection_typo")
    for match in re.finditer(
        r"(?:Romaji|ローマ字)\s*[:：]\s*([^\n]+)",
        value,
        flags=re.IGNORECASE,
    ):
        if re.search(r"[一-龯々ぁ-ゖァ-ヺ]", match.group(1)):
            issues.append("romaji_contains_japanese_script")
            break

    messages = list(source_messages or [])
    if messages:
        source_text = "\n".join(str(message.body or "") for message in messages)
        ignored = {
            "chinese",
            "english",
            "japanese",
            "grammar",
            "meaning",
            "natural",
            "example",
            "lesson",
            "拼音",
            "中文",
            "英文",
            "日文",
            "日语",
            "日本語",
            "语法",
            "词汇",
            "练习",
        }
        source_terms = {
            term
            for term in lexical_terms(source_text)
            if term not in ignored and (len(term) >= 5 or not term.isascii())
        }
        body_terms = lexical_terms(value)
        required_overlap = min(4, len(source_terms))
        if required_overlap and len(source_terms & body_terms) < required_overlap:
            issues.append("weak_previous_day_grounding")
        issues.extend(_source_anchor_issues(value, messages))
    return list(dict.fromkeys(issues))


def review_daily_pdf_body(
    draft: str,
    *,
    report_date: str,
    history: str,
    config: dict,
    source_messages: list,
) -> tuple[str, dict]:
    """Run a source-grounded language-editor pass before compilation."""

    prompt = f"""You are the final senior language editor for an EchoMind daily tutorial.
Rewrite and proofread the LaTeX body below. Return ONLY the revised LaTeX body, with no preamble or code fence.

Quality contract:
- The date is {report_date}. Base the lesson on the supplied previous-day evidence, not on a generic unrelated theme.
- Turn the strongest two to four source-derived expressions into a coherent lesson. Do not narrate the source-recovery process or mention missing logs in the student-facing PDF.
- Treat every labeled Chinese, Pinyin, English, Japanese, and Romaji source example as an immutable anchor: reproduce it exactly, adding LaTeX ruby around Japanese kanji without changing the sentence. Do not silently replace its tense, wording, reading, or register.
- Preserve useful depth but remove filler and repetitive explanations. Make the comparisons genuinely teach how Chinese, English, and Japanese express the same meanings.
- Check every Chinese sentence, full tone-marked pinyin line, English phrase, Japanese spelling/conjugation, furigana, and romaji character by character. Repair accidental duplicated kana and mismatched readings.
- Use at least four accurate \\ruby{{漢字}}{{かな}} expressions. Romaji lines must use Latin letters, never kana. Keep pinyin and romaji distinct and complete.
- Include explicit Grammar / 语法 / 文法 and Vocabulary / 词汇 / 語彙 sections, realistic common mistakes, and exercises with answers. Examples must be natural and semantically aligned, not literal translations.
- Keep the body substantial and study-ready (at least {DAILY_PDF_MIN_BODY_CHARS} meaningful LaTeX-body characters). Add depth through usage contrasts, register, collocations, pronunciation, and answer explanations, not filler. Do not add a document preamble, Markdown, private paths, model names, logs, or unsupported dialogue.

Previous-day evidence ({len(source_messages)} readable exact-chat messages):
{history}

Draft LaTeX body:
{draft}
"""
    result = run_agent_session(
        prompt,
        backend=daily_pdf_quality_backend(config),
        chat_name="EchoMind",
        role="daily_language_pdf_editor",
        model=daily_pdf_quality_model(config),
        reasoning_effort=daily_pdf_quality_effort(config),
        sandbox="read-only",
        timeout_seconds=900,
        reuse=False,
        backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})},
    )
    return normalize_latex_body(str(result.get("message") or "")), result


def repair_daily_pdf_body(
    body: str,
    *,
    report_date: str,
    history: str,
    config: dict,
    source_messages: list,
    issues: list[str],
) -> tuple[str, dict]:
    """Give a failed reviewed draft one bounded, issue-specific repair turn."""

    prompt = f"""Repair this EchoMind LaTeX tutorial body for {report_date}.
Return ONLY the complete repaired LaTeX body without a preamble or code fence.
The validator found: {', '.join(issues)}.

Use the exact previous-day evidence below. Every labeled Chinese, Pinyin, English, Japanese, and Romaji source example is immutable and must be reproduced exactly; only add accurate LaTeX ruby to Japanese kanji. Preserve good material, but make the report source-grounded, substantial (at least {DAILY_PDF_MIN_BODY_CHARS} meaningful characters), linguistically correct, and complete in Chinese, English, and Japanese. Include full tone-marked pinyin, at least four accurate Japanese \\ruby{{漢字}}{{かな}} expressions plus Latin-letter romaji, explicit grammar and vocabulary sections, realistic common mistakes, and exercises with explained answers. Do not discuss source logs or the editing process, and do not pad with repetition.

Previous-day evidence ({len(source_messages)} readable messages):
{history}

Body to repair:
{body}
"""
    result = run_agent_session(
        prompt,
        backend=daily_pdf_quality_backend(config),
        chat_name="EchoMind",
        role="daily_language_pdf_repair",
        model=daily_pdf_quality_model(config),
        reasoning_effort=daily_pdf_quality_effort(config),
        sandbox="read-only",
        timeout_seconds=900,
        reuse=False,
        backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})},
    )
    return normalize_latex_body(str(result.get("message") or "")), result


def daily_pdf_document(report_date: str, body: str) -> str:
    return r"""\documentclass[11pt]{article}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{ruby}
\usepackage{tipa}
\usepackage{amsmath}
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
            state["last_daily_pdf_attempt_date"] = yesterday
            state["last_daily_pdf_attempt_at"] = current.isoformat(timespec="seconds")
            save_state(state)
            already_delivered = daily_pdf_delivery_recorded(config, pending_pdf)
            if deliver and not already_delivered:
                send_scheduled_file(pending_pdf, config)
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
    source_messages = previous_day_language_messages(config, yesterday)
    history_payload = build_context_from_messages(
        source_messages,
        (
            "language lesson sentence correction pronunciation grammar vocabulary "
            "Chinese English Japanese pinyin furigana romaji 中文 英文 日文 拼音 假名 语法 发音"
        ),
        model=DAILY_PDF_MODEL,
        role="daily",
    )
    history = str(history_payload.get("snapshot") or "")
    longitudinal = long_term_language_context(
        config,
        "recurring learner needs and prior corrections",
        model=DAILY_PDF_MODEL,
        role="daily",
    )
    out_dir = ROOT / "output" / "wechat_gui_agent" / "echomind_daily" / yesterday
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_stem = f"echomind-language-review-{yesterday}"
    tex = out_dir / f"{artifact_stem}.tex"
    pdf = out_dir / f"{artifact_stem}.pdf"
    quality_path = out_dir / f"{artifact_stem}.quality.json"
    prompt = f"""Create a beautiful previous-day EchoMind language tutorial for {yesterday}.
Use the source messages and previous lessons below as evidence. Center the report on the strongest two to four expressions actually present rather than substituting an unrelated generic theme. Do not invent dialogue or claim content that is absent, and do not discuss source logs or source availability in the student-facing tutorial.
Return ONLY the LaTeX body, not a preamble. Use \\ruby{{漢字}}{{かな}} for Japanese furigana where useful.
Treat every labeled Chinese, Pinyin, English, Japanese, and Romaji source example as an immutable anchor. Reproduce it exactly; only convert Japanese inline readings into accurate LaTeX ruby. Do not silently change tense, wording, reading, or register.
The report must be at least {DAILY_PDF_MIN_BODY_CHARS} meaningful LaTeX-body characters and study-ready, with sections for Chinese, English, and Japanese. For every important example include natural wording, meaning, full tone-marked pinyin, pronunciation where it materially helps, Japanese kanji plus at least four accurate ruby expressions and Latin-letter romaji, explicit grammar and vocabulary sections, realistic common mistakes, and exercises with explained answers. Compare how the same idea is naturally expressed across the three languages. Proofread every inflection and reading character by character. Add depth through usage contrasts, register, collocations, pronunciation, and answer explanations rather than repetition. Include a short review and practice section. Do not write a shallow chat summary.
Use Unicode IPA directly. Do not use \\textipa, Markdown code fences, a document preamble, or any undeclared LaTeX command.

Previous-day EchoMind source material ({len(source_messages)} readable exact-chat messages):
{history}

Longitudinal learner signals from the complete exact-chat history (use only to
clarify recurring needs and terminology; do not replace the previous-day source):
{longitudinal}
"""
    result = run_agent_session(prompt, backend=select_agent_backend(config), chat_name="EchoMind", role="daily_language_pdf", model=DAILY_PDF_MODEL, reasoning_effort=DAILY_PDF_EFFORT, sandbox="read-only", timeout_seconds=900, reuse=False, backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})})
    draft = normalize_latex_body(str(result.get("message") or ""))
    if not draft:
        raise RuntimeError("daily EchoMind PDF agent returned no LaTeX body")
    (out_dir / f"{artifact_stem}.draft.texbody").write_text(draft, encoding="utf-8")
    body, editor_result = review_daily_pdf_body(
        draft,
        report_date=yesterday,
        history=history,
        config=config,
        source_messages=source_messages,
    )
    if not body:
        raise RuntimeError("daily EchoMind PDF editor returned no LaTeX body")
    (out_dir / f"{artifact_stem}.reviewed.texbody").write_text(body, encoding="utf-8")
    issues = daily_pdf_contract_issues(body, source_messages=source_messages)
    repair_result: dict[str, Any] = {}
    if issues:
        body, repair_result = repair_daily_pdf_body(
            body,
            report_date=yesterday,
            history=history,
            config=config,
            source_messages=source_messages,
            issues=issues,
        )
        (out_dir / f"{artifact_stem}.repaired.texbody").write_text(body, encoding="utf-8")
        issues = daily_pdf_contract_issues(body, source_messages=source_messages)
    quality = {
        "schema": "labcanvas.echomind.daily_pdf_quality.v1",
        "status": "content_rejected" if issues else "content_accepted_pending_compile",
        "report_date": yesterday,
        "source_message_count": len(source_messages),
        "source": (
            "wechat_mirror"
            if any(int(message.source_id) < 0 for message in source_messages)
            else "wechat_memory"
        ),
        "draft_backend": result.get("backend", ""),
        "draft_model": result.get("model", DAILY_PDF_MODEL),
        "editor_backend": editor_result.get("backend", ""),
        "editor_model": editor_result.get("model", DAILY_PDF_EDITOR_MODEL),
        "repair_backend": repair_result.get("backend", ""),
        "repair_model": repair_result.get("model", ""),
        "contract_issues": issues,
        "body_chars": len(body),
    }
    quality_path.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if issues:
        raise RuntimeError(
            "daily EchoMind PDF failed content quality contract: " + ",".join(issues)
        )
    tex.write_text(daily_pdf_document(yesterday, body), encoding="utf-8")
    pdf.unlink(missing_ok=True)
    engine = os.environ.get("ECHOMIND_LATEX_ENGINE", "xelatex")
    proc = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", tex.name], cwd=out_dir, capture_output=True, text=True, timeout=240, check=False)
    if proc.returncode != 0 or not pdf.is_file() or pdf.stat().st_size <= 0:
        diagnostics = "\n".join([proc.stdout or "", proc.stderr or ""]).strip()
        raise RuntimeError(f"daily EchoMind PDF compilation failed: {diagnostics[-1600:]}")
    quality["status"] = "accepted"
    quality["pdf_identity"] = file_transport_identity(pdf)
    quality_path.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    state["pending_daily_pdf"] = {
        "date": yesterday,
        "pdf": str(pdf),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    save_state(state)
    already_delivered = daily_pdf_delivery_recorded(config, pdf)
    if deliver and not already_delivered:
        send_scheduled_file(pdf, config)
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
        MIRROR_DB,
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
            "@LazyingArt 请上一节简洁但完整的中文、日文、英文语言小课。只选一个实用场景，"
            "只用一个三语对齐例句；给自然中文与完整声调拼音、自然英文、日文汉字及行内注音"
            "（如 予約（よやく））和罗马字。再用很短的篇幅说明一个三语语法差异、一个常见错误"
            "和一个带答案的小练习。三种语言和两种读音都不能遗漏，不要机械模板，不要重复最近课程。"
        ),
        "content": "",
        "create_time": now,
    }


def run_once(
    *,
    deliver: bool = True,
    interval_seconds: int = INTERVAL,
    force_pending_retry: bool = False,
) -> dict:
    config = direct.load_config(CONFIG)
    state = load_state()
    pending = state.get("pending_lesson")
    if isinstance(pending, dict) and str(pending.get("message") or "").strip():
        retry_seconds = pending_lesson_retry_seconds(pending)
        if deliver and retry_seconds > 0 and not force_pending_retry:
            scheduler_heartbeat(
                state,
                "lesson_retry_wait",
                lesson_retry_in_seconds=int(retry_seconds),
            )
            return {
                "ok": True,
                "status": "delivery_deferred",
                "retry_in_seconds": int(retry_seconds),
            }
        return deliver_pending_lesson(
            config,
            state,
            pending,
            deliver=deliver,
            interval_seconds=interval_seconds,
        )
    topic_index = int(state.get("topic_index", 0)) % len(TOPICS)
    topic = TOPICS[topic_index]
    history = long_term_language_context(
        config,
        topic,
        model=PERIODIC_MODEL,
        role="chat",
    )
    previous = state.get("last_message", "")
    prompt = f"""You are EchoMind, a patient multilingual language teacher. This is an internal scheduled lesson, not a status check.
Today's required domain is: **{topic}**. Teach a broad, practical lesson in this domain rather than reacting to the group chat. Do not switch back to the previous domain merely because it appears in the history.

The lifetime-memory hierarchy below covers the complete exact-chat history and ends with a few topic-relevant raw excerpts. It is only a weak personalization signal. Use at most one short example from it when helpful; otherwise ignore it. Do not summarize the chat, make its latest message the topic, revive an old request, or keep dwelling on one recurring subject. Avoid repeating the previous lesson and vary the everyday domain from recent lessons.

Write one concise but comprehensive lesson suitable for a single chat message, about 500-900 characters total. Use one practical situation and exactly one aligned core example. Include all of the following without omission:
- natural Chinese and full-sentence pinyin with tone marks;
- natural English, with pronunciation only for a genuinely difficult word;
- natural Japanese using WeChat-safe inline ruby/furigana such as 予約（よやく）, plus romaji.

Use these compact labels exactly once: 场景：, 中文：, 拼音：, English:, 日本語：, Romaji:, 对照：, 易错：, 练习：, 答案：. Keep the labeled prose natural. Finish with one very short three-language grammar contrast, one common mistake, and one tiny exercise with its answer. Keep the three languages semantically aligned. Do not use HTML ruby tags, a PDF, a report, a long essay, status logs, repeated greetings, or unrelated topic sections. Do not say NO_REPLY.

Bounded full-history personalization context:
{history}

Previous scheduled lesson (avoid repeating its topic):
{previous}
"""
    result = run_agent_session(
        prompt,
        backend=select_agent_backend(config),
        chat_name="EchoMind",
        role="scheduled_language_teacher",
        model=PERIODIC_MODEL,
        reasoning_effort=PERIODIC_EFFORT,
        sandbox="read-only",
        timeout_seconds=900,
        reuse=True,
        backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})},
    )
    message = normalize_periodic_lesson(str(result.get("message") or ""))
    if not message:
        raise RuntimeError("EchoMind language teacher returned no lesson")
    final_result = result
    issues = periodic_lesson_contract_issues(message)
    if issues:
        message, final_result = rewrite_periodic_lesson(
            message,
            topic=topic,
            config=config,
            issues=issues,
        )
    pending = {
        "message": message,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": final_result.get("backend", "codex"),
        "model": final_result.get("model", PERIODIC_MODEL),
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


def normalize_periodic_lesson(message: str) -> str:
    """Remove harmless model wrappers without clipping lesson content."""
    value = str(message or "").strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1]).strip()
    return value


def periodic_lesson_contract_issues(
    message: str,
    *,
    max_chars: int = PERIODIC_MAX_CHARS,
) -> list[str]:
    """Return compactness/completeness failures before any live delivery."""
    value = normalize_periodic_lesson(message)
    issues: list[str] = []
    if not value:
        return ["empty"]
    if len(value) > max(500, int(max_chars)):
        issues.append("too_long")
    required_labels = (
        "场景：",
        "中文：",
        "拼音：",
        "English:",
        "日本語：",
        "Romaji:",
        "对照：",
        "易错：",
        "练习：",
        "答案：",
    )
    issues.extend(
        f"missing_{label.rstrip(':：')}"
        for label in required_labels
        if label not in value
    )
    if not re.search(r"[\u4e00-\u9fff]+（[\u3041-\u309fー]+）", value):
        issues.append("missing_inline_furigana")
    if not re.search(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]", value, re.IGNORECASE):
        issues.append("missing_tone_marked_pinyin")
    return issues


def rewrite_periodic_lesson(
    draft: str,
    *,
    topic: str,
    config: dict,
    issues: list[str],
) -> tuple[str, dict]:
    """Use a bounded editor turn instead of truncating an incomplete lesson."""
    prompt = f"""Rewrite the EchoMind lesson below into one complete WeChat message.

Topic: {topic}
Contract failures: {', '.join(issues)}

Hard requirements:
- 500-900 characters, never more than {PERIODIC_MAX_CHARS} characters;
- exactly one semantically aligned example in Chinese, English, and Japanese;
- full tone-marked pinyin for the Chinese sentence;
- Japanese kanji with inline furigana such as 予約（よやく）, followed by romaji;
- one concise three-language grammar contrast, one common mistake, and one tiny exercise with its answer;
- use each label exactly once and in this order: 场景：, 中文：, 拼音：, English:, 日本語：, Romaji:, 对照：, 易错：, 练习：, 答案：;
- return only the finished lesson. Do not explain the edit and do not use code fences.

Draft:
{draft}
"""
    result = run_agent_session(
        prompt,
        backend=select_agent_backend(config),
        chat_name="EchoMind",
        role="scheduled_language_editor",
        model=PERIODIC_EDITOR_MODEL,
        reasoning_effort="low",
        sandbox="read-only",
        timeout_seconds=900,
        reuse=True,
        backend_config={"agent_fallbacks": config.get("agent_fallbacks", {})},
    )
    message = normalize_periodic_lesson(str(result.get("message") or ""))
    remaining = periodic_lesson_contract_issues(message)
    if remaining:
        raise RuntimeError(
            "EchoMind language editor did not satisfy delivery contract: "
            + ",".join(remaining)
        )
    return message, result


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
                screenshot = send_scheduled_message(config, message)
                if not screenshot or not Path(screenshot).is_file():
                    raise RuntimeError(f"EchoMind lesson send was not verified: {screenshot or 'no screenshot'}")
                delivery = {"requested": True, "status": "sent_verified", "screenshot": screenshot}
        except Exception as exc:
            state["last_delivery_error"] = f"{type(exc).__name__}: {exc}"
            schedule_pending_lesson_retry(state, pending)
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
        MIRROR_DB,
        str(config.get("chat_name") or "EchoMind"),
        str(pending.get("message") or ""),
        source_epoch=source_epoch,
        window_seconds=6 * 60 * 60,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run immediately once.")
    parser.add_argument("--loop", action="store_true", help="Resume the durable schedule, then run every six hours.")
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
                            "status": "waiting_for_interval",
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
            result = run_once(
                deliver=not args.no_send,
                interval_seconds=interval,
                force_pending_retry=bool(args.once),
            )
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if result.get("status") == "delivery_deferred" and args.loop:
                time.sleep(
                    min(
                        max(5.0, float(result.get("retry_in_seconds") or 0)),
                        SCHEDULER_POLL_SECONDS,
                    )
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
