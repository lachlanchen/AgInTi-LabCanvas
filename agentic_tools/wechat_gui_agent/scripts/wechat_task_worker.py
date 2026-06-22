#!/usr/bin/env python3
"""Worker-side helper for slower WeChat chatops tasks."""

from __future__ import annotations

import argparse
from datetime import datetime
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
import urllib.error
import urllib.request

from wechat_codex_sessions import run_codex_session
from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
LAZYEDIT_PUBLISH_SKILL = ROOT / "agentic_tools" / "wechat_gui_agent" / "skills" / "lazyedit-publish-workflow" / "SKILL.md"
LAZYEDIT_ROOT = Path(os.environ.get("LAZYEDIT_ROOT", "/home/lachlan/DiskMech/Projects/lazyedit"))
LAZYEDIT_API_URL = os.environ.get("LAZYEDIT_API_URL", "http://127.0.0.1:18787").rstrip("/")
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"
DEFAULT_SEND_TARGETS = PRIVATE / "wechat_send_targets.local.json"
EFFORT_ORDER = ["low", "medium", "high", "xhigh"]
CLAIMED_STATUS = "in_progress"
SEND_DEFERRED_LOCKED_STATUS = "send_deferred_locked"
SEND_RETRYING_STATUS = "send_retrying"
DEFAULT_STALE_IN_PROGRESS_SECONDS = 60 * 60
DEFAULT_DEFERRED_SEND_BACKOFF_SECONDS = 5 * 60
DEFAULT_WORKER_MODEL = "gpt-5.5"
EFFORT_TIMEOUT_SECONDS = {
    "low": 120,
    "medium": 300,
    "high": 600,
    "xhigh": 1200,
}
OUTBOUND_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
    ".pdf",
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".zip",
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".webm",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".ogg",
    ".amr",
    ".opus",
    ".step",
    ".stp",
    ".stl",
    ".scad",
    ".kicad_pcb",
    ".kicad_sch",
    ".blend",
}
DEFAULT_AUTO_SEND_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".pdf",
    ".zip",
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".mp3",
    ".m4a",
    ".wav",
}
DEFAULT_MAX_OUTBOUND_BYTES = 100 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--chat", default="wechat-chat")
    parser.add_argument("--enqueue", help="Add a task to the private queue and exit.")
    parser.add_argument("--once", action="store_true", help="Process one pending task.")
    parser.add_argument("--loop", action="store_true", help="Continuously process pending tasks.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--send", action="store_true", help="Send worker result back to WeChat.")
    parser.add_argument("--send-targets", type=Path, default=DEFAULT_SEND_TARGETS, help="Ignored JSON mapping chat names to GUI target specs.")
    parser.add_argument("--resend", help="Send an existing task result by task id without rerunning the worker.")
    parser.add_argument("--flush-deferred", action="store_true", help="Try one deferred locked send without running new worker tasks.")
    args = parser.parse_args()

    if args.enqueue:
        task = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "chat": args.chat,
            "request": args.enqueue,
            "status": "pending",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        append_jsonl(args.queue, task)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.resend:
        return resend_task_result(args.queue, args.resend, args.chat, send_targets=args.send_targets)

    if args.flush_deferred:
        return 0 if flush_one_deferred_send(args.queue, args.chat, send_targets=args.send_targets, log_idle=True) else 1

    if args.once or args.loop:
        while True:
            processed = process_one(args.queue, args.chat, send=args.send, send_targets=args.send_targets, log_idle=not args.loop)
            if not args.loop:
                return 0
            if not processed:
                import time

                time.sleep(args.poll_seconds)
        return 0
    raise SystemExit("Use --enqueue, --once, --loop, --resend, or --flush-deferred")


def resend_task_result(queue: Path, task_id: str, chat: str, *, send_targets: Path = DEFAULT_SEND_TARGETS) -> int:
    task = find_task(queue, task_id)
    if not task:
        raise SystemExit(f"No task found with id {task_id}")
    result = task.get("result")
    if not isinstance(result, dict):
        raise SystemExit(f"Task {task_id} has no stored result to resend")
    target_chat = str(task.get("chat") or chat)
    errors = send_result_with_retries(result, target_chat, send_targets, task=task)
    apply_send_outcome(task, result, errors)
    task["resent_at"] = datetime.now().isoformat(timespec="seconds")
    rewrite_task(queue, task)
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 1 if errors else 0


def process_one(queue: Path, chat: str, *, send: bool, send_targets: Path = DEFAULT_SEND_TARGETS, log_idle: bool = True) -> bool:
    task = claim_next_pending(queue)
    if not task:
        if send and os.environ.get("WECHAT_WORKER_AUTO_FLUSH_DEFERRED", "1") == "1":
            return flush_one_deferred_send(queue, chat, send_targets=send_targets, log_idle=log_idle)
        if log_idle:
            print(json.dumps({"status": "no-pending-task"}, ensure_ascii=False))
        return False
    log_worker_event("claimed", task)
    try:
        result_text = run_worker_codex(task)
        result = parse_worker_result(result_text)
        result = prepare_result_files(result, result_text)
    except Exception as exc:
        result_text = f"Worker failed before completion: {type(exc).__name__}: {str(exc)[:800]}"
        result = {"message": result_text, "confirmation": "", "files": [], "raw": result_text}
        task["worker_error"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
    target_chat = str(task.get("chat") or chat)
    send_errors = send_result_with_retries(result, target_chat, send_targets, task=task) if send else []
    if result.get("skipped_files"):
        task["skipped_files"] = result["skipped_files"]
    if task.get("worker_error"):
        task["status"] = "worker_failed"
        if send_errors:
            task["send_errors"] = send_errors
    elif send_errors:
        apply_send_outcome(task, result, send_errors)
    else:
        apply_send_outcome(task, result, [])
    task["completed_at"] = datetime.now().isoformat(timespec="seconds")
    task["result"] = result
    rewrite_task(queue, task)
    if send_errors and send_errors_indicate_wechat_locked(send_errors):
        event_status = "send-deferred-locked"
    elif send_errors:
        event_status = "send-failed"
    elif result["confirmation"]:
        event_status = "waiting-confirmation-sent" if send else "waiting-confirmation"
    else:
        event_status = "done-sent" if send else "done"
    record_event(
        chat_name=task.get("chat", chat),
        action="worker_task",
        direction="outbound",
        message=result["confirmation"] or result["message"] or result_text,
        status=event_status,
        db_path=DEFAULT_DB,
        metadata=task,
    )
    print(json.dumps(task, ensure_ascii=False, indent=2))
    log_worker_event(task["status"], task)
    return True


def flush_one_deferred_send(
    queue: Path,
    chat: str,
    *,
    send_targets: Path = DEFAULT_SEND_TARGETS,
    log_idle: bool = True,
) -> bool:
    task = claim_next_deferred_send(queue)
    if not task:
        if log_idle:
            print(json.dumps({"status": "no-deferred-send-ready"}, ensure_ascii=False))
        return False
    log_worker_event("claimed_deferred_send", task)
    result = task.get("result")
    if not isinstance(result, dict):
        task["status"] = "send_failed"
        task["send_errors"] = ["stored result missing or invalid; cannot flush deferred send"]
    else:
        target_chat = str(task.get("chat") or chat)
        errors = send_result_with_retries(result, target_chat, send_targets, task=task)
        apply_send_outcome(task, result, errors)
    task["resent_at"] = datetime.now().isoformat(timespec="seconds")
    rewrite_task(queue, task)
    record_event(
        chat_name=task.get("chat", chat),
        action="worker_task_resend",
        direction="outbound",
        message=(result or {}).get("confirmation") or (result or {}).get("message") or "",
        status=str(task.get("status") or ""),
        db_path=DEFAULT_DB,
        metadata=task,
    )
    print(json.dumps(task, ensure_ascii=False, indent=2))
    log_worker_event(str(task.get("status") or "unknown"), task)
    return True


def apply_send_outcome(task: dict[str, Any], result: dict[str, Any], errors: list[str]) -> None:
    if errors:
        task["send_errors"] = errors
        task["last_send_attempt_at"] = datetime.now().isoformat(timespec="seconds")
        if send_errors_indicate_wechat_locked(errors):
            task["status"] = SEND_DEFERRED_LOCKED_STATUS
            task["send_deferred_reason"] = "wechat_locked"
        else:
            task["status"] = "send_failed"
        return
    task["status"] = "waiting_confirmation" if result.get("confirmation") else "done"
    task.pop("send_errors", None)
    task.pop("send_deferred_reason", None)


def send_errors_indicate_wechat_locked(errors: list[str]) -> bool:
    text = "\n".join(str(error) for error in errors).lower()
    return "wechat_locked" in text or "weixin for linux is locked" in text or "unlock on phone" in text


def send_result_with_retries(
    result: dict[str, Any],
    target_chat: str,
    send_targets: Path,
    *,
    task: dict[str, Any] | None = None,
) -> list[str]:
    attempts = max(1, int(os.environ.get("WECHAT_WORKER_SEND_RETRIES", "2")))
    delay = max(0.0, float(os.environ.get("WECHAT_WORKER_SEND_RETRY_DELAY", "1.5")))
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            if task is None:
                send_result_once(result, target_chat, send_targets)
            else:
                send_result_once(result, target_chat, send_targets, task=task)
            return []
        except Exception as exc:
            errors.append(f"attempt {attempt}: {exc}")
            if send_errors_indicate_wechat_locked(errors):
                break
            if attempt < attempts and delay:
                import time

                time.sleep(delay)
    return errors


def send_result_once(
    result: dict[str, Any],
    target_chat: str,
    send_targets: Path,
    *,
    task: dict[str, Any] | None = None,
    target: dict[str, Any] | None = None,
) -> None:
    target = target if target is not None else guarded_send_target(target_chat, send_targets, task=task)
    files_to_send, files_to_note = partition_result_files_for_wechat(result.get("files") or [])
    if task is not None and files_to_note:
        task["unsent_saved_files"] = [str(path) for path in files_to_note]
    message = message_with_saved_file_note(str(result.get("message") or ""), files_to_note)
    if message:
        send_message(message, target_chat, send_targets, target=target)
    if result["confirmation"]:
        send_message(result["confirmation"], target_chat, send_targets, target=target)
    file_errors = []
    for file_path in files_to_send:
        try:
            send_file(file_path, target_chat, send_targets, target=target)
        except Exception as exc:
            error = {"path": str(file_path), "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
            file_errors.append(error)
            if os.environ.get("WECHAT_WORKER_REQUIRE_FILE_SEND", "0") == "1":
                raise
    if file_errors and task is not None:
        task.setdefault("file_send_errors", []).extend(file_errors)


def partition_result_files_for_wechat(files: list[str]) -> tuple[list[Path], list[Path]]:
    if os.environ.get("WECHAT_WORKER_SEND_FILES", "1") != "1":
        return [], [Path(path) for path in files]
    raw_suffixes = os.environ.get("WECHAT_WORKER_AUTO_SEND_SUFFIXES")
    suffixes = DEFAULT_AUTO_SEND_SUFFIXES
    if raw_suffixes:
        suffixes = {item.strip().lower() for item in raw_suffixes.split(",") if item.strip()}
    send: list[Path] = []
    note: list[Path] = []
    for raw in files:
        path = Path(raw)
        if path.suffix.lower() in suffixes:
            send.append(path)
        else:
            note.append(path)
    return send, note


def message_with_saved_file_note(message: str, files: list[Path]) -> str:
    if not files:
        return message
    lines = [message.strip()] if message.strip() else []
    lines.append("Saved files:")
    for path in files[:8]:
        lines.append(f"- {path}")
    if len(files) > 8:
        lines.append(f"- ... {len(files) - 8} more")
    return "\n".join(lines)


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_tasks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_task(path: Path, task_id: str) -> dict[str, Any] | None:
    for task in read_tasks(path):
        if str(task.get("id") or "") == str(task_id):
            return task
    return None


def next_pending(path: Path) -> dict[str, Any] | None:
    return next((task for task in read_tasks(path) if task.get("status") == "pending"), None)


def claim_next_pending(path: Path) -> dict[str, Any] | None:
    """Atomically claim one pending task so multiple workers cannot duplicate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    worker_id = worker_identity()
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(path)
        now = datetime.now()
        now_text = now.isoformat(timespec="seconds")
        for index, task in enumerate(tasks):
            status = str(task.get("status") or "")
            if status == "pending" or stale_in_progress(task, now):
                if status == CLAIMED_STATUS:
                    task.setdefault("claim_history", []).append(
                        {
                            "worker_id": task.get("worker_id"),
                            "claimed_at": task.get("claimed_at"),
                            "reclaimed_at": now_text,
                        }
                    )
                task["status"] = CLAIMED_STATUS
                task["worker_id"] = worker_id
                task["claimed_at"] = now_text
                task.pop("send_errors", None)
                tasks[index] = task
                write_tasks(path, tasks)
                return task
        return None


def claim_next_deferred_send(path: Path) -> dict[str, Any] | None:
    """Claim one deferred send if its retry backoff has elapsed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    worker_id = worker_identity()
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(path)
        now = datetime.now()
        now_text = now.isoformat(timespec="seconds")
        for index, task in enumerate(tasks):
            status = str(task.get("status") or "")
            if status not in {SEND_DEFERRED_LOCKED_STATUS, SEND_RETRYING_STATUS}:
                continue
            if status == SEND_RETRYING_STATUS and not stale_send_retrying(task, now):
                continue
            if status == SEND_DEFERRED_LOCKED_STATUS and not deferred_send_backoff_elapsed(task, now):
                continue
            task["status"] = SEND_RETRYING_STATUS
            task["worker_id"] = worker_id
            task["send_retry_claimed_at"] = now_text
            task["send_retry_count"] = int(task.get("send_retry_count") or 0) + 1
            tasks[index] = task
            write_tasks(path, tasks)
            return task
        return None


def deferred_send_backoff_elapsed(task: dict[str, Any], now: datetime) -> bool:
    backoff = int(os.environ.get("WECHAT_WORKER_DEFERRED_SEND_BACKOFF_SECONDS", DEFAULT_DEFERRED_SEND_BACKOFF_SECONDS))
    if backoff <= 0:
        return True
    last = parse_iso_datetime(str(task.get("last_send_attempt_at") or task.get("resent_at") or task.get("completed_at") or ""))
    if not last:
        return True
    return (now - last).total_seconds() >= backoff


def stale_send_retrying(task: dict[str, Any], now: datetime) -> bool:
    if task.get("status") != SEND_RETRYING_STATUS:
        return False
    timeout = int(os.environ.get("WECHAT_WORKER_STALE_SEND_RETRY_SECONDS", "180"))
    if timeout <= 0:
        return False
    claimed_at = parse_iso_datetime(str(task.get("send_retry_claimed_at") or ""))
    if not claimed_at:
        return True
    return (now - claimed_at).total_seconds() > timeout


def stale_in_progress(task: dict[str, Any], now: datetime) -> bool:
    if task.get("status") != CLAIMED_STATUS:
        return False
    timeout = int(os.environ.get("WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS", DEFAULT_STALE_IN_PROGRESS_SECONDS))
    if timeout <= 0:
        return False
    claimed_at = parse_iso_datetime(str(task.get("claimed_at") or ""))
    if not claimed_at:
        return False
    return (now - claimed_at).total_seconds() > timeout


def parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def worker_identity() -> str:
    return f"pid:{os.getpid()}"


def rewrite_task(path: Path, updated: dict[str, Any]) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(path)
        for index, task in enumerate(tasks):
            if task.get("id") == updated.get("id"):
                tasks[index] = updated
                break
        write_tasks(path, tasks)


def write_tasks(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks), encoding="utf-8")


def log_worker_event(status: str, task: dict[str, Any]) -> None:
    payload = {
        "worker_event": status,
        "task_id": task.get("id"),
        "chat": task.get("chat"),
        "worker_id": task.get("worker_id") or worker_identity(),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def run_worker_codex(task: dict[str, Any]) -> str:
    policy = choose_worker_policy(task)
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(os.environ.get("WECHAT_WORKER_MAX_CODEX_ATTEMPTS", str(len(EFFORT_ORDER)))))
    for attempt_index in range(max_attempts):
        task["worker_policy"] = policy
        result = run_worker_codex_once(task, policy)
        attempts.append(
            {
                "attempt": attempt_index + 1,
                "model": policy.get("model"),
                "reasoning_effort": policy.get("reasoning_effort"),
                "timeout_seconds": policy.get("timeout_seconds"),
                "escalated_from": policy.get("escalated_from"),
                "result_excerpt": collapse_context_text(result, max_len=280),
            }
        )
        next_policy = escalated_policy(policy, result)
        if not next_policy:
            break
        policy = next_policy
    task["worker_policy"] = policy
    task["worker_policy_attempts"] = attempts
    return result


def run_worker_codex_once(task: dict[str, Any], policy: dict[str, Any]) -> str:
    artifact_dir = worker_artifact_dir(task)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    task.setdefault("artifact_dir", str(artifact_dir))
    preflight = prepare_worker_preflight(task, artifact_dir)
    if preflight:
        task["preflight"] = preflight
    deterministic = deterministic_preflight_result(task)
    if deterministic is not None:
        return deterministic
    tool_context = build_worker_tool_context(task)
    prompt = f"""You are the slower worker agent for a WeChat LabCanvas chat.
Handle the task using available local files/tools. Save downloaded or generated artifacts under the repo's ignored private/output folders when possible.
The task may be a fragment or follow-up from an ongoing WeChat thread. Use the task's source and context fields to resolve pronouns, repeated requests, "same/again/this/that/last one", and incomplete messages.
Before doing work or composing the final message, check whether the recent context already contains a bot/self answer or completed result for the same request. Avoid sending the same answer again; return only the new delta, current status, missing decision, or remaining artifact.
Strict source isolation: the task's `chat`, `source.local_id`, `source.server_id`, `context`, and any explicit source/reference rows embedded in `request` define the only WeChat source. Never use media, files, or generated artifacts from another chat, another direct message, a nearby queue item, or an unrelated old task.
If no exact matching source media is available for "this image", "this PDF", "this video", "last one", or a quoted command, return a source-limited message asking for the exact file/source. Do not synthesize or continue from unrelated media.
Exception for WeChat video-to-AutoPublish requests: if the task asks to copy/download a WeChat video to Nutstore AutoPublish and the recent context contains a same-chat video row, first run:
`PYTHONPATH=src python -m agenticapp wechat autopublish-video --chat "<chat>" --sync --fetch-gui --since-minutes 720 --json`
This opens the chat in the isolated WeChat desktop, clicks the latest visible video so the official client caches the MP4, media-syncs it, and atomically copies it to `/home/lachlan/Nutstore Files/AutoPublish/AutoPublish`. Only report missing source after that command fails or returns no matching video.
If `task.preflight.autopublish_video` exists and has `ok: false` for a task with `message_local_ids`, fail closed: do not publish, transcode, or reuse any nearby/older video. Report that the exact WeChat row was not cached and include the safe next action.

{tool_context}

Return either plain text or this JSON shape:
{{
  "message": "concise message to send back",
  "files": ["/absolute/path/to/file.pdf", "/absolute/path/to/preview.png"],
  "confirmation": "optional question to ask before continuing"
}}

Use confirmation when an important choice, purchase, external send, deletion, privacy-sensitive action, or irreversible action needs approval.
If a download is blocked by login, CAPTCHA, bot check, consent page, or a site that needs human action, do not try to bypass it.
Open a human-assist browser in the isolated virtual desktop with:
PYTHONPATH=src python -m agenticapp wechat browser-assist --url "<url>" --json
Then return a confirmation telling the user to complete the manual step in noVNC and approve continuation.
If other external tools or files are not available, say exactly what is needed next.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}
"""
    result = run_codex_session(
        prompt,
        chat_name=str(task.get("chat") or "wechat-chat"),
        role="worker",
        model=str(policy["model"]),
        reasoning_effort=str(policy["reasoning_effort"]),
        sandbox=str(policy["sandbox"]),
        timeout_seconds=int(policy["timeout_seconds"]),
        workdir=ROOT,
        reuse=bool(policy.get("reuse_session", True)),
    )
    if not result["ok"]:
        return f"Worker failed: {str(result.get('stderr_tail') or result.get('message') or '').strip()[:1000]}"
    task["codex_session"] = {
        "role": "worker",
        "thread_id_short": str(result.get("thread_id") or "")[:8],
        "resumed": bool(result.get("resumed")),
        "fallback_started": bool(result.get("fallback_started")),
    }
    return str(result.get("message") or "").strip()


def worker_artifact_dir(task: dict[str, Any]) -> Path:
    task_id = safe_slug(str(task.get("id") or "manual-task"))
    return ROOT / "output" / "wechat_worker" / task_id


def prepare_worker_preflight(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    if not is_video_publish_task(task):
        return {}
    context_path = artifact_dir / "lazyedit_correction_context.md"
    metadata_path = artifact_dir / "lazyedit_metadata_brief.md"
    context_path.write_text(build_lazyedit_correction_context(task), encoding="utf-8")
    metadata_path.write_text(build_lazyedit_metadata_brief(task), encoding="utf-8")
    preflight: dict[str, Any] = {
        "lazyedit_context": {
            "correction_prompt_file": str(context_path),
            "metadata_prompt_file": str(metadata_path),
            "rule": "Pass correction_prompt_file to --correction-prompt-file and metadata_prompt_file to --metadata-prompt-file.",
        }
    }
    if should_preflight_autopublish(task):
        preflight["autopublish_video"] = run_autopublish_video_preflight(task)
    return preflight


def task_focus_text(task: dict[str, Any]) -> str:
    request = str(task.get("request") or "")
    focused = request
    match = re.search(
        r"Current coalesced request:\n(?P<body>.*?)(?:\n\nRecent history:|\n\nSame-chat reference media/context rows:|\Z)",
        request,
        flags=re.DOTALL,
    )
    if match:
        focused = match.group("body").strip()

    source_local_id = int_or_none((task.get("source") or {}).get("local_id")) if isinstance(task.get("source"), dict) else None
    source_text = ""
    if source_local_id is not None:
        for row in task.get("context") or []:
            if not isinstance(row, dict):
                continue
            if int_or_none(row.get("local_id")) == source_local_id:
                source_text = str(row.get("content") or "").strip()
                break

    parts = []
    for value in (focused, source_text):
        text = collapse_context_text(value, max_len=3000)
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts)


def is_video_publish_task(task: dict[str, Any]) -> bool:
    text = task_focus_text(task).lower()
    markers = [
        "publish",
        "post",
        "upload",
        "shipinhao",
        "视频号",
        "youtube",
        "instagram",
        "lazyedit",
        "autopublish",
        "subtitle",
        "caption",
        "transcript",
        "字幕",
        "发布",
        "上传",
    ]
    return any(marker in text for marker in markers)


def should_preflight_autopublish(task: dict[str, Any]) -> bool:
    text = task_focus_text(task).lower()
    markers = [
        "nutstore",
        "autopublish",
        "publish folder",
        "publish",
        "post",
        "upload",
        "lazyedit",
        "shipinhao",
        "视频号",
        "youtube",
        "instagram",
        "sph",
        "y2b",
        "ytb",
        "ins",
        "发布",
        "上传",
    ]
    return any(marker in text for marker in markers)


def build_lazyedit_correction_context(task: dict[str, Any]) -> str:
    lines = [
        "# LazyEdit Correction Context",
        "",
        "Use this as evidence for subtitle correction. Do not invent dialogue unsupported by the audio/video.",
        "",
        "## Request",
        str(task.get("request") or "").strip() or "(empty)",
        "",
        "## Source",
        json.dumps(task.get("source") or {}, ensure_ascii=False, indent=2),
        "",
        "## Recent Same-Chat Context",
    ]
    for row in task.get("context") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- local_id={row.get('local_id')} sender={row.get('sender_display') or row.get('sender')}: "
            f"{collapse_context_text(row.get('content'))}"
        )
    lines.extend(
        [
            "",
            "## Media Reference Tokens",
            ", ".join(extract_media_tokens_from_task(task)) or "(none)",
            "",
            "## Instructions",
            "- Fix clear ASR mistakes, names, terms, and broken phrases based on the context above.",
            "- Preserve timing and line count where practical.",
            "- Use a separate metadata brief for public title/description/hashtags.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_lazyedit_metadata_brief(task: dict[str, Any]) -> str:
    request = collapse_context_text(task.get("request")) or "WeChat video publish request"
    context_lines = []
    for row in task.get("context") or []:
        if not isinstance(row, dict):
            continue
        text = collapse_context_text(row.get("content"))
        if text:
            context_lines.append(text)
    return (
        "# LazyEdit Metadata Brief\n\n"
        "Use this only for public-facing title, description, keywords, and platform notes.\n"
        "Do not expose private chat logs, internal agent workflow, or every subtitle-correction detail.\n\n"
        f"Request summary: {request[:800]}\n\n"
        "Relevant public context candidates:\n"
        + "\n".join(f"- {line[:360]}" for line in context_lines[-6:])
        + "\n\nSuggested metadata style: concise, natural, viewer-facing.\n"
    )


def run_autopublish_video_preflight(task: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("WECHAT_WORKER_DISABLE_AUTOPUBLISH_PREFLIGHT"):
        return {"ok": False, "status": "disabled-by-env"}
    chat = str(task.get("chat") or "").strip()
    if not chat:
        return {"ok": False, "status": "skipped", "error": "missing chat"}
    command = [
        sys.executable,
        str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_autopublish_video.py"),
        "--chat",
        chat,
        "--sync",
        "--fetch-gui",
        "--since-minutes",
        os.environ.get("WECHAT_WORKER_AUTOPUBLISH_SINCE_MINUTES", "720"),
        "--limit",
        "20",
        "--json",
    ]
    video_local_ids = extract_video_local_ids_from_task(task)
    for local_id in video_local_ids:
        command += ["--message-local-id", str(local_id)]
    timeout = float(os.environ.get("WECHAT_WORKER_AUTOPUBLISH_TIMEOUT", "180"))
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "status": "error", "error": str(exc)[:1000], "command": redact_command(command)}
    payload: dict[str, Any]
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
        payload = parsed if isinstance(parsed, dict) else {"stdout": proc.stdout.strip()[:2000]}
    except json.JSONDecodeError:
        payload = {"stdout": proc.stdout.strip()[:2000]}
    payload.setdefault("ok", proc.returncode == 0)
    payload["returncode"] = proc.returncode
    payload["command"] = redact_command(command)
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr.strip()[:2000]
    if video_local_ids:
        payload["message_local_ids"] = video_local_ids
    return payload


def deterministic_preflight_result(task: dict[str, Any]) -> str | None:
    autopub = ((task.get("preflight") or {}).get("autopublish_video") if isinstance(task.get("preflight"), dict) else None)
    if not isinstance(autopub, dict):
        return None
    if bool(autopub.get("ok")) and should_deterministic_video_publish(task):
        return run_deterministic_lazyedit_publish(task, autopub)
    if bool(autopub.get("ok")):
        return None
    message_local_ids = autopub.get("message_local_ids")
    if not message_local_ids:
        return None
    recent = autopub.get("recent_video_messages") or []
    if recent:
        source_state = "看到了对应的 WeChat 视频消息，但官方客户端还没有把这一条完整 MP4 缓存到本地。"
    else:
        source_state = "没有在本地解密消息库中找到对应的 WeChat 视频行。"
    message = (
        "我没有发布这个视频。"
        f"{source_state}"
        "为了避免误发布，我已按 exact local_id fail-closed 规则停止，没有使用附近的旧视频或上一次视频。"
        "请重新发送原视频，或在 WeChat 里点开这条视频让客户端缓存完整 MP4；缓存到本地后我会继续保存到 Nutstore/AutoPublish 并走 LazyEdit 发布链路。"
    )
    return json.dumps({"message": message, "files": [], "confirmation": ""}, ensure_ascii=False)


def should_deterministic_video_publish(task: dict[str, Any]) -> bool:
    if os.environ.get("WECHAT_WORKER_DISABLE_DETERMINISTIC_VIDEO_PUBLISH"):
        return False
    text = json.dumps(task, ensure_ascii=False).lower()
    negative_markers = [
        "no need to publish",
        "do not publish",
        "don't publish",
        "dont publish",
        "no publish",
        "not publish",
        "先不要发布",
        "先別發布",
        "不要发布",
        "不要發布",
        "不用发布",
        "不用發布",
        "暂不发布",
        "暫不發布",
    ]
    if any(marker in text for marker in negative_markers):
        return False
    direct_markers = [
        "publish it",
        "publish this",
        "publish the video",
        "post it",
        "post this",
        "upload it",
        "upload this",
        "发布它",
        "發布它",
        "发布这个",
        "發布這個",
        "发布视频",
        "發布影片",
        "上传这个",
        "上傳這個",
        "sph",
        "shipinhao",
        "视频号",
        "視頻號",
        "youtube",
        "y2b",
        "ytb",
        "instagram",
    ]
    return any(marker in text for marker in direct_markers) or bool(re.search(r"\b(?:sph|y2b|ytb|ins)\b", text))


def run_deterministic_lazyedit_publish(task: dict[str, Any], autopub: dict[str, Any]) -> str | None:
    target_raw = str(autopub.get("target") or "")
    if not target_raw:
        return None
    target = Path(target_raw)
    if not target.is_file():
        return json.dumps(
            {
                "message": f"视频已匹配但 AutoPublish 目标文件不存在：{target.name or target_raw}。我没有发布；请重新触发保存或重新发送视频。",
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    timeout = float(os.environ.get("WECHAT_WORKER_LAZYEDIT_IMPORT_TIMEOUT", "360"))
    poll = float(os.environ.get("WECHAT_WORKER_LAZYEDIT_IMPORT_POLL_SECONDS", "5"))
    video_id = wait_for_lazyedit_import(target, timeout=timeout, poll_seconds=poll)
    if video_id is None:
        return json.dumps(
            {
                "message": (
                    f"视频已保存到 AutoPublish 文件夹：{target.name}，但 LazyEdit 在 {int(timeout)} 秒内还没有显示导入结果。"
                    "我没有切换到旧视频；稍后会由队列继续或请再发“继续发布”。"
                ),
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    platforms = detect_publish_platforms(task)
    lazy_context = ((task.get("preflight") or {}).get("lazyedit_context") if isinstance(task.get("preflight"), dict) else {}) or {}
    correction_prompt = str(lazy_context.get("correction_prompt_file") or "")
    metadata_prompt = str(lazy_context.get("metadata_prompt_file") or "")
    outcome = run_lazyedit_publish_command(
        video_id=video_id,
        platforms=platforms,
        correction_prompt=correction_prompt,
        metadata_prompt=metadata_prompt,
    )
    message = summarize_lazyedit_publish_outcome(video_id, platforms, target, outcome)
    return json.dumps({"message": message, "files": [], "confirmation": ""}, ensure_ascii=False)


def wait_for_lazyedit_import(target: Path, *, timeout: float, poll_seconds: float) -> int | None:
    deadline = time.monotonic() + max(0.0, timeout)
    target_name = target.name
    target_stem = target.stem
    while True:
        for video in lazyedit_videos():
            file_path = str(video.get("file_path") or "")
            title = str(video.get("title") or "")
            if Path(file_path).name == target_name or title == target_stem or Path(file_path).stem == target_stem:
                try:
                    return int(video.get("id"))
                except (TypeError, ValueError):
                    return None
        if time.monotonic() >= deadline:
            return None
        time.sleep(max(0.25, poll_seconds))


def lazyedit_videos() -> list[dict[str, Any]]:
    payload = lazyedit_api_get("/api/videos", timeout=20)
    videos = payload.get("videos") if isinstance(payload, dict) else []
    return [item for item in videos if isinstance(item, dict)]


def lazyedit_api_get(path: str, *, timeout: float = 20) -> dict[str, Any]:
    url = f"{LAZYEDIT_API_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError):
        return {}
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def detect_publish_platforms(task: dict[str, Any]) -> list[str]:
    text = json.dumps(task, ensure_ascii=False).lower()
    platforms: list[str] = []
    if any(marker in text for marker in ["shipinhao", "视频号", "視頻號"]) or re.search(r"\bsph\b", text):
        platforms.append("shipinhao")
    if "youtube" in text or re.search(r"\b(?:y2b|ytb)\b", text):
        platforms.append("youtube")
    if "instagram" in text or re.search(r"\bins\b", text):
        platforms.append("instagram")
    if not platforms:
        platforms = ["shipinhao", "youtube", "instagram"]
    return platforms


def run_lazyedit_publish_command(
    *,
    video_id: int,
    platforms: list[str],
    correction_prompt: str,
    metadata_prompt: str,
) -> dict[str, Any]:
    timeout = float(os.environ.get("WECHAT_WORKER_LAZYEDIT_PUBLISH_TIMEOUT", "10800"))
    process_timeout = os.environ.get("WECHAT_WORKER_LAZYEDIT_PROCESS_TIMEOUT", "3600")
    publish_timeout = os.environ.get("WECHAT_WORKER_LAZYEDIT_REMOTE_TIMEOUT", "7200")
    command_parts = [
        "source ~/miniconda3/etc/profile.d/conda.sh",
        "conda activate lazyedit",
        "python scripts/lazyedit_publish.py",
        f"--video-id {video_id}",
        "--use-current-settings",
        f"--platforms {','.join(platforms)}",
        "--correct-subtitles",
        "--correction-source polished",
        "--guided-monitor",
        "--wait",
        "--poll-seconds 10",
        f"--process-timeout {process_timeout}",
        f"--publish-timeout {publish_timeout}",
        "--json",
    ]
    if correction_prompt:
        command_parts.append(f"--correction-prompt-file {shell_quote(correction_prompt)}")
    if metadata_prompt:
        command_parts.append(f"--metadata-prompt-file {shell_quote(metadata_prompt)}")
    command = ["bash", "-lc", " ".join(command_parts)]
    try:
        proc = subprocess.run(
            command,
            cwd=LAZYEDIT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "status": "timeout", "stdout": (exc.stdout or "")[-4000:], "stderr": (exc.stderr or "")[-4000:]}
    return {
        "ok": proc.returncode == 0,
        "status": "done" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
        "payload": parse_last_json_object(proc.stdout),
    }


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def parse_last_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    for start in [index for index, char in enumerate(stripped) if char == "{"][::-1]:
        try:
            parsed = json.loads(stripped[start:])
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else {}
    return {}


def summarize_lazyedit_publish_outcome(video_id: int, platforms: list[str], target: Path, outcome: dict[str, Any]) -> str:
    queue = lazyedit_api_get("/api/autopublish/queue", timeout=30)
    jobs = queue.get("jobs") if isinstance(queue, dict) else []
    matching = [
        job for job in jobs
        if isinstance(job, dict) and int_or_none(job.get("video_id")) == video_id
    ]
    latest = matching[0] if matching else {}
    status = str(latest.get("status") or outcome.get("status") or ("done" if outcome.get("ok") else "failed"))
    local_job_id = latest.get("id")
    remote_job_id = latest.get("remote_job_id")
    remote_status = latest.get("remote_status")
    error = latest.get("error") or outcome.get("stderr") or ""
    if outcome.get("ok") or status in {"queued", "running", "done"}:
        pieces = [
            "已自动完成 exact 视频保存、LazyEdit 处理/字幕修正并提交发布。",
            f"video_id={video_id}",
            f"platforms={','.join(platforms)}",
            f"status={status}",
        ]
        if local_job_id:
            pieces.append(f"job_id={local_job_id}")
        if remote_job_id:
            pieces.append(f"remote_job_id={remote_job_id}")
        if remote_status:
            pieces.append(f"remote={remote_status}")
        pieces.append(f"source={target.name}")
        return "；".join(pieces)
    return (
        "视频已严格按 exact source 保存，但 LazyEdit 发布没有完成。"
        f" video_id={video_id}; platforms={','.join(platforms)}; source={target.name}; "
        f"error={str(error)[:500]}"
    )


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_video_local_ids_from_task(task: dict[str, Any]) -> list[int]:
    requested: set[int] = set()
    for groups in re.findall(r"local_id\s*[=:]?\s*(\d+)|local_id(\d+)", str(task.get("request") or "")):
        for value in groups:
            if value:
                requested.add(int(value))
    video_ids = []
    for row in task.get("context") or []:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "")
        try:
            local_id = int(row.get("local_id") or 0)
        except (TypeError, ValueError):
            continue
        if local_id <= 0:
            continue
        if "<videomsg" in content or "[WeChat video]" in content:
            video_ids.append(local_id)
    if requested:
        exact = [local_id for local_id in video_ids if local_id in requested]
        if exact:
            return exact
    return video_ids[-1:] if video_ids else []


def extract_media_tokens_from_task(task: dict[str, Any], *, limit: int = 16) -> list[str]:
    text = json.dumps(task, ensure_ascii=False)
    tokens: list[str] = []
    patterns = [
        r"\b(?:md5|newmd5|rawmd5|originsourcemd5|filemd5)\s*=\s*[\"']([0-9A-Fa-f]{16,64})[\"']",
        r"<md5>\s*([0-9A-Fa-f]{16,64})\s*</md5>",
        r"\b([0-9A-Fa-f]{32,64})\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            token = match.group(1).lower()
            if token not in tokens:
                tokens.append(token)
            if len(tokens) >= limit:
                return tokens
    return tokens


def collapse_context_text(value: Any, *, max_len: int = 2000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= max_len else text[:max_len] + "..."


def redact_command(command: list[str]) -> list[str]:
    return [item if ".private" not in item else "<private-path>" for item in command]


def build_worker_tool_context(task: dict[str, Any]) -> str:
    artifact_dir = str(task.get("artifact_dir") or worker_artifact_dir(task))
    prompt_text = str(task.get("request") or "").strip()
    quoted_prompt = json.dumps(prompt_text or "prepare CAD/PCB/Blender artifacts", ensure_ascii=False)
    return f"""LabCanvas tool playbook:
- Use `{artifact_dir}` as the preferred working/output folder for new artifacts.
- Match every input file/media path to this task's exact `chat`, `source.local_id`, `source.server_id`, explicit source/reference rows in `request`, or source-scoped context text. Do not borrow files from another group/direct chat or from unrelated previous worker tasks.
- If the exact requested media is missing, stop with a source-limited message asking the user to resend/provide it instead of using a nearby file.
- For editable paper-figure grids plus AgInTi image-generation payloads/live images, run:
  `PYTHONPATH=src python -m agenticapp studio figure-grid {quoted_prompt} --storage-dir output/webapp --json`
- For PCB/CAD planning and reusable artifacts, run:
  `PYTHONPATH=src python -m agenticapp studio lab-task {quoted_prompt} --mode auto --execute --storage-dir output/webapp --json`
- For a Blender experiment/setup render, write or reuse a scene JSON under `{artifact_dir}`, then run:
  `PYTHONPATH=src python -m agenticapp render-scene <scene.json> --output-dir {artifact_dir} --timeout 240`
- For a built-in starting scene, run:
  `PYTHONPATH=src python -m agenticapp scene-template experiment-setup --output {artifact_dir}/scene.json`
- For direct target envelopes or MCP handoff, use:
  `PYTHONPATH=src python -m agenticapp studio dispatch blender "<instruction>" --json`
- For existing KiCad/OpenSCAD/Blender workflows, prefer the commands emitted by `studio lab-task`; they know the repo's PCB, CAD, Gerber, STEP, STL, and render locations.
- For AgInTi figure requests, return the editable SVG grid plus AgInTi prompt/request/manifest files; if live image generation is enabled and `imagePaths` contains PNG/JPG outputs, include those image paths too.
- For PCB render requests, return the KiCad/board PNG preview and any STEP/Gerber zip when available. For CAD/Blender render requests, return the PNG render plus STEP/STL/source spec when useful.

LALACHAN/RaraXia/AyaChan/SasaKun story-video generation:
- For requests mentioning LALACHAN, RaraXia/Rara Xia/啦啦侠, AyaChan/Aya Chan/阿芽酱, SasaKun/Sasa Kun/飒飒君, Xiaoyunque/小云雀, XYQ, or Seedance, treat the task as a LALACHAN repo workflow rather than a generic video prompt.
- Use `/home/lachlan/ProjectsLFS/LALACHAN` as the default root. If available, read `/home/lachlan/.codex/skills/lalachan-xyq-browser-video/SKILL.md` and `/home/lachlan/ProjectsLFS/LALACHAN/references/lalachan-story-video-handoff-for-wechat.md` for the current runbook.
- First write a natural, understandable Chinese story with one clear setup -> problem -> action -> twist -> payoff chain. Save it under `/home/lachlan/ProjectsLFS/LALACHAN/references/stories/`.
- Convert the story into a compact Xiaoyunque prompt and save it under `/home/lachlan/ProjectsLFS/LALACHAN/references/prompts/`.
- Use the Xiaoyunque browser UI, not the API, unless explicitly requested. Default to 沉浸式短片, Seedance 2.0 Fast non-VIP, 15s, 4:3, mainly Chinese, with `不要字幕，不要生成任何字幕、说明文字、下三分之一文字或画面文字。`
- Upload and verify the eight default reference images in this exact order: `words-card.jpg`, `LazyingArtRobot.png`, `display.png`, `patchwork-leather-notebook-luxury-clean-v2.png`, `raraxia.jpeg`, `ayachan.png`, `sasakun.jpeg`, `Trio.png`.
- In the Xiaoyunque prompt, refer to uploaded images as 图1 through 图8. Do not paste local filesystem paths or file names into the prompt as scene text.
- Before any paid submit, verify visible page state: mode, model, duration, ratio, prompt, all attachment uploads succeeded, non-VIP model, and point cost. Never double-click submit or retry if the job is queued/running.
- Monitor the thread, download the finished MP4, save/copy it under `/home/lachlan/ProjectsLFS/LALACHAN/Videos`, verify with `ffprobe`, and return the story path, prompt path, MP4 path, and relevant screenshots/logs in `files` where safe.
- If the user asks to publish, then hand the verified MP4 to LazyEdit with the publish workflow below. Otherwise stop after generation/import and report the ready video path.

LazyEdit/AutoPublish video publishing:
- For publish, re-publish, Shipinhao, YouTube, Instagram, AutoPublish, LazyEdit, subtitle-correction, metadata, or platform-monitoring requests, first read the repo-local workflow:
  `sed -n '1,260p' {LAZYEDIT_PUBLISH_SKILL.relative_to(ROOT)}`
- Prefer the LazyEdit CLI in `/home/lachlan/DiskMech/Projects/lazyedit` over manual browser work:
  `cd /home/lachlan/DiskMech/Projects/lazyedit && source ~/miniconda3/etc/profile.d/conda.sh && conda activate lazyedit`
- If the source is a WeChat video, resolve the exact same-chat media first with:
  `PYTHONPATH=src python -m agenticapp wechat autopublish-video --chat "<chat>" --sync --fetch-gui --since-minutes 720 --json`
- For real publishes, verify configured logo settings with:
  `curl -fsS http://127.0.0.1:18787/api/ui-settings/logo_settings | jq .`
- For subtitle correction, create a correction context file under `{artifact_dir}` from the task JSON, current coalesced request, quoted message, recent history, source/reference rows, visible media metadata, and any user-provided script/transcript/story notes. Pass that file as `--correction-prompt-file`.
- Create a separate short metadata brief under `{artifact_dir}` for public title/description/hashtags and pass it as `--metadata-prompt-file`. Do not feed the full chat history or full script as metadata context.
- For processing plus publish, use `scripts/lazyedit_publish.py` with `--use-current-settings`, platform flags, `--guided-monitor`, `--wait`, and separate `--correction-prompt-file` and `--metadata-prompt-file` files when context is needed.
- For explicit publish requests, a `--no-publish` run is only a verification gate. If it succeeds and no manual login/CAPTCHA/approval block appears, immediately run exactly one real publish for the requested platforms with the same corrected output and report the publish job ids/status. Do not stop after a successful no-publish pass.
- If the user asks to correct subtitles or provides contextual wording for a video, use `--correct-subtitles --correction-source polished` unless the source output has already been corrected and verified.
- Before a real publish with subtitle correction, inspect the polished subtitle output such as `DATA/VIDEO_FOLDER/*_mixed_polished.md` and fix obvious ASR errors only when supported by the message context.
- Use `--no-process` only when the final LazyEdit output already exists or the user explicitly asks to reuse the last/current output.
- Monitor local and remote queues:
  `curl -fsS http://127.0.0.1:18787/api/autopublish/queue | jq '.jobs[:8]'`
  `curl -fsS http://lazyingart:8081/publish/queue | jq '.jobs[:8]'`
  `ssh lachlan@lazyingart 'tmux capture-pane -pt autopub:0 -S -120 | tail -n 120'`
- If Shipinhao or another platform needs QR login, CAPTCHA, consent, or a manual click, open the isolated browser via `PYTHONPATH=src python -m agenticapp wechat browser-assist --url "<url>" --json`, then ask for human completion instead of bypassing it.
- Final responses should include LazyEdit job id, remote job id if present, platforms, status, whether processing was reused/rerun, and safe output paths.

Shipinhao/Finder and short-video shares:
- Treat comment sections as useful auxiliary evidence when they are accessible from the local GUI, cached metadata, a browser-assist session, or a public mirrored page.
- Search visible or retrieved comments for Tencent Yuanbao-style prompts such as `@元宝`, `腾讯元宝`, `英文全文`, `全文`, `总结`, `摘要`, `字幕`, `转写`, `transcript`, and `summary`; these comments often request or contain transcript/summary material.
- Also skim other highly visible comments for quoted lines, timestamps, topic summaries, corrections, names, links, or context that helps infer the video content.
- Do not post a comment or ask Yuanbao yourself unless the user explicitly requests that action. Reading comments is allowed; writing comments needs confirmation.
- If the actual video, comments, transcript, or reliable public mirror are not available, do not produce a "deep analysis" or imply you watched/read the source. Return a source-limited note, state what was accessible, and ask the user to provide the video/comments/transcript or approve a manual/browser path if deeper analysis is needed.

Artifact return contract:
- If you generate or find preview files, include their existing absolute or repo-relative paths in the JSON `files` array. The outer worker sends those files to WeChat.
- Prefer PNG/JPG/SVG/PDF/MP4/MOV/audio/STEP/STL/ZIP/SCAD/KiCad files. Do not include decrypted WeChat DBs, private config, cookies, tokens, browser profiles, or chat logs.
- Do not say a file was sent unless it is listed in `files` and exists locally.
"""


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", value.strip()).strip("-").lower()
    return slug[:96] or "task"


def choose_worker_policy(task: dict[str, Any]) -> dict[str, Any]:
    text = worker_policy_text(task).lower()
    xhigh_keywords = [
        "deep research",
        "fully implement",
        "full implementation",
        "complete task",
        "finish the task",
        "end to end",
        "end-to-end",
        "as you",
        "do it all",
        "take over",
        "autonomous",
        "robust",
        "systematic",
        "commit and push",
        "install",
        "github",
        "mcp",
        "publish",
        "place order",
        "submit order",
        "jlc",
        "jlcpcb",
        "wenext",
        "labview",
        "wechat automation",
        "fully control",
        "完整任务",
        "完整实现",
        "自动完成",
        "全自动",
        "提交订单",
        "下单",
        "安装",
        "发布",
    ]
    high_keywords = [
        "pcb",
        "kicad",
        "cad",
        "openscad",
        "blender",
        "render",
        "commit",
        "push",
        "order",
        "full task",
        "agent",
        "webapp",
        "script",
        "cli",
        "database",
        "download",
        "video",
        "lalachan",
        "raraxia",
        "rara xia",
        "ayachan",
        "aya chan",
        "sasakun",
        "sasa kun",
        "xiaoyunque",
        "小云雀",
        "啦啦侠",
        "阿芽酱",
        "飒飒君",
        "seedance",
        "subtitle",
        "autopublish",
        "lazyedit",
        "完整",
        "电路板",
        "渲染",
        "脚本",
        "数据库",
        "下载",
        "视频",
        "字幕",
    ]
    medium_keywords = [
        "paper",
        "pdf",
        "search",
        "summarize",
        "summary",
        "dataset",
        "figure",
        "figure grid",
        "diagram",
        "aginti",
        "imagegen",
        "image generation",
        "icons",
        "overview",
        "research",
        "nature",
        "hyperspectral",
        "论文",
        "总结",
        "搜索",
        "文献",
        "高光谱",
        "高光譜",
    ]
    if any(keyword in text for keyword in xhigh_keywords) or len(text) > 5000:
        effort = "xhigh"
    elif any(keyword in text for keyword in high_keywords) or len(text) > 2200:
        effort = "high"
    elif any(keyword in text for keyword in medium_keywords) or len(text) > 800:
        effort = "medium"
    else:
        effort = "medium"
    effort = clamp_effort(effort, min_effort=worker_min_effort(), max_effort=worker_max_effort())
    return {
        "model": worker_model(),
        "reasoning_effort": effort,
        "sandbox": worker_sandbox(),
        "timeout_seconds": timeout_for_effort(effort),
    }


def worker_policy_text(task: dict[str, Any]) -> str:
    """Return only user/task-relevant text for effort selection.

    Queue entries can contain long reusable playbooks and source-isolation
    instructions. Those are important for execution but should not make a small
    edit or writing task look like an xhigh autonomous implementation task.
    """
    request = str(task.get("request") or "")
    focused = extract_current_request_for_policy(request)
    pieces = [focused or request]
    source = task.get("source")
    if isinstance(source, dict):
        pieces.append(str(source.get("chat") or ""))
    context = task.get("context")
    if isinstance(context, list):
        for item in context[-3:]:
            if isinstance(item, dict):
                pieces.append(str(item.get("content") or ""))
    return "\n".join(piece for piece in pieces if piece).strip()


def extract_current_request_for_policy(request: str) -> str:
    text = str(request or "")
    patterns = [
        ("Current coalesced request:", "\n\nRecent history:"),
        ("Current request:", "\n\nRecent history:"),
        ("Current message:", "\n\nRecent history:"),
    ]
    for start_marker, end_marker in patterns:
        start = text.find(start_marker)
        if start < 0:
            continue
        start += len(start_marker)
        end = text.find(end_marker, start)
        if end < 0:
            end = len(text)
        return text[start:end].strip()
    return ""


def worker_model() -> str:
    raw = os.environ.get("WECHAT_WORKER_CODEX_MODEL", DEFAULT_WORKER_MODEL).strip()
    model = raw or DEFAULT_WORKER_MODEL
    if "spark" in model.lower() and os.environ.get("WECHAT_ALLOW_SPARK_WORKER", "0") != "1":
        return DEFAULT_WORKER_MODEL
    return model


def worker_min_effort() -> str:
    return normalize_effort(os.environ.get("WECHAT_WORKER_MIN_EFFORT", "medium"), fallback="medium")


def worker_max_effort() -> str:
    return normalize_effort(os.environ.get("WECHAT_WORKER_MAX_EFFORT", "xhigh"), fallback="xhigh")


def normalize_effort(value: str | None, *, fallback: str) -> str:
    effort = str(value or "").strip().lower()
    return effort if effort in EFFORT_ORDER else fallback


def clamp_effort(effort: str, *, min_effort: str, max_effort: str) -> str:
    effort = normalize_effort(effort, fallback="medium")
    min_index = EFFORT_ORDER.index(normalize_effort(min_effort, fallback="medium"))
    max_index = EFFORT_ORDER.index(normalize_effort(max_effort, fallback="xhigh"))
    if min_index > max_index:
        min_index, max_index = max_index, min_index
    index = EFFORT_ORDER.index(effort)
    index = max(min_index, min(index, max_index))
    return EFFORT_ORDER[index]


def timeout_for_effort(effort: str) -> int:
    normalized = normalize_effort(effort, fallback="medium")
    env_name = f"WECHAT_WORKER_TIMEOUT_{normalized.upper()}_SECONDS"
    raw = os.environ.get(env_name)
    if raw:
        try:
            return max(30, int(raw))
        except ValueError:
            pass
    return EFFORT_TIMEOUT_SECONDS[normalized]


def worker_sandbox() -> str:
    raw = os.environ.get("WECHAT_WORKER_CODEX_SANDBOX", "danger-full-access").strip()
    aliases = {
        "full": "danger-full-access",
        "full-access": "danger-full-access",
        "danger": "danger-full-access",
        "workspace": "workspace-write",
    }
    return aliases.get(raw, raw or "danger-full-access")


def escalated_policy(policy: dict[str, Any], result: str) -> dict[str, Any] | None:
    if not worker_result_needs_escalation(result):
        return None
    effort = str(policy.get("reasoning_effort") or "medium")
    try:
        index = EFFORT_ORDER.index(effort)
    except ValueError:
        index = 1
    if index >= len(EFFORT_ORDER) - 1:
        return None
    next_effort = EFFORT_ORDER[index + 1]
    next_effort = clamp_effort(next_effort, min_effort=worker_min_effort(), max_effort=worker_max_effort())
    if next_effort == effort:
        return None
    return {
        **policy,
        "model": worker_model(),
        "reasoning_effort": next_effort,
        "timeout_seconds": timeout_for_effort(next_effort),
        "escalated_from": effort,
    }


def worker_result_needs_escalation(result: str) -> bool:
    text = str(result or "").strip().lower()
    if not text:
        return True
    if worker_result_is_terminal_blocker(text):
        return False
    failure_markers = [
        "worker failed",
        "codex failed",
        "timed out",
        "timeout",
        "cannot complete",
        "can't complete",
        "unable to complete",
        "i cannot",
        "i can't",
        "failed before completion",
        "无法完成",
        "不能完成",
        "没有完成",
        "失败",
        "超时",
    ]
    if any(marker in text for marker in failure_markers):
        return True
    return len(text) < 80


def worker_result_is_terminal_blocker(text: str) -> bool:
    blocker_markers = [
        "captcha",
        "login",
        "log in",
        "manual step",
        "manual confirmation",
        "waiting for approval",
        "waiting_confirmation",
        "approve continuation",
        "source-limited",
        "resend",
        "provide the exact",
        "exact file/source",
        "missing source",
        "not accessible",
        "需要登录",
        "需要人工",
        "需要确认",
        "请确认",
        "请重新发送",
        "缺少源文件",
        "找不到源文件",
    ]
    return any(marker in text for marker in blocker_markers)


def parse_worker_result(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            message = str(data.get("message") or "").strip()
            confirmation = str(data.get("confirmation") or data.get("confirm") or "").strip()
            files = file_entries_from_json(data)
            return {"message": message, "confirmation": confirmation, "files": files, "raw": text}
    except Exception:
        pass
    message_lines = []
    files = []
    for line in text.splitlines():
        if line.strip().upper().startswith("FILE:"):
            files.append(str(Path(line.split(":", 1)[1].strip()).expanduser()))
        else:
            message_lines.append(line)
    return {"message": "\n".join(message_lines).strip(), "confirmation": "", "files": files, "raw": text}


def file_entries_from_json(data: Any) -> list[str]:
    files: list[str] = []
    file_keys = {
        "file",
        "files",
        "path",
        "paths",
        "artifact",
        "artifacts",
        "attachment",
        "attachments",
        "image",
        "images",
        "video",
        "videos",
        "audio",
        "audios",
        "subtitle",
        "subtitles",
        "render",
        "renders",
        "preview",
        "previews",
    }

    def visit(value: Any, *, key: str = "") -> None:
        lowered = key.lower()
        if isinstance(value, str):
            if lowered in file_keys or looks_like_artifact_path(value):
                files.append(value)
        elif isinstance(value, list):
            for item in value:
                visit(item, key=key)
        elif isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, key=str(child_key))

    visit(data)
    return unique_strings(files)


def prepare_result_files(result: dict[str, Any], raw_text: str) -> dict[str, Any]:
    candidates = unique_strings([*result.get("files", []), *extract_artifact_paths(raw_text)])
    files: list[str] = []
    skipped: list[dict[str, str]] = []
    for candidate in candidates:
        path = resolve_candidate_path(candidate)
        if not path.exists():
            skipped.append({"path": candidate, "reason": "missing"})
            continue
        ok, reason = is_safe_outbound_file(path)
        if not ok:
            skipped.append({"path": str(path), "reason": reason})
            continue
        files.append(str(path))
    result["files"] = unique_strings(files)
    if skipped:
        result["skipped_files"] = skipped
    if result["files"] and not result.get("message"):
        result["message"] = f"Generated {len(result['files'])} artifact(s); sending them now."
    return result


def extract_artifact_paths(text: str) -> list[str]:
    candidates: list[str] = []
    absolute = r"/[A-Za-z0-9_./:@%+=,\-]+"
    relative = r"(?:output|cad|pcb|publications|references|examples)/[A-Za-z0-9_./:@%+=,\-]+"
    for match in re.finditer(f"(?:{absolute}|{relative})", text):
        token = clean_path_token(match.group(0))
        if looks_like_artifact_path(token):
            candidates.append(token)
    return unique_strings(candidates)


def looks_like_artifact_path(value: str) -> bool:
    token = clean_path_token(value)
    return bool(token and Path(token).suffix.lower() in OUTBOUND_SUFFIXES)


def clean_path_token(value: str) -> str:
    return str(value or "").strip().strip("\"'`").rstrip(".,;:)]}>")


def resolve_candidate_path(value: str) -> Path:
    path = Path(clean_path_token(value)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def is_safe_outbound_file(path: Path) -> tuple[bool, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        return False, "not-a-file"
    if resolved.suffix.lower() not in OUTBOUND_SUFFIXES:
        return False, "unsupported-suffix"
    if ".private" in resolved.parts or resolved == PRIVATE or PRIVATE in resolved.parents:
        return False, "private-path"
    private_markers = {"wechat_decrypt", "xwechat_files", "cookies", "session", "tokens", "keys"}
    if any(marker in part.lower() for part in resolved.parts for marker in private_markers):
        return False, "sensitive-path"
    max_bytes = int(os.environ.get("WECHAT_WORKER_MAX_OUTBOUND_BYTES", DEFAULT_MAX_OUTBOUND_BYTES))
    try:
        if resolved.stat().st_size > max_bytes:
            return False, "too-large"
    except OSError:
        return False, "stat-failed"
    return True, ""


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def send_message(message: str, chat: str, send_targets: Path, *, target: dict[str, Any] | None = None) -> None:
    target = target if target is not None else guarded_send_target(chat, send_targets)
    if target:
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": message, "targets": [target]}, handle, ensure_ascii=False)
        try:
            run_send_subprocess(
                [
                    sys.executable,
                    str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
                    "--targets-file",
                    str(target_file),
                    "--send",
                    "--prefer-current",
                    "--pause",
                    os.environ.get("WECHAT_WORKER_SEND_PAUSE", "0.35"),
                    "--mirror-db",
                    str(DEFAULT_DB),
                ],
            )
        finally:
            target_file.unlink(missing_ok=True)
        return
    if os.environ.get("WECHAT_ALLOW_UNGUARDED_SEND", "0") != "1":
        raise RuntimeError(f"Refusing unguarded WeChat message send for {chat}: missing send_target")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--chat",
            chat,
            "--message",
            message,
        ],
        cwd=ROOT,
        check=False,
    )


def send_file(file_path: Path, chat: str, send_targets: Path, *, target: dict[str, Any] | None = None) -> None:
    ok, reason = is_safe_outbound_file(file_path)
    if not ok:
        raise ValueError(f"Refusing outbound file {file_path}: {reason}")
    target = target if target is not None else guarded_send_target(chat, send_targets)
    if target:
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": "", "targets": [target]}, handle, ensure_ascii=False)
        try:
            run_send_subprocess(
                [
                    sys.executable,
                    str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
                    "--targets-file",
                    str(target_file),
                    "--prefer-current",
                    "--pause",
                    os.environ.get("WECHAT_WORKER_SEND_PAUSE", "0.35"),
                ],
            )
        finally:
            target_file.unlink(missing_ok=True)
    elif os.environ.get("WECHAT_ALLOW_UNGUARDED_SEND", "0") != "1":
        raise RuntimeError(f"Refusing unguarded WeChat file send for {chat}: missing send_target")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--chat",
            chat,
            "--file",
            str(file_path.expanduser().resolve()),
        ],
        cwd=ROOT,
        check=False,
        env=wechat_send_env(),
    )


def run_send_subprocess(command: list[str], timeout: int = 60) -> None:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=wechat_send_env(),
    )
    if proc.returncode == 0:
        return
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parts = [f"send command failed with exit {proc.returncode}"]
    if stdout:
        parts.append(f"stdout={stdout[-1200:]}")
    if stderr:
        parts.append(f"stderr={stderr[-1200:]}")
    raise RuntimeError("; ".join(parts))


def wechat_send_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("WECHAT_INITIAL_TITLE_WAIT", os.environ.get("WECHAT_WORKER_INITIAL_TITLE_WAIT", "0.45"))
    env.setdefault("WECHAT_TITLE_RETRY_SECONDS", os.environ.get("WECHAT_WORKER_TITLE_RETRY_SECONDS", "3.2"))
    return env


def guarded_send_target(chat: str, path: Path, *, task: dict[str, Any] | None = None) -> dict[str, Any] | None:
    target = load_send_target(chat, path)
    if target is None:
        if os.environ.get("WECHAT_ALLOW_UNGUARDED_SEND", "0") == "1":
            return None
        raise RuntimeError(f"Refusing unguarded WeChat send for {chat}: missing send_target")
    validate_worker_send_route(task or {"chat": chat}, chat, target)
    return target


def validate_worker_send_route(task: dict[str, Any], target_chat: str, target: dict[str, Any]) -> None:
    route = task.get("route") if isinstance(task.get("route"), dict) else {}
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    errors: list[str] = []
    task_chat = str(task.get("chat") or "").strip()
    source_chat = str(source.get("chat") or "").strip()
    route_chat = str(route.get("chat") or "").strip()
    target_name = str(target.get("name") or target.get("target") or target.get("query") or "").strip()
    expected_title = str(target.get("expected_title") or target.get("title") or "").strip()
    route_target_name = str(route.get("send_target_name") or "").strip()
    route_expected_title = str(route.get("expected_title") or "").strip()
    if task_chat and task_chat != target_chat:
        errors.append(f"task.chat={task_chat!r} target_chat={target_chat!r}")
    if source_chat and source_chat != target_chat:
        errors.append(f"source.chat={source_chat!r} target_chat={target_chat!r}")
    if route_chat and route_chat != target_chat:
        errors.append(f"route.chat={route_chat!r} target_chat={target_chat!r}")
    if target_name and target_name != target_chat:
        errors.append(f"target.name={target_name!r} target_chat={target_chat!r}")
    if route_target_name and target_name and route_target_name != target_name:
        errors.append(f"route.target={route_target_name!r} resolved.target={target_name!r}")
    if route_expected_title and expected_title and route_expected_title != expected_title:
        errors.append(f"route.expected_title={route_expected_title!r} resolved.expected_title={expected_title!r}")
    if not expected_title and not target.get("expected_title_aliases"):
        errors.append("resolved target has no expected_title/aliases")
    if errors:
        raise RuntimeError("Refusing WeChat send route mismatch: " + "; ".join(errors))


def load_send_target(chat: str, path: Path) -> dict[str, Any] | None:
    direct_target = load_direct_config_send_target(chat)
    registry_target = None
    if not path.exists():
        return direct_target
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return direct_target
    raw = data.get(chat) if isinstance(data, dict) else None
    if isinstance(raw, dict):
        registry_target = raw
    if direct_target and registry_target:
        merged = {**registry_target, **direct_target}
        if not merged.get("fallback_clicks") and registry_target.get("fallback_clicks"):
            merged["fallback_clicks"] = registry_target["fallback_clicks"]
        return merged
    return direct_target or registry_target


def load_direct_config_send_target(chat: str) -> dict[str, Any] | None:
    for config_path in PRIVATE.glob("*direct-chatops.local.json"):
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("chat_name") or "") != chat:
            continue
        target = data.get("send_target")
        if isinstance(target, dict):
            return target
    return None


if __name__ == "__main__":
    raise SystemExit(main())
