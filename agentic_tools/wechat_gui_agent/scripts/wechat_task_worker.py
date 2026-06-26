#!/usr/bin/env python3
"""Worker-side helper for slower WeChat chatops tasks."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import html
import json
import os
from pathlib import Path
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request

from file_lock import fcntl_compat as fcntl
from wechat_agent_backend import run_agent_session as run_codex_session, select_agent_backend
from wechat_mirror import DEFAULT_DB, record_event
from wechat_routines import ensure_task_routine_contract, routine_prompt_context, write_routine_contract


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
LAZYEDIT_PUBLISH_SKILL = ROOT / "agentic_tools" / "wechat_gui_agent" / "skills" / "lazyedit-publish-workflow" / "SKILL.md"
LAZYEDIT_ROOT = Path(os.environ.get("LAZYEDIT_ROOT", "/home/lachlan/DiskMech/Projects/lazyedit"))
LAZYEDIT_API_URL = os.environ.get("LAZYEDIT_API_URL", "http://127.0.0.1:18787").rstrip("/")
LAZYEDIT_REMOTE_QUEUE_URL = os.environ.get("LAZYEDIT_REMOTE_QUEUE_URL", "http://lazyingart:8081/publish/queue")
LAZYEDIT_REMOTE_LOG_COMMAND = os.environ.get("WECHAT_WORKER_LAZYEDIT_REMOTE_LOG_COMMAND", "")
DEFAULT_AUTOPUBLISH_DIR = Path(os.environ.get("LABCANVAS_AUTOPUBLISH_DIR", "/home/lachlan/Nutstore Files/AutoPublish/AutoPublish"))
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"
DEFAULT_SEND_TARGETS = PRIVATE / "wechat_send_targets.local.json"
GUI_SEND_LOCK = PRIVATE / "wechat_gui_send.lock"
EFFORT_ORDER = ["low", "medium", "high", "xhigh"]
CLAIMED_STATUS = "in_progress"
SEND_DEFERRED_LOCKED_STATUS = "send_deferred_locked"
SEND_DEFERRED_ARTIFACT_STATUS = "send_deferred_artifact"
SEND_RETRYING_STATUS = "send_retrying"
GENERATED_VIDEO_WAITING_STATUS = "generation_waiting"
GENERATED_VIDEO_STALE_PAUSED_STATUS = "generation_stale_paused"
GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS = "generation_poststage_pending"
EXISTING_VIDEO_PUBLISH_PENDING_STATUS = "publish_poststage_pending"
DEFAULT_STALE_IN_PROGRESS_SECONDS = 60 * 60
DEFAULT_DEFERRED_SEND_BACKOFF_SECONDS = 5 * 60
DEFAULT_GENERATED_VIDEO_POLL_BACKOFF_SECONDS = 5 * 60
DEFAULT_GENERATED_VIDEO_WATCH_POLLS_PER_CYCLE = 1
DEFAULT_GENERATED_VIDEO_LAZYEDIT_TIMEOUT_SECONDS = 6 * 60 * 60
DEFAULT_GENERATED_VIDEO_LAZYEDIT_PROCESS_TIMEOUT_SECONDS = 3 * 60 * 60
DEFAULT_GENERATED_VIDEO_LAZYEDIT_PUBLISH_TIMEOUT_SECONDS = 3 * 60 * 60
DEFAULT_WORKER_MODEL = "gpt-5.5"
INTERRUPTIBLE_TASK_STATUSES = {
    "pending",
    CLAIMED_STATUS,
    GENERATED_VIDEO_WAITING_STATUS,
    GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS,
    EXISTING_VIDEO_PUBLISH_PENDING_STATUS,
    SEND_DEFERRED_ARTIFACT_STATUS,
    SEND_DEFERRED_LOCKED_STATUS,
    SEND_RETRYING_STATUS,
    "waiting_confirmation",
}
REQUEUE_ON_INTERRUPT_STATUSES = INTERRUPTIBLE_TASK_STATUSES - {CLAIMED_STATUS}
INTERRUPTIBLE_ROUTE_KINDS = {"story_or_script", "generate_video"}
INTERRUPTIBLE_ROUTINE_IDS = {"story_script_generation", "generated_video"}
DEFAULT_INTERRUPT_TARGET_MAX_AGE_SECONDS = 12 * 60 * 60
EFFORT_TIMEOUT_SECONDS = {
    "low": 120,
    "medium": 300,
    "high": 600,
    "xhigh": 1200,
}
OUTBOUND_SUFFIXES = {
    ".3mf",
    ".aac",
    ".amr",
    ".avi",
    ".bib",
    ".blend",
    ".bom",
    ".brep",
    ".csv",
    ".drl",
    ".dwg",
    ".dxf",
    ".docx",
    ".epub",
    ".fcstd",
    ".gbl",
    ".gbo",
    ".gbr",
    ".gbs",
    ".gif",
    ".gko",
    ".glb",
    ".gltf",
    ".gm1",
    ".gto",
    ".gts",
    ".gz",
    ".htm",
    ".html",
    ".iges",
    ".igs",
    ".ipynb",
    ".jpeg",
    ".jpg",
    ".json",
    ".jt",
    ".kicad_pcb",
    ".kicad_pro",
    ".kicad_sch",
    ".m4a",
    ".m4v",
    ".md",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".net",
    ".obj",
    ".ogg",
    ".opus",
    ".pdf",
    ".png",
    ".pos",
    ".pptx",
    ".py",
    ".scad",
    ".sch",
    ".step",
    ".stp",
    ".stl",
    ".svg",
    ".tar",
    ".tex",
    ".tif",
    ".tiff",
    ".tgz",
    ".txt",
    ".usdz",
    ".wav",
    ".webm",
    ".webp",
    ".xlsx",
    ".x_b",
    ".x_t",
    ".xln",
    ".zip",
}
DEFAULT_AUTO_SEND_SUFFIXES = set(OUTBOUND_SUFFIXES)
DEFAULT_MAX_OUTBOUND_BYTES = 100 * 1024 * 1024
MARKDOWN_PDF_COMPANION_SUFFIXES = {".md", ".markdown"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".amr", ".opus"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".svg"}
OCR_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
RAW_WECHAT_MEDIA_SUFFIXES = {".dat"}
PREFERRED_MEDIA_SUFFIXES = (
    IMAGE_SUFFIXES
    | VIDEO_SUFFIXES
    | AUDIO_SUFFIXES
    | RAW_WECHAT_MEDIA_SUFFIXES
    | {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".zip", ".7z", ".rar"}
)
DEFAULT_REQUIRED_DELIVERY_SUFFIXES = set(DEFAULT_AUTO_SEND_SUFFIXES)
GENERATED_VIDEO_PENDING_TERMS = (
    "submitted",
    "queued",
    "running",
    "generating",
    "waiting",
    "in progress",
    "continued",
    "poll",
    "monitor",
    "已提交",
    "已继续",
    "排队",
    "生成中",
    "等待",
    "监控",
)


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
    parser.add_argument("--reprocess", help="Reset an existing task to pending so the worker reruns it with current code.")
    parser.add_argument("--reason", default="", help="Reason recorded when reprocessing a task.")
    parser.add_argument("--flush-deferred", action="store_true", help="Try one deferred locked send without running new worker tasks.")
    parser.add_argument("--repair-missing-artifacts", action="store_true", help="Requeue completed tasks whose required media files were not sent.")
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

    if args.reprocess:
        task = reprocess_task(args.queue, args.reprocess, reason=args.reason)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.flush_deferred:
        return 0 if flush_one_deferred_send(args.queue, args.chat, send_targets=args.send_targets, log_idle=True) else 1

    if args.repair_missing_artifacts:
        payload = repair_missing_artifact_deliveries(args.queue)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.once or args.loop:
        while True:
            processed = process_one(args.queue, args.chat, send=args.send, send_targets=args.send_targets, log_idle=not args.loop)
            if not args.loop:
                return 0
            if not processed:
                import time

                time.sleep(args.poll_seconds)
        return 0
    raise SystemExit("Use --enqueue, --once, --loop, --resend, --reprocess, --flush-deferred, or --repair-missing-artifacts")


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


def reprocess_task(queue: Path, task_id: str, *, reason: str = "") -> dict[str, Any]:
    queue.parent.mkdir(parents=True, exist_ok=True)
    lock_path = queue.with_suffix(queue.suffix + ".lock")
    now_text = datetime.now().isoformat(timespec="seconds")
    stale_fields = [
        "status",
        "worker_id",
        "claimed_at",
        "completed_at",
        "result",
        "worker_error",
        "preflight",
        "routine",
        "routine_contract",
        "orchestrator",
        "worker_policy_attempts",
        "artifact_dir",
        "execution_contract",
        "skipped_files",
        "send_errors",
        "file_send_errors",
        "unsent_saved_files",
        "last_send_attempt_at",
        "send_deferred_reason",
        "sent_file_paths",
        "post_artifact_send_errors",
        "send_retry_claimed_at",
        "send_retry_count",
        "resent_at",
        "existing_video_publish_poststage",
        "next_publish_poststage_at",
        "publish_poststage_queued_at",
        "publish_poststage_last_status",
        "publish_poststage_last_outcome",
        "send_suppressed_reason",
        "send_suppressed_at",
    ]
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(queue)
        for index, task in enumerate(tasks):
            if str(task.get("id") or "") != str(task_id):
                continue
            previous = {
                "at": now_text,
                "reason": reason or "manual_reprocess",
                "previous_status": task.get("status"),
                "previous_worker_id": task.get("worker_id"),
                "previous_completed_at": task.get("completed_at"),
            }
            result = task.get("result") if isinstance(task.get("result"), dict) else {}
            if result:
                previous["previous_result_message_excerpt"] = collapse_context_text(result.get("message"), max_len=500)
            task.setdefault("reprocess_history", []).append(previous)
            for field in stale_fields:
                task.pop(field, None)
            task["status"] = "pending"
            task["reprocess_requested_at"] = now_text
            task["reprocess_reason"] = reason or "manual_reprocess"
            task["queue_path"] = str(queue)
            tasks[index] = task
            write_tasks(queue, tasks)
            return task
    raise SystemExit(f"No task found with id {task_id}")


def process_one(queue: Path, chat: str, *, send: bool, send_targets: Path = DEFAULT_SEND_TARGETS, log_idle: bool = True) -> bool:
    merged = merge_existing_pending_interruptions(queue)
    if merged:
        log_worker_event("interruption-merged", {"count": merged, "queue": str(queue)})
        return True
    adopted = adopt_active_generated_video_tasks(queue)
    if adopted:
        log_worker_event("generation-monitor-adopted", adopted)
        return True
    task = claim_next_pending(queue)
    if not task:
        if send and os.environ.get("WECHAT_WORKER_AUTO_FLUSH_DEFERRED", "1") == "1":
            return flush_one_deferred_send(queue, chat, send_targets=send_targets, log_idle=log_idle)
        if log_idle:
            print(json.dumps({"status": "no-pending-task"}, ensure_ascii=False))
        return False
    log_worker_event("claimed", task)
    task["queue_path"] = str(queue)
    ensure_runtime_instruction_contract(task)
    try:
        result_text = run_worker_codex(task)
        result = parse_worker_result(result_text)
        result = enforce_worker_result_contract(task, result, result_text)
        result = prepare_result_files(result, result_text)
    except Exception as exc:
        result_text = f"Worker failed before completion: {type(exc).__name__}: {str(exc)[:800]}"
        result = {"message": result_text, "confirmation": "", "files": [], "raw": result_text}
        task["worker_error"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
    if requeue_if_task_interrupted_during_run(queue, task):
        log_worker_event("stale-result-suppressed-for-interruption", task)
        return True
    target_chat = str(task.get("chat") or chat)
    send_now = send and should_send_worker_result(task, result)
    if send and not send_now:
        task["send_suppressed_reason"] = "nonterminal_routine_status"
        task["send_suppressed_at"] = datetime.now().isoformat(timespec="seconds")
    send_errors = send_result_with_retries(result, target_chat, send_targets, task=task) if send_now else []
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
    live_statuses = {GENERATED_VIDEO_WAITING_STATUS, GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS, EXISTING_VIDEO_PUBLISH_PENDING_STATUS}
    if task.get("status") in live_statuses:
        task["last_live_status_at"] = datetime.now().isoformat(timespec="seconds")
        if task.get("status") in {GENERATED_VIDEO_WAITING_STATUS, GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS}:
            task["last_generation_status_at"] = task["last_live_status_at"]
        task.pop("completed_at", None)
    else:
        task["completed_at"] = datetime.now().isoformat(timespec="seconds")
    task["result"] = result
    rewrite_task(queue, task)
    if send_errors and send_errors_indicate_deferable(send_errors):
        event_status = "send-deferred-locked"
    elif send_errors:
        event_status = "send-failed"
    elif task.get("status") == GENERATED_VIDEO_WAITING_STATUS:
        event_status = "generation-waiting"
    elif task.get("status") == GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS:
        event_status = "generation-poststage-pending"
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
    chat_filter = chat if chat and chat != "wechat-chat" else None
    task = claim_next_deferred_send(queue, chat_filter=chat_filter)
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
        result = refresh_existing_video_publish_deferred_result(task, result)
        task["result"] = result
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


def refresh_existing_video_publish_deferred_result(task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Re-probe publish state before retrying a deferred status message."""
    if not is_video_publish_task(task):
        return result
    poststage = task.get("existing_video_publish_poststage") if isinstance(task.get("existing_video_publish_poststage"), dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if not poststage and isinstance(data.get("poststage"), dict):
        poststage = data["poststage"]
    if not poststage:
        return result
    video_id = int_or_none(poststage.get("video_id"))
    if video_id is None:
        return result
    platforms = [str(item) for item in poststage.get("platforms") or detect_publish_platforms(task)]
    target = Path(str(poststage.get("target") or poststage.get("target_name") or ""))
    verification = verify_lazyedit_publish_stage(video_id, platforms, target, {"status": "probe"})
    old_stage = ""
    if isinstance(data.get("publish_stage"), dict):
        old_stage = str(data["publish_stage"].get("stage") or "")
    if not verification.get("verified") and str(verification.get("stage") or "") == old_stage:
        return result
    message = summarize_lazyedit_publish_outcome(video_id, platforms, target, {"status": "probe"}, verification=verification)
    payload: dict[str, Any] = {
        "message": message,
        "files": [],
        "confirmation": "",
        "publish_stage": verification,
    }
    confirmation = publish_stage_confirmation(verification)
    if confirmation:
        payload["confirmation"] = confirmation
        payload["poststage"] = poststage
    elif not bool(verification.get("verified")):
        payload["publish_poststage_retry"] = {
            "status": verification.get("stage") or "not_verified",
            "retry_seconds": publish_stage_retry_seconds(verification),
            "poststage": poststage,
            "outcome": {"status": "probe"},
        }
    task["publish_deferred_refresh_at"] = datetime.now().isoformat(timespec="seconds")
    task["publish_deferred_refresh_from"] = old_stage
    task["publish_deferred_refresh_to"] = verification.get("stage")
    return {
        "message": str(payload.get("message") or ""),
        "confirmation": str(payload.get("confirmation") or ""),
        "files": [],
        "raw": json.dumps(payload, ensure_ascii=False),
        "data": payload,
    }


def apply_send_outcome(task: dict[str, Any], result: dict[str, Any], errors: list[str]) -> None:
    if existing_video_publish_result_is_nonterminal(task, result):
        if errors:
            task["last_publish_progress_send_errors"] = errors
            task["last_publish_progress_send_attempt_at"] = datetime.now().isoformat(timespec="seconds")
        else:
            task.pop("last_publish_progress_send_errors", None)
        schedule_existing_video_publish_poststage(task, result)
        return
    if generated_video_result_is_nonterminal(task, result):
        if errors:
            task["last_progress_send_errors"] = errors
            task["last_progress_send_attempt_at"] = datetime.now().isoformat(timespec="seconds")
        else:
            task.pop("last_progress_send_errors", None)
        schedule_generated_video_poll(task, result)
        return
    if errors:
        task["send_errors"] = errors
        task["last_send_attempt_at"] = datetime.now().isoformat(timespec="seconds")
        if result_requires_file_delivery(task, result) and required_file_delivery_complete(task, result):
            task["post_artifact_send_errors"] = errors
            if send_errors_indicate_deferable(errors):
                task["status"] = SEND_DEFERRED_LOCKED_STATUS
                task["send_deferred_reason"] = send_deferred_reason_from_errors(errors)
            else:
                task["status"] = "send_failed"
            return
        if send_errors_indicate_deferable(errors):
            task["status"] = SEND_DEFERRED_LOCKED_STATUS
            task["send_deferred_reason"] = send_deferred_reason_from_errors(errors)
        elif result_requires_file_delivery(task, result):
            task["status"] = SEND_DEFERRED_ARTIFACT_STATUS
            task["send_deferred_reason"] = "required_artifact_delivery"
        else:
            task["status"] = "send_failed"
        return
    poststage = generated_video_poststage_from_result(result)
    if poststage:
        if generated_video_poststage_delivery_complete(task, poststage):
            task["status"] = GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS
            task["generated_video_poststage"] = poststage
            task["poststage_queued_at"] = datetime.now().isoformat(timespec="seconds")
            task.pop("send_errors", None)
            task.pop("send_deferred_reason", None)
        else:
            task["status"] = SEND_DEFERRED_ARTIFACT_STATUS
            task["send_deferred_reason"] = "required_artifact_delivery_before_poststage"
        return
    if result_requires_file_delivery(task, result) and not required_file_delivery_complete(task, result):
        task["status"] = SEND_DEFERRED_ARTIFACT_STATUS
        task["send_deferred_reason"] = "required_artifact_delivery"
        task["last_send_attempt_at"] = datetime.now().isoformat(timespec="seconds")
        return
    if result.get("confirmation"):
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        poststage = data.get("poststage") if isinstance(data.get("poststage"), dict) else {}
        if poststage and is_video_publish_task(task):
            task["existing_video_publish_poststage"] = poststage
            task["publish_poststage_blocked_at"] = datetime.now().isoformat(timespec="seconds")
    task["status"] = "waiting_confirmation" if result.get("confirmation") else "done"
    task.pop("send_errors", None)
    task.pop("send_deferred_reason", None)


def existing_video_publish_result_is_nonterminal(task: dict[str, Any], result: dict[str, Any]) -> bool:
    if not is_video_publish_task(task):
        return False
    return bool(existing_video_publish_poststage_retry_from_result(result))


def generated_video_result_is_nonterminal(task: dict[str, Any], result: dict[str, Any]) -> bool:
    if not is_generate_video_task(task):
        return False
    if result.get("confirmation"):
        return False
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if data.get("generated_video_download_ready"):
        return True
    if generated_video_poststage_retry_from_result(result):
        return True
    if generated_video_has_file(result):
        return False
    status_probe = ((task.get("preflight") or {}).get("generated_video_status") if isinstance(task.get("preflight"), dict) else None)
    if isinstance(status_probe, dict) and status_probe.get("status") in {"submitted", "running", "queued", "generating", "waiting", "download_ready"}:
        return True
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    text = generated_video_result_text(result)
    if "timeout" in text or "timed out" in text:
        return True
    if monitor.get("thread_url") and monitor.get("page_id") and worker_result_needs_escalation(text):
        return True
    return any(marker in text for marker in GENERATED_VIDEO_PENDING_TERMS)


def generated_video_has_file(result: dict[str, Any]) -> bool:
    return any(Path(str(path)).suffix.lower() in VIDEO_SUFFIXES for path in result.get("files") or [])


def result_requires_file_delivery(task: dict[str, Any] | None, result: dict[str, Any]) -> bool:
    if not result.get("files"):
        return False
    if result_is_file_intake_receipt(result):
        return False
    if os.environ.get("WECHAT_WORKER_REQUIRE_FILE_SEND", "0") == "1":
        return True
    route = task_route_decision(task or {})
    if route and str(route.get("route_kind") or "") == "research_or_summary":
        return bool((result.get("data") or {}).get("require_file_delivery")) if isinstance(result.get("data"), dict) else False
    if required_delivery_file_paths(result):
        return True
    if task is not None and is_generate_video_task(task) and generated_video_has_file(result):
        return True
    return bool((result.get("data") or {}).get("require_file_delivery")) if isinstance(result.get("data"), dict) else False


def required_delivery_suffixes() -> set[str]:
    raw = os.environ.get("WECHAT_WORKER_REQUIRED_FILE_SUFFIXES")
    if raw is None:
        return set(DEFAULT_REQUIRED_DELIVERY_SUFFIXES)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def required_delivery_file_paths(result: dict[str, Any]) -> list[Path]:
    suffixes = required_delivery_suffixes()
    if not suffixes:
        return []
    required: list[Path] = []
    for raw in result.get("files") or []:
        path = Path(str(raw))
        if path.suffix.lower() in suffixes:
            required.append(path.expanduser().resolve())
    return required


def required_file_delivery_complete(task: dict[str, Any] | None, result: dict[str, Any]) -> bool:
    required = {str(path) for path in required_delivery_file_paths(result)}
    if not required:
        return True
    sent = {str(Path(str(path)).expanduser().resolve()) for path in (task or {}).get("sent_file_paths", [])}
    return required.issubset(sent)


def generated_video_poststage_from_result(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    poststage = data.get("generated_video_poststage")
    return dict(poststage) if isinstance(poststage, dict) else {}


def generated_video_poststage_retry_from_result(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    retry = data.get("generated_video_poststage_retry")
    return dict(retry) if isinstance(retry, dict) else {}


def existing_video_publish_poststage_retry_from_result(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    retry = data.get("publish_poststage_retry")
    return dict(retry) if isinstance(retry, dict) else {}


def generated_video_poststage_delivery_complete(task: dict[str, Any], poststage: dict[str, Any]) -> bool:
    video_path = str(poststage.get("video_path") or "")
    if not video_path:
        return True
    try:
        resolved = str(Path(video_path).expanduser().resolve())
    except OSError:
        resolved = video_path
    sent_files = {str(item) for item in task.get("sent_file_paths") or []}
    return resolved in sent_files


def generated_video_result_text(result: dict[str, Any]) -> str:
    parts = [
        str(result.get("message") or ""),
        str(result.get("confirmation") or ""),
        str(result.get("raw") or ""),
        json.dumps(result.get("data") or {}, ensure_ascii=False),
    ]
    return "\n".join(parts).lower()


def schedule_generated_video_poll(task: dict[str, Any], result: dict[str, Any]) -> None:
    poststage_retry = generated_video_poststage_retry_from_result(result)
    if poststage_retry:
        try:
            retry_seconds = max(60.0, float(poststage_retry.get("retry_seconds") or 600))
        except (TypeError, ValueError):
            retry_seconds = 600.0
        now = datetime.now()
        task["status"] = GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS
        task["generated_video_poststage"] = poststage_retry.get("poststage") or task.get("generated_video_poststage") or {}
        task["next_poststage_at"] = (now + timedelta(seconds=retry_seconds)).timestamp()
        task["next_poststage_at_iso"] = datetime.fromtimestamp(float(task["next_poststage_at"])).isoformat(timespec="seconds")
        task["poststage_wait_count"] = int(task.get("poststage_wait_count") or 0) + 1
        task["poststage_last_status"] = poststage_retry.get("status") or "retry"
        task["poststage_last_outcome"] = poststage_retry.get("outcome") or {}
        task.pop("completed_at", None)
        return
    now = datetime.now()
    backoff = generated_video_next_poll_seconds(task, result)
    task["status"] = GENERATED_VIDEO_WAITING_STATUS
    task["next_poll_at"] = (now.timestamp() + max(1, backoff))
    task["next_poll_at_iso"] = datetime.fromtimestamp(float(task["next_poll_at"])).isoformat(timespec="seconds")
    task["generation_wait_count"] = int(task.get("generation_wait_count") or 0) + 1
    monitor = merge_generated_video_monitor(
        task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {},
        result,
    )
    if not (monitor.get("thread_url") and monitor.get("page_id")):
        discovered = discover_generated_video_monitor_from_browser(task)
        if discovered:
            monitor.update(discovered)
    task["generated_video_monitor"] = monitor
    task.setdefault("generation_started_at", now.isoformat(timespec="seconds"))


def schedule_existing_video_publish_poststage(task: dict[str, Any], result: dict[str, Any]) -> None:
    retry = existing_video_publish_poststage_retry_from_result(result)
    try:
        retry_seconds = max(60.0, float(retry.get("retry_seconds") or os.environ.get("WECHAT_WORKER_EXISTING_VIDEO_PUBLISH_RETRY_SECONDS", "600")))
    except (TypeError, ValueError):
        retry_seconds = 600.0
    now = datetime.now()
    task["status"] = EXISTING_VIDEO_PUBLISH_PENDING_STATUS
    task["existing_video_publish_poststage"] = retry.get("poststage") or task.get("existing_video_publish_poststage") or {}
    task["publish_poststage_queued_at"] = now.isoformat(timespec="seconds")
    task["next_publish_poststage_at"] = (now + timedelta(seconds=retry_seconds)).timestamp()
    task["next_publish_poststage_at_iso"] = datetime.fromtimestamp(float(task["next_publish_poststage_at"])).isoformat(timespec="seconds")
    task["publish_poststage_wait_count"] = int(task.get("publish_poststage_wait_count") or 0) + 1
    task["publish_poststage_last_status"] = retry.get("status") or retry.get("stage") or "retry"
    task["publish_poststage_last_outcome"] = retry.get("outcome") or {}
    task.pop("completed_at", None)
    task.pop("send_errors", None)
    task.pop("send_deferred_reason", None)


def generated_video_next_poll_seconds(task: dict[str, Any], result: dict[str, Any] | None = None) -> int:
    env_value = os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_POLL_BACKOFF_SECONDS")
    if env_value:
        try:
            return max(10, int(env_value))
        except ValueError:
            pass
    status_text = generated_video_result_text(result or {})
    status_probe = ((task.get("preflight") or {}).get("generated_video_status") if isinstance(task.get("preflight"), dict) else None)
    if isinstance(status_probe, dict):
        if status_probe.get("status") == "download_ready":
            return int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_DOWNLOAD_READY_POLL_SECONDS", "30"))
        status_text += "\n" + str(status_probe.get("status_text") or "")
    return generated_video_status_backoff_seconds(status_text, task_focus_text(task))


def generated_video_status_backoff_seconds(status_text: str, request_text: str = "") -> int:
    text = f"{status_text}\n{request_text}".lower()
    hour_match = re.search(r"还需\s*(\d+)\s*(?:小时|小時)", text)
    if not hour_match:
        hour_match = re.search(r"(?:about|around|approximately|approx\.?|roughly)?\s*(\d+)\s*(?:h|hr|hrs|hour|hours)\b", text)
    if hour_match:
        hours = int(hour_match.group(1))
        return max(300, min(1800, int(hours * 60 * 60 * 0.35)))
    minute_match = re.search(r"还需\s*(\d+)\s*分钟", text)
    if not minute_match:
        minute_match = re.search(r"(?:about|around|approximately|approx\.?|roughly)?\s*(\d+)\s*(?:m|min|mins|minute|minutes)\b", text)
    if minute_match:
        minutes = int(minute_match.group(1))
        return max(60, min(900, int(minutes * 60 * 0.65)))
    if "排队" in text or "queued" in text:
        return 300
    if "生成中" in text or "generating" in text or "running" in text:
        return 120
    if "download_ready" in text or "final_video.mp4" in text or "下载" in text:
        return 30
    duration_match = re.search(r"(\d+)\s*(?:s|sec|second|seconds|秒)", text)
    if duration_match and int(duration_match.group(1)) >= 30:
        return 180
    return DEFAULT_GENERATED_VIDEO_POLL_BACKOFF_SECONDS


def merge_generated_video_monitor(existing: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    monitor = dict(existing)
    payload = result.get("data") if isinstance(result.get("data"), dict) else {}
    candidates = [
        payload,
        payload.get("generation") if isinstance(payload.get("generation"), dict) else {},
        payload.get("generated_video") if isinstance(payload.get("generated_video"), dict) else {},
        payload.get("monitor") if isinstance(payload.get("monitor"), dict) else {},
    ]
    for candidate in candidates:
        for key in ("thread_url", "page_id", "cdp_url", "output_dir", "filename", "story_file", "prompt_file"):
            value = candidate.get(key) if isinstance(candidate, dict) else None
            if value:
                monitor[key] = str(value)
    raw = "\n".join(
        [
            str(result.get("message") or ""),
            str(result.get("raw") or ""),
            json.dumps(payload, ensure_ascii=False),
        ]
    )
    if "thread_url" not in monitor:
        match = re.search(r"https?://[^\s\"'<>]+(?:thread_id|pippit_video_part_agent)[^\s\"'<>]*", raw)
        if match:
            monitor["thread_url"] = clean_url_token(match.group(0))
    if "page_id" not in monitor:
        match = re.search(r"(?:page[-_ ]?id|PAGE_ID)\s*[:=]\s*([0-9A-Za-z_-]{6,})", raw, flags=re.I)
        if match:
            monitor["page_id"] = match.group(1)
    monitor["last_status"] = collapse_context_text(result.get("message") or result.get("raw") or "", max_len=800)
    monitor["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return monitor


def clean_url_token(value: str) -> str:
    return str(value or "").strip().strip("\"'`").rstrip(".,;:)]}>")


def discover_generated_video_monitor_from_browser(task: dict[str, Any]) -> dict[str, str]:
    probe_monitor = discover_generated_video_monitor_from_probe(task)
    if probe_monitor:
        return probe_monitor
    cdp_url = os.environ.get("WECHAT_WORKER_XYQ_CDP_URL") or os.environ.get("XYQ_CDP_URL") or "http://127.0.0.1:9222"
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/list", timeout=5) as response:
            pages = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {}
    if not isinstance(pages, list):
        return {}
    candidates: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict) or page.get("type") != "page":
            continue
        url = str(page.get("url") or "")
        if "xyq.jianying.com" not in url or "thread_id=" not in url:
            continue
        candidates.append(page)
    if not candidates:
        return {}
    request_text = task_focus_text(task).lower()
    if "lalachan" in request_text or "小云雀" in request_text or "seedance" in request_text:
        preferred = [
            page for page in candidates
            if "pippit_nest_agent" in str(page.get("url") or "")
            or "integrated-agent" in str(page.get("url") or "")
        ]
        if preferred:
            candidates = preferred
    page = candidates[0]
    return {
        "cdp_url": cdp_url,
        "page_id": str(page.get("id") or ""),
        "thread_url": str(page.get("url") or ""),
        "title": str(page.get("title") or ""),
        "discovered_from": "chrome_cdp_pages",
        "discovered_at": datetime.now().isoformat(timespec="seconds"),
    }


def page_id_for_thread_url(cdp_url: str, thread_url: str) -> str:
    thread_id = extract_xyq_thread_id(thread_url)
    if not thread_id:
        return ""
    try:
        with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/list", timeout=5) as response:
            pages = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return ""
    if not isinstance(pages, list):
        return ""
    for page in pages:
        if not isinstance(page, dict):
            continue
        if extract_xyq_thread_id(str(page.get("url") or "")) == thread_id:
            return str(page.get("id") or "")
    return ""


def extract_xyq_thread_id(url: str) -> str:
    match = re.search(r"[?&]thread_id=([^&]+)", str(url or ""))
    return match.group(1) if match else ""


def send_errors_indicate_wechat_locked(errors: list[str]) -> bool:
    text = "\n".join(str(error) for error in errors).lower()
    return "wechat_locked" in text or "weixin for linux is locked" in text or "unlock on phone" in text


def send_errors_indicate_gui_busy(errors: list[str]) -> bool:
    text = "\n".join(str(error) for error in errors).lower()
    return "wechat_send_busy" in text or "serialized gui sender is already sending" in text


def send_errors_indicate_gui_timeout(errors: list[str]) -> bool:
    text = "\n".join(str(error) for error in errors).lower()
    return "wechat_send_timeout" in text or "timed out after" in text


def send_errors_indicate_wechat_entry_required(errors: list[str]) -> bool:
    text = "\n".join(str(error) for error in errors).lower()
    return "wechat_entry_required" in text or "not in the main chat ui" in text


def send_errors_indicate_blank_title_guard(errors: list[str]) -> bool:
    text = "\n".join(str(error) for error in errors).lower()
    if "opened chat title guard failed" not in text:
        return False
    if "ocr=''" in text or 'ocr=""' in text:
        return True
    for match in re.finditer(r"ocr=(['\"])(.*?)\1", text, flags=re.DOTALL):
        observed = match.group(2).replace("\\n", "").replace("\\r", "")
        compact = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", observed)
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", compact))
        if not compact or ((not has_cjk and len(compact) <= 3) or compact in {"3oo", "30o", "3o0", "300"}):
            return True
    return False


def send_errors_indicate_deferable(errors: list[str]) -> bool:
    return (
        send_errors_indicate_wechat_locked(errors)
        or send_errors_indicate_gui_busy(errors)
        or send_errors_indicate_gui_timeout(errors)
        or send_errors_indicate_wechat_entry_required(errors)
        or send_errors_indicate_blank_title_guard(errors)
    )


def send_deferred_reason_from_errors(errors: list[str]) -> str:
    if send_errors_indicate_gui_busy(errors):
        return "gui_send_busy"
    if send_errors_indicate_gui_timeout(errors):
        return "gui_send_timeout"
    if send_errors_indicate_wechat_entry_required(errors):
        return "wechat_entry_required"
    if send_errors_indicate_blank_title_guard(errors):
        return "title_guard_blank"
    return "wechat_locked"


def should_send_worker_result(task: dict[str, Any], result: dict[str, Any]) -> bool:
    if existing_video_publish_result_is_nonterminal(task, result):
        return os.environ.get("WECHAT_WORKER_SEND_PUBLISH_PROGRESS", "0") == "1"
    if not generated_video_result_is_nonterminal(task, result):
        return True
    return os.environ.get("WECHAT_WORKER_SEND_GENERATION_PROGRESS", "0") == "1"


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
            if send_errors_indicate_deferable(errors):
                break
            if attempt < attempts and delay:
                import time

                time.sleep(delay)
    if task is not None and android_text_fallback_allowed(task, result, errors):
        try:
            send_result_text_via_android_fallback(result, target_chat, task)
            return []
        except Exception as exc:
            errors.append(f"android fallback: {type(exc).__name__}: {str(exc)[:500]}")
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
    require_file_delivery = result_requires_file_delivery(task, result)
    file_errors = []
    sent_files = {str(path) for path in (task or {}).get("sent_file_paths", [])}

    def send_files() -> None:
        nonlocal file_errors
        for file_path in files_to_send:
            resolved = str(file_path.expanduser().resolve())
            if resolved in sent_files:
                continue
            try:
                send_file(file_path, target_chat, send_targets, target=target)
                sent_files.add(resolved)
                if task is not None:
                    task["sent_file_paths"] = sorted(sent_files)
            except Exception as exc:
                error = {"path": str(file_path), "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
                file_errors.append(error)
                if require_file_delivery:
                    break
                if os.environ.get("WECHAT_WORKER_REQUIRE_FILE_SEND", "0") == "1":
                    break
        if file_errors and task is not None:
            task.setdefault("file_send_errors", []).extend(file_errors)
        if file_errors and require_file_delivery:
            detail = "; ".join(f"{item['path']}: {item['error']}" for item in file_errors[:3])
            raise RuntimeError(f"required artifact delivery failed: {detail}")
        if require_file_delivery and task is not None and not required_file_delivery_complete(task, result):
            missing = sorted(set(str(path) for path in required_delivery_file_paths(result)) - sent_files)
            detail = "; ".join(missing[:3])
            raise RuntimeError(f"required artifact delivery incomplete: {detail}")

    if require_file_delivery:
        send_files()
    if message:
        send_message(message, target_chat, send_targets, target=target)
    if result["confirmation"]:
        send_message(result["confirmation"], target_chat, send_targets, target=target)
    if not require_file_delivery:
        send_files()


def android_text_fallback_allowed(task: dict[str, Any], result: dict[str, Any], errors: list[str]) -> bool:
    if os.environ.get("WECHAT_WORKER_ANDROID_TEXT_FALLBACK", "1") != "1":
        return False
    if not errors or not send_errors_indicate_deferable(errors):
        return False
    if not (verified_publish_send_completion(task) or verified_publish_result_completion(result)):
        return False
    if result.get("files"):
        return False
    return bool(android_publish_completion_message(result))


def android_publish_completion_message(result: dict[str, Any]) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    publish_stage = data.get("publish_stage") if isinstance(data.get("publish_stage"), dict) else {}
    if not (publish_stage.get("verified") or str(publish_stage.get("stage") or "") == "published_verified"):
        return ""
    video_id = publish_stage.get("video_id")
    platforms = [str(item) for item in publish_stage.get("verified_platforms") or publish_stage.get("requested_platforms") or []]
    local_jobs = publish_stage.get("local_jobs") if isinstance(publish_stage.get("local_jobs"), list) else []
    remote_jobs = publish_stage.get("remote_jobs") if isinstance(publish_stage.get("remote_jobs"), list) else []
    local_job = next((item for item in local_jobs if isinstance(item, dict)), {})
    remote_job = next((item for item in remote_jobs if isinstance(item, dict)), {})
    local_id = local_job.get("id") or ""
    remote_id = remote_job.get("id") or local_job.get("remote_job_id") or ""
    parts = ["Published OK"]
    if video_id not in (None, ""):
        parts.append(f"video_id {video_id}")
    if platforms:
        parts.append(f"platforms {' '.join(platforms)} done")
    if local_id:
        parts.append(f"LazyEdit job {local_id}")
    if remote_id:
        parts.append(f"remote job {remote_id}")
    return sanitize_android_input_text(". ".join(parts) + ".")


def send_result_text_via_android_fallback(result: dict[str, Any], target_chat: str, task: dict[str, Any]) -> None:
    message = android_publish_completion_message(result)
    if not message:
        raise RuntimeError("no android fallback message")
    adb = os.environ.get("ADB", "adb")
    serial = resolve_android_serial(adb, os.environ.get("ANDROID_SERIAL", ""))
    require_android_tools(adb)
    android_shell(adb, serial, ["input", "keyevent", "224"], check=False)
    android_shell(adb, serial, ["wm", "dismiss-keyguard"], check=False)
    android_shell(adb, serial, ["svc", "power", "stayon", "true"], check=False)
    before = android_screenshot(adb, serial, task, "before-send")
    ocr_text = android_header_ocr(before)
    if not android_title_matches(target_chat, ocr_text):
        raise RuntimeError(f"android target title guard failed for {target_chat}: OCR={ocr_text!r}")
    tap = parse_xy_env("WECHAT_WORKER_ANDROID_COMPOSER_TAP", (430, 2035))
    android_shell(adb, serial, ["input", "tap", str(tap[0]), str(tap[1])])
    time.sleep(float(os.environ.get("WECHAT_WORKER_ANDROID_AFTER_TAP_DELAY", "0.6")))
    android_shell(adb, serial, ["input", "text", android_input_token(message)])
    time.sleep(float(os.environ.get("WECHAT_WORKER_ANDROID_AFTER_TEXT_DELAY", "0.6")))
    typed = android_screenshot(adb, serial, task, "typed")
    send_tap = parse_xy_env("WECHAT_WORKER_ANDROID_SEND_TAP", (980, 1275))
    android_shell(adb, serial, ["input", "tap", str(send_tap[0]), str(send_tap[1])])
    time.sleep(float(os.environ.get("WECHAT_WORKER_ANDROID_AFTER_SEND_DELAY", "1.0")))
    after = android_screenshot(adb, serial, task, "sent")
    task["android_text_fallback_send"] = {
        "sent_at": datetime.now().isoformat(timespec="seconds"),
        "serial": serial,
        "chat": target_chat,
        "ocr_title": ocr_text,
        "message": message,
        "screenshots": {
            "before": str(before),
            "typed": str(typed),
            "after": str(after),
        },
    }


def require_android_tools(adb: str) -> None:
    missing = [tool for tool in (adb, "convert", "tesseract") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(f"android fallback missing tools: {', '.join(missing)}")


def resolve_android_serial(adb: str, serial: str) -> str:
    if serial:
        state = subprocess.run([adb, "-s", serial, "get-state"], capture_output=True, text=True, check=False)
        if state.returncode == 0 and state.stdout.strip() == "device":
            return serial
        raise RuntimeError(f"android device {serial} is not available")
    proc = subprocess.run([adb, "devices"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"adb devices failed: {(proc.stderr or proc.stdout).strip()[:300]}")
    devices = [line.split()[0] for line in proc.stdout.splitlines()[1:] if len(line.split()) >= 2 and line.split()[1] == "device"]
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise RuntimeError("no authorized android device available")
    raise RuntimeError(f"multiple android devices available: {', '.join(devices)}")


def android_shell(adb: str, serial: str, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run([adb, "-s", serial, "shell", *command], capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"adb shell failed: {' '.join(command)}: {(proc.stderr or proc.stdout).strip()[:300]}")
    return proc


def android_screenshot(adb: str, serial: str, task: dict[str, Any], label: str) -> Path:
    out_dir = ROOT / "output" / "android_device_agent" / datetime.now().strftime("%F")
    out_dir.mkdir(parents=True, exist_ok=True)
    task_id = safe_slug(str(task.get("id") or "task"))
    path = out_dir / f"{task_id}-{label}-{datetime.now().strftime('%H%M%S')}.png"
    proc = subprocess.run([adb, "-s", serial, "exec-out", "screencap", "-p"], capture_output=True, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace") if isinstance(proc.stderr, bytes) else str(proc.stderr)
        raise RuntimeError(f"android screenshot failed: {err[:300]}")
    path.write_bytes(proc.stdout)
    return path


def android_header_ocr(screenshot: Path) -> str:
    crop = os.environ.get("WECHAT_WORKER_ANDROID_HEADER_CROP", "720x140+180+80")
    langs = os.environ.get("WECHAT_WORKER_ANDROID_OCR_LANGS", "chi_sim+chi_tra+eng")
    psm = os.environ.get("WECHAT_WORKER_ANDROID_OCR_PSM", "6")
    header = screenshot.with_name(f"{screenshot.stem}-header.png")
    proc = subprocess.run(["convert", str(screenshot), "-crop", crop, str(header)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"android header crop failed: {(proc.stderr or proc.stdout).strip()[:300]}")
    ocr = subprocess.run(["tesseract", str(header), "stdout", "-l", langs, "--psm", psm], capture_output=True, text=True, check=False)
    if ocr.returncode != 0:
        raise RuntimeError(f"android header OCR failed: {(ocr.stderr or ocr.stdout).strip()[:300]}")
    return ocr.stdout.strip()


def android_title_matches(target_chat: str, ocr_text: str) -> bool:
    return normalize_android_title(target_chat) in normalize_android_title(ocr_text)


def normalize_android_title(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value)


def sanitize_android_input_text(value: str) -> str:
    ascii_text = value.encode("ascii", errors="ignore").decode("ascii")
    ascii_text = re.sub(r"[^A-Za-z0-9 .,;:!?_/@#+=()\\-]+", " ", ascii_text)
    return re.sub(r"\s+", " ", ascii_text).strip()


def android_input_token(value: str) -> str:
    text = sanitize_android_input_text(value)
    if not text:
        raise RuntimeError("android input text is empty after sanitization")
    return text.replace("%", "%25").replace(" ", "%s")


def parse_xy_env(name: str, default: tuple[int, int]) -> tuple[int, int]:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 2:
        return default
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return default


def partition_result_files_for_wechat(files: list[str]) -> tuple[list[Path], list[Path]]:
    if os.environ.get("WECHAT_WORKER_SEND_FILES", "1") != "1":
        return [], [Path(path) for path in files]
    raw_suffixes = os.environ.get("WECHAT_WORKER_AUTO_SEND_SUFFIXES")
    suffixes = DEFAULT_AUTO_SEND_SUFFIXES
    if raw_suffixes:
        suffixes = {item.strip().lower() for item in raw_suffixes.split(",") if item.strip()}
    send: list[Path] = []
    note: list[Path] = []
    for raw in add_markdown_pdf_companions(files):
        path = Path(raw)
        if path.suffix.lower() in suffixes:
            send.append(path)
        else:
            note.append(path)
    return send, note


def add_markdown_pdf_companions(files: list[str]) -> list[str]:
    if os.environ.get("WECHAT_MARKDOWN_PDF_COMPANIONS", "1") == "0":
        return [str(path) for path in files]
    expanded: list[str] = []
    for raw in files:
        path_text = str(raw or "").strip()
        if not path_text:
            continue
        expanded.append(path_text)
        companion = ensure_markdown_pdf_companion(Path(path_text))
        if companion:
            expanded.append(str(companion))
    return unique_strings(expanded)


def ensure_markdown_pdf_companion(path: Path) -> Path | None:
    source = path.expanduser()
    if source.suffix.lower() not in MARKDOWN_PDF_COMPANION_SUFFIXES:
        return None
    if not source.is_absolute():
        source = (ROOT / source).resolve()
    if not source.is_file():
        return None
    output = source.with_suffix(".pdf")
    try:
        if output.is_file() and output.stat().st_size > 0 and output.stat().st_mtime >= source.stat().st_mtime:
            return output
    except OSError:
        pass
    try:
        return render_markdown_pdf(source, output)
    except Exception:
        return None


def render_markdown_pdf(source: Path, output: Path) -> Path | None:
    pandoc = shutil.which(os.environ.get("WECHAT_MARKDOWN_PDF_PANDOC", "pandoc"))
    if not pandoc:
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_output = output.with_name(f"{output.stem}.tmp.pdf")
    tmp_output.unlink(missing_ok=True)
    command = [
        pandoc,
        str(source),
        "-o",
        str(tmp_output),
        "--standalone",
        "--pdf-engine",
        os.environ.get("WECHAT_MARKDOWN_PDF_ENGINE", "xelatex"),
        "-V",
        f"mainfont={os.environ.get('WECHAT_MARKDOWN_PDF_MAINFONT', 'Noto Sans CJK SC')}",
        "-V",
        f"CJKmainfont={os.environ.get('WECHAT_MARKDOWN_PDF_CJKFONT', 'Noto Sans CJK SC')}",
        "-V",
        f"monofont={os.environ.get('WECHAT_MARKDOWN_PDF_MONOFONT', 'DejaVu Sans Mono')}",
        "-V",
        os.environ.get("WECHAT_MARKDOWN_PDF_GEOMETRY", "geometry:margin=18mm"),
    ]
    timeout = int(os.environ.get("WECHAT_MARKDOWN_PDF_TIMEOUT_SECONDS", "120"))
    proc = subprocess.run(command, cwd=str(source.parent), capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0 or not tmp_output.is_file() or tmp_output.stat().st_size <= 0:
        tmp_output.unlink(missing_ok=True)
        return None
    tmp_output.replace(output)
    return output


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


def merge_existing_pending_interruptions(path: Path) -> int:
    """Fold queued same-chat follow-ups into the active story/video task.

    This handles follow-ups that were queued before the latest monitor code was
    loaded, and keeps one per-chat worker session responsible for the evolving
    story/video workflow.
    """
    if not path.exists():
        return 0
    lock_path = path.with_suffix(path.suffix + ".lock")
    now_text = datetime.now().isoformat(timespec="seconds")
    merged = 0
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(path)
        for incoming_index, incoming in enumerate(list(tasks)):
            if str(incoming.get("status") or "") != "pending" or not is_interruptible_story_video_task(incoming):
                continue
            target_index = find_interruption_target_index(tasks, incoming_index)
            if target_index is None:
                continue
            target = tasks[target_index]
            incoming_source = incoming.get("source") if isinstance(incoming.get("source"), dict) else {}
            if interruption_already_recorded(target, incoming_source):
                incoming["status"] = "canceled_superseded"
                incoming["completed_at"] = now_text
                incoming["superseded_by"] = target.get("id")
                incoming["superseded_reason"] = "same_chat_interruption_already_recorded"
                tasks[incoming_index] = incoming
                merged += 1
                continue
            interruption = build_task_interruption(target, incoming)
            if is_manual_generated_video_handoff_update(interruption.get("request") or interruption.get("request_excerpt") or ""):
                apply_manual_generated_video_handoff(target, incoming, interruption)
                incoming["status"] = "canceled_superseded"
                incoming["completed_at"] = now_text
                incoming["superseded_at"] = now_text
                incoming["superseded_by"] = target.get("id")
                incoming["superseded_reason"] = "manual_generated_video_handoff_recorded"
                tasks[target_index] = target
                tasks[incoming_index] = incoming
                merged += 1
                continue
            target.setdefault("interruptions", []).append(interruption)
            target["interruptions"] = target["interruptions"][-20:]
            target["interruption_pending"] = True
            target["interruption_count"] = len(target["interruptions"])
            target["last_interruption_at"] = interruption["at"]
            target["last_interruption_source"] = interruption["source"]
            target["interruption_policy"] = story_video_interruption_policy()
            target["request"] = append_interruption_notice_to_request(target.get("request"), interruption)
            promote_story_target_for_generation_interruption(target, interruption)
            status = str(target.get("status") or "")
            if status in REQUEUE_ON_INTERRUPT_STATUSES:
                target["status"] = "pending"
                target["reprocess_requested_at"] = interruption["at"]
                target["reprocess_reason"] = "same_chat_interruption"
                for field in (
                    "completed_at",
                    "claimed_at",
                    "worker_id",
                    "result",
                    "send_suppressed_reason",
                    "next_poll_at",
                    "next_poststage_at",
                    "next_publish_poststage_at",
                ):
                    target.pop(field, None)
            elif status == CLAIMED_STATUS:
                target["interrupt_requested_at"] = interruption["at"]
                target["interrupt_delivery"] = "suppress_current_result_and_requeue_when_worker_turn_returns"
            incoming["status"] = "canceled_superseded"
            incoming["completed_at"] = now_text
            incoming["superseded_at"] = now_text
            incoming["superseded_by"] = target.get("id")
            incoming["superseded_reason"] = "merged_as_same_chat_interruption"
            tasks[target_index] = target
            tasks[incoming_index] = incoming
            merged += 1
        if merged:
            write_tasks(path, tasks)
        fcntl.flock(lock, fcntl.LOCK_UN)
    return merged


def find_interruption_target_index(tasks: list[dict[str, Any]], incoming_index: int) -> int | None:
    incoming = tasks[incoming_index]
    for target_index in range(incoming_index - 1, -1, -1):
        target = tasks[target_index]
        if same_chat_interruption_target(target, incoming):
            return target_index
    return None


def same_chat_interruption_target(target: dict[str, Any], incoming: dict[str, Any]) -> bool:
    if not is_interruptible_story_video_task(target):
        return False
    if str(target.get("status") or "") not in INTERRUPTIBLE_TASK_STATUSES:
        return False
    if str(target.get("chat") or "") != str(incoming.get("chat") or ""):
        return False
    target_source = target.get("source") if isinstance(target.get("source"), dict) else {}
    incoming_source = incoming.get("source") if isinstance(incoming.get("source"), dict) else {}
    if not same_optional_field(target_source, incoming_source, "message_table"):
        return False
    if not same_optional_field(target_source, incoming_source, "config_id"):
        return False
    if not interruption_target_recent_enough(target, incoming):
        return False
    target_local_id = int_or_none(target_source.get("local_id"))
    incoming_local_id = int_or_none(incoming_source.get("local_id"))
    if target_local_id is None or incoming_local_id is None or incoming_local_id <= target_local_id:
        return False
    return True


def same_optional_field(left: dict[str, Any], right: dict[str, Any], key: str) -> bool:
    left_value = str(left.get(key) or "")
    right_value = str(right.get(key) or "")
    return not (left_value and right_value and left_value != right_value)


def interruption_target_recent_enough(target: dict[str, Any], incoming: dict[str, Any]) -> bool:
    max_age = int(os.environ.get("WECHAT_WORKER_INTERRUPT_TARGET_MAX_AGE_SECONDS", str(DEFAULT_INTERRUPT_TARGET_MAX_AGE_SECONDS)))
    if max_age <= 0:
        return True
    target_ts = task_event_timestamp(target)
    incoming_ts = task_event_timestamp(incoming)
    if target_ts is None or incoming_ts is None:
        return True
    return 0 <= incoming_ts - target_ts <= max_age


def task_event_timestamp(task: dict[str, Any]) -> float | None:
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    for raw in (
        source.get("create_time"),
        task.get("created_at"),
        task.get("last_interruption_at"),
        task.get("claimed_at"),
    ):
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
        if isinstance(raw, str):
            as_float = float_or_none(raw)
            if as_float:
                return as_float
            parsed = parse_iso_datetime(raw)
            if parsed:
                return parsed.timestamp()
    return None


def is_interruptible_story_video_task(task: dict[str, Any]) -> bool:
    route = task_route_decision(task)
    routine = task.get("routine") if isinstance(task.get("routine"), dict) else {}
    route_kind = str(route.get("route_kind") or "")
    routine_id = str(routine.get("id") or "")
    project = str(route.get("project") or "").lower()
    if route_kind in INTERRUPTIBLE_ROUTE_KINDS or routine_id in INTERRUPTIBLE_ROUTINE_IDS or project == "lalachan":
        return True
    text = str(task.get("request") or "").lower()
    return any(marker in text for marker in ("lalachan", "raraxia", "ayachan", "sasakun", "小云雀", "啦啦侠", "阿芽酱", "飒飒君"))


def is_manual_generated_video_handoff_update(text: str) -> bool:
    lowered = str(text or "").lower()
    video_context = any(marker in lowered for marker in ("xyq", "xiaoyunque", "小云雀", "video", "mp4", "视频", "影片"))
    manual_download = any(
        marker in lowered
        for marker in (
            "already downloaded",
            "downloaded the two",
            "downloaded both",
            "i downloaded",
            "i have downloaded",
            "saved to downloads",
            "to downloads",
            "在 downloads",
            "已下载",
            "已经下载",
            "下載好了",
            "下载好了",
        )
    )
    handoff_or_no_action = any(
        marker in lowered
        for marker in (
            "lazyedit",
            "give lazyedit",
            "gave lazyedit",
            "handed",
            "handoff",
            "publish",
            "publishing",
            "do nothing",
            "need to do nothing",
            "no need",
            "just let you know",
            "不用",
            "不需要",
            "交给",
            "交給",
            "发布",
            "發布",
        )
    )
    return bool(video_context and manual_download and handoff_or_no_action)


def manual_generated_video_handoff_payload(text: str) -> dict[str, Any]:
    lowered = str(text or "").lower()
    count = 0
    if any(marker in lowered for marker in ("two", "both", "2 videos", "2个", "两个", "兩個", "两条", "兩條")):
        count = 2
    return {
        "kind": "manual_generated_video_handoff",
        "reported_at": datetime.now().isoformat(timespec="seconds"),
        "reported_video_count": count or None,
        "downloads_dir_reported": "downloads" in lowered,
        "lazyedit_handoff_reported": "lazyedit" in lowered,
        "automation_action": "none",
        "note": collapse_context_text(text, max_len=1000),
    }


def apply_manual_generated_video_handoff(candidate: dict[str, Any], incoming: dict[str, Any], interruption: dict[str, Any]) -> None:
    payload = manual_generated_video_handoff_payload(interruption.get("request") or interruption.get("request_excerpt") or "")
    payload.update(
        {
            "incoming_task_id": incoming.get("id"),
            "source": interruption.get("source") if isinstance(interruption.get("source"), dict) else {},
            "target_task_id": candidate.get("id"),
        }
    )
    candidate.setdefault("manual_handoffs", []).append(payload)
    candidate["manual_handoffs"] = candidate["manual_handoffs"][-10:]
    candidate["manual_generated_video_handoff"] = payload
    candidate["manual_handoff_pending"] = False
    candidate["interruption_pending"] = False
    candidate["last_interruption_at"] = payload["reported_at"]
    candidate["last_interruption_source"] = payload["source"]
    route = dict(task_route_decision(candidate))
    route.update(
        {
            "manual_handoff_update": True,
            "manual_handoff": payload,
            "no_new_xyq_submit": True,
            "monitor_only_no_resubmit": True,
            "public_publish_allowed": False,
            "public_publish_intent": False,
            "external_action_allowed": False,
            "reason": "manual XYQ/LazyEdit handoff recorded; automation should not repeat generation/download/publish",
        }
    )
    candidate["route_decision"] = route
    candidate["status"] = "done"
    candidate["completed_at"] = payload["reported_at"]
    candidate["result"] = manual_generated_video_handoff_result_payload(payload)
    for field in (
        "claimed_at",
        "worker_id",
        "next_poll_at",
        "next_poststage_at",
        "next_publish_poststage_at",
        "reprocess_requested_at",
        "reprocess_reason",
        "generation_blocked_until_story_confirmed",
        "story_confirmation_required",
    ):
        candidate.pop(field, None)


def manual_generated_video_handoff_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": (
            "Manual handoff noted: the owner reported the Xiaoyunque video output(s) were already downloaded "
            "and handed to LazyEdit. No automatic generation, download, or publish action was run."
        ),
        "files": [],
        "confirmation": "",
        "manual_handoff": payload,
    }


def promote_story_target_for_generation_interruption(task: dict[str, Any], interruption: dict[str, Any]) -> bool:
    """Turn an approved story row into the generated-video routine.

    The monitor may first create a story task, then receive a same-chat
    "story ok, generate video" message. That update must move the same queue row
    forward instead of asking the worker to rediscover the stage from prose.
    """
    incoming_route = interruption.get("route_decision") if isinstance(interruption.get("route_decision"), dict) else {}
    incoming_text = "\n".join(
        [
            str(interruption.get("request") or ""),
            str(interruption.get("request_excerpt") or ""),
            json.dumps(incoming_route, ensure_ascii=False),
        ]
    ).lower()
    if str(incoming_route.get("route_kind") or "") != "generate_video" and not text_confirms_story_video_generation(incoming_text):
        return False
    current_route = task_route_decision(task)
    current_kind = str(current_route.get("route_kind") or "")
    if current_kind not in {"story_or_script", "generate_video"}:
        return False
    route = dict(current_route)
    route.update(incoming_route)
    route.update(
        {
            "route_kind": "generate_video",
            "project": "lalachan",
            "worker_needed": True,
            "needs_recent_media": False,
            "public_publish_allowed": bool(incoming_route.get("public_publish_allowed")),
            "public_publish_intent": bool(incoming_route.get("public_publish_intent")),
            "source_policy": incoming_route.get("source_policy") or route.get("source_policy") or "current_plus_explicit_refs",
            "approval_promoted_from": current_kind or "story_interruption",
            "approval_interruption": {
                "at": interruption.get("at"),
                "incoming_task_id": interruption.get("incoming_task_id"),
                "source": interruption.get("source") if isinstance(interruption.get("source"), dict) else {},
            },
        }
    )
    task["route_decision"] = route
    task["routine"] = generated_video_routine_snapshot(task, selected_by="wechat_task_worker.promote_story_target_for_generation_interruption")
    task["story_confirmation_required"] = False
    task["generation_blocked_until_story_confirmed"] = False
    task["confirmed_story_for_generation_at"] = interruption.get("at") or datetime.now().isoformat(timespec="seconds")
    task["confirmed_story_for_generation_note"] = collapse_context_text(interruption.get("request_excerpt") or interruption.get("request"), max_len=1000)
    preserve_story_confirmation_material(task)
    task["stage_transition"] = {
        "from": "story_script_generation",
        "to": "generated_video",
        "at": task["confirmed_story_for_generation_at"],
        "reason": "same_chat_generation_confirmation",
        "interruption_task_id": interruption.get("incoming_task_id"),
    }
    for field in ("preflight", "routine_contract", "orchestrator", "worker_policy_attempts", "story_confirmation_gate"):
        task.pop(field, None)
    return True


def text_confirms_story_video_generation(text: str) -> bool:
    lowered = str(text or "").lower()
    negative = (
        "do not generate",
        "don't generate",
        "dont generate",
        "not generate",
        "wait",
        "不要生成",
        "别生成",
        "不用生成",
        "先别",
        "等一下",
    )
    if any(marker in lowered for marker in negative):
        return False
    positive = (
        "story ok",
        "ok generate",
        "generate video",
        "continue generation",
        "continue to generate",
        "开始生成",
        "继续生成",
        "可以生成",
        "故事可以",
        "生成视频",
    )
    return any(marker in lowered for marker in positive)


def generated_video_routine_snapshot(task: dict[str, Any], *, selected_by: str) -> dict[str, Any]:
    route = task_route_decision(task)
    return {
        "id": "generated_video",
        "title": "Generated Video Routine",
        "task_id": task.get("id"),
        "chat": task.get("chat"),
        "source": task.get("source") if isinstance(task.get("source"), dict) else {},
        "route_kind": "generate_video",
        "project": "lalachan",
        "purpose": "Create a new video from the approved story, monitor long generation, send MP4 back, then run optional poststages.",
        "selected_at": datetime.now().isoformat(timespec="seconds"),
        "selected_by": selected_by,
        "public_publish_allowed": bool(route.get("public_publish_allowed")),
    }


def preserve_story_confirmation_material(task: dict[str, Any]) -> None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if result:
        task.setdefault("story_confirmation_result", result)
        message = str(result.get("message") or "").strip()
        if message:
            task.setdefault("approved_story_message", message)
        files = [str(path) for path in result.get("files") or [] if str(path)]
        if files:
            task.setdefault("approved_story_files", files)
    existing_files = [str(path) for path in task.get("sent_file_paths") or [] if str(path)]
    story_files = [path for path in existing_files if Path(path).suffix.lower() in {".md", ".markdown", ".txt"}]
    if story_files:
        merged_files = list(task.get("approved_story_files") or [])
        for path in story_files:
            if path not in merged_files:
                merged_files.append(path)
        task["approved_story_files"] = merged_files
    if not str(task.get("approved_story_message") or "").strip():
        for path_text in task.get("approved_story_files") or []:
            path = Path(str(path_text))
            try:
                if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"}:
                    text = path.read_text(encoding="utf-8", errors="replace").strip()
                else:
                    text = ""
            except OSError:
                text = ""
            if text:
                task["approved_story_message"] = collapse_context_text(text, max_len=8000)
                break


def interruption_already_recorded(task: dict[str, Any], incoming_source: dict[str, Any]) -> bool:
    incoming_key = (
        str(incoming_source.get("message_table") or ""),
        str(incoming_source.get("server_id") or ""),
        str(incoming_source.get("local_id") or ""),
    )
    for item in task_interruptions(task):
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        existing_key = (
            str(source.get("message_table") or ""),
            str(source.get("server_id") or ""),
            str(source.get("local_id") or ""),
        )
        if existing_key == incoming_key:
            return True
    return False


def build_task_interruption(target: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    source = incoming.get("source") if isinstance(incoming.get("source"), dict) else {}
    return {
        "at": datetime.now().isoformat(timespec="seconds"),
        "mode": "same_chat_interruption",
        "target_task_id": target.get("id"),
        "incoming_task_id": incoming.get("id"),
        "source": source,
        "route_decision": task_route_decision(incoming),
        "request": str(incoming.get("request") or ""),
        "request_excerpt": collapse_context_text(incoming.get("request"), max_len=1200),
        "context": incoming.get("context")[-8:] if isinstance(incoming.get("context"), list) else [],
        "instruction": "Newer same-chat user messages override stale story/video plan details.",
    }


def append_interruption_notice_to_request(request: Any, interruption: dict[str, Any]) -> str:
    source = interruption.get("source") if isinstance(interruption.get("source"), dict) else {}
    notice = (
        "\n\nSame-chat interruption/update received after the original task:\n"
        f"- local_id={source.get('local_id')} server_id={source.get('server_id')} "
        f"sender={source.get('sender_display') or source.get('sender')}\n"
        f"{interruption.get('request_excerpt') or ''}\n"
        "The resumed worker agent must use this update to dynamically adjust the next routine stage."
    )
    base = str(request or "").rstrip()
    if notice in base:
        return base
    return base + notice


def story_video_interruption_policy() -> dict[str, Any]:
    return {
        "mode": "agent_adjusts_existing_routine",
        "monitor_role": "append_only_transport",
        "agent_role": "draft_or_revise_from_full_context_then_choose_next_stage",
        "confirmation_gate": "story_must_be_sent_to_group_and_confirmed_before_xiaoyunque_submit_or_continue",
    }


def requeue_if_task_interrupted_during_run(queue: Path, task: dict[str, Any]) -> bool:
    task_id = str(task.get("id") or "")
    if not task_id:
        return False
    lock_path = queue.with_suffix(queue.suffix + ".lock")
    now_text = datetime.now().isoformat(timespec="seconds")
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(queue)
        for index, current in enumerate(tasks):
            if str(current.get("id") or "") != task_id:
                continue
            if not current.get("interruption_pending"):
                return False
            if not interruption_is_newer_than_claim(current, task):
                task["interruption_pending"] = False
                task["interruption_handled_at"] = now_text
                task["interruption_handled_by"] = str(task.get("worker_id") or worker_identity())
                task["interruption_handled_count"] = int(current.get("interruption_count") or len(task_interruptions(current)))
                return False
            current["status"] = "pending"
            current["reprocess_requested_at"] = now_text
            current["reprocess_reason"] = "interruption_arrived_during_worker_turn"
            current["stale_result_suppressed_at"] = now_text
            current.pop("claimed_at", None)
            current.pop("worker_id", None)
            current.pop("result", None)
            tasks[index] = current
            write_tasks(queue, tasks)
            return True
    return False


def interruption_is_newer_than_claim(current: dict[str, Any], claimed_task: dict[str, Any]) -> bool:
    last_interrupt = parse_iso_datetime(str(current.get("last_interruption_at") or ""))
    claimed_at = parse_iso_datetime(str(claimed_task.get("claimed_at") or current.get("claimed_at") or ""))
    if not last_interrupt or not claimed_at:
        return False
    return last_interrupt > claimed_at


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
        candidates: list[tuple[tuple[int, float, int], int, str]] = []
        changed = False
        for index, task in enumerate(tasks):
            status = str(task.get("status") or "")
            if generated_video_stale_pause_due(task, now):
                task.setdefault("generation_pause_history", []).append(
                    {
                        "at": now_text,
                        "previous_status": status,
                        "worker_id": task.get("worker_id"),
                        "generation_wait_count": task.get("generation_wait_count"),
                        "reason": "stale_generated_video_wait_exceeded",
                    }
                )
                task["status"] = GENERATED_VIDEO_STALE_PAUSED_STATUS
                task["generation_paused_at"] = now_text
                task["generation_pause_reason"] = "stale_generated_video_wait_exceeded"
                task.pop("completed_at", None)
                tasks[index] = task
                changed = True
                continue
            if (
                status == "pending"
                or stale_in_progress(task, now)
                or generated_video_poll_ready(task, now)
                or generated_video_poststage_ready(task, now)
                or existing_video_publish_poststage_ready(task, now)
            ):
                candidates.append((claim_ready_sort_key(task, status, index), index, status))
        if not candidates:
            if changed:
                write_tasks(path, tasks)
            return None
        _sort_key, index, status = min(candidates, key=lambda item: item[0])
        task = tasks[index]
        if status == CLAIMED_STATUS:
            task.setdefault("claim_history", []).append(
                {
                    "worker_id": task.get("worker_id"),
                    "claimed_at": task.get("claimed_at"),
                    "reclaimed_at": now_text,
                }
            )
        if status == GENERATED_VIDEO_WAITING_STATUS:
            task.setdefault("generation_poll_history", []).append(
                {
                    "wait_count": task.get("generation_wait_count"),
                    "next_poll_at_iso": task.get("next_poll_at_iso"),
                    "claimed_at": now_text,
                }
            )
        if status == GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS:
            task.setdefault("poststage_history", []).append(
                {
                    "queued_at": task.get("poststage_queued_at"),
                    "claimed_at": now_text,
                    "kind": (task.get("generated_video_poststage") or {}).get("kind"),
                }
            )
        if status == EXISTING_VIDEO_PUBLISH_PENDING_STATUS:
            task.setdefault("publish_poststage_history", []).append(
                {
                    "queued_at": task.get("publish_poststage_queued_at"),
                    "claimed_at": now_text,
                    "stage": (task.get("existing_video_publish_poststage") or {}).get("stage"),
                    "video_id": (task.get("existing_video_publish_poststage") or {}).get("video_id"),
                }
            )
        task["status"] = CLAIMED_STATUS
        task["worker_id"] = worker_id
        task["claimed_at"] = now_text
        task.pop("send_errors", None)
        tasks[index] = task
        write_tasks(path, tasks)
        return task


def claim_ready_sort_key(task: dict[str, Any], status: str, index: int) -> tuple[int, float, int]:
    if status == "pending":
        priority = 0
        timestamp = parse_iso_datetime(str(task.get("created_at") or ""))
        return priority, timestamp.timestamp() if timestamp else 0.0, index
    if status in {GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS, EXISTING_VIDEO_PUBLISH_PENDING_STATUS}:
        priority = 1
        raw = task.get("next_poststage_at") or task.get("next_publish_poststage_at") or 0
        return priority, safe_float(raw), index
    if status == GENERATED_VIDEO_WAITING_STATUS:
        priority = 2
        return priority, safe_float(task.get("next_poll_at") or 0), index
    return 3, 0.0, index


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def adopt_active_generated_video_tasks(path: Path) -> dict[str, Any] | None:
    """Persist active Xiaoyunque thread state so long renders do not hold a worker."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(path)
        now = datetime.now()
        for index, task in enumerate(tasks):
            if not generated_video_adoption_due(task, now):
                continue
            monitor = discover_generated_video_monitor_from_probe(task) or discover_generated_video_monitor_from_browser(task)
            if not (monitor.get("thread_url") and monitor.get("page_id")):
                continue
            now_text = now.isoformat(timespec="seconds")
            adopted_monitor = dict(task.get("generated_video_monitor") or {})
            adopted_monitor.update(monitor)
            adopted_monitor.setdefault("output_dir", str(Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))))
            adopted_monitor.setdefault("filename", f"{safe_slug(str(task.get('id') or 'generated-video'))}.mp4")
            adopted_monitor["adopted_at"] = now_text
            task["generated_video_monitor"] = adopted_monitor
            task["status"] = GENERATED_VIDEO_WAITING_STATUS
            task["next_poll_at"] = now.timestamp() + generated_video_adoption_poll_seconds()
            task["next_poll_at_iso"] = datetime.fromtimestamp(float(task["next_poll_at"])).isoformat(timespec="seconds")
            task["generation_wait_count"] = max(1, int(task.get("generation_wait_count") or 0))
            task["last_generation_status_at"] = now_text
            task["last_live_status_at"] = now_text
            task.setdefault("generation_adoption_history", []).append(
                {
                    "at": now_text,
                    "previous_status": CLAIMED_STATUS,
                    "previous_worker_id": task.get("worker_id"),
                    "thread_url": adopted_monitor.get("thread_url"),
                    "page_id": adopted_monitor.get("page_id"),
                }
            )
            task["result"] = {
                "message": "Xiaoyunque generation was adopted into durable queue monitoring.",
                "files": [],
                "confirmation": "",
                "data": {"generated_video": adopted_monitor, "generation": adopted_monitor},
            }
            task.pop("completed_at", None)
            task.pop("send_errors", None)
            task.pop("send_deferred_reason", None)
            tasks[index] = task
            write_tasks(path, tasks)
            return task
    return None


def generated_video_adoption_due(task: dict[str, Any], now: datetime) -> bool:
    if not is_generate_video_task(task) or str(task.get("status") or "") != CLAIMED_STATUS:
        return False
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    if monitor.get("thread_url") and monitor.get("page_id"):
        return False
    if task.get("generation_wait_count"):
        return False
    claimed_at = parse_iso_datetime(str(task.get("claimed_at") or ""))
    if not claimed_at:
        return False
    min_age = int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_ADOPT_IN_PROGRESS_SECONDS", "90"))
    return (now - claimed_at).total_seconds() >= max(0, min_age)


def generated_video_adoption_poll_seconds() -> int:
    return max(1, int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_ADOPT_POLL_SECONDS", "60")))


def generated_video_stale_pause_due(task: dict[str, Any], now: datetime) -> bool:
    if not is_generate_video_task(task):
        return False
    if str(task.get("status") or "") not in {CLAIMED_STATUS, GENERATED_VIDEO_WAITING_STATUS}:
        return False
    min_waits = int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_STALE_MIN_WAITS", "20"))
    if int(task.get("generation_wait_count") or 0) < min_waits:
        return False
    max_age = int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_STALE_SECONDS", str(6 * 60 * 60)))
    if max_age <= 0:
        return False
    anchors = [
        parse_iso_datetime(str(task.get("generation_started_at") or "")),
        parse_iso_datetime(str(task.get("created_at") or "")),
        parse_iso_datetime(str(task.get("claimed_at") or "")),
    ]
    started = next((item for item in anchors if item is not None), None)
    if not started:
        return False
    return (now - started).total_seconds() >= max_age


def generated_video_poll_ready(task: dict[str, Any], now: datetime) -> bool:
    if str(task.get("status") or "") != GENERATED_VIDEO_WAITING_STATUS:
        return False
    if task.get("confirmation"):
        return False
    raw = task.get("next_poll_at")
    try:
        next_poll = float(raw)
    except (TypeError, ValueError):
        next_poll = 0.0
    return now.timestamp() >= next_poll


def generated_video_poststage_ready(task: dict[str, Any], now: datetime) -> bool:
    if str(task.get("status") or "") != GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS:
        return False
    if task.get("confirmation"):
        return False
    raw = task.get("next_poststage_at")
    try:
        next_poststage = float(raw)
    except (TypeError, ValueError):
        next_poststage = 0.0
    return now.timestamp() >= next_poststage


def existing_video_publish_poststage_ready(task: dict[str, Any], now: datetime) -> bool:
    if str(task.get("status") or "") != EXISTING_VIDEO_PUBLISH_PENDING_STATUS:
        return False
    if task.get("confirmation"):
        return False
    raw = task.get("next_publish_poststage_at")
    try:
        next_poststage = float(raw)
    except (TypeError, ValueError):
        next_poststage = 0.0
    return now.timestamp() >= next_poststage


def claim_next_deferred_send(path: Path, chat_filter: str | None = None) -> dict[str, Any] | None:
    """Claim one deferred send if its retry backoff has elapsed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    worker_id = worker_identity()
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(path)
        now = datetime.now()
        now_text = now.isoformat(timespec="seconds")
        changed = False
        candidates: list[int] = []
        for index, task in enumerate(tasks):
            if chat_filter and str(task.get("chat") or "") != chat_filter:
                continue
            status = str(task.get("status") or "")
            if status == "send_failed":
                if not failed_send_retryable(task, now):
                    continue
                task.setdefault("send_failed_repair_history", []).append(
                    {
                        "repaired_at": now_text,
                        "reason": send_deferred_reason_from_errors([str(item) for item in task.get("send_errors") or []]),
                        "from_status": "send_failed",
                    }
                )
            elif status not in {SEND_DEFERRED_LOCKED_STATUS, SEND_DEFERRED_ARTIFACT_STATUS, SEND_RETRYING_STATUS}:
                continue
            if status == SEND_RETRYING_STATUS and not stale_send_retrying(task, now):
                continue
            if status == SEND_DEFERRED_LOCKED_STATUS and not deferred_send_backoff_elapsed(task, now):
                continue
            if transient_send_retry_limit_reached(task):
                task["status"] = "send_failed"
                task.setdefault("send_errors", []).append(
                    f"transient send retry limit reached ({int(task.get('send_retry_count') or 0)} attempts)"
                )
                tasks[index] = task
                changed = True
                continue
            candidates.append(index)
        if candidates:
            candidates.sort(key=lambda idx: (deferred_send_priority(tasks[idx]), -deferred_send_sort_timestamp(tasks[idx])))
            index = candidates[0]
            task = tasks[index]
            task["status"] = SEND_RETRYING_STATUS
            task["worker_id"] = worker_id
            task["send_retry_claimed_at"] = now_text
            task["send_retry_count"] = int(task.get("send_retry_count") or 0) + 1
            tasks[index] = task
            write_tasks(path, tasks)
            return task
        if changed:
            write_tasks(path, tasks)
        return None


def deferred_send_priority(task: dict[str, Any]) -> int:
    if verified_publish_send_completion(task):
        return 0
    if result_requires_file_delivery(task, task.get("result") if isinstance(task.get("result"), dict) else {}):
        return 2
    return 1


def deferred_send_sort_timestamp(task: dict[str, Any]) -> float:
    for key in ("last_send_attempt_at", "created_at", "completed_at", "resent_at"):
        value = parse_iso_datetime(str(task.get(key) or ""))
        if value:
            return value.timestamp()
    return 0.0


def verified_publish_send_completion(task: dict[str, Any]) -> bool:
    result = task.get("result")
    if not isinstance(result, dict):
        return False
    return verified_publish_result_completion(result)


def verified_publish_result_completion(result: dict[str, Any]) -> bool:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    publish_stage = data.get("publish_stage") if isinstance(data.get("publish_stage"), dict) else {}
    return bool(publish_stage.get("verified")) or str(publish_stage.get("stage") or "") == "published_verified"


def repair_missing_artifact_deliveries(path: Path) -> dict[str, Any]:
    """Move completed required-media tasks back to the deferred outbox."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    repaired: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    active_statuses = {
        "pending",
        CLAIMED_STATUS,
        SEND_DEFERRED_LOCKED_STATUS,
        SEND_DEFERRED_ARTIFACT_STATUS,
        SEND_RETRYING_STATUS,
        GENERATED_VIDEO_WAITING_STATUS,
        GENERATED_VIDEO_POSTSTAGE_PENDING_STATUS,
    }
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = read_tasks(path)
        for index, task in enumerate(tasks):
            status = str(task.get("status") or "")
            if status in active_statuses:
                continue
            result = task.get("result")
            if not isinstance(result, dict):
                continue
            if not result_requires_file_delivery(task, result):
                continue
            required = required_delivery_file_paths(result)
            if not required or required_file_delivery_complete(task, result):
                continue
            missing_existing = [str(item) for item in required if item.exists()]
            missing_absent = [str(item) for item in required if not item.exists()]
            if not missing_existing:
                skipped.append({"id": task.get("id"), "chat": task.get("chat"), "reason": "required_files_missing", "files": missing_absent})
                continue
            task.setdefault("repair_history", []).append(
                {
                    "from_status": status,
                    "reason": "required_media_not_sent",
                    "repaired_at": datetime.now().isoformat(timespec="seconds"),
                    "required_files": [str(item) for item in required],
                    "sent_file_paths": task.get("sent_file_paths") or [],
                }
            )
            task["status"] = SEND_DEFERRED_ARTIFACT_STATUS
            task["send_deferred_reason"] = "required_artifact_delivery"
            task["last_send_attempt_at"] = "1970-01-01T00:00:00"
            task.pop("completed_at", None)
            tasks[index] = task
            repaired.append({"id": task.get("id"), "chat": task.get("chat"), "from_status": status, "files": missing_existing})
        write_tasks(path, tasks)
    return {"ok": True, "queue": str(path), "repaired_count": len(repaired), "repaired": repaired, "skipped": skipped}


def deferred_send_backoff_elapsed(task: dict[str, Any], now: datetime) -> bool:
    reason = str(task.get("send_deferred_reason") or "")
    if reason == "gui_send_busy":
        if gui_send_lock_busy():
            return False
        backoff = int(os.environ.get("WECHAT_WORKER_BUSY_SEND_BACKOFF_SECONDS", "15"))
        if backoff <= 0:
            return True
        last = parse_iso_datetime(str(task.get("last_send_attempt_at") or task.get("resent_at") or task.get("completed_at") or ""))
        if not last:
            return True
        return (now - last).total_seconds() >= backoff
    if reason == "gui_send_timeout":
        if gui_send_lock_busy():
            return False
        backoff = int(os.environ.get("WECHAT_WORKER_TIMEOUT_SEND_BACKOFF_SECONDS", "15"))
        if backoff <= 0:
            return True
        last = parse_iso_datetime(str(task.get("last_send_attempt_at") or task.get("resent_at") or task.get("completed_at") or ""))
        if not last:
            return True
        return (now - last).total_seconds() >= backoff
    if reason == "wechat_entry_required":
        if gui_send_lock_busy():
            return False
        backoff = int(os.environ.get("WECHAT_WORKER_ENTRY_SEND_BACKOFF_SECONDS", "15"))
        if backoff <= 0:
            return True
        last = parse_iso_datetime(str(task.get("last_send_attempt_at") or task.get("resent_at") or task.get("completed_at") or ""))
        if not last:
            return True
        return (now - last).total_seconds() >= backoff
    if reason == "title_guard_blank":
        backoff = int(os.environ.get("WECHAT_WORKER_TITLE_GUARD_BLANK_BACKOFF_SECONDS", "20"))
        if backoff <= 0:
            return True
        last = parse_iso_datetime(str(task.get("last_send_attempt_at") or task.get("resent_at") or task.get("completed_at") or ""))
        if not last:
            return True
        return (now - last).total_seconds() >= backoff
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
    raw_timeout = os.environ.get("WECHAT_WORKER_STALE_SEND_RETRY_SECONDS")
    if raw_timeout is None:
        send_timeout = int(os.environ.get("WECHAT_WORKER_SEND_TIMEOUT_SECONDS", "120"))
        timeout = max(send_timeout + 30, 150)
    else:
        timeout = int(raw_timeout)
    if timeout <= 0:
        return False
    claimed_at = parse_iso_datetime(str(task.get("send_retry_claimed_at") or ""))
    if not claimed_at:
        return True
    return (now - claimed_at).total_seconds() > timeout


def failed_send_retryable(task: dict[str, Any], now: datetime) -> bool:
    errors = [str(item) for item in task.get("send_errors") or []]
    if not send_errors_indicate_deferable(errors) and not verified_publish_send_completion(task):
        return False
    reason = send_deferred_reason_from_errors(errors)
    if verified_publish_send_completion(task):
        max_retries = int(os.environ.get("WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES", "12"))
    else:
        max_retries = int(os.environ.get("WECHAT_WORKER_FAILED_SEND_MAX_RETRIES", "0"))
    if max_retries >= 0 and int(task.get("send_retry_count") or 0) >= max_retries:
        max_recoveries = int(os.environ.get("WECHAT_WORKER_FAILED_SEND_RECOVERY_CYCLES", "10"))
        recoveries = int(task.get("send_failed_recovery_count") or 0)
        if max_recoveries < 0 or recoveries < max_recoveries or stale_transport_send_failure_recoverable(task, now, reason):
            task["send_retry_count"] = 0
            task["send_failed_recovery_count"] = recoveries + 1
            task["send_failed_recovered_at"] = now.isoformat(timespec="seconds")
        else:
            return False
    task["send_deferred_reason"] = reason
    if not task["send_deferred_reason"] and verified_publish_send_completion(task):
        task["send_deferred_reason"] = "gui_send_timeout"
    return deferred_send_backoff_elapsed(task, now)


def stale_transport_send_failure_recoverable(task: dict[str, Any], now: datetime, reason: str) -> bool:
    if reason not in {"gui_send_busy", "gui_send_timeout"}:
        return False
    if gui_send_lock_busy():
        return False
    stale_seconds = int(os.environ.get("WECHAT_WORKER_FAILED_SEND_STALE_RECOVERY_SECONDS", "300"))
    if stale_seconds < 0:
        return True
    last = parse_iso_datetime(
        str(
            task.get("last_send_attempt_at")
            or task.get("send_failed_recovered_at")
            or task.get("resent_at")
            or task.get("completed_at")
            or ""
        )
    )
    if not last:
        return True
    return (now - last).total_seconds() >= stale_seconds


def transient_send_retry_limit_reached(task: dict[str, Any]) -> bool:
    reason = str(task.get("send_deferred_reason") or "")
    if reason not in {"gui_send_busy", "gui_send_timeout", "wechat_entry_required", "title_guard_blank"}:
        return False
    if verified_publish_send_completion(task):
        max_retries = int(os.environ.get("WECHAT_WORKER_VERIFIED_PUBLISH_SEND_MAX_RETRIES", "12"))
    else:
        max_retries = int(os.environ.get("WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES", "5"))
    if max_retries < 0:
        return False
    return int(task.get("send_retry_count") or 0) >= max_retries


def stale_in_progress(task: dict[str, Any], now: datetime) -> bool:
    if task.get("status") != CLAIMED_STATUS:
        return False
    if claimed_worker_process_dead(task):
        return True
    timeout = int(os.environ.get("WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS", DEFAULT_STALE_IN_PROGRESS_SECONDS))
    if timeout <= 0:
        return False
    claimed_at = parse_iso_datetime(str(task.get("claimed_at") or ""))
    if not claimed_at:
        return False
    return (now - claimed_at).total_seconds() > timeout


def claimed_worker_process_dead(task: dict[str, Any]) -> bool:
    worker_id = str(task.get("worker_id") or "")
    if not worker_id.startswith("pid:"):
        return False
    try:
        pid = int(worker_id.split(":", 1)[1])
    except ValueError:
        return False
    if pid <= 0 or pid == os.getpid():
        return False
    return not process_alive(pid)


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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


def persist_task_progress(task: dict[str, Any]) -> None:
    queue_path = str(task.get("queue_path") or "")
    if not queue_path:
        return
    try:
        path = Path(queue_path)
    except (TypeError, ValueError):
        return
    if not path.exists():
        return
    try:
        rewrite_task(path, task)
    except Exception as exc:
        task.setdefault("progress_persist_errors", []).append(
            {
                "at": datetime.now().isoformat(timespec="seconds"),
                "type": type(exc).__name__,
                "message": str(exc)[:300],
            }
        )


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
        next_policy = escalated_policy(policy, result, task=task)
        if not next_policy:
            break
        policy = next_policy
    task["worker_policy"] = policy
    task["worker_policy_attempts"] = attempts
    return result


def run_worker_codex_once(task: dict[str, Any], policy: dict[str, Any]) -> str:
    return run_task_orchestrator(task, policy)


def run_task_orchestrator(task: dict[str, Any], policy: dict[str, Any]) -> str:
    """Central routine supervisor for a queued WeChat task.

    Deterministic code only handles mature routine stages such as source
    resolution, cheap status probes, and delivery gates. Any ambiguous,
    repair-oriented, or tool-heavy work falls through to the resumed per-chat
    Codex worker session below.
    """
    artifact_dir = worker_artifact_dir(task)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    task.setdefault("artifact_dir", str(artifact_dir))
    ensure_task_routine_contract(task)
    task["routine_contract"] = write_routine_contract(task, artifact_dir)
    task["orchestrator"] = {
        "mode": "routine_supervisor",
        "routine_id": (task.get("routine") or {}).get("id") if isinstance(task.get("routine"), dict) else None,
        "stage": task_orchestrator_stage(task),
        "policy": {
            "model": policy.get("model"),
            "reasoning_effort": policy.get("reasoning_effort"),
            "timeout_seconds": policy.get("timeout_seconds"),
            "reuse_session": bool(policy.get("reuse_session", True)),
        },
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    preflight = prepare_worker_preflight(task, artifact_dir)
    if preflight:
        task["preflight"] = preflight
        persist_task_progress(task)
    deterministic = deterministic_preflight_result(task)
    if deterministic is not None:
        task["orchestrator"]["last_action"] = "deterministic_routine_stage"
        task["orchestrator"]["last_action_at"] = datetime.now().isoformat(timespec="seconds")
        return deterministic
    task["orchestrator"]["last_action"] = "resume_codex_worker_session"
    task["orchestrator"]["last_action_at"] = datetime.now().isoformat(timespec="seconds")
    return run_worker_agent_session(task, policy)


def task_orchestrator_stage(task: dict[str, Any]) -> str:
    if isinstance(task.get("existing_video_publish_poststage"), dict) and task.get("existing_video_publish_poststage"):
        return "existing_video_publish_poststage"
    if isinstance(task.get("generated_video_poststage"), dict) and task.get("generated_video_poststage"):
        return "generated_video_poststage"
    if isinstance(task.get("generated_video_monitor"), dict) and task.get("generated_video_monitor"):
        return "generated_video_monitor"
    if isinstance(task.get("routine"), dict) and task["routine"].get("id"):
        return f"routine:{task['routine']['id']}"
    return "routine:unclassified"


def run_worker_agent_session(task: dict[str, Any], policy: dict[str, Any]) -> str:
    routine_context = routine_prompt_context(task)
    tool_context = build_worker_tool_context(task)
    interruption_context = build_interruption_prompt_context(task)
    orchestrator_context = json.dumps(task.get("orchestrator") or {}, ensure_ascii=False, indent=2)
    execution_context = json.dumps(worker_execution_contract(task), ensure_ascii=False, indent=2)
    instruction_context = json.dumps(worker_instruction_contract(task), ensure_ascii=False, indent=2)
    prompt = f"""You are the slower worker agent for a WeChat LabCanvas chat.
Handle the task using available local files/tools. Save downloaded or generated artifacts under the repo's ignored private/output folders when possible.
WeChat is only the message transport: it receives user messages and returns safe files/messages. Backend execution belongs to the routine orchestrator and the selected per-chat worker agent session.
You are being resumed by the central routine orchestrator. Treat the routine contract and orchestrator handoff as the execution center: inspect current stage, use mature routine entrypoints first, repair blockers, and only invent a new approach if no routine stage applies.
The task may be a fragment or follow-up from an ongoing WeChat thread. Use the task's source and context fields to resolve pronouns, repeated requests, "same/again/this/that/last one", and incomplete messages.
If `task.interruptions` or `task.preflight.interruptions` exists, those are newer same-chat user updates attached by the monitor. Treat them as authoritative updates to this active routine, not as separate unrelated tasks. Read all interruptions together before acting, revise the plan, and continue from the real current stage.
For story/video workflows, a newer request to revise/show/confirm the story must pause or replace the stale story-generation plan before any new video submit. Send the updated story back and ask whether to generate the video unless the latest same-chat messages already give clear generation permission. If a generation was submitted but the user says they stopped it or asks to update the story, do not keep polling the stale run as success; update the story/prompt first and wait for or use the latest confirmation.
Follow the machine-readable instruction contract below. Follow every safe, explicit instruction in the current coalesced request. If the user asks for multiple stages, do them in order or persist a resumable state for unfinished stages; do not collapse the request to a smaller hardcoded action just because one routine or keyword matched.
Before executing, inspect `task.route_decision` against the Current coalesced request and recent context. If they conflict, choose the safer interpretation and state the conflict instead of acting. If `task.route_decision` exists, treat it as the intent contract. If it says `route_kind=generate_video`, generate/import the requested new video and do not process an old WeChat MP4 as the output. Treat stages separately: story writing, video generation/download/send-back, LazyEdit import/process, and public publishing are independent permissions. If `public_publish_allowed` is false, do not publish/post/upload to Shipinhao, YouTube, Instagram, AutoPublish public queues, or any public platform even if old context mentions publishing. Public posting requires an explicit publish/post/platform instruction in the current user request, not merely old history. LazyEdit import/process is allowed only when the current request explicitly asks for LazyEdit/import/process.
For paid Xiaoyunque/Seedance work, use request-level idempotence: one logical WeChat request owns at most one paid generation thread unless the current user message explicitly asks for a new paid rerun. If `task.generated_video_monitor.thread_url`, `task.generated_video_submit_probe`, `task.credit_guard`, `route_decision.no_new_xyq_submit`, or `monitor_only_no_resubmit` exists, do not submit, retry, continue, or create another Xiaoyunque job. Only monitor/download the existing thread and send the resulting MP4 back.
Before doing work or composing the final message, check whether the recent context already contains a bot/self answer or completed result for the same request. Avoid sending the same answer again; return only the new delta, current status, missing decision, or remaining artifact.
Strict source isolation: the task's `chat`, `source.local_id`, `source.server_id`, `context`, and any explicit source/reference rows embedded in `request` define the only WeChat source. Never use media, files, or generated artifacts from another chat, another direct message, a nearby queue item, or an unrelated old task.
If no exact matching source media is available for "this image", "this PDF", "this video", "last one", or a quoted command, return a source-limited message asking for the exact file/source. Do not synthesize or continue from unrelated media.
Follow the routine supervisor contract. The contract is saved in `task.routine_contract`; use it as the routine checklist and update task state through the existing queue/status mechanisms instead of inventing an ad hoc workflow.
Exception for WeChat video-to-AutoPublish requests: if the task asks to copy/download a WeChat video to Nutstore AutoPublish and the recent context contains a same-chat video row, first run:
`PYTHONPATH=src python -m agenticapp wechat autopublish-video --chat "<chat>" --sync --fetch-gui --since-minutes 720 --json`
This opens the chat in the isolated WeChat desktop, clicks the latest visible video so the official client caches the MP4, media-syncs it, and atomically copies it to `/home/lachlan/Nutstore Files/AutoPublish/AutoPublish`. Only report missing source after that command fails or returns no matching video.
If `task.preflight.autopublish_video` has `status: "artifact-ledger-match"` or `status: "copied"`, treat its `target` as the exact source video: it was matched by same-chat task history or WeChat video local_id/stem/size. Non-publish tasks save this source under the task artifact directory; LazyEdit/public publish tasks may copy into the AutoPublish intake when explicitly permitted.
If `task.preflight.autopublish_video` exists and has `ok: false` for a task with `message_local_ids`, fail closed only after its `artifact_resolution.ok` is also false or missing: do not publish, transcode, or reuse any nearby/older video. Report that neither the exact WeChat cache nor the same-chat artifact ledger contained the referenced source, and include the safe next action.

{routine_context}

Central orchestrator handoff:
```json
{orchestrator_context}
```

Execution contract:
```json
{execution_context}
```

Instruction contract:
```json
{instruction_context}
```

{interruption_context}

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
PYTHONPATH=src python -m agenticapp wechat browser-assist --url "<url>" --wait-seconds 8 --capture --close-after --json
Then return a confirmation telling the user to complete the manual step in noVNC and approve continuation.
If other external tools or files are not available, say exactly what is needed next.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}
"""
    backend = select_agent_backend(task)
    result = run_codex_session(
        prompt,
        backend=backend,
        chat_name=str(task.get("chat") or "wechat-chat"),
        role="worker",
        model=str(policy["model"]),
        reasoning_effort=str(policy["reasoning_effort"]),
        sandbox=str(policy["sandbox"]),
        timeout_seconds=int(policy["timeout_seconds"]),
        workdir=ROOT,
        reuse=bool(policy.get("reuse_session", True)),
        backend_config=worker_backend_config(task, backend),
    )
    if not result["ok"]:
        return f"Worker failed via {backend}: {str(result.get('stderr_tail') or result.get('message') or '').strip()[:1000]}"
    task["agent_session"] = {
        "backend": backend,
        "role": "worker",
        "thread_id_short": str(result.get("thread_id") or "")[:8],
        "resumed": bool(result.get("resumed")),
        "fallback_started": bool(result.get("fallback_started")),
    }
    task["codex_session"] = {
        "role": "worker",
        "thread_id_short": str(result.get("thread_id") or "")[:8],
        "resumed": bool(result.get("resumed")),
        "fallback_started": bool(result.get("fallback_started")),
    }
    return str(result.get("message") or "").strip()


def worker_backend_config(task: dict[str, Any], backend: str) -> dict[str, Any]:
    raw = task.get("agent_backend_config")
    if isinstance(raw, dict):
        return raw
    raw = task.get(backend)
    return raw if isinstance(raw, dict) else {}


def worker_execution_contract(task: dict[str, Any]) -> dict[str, Any]:
    instruction = worker_instruction_contract(task)
    contract = task.get("execution_contract") if isinstance(task.get("execution_contract"), dict) else {}
    if contract:
        merged = dict(contract)
        merged.setdefault("instruction_contract", instruction)
        return merged
    return default_worker_execution_contract(task, instruction)


def default_worker_execution_contract(task: dict[str, Any], instruction: dict[str, Any]) -> dict[str, Any]:
    return {
        "wechat_role": "message_transport_only",
        "monitor_role": "receive_coalesce_ack_enqueue",
        "routine_source": "task.routine",
        "worker_entrypoint": "wechat_task_worker.run_task_orchestrator",
        "agent_backend": select_agent_backend(task),
        "agent_entrypoint": "wechat_agent_backend.run_agent_session",
        "codex_entrypoint": "wechat_codex_sessions.run_codex_session",
        "codex_exec_mode": "resume_per_chat_worker_session",
        "claude_exec_mode": "stable_per_chat_role_session_id",
        "codex_session": {
            "chat": str(task.get("chat") or "wechat-chat"),
            "role": "worker",
            "reuse": True,
        },
        "instruction_contract": instruction,
    }


def worker_instruction_contract(task: dict[str, Any]) -> dict[str, Any]:
    contract = task.get("instruction_contract") if isinstance(task.get("instruction_contract"), dict) else {}
    if instruction_contract_complete(contract):
        contract.setdefault("autonomous_completion_required", True)
        contract.setdefault("human_supervision_role", "approval_only_for_login_captcha_payment_public_posting_deletion_or_unsafe_irreversible_actions")
        contract.setdefault("worker_must_continue_via_routine_until_terminal_state", True)
        contract.setdefault("same_chat_interruptions_authoritative", True)
        contract.setdefault("interruption_policy", "newer_same_chat_messages_update_the_active_routine_and_must_be_read_before_next_action")
        contract.setdefault("story_video_confirmation_policy", "after story revision, send story to group and confirm before video generation unless latest user text explicitly authorizes generation")
        return contract
    route = task_route_decision(task)
    return {
        "current_request_authoritative": True,
        "same_chat_interruptions_authoritative": True,
        "interruption_policy": "newer_same_chat_messages_update_the_active_routine_and_must_be_read_before_next_action",
        "story_video_confirmation_policy": "after story revision, send story to group and confirm before video generation unless latest user text explicitly authorizes generation",
        "preserve_safe_explicit_instructions": True,
        "multi_stage_policy": "complete_in_order_or_persist_resumable_state",
        "no_keyword_shrink": True,
        "use_agent_reasoning": "resume_exact_chat_route_and_worker_sessions",
        "hardcoded_logic_role": "safety_source_isolation_and_deterministic_gates_only",
        "autonomous_completion_required": True,
        "human_supervision_role": "approval_only_for_login_captcha_payment_public_posting_deletion_or_unsafe_irreversible_actions",
        "worker_must_continue_via_routine_until_terminal_state": True,
        "same_chat_source_isolation": True,
        "irreversible_actions_require_current_message_intent": True,
        "route_kind": str(route.get("route_kind") or "other_worker"),
        "chat": str(task.get("chat") or "wechat-chat"),
    }


def instruction_contract_complete(contract: dict[str, Any]) -> bool:
    return bool(
        contract.get("current_request_authoritative")
        and contract.get("preserve_safe_explicit_instructions")
        and contract.get("no_keyword_shrink")
        and contract.get("use_agent_reasoning")
    )


def ensure_runtime_instruction_contract(task: dict[str, Any]) -> None:
    instruction = worker_instruction_contract(task)
    task["instruction_contract"] = instruction
    execution = task.get("execution_contract") if isinstance(task.get("execution_contract"), dict) else {}
    if execution:
        execution = dict(execution)
        execution["instruction_contract"] = instruction
        task["execution_contract"] = execution
    else:
        task["execution_contract"] = default_worker_execution_contract(task, instruction)


def task_interruptions(task: dict[str, Any]) -> list[dict[str, Any]]:
    raw = task.get("interruptions") if isinstance(task.get("interruptions"), list) else []
    return [item for item in raw if isinstance(item, dict)]


def task_interruptions_manifest(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any] | None:
    interruptions = task_interruptions(task)
    if not interruptions:
        return None
    latest = interruptions[-1]
    manifest = {
        "task_id": task.get("id"),
        "chat": task.get("chat"),
        "status": "pending-agent-review",
        "count": len(interruptions),
        "latest_at": latest.get("at"),
        "latest_source": latest.get("source") if isinstance(latest.get("source"), dict) else {},
        "policy": {
            "monitor_role": "append-only transport; do not decide the creative or workflow outcome",
            "agent_role": "read all interruptions and dynamically adjust the active routine before the next action",
            "story_video_default": [
                "update/rewrite story from the full same-chat context",
                "send the revised story to the group",
                "ask whether to generate video unless latest text explicitly authorizes generation",
                "send the verified MP4 back before asking whether to publish",
            ],
        },
        "items": interruptions,
    }
    json_path = artifact_dir / "same_chat_interruptions.json"
    md_path = artifact_dir / "same_chat_interruptions.md"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(format_task_interruptions_markdown(manifest), encoding="utf-8")
    manifest["json"] = str(json_path)
    manifest["markdown"] = str(md_path)
    return manifest


def format_task_interruptions_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Same-Chat Interruptions",
        "",
        f"- Task: `{manifest.get('task_id') or ''}`",
        f"- Chat: `{manifest.get('chat') or ''}`",
        f"- Count: `{manifest.get('count') or 0}`",
        f"- Latest: `{manifest.get('latest_at') or ''}`",
        "",
        "## Policy",
        "",
        "- Newer same-chat messages are authoritative updates to the active routine.",
        "- The monitor only appends the messages; the resumed worker agent decides the next stage.",
        "- For story/video work, revise and show the story before generating unless the latest messages clearly authorize generation.",
        "",
        "## Items",
    ]
    for index, item in enumerate(manifest.get("items") or [], start=1):
        if not isinstance(item, dict):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        lines.extend(
            [
                "",
                f"### {index}. local_id={source.get('local_id') or ''}",
                "",
                f"- At: `{item.get('at') or ''}`",
                f"- Sender: `{source.get('sender_display') or source.get('sender') or ''}`",
                f"- Server ID: `{source.get('server_id') or ''}`",
                "",
                "```text",
                collapse_context_text(item.get("request"), max_len=3000),
                "```",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_interruption_prompt_context(task: dict[str, Any]) -> str:
    interruptions = task_interruptions(task)
    if not interruptions:
        return ""
    preflight = task.get("preflight") if isinstance(task.get("preflight"), dict) else {}
    manifest = preflight.get("interruptions") if isinstance(preflight.get("interruptions"), dict) else {}
    manifest_path = manifest.get("markdown") if isinstance(manifest, dict) else ""
    summary = []
    for item in interruptions[-6:]:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        summary.append(
            {
                "at": item.get("at"),
                "local_id": source.get("local_id"),
                "sender": source.get("sender_display") or source.get("sender"),
                "request_excerpt": item.get("request_excerpt") or collapse_context_text(item.get("request"), max_len=600),
            }
        )
    return f"""
Same-chat interruption packet:
- The monitor appended {len(interruptions)} newer same-chat message(s) to this active task.
- Manifest: `{manifest_path or '(not written yet)'}`
- These messages are authoritative updates for the next action. Do not answer from stale story/prompt context.
- If the user stopped a submitted Xiaoyunque run or says the story is wrong, update the story/prompt first and do not treat the stale run as success.
```json
{json.dumps(summary, ensure_ascii=False, indent=2)}
```
"""


def worker_artifact_dir(task: dict[str, Any]) -> Path:
    task_id = safe_slug(str(task.get("id") or "manual-task"))
    return ROOT / "output" / "wechat_worker" / task_id


def prepare_worker_preflight(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    preflight: dict[str, Any] = {}
    interruptions = task_interruptions_manifest(task, artifact_dir)
    if interruptions:
        preflight["interruptions"] = interruptions
    generate_video_task = is_generate_video_task(task)
    if generate_video_task:
        preflight["generated_video_contract"] = write_generated_video_contract(task, artifact_dir)
        generated_status = inspect_generated_video_status(task)
        if generated_status:
            preflight["generated_video_status"] = generated_status
    if should_prepare_media_resolution(task):
        preflight["media_resolution"] = prepare_media_resolution_preflight(task, artifact_dir)
        task["preflight"] = preflight
    if is_file_intake_task(task):
        preflight["file_intake"] = prepare_file_intake_preflight(task, artifact_dir)
    if not is_video_publish_task(task):
        return preflight
    context_path = artifact_dir / "lazyedit_correction_context.md"
    metadata_path = artifact_dir / "lazyedit_metadata_brief.md"
    preflight["lazyedit_context"] = {
        "correction_prompt_file": str(context_path),
        "metadata_prompt_file": str(metadata_path),
        "rule": "Pass correction_prompt_file to --correction-prompt-file and metadata_prompt_file to --metadata-prompt-file.",
    }
    if should_resolve_recent_video_artifact(task):
        artifact_resolution = resolve_recent_video_artifact_preflight(task)
        if bool(artifact_resolution.get("ok")):
            preflight["resolved_video_artifact"] = artifact_resolution
    if not generate_video_task and should_preflight_autopublish(task):
        if "resolved_video_artifact" not in preflight:
            autopub = run_autopublish_video_preflight(task)
            if bool(autopub.get("ok")):
                preflight["autopublish_video"] = autopub
            else:
                artifact_resolution = resolve_exact_video_artifact_preflight(task, autopub)
                if bool(artifact_resolution.get("ok")):
                    preflight["autopublish_video"] = artifact_resolution
                else:
                    autopub["artifact_resolution"] = artifact_resolution
                    preflight["autopublish_video"] = autopub
    context_path.write_text(build_lazyedit_correction_context(task, preflight=preflight), encoding="utf-8")
    metadata_path.write_text(build_lazyedit_metadata_brief(task, preflight=preflight), encoding="utf-8")
    return preflight


def is_file_intake_task(task: dict[str, Any]) -> bool:
    route = task_route_decision(task)
    return str(route.get("route_kind") or "") == "file_intake"


def should_prepare_media_resolution(task: dict[str, Any]) -> bool:
    route = task_route_decision(task)
    route_kind = str(route.get("route_kind") or "")
    if route_kind in {"edit_existing_media", "file_intake", "file_download_or_save", "process_existing_video", "publish_video"}:
        return True
    text = task_focus_text(task).lower()
    explicit_media_text = any(
        marker in text
        for marker in ("this image", "this photo", "this file", "这个图片", "這個圖片", "这张图", "這張圖", "这份文件", "这个文件")
    )
    if explicit_media_text:
        return True
    if not bool(route.get("needs_recent_media")):
        return False
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    source_kind = str(source.get("kind") or "").lower()
    source_type = int_or_none(source.get("local_type"))
    return source_kind in {"image", "video", "file", "voice"} or source_type in {3, 34, 43, 49}


def prepare_media_resolution_preflight(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    refresh = refresh_media_sync_for_task(task)
    candidates = resolve_synced_media_from_mirror(task, limit=12)
    gui_cache_probe: dict[str, Any] = {}
    second_refresh: dict[str, Any] = {}
    gui_probe_reason = media_gui_cache_probe_reason(task, candidates)
    if gui_probe_reason and should_probe_gui_media_cache(task):
        gui_cache_probe = materialize_chat_for_media_cache(task, artifact_dir)
        gui_cache_probe["reason"] = gui_probe_reason
        second_refresh = refresh_media_sync_for_task(task)
        candidates = resolve_synced_media_from_mirror(task, limit=12)
        crop_candidates = gui_probe_image_crop_candidates(task, candidates, gui_cache_probe)
        if crop_candidates:
            candidates = sorted(
                candidates + crop_candidates,
                key=lambda item: (float(item.get("score") or 0), float(item.get("source_mtime") or 0), int(item.get("size_bytes") or 0)),
                reverse=True,
            )
    source_dir = artifact_dir / "source_media"
    copied: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for index, item in enumerate(candidates[:8], start=1):
        source = Path(str(item.get("mirror_path") or "")).expanduser()
        if not source.is_file():
            skipped.append({"path": str(source), "reason": "missing"})
            continue
        target = unique_intake_target(source_dir, source.name, index=index)
        try:
            source_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            stat = target.stat()
        except OSError as exc:
            skipped.append({"path": str(source), "reason": f"copy-failed: {exc}"[:160]})
            continue
        copied.append(
            {
                **item,
                "task_copy_path": str(target),
                "filename": source.name,
                "suffix": source.suffix.lower(),
                "size_bytes": stat.st_size,
                "sha256": sha256_file(target),
            }
        )
    enrich_media_resolution_copies_with_image_read(copied, artifact_dir)
    manifest = {
        "task_id": task.get("id"),
        "chat": task.get("chat"),
        "status": "ok" if copied else "missing",
        "refresh": refresh,
        "gui_cache_probe": gui_cache_probe,
        "second_refresh": second_refresh,
        "tokens": extract_media_tokens_from_task(task),
        "source_windows": task_media_source_windows(task),
        "copied": copied,
        "skipped": skipped,
        "policy": "source-scoped media resolution; use task_copy_path files for this task only; retry after official-client chat materialization before declaring missing",
        "resolver": "media_files mirror + prompt paths + exact tokens/time windows + optional WeChat GUI cache probe",
    }
    manifest_json = artifact_dir / "media_resolution_manifest.json"
    manifest_md = artifact_dir / "media_resolution_manifest.md"
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest_md.write_text(media_resolution_markdown(manifest), encoding="utf-8")
    manifest["manifest_json"] = str(manifest_json)
    manifest["manifest_md"] = str(manifest_md)
    return manifest


def should_probe_gui_media_cache(task: dict[str, Any]) -> bool:
    if os.environ.get("WECHAT_WORKER_DISABLE_GUI_MEDIA_CACHE_PROBE"):
        return False
    if os.environ.get("WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT"):
        return False
    chat = str(task.get("chat") or "").strip()
    if not chat:
        return False
    route = task_route_decision(task)
    if str(route.get("route_kind") or "") in {"file_intake"}:
        return False
    return should_prepare_media_resolution(task)


def media_gui_cache_probe_reason(task: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "no_candidates"
    if not should_click_probe_gui_media_cache(task):
        return ""
    if os.environ.get("WECHAT_WORKER_DISABLE_LOW_QUALITY_IMAGE_CACHE_PROBE"):
        return ""
    image_candidates = [
        item for item in candidates
        if str(item.get("suffix") or Path(str(item.get("mirror_path") or "")).suffix).lower() in OCR_IMAGE_SUFFIXES
    ]
    if not image_candidates:
        return "image_source_without_image_candidate"
    try:
        min_width = int(os.environ.get("WECHAT_WORKER_MIN_CACHED_IMAGE_WIDTH", "320"))
        min_height = int(os.environ.get("WECHAT_WORKER_MIN_CACHED_IMAGE_HEIGHT", "320"))
        min_bytes = int(os.environ.get("WECHAT_WORKER_MIN_CACHED_IMAGE_BYTES", "30000"))
    except ValueError:
        min_width, min_height, min_bytes = 320, 320, 30000
    best_reason = "only_thumbnail_or_tiny_image_candidates"
    for item in image_candidates[:8]:
        path = Path(str(item.get("mirror_path") or "")).expanduser()
        try:
            size = path.stat().st_size
        except OSError:
            continue
        metadata = image_file_metadata(path)
        if metadata.get("status") == "ok":
            width = int(metadata.get("width") or 0)
            height = int(metadata.get("height") or 0)
            if width >= min_width and height >= min_height and size >= min_bytes:
                return ""
            best_reason = f"cached_image_too_small:{width}x{height}:{size}"
        elif size >= min_bytes:
            return ""
    return best_reason


def materialize_chat_for_media_cache(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    """Dry-open the source chat so the official WeChat client can cache media.

    The direct DB/media mirror is fast, but Linux WeChat often does not expose a
    newly sent image/file until the chat is opened in the official client. This
    probe never sends text; it only reuses the guarded GUI opener once, then the
    normal media sync is run again.
    """
    chat = str(task.get("chat") or "").strip()
    if not chat:
        return {"status": "skipped", "reason": "missing_chat"}
    script = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chat_sync_loop.py"
    if not script.is_file():
        return {"status": "skipped", "reason": "missing_wechat_chat_sync_loop"}
    output_dir = artifact_dir / "gui_media_cache_probe"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(script),
        "--once",
        "--only",
        chat,
        "--output-dir",
        str(output_dir),
        "--no-yield-to-queue",
    ]
    queue_path = str(task.get("queue_path") or "")
    if queue_path:
        command += ["--queue", queue_path]
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=float(os.environ.get("WECHAT_WORKER_GUI_MEDIA_CACHE_PROBE_TIMEOUT", "60")),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "error", "error": str(exc)[:500], "command": redact_command(command)}
    payload = {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "command": redact_command(command),
        "output_dir": str(output_dir),
        "stdout": collapse_context_text(proc.stdout, max_len=1000),
        "stderr": collapse_context_text(proc.stderr, max_len=1000) if proc.stderr.strip() else "",
    }
    if proc.returncode == 0 and should_click_probe_gui_media_cache(task):
        payload["image_click_probe"] = click_visible_media_for_cache(task, output_dir)
    return payload


def should_click_probe_gui_media_cache(task: dict[str, Any]) -> bool:
    if os.environ.get("WECHAT_WORKER_DISABLE_GUI_MEDIA_CLICK_PROBE"):
        return False
    text = task_focus_text(task).lower()
    image_markers = (
        "this image",
        "this photo",
        "this picture",
        "screenshot",
        "image i sent",
        "photo i sent",
        "read the image",
        "transcribe the image",
        "这个图片",
        "這個圖片",
        "这张图",
        "這張圖",
        "这张图片",
        "图片",
        "照片",
        "截图",
        "截圖",
        "读图",
        "识图",
    )
    if any(marker in text for marker in image_markers):
        return True
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    if str(source.get("kind") or "").lower() == "image" or int_or_none(source.get("local_type")) == 3:
        return True
    for row in task.get("context") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "").lower() == "image" or int_or_none(row.get("local_type")) == 3:
            return True
        if "<img" in str(row.get("content") or "").lower():
            return True
    return False


def click_visible_media_for_cache(task: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Click recent visible image bubbles so the official client downloads/caches them.

    This is deliberately narrow: it runs only after the exact chat was opened by
    the guarded chat-sync path and only when the first source-scoped mirror pass
    found no local media. It never sends text and it closes preview overlays with
    Escape after each click.
    """
    if shutil.which("xdotool") is None:
        return {"status": "skipped", "reason": "xdotool_missing"}
    display = os.environ.get("WECHAT_WORKER_DISPLAY") or os.environ.get("WECHAT_DISPLAY") or ":97"
    env = os.environ.copy()
    env["DISPLAY"] = display
    env.setdefault("XAUTHORITY", "")
    try:
        lock = acquire_gui_send_lock_or_raise()
    except RuntimeError as exc:
        return {"status": "skipped", "reason": str(exc)[:300]}
    try:
        window = find_probe_wechat_window(env)
        if not window:
            return {"status": "skipped", "reason": f"no_visible_wechat_window:{display}"}
        wid, wx, wy, width, height = window
        focus_probe_window(env, wid)
        screenshots: list[str] = []
        before = screenshot_probe_window(env, wid, output_dir / "before-click-probe.png")
        if before:
            screenshots.append(before)
        clicked: list[dict[str, int]] = []
        candidate_crops: list[str] = []
        max_clicks = int(os.environ.get("WECHAT_IMAGE_CACHE_CLICK_MAX", "5"))
        click_repeat = max(1, int(os.environ.get("WECHAT_IMAGE_CACHE_CLICK_REPEAT", "2")))
        wait_seconds = float(os.environ.get("WECHAT_IMAGE_CACHE_CLICK_WAIT_SECONDS", "1.2"))
        for index, (x, y) in enumerate(default_image_cache_clicks()[:max_clicks], start=1):
            if x < 0 or y < 0 or x > width or y > height:
                continue
            crop_source = before or (screenshots[-1] if screenshots else "")
            if crop_source:
                crop = crop_probe_region(Path(crop_source), x, y, output_dir / f"candidate-crop-{index}.png")
                if crop:
                    candidate_crops.append(crop)
            run_probe_command(
                [
                    "xdotool",
                    "mousemove",
                    str(wx + x),
                    str(wy + y),
                    "click",
                    "--repeat",
                    str(click_repeat),
                    "--delay",
                    "80",
                    "1",
                ],
                env=env,
            )
            clicked.append({"x": x, "y": y})
            time.sleep(wait_seconds)
            shot = screenshot_probe_window(env, wid, output_dir / f"after-click-{index}.png")
            if shot:
                screenshots.append(shot)
            run_probe_command(["xdotool", "key", "--clearmodifiers", "Escape"], env=env, check=False)
            time.sleep(0.35)
        return {
            "status": "ok" if clicked else "skipped",
            "display": display,
            "window": {"id": wid, "x": wx, "y": wy, "width": width, "height": height},
            "clicks": clicked,
            "screenshots": screenshots,
            "candidate_crops": candidate_crops,
            "reason": "" if clicked else "no_valid_click_points",
        }
    except Exception as exc:  # GUI probing is best-effort; source sync remains authoritative.
        return {"status": "error", "display": display, "error": str(exc)[:500]}
    finally:
        release_gui_send_lock(lock)


def default_image_cache_clicks() -> list[tuple[int, int]]:
    parsed = parse_probe_clicks(os.environ.get("WECHAT_IMAGE_CACHE_CLICK_POINTS", ""))
    if parsed:
        return parsed
    return [
        (820, 430),  # common center of right-side image bubble
        (820, 360),
        (820, 520),
        (510, 430),  # common center of newest visible received image bubble
        (610, 430),
        (760, 430),
        (510, 360),
        (610, 360),
        (760, 360),
        (510, 520),
        (610, 520),
        (760, 520),
    ]


def parse_probe_clicks(raw: str) -> list[tuple[int, int]]:
    clicks: list[tuple[int, int]] = []
    for item in str(raw or "").split(";"):
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 2:
            continue
        try:
            click = (int(parts[0]), int(parts[1]))
        except ValueError:
            continue
        if click not in clicks:
            clicks.append(click)
    return clicks


def find_probe_wechat_window(env: dict[str, str]) -> tuple[str, int, int, int, int] | None:
    proc = run_probe_command(["xdotool", "search", "--onlyvisible", "--class", "wechat"], env=env, check=False)
    best: tuple[str, int, int, int, int] | None = None
    best_area = 0
    for wid in proc.stdout.split():
        geom = run_probe_command(["xdotool", "getwindowgeometry", "--shell", wid], env=env, check=False).stdout
        values = dict(line.split("=", 1) for line in geom.splitlines() if "=" in line)
        try:
            x, y, width, height = (int(values.get(key, "0")) for key in ("X", "Y", "WIDTH", "HEIGHT"))
        except ValueError:
            continue
        area = width * height
        if area > best_area:
            best = (wid, x, y, width, height)
            best_area = area
    return best


def focus_probe_window(env: dict[str, str], wid: str) -> None:
    proc = run_probe_command(["xdotool", "windowactivate", "--sync", wid], env=env, check=False)
    if proc.returncode != 0:
        proc = run_probe_command(["xdotool", "windowfocus", wid], env=env, check=False)
        if proc.returncode != 0:
            stderr = proc.stderr if isinstance(proc.stderr, str) else str(proc.stderr or "")
            raise RuntimeError(f"Could not focus WeChat window {wid}: {stderr.strip()[:300]}")
    time.sleep(0.2)


def screenshot_probe_window(env: dict[str, str], wid: str, target: Path) -> str:
    if shutil.which("import") is None:
        return ""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        proc = run_probe_command(["import", "-window", wid, str(target)], env=env, check=False)
    except RuntimeError:
        return ""
    return str(target) if proc.returncode == 0 and target.is_file() else ""


def crop_probe_region(source: Path, x: int, y: int, target: Path) -> str:
    try:
        from PIL import Image
    except Exception:
        return ""
    try:
        with Image.open(source) as image:
            width, height = image.size
            crop_size = int(os.environ.get("WECHAT_IMAGE_CACHE_CROP_SIZE", "360"))
            half = max(80, crop_size // 2)
            left = max(0, x - half)
            top = max(0, y - half)
            right = min(width, x + half)
            bottom = min(height, y + half)
            if right - left < 80 or bottom - top < 80:
                return ""
            target.parent.mkdir(parents=True, exist_ok=True)
            image.crop((left, top, right, bottom)).save(target, format="PNG")
            return str(target) if target.is_file() else ""
    except Exception:
        return ""


def gui_probe_image_crop_candidates(
    task: dict[str, Any],
    candidates: list[dict[str, Any]],
    gui_cache_probe: dict[str, Any],
) -> list[dict[str, Any]]:
    if not gui_cache_probe or not should_click_probe_gui_media_cache(task):
        return []
    if not media_gui_cache_probe_reason(task, candidates):
        return []
    click_probe = gui_cache_probe.get("image_click_probe") if isinstance(gui_cache_probe.get("image_click_probe"), dict) else {}
    crop_paths = [Path(str(path)).expanduser() for path in click_probe.get("candidate_crops") or []]
    crop_candidates: list[dict[str, Any]] = []
    now = time.time()
    for index, path in enumerate(crop_paths, start=1):
        if not path.is_file():
            continue
        metadata = image_file_metadata(path)
        if metadata.get("status") != "ok":
            continue
        width = int(metadata.get("width") or 0)
        height = int(metadata.get("height") or 0)
        if width < 120 or height < 120:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        crop_candidates.append(
            {
                "source_path": str(path),
                "mirror_path": str(path),
                "suffix": ".png",
                "size_bytes": size,
                "source_mtime": now - index,
                "status": "gui-crop",
                "matched_by": "gui-cache-probe-crop",
                "metadata": {"image_metadata": metadata, "generated_at": now},
                "score": 220.0 - index,
                "match_reasons": ["gui_cache_probe_crop", f"visible_wechat_image_fallback:{index}"],
            }
        )
    return crop_candidates


def run_probe_command(
    command: list[str],
    *,
    env: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            check=check,
            timeout=float(os.environ.get("WECHAT_GUI_COMMAND_TIMEOUT", "8")),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"{' '.join(command)} failed: {detail[:500]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{' '.join(command)} timed out after {exc.timeout}s") from exc


def enrich_media_resolution_copies_with_image_read(copied: list[dict[str, Any]], artifact_dir: Path) -> None:
    for item in copied:
        if not isinstance(item, dict):
            continue
        path = Path(str(item.get("task_copy_path") or "")).expanduser()
        suffix = str(item.get("suffix") or path.suffix).lower()
        if suffix not in OCR_IMAGE_SUFFIXES:
            continue
        metadata = image_file_metadata(path)
        if metadata:
            item["image_metadata"] = metadata
        if metadata.get("status") not in {"ok", "metadata_unavailable"}:
            item["ocr"] = {"status": "skipped", "reason": metadata.get("status") or "image_unreadable"}
            continue
        item["ocr"] = ocr_image_file(path, artifact_dir / "image_text")


def image_file_metadata(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except Exception:
        return {"status": "metadata_unavailable", "reason": "pillow_missing"}
    try:
        with Image.open(path) as image:
            return {
                "status": "ok",
                "width": int(image.width),
                "height": int(image.height),
                "mode": str(image.mode),
                "format": str(image.format or ""),
            }
    except Exception as exc:
        return {"status": "unreadable_image", "error": str(exc)[:240]}


def ocr_image_file(path: Path, output_dir: Path) -> dict[str, Any]:
    if os.environ.get("WECHAT_WORKER_DISABLE_IMAGE_OCR"):
        return {"status": "skipped", "reason": "disabled"}
    if shutil.which("tesseract") is None:
        return {"status": "skipped", "reason": "tesseract_missing"}
    languages = tesseract_language_string()
    if not languages:
        return {"status": "skipped", "reason": "no_tesseract_languages"}
    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = unique_intake_target(output_dir, f"{path.stem}.ocr.txt", index=1)
    ocr_input = prepare_ocr_input_image(path, output_dir)
    psms = [os.environ.get("WECHAT_IMAGE_OCR_PSM", "6"), "11"]
    seen: set[str] = set()
    attempts: list[dict[str, Any]] = []
    timeout = float(os.environ.get("WECHAT_IMAGE_OCR_TIMEOUT", "30"))
    for psm in psms:
        if not psm or psm in seen:
            continue
        seen.add(psm)
        command = ["tesseract", str(ocr_input), "stdout", "-l", languages, "--psm", psm]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            attempts.append({"psm": psm, "status": "error", "error": str(exc)[:300]})
            continue
        text = normalize_ocr_text(proc.stdout)
        attempts.append(
            {
                "psm": psm,
                "returncode": proc.returncode,
                "text_chars": len(text),
                "stderr": collapse_context_text(proc.stderr, max_len=300) if proc.stderr.strip() else "",
            }
        )
        if text:
            text_path.write_text(text + "\n", encoding="utf-8")
            return {
                "status": "ok",
                "text_path": str(text_path),
                "text_preview": collapse_context_text(text, max_len=500),
                "languages": languages,
                "psm": psm,
                "ocr_input_path": str(ocr_input),
                "attempts": attempts,
            }
    text_path.write_text("", encoding="utf-8")
    return {
        "status": "empty",
        "text_path": str(text_path),
        "text_preview": "",
        "languages": languages,
        "ocr_input_path": str(ocr_input),
        "attempts": attempts,
    }


def prepare_ocr_input_image(path: Path, output_dir: Path) -> Path:
    """Return a Tesseract-friendly image, repairing partial WeChat JPEGs when possible."""
    try:
        from PIL import Image, ImageFile, ImageOps
    except Exception:
        return path
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            target = unique_intake_target(output_dir, f"{path.stem}.ocr-source.png", index=1)
            image.save(target, format="PNG")
            return target if target.is_file() else path
    except Exception:
        return path


def normalize_ocr_text(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def tesseract_language_string() -> str:
    env_value = os.environ.get("WECHAT_IMAGE_OCR_LANGS")
    if env_value:
        return env_value
    available = tesseract_available_languages()
    priority = ["eng", "chi_sim", "chi_tra", "jpn"]
    selected = [lang for lang in priority if lang in available]
    if selected:
        return "+".join(selected)
    fallback = [lang for lang in available if lang != "osd"]
    return fallback[0] if fallback else ""


def tesseract_available_languages() -> set[str]:
    try:
        proc = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return set()
    languages: set[str] = set()
    for line in proc.stdout.splitlines():
        item = line.strip()
        if not item or item.startswith("List of available"):
            continue
        languages.add(item)
    return languages


def prepare_file_intake_preflight(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    intake_dir = artifact_dir / "intake"
    intake_dir.mkdir(parents=True, exist_ok=True)
    source_paths = extract_recent_synced_files_from_task(task)
    copied: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for index, source in enumerate(source_paths[:8], start=1):
        if not source.is_file():
            skipped.append({"path": str(source), "reason": "missing"})
            continue
        try:
            stat = source.stat()
        except OSError as exc:
            skipped.append({"path": str(source), "reason": f"stat-failed: {exc}"[:160]})
            continue
        target = unique_intake_target(intake_dir, source.name, index=index)
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            skipped.append({"path": str(source), "reason": f"copy-failed: {exc}"[:160]})
            continue
        copied.append(
            {
                "source_path": str(source),
                "saved_path": str(target),
                "filename": source.name,
                "suffix": source.suffix.lower(),
                "size_bytes": stat.st_size,
                "sha256": sha256_file(target),
            }
        )
    manifest = {
        "task_id": task.get("id"),
        "chat": task.get("chat"),
        "source": task.get("source") if isinstance(task.get("source"), dict) else {},
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "copied": copied,
        "skipped": skipped,
        "status": "ok" if copied else "missing",
        "policy": "bare file upload intake only; no deep read/summary unless explicitly requested",
    }
    manifest_json = artifact_dir / "file_intake_manifest.json"
    manifest_md = artifact_dir / "file_intake_manifest.md"
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest_md.write_text(file_intake_markdown(manifest), encoding="utf-8")
    manifest["manifest_json"] = str(manifest_json)
    manifest["manifest_md"] = str(manifest_md)
    return manifest


def extract_recent_synced_files_from_task(task: dict[str, Any]) -> list[Path]:
    request = str(task.get("request") or "")
    files: list[Path] = []
    for line in request.splitlines():
        match = re.match(r"^-\s+(?P<path>.+?)\s+\((?P<size>\d+)\s+bytes\)\s*$", line.strip())
        if not match:
            continue
        raw_path = match.group("path")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        resolved = path.resolve()
        if resolved not in files:
            files.append(resolved)
    title = current_request_file_title(request)
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    local_id = str(source.get("local_id") or "")
    title_matches = [path for path in files if title and path.name == title]
    if title_matches:
        return title_matches
    local_id_matches = [
        path for path in files
        if local_id and (path.name.startswith(f"{local_id}_") or f"/{local_id}_" in path.as_posix())
    ]
    if local_id_matches:
        return local_id_matches
    if files:
        return ranked_media_paths(files)[:8]
    media_resolution = (task.get("preflight") or {}).get("media_resolution") if isinstance(task.get("preflight"), dict) else {}
    if isinstance(media_resolution, dict):
        resolved = [
            Path(str(item.get("task_copy_path") or "")).expanduser().resolve()
            for item in media_resolution.get("copied") or []
            if isinstance(item, dict) and item.get("task_copy_path")
        ]
        if resolved:
            return resolved
    mirror_matches = [Path(str(item.get("mirror_path") or "")).expanduser().resolve() for item in resolve_synced_media_from_mirror(task, limit=8)]
    for path in mirror_matches:
        if path.is_file() and path not in files:
            files.append(path)
    return ranked_media_paths(files)[:8]


def ranked_media_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if resolved not in unique:
            unique.append(resolved)
    return sorted(unique, key=media_path_sort_key)


def media_path_sort_key(path: Path) -> tuple[int, float, int, str]:
    try:
        stat = path.stat()
    except OSError:
        return (-1000, 0.0, 0, path.name)
    suffix = path.suffix.lower()
    score = 0
    if suffix in IMAGE_SUFFIXES:
        score += 80
    elif suffix in VIDEO_SUFFIXES:
        score += 70
    elif suffix == ".pdf":
        score += 65
    elif suffix == ".dat":
        score -= 30
    elif suffix in PREFERRED_MEDIA_SUFFIXES:
        score += 50
    return (score, stat.st_mtime, stat.st_size, path.name)


def resolve_synced_media_from_mirror(
    task: dict[str, Any],
    *,
    limit: int = 8,
    suffixes: set[str] | None = None,
) -> list[dict[str, Any]]:
    chat = str(task.get("chat") or "").strip()
    if not chat:
        return []
    db = Path(os.environ.get("WECHAT_MIRROR_DB") or DEFAULT_DB)
    if not db.is_file():
        return []
    accepted_suffixes = {item.lower() for item in (suffixes or PREFERRED_MEDIA_SUFFIXES)}
    tokens = extract_media_tokens_from_task(task)
    windows = task_media_source_windows(task)
    try:
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                """
                SELECT media_files.source_path, media_files.mirror_path, media_files.suffix,
                       media_files.size_bytes, media_files.source_mtime, media_files.status,
                       media_files.matched_by, media_files.metadata_json, media_files.updated_at
                FROM media_files
                JOIN chats ON chats.id = media_files.chat_id
                WHERE chats.name = ?
                ORDER BY media_files.updated_at DESC, media_files.source_mtime DESC
                LIMIT 240
                """,
                (chat,),
            ).fetchall()
    except sqlite3.Error:
        return []
    candidates: list[dict[str, Any]] = []
    for row in rows:
        item = media_db_row_to_candidate(row)
        path = Path(str(item.get("mirror_path") or "")).expanduser()
        suffix = str(item.get("suffix") or path.suffix).lower()
        if accepted_suffixes and suffix not in accepted_suffixes and path.suffix.lower() not in accepted_suffixes:
            continue
        if not path.is_file():
            continue
        score, reasons = score_media_candidate(item, tokens=tokens, windows=windows)
        if score <= 0 and tokens:
            continue
        if score <= 0 and windows:
            continue
        if score <= 0 and not fallback_recent_media_candidate(item):
            continue
        item["score"] = score
        item["match_reasons"] = reasons
        item["suffix"] = suffix or path.suffix.lower()
        candidates.append(item)
    candidates.sort(key=lambda item: (float(item.get("score") or 0), float(item.get("source_mtime") or 0), int(item.get("size_bytes") or 0)), reverse=True)
    return candidates[:limit]


def media_db_row_to_candidate(row: Any) -> dict[str, Any]:
    source_path, mirror_path, suffix, size_bytes, source_mtime, status, matched_by, metadata_json, updated_at = row
    metadata: dict[str, Any] = {}
    try:
        parsed = json.loads(metadata_json or "{}")
        if isinstance(parsed, dict):
            metadata = parsed
    except json.JSONDecodeError:
        metadata = {}
    return {
        "source_path": source_path,
        "mirror_path": mirror_path,
        "suffix": str(suffix or Path(str(mirror_path or "")).suffix).lower(),
        "size_bytes": int(size_bytes or 0),
        "source_mtime": float(source_mtime or 0.0),
        "status": status,
        "matched_by": matched_by,
        "updated_at": updated_at,
        "metadata": metadata,
    }


def score_media_candidate(item: dict[str, Any], *, tokens: list[str], windows: list[tuple[float, float]]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text = json.dumps(item, ensure_ascii=False).lower()
    for token in tokens:
        if token and token.lower() in text:
            score += 120
            reasons.append(f"token:{token[:16]}")
            break
    source_mtime = float(item.get("source_mtime") or 0.0)
    for start, end in windows:
        if start <= source_mtime <= end:
            score += 70
            reasons.append("source_mtime_window")
            break
    suffix = str(item.get("suffix") or "").lower()
    status = str(item.get("status") or "")
    decode_status = str((item.get("metadata") or {}).get("decode_status") or "")
    if suffix in IMAGE_SUFFIXES:
        score += 35
        reasons.append("readable_image")
    elif suffix in VIDEO_SUFFIXES:
        score += 30
        reasons.append("video")
    elif suffix == ".pdf":
        score += 25
        reasons.append("pdf")
    elif suffix == ".dat":
        score -= 20
        reasons.append("raw_dat_penalty")
    if status in {"decoded", "copied", "exists"}:
        score += 10
    if "decoded" in decode_status:
        score += 10
        reasons.append(decode_status)
    if str(item.get("matched_by") or "").startswith("associated:"):
        score += 8
        reasons.append(str(item.get("matched_by")))
    return score, reasons


def fallback_recent_media_candidate(item: dict[str, Any]) -> bool:
    suffix = str(item.get("suffix") or "").lower()
    if suffix in RAW_WECHAT_MEDIA_SUFFIXES:
        return False
    if suffix not in PREFERRED_MEDIA_SUFFIXES:
        return False
    try:
        source_mtime = float(item.get("source_mtime") or 0.0)
    except (TypeError, ValueError):
        source_mtime = 0.0
    if source_mtime <= 0:
        return False
    max_age = float(os.environ.get("WECHAT_WORKER_RECENT_MEDIA_FALLBACK_SECONDS", "1800"))
    return time.time() - source_mtime <= max_age


def task_media_source_windows(task: dict[str, Any]) -> list[tuple[float, float]]:
    window = float(os.environ.get("WECHAT_WORKER_MEDIA_SOURCE_WINDOW_SECONDS", "360"))
    times: list[float] = []
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    for raw in (source.get("create_time"),):
        value = float_or_none(raw)
        if value:
            times.append(value)
    for row in task.get("context") or []:
        if not isinstance(row, dict):
            continue
        value = float_or_none(row.get("create_time"))
        if value:
            times.append(value)
    windows: list[tuple[float, float]] = []
    for value in times:
        start = max(0.0, value - window)
        end = min(time.time() + 120.0, value + window)
        if (start, end) not in windows:
            windows.append((start, end))
    return windows


def float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def refresh_media_sync_for_task(task: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT"):
        return {"status": "disabled"}
    chat = str(task.get("chat") or "").strip()
    if not chat:
        return {"status": "skipped", "error": "missing chat"}
    tokens = extract_media_tokens_from_task(task, limit=8)
    command = [
        sys.executable,
        str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_media_sync.py"),
        "--chat",
        chat,
        "--auto-source",
        "--summary-only",
        "--record-empty",
        "--db",
        str(Path(os.environ.get("WECHAT_MIRROR_DB") or DEFAULT_DB)),
    ]
    windows = task_media_source_windows(task)
    if windows:
        start = min(item[0] for item in windows)
        end = max(item[1] for item in windows)
        command += ["--since-epoch", str(start), "--until-epoch", str(end)]
    else:
        command += ["--since-minutes", os.environ.get("WECHAT_WORKER_MEDIA_SYNC_SINCE_MINUTES", "30")]
    for token in tokens:
        command += ["--match-token", token]
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=float(os.environ.get("WECHAT_WORKER_MEDIA_SYNC_TIMEOUT", "30")),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "error", "error": str(exc)[:500], "command": redact_command(command)}
    payload: dict[str, Any]
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
        payload = parsed if isinstance(parsed, dict) else {"stdout": proc.stdout.strip()[:1000]}
    except json.JSONDecodeError:
        payload = {"stdout": proc.stdout.strip()[:1000]}
    payload["returncode"] = proc.returncode
    payload["command"] = redact_command(command)
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr.strip()[:1000]
    return payload


def media_resolution_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# WeChat Media Resolution",
        "",
        f"- Task: `{manifest.get('task_id') or ''}`",
        f"- Chat: `{manifest.get('chat') or ''}`",
        f"- Status: `{manifest.get('status') or ''}`",
        f"- Resolver: `{manifest.get('resolver') or ''}`",
        "",
        "## Resolved Files",
    ]
    copied = manifest.get("copied") if isinstance(manifest.get("copied"), list) else []
    if copied:
        for item in copied:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('task_copy_path')}` from `{item.get('mirror_path')}` "
                f"score={item.get('score')} reasons={', '.join(str(reason) for reason in item.get('match_reasons') or [])}"
            )
            metadata = item.get("image_metadata") if isinstance(item.get("image_metadata"), dict) else {}
            if metadata:
                dims = ""
                if metadata.get("width") and metadata.get("height"):
                    dims = f" {metadata.get('width')}x{metadata.get('height')}"
                lines.append(f"  - Image metadata: `{metadata.get('status')}`{dims} {metadata.get('format') or ''}".rstrip())
            ocr = item.get("ocr") if isinstance(item.get("ocr"), dict) else {}
            if ocr:
                lines.append(f"  - OCR: `{ocr.get('status')}` `{ocr.get('text_path') or ''}`")
                if ocr.get("text_preview"):
                    lines.append(f"  - OCR preview: {collapse_context_text(ocr.get('text_preview'), max_len=240)}")
    else:
        lines.append("- none")
    skipped = manifest.get("skipped") if isinstance(manifest.get("skipped"), list) else []
    if skipped:
        lines.extend(["", "## Skipped"])
        for item in skipped:
            lines.append(f"- `{item.get('path')}`: {item.get('reason')}")
    gui_probe = manifest.get("gui_cache_probe") if isinstance(manifest.get("gui_cache_probe"), dict) else {}
    if gui_probe:
        lines.extend(
            [
                "",
                "## GUI Cache Probe",
                f"- Status: `{gui_probe.get('status') or ''}`",
                f"- Output: `{gui_probe.get('output_dir') or ''}`",
            ]
        )
        if gui_probe.get("stderr"):
            lines.append(f"- Stderr: `{collapse_context_text(gui_probe.get('stderr'), max_len=240)}`")
        click_probe = gui_probe.get("image_click_probe") if isinstance(gui_probe.get("image_click_probe"), dict) else {}
        if click_probe:
            lines.append(f"- Image click probe: `{click_probe.get('status') or ''}` clicks={len(click_probe.get('clicks') or [])}")
    second_refresh = manifest.get("second_refresh") if isinstance(manifest.get("second_refresh"), dict) else {}
    if second_refresh:
        lines.extend(
            [
                "",
                "## Second Sync",
                f"- Status: `{second_refresh.get('status') or second_refresh.get('returncode')}`",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def current_request_file_title(request: str) -> str:
    in_current = False
    for line in str(request or "").splitlines():
        stripped = line.strip()
        if stripped == "Current coalesced request:":
            in_current = True
            continue
        if in_current and not stripped:
            break
        if in_current and stripped.lower().startswith("title:"):
            return stripped.split(":", 1)[1].strip()
    match = re.search(r"(?im)^title:\s*(.+?)\s*$", str(request or ""))
    return match.group(1).strip() if match else ""


def unique_intake_target(intake_dir: Path, filename: str, *, index: int) -> Path:
    original = Path(filename)
    stem = safe_slug(original.stem) or f"file-{index}"
    suffix = original.suffix.lower()
    target = intake_dir / f"{stem}{suffix}"
    counter = 2
    while target.exists():
        target = intake_dir / f"{stem}-{counter}{suffix}"
        counter += 1
    return target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_intake_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# WeChat File Intake",
        "",
        f"- Task: `{manifest.get('task_id') or ''}`",
        f"- Chat: `{manifest.get('chat') or ''}`",
        f"- Status: `{manifest.get('status') or ''}`",
        "",
        "## Files",
    ]
    copied = manifest.get("copied") if isinstance(manifest.get("copied"), list) else []
    if copied:
        for item in copied:
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"- Filename: `{item.get('filename') or ''}`",
                    f"  - Size: `{item.get('size_bytes') or 0}` bytes",
                    f"  - Type: `{item.get('suffix') or ''}`",
                    f"  - SHA-256: `{item.get('sha256') or ''}`",
                    f"  - Saved copy: `{item.get('saved_path') or ''}`",
                ]
            )
    else:
        lines.append("- No exact local file copy was available yet.")
    skipped = manifest.get("skipped") if isinstance(manifest.get("skipped"), list) else []
    if skipped:
        lines.extend(["", "## Skipped"])
        for item in skipped:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('path') or ''}`: {item.get('reason') or ''}")
    lines.append("")
    return "\n".join(lines)


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
    story_result = task.get("story_confirmation_result") if isinstance(task.get("story_confirmation_result"), dict) else {}
    approved_story_message = str(task.get("approved_story_message") or story_result.get("message") or "").strip()
    if approved_story_message:
        text = collapse_context_text(approved_story_message, max_len=6000)
        if text and text not in parts:
            parts.append("Approved story for video generation:\n" + text)
    story_files = task.get("approved_story_files")
    if not isinstance(story_files, list):
        story_files = story_result.get("files") if isinstance(story_result.get("files"), list) else []
    file_lines = [str(path) for path in story_files if str(path).strip()]
    if file_lines:
        text = "Approved story file(s):\n" + "\n".join(f"- {path}" for path in file_lines)
        if text not in parts:
            parts.append(text)
    for item in task_interruptions(task):
        text = collapse_context_text(item.get("request") or item.get("request_excerpt"), max_len=3000)
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts)


def is_video_publish_task(task: dict[str, Any]) -> bool:
    routine = task.get("routine") if isinstance(task.get("routine"), dict) else {}
    if str(routine.get("id") or "") == "video_publish_existing":
        return True
    if str(task.get("status") or "") == EXISTING_VIDEO_PUBLISH_PENDING_STATUS:
        return True
    route = task_route_decision(task)
    if route:
        route_kind = str(route.get("route_kind") or "")
        if route_kind == "generate_video":
            return bool(route.get("public_publish_allowed"))
        if route_kind == "publish_video":
            return bool(route.get("public_publish_allowed"))
        if route_kind in {"process_existing_video", "file_download_or_save"}:
            return bool(route.get("needs_recent_media"))
        return False
    text = task_focus_text(task).lower()
    if has_public_publish_intent(text):
        return True
    return any(marker in text for marker in ("subtitle", "caption", "transcript", "字幕", "转写", "校正"))


def is_generate_video_task(task: dict[str, Any]) -> bool:
    route = task_route_decision(task)
    if route:
        return str(route.get("route_kind") or "") == "generate_video"
    text = task_focus_text(task).lower()
    generation_markers = ("generate", "create", "make", "生成", "创作", "做")
    return "video" in text and any(marker in text for marker in generation_markers)


def generated_video_monitor_only(task: dict[str, Any]) -> bool:
    """Return true when a paid XYQ thread already exists for this request.

    This is an idempotence guard, not a story-specific rule: once the queue has
    evidence that a Xiaoyunque request was submitted or credits were consumed,
    the worker may monitor/download that thread but must not submit/continue a
    second paid action for the same logical request.
    """
    route = task_route_decision(task)
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    credit_guard = task.get("credit_guard") if isinstance(task.get("credit_guard"), dict) else {}
    submit_probe = task.get("generated_video_submit_probe") if isinstance(task.get("generated_video_submit_probe"), dict) else {}
    if bool(route.get("no_new_xyq_submit")) or bool(route.get("monitor_only_no_resubmit")):
        return True
    if bool(monitor.get("monitor_only_no_resubmit")) or bool(monitor.get("no_new_xyq_submit")):
        return True
    if bool(credit_guard.get("enabled")):
        return True
    if submit_probe.get("ok") and str(submit_probe.get("thread_url") or submit_probe.get("page_id") or ""):
        return True
    if task.get("generation_wait_count") and monitor.get("thread_url"):
        return True
    return False


def generated_video_stage_permissions(task: dict[str, Any]) -> dict[str, Any]:
    text = task_focus_text(task)
    lowered = text.lower()
    route = task_route_decision(task)
    route_kind = str(route.get("route_kind") or "")
    public_publish = bool(route.get("public_publish_allowed")) if route else has_public_publish_intent(text)
    lazyedit_import = wants_lazyedit_import(text) or public_publish
    story_generation = route_kind == "generate_video" or any(marker in lowered for marker in ("story", "script", "prompt", "故事", "脚本", "劇本", "提示词", "提示詞", "lalachan", "raraxia", "ayachan", "sasakun", "啦啦侠", "阿芽酱", "飒飒君"))
    video_generation = route_kind == "generate_video" or any(marker in lowered for marker in ("video", "mp4", "视频", "影片", "小云雀", "seedance", "xyq"))
    return {
        "story_generation": story_generation,
        "video_generation": video_generation,
        "generation": bool(story_generation or video_generation),
        "wechat_send_back": True,
        "lazyedit_import": lazyedit_import,
        "public_publish": public_publish,
        "publication": public_publish,
        "publish_platforms": detect_publish_platforms(task, current_only=True) if public_publish else [],
        "generation_is_publication": False,
        "stage_boundary": "generation creates/downloads/sends artifacts; publication posts to public platforms and requires explicit current-message permission",
        "lazyedit_requires_current_request": True,
        "public_publish_requires_current_request": True,
        "scope": "current_request_only",
    }


def generated_video_orchestration_routine(task: dict[str, Any]) -> list[dict[str, Any]]:
    stages = generated_video_stage_permissions(task)
    publish_platforms = stages.get("publish_platforms") or []
    return [
        {
            "id": "route_contract",
            "enabled": True,
            "owner": "fast_chat_agent",
            "entrypoint": "prepare_worker_preflight -> write_generated_video_contract",
            "success": "route_decision and stage_permissions are persisted before worker execution",
        },
        {
            "id": "story_and_prompt",
            "enabled": bool(stages.get("story_generation")),
            "owner": "worker_agent",
            "entrypoint": "run_worker_codex_once with LALACHAN/Xiaoyunque tool context",
            "success": "story markdown, Xiaoyunque prompt, and browser submission evidence are saved",
        },
        {
            "id": "xyq_submit_or_resume",
            "enabled": bool(stages.get("video_generation")),
            "owner": "worker_agent",
            "entrypoint": "Xiaoyunque browser helpers; return submitted/running/blocked state or MP4",
            "success": "new MP4 path or resumable monitor state with thread_url/page_id",
        },
        {
            "id": "xyq_deterministic_monitor",
            "enabled": bool(stages.get("video_generation")),
            "owner": "queue_orchestrator",
            "entrypoint": "deterministic_generated_video_monitor_result",
            "success": "downloaded MP4 or generation_waiting requeue with next_poll_at",
        },
        {
            "id": "wechat_artifact_delivery_gate",
            "enabled": bool(stages.get("wechat_send_back")),
            "owner": "queue_orchestrator",
            "entrypoint": "send_result_with_retries -> apply_send_outcome",
            "success": "sent_file_paths contains the generated MP4 before any poststage starts",
            "failure": "send_deferred_artifact or send_deferred_locked; LazyEdit/public publish remains blocked",
        },
        {
            "id": "lazyedit_poststage",
            "enabled": bool(stages.get("lazyedit_import")),
            "owner": "queue_orchestrator",
            "entrypoint": "deterministic_generated_video_poststage_result",
            "depends_on": "wechat_artifact_delivery_gate",
            "success": "LazyEdit import/process completes or requeues generation_poststage_pending",
        },
        {
            "id": "public_publish",
            "enabled": bool(stages.get("public_publish")),
            "owner": "queue_orchestrator",
            "entrypoint": "run_generated_video_lazyedit_command --platforms",
            "depends_on": "lazyedit_poststage",
            "platforms": publish_platforms,
            "success": "requested public platforms finish or poststage requeues for later verification",
        },
    ]


def should_preflight_autopublish(task: dict[str, Any]) -> bool:
    route = task_route_decision(task)
    if route:
        route_kind = str(route.get("route_kind") or "")
        if route_kind == "generate_video":
            return False
        if route_kind == "publish_video":
            return bool(route.get("public_publish_allowed"))
        if route_kind in {"process_existing_video", "file_download_or_save"}:
            return bool(route.get("needs_recent_media"))
        return False
    text = task_focus_text(task).lower()
    if any(marker in text for marker in ("nutstore", "autopublish", "publish folder")):
        return True
    return has_public_publish_intent(text)


def should_resolve_recent_video_artifact(task: dict[str, Any]) -> bool:
    route = task_route_decision(task)
    if route:
        route_kind = str(route.get("route_kind") or "")
        if route_kind not in {"file_download_or_save", "process_existing_video"}:
            return False
        if not bool(route.get("needs_recent_media")):
            return False
    text = task_focus_text(task).lower()
    asks_video = any(marker in text for marker in ("video", "mp4", "视频", "影片"))
    asks_artifact_action = any(
        marker in text
        for marker in (
            "send",
            "give me",
            "download",
            "save",
            "submit",
            "lazyedit",
            "发",
            "发送",
            "回传",
            "下载",
            "保存",
            "提交",
        )
    )
    return bool(asks_video and asks_artifact_action)


def write_generated_video_contract(task: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    stages = generated_video_stage_permissions(task)
    contract = {
        "task_id": task.get("id"),
        "chat": task.get("chat"),
        "source": task.get("source") or {},
        "route_decision": task_route_decision(task),
        "current_request": task_focus_text(task),
        "stage_permissions": stages,
        "verification_policy": generated_video_verification_policy(task),
        "orchestration_routine": generated_video_orchestration_routine(task),
        "rules": [
            "Re-check route_decision against the current request before acting.",
            "Follow orchestration_routine in order; do not invent a new workflow for routine stages.",
            "For route_kind=generate_video, create or import a new video; do not process old WeChat MP4 files.",
            "Always send the verified generated MP4 back to the source WeChat chat when GUI sending is available.",
            "Treat story generation, video generation/download/send-back, LazyEdit import/process, and public publishing as separate stages.",
            "If task.interruptions contains newer same-chat messages, read them all before the next action and revise the routine plan dynamically.",
            "For story/video work, a newer story revision/show/confirmation request pauses stale video submit/polling; send the updated story to the group and confirm before generating unless the latest message explicitly authorizes generation.",
            "If the user says a submitted website generation was stopped or cancelled, do not treat that stale run as success; update the story/prompt and continue from the latest confirmed stage.",
            "Generation is not publication: generating/downloading/sending a video never authorizes LazyEdit import or public posting.",
            "Do not publish/post/upload to Shipinhao, YouTube, Instagram, AutoPublish, or public queues unless stage_permissions.public_publish is true.",
            "Do not import/process in LazyEdit unless stage_permissions.lazyedit_import is true.",
            "For LazyEdit stages, use the resumed Codex worker agent to call mature routines/scripts/commands; deterministic code is only for source isolation, queue probes, duplicate guards, terminal verification, and artifact delivery.",
            "LazyEdit correction context must include the WeChat message sent with the video; AI-generated video publication must also append the generated story/script and Xiaoyunque/Seedance prompt.",
            "If the browser cannot submit or download a new video, return an explicit blocked/in-progress status instead of claiming success.",
            "Long Xiaoyunque rendering must stay in the queue with deterministic status probes; do not spend model tokens just to poll.",
            "Paid Xiaoyunque/Seedance idempotence: one logical WeChat request owns at most one paid generation thread unless the current user explicitly asks for a new paid rerun.",
            "If generated_video_monitor.thread_url, generated_video_submit_probe, credit_guard, no_new_xyq_submit, or monitor_only_no_resubmit exists, do not submit, retry, continue, or create another Xiaoyunque job; only monitor/download/send the existing thread result.",
        ],
        "expected_artifacts": [
            "story markdown",
            "Xiaoyunque prompt markdown",
            "verification screenshot/log",
            "new MP4 or blocked/in-progress status",
        ],
    }
    json_path = artifact_dir / "generated_video_route_contract.json"
    md_path = artifact_dir / "generated_video_route_contract.md"
    json_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(format_generated_video_contract_markdown(contract), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "rule": "Worker must satisfy this contract before reporting success."}


def inspect_generated_video_status(task: dict[str, Any]) -> dict[str, Any] | None:
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    artifact_dir = Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))
    output_dir = Path(str(monitor.get("output_dir") or artifact_dir))
    files = generated_video_existing_files(output_dir, monitor)
    if files:
        return {"status": "done", "files": [str(path) for path in files], "output_dir": str(output_dir)}
    probe = latest_generated_video_probe(output_dir)
    if not probe:
        if monitor.get("thread_url") and monitor.get("page_id"):
            return {"status": "waiting", "files": [], "monitor": monitor, "reason": "monitor-state-present-no-probe-yet"}
        return None
    status_text = generated_video_probe_status_text(probe)
    lowered = status_text.lower()
    if generated_video_probe_has_completed_artifact(probe):
        status = "done" if generated_video_existing_files(output_dir, monitor) else "download_ready"
    elif any(marker in status_text for marker in ("完成", "下载")):
        status = "done" if generated_video_existing_files(output_dir, monitor) else "waiting"
    elif any(marker in status_text for marker in ("失败", "内部错误", "审核", "合规", "积分不足", "余额不足")):
        status = "blocked"
    elif any(marker in status_text for marker in ("生成中", "排队", "还需", "等待", "进行中")):
        status = "generating"
    elif any(marker in lowered for marker in ("generating", "queued", "running", "waiting")):
        status = "generating"
    else:
        status = "waiting"
    return {
        "status": status,
        "files": [str(path) for path in generated_video_existing_files(output_dir, monitor)],
        "monitor": monitor,
        "output_dir": str(output_dir),
        "probe_file": str(probe.get("_path") or ""),
        "status_text": collapse_context_text(status_text, max_len=500),
    }


def generated_video_existing_files(output_dir: Path, monitor: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    filename = str(monitor.get("filename") or "")
    if filename:
        candidates.append(output_dir / filename)
    candidates.extend(sorted(output_dir.glob("*.mp4"), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True))
    video_dir = Path(os.environ.get("LALACHAN_VIDEO_DIR", "/home/lachlan/ProjectsLFS/LALACHAN/Videos"))
    if filename:
        candidates.append(video_dir / filename)
    found: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved.suffix.lower() in VIDEO_SUFFIXES and resolved not in found:
            found.append(resolved)
    return found


def latest_generated_video_probe(output_dir: Path) -> dict[str, Any] | None:
    patterns = ["watch_*.json", "poll_*.json"]
    probes: list[Path] = []
    for pattern in patterns:
        probes.extend(output_dir.glob(pattern))
    probes = [path for path in probes if path.is_file()]
    if not probes:
        return None
    latest = max(probes, key=lambda path: path.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        data["_path"] = str(latest)
        return data
    return None


def generated_video_probe_status_text(probe: dict[str, Any] | None) -> str:
    if not isinstance(probe, dict):
        return ""
    parts = [
        "\n".join(str(item) for item in probe.get("status") or []),
        str(probe.get("tail") or ""),
        str(probe.get("bodyTail") or ""),
    ]
    return "\n".join(part for part in parts if part)


def generated_video_probe_has_completed_artifact(probe: dict[str, Any] | None) -> bool:
    if not isinstance(probe, dict):
        return False
    if probe.get("videos"):
        return True
    text = generated_video_probe_status_text(probe)
    lowered = text.lower()
    if "final_video.mp4" in lowered and ("mp4" in lowered or "视频" in text or "生成结果" in text):
        return True
    return bool(
        "渲染合成最终视频" in text
        and "已完成" in text
        and ("生成结果" in text or "视频\n共" in text or "final_video" in lowered)
    )


def discover_generated_video_monitor_from_probe(task: dict[str, Any]) -> dict[str, str]:
    artifact_dir = Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))
    existing = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    output_dir = Path(str(existing.get("output_dir") or artifact_dir))
    probe = latest_generated_video_probe(output_dir)
    if not probe:
        return {}
    href = str(probe.get("href") or "")
    if "xyq.jianying.com" not in href or "thread_id=" not in href:
        return {}
    cdp_url = str(existing.get("cdp_url") or os.environ.get("WECHAT_WORKER_XYQ_CDP_URL") or os.environ.get("XYQ_CDP_URL") or "http://127.0.0.1:9222")
    page_id = str(existing.get("page_id") or page_id_for_thread_url(cdp_url, href) or "")
    if not page_id:
        return {}
    status_text = generated_video_probe_status_text(probe)
    return {
        "cdp_url": cdp_url,
        "page_id": page_id,
        "thread_url": href,
        "title": str(probe.get("title") or ""),
        "output_dir": str(output_dir),
        "filename": str(existing.get("filename") or f"{safe_slug(str(task.get('id') or 'generated-video'))}.mp4"),
        "probe_file": str(probe.get("_path") or ""),
        "status_text": collapse_context_text(status_text, max_len=500),
        "discovered_from": "generated_video_probe",
        "discovered_at": datetime.now().isoformat(timespec="seconds"),
    }


def format_generated_video_contract_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# Generated Video Route Contract",
        "",
        f"- Task: {contract.get('task_id')}",
        f"- Chat: {contract.get('chat')}",
        f"- Source: {json.dumps(contract.get('source') or {}, ensure_ascii=False)}",
        "",
        "## Current Request",
        str(contract.get("current_request") or "").strip() or "(empty)",
        "",
        "## Route Decision",
        "```json",
        json.dumps(contract.get("route_decision") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Stage Permissions",
        "```json",
        json.dumps(contract.get("stage_permissions") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Required Checks",
    ]
    for rule in contract.get("rules") or []:
        lines.append(f"- {rule}")
    lines.extend(["", "## Orchestration Routine"])
    for routine in contract.get("orchestration_routine") or []:
        if not isinstance(routine, dict):
            continue
        enabled = "enabled" if routine.get("enabled") else "disabled"
        line = f"- `{routine.get('id')}` ({enabled}, owner: {routine.get('owner')})"
        if routine.get("depends_on"):
            line += f"; after `{routine.get('depends_on')}`"
        if routine.get("entrypoint"):
            line += f"; entrypoint: {routine.get('entrypoint')}"
        lines.append(line)
    lines.extend(["", "## Expected Artifacts"])
    for artifact in contract.get("expected_artifacts") or []:
        lines.append(f"- {artifact}")
    return "\n".join(lines).rstrip() + "\n"


def enforce_worker_result_contract(task: dict[str, Any], result: dict[str, Any], raw_text: str) -> dict[str, Any]:
    if not is_generate_video_task(task):
        return result
    stages = generated_video_stage_permissions(task)
    public_allowed = bool(stages.get("public_publish"))
    lazyedit_allowed = bool(stages.get("lazyedit_import"))
    text = "\n".join(
        [
            str(result.get("message") or ""),
            str(result.get("confirmation") or ""),
            str(raw_text or ""),
            "\n".join(str(item) for item in result.get("files") or []),
        ]
    )
    lowered = text.lower()
    public_markers = ("shipinhao", "视频号", "youtube", "instagram", "public platform", "发布", "投稿")
    if not public_allowed and any(marker in lowered for marker in public_markers):
        guarded = dict(result)
        guarded["message"] = (
            "我已拦截这个结果：当前任务被路由为“生成新视频”，不是发布旧视频或投稿到公共平台。"
            "我没有把旧 WeChat 视频当成结果，也不会发布到视频号、YouTube、Instagram 或公共队列。"
            "请继续使用 Xiaoyunque 生成/下载新 MP4；只有当前请求明确要求 LazyEdit 导入或公开发布时才进入后续阶段。"
        )
        guarded["confirmation"] = guarded.get("confirmation") or ""
        guarded["files"] = filter_generated_video_result_files(guarded.get("files") or [])
        guarded["contract_guard"] = "blocked_public_publish_claim_for_generate_video"
        return guarded
    if not lazyedit_allowed and ("lazyedit" in lowered or "lazy edit" in lowered):
        guarded = dict(result)
        guarded["message"] = (
            "我已拦截这个结果：当前请求只允许生成/下载并发回新视频，没有要求导入或处理到 LazyEdit。"
            "我会继续按阶段合约完成新 MP4 生成和回传；只有当前请求明确要求 LazyEdit/import/process 时才进入 LazyEdit。"
        )
        guarded["confirmation"] = guarded.get("confirmation") or ""
        guarded["files"] = filter_generated_video_result_files(guarded.get("files") or [])
        guarded["contract_guard"] = "blocked_unrequested_lazyedit_for_generate_video"
        return guarded
    files = filter_generated_video_result_files(result.get("files") or [])
    has_video = any(Path(str(path)).suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"} for path in files)
    sent_video_files = filter_generated_video_result_files(task.get("sent_file_paths") or [])
    has_sent_video = any(Path(str(path)).suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"} for path in sent_video_files)
    poststage_result = result.get("poststage") if isinstance(result.get("poststage"), dict) else {}
    if poststage_result and (has_sent_video or isinstance(task.get("generated_video_poststage"), dict)):
        guarded = dict(result)
        guarded["files"] = files
        return guarded
    status_terms = (
        "queued",
        "running",
        "generating",
        "submitted",
        "blocked",
        "waiting",
        "in progress",
        "排队",
        "生成中",
        "已提交",
        "等待",
        "阻塞",
        "卡住",
    )
    if has_video or any(term in lowered for term in status_terms):
        guarded = dict(result)
        guarded["files"] = files
        return guarded
    guarded = dict(result)
    guarded["message"] = (
        str(result.get("message") or "").strip()
        + "\n\n生成视频任务还没有验证到新的 MP4、提交状态或明确阻塞原因；我已按路由合约停止把它当成完成。"
        "下一步需要继续 Xiaoyunque 浏览器生成并返回新视频路径，或说明具体卡在哪个页面状态。"
    ).strip()
    guarded["files"] = files
    guarded["contract_guard"] = "missing_generated_video_completion_evidence"
    return guarded


def filter_generated_video_result_files(files: list[Any]) -> list[str]:
    safe: list[str] = []
    blocked_fragments = ("AutoPublish", "autopublish", "lazyedit", "Nutstore Files/AutoPublish")
    for raw in files:
        value = str(raw)
        if any(fragment in value for fragment in blocked_fragments):
            continue
        safe.append(value)
    return safe


def task_route_decision(task: dict[str, Any]) -> dict[str, Any]:
    route = task.get("route_decision")
    return route if isinstance(route, dict) else {}


def has_public_publish_intent(text: str) -> bool:
    lowered = str(text or "").lower()
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
    if any(marker in lowered for marker in negative_markers):
        return False
    explicit_markers = [
        "publish",
        "re-publish",
        "republish",
        "post",
        "shipinhao",
        "wechat channel",
        "视频号",
        "視頻號",
        "youtube",
        "instagram",
        "发布",
        "發布",
        "投稿",
    ]
    if any(marker in lowered for marker in explicit_markers):
        return True
    if re.search(r"\b(?:sph|y2b|ytb|ins)\b", lowered):
        return True
    if re.search(r"\b(?:upload|send)\s+to\s+(?:youtube|instagram|shipinhao|sph|y2b|ytb|ins)\b", lowered):
        return True
    if re.search(r"上传.*(?:视频号|youtube|instagram|平台)", lowered):
        return True
    return False


def build_lazyedit_correction_context(task: dict[str, Any], *, preflight: dict[str, Any] | None = None) -> str:
    autopub = (preflight or {}).get("autopublish_video") if isinstance(preflight, dict) else None
    resolved_video = (preflight or {}).get("resolved_video_artifact") if isinstance(preflight, dict) else None
    resolved_by_artifact = isinstance(autopub, dict) and str(autopub.get("status") or "") == "artifact-ledger-match"
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
        content = collapse_context_text(row.get("content"))
        marker = " "
        if resolved_by_artifact and is_obsolete_video_cache_refusal(content):
            marker = " OBSOLETE-CACHE-MISS "
        elif is_unverified_publish_claim(content):
            marker = " OBSOLETE-UNVERIFIED-PUBLISH "
        lines.append(
            f"-{marker}local_id={row.get('local_id')} sender={row.get('sender_display') or row.get('sender')}: "
            f"{content}"
        )
    if isinstance(autopub, dict):
        lines.extend(
            [
                "",
                "## Resolved Source Material",
                json.dumps(
                    {
                        "status": autopub.get("status"),
                        "target": autopub.get("target"),
                        "source_path": autopub.get("source_path"),
                        "matched_by": autopub.get("matched_by"),
                        "md5": autopub.get("md5"),
                        "bytes": autopub.get("bytes"),
                        "source_task": autopub.get("source_task"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
        source_task = autopub.get("source_task") if isinstance(autopub.get("source_task"), dict) else {}
        supporting_materials = source_task.get("supporting_materials") if isinstance(source_task, dict) else []
        if isinstance(supporting_materials, list) and supporting_materials:
            lines.extend(["", "## Source Generation / Prompt Material"])
            for item in supporting_materials[:8]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("path") or "supporting material")
                excerpt = collapse_context_text(item.get("excerpt"), max_len=1200)
                if excerpt:
                    lines.append(f"- {title}: {excerpt}")
    if isinstance(resolved_video, dict):
        lines.extend(
            [
                "",
                "## Resolved Recent Generated Video",
                json.dumps(
                    {
                        "status": resolved_video.get("status"),
                        "source_path": resolved_video.get("source_path"),
                        "matched_by": resolved_video.get("matched_by"),
                        "bytes": resolved_video.get("bytes"),
                        "source_task": resolved_video.get("source_task"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
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


def build_lazyedit_metadata_brief(task: dict[str, Any], *, preflight: dict[str, Any] | None = None) -> str:
    request = collapse_context_text(task.get("request")) or "WeChat video publish request"
    focused_request = collapse_context_text(task_focus_text(task), max_len=800)
    context_lines = []
    for row in task.get("context") or []:
        if not isinstance(row, dict):
            continue
        text = collapse_context_text(row.get("content"))
        if text:
            context_lines.append(text)
    source_task = {}
    autopub = (preflight or {}).get("autopublish_video") if isinstance(preflight, dict) else None
    resolved_video = (preflight or {}).get("resolved_video_artifact") if isinstance(preflight, dict) else None
    if isinstance(autopub, dict) and isinstance(autopub.get("source_task"), dict):
        source_task = autopub["source_task"]
    elif isinstance(resolved_video, dict) and isinstance(resolved_video.get("source_task"), dict):
        source_task = resolved_video["source_task"]
    if source_task:
        excerpt = collapse_context_text(source_task.get("request_excerpt"), max_len=360)
        if excerpt:
            context_lines.append(excerpt)
        result_excerpt = collapse_context_text(source_task.get("result_message_excerpt"), max_len=360)
        if result_excerpt:
            context_lines.append(result_excerpt)
        supporting_materials = source_task.get("supporting_materials")
        if isinstance(supporting_materials, list):
            for item in supporting_materials:
                if not isinstance(item, dict):
                    continue
                excerpt = collapse_context_text(item.get("excerpt"), max_len=360)
                if excerpt:
                    context_lines.append(excerpt)
    return (
        "# LazyEdit Metadata Brief\n\n"
        "Use this only for public-facing title, description, keywords, and platform notes.\n"
        "Do not expose private chat logs, internal agent workflow, or every subtitle-correction detail.\n\n"
        f"Current user request: {focused_request or request[:800]}\n\n"
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
    private_dest = nonpublish_video_preflight_dest(task)
    if private_dest:
        private_dest.mkdir(parents=True, exist_ok=True)
        command += ["--dest", str(private_dest), "--title", f"{safe_slug(str(task.get('id') or 'wechat-video'))}_source_video", "--replace"]
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
    if private_dest:
        payload["private_save_dest"] = str(private_dest)
    return payload


def nonpublish_video_preflight_dest(task: dict[str, Any]) -> Path | None:
    route = task_route_decision(task)
    text = task_focus_text(task)
    if bool(route.get("public_publish_allowed")) or has_public_publish_intent(text) or wants_lazyedit_import(text):
        return None
    return worker_artifact_dir(task) / "source_media"


def resolve_exact_video_artifact_preflight(task: dict[str, Any], original_preflight: dict[str, Any]) -> dict[str, Any]:
    """Resolve a quoted/generated WeChat video through same-chat task artifacts."""
    refs = extract_video_reference_metadata(task)
    if not refs["md5s"] and not refs["sizes"]:
        return {
            "ok": False,
            "status": "artifact-ledger-miss",
            "error": "no video md5 or length tokens in task context",
            "message_local_ids": extract_video_local_ids_from_task(task),
        }
    queue_path = task_queue_path(task)
    if not queue_path.is_file():
        return {
            "ok": False,
            "status": "artifact-ledger-miss",
            "error": f"queue not found: {queue_path}",
            "message_local_ids": extract_video_local_ids_from_task(task),
            "refs": refs,
        }
    try:
        tasks = read_tasks(queue_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "artifact-ledger-miss",
            "error": f"could not read queue: {type(exc).__name__}: {str(exc)[:300]}",
            "message_local_ids": extract_video_local_ids_from_task(task),
            "refs": refs,
        }
    matches = exact_video_artifact_matches(task, tasks, refs)
    if not matches:
        return {
            "ok": False,
            "status": "artifact-ledger-miss",
            "error": "no same-chat sent/generated video artifact matched the referenced md5/length",
            "message_local_ids": extract_video_local_ids_from_task(task),
            "refs": refs,
            "queue": str(queue_path),
        }
    match = matches[0]
    target = copy_exact_video_artifact_to_autopublish(match["path"], task)
    return {
        "ok": True,
        "status": "artifact-ledger-match",
        "target": str(target),
        "target_name": target.name,
        "source_path": str(match["path"]),
        "bytes": match["bytes"],
        "md5": match.get("md5"),
        "matched_by": match["matched_by"],
        "message_local_ids": extract_video_local_ids_from_task(task),
        "source_task": match.get("source_task") or {},
        "refs": refs,
        "queue": str(queue_path),
        "wechat_cache_preflight": original_preflight,
        "rule": "Exact same-chat artifact fallback: WeChat cache miss was recovered by md5/length match against prior generated/sent task output.",
    }


def resolve_recent_video_artifact_preflight(task: dict[str, Any]) -> dict[str, Any]:
    """Resolve the latest same-chat generated MP4 for follow-up send/save requests."""
    queue_path = task_queue_path(task)
    if not queue_path.is_file():
        return {"ok": False, "status": "recent-artifact-miss", "error": f"queue not found: {queue_path}"}
    try:
        tasks = read_tasks(queue_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": "recent-artifact-miss", "error": f"could not read queue: {type(exc).__name__}: {str(exc)[:300]}"}
    matches = recent_video_artifact_matches(task, tasks)
    if not matches:
        return {
            "ok": False,
            "status": "recent-artifact-miss",
            "error": "no recent same-chat generated/saved MP4 artifact found",
            "queue": str(queue_path),
        }
    match = matches[0]
    return {
        "ok": True,
        "status": "recent-artifact-match",
        "source_path": str(match["path"]),
        "source_name": match["path"].name,
        "bytes": match["bytes"],
        "md5": match.get("md5"),
        "matched_by": match["matched_by"],
        "source_task": match.get("source_task") or {},
        "queue": str(queue_path),
        "rule": "Recent same-chat generated-video artifact fallback for follow-up send/download/save requests.",
    }


def recent_video_artifact_matches(task: dict[str, Any], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chat = str(task.get("chat") or "")
    current_id = str(task.get("id") or "")
    max_age = float(os.environ.get("WECHAT_WORKER_RECENT_VIDEO_ARTIFACT_MAX_AGE_SECONDS", "21600"))
    created_at = parse_iso_datetime(str(task.get("created_at") or "")) or datetime.now()
    current_ts = created_at.timestamp()
    matches: list[dict[str, Any]] = []
    for source_task in tasks:
        if not isinstance(source_task, dict):
            continue
        if current_id and str(source_task.get("id") or "") == current_id:
            continue
        if chat and str(source_task.get("chat") or "") != chat:
            continue
        for path in collect_task_video_paths(source_task):
            path_text = str(path)
            if "Nutstore Files/AutoPublish" in path_text or "/AutoPublish/" in path_text:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            age = max(0.0, current_ts - stat.st_mtime)
            if max_age > 0 and age > max_age:
                continue
            matches.append(
                {
                    "path": path,
                    "bytes": stat.st_size,
                    "md5": None,
                    "mtime": stat.st_mtime,
                    "age_seconds": age,
                    "matched_by": ["same-chat-task-ledger", "recent-generated-video-artifact"],
                    "source_task": summarize_video_source_task(source_task, path),
                }
            )
    matches.sort(key=lambda item: float(item["mtime"]), reverse=True)
    return matches


def task_queue_path(task: dict[str, Any]) -> Path:
    raw = str(task.get("queue_path") or os.environ.get("WECHAT_WORKER_QUEUE") or "")
    return Path(raw).expanduser() if raw else DEFAULT_QUEUE


def extract_video_reference_metadata(task: dict[str, Any]) -> dict[str, Any]:
    source_local_ids = extract_video_local_ids_from_task(task)
    scoped_chunks: list[str] = []
    if source_local_ids:
        wanted = set(source_local_ids)
        for row in task.get("context") or []:
            if not isinstance(row, dict):
                continue
            local_id = int_or_none(row.get("local_id"))
            if local_id in wanted:
                scoped_chunks.append(json.dumps(row, ensure_ascii=False))
    raw = "\n".join(scoped_chunks) if scoped_chunks else json.dumps(task, ensure_ascii=False)
    text = html.unescape(raw).replace('\\"', '"')
    md5s: list[str] = []
    sizes: list[int] = []
    server_ids: list[str] = []
    for key in ("md5", "newmd5", "rawmd5", "originsourcemd5", "filemd5"):
        for value in re.findall(rf'\b{key}\s*=\s*["\']?([0-9A-Fa-f]{{32,64}})["\']?', text):
            add_once(md5s, value.lower())
    for value in re.findall(r"<md5>\s*([0-9A-Fa-f]{32,64})\s*</md5>", text):
        add_once(md5s, value.lower())
    for key in ("length", "rawlength", "cdnvideourl_size"):
        for value in re.findall(rf'\b{key}\s*=\s*["\']?([0-9]{{4,}})["\']?', text):
            try:
                add_once(sizes, int(value))
            except ValueError:
                continue
    for value in re.findall(r"\b(?:svrid|server_id|serverId|MsgSvrID)\s*[=:]\s*[\"']?([0-9]{8,})", text):
        add_once(server_ids, value)
    return {
        "md5s": md5s[:8],
        "sizes": sizes[:8],
        "server_ids": server_ids[:8],
        "local_ids": source_local_ids,
        "scope": "source_video_local_ids" if scoped_chunks else "task_context",
    }


def exact_video_artifact_matches(task: dict[str, Any], tasks: list[dict[str, Any]], refs: dict[str, Any]) -> list[dict[str, Any]]:
    chat = str(task.get("chat") or "")
    current_id = str(task.get("id") or "")
    md5s = {str(item).lower() for item in refs.get("md5s") or []}
    sizes = {int(item) for item in refs.get("sizes") or [] if int_or_none(item) is not None}
    matches: list[dict[str, Any]] = []
    for source_task in tasks:
        if not isinstance(source_task, dict):
            continue
        if current_id and str(source_task.get("id") or "") == current_id:
            continue
        if chat and str(source_task.get("chat") or "") != chat:
            continue
        for path in collect_task_video_paths(source_task):
            try:
                stat = path.stat()
            except OSError:
                continue
            if sizes and stat.st_size not in sizes and not md5s:
                continue
            path_md5 = ""
            matched_by: list[str] = []
            if md5s:
                path_md5 = file_md5(path)
                if path_md5 not in md5s:
                    continue
                matched_by.append(f"md5:{path_md5}")
            if sizes and stat.st_size in sizes:
                matched_by.append(f"bytes:{stat.st_size}")
            if not matched_by:
                continue
            matched_by.append("same-chat-task-ledger")
            matches.append(
                {
                    "path": path,
                    "bytes": stat.st_size,
                    "md5": path_md5 or None,
                    "mtime": stat.st_mtime,
                    "matched_by": matched_by,
                    "source_task": summarize_video_source_task(source_task, path),
                }
            )
    matches.sort(key=lambda item: (len(item["matched_by"]), float(item["mtime"])), reverse=True)
    return matches


def collect_task_video_paths(task: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []

    def add(raw: Any) -> None:
        if not raw:
            return
        path = Path(str(raw)).expanduser()
        if path.suffix.lower() not in VIDEO_SUFFIXES:
            return
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved.is_file() and resolved not in paths:
            paths.append(resolved)

    for key in ("sent_file_paths", "artifact_file_paths", "files"):
        value = task.get(key)
        if isinstance(value, list):
            for item in value:
                add(item)
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    for item in result.get("files") or []:
        add(item)
    preflight = task.get("preflight") if isinstance(task.get("preflight"), dict) else {}
    for section_name in ("generated_video_status", "autopublish_video"):
        section = preflight.get(section_name) if isinstance(preflight, dict) else {}
        if not isinstance(section, dict):
            continue
        add(section.get("target"))
        add(section.get("source_path"))
        for item in section.get("files") or []:
            add(item)
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    for item in monitor.get("files") or []:
        add(item)
    artifact_dir = task.get("artifact_dir")
    if artifact_dir:
        root = Path(str(artifact_dir)).expanduser()
        if root.is_dir():
            for path in sorted(root.glob("*.mp4"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
                add(path)
    return paths


def summarize_video_source_task(task: dict[str, Any], path: Path) -> dict[str, Any]:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    return {
        "id": task.get("id"),
        "chat": task.get("chat"),
        "created_at": task.get("created_at"),
        "completed_at": task.get("completed_at"),
        "source": task.get("source") or {},
        "request_excerpt": collapse_context_text(task_focus_text(task) or task.get("request"), max_len=1200),
        "result_message_excerpt": collapse_context_text(result.get("message"), max_len=800),
        "artifact_dir": task.get("artifact_dir"),
        "matched_file": str(path),
        "sent_file_paths": task.get("sent_file_paths") or [],
        "supporting_materials": collect_video_supporting_materials(task, path),
    }


def is_obsolete_video_cache_refusal(text: str) -> bool:
    lowered = str(text or "").lower()
    markers = [
        "官方客户端还没有把这一条完整 mp4 缓存到本地",
        "没有把这一条完整 mp4 缓存到本地",
        "no matching mirrored video found",
        "official client",
        "cache",
    ]
    return ("mp4" in lowered or "视频" in lowered or "video" in lowered) and any(marker in lowered for marker in markers)


def is_unverified_publish_claim(text: str) -> bool:
    lowered = str(text or "").lower()
    claim_markers = [
        "已自动完成 exact 视频保存",
        "lazyedit 处理/字幕修正并提交发布",
        "并提交发布",
        "submitted publish",
    ]
    proof_markers = [
        "stage=published_verified",
        "已确认发布完成",
        "remote=done",
        "remote_status=done",
        "public_url",
        "published_urls",
    ]
    return any(marker in lowered for marker in claim_markers) and not any(marker in lowered for marker in proof_markers)


def collect_video_supporting_materials(task: dict[str, Any], path: Path) -> list[dict[str, str]]:
    """Collect safe local prompt/story/context snippets that explain a generated video."""
    materials: list[dict[str, str]] = []
    seen: set[Path] = set()

    def add_file(candidate: Path, *, title: str | None = None) -> None:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            return
        if resolved in seen or not resolved.is_file():
            return
        if resolved.suffix.lower() not in {".md", ".txt", ".json"}:
            return
        try:
            if resolved.stat().st_size > int(os.environ.get("WECHAT_WORKER_SUPPORTING_MATERIAL_MAX_BYTES", "60000")):
                return
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        excerpt = collapse_context_text(text, max_len=1600)
        if not excerpt:
            return
        seen.add(resolved)
        materials.append(
            {
                "title": title or resolved.name,
                "path": str(resolved),
                "excerpt": excerpt,
            }
        )

    artifact_dir = task.get("artifact_dir")
    if artifact_dir:
        root = Path(str(artifact_dir)).expanduser()
        if root.is_dir():
            for pattern in ("*prompt*.md", "*story*.md", "*script*.md", "*context*.md", "*metadata*.md", "*contract*.md", "*.txt", "*.json"):
                for candidate in sorted(root.glob(pattern)):
                    add_file(candidate, title=f"source task {candidate.name}")
                    if len(materials) >= 6:
                        break
                if len(materials) >= 6:
                    break

    for candidate in related_lalachan_material_files(path):
        add_file(candidate, title=f"LALACHAN {candidate.name}")
        if len(materials) >= 10:
            break
    return materials[:10]


def related_lalachan_material_files(path: Path) -> list[Path]:
    lalachan = Path(os.environ.get("LALACHAN_ROOT", "/home/lachlan/ProjectsLFS/LALACHAN")).expanduser()
    if not lalachan.is_dir():
        return []
    stem_tokens = video_stem_tokens(path)
    if not stem_tokens:
        return []
    candidates: list[tuple[int, float, Path]] = []
    roots = [lalachan / "references", lalachan / "outputs"]
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in root.rglob("*"):
            if candidate.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            name_tokens = video_stem_tokens(candidate)
            score = len(stem_tokens & name_tokens)
            if "2026" in stem_tokens and "2026" in name_tokens:
                score += 1
            if score < 2:
                continue
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((score, mtime, candidate))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in candidates[:12]]


def video_stem_tokens(path: Path) -> set[str]:
    raw = path.stem.lower()
    tokens = {item for item in re.split(r"[^a-z0-9]+", raw) if len(item) >= 3}
    stop = {"mp4", "wechat", "completed", "final", "video", "seedance", "fast", "revised"}
    return {item for item in tokens if item not in stop}


def copy_exact_video_artifact_to_autopublish(source: Path, task: dict[str, Any]) -> Path:
    dest_dir = Path(os.environ.get("LABCANVAS_AUTOPUBLISH_DIR") or str(DEFAULT_AUTOPUBLISH_DIR)).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_slug(source.stem)
    if not stem.endswith("_completed"):
        stem = f"{stem}_COMPLETED"
    target = dest_dir / f"{stem}{source.suffix.lower()}"
    if target.exists():
        try:
            if target.stat().st_size == source.stat().st_size and file_md5(target) == file_md5(source):
                return target
        except OSError:
            pass
        suffix = safe_slug(str(task.get("id") or datetime.now().strftime("%Y%m%d%H%M%S")))
        target = dest_dir / f"{stem}_{suffix}{source.suffix.lower()}"
    shutil.copy2(source, target)
    return target


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_once(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def story_video_confirmation_gate_active(task: dict[str, Any]) -> bool:
    """Return true when story revision must be confirmed before video work."""
    if not is_interruptible_story_video_task(task):
        return False
    if bool(task.get("generation_blocked_until_story_confirmed")) or bool(task.get("story_confirmation_required")):
        return not latest_same_chat_confirms_video_generation(task)
    text = task_focus_text(task)
    lowered = text.lower()
    asks_story_first = any(
        marker in lowered
        for marker in (
            "first show the story",
            "show the story",
            "story is not",
            "update the story",
            "rewrite the story",
            "confirm the story",
            "story first",
            "先发故事",
            "先给故事",
            "先看故事",
            "故事不",
            "改故事",
            "更新故事",
            "重写故事",
            "确认故事",
            "先确认",
        )
    )
    stopped_generation = any(marker in lowered for marker in ("i stopped", "stopped it", "cancelled", "canceled", "我停", "我取消", "停止生成"))
    return bool((asks_story_first or stopped_generation or task_interruptions(task)) and not latest_same_chat_confirms_video_generation(task))


def latest_same_chat_confirms_video_generation(task: dict[str, Any]) -> bool:
    """Look only at the latest same-chat user update for clear generation approval."""
    latest = latest_task_update_text(task).lower()
    if not latest:
        return False
    negative = (
        "do not generate",
        "don't generate",
        "dont generate",
        "not generate",
        "wait",
        "先别",
        "不要生成",
        "不用生成",
        "别生成",
        "等一下",
        "先看",
        "先确认",
    )
    if any(marker in latest for marker in negative):
        return False
    positive = (
        "ok generate",
        "okay generate",
        "story ok",
        "looks good generate",
        "continue generation",
        "continue to generate",
        "go generate",
        "generate video now",
        "可以生成",
        "开始生成",
        "继续生成",
        "故事可以",
        "故事 ok",
        "没问题生成",
        "就这样生成",
        "生成视频",
    )
    return any(marker in latest for marker in positive)


def latest_task_update_text(task: dict[str, Any]) -> str:
    interruptions = task_interruptions(task)
    if interruptions:
        latest = interruptions[-1]
        return str(latest.get("request") or latest.get("request_excerpt") or "")
    source_local_id = int_or_none((task.get("source") or {}).get("local_id")) if isinstance(task.get("source"), dict) else None
    if source_local_id is not None:
        for row in reversed(task.get("context") or []):
            if not isinstance(row, dict):
                continue
            if int_or_none(row.get("local_id")) == source_local_id:
                return str(row.get("content") or "")
    return task_focus_text(task)


def story_confirmation_gate_result(task: dict[str, Any]) -> str:
    return json.dumps(
        {
            "message": (
                "我先停在故事确认阶段，不会直接提交或继续 Xiaoyunque 视频生成。"
                "我会用最新群消息重写故事并发到群里，请确认故事 OK 后再生成视频。"
            ),
            "files": [],
            "confirmation": "",
            "data": {
                "story_confirmation_gate": {
                    "status": "blocked_until_story_confirmed",
                    "latest_update": collapse_context_text(latest_task_update_text(task), max_len=800),
                    "rule": "story must be sent to group and confirmed before video generation",
                }
            },
        },
        ensure_ascii=False,
    )


def deterministic_manual_generated_video_handoff_result(task: dict[str, Any]) -> str | None:
    route = task_route_decision(task)
    manual = route.get("manual_handoff") if isinstance(route.get("manual_handoff"), dict) else None
    if not manual and isinstance(task.get("manual_generated_video_handoff"), dict):
        manual = task["manual_generated_video_handoff"]
    if not manual and bool(route.get("manual_handoff_update")):
        manual = manual_generated_video_handoff_payload(task_focus_text(task))
    if not manual:
        return None
    task["manual_generated_video_handoff"] = manual
    task["status"] = "done"
    return json.dumps(manual_generated_video_handoff_result_payload(manual), ensure_ascii=False)


def deterministic_preflight_result(task: dict[str, Any]) -> str | None:
    manual_handoff = deterministic_manual_generated_video_handoff_result(task)
    if manual_handoff is not None:
        return manual_handoff
    existing_publish = deterministic_existing_video_publish_poststage_result(task)
    if existing_publish is not None:
        return existing_publish
    poststage = deterministic_generated_video_poststage_result(task)
    if poststage is not None:
        return poststage
    existing_generated_video = deterministic_existing_generated_video_file_result(task)
    if existing_generated_video is not None:
        return existing_generated_video
    generated_continue = deterministic_generated_video_continue_result(task)
    if generated_continue is not None:
        return generated_continue
    generated_video = deterministic_generated_video_monitor_result(task)
    if generated_video is not None:
        return generated_video
    generated_submit = deterministic_generated_video_submit_result(task)
    if generated_submit is not None:
        return generated_submit
    file_intake = deterministic_file_intake_result(task)
    if file_intake is not None:
        return file_intake
    preflight_status = ((task.get("preflight") or {}).get("generated_video_status") if isinstance(task.get("preflight"), dict) else None)
    if isinstance(preflight_status, dict) and preflight_status.get("status") in {"submitted", "running", "queued", "generating", "waiting"}:
        return json.dumps(
            {
                "message": (
                    "Xiaoyunque 视频任务仍在生成/排队，我已记录状态并进入低频自动监控；"
                    "不会重复提交，也不会发布。"
                ),
                "files": preflight_status.get("files") or [],
                "confirmation": "",
                "generation": preflight_status,
            },
            ensure_ascii=False,
        )
    resolved_video = ((task.get("preflight") or {}).get("resolved_video_artifact") if isinstance(task.get("preflight"), dict) else None)
    if isinstance(resolved_video, dict) and bool(resolved_video.get("ok")):
        return resolved_video_artifact_result(task, resolved_video)
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
    artifact_resolution = autopub.get("artifact_resolution") if isinstance(autopub.get("artifact_resolution"), dict) else {}
    artifact_state = ""
    if artifact_resolution:
        artifact_state = (
            "我也检查了同一微信群的任务 artifact ledger，"
            f"没有找到匹配该视频 md5/length 的已生成或已发送 MP4（{artifact_resolution.get('error') or 'no match'}）。"
        )
    message = (
        "我没有发布这个视频。"
        f"{source_state}"
        f"{artifact_state}"
        "为了避免误发布，我已按 exact-source fail-closed 规则停止，没有使用附近的旧视频或上一次视频。"
        "请重新发送原视频，或在 WeChat 里点开这条视频让客户端缓存完整 MP4；如果这是我生成过的视频，请确保对应任务 artifact 仍在本机输出目录。"
    )
    return json.dumps({"message": message, "files": [], "confirmation": ""}, ensure_ascii=False)


def deterministic_file_intake_result(task: dict[str, Any]) -> str | None:
    if not is_file_intake_task(task):
        return None
    preflight = task.get("preflight") if isinstance(task.get("preflight"), dict) else {}
    intake = preflight.get("file_intake") if isinstance(preflight.get("file_intake"), dict) else {}
    if not intake:
        return None
    copied = intake.get("copied") if isinstance(intake.get("copied"), list) else []
    if copied:
        file_count = len(copied)
        first = copied[0] if isinstance(copied[0], dict) else {}
        filename = str(first.get("filename") or "file")
        size = int(first.get("size_bytes") or 0)
        suffix = str(first.get("suffix") or "file")
        checksum = str(first.get("sha256") or "")
        saved = str(first.get("saved_path") or "")
        more = f"；另有 {file_count - 1} 个文件也已入库" if file_count > 1 else ""
        message = (
            f"已做文件预检并保存：{filename}（{suffix or 'unknown'}, {size} bytes）{more}。\n"
            f"SHA-256: {checksum[:16]}…\n"
            "我没有深度阅读或总结，因为这次只是裸文件上传；你接下来可以直接说“总结这份 PDF / 提取目录 / 翻译重点 / 生成读书笔记”。"
        )
        status = "saved"
    else:
        message = (
            "我看到一条文件上传消息，但本地还没有拿到可复制的原文件。"
            "我已记录这次预检；如果需要处理，请在 WeChat 里点开文件让客户端缓存，或重新发送一次原文件。"
        )
        status = "missing"
        saved = ""
    return json.dumps(
        {
            "message": message,
            "files": [],
            "confirmation": "",
            "data": {
                "file_intake": intake,
                "status": status,
                "saved_path": saved,
                "require_file_delivery": False,
            },
        },
        ensure_ascii=False,
    )


def resolved_video_artifact_result(task: dict[str, Any], resolved: dict[str, Any]) -> str | None:
    source_raw = str(resolved.get("source_path") or "")
    if not source_raw:
        return None
    source = Path(source_raw).expanduser()
    if not source.is_file():
        return json.dumps(
            {
                "message": f"找到同群视频 artifact 记录，但源文件已经不存在：{source_raw}。请重新发送或重新生成视频。",
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    text = task_focus_text(task)
    data: dict[str, Any] = {
        "require_file_delivery": True,
        "resolved_video_artifact": resolved,
    }
    lazyedit_target = ""
    if wants_lazyedit_import(text):
        target = copy_exact_video_artifact_to_autopublish(source.resolve(), task)
        lazyedit_target = str(target)
        data["lazyedit_import"] = {
            "status": "submitted_to_autopublish_intake",
            "target": str(target),
            "target_name": target.name,
            "public_publish": False,
            "rule": "LazyEdit import/process only; no public platform publish without current-message publish permission.",
        }
    if lazyedit_target:
        message = f"已找到同群已生成视频，先回传 MP4，并已提交到 LazyEdit intake（不公开发布）：{Path(lazyedit_target).name}"
    else:
        message = "已找到同群已生成视频，正在回传 MP4。"
    return json.dumps(
        {
            "message": message,
            "files": [str(source.resolve())],
            "confirmation": "",
            "data": data,
        },
        ensure_ascii=False,
    )


def deterministic_existing_generated_video_file_result(task: dict[str, Any]) -> str | None:
    """Return an already downloaded generated MP4 before invoking any agent/model.

    This is the core paid-generation idempotence path: if a Xiaoyunque monitor
    has already produced an MP4 for the logical request, the worker should send
    that artifact back and optionally queue the allowed poststage. It must not
    ask a model to re-plan, continue, or submit another paid generation.
    """
    if not is_generate_video_task(task) or str(task.get("status") or "") != CLAIMED_STATUS:
        return None
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    if not monitor:
        return None
    artifact_dir = Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))
    output_dir = Path(str(monitor.get("output_dir") or artifact_dir))
    files = generated_video_existing_files(output_dir, monitor)
    if not files:
        return None
    raw = generated_video_completion_result(files[0], task, monitor, abnormal=False)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    message = str(payload.get("message") or "")
    payload["message"] = (
        f"{message}\n"
        "已按现有 artifact 完成：不会重新提交、继续确认、或创建新的 Xiaoyunque/Seedance 付费任务。"
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    data["require_file_delivery"] = bool(payload.get("require_file_delivery", True))
    data["existing_generated_video_artifact"] = {
        "status": "found",
        "video_path": str(files[0].resolve()),
        "output_dir": str(output_dir),
        "monitor_only_no_resubmit": generated_video_monitor_only(task),
    }
    payload["data"] = data
    return json.dumps(payload, ensure_ascii=False)


def deterministic_generated_video_submit_result(task: dict[str, Any]) -> str | None:
    if not is_generate_video_task(task) or str(task.get("status") or "") != CLAIMED_STATUS:
        return None
    if generated_video_monitor_only(task):
        return None
    if story_video_confirmation_gate_active(task):
        task["story_confirmation_gate"] = {
            "status": "blocked_deterministic_submit",
            "at": datetime.now().isoformat(timespec="seconds"),
            "latest_update": collapse_context_text(latest_task_update_text(task), max_len=800),
        }
        return None
    if task.get("generated_video_monitor") or task.get("generation_wait_count"):
        return None
    script = generated_video_submit_script()
    if not script:
        return None
    artifact_dir = Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cdp_url = os.environ.get("WECHAT_WORKER_XYQ_CDP_URL") or os.environ.get("XYQ_CDP_URL") or "http://127.0.0.1:9222"
    request_text = task_focus_text(task)
    duration = requested_generated_video_duration_seconds(task)
    command = [
        sys.executable,
        str(script),
        "--cdp-url",
        cdp_url,
        "--artifact-dir",
        str(artifact_dir),
        "--task-id",
        safe_slug(str(task.get("id") or "generated-video")),
        "--request-text",
        request_text,
        "--min-attachments",
        "8",
        "--min-prompt-chars",
        os.environ.get("WECHAT_WORKER_XYQ_MIN_PROMPT_CHARS", "300"),
        "--submit",
    ]
    if duration:
        command.extend(["--expect-duration", str(duration)])
    timeout = int(os.environ.get("WECHAT_WORKER_XYQ_SUBMIT_TIMEOUT_SECONDS", "120"))
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        task["generated_video_submit_probe"] = {
            "ok": False,
            "status": "timeout",
            "stdout": collapse_context_text(stdout, max_len=800),
            "stderr": collapse_context_text(stderr, max_len=800),
        }
        return None
    payload = parse_last_json_object((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if not payload:
        task["generated_video_submit_probe"] = {
            "ok": False,
            "status": "parse_failed",
            "returncode": proc.returncode,
            "stdout": collapse_context_text(proc.stdout, max_len=1000),
            "stderr": collapse_context_text(proc.stderr, max_len=1000),
        }
        return None
    task["generated_video_submit_probe"] = payload
    persist_task_progress(task)
    status = str(payload.get("status") or "")
    if not bool(payload.get("ok")) or status == "not_ready":
        return None
    screenshots = [str(path) for path in payload.get("screenshots") or [] if path]
    thread_url = str(payload.get("thread_url") or "")
    page_id = str(payload.get("page_id") or "")
    message = (
        "Xiaoyunque 生成任务已提交/恢复，已进入自动监控；"
        "我会等待 MP4，下载后先发回本群，再按当前请求继续 LazyEdit 和发布。"
    )
    monitor = {
        "status": status or "submitted",
        "thread_url": thread_url,
        "page_id": page_id,
        "cdp_url": cdp_url,
        "output_dir": str(artifact_dir),
        "filename": f"{safe_slug(str(task.get('id') or 'generated-video'))}.mp4",
        "screenshots": screenshots,
        "stage_permissions": generated_video_stage_permissions(task),
    }
    return json.dumps(
        {
            "message": message,
            "files": screenshots,
            "confirmation": "",
            "data": {
                "generated_video": monitor,
                "generation": monitor,
            },
        },
        ensure_ascii=False,
    )


def deterministic_generated_video_continue_result(task: dict[str, Any]) -> str | None:
    if not is_generate_video_task(task) or str(task.get("status") or "") != CLAIMED_STATUS:
        return None
    if generated_video_monitor_only(task):
        return None
    if story_video_confirmation_gate_active(task):
        task["story_confirmation_gate"] = {
            "status": "blocked_deterministic_continue",
            "at": datetime.now().isoformat(timespec="seconds"),
            "latest_update": collapse_context_text(latest_task_update_text(task), max_len=800),
        }
        return None
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    thread_url = str(monitor.get("thread_url") or "").strip()
    if not thread_url:
        return None
    artifact_dir = Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))
    output_dir = Path(str(monitor.get("output_dir") or artifact_dir))
    probe = latest_generated_video_probe(output_dir)
    if not generated_video_probe_needs_continuation(probe):
        return None
    if generated_video_recently_continued(task):
        # The latest local probe may still be the pre-continuation snapshot.
        # Do not return a nonterminal status here; let the monitor run a fresh
        # CDP probe against the same thread so it can observe generating/done.
        return None
    script = generated_video_continue_script()
    if not script:
        return json.dumps(
            {
                "message": "Xiaoyunque 当前线程正在等待确认，但本机找不到 continuation helper；任务保留在队列等待 worker 恢复。",
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    cdp_url = str(monitor.get("cdp_url") or os.environ.get("WECHAT_WORKER_XYQ_CDP_URL") or os.environ.get("XYQ_CDP_URL") or "http://127.0.0.1:9222")
    page_id = str(monitor.get("page_id") or page_id_for_thread_url(cdp_url, thread_url) or "")
    prompt = generated_video_continuation_prompt(task)
    command = [
        sys.executable,
        str(script),
        "--cdp-url",
        cdp_url,
        "--thread-url",
        thread_url,
        "--artifact-dir",
        str(artifact_dir),
        "--task-id",
        safe_slug(str(task.get("id") or "generated-video")),
        "--message",
        prompt,
        "--submit",
    ]
    if page_id:
        command.extend(["--page-id", page_id])
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=90)
    except (OSError, subprocess.SubprocessError) as exc:
        return json.dumps(
            {
                "message": f"Xiaoyunque 继续生成确认提交失败：{type(exc).__name__}: {str(exc)[:240]}；任务保留在队列稍后重试。",
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    payload = parse_last_json_object((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if not isinstance(payload, dict):
        payload = {}
    if proc.returncode == 0 and payload.get("status") in {"continued", "ready"}:
        continuation = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "thread_url": str(payload.get("thread_url") or thread_url),
            "page_id": str(payload.get("page_id") or page_id),
            "message": prompt,
            "status": str(payload.get("status") or ""),
        }
        task.setdefault("generated_video_continuations", []).append(continuation)
        updated_monitor = dict(monitor)
        updated_monitor.update(
            {
                "cdp_url": cdp_url,
                "page_id": continuation["page_id"],
                "thread_url": continuation["thread_url"],
                "last_status": "Xiaoyunque continuation submitted; waiting for final MP4.",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return json.dumps(
            {
                "message": "已向 Xiaoyunque 当前线程提交继续生成确认；会继续监控同一个 thread_id，下载 MP4 后先发回本群，再按当前请求处理后续阶段。",
                "files": [],
                "confirmation": "",
                "data": {
                    "generated_video": updated_monitor,
                    "generation": updated_monitor,
                    "generated_video_continuation": continuation,
                },
            },
            ensure_ascii=False,
        )
    combined = collapse_context_text((proc.stdout or "") + "\n" + (proc.stderr or ""), max_len=900)
    return json.dumps(
        {
            "message": f"Xiaoyunque 当前线程需要继续确认，但自动提交没有成功；任务保留在队列稍后重试。 last_log={combined}",
            "files": [],
            "confirmation": "",
            "data": {"generated_video": monitor, "generation": monitor},
        },
        ensure_ascii=False,
    )


def generated_video_probe_needs_continuation(probe: dict[str, Any] | None) -> bool:
    if not isinstance(probe, dict):
        return False
    tail = str(probe.get("tail") or "")
    status = "\n".join(str(item) for item in probe.get("status") or [])
    text = f"{tail}\n{status}"
    has_confirm = "请确认" in text or "符合预期" in text
    has_continue = "继续帮您生成视频" in text or ("继续" in text and "生成视频" in text)
    has_blocker = any(marker in text for marker in ("生成失败", "任务失败", "内部错误", "审核", "合规", "积分不足", "余额不足"))
    has_final_video = generated_video_probe_has_completed_artifact(probe) or ("最终视频" in text and "下载" in text)
    return bool(has_confirm and has_continue and not has_blocker and not has_final_video)


def generated_video_recently_continued(task: dict[str, Any]) -> bool:
    continuations = task.get("generated_video_continuations")
    if not isinstance(continuations, list) or not continuations:
        return False
    latest = continuations[-1] if isinstance(continuations[-1], dict) else {}
    max_age = float(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_CONTINUE_COOLDOWN_SECONDS", "900"))
    try:
        at = datetime.fromisoformat(str(latest.get("at") or ""))
    except ValueError:
        return True
    return (datetime.now() - at).total_seconds() < max_age


def generated_video_continuation_prompt(task: dict[str, Any]) -> str:
    requested = requested_generated_video_duration_seconds(task)
    tolerance = generated_video_duration_tolerance_seconds(task)
    duration_note = f"{requested}秒，允许±{tolerance}秒" if requested else "当前故事板时长"
    latest_context = generated_video_latest_instruction_summary(task)
    latest_instruction = ""
    if latest_context:
        latest_instruction = (
            "\n\n微信群最新确认/补充要求如下，必须优先遵守：\n"
            f"{latest_context}\n"
            "如果这些要求与旧故事板、旧提示词或页面当前故事冲突，以最新群消息为准；"
            "不要继续旧故事，不要保留用户已经否定的剧情。"
        )
    return (
        "确认，当前故事板、参考角色/场景/道具素材、4:3比例、无字幕设置均符合预期；"
        f"总时长按 {duration_note} 继续即可。"
        "请优先使用 Seedance 2.0 Mini 体验版 / vipnew / 单秒低至4积分 的便宜模型；"
        "如果 Fast Vision 积分不足，不要因为模型选择停止，改用当前可用的最低成本 Mini/Fast 方案。"
        "请不要再等待人工确认，直接继续生成最终视频 MP4。"
        "不要字幕、不要画面文字、不要说明文字；保持当前故事板和参考素材一致。"
        f"{latest_instruction}"
    )


def generated_video_latest_instruction_summary(task: dict[str, Any]) -> str:
    lines: list[str] = []
    for item in task_interruptions(task)[-6:]:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        sender = source.get("sender_display") or source.get("sender") or "user"
        local_id = source.get("local_id") or ""
        text = collapse_context_text(item.get("request") or item.get("request_excerpt"), max_len=1000)
        if text:
            lines.append(f"- local_id={local_id} {sender}: {text}")
    latest = latest_task_update_text(task)
    if latest and not any(latest in line for line in lines):
        lines.append(f"- latest: {collapse_context_text(latest, max_len=1000)}")
    return "\n".join(lines)


def requested_generated_video_duration_seconds(task: dict[str, Any]) -> int | None:
    match = re.search(r"(\d+)\s*(?:s|sec|secs|second|seconds|秒)", task_focus_text(task), flags=re.I)
    if not match:
        return None
    return int(match.group(1))


def generated_video_duration_tolerance_seconds(task: dict[str, Any]) -> int:
    if re.search(r"\bexact(?:ly)?\b|必须\s*正好|严格\s*(?:时长|长度)|精确", task_focus_text(task), flags=re.I):
        return int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_EXACT_DURATION_TOLERANCE_SECONDS", "1"))
    return int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_DURATION_TOLERANCE_SECONDS", "5"))


def generated_video_verification_policy(task: dict[str, Any]) -> dict[str, Any]:
    requested = requested_generated_video_duration_seconds(task)
    tolerance = generated_video_duration_tolerance_seconds(task)
    policy: dict[str, Any] = {
        "ffprobe_required": True,
        "duration_tolerance_seconds": tolerance,
        "duration_rule": "Accept requested duration within tolerance unless the current request explicitly requires exact duration.",
    }
    if requested:
        policy.update(
            {
                "requested_duration_seconds": requested,
                "accepted_min_duration_seconds": max(0, requested - tolerance),
                "accepted_max_duration_seconds": requested + tolerance,
            }
        )
    return policy


def deterministic_generated_video_poststage_result(task: dict[str, Any]) -> str | None:
    if not is_generate_video_task(task) or str(task.get("status") or "") != CLAIMED_STATUS:
        return None
    poststage = task.get("generated_video_poststage") if isinstance(task.get("generated_video_poststage"), dict) else {}
    if not poststage:
        return None
    video_path = Path(str(poststage.get("video_path") or "")).expanduser()
    if not video_path.is_file():
        return json.dumps(
            {
                "message": f"生成视频后续阶段暂不能继续：找不到已回传的视频文件 {video_path}。",
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    monitor = poststage.get("monitor") if isinstance(poststage.get("monitor"), dict) else {}
    publish = bool(poststage.get("publish"))
    outcome = run_generated_video_lazyedit_command(video_path.resolve(), task, monitor, publish=publish)
    status = outcome.get("status") or ("done" if outcome.get("ok") else "failed")
    if status in {"timeout", "running", "queued"}:
        retry_seconds = int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_POSTSTAGE_RETRY_SECONDS", "600"))
        if publish:
            stage = "LazyEdit/public publish"
        else:
            stage = "LazyEdit import/process"
        return json.dumps(
            {
                "message": (
                    f"生成视频的 {stage} 后续阶段仍在运行或超时未确认：status={status}。"
                    "我会保留任务并稍后继续检查，不会重复回传 MP4，也不会当作完成。"
                ),
                "files": [],
                "confirmation": "",
                "generated_video_poststage_retry": {
                    "status": status,
                    "retry_seconds": retry_seconds,
                    "poststage": poststage,
                    "outcome": outcome,
                },
            },
            ensure_ascii=False,
        )
    if publish:
        platforms = ",".join(detect_publish_platforms(task, current_only=True))
        message = f"已继续完成生成视频的 LazyEdit/public publish 后续阶段：status={status}; platforms={platforms}."
    else:
        message = f"已继续完成生成视频的 LazyEdit import/process 后续阶段：status={status}; no public publish."
    return json.dumps(
        {
            "message": message,
            "files": [],
            "confirmation": "",
            "poststage": {"status": status, "publish": publish, "outcome": outcome},
        },
        ensure_ascii=False,
    )


def deterministic_generated_video_monitor_result(task: dict[str, Any]) -> str | None:
    if not is_generate_video_task(task) or str(task.get("status") or "") != CLAIMED_STATUS:
        return None
    if story_video_confirmation_gate_active(task):
        task["story_confirmation_gate"] = {
            "status": "blocked_deterministic_monitor",
            "at": datetime.now().isoformat(timespec="seconds"),
            "latest_update": collapse_context_text(latest_task_update_text(task), max_len=800),
        }
        return None
    previous_statuses = {
        str(item.get("status") or "")
        for item in task.get("claim_history") or []
        if isinstance(item, dict)
    }
    if GENERATED_VIDEO_WAITING_STATUS not in previous_statuses and not task.get("generation_wait_count"):
        return None
    monitor = task.get("generated_video_monitor") if isinstance(task.get("generated_video_monitor"), dict) else {}
    thread_url = str(monitor.get("thread_url") or "").strip()
    page_id = str(monitor.get("page_id") or "").strip()
    if not thread_url or not page_id:
        return None
    return run_generated_video_monitor(task, monitor)


def run_generated_video_monitor(task: dict[str, Any], monitor: dict[str, Any]) -> str:
    script = generated_video_watcher_script()
    if not script:
        return json.dumps(
            {
                "message": "Xiaoyunque 生成任务还在等待，但本机找不到 watcher 脚本；我会让 worker 重新接手恢复监控。",
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    artifact_dir = Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))
    output_dir = Path(str(monitor.get("output_dir") or artifact_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = str(monitor.get("filename") or f"{safe_slug(str(task.get('id') or 'generated-video'))}.mp4")
    cdp_url = str(monitor.get("cdp_url") or os.environ.get("XYQ_CDP_URL") or "http://127.0.0.1:9222")
    status = inspect_generated_video_status(task) or {}
    poll_seconds = float(
        os.environ.get(
            "WECHAT_WORKER_GENERATED_VIDEO_WATCH_INTERVAL_SECONDS",
            str(generated_video_status_backoff_seconds(str(status.get("status_text") or ""), task_focus_text(task))),
        )
    )
    max_interval = float(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_WATCH_MAX_INTERVAL_SECONDS", "30"))
    if max_interval > 0:
        poll_seconds = min(poll_seconds, max_interval)
    max_polls = max(
        1,
        int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_WATCH_POLLS_PER_CYCLE", DEFAULT_GENERATED_VIDEO_WATCH_POLLS_PER_CYCLE)),
    )
    probe_grace = float(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_WATCH_GRACE_SECONDS", "30"))
    timeout = int(max(60.0, poll_seconds * max_polls + probe_grace))
    copy_to = Path(os.environ.get("LALACHAN_VIDEO_DIR", "/home/lachlan/ProjectsLFS/LALACHAN/Videos"))
    command = [
        sys.executable,
        str(script),
        "--cdp-url",
        cdp_url,
        "--page-id",
        str(monitor["page_id"]),
        "--thread-url",
        str(monitor["thread_url"]),
        "--output-dir",
        str(output_dir),
        "--filename",
        filename,
        "--copy-to",
        str(copy_to),
        "--interval",
        str(int(poll_seconds)),
        "--max-polls",
        str(max_polls),
        "--reload-every",
        os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_RELOAD_SECONDS", "300"),
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=script.parent.parent if script.parent.name == "xyq_chrome" else script.parent,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
        message = (
            "Xiaoyunque 视频状态探测周期结束，任务仍在生成/排队；我会按页面状态继续低频监控，不会重新提交，也不会发布。"
            f" last_log={collapse_context_text(stdout + ' ' + stderr, max_len=500)}"
        )
        return json.dumps({"message": message, "files": [], "confirmation": ""}, ensure_ascii=False)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = collapse_context_text(stdout + "\n" + stderr, max_len=900)
    latest_probe = latest_generated_video_probe(output_dir)
    if proc.returncode == 43 and generated_video_credit_block_seen(combined) and not generated_video_probe_has_completed_artifact(latest_probe):
        message = (
            "Xiaoyunque 已返回积分不足/余额不足，当前线程无法继续生成最终 MP4。"
            "我已停止重复轮询和重复提交；需要充值、切换到更低成本/更短视频方案，或明确授权其它生成方式后再继续。"
        )
        return json.dumps(
            {
                "message": message,
                "files": [],
                "confirmation": "Xiaoyunque 生成被积分不足挡住。请充值/补充积分，或回复允许我改用更短/更低成本的替代方案。",
                "data": {
                    "generated_video_blocker": {
                        "kind": "insufficient_credits",
                        "monitor": monitor,
                        "last_log": combined,
                    }
                },
            },
            ensure_ascii=False,
        )
    output_path = generated_video_output_path(stdout, output_dir / filename)
    if proc.returncode == 0 and output_path and output_path.is_file():
        return generated_video_completion_result(output_path, task, monitor, abnormal=False)
    if output_path and output_path.is_file():
        return generated_video_completion_result(output_path, task, monitor, abnormal=True)
    if generated_video_probe_has_completed_artifact(latest_probe):
        return generated_video_download_ready_result(task, monitor, latest_probe, combined)
    if proc.returncode == 0:
        status = "Xiaoyunque 监控结束但没有找到 MP4；我会继续低频监控，避免重复提交。"
    else:
        status = "Xiaoyunque 监控暂未拿到 MP4，可能仍在生成、页面未暴露下载、或需要人工处理。"
    return json.dumps({"message": f"{status} last_log={combined}", "files": [], "confirmation": ""}, ensure_ascii=False)


def generated_video_credit_block_seen(text: str) -> bool:
    return any(marker in str(text or "") for marker in ("积分不足", "余额不足", "insufficient_credit", "insufficient credits"))


def generated_video_download_ready_result(
    task: dict[str, Any],
    monitor: dict[str, Any],
    probe: dict[str, Any] | None,
    last_log: str,
) -> str:
    retry_seconds = int(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_DOWNLOAD_READY_POLL_SECONDS", "30"))
    status_text = collapse_context_text(generated_video_probe_status_text(probe), max_len=500)
    return json.dumps(
        {
            "message": (
                "Xiaoyunque 已在当前 thread_id 显示 final_video.mp4 / 最终视频完成；"
                "我会继续同一线程下载并回传 MP4，不会重新生成、不会再发送继续确认，也不会把后续积分不足当作本次视频失败。"
            ),
            "files": [],
            "confirmation": "",
            "data": {
                "generated_video_download_ready": {
                    "status": "download_ready",
                    "retry_seconds": retry_seconds,
                    "monitor": monitor,
                    "probe_file": str((probe or {}).get("_path") or ""),
                    "status_text": status_text,
                    "last_log": last_log,
                },
                "generated_video": monitor,
                "generation": monitor,
            },
        },
        ensure_ascii=False,
    )


def generated_video_completion_result(output_path: Path, task: dict[str, Any], monitor: dict[str, Any], *, abnormal: bool) -> str:
    resolved = output_path.resolve()
    stages = generated_video_stage_permissions(task)
    verification = generated_video_output_verification(resolved, task)
    message = (
        f"监控命令返回异常，但已经找到生成视频文件：{resolved}"
        if abnormal
        else f"Xiaoyunque 视频已生成并下载完成：{resolved}"
    )
    data: dict[str, Any] = {
        "require_file_delivery": True,
        "generated_video": {
            "status": "downloaded",
            "video_path": str(resolved),
            "verification": verification,
            "stage_permissions": stages,
        },
    }
    if stages.get("lazyedit_import"):
        publish = bool(stages.get("public_publish"))
        data["generated_video_poststage"] = {
            "kind": "lazyedit_public_publish" if publish else "lazyedit_import",
            "video_path": str(resolved),
            "publish": publish,
            "platforms": stages.get("publish_platforms") or [],
            "monitor": dict(monitor),
        }
        if publish:
            message += "\n已排队：先把 MP4 回传到本群；送达后 worker 会自动继续 LazyEdit 并发布到请求的平台。"
        else:
            message += "\n已排队：先把 MP4 回传到本群；送达后 worker 会自动继续 LazyEdit import/process（不公开发布）。"
    return json.dumps({"message": message, "files": [str(resolved)], "confirmation": "", **data}, ensure_ascii=False)


def generated_video_output_verification(path: Path, task: dict[str, Any]) -> dict[str, Any]:
    policy = generated_video_verification_policy(task)
    verification: dict[str, Any] = {"policy": policy, "path": str(path)}
    if not shutil.which("ffprobe"):
        verification.update({"ok": True, "warning": "ffprobe unavailable; duration could not be checked"})
        return verification
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=width,height,codec_name",
        "-of",
        "json",
        str(path),
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        verification.update({"ok": True, "warning": f"ffprobe failed: {type(exc).__name__}: {str(exc)[:200]}"})
        return verification
    verification["ffprobe_returncode"] = proc.returncode
    if proc.returncode != 0:
        verification.update({"ok": True, "warning": collapse_context_text(proc.stderr or proc.stdout, max_len=300)})
        return verification
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        verification.update({"ok": True, "warning": "ffprobe returned non-json output"})
        return verification
    duration_raw = ((payload.get("format") or {}) if isinstance(payload, dict) else {}).get("duration")
    try:
        duration = float(duration_raw)
    except (TypeError, ValueError):
        duration = None
    verification["ffprobe"] = payload
    verification["duration_seconds"] = duration
    requested = policy.get("requested_duration_seconds")
    if duration is not None and requested:
        min_duration = float(policy.get("accepted_min_duration_seconds") or 0)
        max_duration = float(policy.get("accepted_max_duration_seconds") or requested)
        verification["duration_within_tolerance"] = min_duration <= duration <= max_duration
        verification["duration_delta_seconds"] = round(duration - float(requested), 3)
    verification["ok"] = True
    return verification


def generated_video_watcher_script() -> Path | None:
    candidates = [
        ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "xyq_watch_thread_dom_download.py",
        Path("/home/lachlan/ProjectsLFS/LALACHAN/scripts/xyq_chrome/watch_thread_dom_download.py"),
        Path("/home/lachlan/.codex/skills/lalachan-xyq-browser-video/scripts/xyq_chrome/watch_thread_dom_download.py"),
    ]
    return next((path for path in candidates if path.is_file()), None)


def generated_video_submit_script() -> Path | None:
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "xyq_submit_current.py"
    return path if path.is_file() else None


def generated_video_continue_script() -> Path | None:
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "xyq_continue_thread.py"
    return path if path.is_file() else None


def generated_video_output_path(stdout: str, default_path: Path) -> Path | None:
    for match in re.finditer(r"DONE\s+output=([^\r\n]+)", stdout):
        candidate = Path(clean_path_token(match.group(1)))
        if candidate.is_file():
            return candidate.resolve()
    if default_path.is_file():
        return default_path.resolve()
    return None


def maybe_run_generated_video_lazyedit_stage(video_path: Path, task: dict[str, Any], monitor: dict[str, Any]) -> str:
    stages = generated_video_stage_permissions(task)
    wants_lazyedit = bool(stages.get("lazyedit_import"))
    publish_allowed = bool(stages.get("public_publish"))
    if not wants_lazyedit:
        return ""
    outcome = run_generated_video_lazyedit_command(video_path, task, monitor, publish=publish_allowed)
    status = outcome.get("status") or ("done" if outcome.get("ok") else "failed")
    if publish_allowed:
        return f"LazyEdit/public publish stage requested: status={status}."
    return f"LazyEdit import/process stage requested: status={status}; no public publish was requested."


def wants_lazyedit_import(text: str) -> bool:
    lowered = str(text or "").lower()
    patterns = [
        r"\blazy\s*edit\b",
        r"\blazyedit\b",
        r"upload\s+(?:it|this|the\s+video|video)\s+to\s+lazyedit",
        r"submit\s+(?:it|this|the\s+video|video)\s+to\s+lazyedit",
        r"import\s+(?:it|this|the\s+video|video)\s+to\s+lazyedit",
        r"上传.*lazyedit",
        r"提交.*lazyedit",
        r"导入.*lazyedit",
        r"交给.*lazyedit",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def generated_video_public_publish_allowed(task: dict[str, Any]) -> bool:
    return bool(generated_video_stage_permissions(task).get("public_publish"))


def run_generated_video_lazyedit_command(video_path: Path, task: dict[str, Any], monitor: dict[str, Any], *, publish: bool) -> dict[str, Any]:
    if os.environ.get("WECHAT_WORKER_DISABLE_GENERATED_VIDEO_LAZYEDIT"):
        return {"ok": False, "status": "disabled-by-env"}
    timeout = float(os.environ.get("WECHAT_WORKER_GENERATED_VIDEO_LAZYEDIT_TIMEOUT", str(DEFAULT_GENERATED_VIDEO_LAZYEDIT_TIMEOUT_SECONDS)))
    process_timeout = os.environ.get("WECHAT_WORKER_LAZYEDIT_PROCESS_TIMEOUT", str(DEFAULT_GENERATED_VIDEO_LAZYEDIT_PROCESS_TIMEOUT_SECONDS))
    publish_timeout = os.environ.get("WECHAT_WORKER_LAZYEDIT_REMOTE_TIMEOUT", str(DEFAULT_GENERATED_VIDEO_LAZYEDIT_PUBLISH_TIMEOUT_SECONDS))
    title = safe_slug(Path(str(monitor.get("filename") or video_path.stem)).stem or str(task.get("id") or "generated-video"))
    command_parts = [
        "source ~/miniconda3/etc/profile.d/conda.sh",
        "conda activate lazyedit",
        "python scripts/lazyedit_publish.py",
        f"--video {shell_quote(str(video_path))}",
        f"--title {shell_quote(title)}",
        "--use-current-settings",
        "--correct-subtitles",
        "--correction-source polished",
        "--guided-monitor",
        "--wait",
        "--poll-seconds 10",
        f"--process-timeout {process_timeout}",
        f"--publish-timeout {publish_timeout}",
        "--json",
    ]
    if LAZYEDIT_REMOTE_LOG_COMMAND:
        command_parts.append(f"--remote-log-command {shell_quote(LAZYEDIT_REMOTE_LOG_COMMAND)}")
    if publish:
        command_parts.append(f"--platforms {','.join(detect_publish_platforms(task, current_only=True))}")
    else:
        command_parts.append("--no-publish")
    correction_prompt, metadata_prompt = generated_video_lazyedit_context_paths(video_path, task, monitor)
    augment_generated_video_lazyedit_context(correction_prompt, metadata_prompt, monitor)
    if correction_prompt:
        command_parts.append(f"--correction-prompt-file {shell_quote(correction_prompt)}")
    if metadata_prompt:
        command_parts.append(f"--metadata-prompt-file {shell_quote(metadata_prompt)}")
    command = ["bash", "-lc", lazyedit_shell_command(command_parts)]
    return run_lazyedit_publish_subprocess(
        command,
        timeout=timeout,
        video_id=None,
        platforms=detect_publish_platforms(task, current_only=True) if publish else [],
        target=video_path,
    )


def generated_video_lazyedit_context_paths(video_path: Path, task: dict[str, Any], monitor: dict[str, Any]) -> tuple[str, str]:
    lazy_context = ((task.get("preflight") or {}).get("lazyedit_context") if isinstance(task.get("preflight"), dict) else {}) or {}
    correction_prompt = str(lazy_context.get("correction_prompt_file") or monitor.get("story_file") or "")
    metadata_prompt = str(lazy_context.get("metadata_prompt_file") or monitor.get("prompt_file") or "")
    artifact_dir = Path(str(task.get("artifact_dir") or worker_artifact_dir(task)))
    if not correction_prompt:
        correction_prompt = str(artifact_dir / "lazyedit_correction_context.md")
    if not metadata_prompt:
        metadata_prompt = str(artifact_dir / "lazyedit_metadata_brief.md")
    ensure_generated_video_lazyedit_context_files(video_path, task, correction_prompt, metadata_prompt)
    return correction_prompt, metadata_prompt


def ensure_generated_video_lazyedit_context_files(
    video_path: Path,
    task: dict[str, Any],
    correction_prompt: str,
    metadata_prompt: str,
) -> None:
    request = collapse_context_text(task_focus_text(task), max_len=3000)
    approved_story = collapse_context_text(str(task.get("approved_story_message") or ""), max_len=3000)
    interruption_summary = collapse_context_text(
        "\n".join(str(item.get("request_excerpt") or item.get("request") or "") for item in task_interruptions(task)[-4:] if isinstance(item, dict)),
        max_len=2000,
    )
    correction_body = "\n\n".join(
        part
        for part in [
            f"Video path: {video_path}",
            "Correct ASR subtitles using the current WeChat request, approved story, and same-chat interruptions as context. Preserve timing and avoid inventing unsupported dialogue.",
            f"Current request:\n{request}" if request else "",
            f"Approved story message:\n{approved_story}" if approved_story else "",
            f"Recent same-chat interruptions:\n{interruption_summary}" if interruption_summary else "",
        ]
        if part
    )
    metadata_body = "\n".join(
        part
        for part in [
            f"- Video path: {video_path}",
            "- Create concise viewer-facing metadata. Do not dump the full script.",
            f"- Current request: {collapse_context_text(request, max_len=800)}" if request else "",
            f"- Approved story: {collapse_context_text(approved_story, max_len=600)}" if approved_story else "",
        ]
        if part
    )
    append_lazyedit_context_once(Path(correction_prompt), "## WeChat Generated Video Context", correction_body)
    append_lazyedit_context_once(Path(metadata_prompt), "## WeChat Generated Video Metadata Brief", metadata_body)


def augment_generated_video_lazyedit_context(correction_prompt: str, metadata_prompt: str, monitor: dict[str, Any]) -> None:
    """Append generated story/prompt material to LazyEdit context files once."""
    story_text = read_lazyedit_context_source(monitor.get("story_file"), max_len=12000)
    prompt_text = read_lazyedit_context_source(monitor.get("prompt_file"), max_len=12000)
    if correction_prompt:
        sections = []
        if story_text:
            sections.append("### Generated Story / Script\n\n" + story_text)
        if prompt_text:
            sections.append("### Xiaoyunque Prompt / Generation Prompt\n\n" + prompt_text)
        append_lazyedit_context_once(
            Path(correction_prompt),
            "## Generated Video Script Context",
            "\n\n".join(sections),
        )
    if metadata_prompt:
        brief_sections = []
        if story_text:
            brief_sections.append("Story/script excerpt: " + collapse_context_text(story_text, max_len=900))
        if prompt_text:
            brief_sections.append("Generation prompt excerpt: " + collapse_context_text(prompt_text, max_len=900))
        append_lazyedit_context_once(
            Path(metadata_prompt),
            "## Generated Video Metadata Context",
            "\n".join(f"- {item}" for item in brief_sections),
        )


def read_lazyedit_context_source(path_value: Any, *, max_len: int) -> str:
    path_text = str(path_value or "").strip()
    if not path_text:
        return ""
    path = Path(path_text)
    try:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > max_len:
        return text[:max_len].rstrip() + "\n\n[truncated]"
    return text


def append_lazyedit_context_once(path: Path, marker: str, body: str) -> None:
    body = body.strip()
    if not body:
        return
    try:
        current = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    except OSError:
        return
    if marker in current:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current.rstrip() + "\n\n" + marker + "\n\n" + body + "\n", encoding="utf-8")
    except OSError:
        return


def should_deterministic_video_publish(task: dict[str, Any]) -> bool:
    if os.environ.get("WECHAT_WORKER_DISABLE_DETERMINISTIC_VIDEO_PUBLISH"):
        return False
    route = task_route_decision(task)
    if route:
        return str(route.get("route_kind") or "") == "publish_video" and bool(route.get("public_publish_allowed"))
    text = task_focus_text(task).lower()
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
    return has_public_publish_intent(text)


def run_deterministic_lazyedit_publish(task: dict[str, Any], autopub: dict[str, Any]) -> str | None:
    target_raw = str(autopub.get("target") or "")
    if not target_raw:
        return None
    target = Path(target_raw)
    if not target.is_file():
        source_path = Path(str(autopub.get("source_path") or "")).expanduser()
        if source_path.is_file():
            target = source_path
        else:
            return json.dumps(
                {
                    "message": f"视频已匹配但 AutoPublish 目标文件不存在：{target.name or target_raw}。我没有发布；请重新触发保存或重新发送视频。",
                    "files": [],
                    "confirmation": "",
                },
                ensure_ascii=False,
            )
    if not target.is_file():
        return json.dumps(
            {
                "message": f"视频已匹配但 AutoPublish 目标文件不存在：{target.name or target_raw}。我没有发布；请重新触发保存或重新发送视频。",
                "files": [],
                "confirmation": "",
            },
            ensure_ascii=False,
        )
    video_id = known_lazyedit_video_id_for_autopub(autopub)
    if video_id is None:
        timeout = float(os.environ.get("WECHAT_WORKER_LAZYEDIT_IMPORT_TIMEOUT", "360"))
        poll = float(os.environ.get("WECHAT_WORKER_LAZYEDIT_IMPORT_POLL_SECONDS", "5"))
        video_id = wait_for_lazyedit_import(target, timeout=timeout, poll_seconds=poll)
    else:
        timeout = 0.0
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
    verification = verify_lazyedit_publish_stage(video_id, platforms, target, {"status": "preflight"})
    if bool(verification.get("verified")):
        outcome = {"ok": True, "status": "already_verified", "duplicate_publish_guard": True}
    else:
        outcome = run_lazyedit_publish_command(
            video_id=video_id,
            platforms=platforms,
            correction_prompt=correction_prompt,
            metadata_prompt=metadata_prompt,
            target=target,
        )
        verification = verify_lazyedit_publish_stage(video_id, platforms, target, outcome)
    message = summarize_lazyedit_publish_outcome(video_id, platforms, target, outcome, verification=verification)
    payload: dict[str, Any] = {
        "message": message,
        "files": [],
        "confirmation": "",
        "publish_stage": verification,
    }
    confirmation = publish_stage_confirmation(verification)
    if confirmation:
        payload["confirmation"] = confirmation
    if not bool(verification.get("verified")):
        poststage = {
            "kind": "existing_video_publish",
            "stage": verification.get("stage") or "not_verified",
            "video_id": video_id,
            "platforms": platforms,
            "target": str(target),
            "target_name": target.name,
            "source_path": autopub.get("source_path"),
            "autopublish_video": autopub,
            "lazyedit_context": lazy_context,
        }
        if confirmation:
            payload["poststage"] = poststage
        else:
            payload["publish_poststage_retry"] = {
                "status": verification.get("stage") or "not_verified",
                "retry_seconds": publish_stage_retry_seconds(verification),
                "poststage": poststage,
                "outcome": compact_publish_outcome(outcome),
            }
    return json.dumps(payload, ensure_ascii=False)


def known_lazyedit_video_id_for_autopub(autopub: dict[str, Any]) -> int | None:
    for key in ("video_id", "lazyedit_video_id"):
        value = int_or_none(autopub.get(key))
        if value is not None:
            return value
    source_task = autopub.get("source_task") if isinstance(autopub.get("source_task"), dict) else {}
    texts = [
        source_task.get("result_message_excerpt"),
        source_task.get("request_excerpt"),
        source_task.get("result"),
    ]
    for text in texts:
        if not text:
            continue
        match = re.search(r"\bvideo_id\s*[=:]\s*(\d+)\b", str(text), flags=re.I)
        if match:
            return int(match.group(1))
    return None


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


def detect_publish_platforms(task: dict[str, Any], *, current_only: bool = False) -> list[str]:
    text = task_focus_text(task).lower() if current_only else json.dumps(task, ensure_ascii=False).lower()
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
    target: Path | None = None,
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
    if LAZYEDIT_REMOTE_LOG_COMMAND:
        command_parts.append(f"--remote-log-command {shell_quote(LAZYEDIT_REMOTE_LOG_COMMAND)}")
    if correction_prompt:
        command_parts.append(f"--correction-prompt-file {shell_quote(correction_prompt)}")
    if metadata_prompt:
        command_parts.append(f"--metadata-prompt-file {shell_quote(metadata_prompt)}")
    command = ["bash", "-lc", lazyedit_shell_command(command_parts)]
    return run_lazyedit_publish_subprocess(
        command,
        timeout=timeout,
        video_id=video_id,
        platforms=platforms,
        target=target,
    )


def run_lazyedit_publish_subprocess(
    command: list[str],
    *,
    timeout: float,
    video_id: int | None,
    platforms: list[str],
    target: Path | None,
) -> dict[str, Any]:
    if not lazyedit_publish_watchdog_enabled() or video_id is None:
        return run_lazyedit_publish_subprocess_blocking(command, timeout=timeout)
    poll_seconds = lazyedit_publish_watchdog_poll_seconds()
    start = time.monotonic()
    next_probe = start + poll_seconds
    proc = subprocess.Popen(
        command,
        cwd=LAZYEDIT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while True:
            remaining = max(0.0, timeout - (time.monotonic() - start))
            if remaining <= 0:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
                return {"ok": False, "status": "timeout", "stdout": (stdout or "")[-4000:], "stderr": (stderr or "")[-4000:], "command": command[-1] if command else ""}
            try:
                stdout, stderr = proc.communicate(timeout=min(1.0, remaining))
                completed = subprocess.CompletedProcess(command, proc.returncode, stdout or "", stderr or "")
                return lazyedit_publish_proc_result(completed, command=command)
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if now < next_probe:
                    continue
                next_probe = now + poll_seconds
                verification = verify_lazyedit_publish_stage(video_id, platforms, target or Path(""), {"status": "running"})
                if str(verification.get("stage") or "") == "waiting_login":
                    terminate_process(proc)
                    stdout, stderr = proc.communicate(timeout=10)
                    return {
                        "ok": False,
                        "status": "waiting_login",
                        "returncode": proc.returncode,
                        "stdout": (stdout or "")[-8000:],
                        "stderr": (stderr or "")[-4000:],
                        "payload": {"publish_stage": verification},
                        "command": command[-1] if command else "",
                    }
    except Exception:
        terminate_process(proc)
        raise


def run_lazyedit_publish_subprocess_blocking(command: list[str], *, timeout: float) -> dict[str, Any]:
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
        return {"ok": False, "status": "timeout", "stdout": (exc.stdout or "")[-4000:], "stderr": (exc.stderr or "")[-4000:], "command": command[-1] if command else ""}
    return lazyedit_publish_proc_result(proc, command=command)


def lazyedit_publish_watchdog_enabled() -> bool:
    if os.environ.get("WECHAT_WORKER_LAZYEDIT_PUBLISH_WATCHDOG", "1") == "0":
        return False
    return bool(LAZYEDIT_REMOTE_LOG_COMMAND)


def lazyedit_publish_watchdog_poll_seconds() -> float:
    try:
        return max(5.0, float(os.environ.get("WECHAT_WORKER_LAZYEDIT_PUBLISH_WATCHDOG_SECONDS", "30")))
    except ValueError:
        return 30.0


def terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def lazyedit_shell_command(command_parts: list[str]) -> str:
    if len(command_parts) < 3:
        return " ".join(command_parts)
    return " && ".join([command_parts[0], command_parts[1], " ".join(command_parts[2:])])


def lazyedit_publish_proc_result(proc: subprocess.CompletedProcess[str], *, command: list[str]) -> dict[str, Any]:
    payload = parse_last_json_object(proc.stdout)
    if not payload:
        payload = parse_last_json_object(proc.stderr)
    ok = proc.returncode == 0 and bool(payload)
    if ok:
        status = "done"
    elif proc.returncode == 0:
        status = "no_json_output"
    else:
        status = "failed"
    return {
        "ok": ok,
        "status": status,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
        "payload": payload,
        "command": command[-1] if command else "",
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


def deterministic_existing_video_publish_poststage_result(task: dict[str, Any]) -> str | None:
    if not is_video_publish_task(task) or str(task.get("status") or "") != CLAIMED_STATUS:
        return None
    poststage = task.get("existing_video_publish_poststage") if isinstance(task.get("existing_video_publish_poststage"), dict) else {}
    if not poststage:
        return None
    video_id = int_or_none(poststage.get("video_id"))
    if video_id is None:
        return None
    platforms = [str(item) for item in poststage.get("platforms") or detect_publish_platforms(task)]
    target = Path(str(poststage.get("target") or poststage.get("target_name") or ""))
    verification = verify_lazyedit_publish_stage(video_id, platforms, target, {"status": "probe"})
    stage = str(verification.get("stage") or "not_verified")
    if should_reissue_existing_video_publish(task, poststage, verification):
        outcome = run_existing_video_publish_from_poststage(task, poststage, video_id, platforms)
        task["publish_poststage_reissue_count"] = int(task.get("publish_poststage_reissue_count") or 0) + 1
        task["publish_poststage_last_reissue_at"] = datetime.now().isoformat(timespec="seconds")
        task["publish_poststage_last_reissue_outcome"] = compact_publish_outcome(outcome)
        verification = verify_lazyedit_publish_stage(video_id, platforms, target, outcome)
        stage = str(verification.get("stage") or "not_verified")
        message = summarize_lazyedit_publish_outcome(video_id, platforms, target, outcome, verification=verification)
        payload = {
            "message": message,
            "files": [],
            "confirmation": "",
            "publish_stage": verification,
            "publish_reissue": compact_publish_outcome(outcome),
        }
        confirmation = publish_stage_confirmation(verification)
        if confirmation:
            payload["confirmation"] = confirmation
        if not bool(verification.get("verified")):
            if confirmation:
                payload["poststage"] = poststage
            else:
                payload["publish_poststage_retry"] = {
                    "status": stage,
                    "retry_seconds": publish_stage_retry_seconds(verification),
                    "poststage": poststage,
                    "outcome": compact_publish_outcome(outcome),
                }
        return json.dumps(payload, ensure_ascii=False)
    wait_count = int(task.get("publish_poststage_wait_count") or 0)
    probe_only_retries = int(os.environ.get("WECHAT_WORKER_EXISTING_VIDEO_PUBLISH_PROBE_ONLY_RETRIES", "1"))
    if stage in {"no_local_job", "failed", "unverified_done"} and wait_count >= probe_only_retries:
        # Let the resumed per-chat Codex worker inspect LazyEdit/browser state
        # and repair the routine. The deterministic probe has no proof to close
        # or continue by itself.
        return None
    message = summarize_lazyedit_publish_outcome(video_id, platforms, target, {"status": "probe"}, verification=verification)
    payload: dict[str, Any] = {
        "message": message,
        "files": [],
        "confirmation": "",
        "publish_stage": verification,
    }
    confirmation = publish_stage_confirmation(verification)
    if confirmation:
        payload["confirmation"] = confirmation
    if not bool(verification.get("verified")):
        if confirmation:
            payload["poststage"] = poststage
        else:
            payload["publish_poststage_retry"] = {
                "status": stage,
                "retry_seconds": publish_stage_retry_seconds(verification),
                "poststage": poststage,
                "outcome": {"status": "probe"},
            }
    return json.dumps(payload, ensure_ascii=False)


def should_reissue_existing_video_publish(task: dict[str, Any], poststage: dict[str, Any], verification: dict[str, Any]) -> bool:
    if os.environ.get("WECHAT_WORKER_DISABLE_EXISTING_VIDEO_PUBLISH_REISSUE"):
        return False
    if str(verification.get("stage") or "") != "no_local_job":
        return False
    if not int_or_none(poststage.get("video_id")):
        return False
    if not poststage.get("platforms"):
        return False
    max_reissues = int(os.environ.get("WECHAT_WORKER_EXISTING_VIDEO_PUBLISH_MAX_REISSUES", "3"))
    if int(task.get("publish_poststage_reissue_count") or 0) >= max_reissues:
        return False
    return should_deterministic_video_publish(task)


def run_existing_video_publish_from_poststage(
    task: dict[str, Any],
    poststage: dict[str, Any],
    video_id: int,
    platforms: list[str],
) -> dict[str, Any]:
    lazy_context = poststage.get("lazyedit_context") if isinstance(poststage.get("lazyedit_context"), dict) else {}
    if not lazy_context and isinstance(task.get("preflight"), dict):
        lazy_context = task["preflight"].get("lazyedit_context") if isinstance(task["preflight"].get("lazyedit_context"), dict) else {}
    target = Path(str(poststage.get("target") or poststage.get("target_name") or ""))
    verification = verify_lazyedit_publish_stage(video_id, platforms, target, {"status": "preflight"})
    if bool(verification.get("verified")):
        return {"ok": True, "status": "already_verified", "duplicate_publish_guard": True}
    return run_lazyedit_publish_command(
        video_id=video_id,
        platforms=platforms,
        correction_prompt=str(lazy_context.get("correction_prompt_file") or ""),
        metadata_prompt=str(lazy_context.get("metadata_prompt_file") or ""),
        target=target,
    )


def verify_lazyedit_publish_stage(video_id: int, platforms: list[str], target: Path, outcome: dict[str, Any]) -> dict[str, Any]:
    requested = normalize_platforms(platforms)
    local_jobs = matching_lazyedit_publish_jobs(video_id, outcome)
    remote_jobs = remote_publish_jobs_for(local_jobs)
    verified_platforms: set[str] = set()
    pending = False
    failed = False
    for index, job in enumerate(local_jobs):
        remote = remote_jobs[index] if index < len(remote_jobs) else {}
        status = normalized_status(job.get("status"))
        remote_status = normalized_status(job.get("remote_status") or remote.get("status"))
        job_platforms = normalize_platforms(job.get("platforms") or requested)
        if publish_job_verified(job, remote):
            verified_platforms.update(job_platforms)
        elif status in {"queued", "running", "pending"} or remote_status in {"queued", "running", "pending"}:
            pending = True
        elif status in {"failed", "error"} or remote_status in {"failed", "error"}:
            failed = True
        elif status == "done":
            pending = True
    verified = bool(requested) and set(requested).issubset(verified_platforms)
    if verified:
        stage = "published_verified"
    elif not local_jobs:
        stage = "no_local_job"
    elif failed and not pending:
        stage = "failed"
    elif pending:
        stage = "publish_running"
    else:
        stage = "unverified_done"
    blocker = lazyedit_remote_blocker(local_jobs, remote_jobs) if not verified else {}
    if blocker:
        stage = str(blocker.get("stage") or stage)
    return {
        "verified": verified,
        "stage": stage,
        "video_id": video_id,
        "requested_platforms": requested,
        "verified_platforms": sorted(verified_platforms),
        "local_jobs": compact_publish_jobs(local_jobs),
        "remote_jobs": compact_publish_jobs(remote_jobs),
        "blocker": blocker,
        "source": target.name if str(target) else "",
        "rule": "Do not say published unless all requested platforms have terminal platform evidence.",
    }


def lazyedit_remote_blocker(local_jobs: list[dict[str, Any]], remote_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    if not LAZYEDIT_REMOTE_LOG_COMMAND:
        return {}
    if not any(job_is_active(job, remote_jobs[index] if index < len(remote_jobs) else {}) for index, job in enumerate(local_jobs)):
        return {}
    try:
        proc = subprocess.run(
            ["bash", "-lc", LAZYEDIT_REMOTE_LOG_COMMAND],
            capture_output=True,
            text=True,
            check=False,
            timeout=float(os.environ.get("WECHAT_WORKER_LAZYEDIT_REMOTE_LOG_TIMEOUT", "15")),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    log = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-12000:]
    return detect_remote_publish_blocker_from_log(local_jobs, remote_jobs, log)


def job_is_active(job: dict[str, Any], remote: dict[str, Any]) -> bool:
    status = normalized_status(job.get("status"))
    remote_status = normalized_status(job.get("remote_status") or remote.get("status"))
    return status in {"queued", "running", "pending"} or remote_status in {"queued", "running", "pending"}


def detect_remote_publish_blocker_from_log(
    local_jobs: list[dict[str, Any]],
    remote_jobs: list[dict[str, Any]],
    log: str,
) -> dict[str, Any]:
    if not log:
        return {}
    lowered = log.lower()
    login_markers = (
        "login iframe detected",
        "login required",
        "not logged in yet",
        "扫码",
        "登录",
        "登入",
    )
    if not any(marker in lowered for marker in login_markers):
        return {}
    identifiers: list[str] = []
    for index, job in enumerate(local_jobs):
        remote = remote_jobs[index] if index < len(remote_jobs) else {}
        for key in ("remote_job_id", "filename"):
            value = str(job.get(key) or "")
            if value:
                identifiers.append(value)
        for key in ("id", "job_id", "filename"):
            value = str(remote.get(key) or "")
            if value:
                identifiers.append(value)
    matched = [identifier for identifier in identifiers if identifier and identifier in log]
    if not matched:
        return {}
    return {
        "stage": "waiting_login",
        "kind": "remote_login_required",
        "matched": matched[:4],
        "message": "Remote AutoPublish is waiting for platform login or QR confirmation.",
    }


def matching_lazyedit_publish_jobs(video_id: int, outcome: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    queue = lazyedit_api_get("/api/autopublish/queue", timeout=30)
    queue_jobs = queue.get("jobs") if isinstance(queue, dict) else []
    for job in queue_jobs or []:
        if isinstance(job, dict) and int_or_none(job.get("video_id")) == video_id:
            jobs.append(job)
    payload = outcome.get("payload") if isinstance(outcome.get("payload"), dict) else {}
    for key in ("publish_job", "publish_started"):
        candidate = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(candidate, dict):
            job = candidate.get("job") if isinstance(candidate.get("job"), dict) else candidate
            if isinstance(job, dict) and not any(same_local_job_id(existing.get("id"), int_or_none(job.get("id")) or -1) for existing in jobs):
                if int_or_none(job.get("video_id")) is None:
                    job = {**job, "video_id": video_id}
                jobs.append(job)
    jobs.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return jobs


def same_local_job_id(left: Any, right: Any) -> bool:
    left_int = int_or_none(left)
    right_int = int_or_none(right)
    if left_int is not None and right_int is not None:
        return left_int == right_int
    return str(left or "") == str(right or "")


def remote_publish_jobs_for(local_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not local_jobs or not LAZYEDIT_REMOTE_QUEUE_URL:
        return [{} for _ in local_jobs]
    try:
        with urllib.request.urlopen(LAZYEDIT_REMOTE_QUEUE_URL, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return [{} for _ in local_jobs]
    remote_jobs = payload.get("jobs") if isinstance(payload, dict) else []
    if not isinstance(remote_jobs, list):
        return [{} for _ in local_jobs]
    matches: list[dict[str, Any]] = []
    for job in local_jobs:
        remote_id = str(job.get("remote_job_id") or "")
        filename = str(job.get("remote_filename") or job.get("filename") or "")
        match = {}
        for remote in remote_jobs:
            if not isinstance(remote, dict):
                continue
            if remote_id and str(remote.get("id") or remote.get("job_id") or "") == remote_id:
                match = remote
                break
            if not remote_id and filename and str(remote.get("filename") or "") == filename:
                match = remote
                break
        matches.append(match)
    return matches


def publish_job_verified(job: dict[str, Any], remote: dict[str, Any]) -> bool:
    status = normalized_status(job.get("status"))
    remote_status = normalized_status(job.get("remote_status") or remote.get("status"))
    if status not in {"done", "completed", "success", "succeeded"}:
        return False
    if remote_status in {"done", "completed", "success", "succeeded"}:
        return True
    return bool(public_publish_evidence(job) or public_publish_evidence(remote))


def public_publish_evidence(job: dict[str, Any]) -> bool:
    for key in ("url", "urls", "public_url", "public_urls", "post_url", "post_urls", "published_urls", "result_urls"):
        value = job.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return True
        if isinstance(value, list) and any(str(item).startswith(("http://", "https://")) for item in value):
            return True
    return False


def normalize_platforms(platforms: Any) -> list[str]:
    if isinstance(platforms, str):
        raw = [platforms]
    elif isinstance(platforms, list):
        raw = [str(item) for item in platforms]
    else:
        raw = []
    normalized: list[str] = []
    aliases = {"sph": "shipinhao", "视频号": "shipinhao", "視頻號": "shipinhao", "y2b": "youtube", "ytb": "youtube", "ins": "instagram"}
    for item in raw:
        for part in re.split(r"[,，、\s]+", item.lower()):
            part = aliases.get(part.strip(), part.strip())
            if part and part not in normalized:
                normalized.append(part)
    return normalized


def normalized_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    aliases = {"complete": "done", "completed": "completed", "success": "success", "succeeded": "succeeded", "queued": "queued", "running": "running", "pending": "pending", "error": "error"}
    return aliases.get(status, status)


def compact_publish_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = ("id", "video_id", "status", "platforms", "remote_status", "remote_job_id", "filename", "updated_at", "error")
    return [{key: job.get(key) for key in keep if job.get(key) not in (None, "")} for job in jobs[:6] if isinstance(job, dict)]


def compact_publish_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": outcome.get("ok"),
        "status": outcome.get("status"),
        "returncode": outcome.get("returncode"),
        "payload": outcome.get("payload") if isinstance(outcome.get("payload"), dict) else {},
        "stderr_tail": collapse_context_text(outcome.get("stderr"), max_len=600),
    }


def publish_stage_retry_seconds(verification: dict[str, Any]) -> int:
    stage = str(verification.get("stage") or "")
    if stage == "publish_running":
        return int(os.environ.get("WECHAT_WORKER_EXISTING_VIDEO_PUBLISH_RUNNING_RETRY_SECONDS", "600"))
    if stage == "no_local_job":
        return int(os.environ.get("WECHAT_WORKER_EXISTING_VIDEO_PUBLISH_IMPORT_RETRY_SECONDS", "180"))
    if stage == "waiting_login":
        return int(os.environ.get("WECHAT_WORKER_EXISTING_VIDEO_PUBLISH_LOGIN_RETRY_SECONDS", "1800"))
    return int(os.environ.get("WECHAT_WORKER_EXISTING_VIDEO_PUBLISH_RETRY_SECONDS", "600"))


def publish_stage_confirmation(verification: dict[str, Any]) -> str:
    if str(verification.get("stage") or "") != "waiting_login":
        return ""
    blocker = verification.get("blocker") if isinstance(verification.get("blocker"), dict) else {}
    message = str(blocker.get("message") or "Remote AutoPublish is waiting for platform login or QR confirmation.")
    return (
        f"{message} Please complete the platform login in the AutoPublish browser/noVNC, "
        "then approve this waiting task so the worker can resume verification. I will not mark it as published until the queue has terminal evidence."
    )


def summarize_lazyedit_publish_outcome(
    video_id: int,
    platforms: list[str],
    target: Path,
    outcome: dict[str, Any],
    *,
    verification: dict[str, Any] | None = None,
) -> str:
    verification = verification or verify_lazyedit_publish_stage(video_id, platforms, target, outcome)
    requested = ",".join(verification.get("requested_platforms") or normalize_platforms(platforms))
    stage = str(verification.get("stage") or "not_verified")
    local_jobs = verification.get("local_jobs") or []
    latest = local_jobs[0] if local_jobs else {}
    local_job_id = latest.get("id") if isinstance(latest, dict) else None
    remote_job_id = latest.get("remote_job_id") if isinstance(latest, dict) else None
    remote_status = latest.get("remote_status") if isinstance(latest, dict) else None
    if verification.get("verified"):
        pieces = [
            "已确认发布完成。",
            f"video_id={video_id}",
            f"platforms={requested}",
            f"stage={stage}",
        ]
        if local_job_id:
            pieces.append(f"job_id={local_job_id}")
        if remote_job_id:
            pieces.append(f"remote_job_id={remote_job_id}")
        if remote_status:
            pieces.append(f"remote={remote_status}")
        pieces.append(f"source={target.name}")
        return "；".join(pieces)
    pieces = [
        "未确认发布完成；不会把提交/排队当作已发布。",
        f"video_id={video_id}",
        f"platforms={requested}",
        f"stage={stage}",
    ]
    if local_job_id:
        pieces.append(f"job_id={local_job_id}")
    if remote_job_id:
        pieces.append(f"remote_job_id={remote_job_id}")
    if remote_status:
        pieces.append(f"remote={remote_status}")
    error = latest.get("error") if isinstance(latest, dict) else ""
    if not error:
        error = outcome.get("stderr") or outcome.get("status") or ""
    if error:
        pieces.append(f"detail={collapse_context_text(error, max_len=240)}")
    pieces.append(f"source={target.name}")
    pieces.append("我会保留任务并继续用同一聊天的 worker session 检查/修复。")
    return "；".join(pieces)


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_video_local_ids_from_task(task: dict[str, Any]) -> list[int]:
    source_local_id = int_or_none((task.get("source") or {}).get("local_id")) if isinstance(task.get("source"), dict) else None
    if source_local_id is not None:
        for row in task.get("context") or []:
            if not isinstance(row, dict):
                continue
            if int_or_none(row.get("local_id")) != source_local_id:
                continue
            content = str(row.get("content") or "")
            referenced = referenced_video_local_ids_from_source(task, content)
            if referenced:
                return referenced
            if "<videomsg" in content or "[WeChat video]" in content:
                return [source_local_id]
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


def referenced_video_local_ids_from_source(task: dict[str, Any], source_content: str) -> list[int]:
    if "<refermsg>" not in source_content and "&lt;refermsg&gt;" not in source_content:
        return []
    text = html.unescape(str(source_content or ""))
    server_ids: list[str] = []
    for value in re.findall(r"<svrid>\s*([0-9]{8,})\s*</svrid>", text):
        add_once(server_ids, value)
    if not server_ids:
        return []
    server_to_local = video_server_id_to_local_id_map(task)
    local_ids: list[int] = []
    for server_id in server_ids:
        local_id = server_to_local.get(server_id)
        if local_id is not None:
            add_once(local_ids, local_id)
    return local_ids


def video_server_id_to_local_id_map(task: dict[str, Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    request = str(task.get("request") or "")
    pattern = re.compile(r"local_id\s*[=:]\s*(\d+)\s+server_id\s*[=:]\s*([0-9]{8,})")
    for match in pattern.finditer(request):
        local_id = int_or_none(match.group(1))
        server_id = match.group(2)
        if local_id is None:
            continue
        row = next((item for item in task.get("context") or [] if isinstance(item, dict) and int_or_none(item.get("local_id")) == local_id), None)
        content = str((row or {}).get("content") or "")
        if "<videomsg" in content or "[WeChat video]" in content:
            mapping.setdefault(server_id, local_id)
    return mapping


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


def build_generated_video_tool_context(task: dict[str, Any]) -> str:
    if not is_generate_video_task(task):
        return ""
    artifact_dir = str(task.get("artifact_dir") or worker_artifact_dir(task))
    stages = json.dumps(generated_video_stage_permissions(task), ensure_ascii=False, indent=2)
    routine = json.dumps(generated_video_orchestration_routine(task), ensure_ascii=False, indent=2)
    return f"""

Generated-video route contract:
- This task is classified as `generate_video`. Before doing anything, re-check `task.route_decision` against the current request and follow the safer interpretation if they conflict.
- Use the route contract saved in `{artifact_dir}/generated_video_route_contract.md` as the handoff for any subsequent agent or browser helper.
- Treat this as a routine orchestration job. Follow the orchestration routine below in order; do not invent a new approach for stages that already have an entrypoint.
- Stage permissions from the current request:
```json
{stages}
```
- Orchestration routine:
```json
{routine}
```
- Do not process old WeChat MP4 files, Nutstore AutoPublish files, LazyEdit videos, or public platform jobs as the output for this task.
- After a new MP4 is downloaded and verified, include it in the JSON `files` array so the outer worker sends it back to the source WeChat chat.
- Generation is not publication: creating/downloading/sending the MP4 does not authorize LazyEdit import, AutoPublish, or public posting.
- If `task.route_decision.public_publish_allowed` is false, public posting and AutoPublish public queue submission are forbidden even if older chat history mentions them.
- LazyEdit import/process is a separate stage: do it only when the current request explicitly says LazyEdit/import/process, and use no-public-publish mode unless public publishing is also explicitly allowed.
- Same-chat interruptions are part of this route contract. If newer messages ask to update/rewrite/show/confirm the story, or say the current website generation was stopped/cancelled, revise the story and prompt from the full interruption context before any further video submit. Send the updated story to the group and ask whether to generate unless the latest messages clearly authorize generation.
- If the user confirms the revised story after seeing it, update the Xiaoyunque prompt/continuation from that approved story and the latest same-chat context. Prefer continuing the same usable XYQ thread/session; only start a new paid run when the current request explicitly authorizes a new run and the existing thread cannot be used.
- If a newer same-chat or operator note says the owner already downloaded one or more XYQ videos to Downloads and handed them to LazyEdit/publication, record that manual handoff as terminal state for this automation path. Do not reopen the XYQ page, redownload, resubmit, continue, import, or publish unless a later explicit request asks the automation to take over again.
- Do not keep polling, download, publish, or report success for a stale Xiaoyunque run after a same-chat interruption says the story is wrong or the browser run was stopped.
- Paid Xiaoyunque/Seedance actions are idempotent per logical WeChat request. If this task already has `generated_video_monitor.thread_url`, `generated_video_submit_probe`, `credit_guard`, `route_decision.no_new_xyq_submit`, or `monitor_only_no_resubmit`, do not submit/continue/retry a paid generation; monitor/download/send only.
- For LALACHAN/Xiaoyunque, model selection must not block the task. Choose a relatively cheaper suitable model from the available page options and proceed. Prefer `Seedance 2.0 Mini 体验版` / `vipnew` when it shows `单秒限时低至4积分`; otherwise use the cheapest suitable `Seedance 2.0 Fast`, `Fast VIP`, or available Seedance row. Pause only for real non-model blockers such as no credits, recharge/payment approval, disabled submit, login, CAPTCHA, or an explicit user budget limit.
- Prefer these existing Xiaoyunque helpers from `/home/lachlan/.codex/skills/lalachan-xyq-browser-video`:
  `scripts/xyq_cdp_browser.py list-pages`
  `scripts/xyq_cdp_browser.py upload-images-verify PAGE_ID <8 reference images> --timeout 180 --screenshot {artifact_dir}/xyq_after_upload.png`
  `scripts/xyq_cdp_browser.py type-prompt PAGE_ID <prompt.md> --wait 0.5`
  `scripts/xyq_chrome/watch_thread_dom_download.py --page-id PAGE_ID --thread-url THREAD_URL --output-dir {artifact_dir} --filename result.mp4 --copy-to /home/lachlan/ProjectsLFS/LALACHAN/Videos`
- A valid final result must include a new MP4 path that can be sent back to WeChat, or clearly say the browser job is submitted/running/blocked and include the screenshot/log path.
"""


def build_worker_tool_context(task: dict[str, Any]) -> str:
    artifact_dir = str(task.get("artifact_dir") or worker_artifact_dir(task))
    prompt_text = str(task.get("request") or "").strip()
    quoted_prompt = json.dumps(prompt_text or "prepare CAD/PCB/Blender artifacts", ensure_ascii=False)
    generated_video_note = build_generated_video_tool_context(task)
    media_resolution_note = build_media_resolution_tool_context(task)
    return f"""LabCanvas tool playbook:
- Use `{artifact_dir}` as the preferred working/output folder for new artifacts.
- Match every input file/media path to this task's exact `chat`, `source.local_id`, `source.server_id`, explicit source/reference rows in `request`, or source-scoped context text. Do not borrow files from another group/direct chat or from unrelated previous worker tasks.
- If the exact requested media is missing, stop with a source-limited message asking the user to resend/provide it instead of using a nearby file.
{media_resolution_note}
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
{generated_video_note}

LALACHAN/RaraXia/AyaChan/SasaKun story-video generation:
- For requests mentioning LALACHAN, RaraXia/Rara Xia/啦啦侠, AyaChan/Aya Chan/阿芽酱, SasaKun/Sasa Kun/飒飒君, Xiaoyunque/小云雀, XYQ, or Seedance, treat the task as a LALACHAN repo workflow rather than a generic video prompt.
- Use `/home/lachlan/ProjectsLFS/LALACHAN` as the default root. If available, read `/home/lachlan/.codex/skills/lalachan-xyq-browser-video/SKILL.md` and `/home/lachlan/ProjectsLFS/LALACHAN/references/lalachan-story-video-handoff-for-wechat.md` for the current runbook.
- First write a natural, understandable Chinese story with one clear setup -> problem -> action -> twist -> payoff chain. Save it under `/home/lachlan/ProjectsLFS/LALACHAN/references/stories/`.
- Convert the story into a compact Xiaoyunque prompt and save it under `/home/lachlan/ProjectsLFS/LALACHAN/references/prompts/`.
- Use the Xiaoyunque browser UI, not the API, unless explicitly requested. Default to 沉浸式短片, a relatively cheap suitable Seedance model, 4:3, mainly Chinese, with `不要字幕，不要生成任何字幕、说明文字、下三分之一文字或画面文字。` Respect an explicit requested duration such as 30s; use 15s only when the request gives no duration. A generated MP4 within ±5 seconds of the requested duration is acceptable unless the current request explicitly says the duration must be exact.
- Model selection must not block the task. For "cheap model", prefer `Seedance 2.0 Mini 体验版` / `vipnew` when the page shows a cheap rate such as `单秒限时低至4积分`; otherwise choose the relatively cheaper suitable `Seedance 2.0 Fast`, `Fast VIP`, or available Seedance option and continue.
- Upload and verify the eight default reference images in this exact order: `words-card.jpg`, `LazyingArtRobot.png`, `display.png`, `patchwork-leather-notebook-luxury-clean-v2.png`, `raraxia.jpeg`, `ayachan.png`, `sasakun.jpeg`, `Trio.png`.
- In the Xiaoyunque prompt, refer to uploaded images as 图1 through 图8. Do not paste local filesystem paths or file names into the prompt as scene text.
- Before any submit, verify visible page state as far as the UI allows: mode, selected model row, duration, ratio, prompt, upload success, and any visible point cost/VIP/vipnew state. Do not block only because the exact preferred model or exact cost text is unavailable. Never double-click submit or retry if the job is queued/running.
- Before any submit or continuation, inspect the task for existing XYQ thread/credit evidence. If a thread already exists or the task is monitor-only, do not spend more credits. Ask for explicit "new paid rerun" permission if the user truly wants another generation.
- If the active task has same-chat interruptions, read them all before writing or submitting. When interruptions revise the story, save a new story/prompt revision, send the story text back for confirmation, and wait unless the latest user message explicitly says to continue generating.
- If the user confirms the shown story, turn that exact approved story plus all later same-chat constraints into the Xiaoyunque prompt or continuation message. Avoid generic "continue" prompts when the chat has supplied new story details.
- If the user reports that they manually downloaded multiple XYQ outputs and gave them to LazyEdit, record the handoff and stop automation for that session. Do not duplicate downloads or LazyEdit publishing.
- Monitor the thread, download the finished MP4, save/copy it under `/home/lachlan/ProjectsLFS/LALACHAN/Videos`, verify with `ffprobe`, apply the duration tolerance above, and return the story path, prompt path, MP4 path, and relevant screenshots/logs in `files` where safe. The outer worker will send the MP4 back to the source WeChat chat.
- If the current request asks for LazyEdit import/process, hand the verified MP4 to LazyEdit with no public publish unless public publishing is also explicitly requested. If the user asks to publish in the current request, then hand the verified MP4 to LazyEdit with the publish workflow below. Otherwise stop after generation/download/send-back and report the ready video path.

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

WeChat article / `mp.weixin.qq.com` link cards:
- Direct HTTP fetches commonly return `环境异常`, `完成验证后继续访问`, or another verification gate. Treat that as a browser-required state, not as a finished article read.
- Do not open an external Chrome/browser for mp.weixin by default. It can steal focus from the official WeChat client and make the desktop appear locked. Treat external browser-assist as opt-in only: use it only if the current user message explicitly asks for browser/noVNC, or `WECHAT_ALLOW_EXTERNAL_BROWSER_FOR_MP_WEIXIN=1` is set.
- Preferred order:
  1. Use already captured readable article text if present.
  2. Use the native WeChat article/webview path from the official client when the card is visible or the user has opened it there.
  3. If verification is required, return `waiting_confirmation` and ask the user to verify/open it in WeChat, then resume capture after confirmation.
  4. Only with explicit permission/config, use `PYTHONPATH=src python -m agenticapp wechat browser-assist --url "<mp.weixin.qq.com URL>" --reuse-window --wait-seconds 8 --capture --wait-readable-seconds 60 --json`.
- If the source remains blocked, say exactly what was accessible. Do not claim the card title/description is the full article.

Link/read-later summary reports:
- For web_clip_inbox/link_inbox sources, return a concise chat summary plus a Markdown report under the task artifact directory when the source has substantive content.
- For papers, PDFs, arXiv/DOI links, GitHub repositories, technical articles, mp.weixin/Gongzhonghao articles, and useful Shipinhao/Finder summaries, also generate a PDF report when practical and list it in `files`. If PDF generation is unavailable, include the Markdown report.
- For GitHub links, summarize purpose, install/use path, key files, license/stars if accessible, risks, and likely relevance.
- For papers, include title/authors/venue/DOI when accessible, problem, method, results, limitations, and links/PDF evidence.
- For Shipinhao/Finder videos, use accessible metadata, video media, comments, transcript/summary comments, or public mirrors; clearly mark limitations if the video/comments/transcript are not available.

Artifact return contract:
- If you generate or find safe artifacts, include their existing absolute or repo-relative paths in the JSON `files` array. The outer worker sends those files to WeChat by default.
- Return artifacts, not only saved paths: story Markdown, LaTeX/source files, compiled PDFs, image previews, renders, CAD/PCB exports, manifests, archives, video/audio, and any requested downloadable file should be listed when safe.
- Prefer PNG/JPG/SVG/PDF/MD/TEX/MP4/MOV/audio/STEP/STL/3MF/DXF/ZIP/SCAD/Blend/KiCad/Gerber files. Do not include decrypted WeChat DBs, private config, cookies, tokens, browser profiles, or chat logs.
- Do not say a file was sent unless it is listed in `files` and exists locally.
"""


def build_media_resolution_tool_context(task: dict[str, Any]) -> str:
    preflight = task.get("preflight") if isinstance(task.get("preflight"), dict) else {}
    media = preflight.get("media_resolution") if isinstance(preflight.get("media_resolution"), dict) else {}
    if not media:
        return ""
    copied = media.get("copied") if isinstance(media.get("copied"), list) else []
    if not copied:
        return (
            "- Media resolution preflight ran but did not find a source-scoped local file. "
            f"Manifest: `{media.get('manifest_md') or media.get('manifest_json') or ''}`. "
            "Do not claim the image/file is unavailable until you have checked this manifest and the source rows.\n"
        )
    lines = [
        "- Media resolution preflight found source-scoped local files. Use these paths as the first-choice inputs for this task:",
    ]
    for item in copied[:8]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"  - `{item.get('task_copy_path')}` "
            f"suffix={item.get('suffix')} bytes={item.get('size_bytes')} "
            f"score={item.get('score')} reasons={','.join(str(reason) for reason in item.get('match_reasons') or [])}"
        )
        metadata = item.get("image_metadata") if isinstance(item.get("image_metadata"), dict) else {}
        if metadata.get("status") == "ok":
            lines.append(
                f"    image={metadata.get('width')}x{metadata.get('height')} "
                f"format={metadata.get('format') or ''}"
            )
        ocr = item.get("ocr") if isinstance(item.get("ocr"), dict) else {}
        if ocr:
            if ocr.get("text_path"):
                lines.append(f"    OCR text: `{ocr.get('text_path')}` status={ocr.get('status')}")
            if ocr.get("text_preview"):
                lines.append(f"    OCR preview: {collapse_context_text(ocr.get('text_preview'), max_len=360)}")
    if media.get("manifest_md") or media.get("manifest_json"):
        lines.append(f"  - Manifest: `{media.get('manifest_md') or media.get('manifest_json')}`")
    lines.append("  - For image-reading tasks, use the OCR text path/preview above first, then inspect the image file itself if more visual context is needed.")
    lines.append("  - Do not say the image/file is missing if one of these files exists and matches the requested source.")
    return "\n".join(lines) + "\n"


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", value.strip()).strip("-").lower()
    return slug[:96] or "task"


def choose_worker_policy(task: dict[str, Any]) -> dict[str, Any]:
    text = worker_policy_text(task).lower()
    routine_id = task_routine_id(task)
    routine_effort = task_routine_default_effort(task)
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
    if routine_id in {"research_summary", "story_script_generation"} and routine_effort:
        effort = routine_effort
    elif is_generate_video_task(task) and not bool(task_route_decision(task).get("public_publish_allowed")):
        effort = "medium"
    elif any(keyword in text for keyword in xhigh_keywords) or len(text) > 5000:
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


def task_routine_id(task: dict[str, Any]) -> str:
    routine = task.get("routine")
    if isinstance(routine, dict):
        return str(routine.get("id") or "")
    return ""


def task_routine_default_effort(task: dict[str, Any]) -> str:
    routine = task.get("routine")
    if isinstance(routine, dict):
        return normalize_effort(str(routine.get("default_effort") or ""), fallback="")
    return ""


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


def escalated_policy(policy: dict[str, Any], result: str, *, task: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if task is not None and is_generate_video_task(task) and generated_video_result_has_progress(result):
        return None
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


def generated_video_result_has_progress(result: str) -> bool:
    text = str(result or "").lower()
    markers = [
        ".mp4",
        ".mov",
        ".webm",
        "submitted",
        "queued",
        "running",
        "generating",
        "blocked",
        "waiting",
        "in progress",
        "已提交",
        "排队",
        "生成中",
        "等待",
        "阻塞",
        "卡住",
    ]
    return any(marker in text for marker in markers)


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
            files = [] if json_payload_is_file_intake_receipt(data) else file_entries_from_json(data)
            return {"message": message, "confirmation": confirmation, "files": files, "raw": text, "data": data}
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


def json_payload_is_file_intake_receipt(data: dict[str, Any]) -> bool:
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    return isinstance(nested.get("file_intake"), dict) and nested.get("require_file_delivery") is False


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
    raw_files = result.get("files") or []
    if not isinstance(raw_files, list):
        raw_files = [raw_files]
    auto_files = [] if suppress_auto_artifact_extraction(result) else extract_artifact_paths(raw_text)
    candidates = unique_strings([*raw_files, *auto_files])
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


def suppress_auto_artifact_extraction(result: dict[str, Any]) -> bool:
    data = result_delivery_data(result)
    if not isinstance(data.get("file_intake"), dict):
        return False
    return data.get("require_file_delivery") is False


def result_is_file_intake_receipt(result: dict[str, Any]) -> bool:
    data = result_delivery_data(result)
    return isinstance(data.get("file_intake"), dict) and data.get("require_file_delivery") is False


def result_delivery_data(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    if "file_intake" in nested or "require_file_delivery" in nested:
        return nested
    return data


def extract_artifact_paths(text: str) -> list[str]:
    candidates: list[str] = []
    scan_text = re.sub(r"https?://\S+", " ", str(text or ""))
    absolute = r"(?<![:/])/[A-Za-z0-9_./:@%+=,\-]+"
    relative = r"(?:output|cad|pcb|publications|references|examples)/[A-Za-z0-9_./:@%+=,\-]+"
    for match in re.finditer(f"(?:{absolute}|{relative})", scan_text):
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


def gui_search_allowed_for_target(target: dict[str, Any]) -> bool:
    return bool(target.get("allow_search", False))


def send_message(message: str, chat: str, send_targets: Path, *, target: dict[str, Any] | None = None) -> None:
    target = target if target is not None else guarded_send_target(chat, send_targets)
    if target:
        command = [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
            "--targets-file",
            "",
            "--send",
            "--prefer-current",
            "--pause",
            os.environ.get("WECHAT_WORKER_SEND_PAUSE", "0.35"),
            "--mirror-db",
            str(DEFAULT_DB),
        ]
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": message, "targets": [target]}, handle, ensure_ascii=False)
        command[command.index("--targets-file") + 1] = str(target_file)
        if gui_search_allowed_for_target(target):
            command.append("--allow-search")
        else:
            command.append("--no-search")
        try:
            run_send_subprocess(command)
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
        command = [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
            "--targets-file",
            "",
            "--prefer-current",
            "--pause",
            os.environ.get("WECHAT_WORKER_SEND_PAUSE", "0.35"),
        ]
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": "", "targets": [target]}, handle, ensure_ascii=False)
        command[command.index("--targets-file") + 1] = str(target_file)
        if gui_search_allowed_for_target(target):
            command.append("--allow-search")
        else:
            command.append("--no-search")
        try:
            run_send_subprocess(command)
        finally:
            target_file.unlink(missing_ok=True)
    elif os.environ.get("WECHAT_ALLOW_UNGUARDED_SEND", "0") != "1":
        raise RuntimeError(f"Refusing unguarded WeChat file send for {chat}: missing send_target")
    run_file_bridge_subprocess(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            os.environ.get("WECHAT_WORKER_FILE_SEND_CONFIG", str(PRIVATE / "lazy-research-chatops.local.json")),
            "--chat",
            chat,
            "--file",
            str(file_path.expanduser().resolve()),
        ]
    )


def run_subprocess_group(command: list[str], *, timeout: int, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(command, exc.timeout, output=stdout, stderr=stderr) from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def run_send_subprocess(command: list[str], timeout: int | None = None) -> None:
    if gui_send_lock_busy():
        raise RuntimeError("WECHAT_SEND_BUSY: serialized GUI sender is already sending; defer this worker reply.")
    if timeout is None:
        timeout = int(os.environ.get("WECHAT_WORKER_SEND_TIMEOUT_SECONDS", "120"))
    try:
        proc = run_subprocess_group(command, timeout=timeout, env=wechat_send_env())
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"WECHAT_SEND_TIMEOUT: GUI sender timed out after {exc.timeout} seconds; defer this worker reply."
        ) from exc
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


def run_file_bridge_subprocess(command: list[str], timeout: int | None = None) -> None:
    if timeout is None:
        timeout = int(
            os.environ.get(
                "WECHAT_WORKER_FILE_SEND_TIMEOUT_SECONDS",
                os.environ.get("WECHAT_WORKER_SEND_TIMEOUT_SECONDS", "120"),
            )
        )
    attempts = max(1, int(os.environ.get("WECHAT_WORKER_FILE_SEND_UNLOCK_RETRIES", "2")) + 1)
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        proc = run_file_bridge_attempt(command, timeout=timeout)
        if proc.returncode == 0:
            return
        message = file_bridge_failure_message(proc)
        errors.append(f"attempt {attempt}: {message}")
        if attempt < attempts and file_bridge_indicates_wechat_locked(proc) and os.environ.get("WECHAT_WORKER_FILE_SEND_AUTO_UNLOCK", "1") != "0":
            unlock_error = unlock_wechat_for_file_send()
            if unlock_error:
                errors.append(f"unlock attempt {attempt}: {unlock_error}")
            time.sleep(float(os.environ.get("WECHAT_WORKER_FILE_SEND_UNLOCK_RETRY_DELAY", "1.0")))
            continue
        break
    raise RuntimeError("; ".join(errors[-4:]))


def run_file_bridge_attempt(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    lock = acquire_gui_send_lock_or_raise()
    try:
        try:
            return run_subprocess_group(command, timeout=timeout, env=wechat_send_env())
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"WECHAT_SEND_TIMEOUT: file bridge timed out after {exc.timeout} seconds; defer this worker reply."
            ) from exc
    finally:
        release_gui_send_lock(lock)


def file_bridge_failure_message(proc: subprocess.CompletedProcess[str]) -> str:
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parts = [f"file bridge failed with exit {proc.returncode}"]
    if stdout:
        parts.append(f"stdout={stdout[-1200:]}")
    if stderr:
        parts.append(f"stderr={stderr[-1200:]}")
    return "; ".join(parts)


def file_bridge_indicates_wechat_locked(proc: subprocess.CompletedProcess[str]) -> bool:
    text = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
    return "wechat_locked" in text or "weixin for linux is locked" in text or "状态栏解锁" in text


def unlock_wechat_for_file_send() -> str:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'src'}:{env.get('PYTHONPATH', '')}"
    timeout = int(os.environ.get("WECHAT_WORKER_FILE_SEND_UNLOCK_TIMEOUT_SECONDS", "60"))
    command = [
        sys.executable,
        "-m",
        "agenticapp",
        "wechat",
        "unlock-watchdog",
        "once",
        "--flush-deferred",
        "--json",
    ]
    try:
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return f"unlock watchdog timed out after {exc.timeout}s"
    if proc.returncode == 0:
        return ""
    detail = (proc.stderr or proc.stdout or "").strip()
    return detail[-1200:] or f"unlock watchdog failed with exit {proc.returncode}"


def gui_send_lock_busy(lock_path: Path = GUI_SEND_LOCK) -> bool:
    reap_stale_orphaned_gui_senders()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        acquired = False
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            return True
        finally:
            if acquired:
                try:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                except OSError:
                    pass
    return False


def acquire_gui_send_lock_or_raise(lock_path: Path = GUI_SEND_LOCK):
    reap_stale_orphaned_gui_senders()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open("a", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise RuntimeError("WECHAT_SEND_BUSY: serialized GUI sender is already sending; defer this worker reply.") from exc
    return lock


def release_gui_send_lock(lock) -> None:
    try:
        fcntl.flock(lock, fcntl.LOCK_UN)
    finally:
        lock.close()


def reap_stale_orphaned_gui_senders() -> None:
    """Kill orphaned GUI send helpers that can hold the fcntl send lane forever."""
    if os.environ.get("WECHAT_WORKER_DISABLE_STALE_SEND_REAPER") == "1":
        return
    max_age = int(os.environ.get("WECHAT_WORKER_STALE_GUI_SEND_SECONDS", "180"))
    orphan_max_age = int(os.environ.get("WECHAT_WORKER_ORPHAN_GUI_SEND_SECONDS", "15"))
    if max_age <= 0 and orphan_max_age <= 0:
        return
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return
    for raw_pid in proc.stdout.split():
        try:
            pid = int(raw_pid)
        except ValueError:
            continue
        if pid <= 0 or pid == os.getpid():
            continue
        try:
            stat_proc = subprocess.run(
                ["ps", "-o", "ppid=,etimes=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        parts = stat_proc.stdout.split()
        if len(parts) < 2:
            continue
        try:
            ppid = int(parts[0])
            age = int(parts[1])
        except ValueError:
            continue
        age_limit = orphan_max_age if ppid == 1 else max_age
        if age_limit <= 0 or age < age_limit:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except OSError:
            continue


def wechat_send_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("WECHAT_INITIAL_TITLE_WAIT", os.environ.get("WECHAT_WORKER_INITIAL_TITLE_WAIT", "0.8"))
    env.setdefault("WECHAT_TITLE_RETRY_SECONDS", os.environ.get("WECHAT_WORKER_TITLE_RETRY_SECONDS", "8.0"))
    worker_timeout = int(os.environ.get("WECHAT_WORKER_SEND_TIMEOUT_SECONDS", "120"))
    gui_timeout = os.environ.get("WECHAT_WORKER_GUI_SEND_MAX_SECONDS", str(max(45, worker_timeout - 5)))
    env.setdefault("WECHAT_GUI_SEND_MAX_SECONDS", gui_timeout)
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
        return {**direct_target, **registry_target}
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
