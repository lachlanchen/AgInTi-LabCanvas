#!/usr/bin/env python3
"""Daily private career, writing, and money strategy agent for WeChat."""

from __future__ import annotations

import argparse
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

from wechat_agent_backend import run_agent_session, select_agent_backend
from wechat_task_worker import ensure_markdown_pdf_companions, send_file, send_message


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
OUTPUT = ROOT / "output" / "wechat_strategy"
DEFAULT_MEMORY_DB = PRIVATE / "wechat_memory.sqlite"
DEFAULT_SEND_TARGETS = PRIVATE / "wechat_send_targets.local.json"
DEFAULT_CHATS = ["写作 外语 挣钱", "lachlanchan"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "loop"], nargs="?", default="run")
    parser.add_argument("--chat", action="append", default=[], help="Memory chat to include. Repeatable.")
    parser.add_argument("--send-chat", default="lachlanchan", help="WeChat chat/DM to receive the daily note.")
    parser.add_argument("--send", action="store_true", help="Send the concise result and shareable report to WeChat.")
    parser.add_argument("--attach-report", action="store_true", help="Attach the shareable Markdown report when sending.")
    parser.add_argument("--memory-db", type=Path, default=DEFAULT_MEMORY_DB)
    parser.add_argument("--send-targets", type=Path, default=DEFAULT_SEND_TARGETS)
    parser.add_argument("--morning-time", default="08:30", help="Loop run time in HH:MM local time.")
    parser.add_argument("--loop-sleep", type=float, default=60.0)
    parser.add_argument("--model", default=os.environ.get("WECHAT_CAREER_AGENT_MODEL", "gpt-5.5"))
    parser.add_argument("--reasoning-effort", default=os.environ.get("WECHAT_CAREER_AGENT_EFFORT", "xhigh"))
    parser.add_argument("--timeout-seconds", type=int, default=int(os.environ.get("WECHAT_CAREER_AGENT_TIMEOUT", "900")))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.action == "loop":
        return loop_daily(args)
    payload = run_daily(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload.get("summary") or payload.get("status") or "done")
    return 0 if payload.get("ok") else 1


def loop_daily(args: argparse.Namespace) -> int:
    last_run_key = ""
    while True:
        now = datetime.now()
        run_at = next_run_time(now, args.morning_time)
        if run_at.date() == now.date() and now >= run_at and last_run_key != run_at.strftime("%Y-%m-%d"):
            payload = run_daily(args)
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
            last_run_key = run_at.strftime("%Y-%m-%d")
        sleep_until = next_run_time(datetime.now(), args.morning_time)
        delay = min(max(5.0, (sleep_until - datetime.now()).total_seconds()), max(5.0, args.loop_sleep))
        time.sleep(delay)


def next_run_time(now: datetime, hhmm: str) -> datetime:
    try:
        hour, minute = [int(part) for part in hhmm.split(":", 1)]
    except (ValueError, TypeError):
        hour, minute = 8, 30
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now > candidate + timedelta(minutes=5):
        candidate += timedelta(days=1)
    return candidate


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
    if not result.get("ok") or not body:
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
    if args.send:
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
    return {
        "ok": bool(result.get("ok")) and bool(body),
        "status": "done",
        "run_id": run_id,
        "trace_dir": str(trace_dir),
        "manifest": str(trace_dir / "manifest.json"),
        "private_report": str(private_report),
        "share_report": str(share_report),
        "send": send_status,
        "summary": one_line_summary(body),
        "agent": {
            "backend": result.get("backend", "codex"),
            "thread_id": result.get("thread_id"),
            "resumed": result.get("resumed"),
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
        },
    }


def collect_evidence(chats: list[str], memory_db: Path) -> dict[str, str]:
    return {
        "memory_snapshot": memory_snapshot(memory_db, chats),
        "project_surface": project_surface(),
        "lazyinvestment_snapshot": repo_readme_snapshot(Path("/home/lachlan/ProjectsLFS/LazyInvestment")),
        "voidabyss_snapshot": voidabyss_snapshot(),
        "identity_surface": identity_surface(),
    }


def build_prompt(evidence: dict[str, str]) -> str:
    return f"""You are the daily career, writing, and opportunity strategy agent for Lachlan.

Goal: give one useful morning note for wealth, freedom, and happiness.

Use the evidence below:
- WeChat memory summary, especially writing/language/money and lachlanchan.
- Local repo/project surface.
- LazyInvestment/LazyEdit/LabCanvas/LazySkills/LALACHAN/voidabyss evidence when present.
- Current public web/GitHub/company research only when needed. Verify current facts before recommending companies or stocks.

Important:
- This is educational analysis, not financial advice. For investments, provide a watchlist/rationale/risk framework, not certainty.
- Do not expose raw private chat logs. Summarize patterns and evidence.
- Do not claim the user's fate is fixed. Discuss recurring strengths and likely compounding lanes.
- Prefer concrete experiments and repeatable actions over broad life advice.

Answer in Markdown with these sections:
1. Today’s thesis
2. What to write
3. Talent/profile evidence
4. Money and career opportunities
5. Investment/watchlist notes, with risks
6. The single primary bet
7. 90-day execution plan
8. Today’s 3 actions
9. Today’s 3 self-discovery questions

For section 9, write exactly three questions. They must be specific to the
evidence from today's run, not generic journaling prompts. Each question should
be answerable in 10-15 minutes, a little uncomfortable but kind, and capable of
changing tomorrow's plan if answered honestly. Format them as `Q1: ...?`,
`Q2: ...?`, and `Q3: ...?`, each followed by one short `Why it matters: ...`
sentence.

WeChat memory snapshot:
{evidence.get('memory_snapshot', '')}

Local project surface:
{evidence.get('project_surface', '')}

LazyInvestment snapshot:
{evidence.get('lazyinvestment_snapshot', '')}

voidabyss snapshot:
{evidence.get('voidabyss_snapshot', '')}

lazying.art/local web identity hints:
{evidence.get('identity_surface', '')}
"""


def write_evidence_artifacts(trace_dir: Path, evidence: dict[str, str]) -> None:
    filenames = {
        "memory_snapshot": "memory_snapshot.md",
        "project_surface": "project_surface.md",
        "lazyinvestment_snapshot": "lazyinvestment_snapshot.md",
        "voidabyss_snapshot": "voidabyss_snapshot.md",
        "identity_surface": "identity_surface.md",
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
                "project_surface": str(trace_dir / "project_surface.md"),
                "lazyinvestment_snapshot": str(trace_dir / "lazyinvestment_snapshot.md"),
                "voidabyss_snapshot": str(trace_dir / "voidabyss_snapshot.md"),
                "identity_surface": str(trace_dir / "identity_surface.md"),
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


def run_short(command: list[str], *, timeout: float = 2.0) -> str:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return compact(proc.stdout, 220)


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
    summary = one_line_summary(body)
    message = "今日方向简报已完成。\n" + summary
    questions = extract_self_discovery_questions(body)
    if questions:
        question_lines = [f"{index}. {question}" for index, question in enumerate(questions, start=1)]
        message += "\n\n今日3个自我发现问题:\n" + "\n".join(question_lines)
    status: dict[str, Any] = {"attempted": True, "message_sent": False, "file_sent": False, "files_sent": [], "errors": []}
    try:
        send_message(message, args.send_chat, args.send_targets)
        status["message_sent"] = True
    except Exception as exc:  # noqa: BLE001 - preserve send blocker for operator.
        status["errors"].append(f"message: {exc}")
    if args.attach_report:
        report_files = [report]
        companions = ensure_markdown_pdf_companions(report)
        if companions:
            status["pdf_companions"] = [str(path) for path in companions]
            status["pdf_companion"] = str(companions[0])
            report_files.extend(companions)
        for report_file in report_files:
            try:
                send_file(report_file, args.send_chat, args.send_targets)
                status["files_sent"].append(str(report_file))
            except Exception as exc:  # noqa: BLE001
                status["errors"].append(f"file {report_file}: {exc}")
        status["file_sent"] = len(status["files_sent"]) == len(report_files)
    return status


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


def compact(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[: max(0, limit - 1)] + ("…" if len(text) > limit else "")


if __name__ == "__main__":
    raise SystemExit(main())
