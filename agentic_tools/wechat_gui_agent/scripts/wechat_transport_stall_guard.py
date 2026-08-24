#!/usr/bin/env python3
"""Observe and safely repair LabCanvas WeChat/WeCom transport liveness.

The guard never reads chat text and never restarts a healthy client. Repairs are
limited to missing/dead tmux workers and a failed Android relay endpoint after
the same fault has been observed repeatedly.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from wechat_agent_backend import run_agent_session, select_agent_backend  # noqa: E402

WECHAT_PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
WECOM_PRIVATE = ROOT / "agentic_tools" / "wecom_agent" / ".private"
SEND_LOCK = WECHAT_PRIVATE / "wechat_gui_send.lock"
WECHAT_QUEUE = WECHAT_PRIVATE / "wechat_task_queue.jsonl"
WECOM_QUEUE = WECOM_PRIVATE / "wecom_task_queue.jsonl"
MODEL_POLICY_PATH = ROOT / "configs" / "model-policy.json"
WECHAT_ORGANIZER_DELIVERY = (
    WECHAT_PRIVATE / "output" / "career_daily" / "organizer-delivery.json"
)
WECHAT_CAREER_SCHEDULE_STATE = (
    WECHAT_PRIVATE / "output" / "career_daily" / "scheduler-state.json"
)
WECHAT_SUPERVISOR = (
    ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_supervisor_tmux.sh"
)
WECHAT_VIRTUAL_DESKTOP = (
    ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_virtual_desktop.sh"
)
WECHAT_GUI_SEND = (
    ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"
)
WECOM_SUPERVISOR = ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_tmux.sh"
ANDROID_CONFIG = WECOM_PRIVATE / "wecom_android_bridge.local.json"
GUI_CONFIG = WECOM_PRIVATE / "wecom_gui_bridge.local.json"
CLI_CONFIG = WECOM_PRIVATE / "wecom_cli_bridge.local.json"
CLI_TRANSPORT_STATE = WECOM_PRIVATE / "wecom_cli_transport.local.json"
ECHOMIND_SCHEDULE_STATE = WECHAT_PRIVATE / "echomind-language-schedule.state.json"
LABAGENT_SCHEDULE_HEARTBEAT = WECOM_PRIVATE / "wecom_daily_research.health.json"
ECHOMIND_SCHEDULE_HELPER = (
    ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / "scripts"
    / "echomind_language_scheduler_tmux.sh"
)
WECHAT_STACK = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_stack_tmux.sh"
ECHOMIND_SCHEDULE_SESSION = "labcanvas-echomind-language"
CAREER_SCHEDULE_SESSION = "labcanvas-career-daily"
ECHOMIND_INTERVAL_SECONDS = 6 * 60 * 60
ECHOMIND_HEARTBEAT_STALE_SECONDS = 12 * 60
ECHOMIND_PENDING_DELIVERY_GRACE_SECONDS = 10 * 60
ECHOMIND_DAILY_PDF_RETRY_SECONDS = 30 * 60
CAREER_HEARTBEAT_STALE_SECONDS = 30 * 60
TERMINAL_FAILURE_STATUSES = {"failed", "worker_failed"}
QUOTA_FAILURE_MARKERS = (
    "billing hard limit",
    "credits exhausted",
    "insufficient_quota",
    "model quota",
    "out of quota",
    "quota exceeded",
    "rate limit",
    "rate_limit",
    "resource_exhausted",
    "too many requests",
    "usage limit",
)
ALERTABLE_DEGRADED_CODES = {
    "android_poll_stalled",
    "schedule_career_delivery_overdue",
    "schedule_career_missing",
    "schedule_career_stalled",
    "schedule_memo_delivery_overdue",
    "schedule_echomind_cadence",
    "schedule_echomind_daily_delivery_pending",
    "schedule_echomind_lesson_delivery_pending",
    "schedule_echomind_missing",
    "schedule_echomind_stalled",
    "schedule_labagent_stalled",
    "wechat_direct_monitor_stalled",
}

ACTIVE_STATUSES = {
    "claimed",
    "download_pending",
    "generating",
    "generation_submitted",
    "in_progress",
    "pending",
    "processing",
    "publishing",
    "send_retrying",
}
IN_PROGRESS_STATUSES = ACTIVE_STATUSES - {"pending"}
REPAIR_AGENT_MODEL = "gpt-5.6-sol"
REPAIR_AGENT_ROLE = "transport_stall_repair"
REPAIR_AGENT_CHAT = "LabCanvas transport health"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def run_command(command: list[str], *, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    item
                    for item in (str(ROOT / "src"), os.environ.get("PYTHONPATH", ""))
                    if item
                ),
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 124, "", f"{type(exc).__name__}: {exc}")


def processes(pattern: str) -> list[int]:
    proc = run_command(["pgrep", "-f", pattern], timeout=3)
    return [
        int(value)
        for value in proc.stdout.split()
        if value.isdigit() and int(value) != os.getpid()
    ]


def process_details(pid: int) -> dict[str, int] | None:
    proc = run_command(["ps", "-o", "ppid=,etimes=", "-p", str(pid)], timeout=3)
    parts = proc.stdout.split()
    if len(parts) < 2:
        return None
    try:
        return {"pid": pid, "ppid": int(parts[0]), "elapsed_seconds": int(parts[1])}
    except ValueError:
        return None


def lock_is_held(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        acquired = False
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
            return False
        except BlockingIOError:
            return True
        finally:
            if acquired:
                fcntl.flock(handle, fcntl.LOCK_UN)


def sender_lock_health(
    path: Path = SEND_LOCK,
    *,
    max_holder_seconds: float = 180.0,
    repair_orphans: bool = False,
) -> dict[str, Any]:
    """Inspect the real advisory lock; file mtime alone is not lock state."""

    if not path.exists():
        return {"ok": True, "state": "absent", "held": False, "holders": []}
    held = lock_is_held(path)
    holder_pids = sorted(
        set(processes(r"[w]echat_gui_send\.py") + processes(r"[s]hipinhao_gui_audio_capture\.py"))
    )
    holders = [item for pid in holder_pids if (item := process_details(pid)) is not None]
    stale_orphans = [
        item
        for item in holders
        if item["elapsed_seconds"] >= max_holder_seconds
        and (item["ppid"] <= 1 or not Path(f"/proc/{item['ppid']}").exists())
    ]
    terminated: list[int] = []
    if held and repair_orphans:
        for item in stale_orphans:
            try:
                os.kill(item["pid"], signal.SIGTERM)
                terminated.append(item["pid"])
            except ProcessLookupError:
                continue
    stale = bool(held and holders and all(item["elapsed_seconds"] >= max_holder_seconds for item in holders))
    unknown_holder = bool(held and not holders)
    return {
        "ok": not stale and not unknown_holder,
        "state": "free" if not held else ("stale" if stale else "active"),
        "held": held,
        "holders": holders,
        "stale_orphan_count": len(stale_orphans),
        "terminated_orphans": terminated,
        "unknown_holder": unknown_holder,
    }


def tmux_snapshot(session: str) -> dict[str, Any]:
    proc = run_command(
        [
            "tmux",
            "list-panes",
            "-a",
            "-F",
            "#{session_name}\t#{window_name}\t#{pane_dead}\t#{pane_pid}\t#{pane_current_command}",
        ],
        timeout=5,
    )
    if proc.returncode != 0:
        return {"running": False, "windows": {}}
    windows: dict[str, dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        fields = line.split("\t", 4)
        if len(fields) != 5 or fields[0] != session:
            continue
        _, name, dead, pid, command = fields
        entry = windows.setdefault(name, {"live_panes": 0, "dead_panes": 0, "commands": []})
        if dead == "1":
            entry["dead_panes"] += 1
        else:
            entry["live_panes"] += 1
        entry["commands"].append(command)
        if pid.isdigit():
            entry.setdefault("pids", []).append(int(pid))
    return {"running": True, "windows": windows}


def window_live(snapshot: dict[str, Any], name: str) -> bool:
    return bool((snapshot.get("windows", {}).get(name) or {}).get("live_panes"))


def config_enabled(path: Path, *, default: bool = False) -> bool:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("enabled", True)) if isinstance(payload, dict) else False


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def cli_transport_health(
    config_path: Path = CLI_CONFIG,
    state_path: Path = CLI_TRANSPORT_STATE,
) -> dict[str, Any]:
    """Distinguish an unavailable optional CLI route from a failed required route."""

    enabled = config_enabled(config_path)
    state = read_json(state_path)
    state_name = str(state.get("state") or "")
    permission_unavailable = (
        state_name == "message_permission_unavailable"
        or state.get("msg_permission") is False
        and "暂不支持" in str(state.get("last_error") or "")
    )
    return {
        "enabled": enabled,
        "required": bool(enabled and not permission_unavailable),
        "state": state_name or ("configured" if enabled else "disabled"),
        "official_message_permission": not permission_unavailable,
    }


def expected_wechat_windows(snapshot: dict[str, Any]) -> tuple[list[str], list[str]]:
    windows = snapshot.get("windows", {})
    required = ["desktop", "media-sync"]
    if os.environ.get("WECHAT_CHAT_SYNC_WATCHDOG", "1") != "0":
        required.append("chat-sync")
    missing = [name for name in required if not window_live(snapshot, name)]
    if not any(name == "worker" or name.startswith("worker-") for name in windows):
        missing.append("worker*")
    if not any(name.startswith("direct-") for name in windows):
        missing.append("direct-*")
    return required, sorted(set(missing))


def expected_wecom_windows(snapshot: dict[str, Any]) -> tuple[list[str], list[str]]:
    required = ["gateway", "worker", "daily", "knowledge", "health"]
    if config_enabled(ANDROID_CONFIG):
        required.append("android-relay")
    if config_enabled(GUI_CONFIG):
        required.extend(["wecom-client", "external-gui"])
    if cli_transport_health()["required"]:
        required.append("external")
    missing = [name for name in required if not window_live(snapshot, name)]
    return required, missing


def probe_json_url(url: str, *, timeout: float = 4.0, attempts: int = 2) -> dict[str, Any]:
    payload: Any = None
    last_error = "unavailable"
    for attempt in range(max(1, attempts)):
        try:
            with request.urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            break
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
            if attempt + 1 < max(1, attempts):
                time.sleep(0.2)
    else:
        return {"ok": False, "endpoint_reachable": False, "error": last_error}
    if not isinstance(payload, dict):
        return {"ok": False, "endpoint_reachable": True, "error": "invalid_payload"}
    return {
        "ok": bool(payload.get("ok")),
        "endpoint_reachable": True,
        "device_authorized": bool(payload.get("device_authorized")),
        "wecom_foreground": bool(payload.get("wecom_foreground")),
        "transport": str(payload.get("transport") or ""),
        "surface_state": str(payload.get("surface_state") or ""),
        "poll_healthy": bool(payload.get("poll_healthy", payload.get("ok"))),
        "poll_stale": bool(payload.get("poll_stale")),
        "poll_in_progress": bool(payload.get("poll_in_progress")),
        "consecutive_poll_failures": int(payload.get("consecutive_poll_failures") or 0),
        "blocked_media_recoveries": int(payload.get("blocked_media_recoveries") or 0),
        "last_poll_success_at": str(payload.get("last_poll_success_at") or ""),
        "last_poll_error": str(payload.get("last_poll_error") or "")[:300],
        "last_recovery_at": str(payload.get("last_recovery_at") or ""),
        "last_recovery_action": str(payload.get("last_recovery_action") or "")[:160],
        "authentication_reason": str(payload.get("authentication_reason") or "")[:200],
        "device_storage": (
            payload.get("device_storage")
            if isinstance(payload.get("device_storage"), dict)
            else {}
        ),
    }


def parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.astimezone(timezone.utc)


def resolve_private_path(value: object, *, fallback: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return fallback
    path = Path(text).expanduser()
    return path if path.is_absolute() else ROOT / path


def direct_monitor_health(
    *,
    private_dir: Path = WECHAT_PRIVATE,
    now: datetime | None = None,
    minimum_stale_seconds: float = 30.0,
    poll_multiplier: float = 30.0,
    processing_stale_seconds: float = 900.0,
) -> dict[str, Any]:
    """Check process heartbeats without treating an inactive chat as stale."""

    current = now or utc_now()
    configs = sorted(private_dir.glob("*direct-chatops.local.json"))
    monitors: list[dict[str, Any]] = []
    for config_path in configs:
        config = read_json(config_path)
        if config.get("enabled") is False:
            continue
        try:
            poll_seconds = max(0.1, float(config.get("poll_seconds") or 0.8))
        except (TypeError, ValueError):
            poll_seconds = 0.8
        threshold = max(minimum_stale_seconds, poll_seconds * poll_multiplier)
        state_path = resolve_private_path(
            config.get("state_path"),
            fallback=config_path.with_name(config_path.name.replace(".local.json", ".state.json")),
        )
        state = read_json(state_path)
        heartbeat = parse_timestamp(state.get("last_loop_at"))
        age = max(0.0, (current - heartbeat).total_seconds()) if heartbeat else None
        inflight = [item for item in state.get("inflight_local_ids") or [] if str(item).isdigit()]
        processing_started = parse_timestamp(state.get("inflight_started_at"))
        processing_age = (
            max(0.0, (current - processing_started).total_seconds())
            if processing_started
            else None
        )
        processing = bool(inflight)
        within_processing_deadline = (
            processing
            and processing_age is not None
            and processing_age <= processing_stale_seconds
        )
        healthy = (
            heartbeat is not None
            and age is not None
            and (age <= threshold or within_processing_deadline)
        )
        monitors.append(
            {
                "config": config_path.name,
                "ok": healthy,
                "state": "processing" if within_processing_deadline else "polling",
                "heartbeat_age_seconds": int(age) if age is not None else None,
                "stale_after_seconds": int(threshold),
                "inflight_count": len(inflight),
                "processing_age_seconds": int(processing_age) if processing_age is not None else None,
                "processing_stale_after_seconds": int(processing_stale_seconds),
            }
        )
    stale = [item["config"] for item in monitors if not item["ok"]]
    return {
        "ok": bool(monitors) and not stale,
        "configured": len(monitors),
        "healthy": sum(1 for item in monitors if item["ok"]),
        "stale_configs": stale,
        "monitors": monitors,
    }


def tmux_session_live(name: str) -> bool:
    return run_command(["tmux", "has-session", "-t", name], timeout=3).returncode == 0


def schedule_health(
    *,
    labagent_heartbeat: Path = LABAGENT_SCHEDULE_HEARTBEAT,
    career_state_path: Path = WECHAT_CAREER_SCHEDULE_STATE,
    now: datetime | None = None,
    labagent_stale_seconds: float = 120.0,
    career_stale_seconds: float = CAREER_HEARTBEAT_STALE_SECONDS,
) -> dict[str, Any]:
    echo_state = read_json(ECHOMIND_SCHEDULE_STATE)
    career_state = read_json(career_state_path)
    try:
        interval = int(echo_state.get("interval_seconds") or 0)
    except (TypeError, ValueError):
        interval = 0
    echomind_running = tmux_session_live(
        os.environ.get("ECHOMIND_LANGUAGE_TMUX_SESSION", ECHOMIND_SCHEDULE_SESSION)
    )
    career_running = tmux_session_live(
        os.environ.get("WECHAT_CAREER_SESSION", CAREER_SCHEDULE_SESSION)
    )
    heartbeat = read_json(labagent_heartbeat)
    heartbeat_at = parse_timestamp(heartbeat.get("checked_at"))
    current = now or utc_now()
    echo_heartbeat = parse_timestamp(echo_state.get("last_loop_at"))
    career_heartbeat = parse_timestamp(career_state.get("last_loop_at"))
    echo_heartbeat_age = (
        max(0.0, (current - echo_heartbeat).total_seconds())
        if echo_heartbeat
        else None
    )
    echomind_heartbeat_ok = (
        echo_heartbeat_age is not None
        and echo_heartbeat_age <= ECHOMIND_HEARTBEAT_STALE_SECONDS
    )
    pending_lesson = echo_state.get("pending_lesson")
    echomind_pending_lesson = bool(pending_lesson)
    pending_lesson_generated_at = parse_timestamp(
        pending_lesson.get("generated_at")
        if isinstance(pending_lesson, dict)
        else ""
    )
    pending_lesson_age = (
        max(0.0, (current - pending_lesson_generated_at).total_seconds())
        if pending_lesson_generated_at
        else None
    )
    echomind_phase = str(echo_state.get("scheduler_phase") or "unknown")
    pending_lesson_in_progress = bool(
        echomind_pending_lesson
        and echomind_phase == "lesson_delivery_attempt"
        and echomind_heartbeat_ok
    )
    pending_lesson_quiet_hours_deferred = bool(
        echomind_pending_lesson and echomind_phase == "quiet_hours"
    )
    pending_lesson_retry_at = parse_timestamp(
        pending_lesson.get("next_attempt_at")
        if isinstance(pending_lesson, dict)
        else ""
    )
    pending_lesson_retry_pending = bool(
        pending_lesson_retry_at and pending_lesson_retry_at > current
    )
    pending_lesson_actionable = bool(
        echomind_pending_lesson
        and not pending_lesson_in_progress
        and not pending_lesson_quiet_hours_deferred
        and not pending_lesson_retry_pending
        and (
            pending_lesson_age is None
            or pending_lesson_age > ECHOMIND_PENDING_DELIVERY_GRACE_SECONDS
        )
    )
    pending_daily_pdf = echo_state.get("pending_daily_pdf")
    echomind_pending_daily_pdf = bool(pending_daily_pdf)
    pending_daily_generated_at = parse_timestamp(
        pending_daily_pdf.get("generated_at")
        if isinstance(pending_daily_pdf, dict)
        else ""
    )
    pending_daily_pdf_age = (
        max(0.0, (current - pending_daily_generated_at).total_seconds())
        if pending_daily_generated_at
        else None
    )
    pending_daily_attempt_at = parse_timestamp(
        echo_state.get("last_daily_pdf_attempt_at")
    )
    pending_daily_retry_at = (
        pending_daily_attempt_at
        + timedelta(seconds=ECHOMIND_DAILY_PDF_RETRY_SECONDS)
        if pending_daily_attempt_at
        and isinstance(pending_daily_pdf, dict)
        and str(echo_state.get("last_daily_pdf_attempt_date") or "")
        == str(pending_daily_pdf.get("date") or "")
        else None
    )
    pending_daily_retry_pending = bool(
        pending_daily_retry_at and pending_daily_retry_at > current
    )
    pending_daily_pdf_actionable = bool(
        echomind_pending_daily_pdf
        and not pending_daily_retry_pending
        and (
            pending_daily_pdf_age is None
            or pending_daily_pdf_age > ECHOMIND_PENDING_DELIVERY_GRACE_SECONDS
        )
    )
    echomind_delivery_pending = (
        pending_lesson_actionable or pending_daily_pdf_actionable
    )
    echomind_ok = (
        echomind_running
        and echomind_heartbeat_ok
        and not echomind_delivery_pending
    )
    career_heartbeat_age = (
        max(0.0, (current - career_heartbeat).total_seconds())
        if career_heartbeat
        else None
    )
    career_heartbeat_ok = (
        career_heartbeat_age is not None
        and career_heartbeat_age <= career_stale_seconds
    )
    career_phase = str(career_state.get("phase") or "missing")
    career_in_progress = career_phase == "career_running" and career_heartbeat_ok
    organizer_in_progress = (
        career_phase == "organizer_running" and career_heartbeat_ok
    )
    workflow_in_progress = career_in_progress or organizer_in_progress
    career_retry_at = parse_timestamp(career_state.get("career_next_attempt_at"))
    organizer_retry_at = parse_timestamp(
        career_state.get("organizer_next_attempt_at")
    )
    career_retry_pending = bool(career_retry_at and career_retry_at > current)
    organizer_retry_pending = bool(
        organizer_retry_at and organizer_retry_at > current
    )
    career_overdue = bool(
        career_state.get("career_overdue")
        and not career_retry_pending
        and not workflow_in_progress
    )
    organizer_overdue = bool(
        career_state.get("organizer_overdue")
        and not organizer_retry_pending
        and not workflow_in_progress
    )
    career_ok = (
        career_running
        and career_heartbeat_ok
        and not career_overdue
        and not organizer_overdue
    )
    heartbeat_age = (
        max(0.0, (current - heartbeat_at).total_seconds())
        if heartbeat_at
        else None
    )
    labagent_ok = heartbeat_age is not None and heartbeat_age <= labagent_stale_seconds
    return {
        "ok": (
            echomind_ok
            and career_ok
            and interval == ECHOMIND_INTERVAL_SECONDS
            and labagent_ok
        ),
        "echomind": {
            "running": echomind_running,
            "ok": echomind_ok,
            "interval_seconds": interval,
            "expected_interval_seconds": ECHOMIND_INTERVAL_SECONDS,
            "heartbeat_age_seconds": int(echo_heartbeat_age) if echo_heartbeat_age is not None else None,
            "stale_after_seconds": ECHOMIND_HEARTBEAT_STALE_SECONDS,
            "phase": echomind_phase,
            "pending_delivery": echomind_delivery_pending,
            "pending_lesson": echomind_pending_lesson,
            "pending_lesson_actionable": pending_lesson_actionable,
            "pending_lesson_in_progress": pending_lesson_in_progress,
            "pending_lesson_quiet_hours_deferred": (
                pending_lesson_quiet_hours_deferred
            ),
            "pending_lesson_retry_pending": pending_lesson_retry_pending,
            "pending_lesson_next_attempt_at": (
                str(pending_lesson.get("next_attempt_at") or "")
                if isinstance(pending_lesson, dict)
                else ""
            ),
            "pending_lesson_age_seconds": (
                int(pending_lesson_age)
                if pending_lesson_age is not None
                else None
            ),
            "pending_daily_pdf": echomind_pending_daily_pdf,
            "pending_daily_pdf_actionable": pending_daily_pdf_actionable,
            "pending_daily_pdf_retry_pending": pending_daily_retry_pending,
            "pending_daily_pdf_next_attempt_at": (
                pending_daily_retry_at.isoformat()
                if pending_daily_retry_at is not None
                else ""
            ),
            "pending_daily_pdf_age_seconds": (
                int(pending_daily_pdf_age)
                if pending_daily_pdf_age is not None
                else None
            ),
            "daily_pdf_error": str(echo_state.get("last_daily_pdf_error") or ""),
        },
        "career_daily": {
            "running": career_running,
            "ok": career_ok,
            "heartbeat_age_seconds": (
                int(career_heartbeat_age)
                if career_heartbeat_age is not None
                else None
            ),
            "stale_after_seconds": int(career_stale_seconds),
            "phase": career_phase,
            "date": str(career_state.get("date") or ""),
            "morning_time": str(career_state.get("morning_time") or ""),
            "career_complete": bool(career_state.get("career_complete")),
            "organizer_required": bool(career_state.get("organizer_required")),
            "organizer_complete": bool(career_state.get("organizer_complete")),
            "career_overdue": career_overdue,
            "organizer_overdue": organizer_overdue,
            "career_retry_pending": career_retry_pending,
            "organizer_retry_pending": organizer_retry_pending,
            "career_in_progress": career_in_progress,
            "organizer_in_progress": organizer_in_progress,
            "career_next_attempt_at": str(
                career_state.get("career_next_attempt_at") or ""
            ),
            "organizer_next_attempt_at": str(
                career_state.get("organizer_next_attempt_at") or ""
            ),
            "career_status": str(career_state.get("career_status") or ""),
            "organizer_status": str(career_state.get("organizer_status") or ""),
        },
        "labagent_idle_inspiration": {
            "ok": labagent_ok,
            "status": str(heartbeat.get("status") or "missing"),
            "heartbeat_age_seconds": int(heartbeat_age) if heartbeat_age is not None else None,
            "stale_after_seconds": int(labagent_stale_seconds),
        },
    }


def task_failure_text(task: dict[str, Any]) -> str:
    fragments: list[str] = []
    worker_error = task.get("worker_error")
    if isinstance(worker_error, dict):
        fragments.extend(str(worker_error.get(key) or "") for key in ("type", "message"))
    else:
        fragments.append(str(worker_error or ""))
    for key in ("worker_policy_attempts",):
        attempts = task.get(key)
        if isinstance(attempts, list):
            for attempt in attempts:
                if isinstance(attempt, dict):
                    fragments.extend(
                        str(attempt.get(field) or "")
                        for field in ("result_excerpt", "error", "failure_kind")
                    )
    session = task.get("agent_session")
    if isinstance(session, dict):
        attempts = session.get("backend_attempts")
        if isinstance(attempts, list):
            for attempt in attempts:
                if isinstance(attempt, dict):
                    fragments.extend(str(value or "") for value in attempt.values())
    return " ".join(fragments).lower()


def recent_terminal_agent_failures(
    paths: tuple[Path, ...] = (WECHAT_QUEUE, WECOM_QUEUE),
    *,
    now: datetime | None = None,
    window_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Report recent terminal quota failures only after all configured fallbacks failed."""

    current = now or utc_now()
    quota_failure_ids: list[str] = []
    terminal_failures = 0
    for path in paths:
        if not path.exists():
            continue
        latest: dict[str, dict[str, Any]] = {}
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                task = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id") or task.get("task_id") or "")
            if task_id:
                latest[task_id] = task
        for task_id, task in latest.items():
            if str(task.get("status") or "") not in TERMINAL_FAILURE_STATUSES:
                continue
            completed = parse_timestamp(
                task.get("completed_at") or task.get("updated_at") or task.get("created_at")
            )
            if completed is None or (current - completed).total_seconds() > window_seconds:
                continue
            terminal_failures += 1
            if task.get("worker_result_exhausted") is not True:
                continue
            text = task_failure_text(task)
            if any(marker in text for marker in QUOTA_FAILURE_MARKERS):
                quota_failure_ids.append(task_id)
    return {
        "ok": not quota_failure_ids,
        "window_seconds": int(window_seconds),
        "terminal_failures": terminal_failures,
        "quota_failure_count": len(quota_failure_ids),
        "quota_failure_ids": quota_failure_ids[:20],
    }


def queue_health(
    path: Path,
    *,
    now: datetime | None = None,
    stale_active_seconds: float = 14_400.0,
    stale_pending_seconds: float = 14_400.0,
    coverage_alert_seconds: float = 21_600.0,
    failure_alert_seconds: float = 21_600.0,
) -> dict[str, Any]:
    if not path.exists():
        return {"ok": True, "exists": False, "active": 0, "pending": 0, "stale_ids": []}
    latest: dict[str, dict[str, Any]] = {}
    invalid_lines = 0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"ok": False, "exists": True, "error": "unreadable"}
    for line in lines:
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(task, dict):
            invalid_lines += 1
            continue
        task_id = str(task.get("id") or task.get("task_id") or "")
        if task_id:
            latest[task_id] = task
    now = now or utc_now()
    active: list[dict[str, Any]] = []
    stale_ids: list[str] = []
    coverage_unresolved_ids: list[str] = []
    historical_coverage_unresolved_ids: list[str] = []
    historical_coverage_categories: dict[str, int] = {}
    recent_failed_ids: list[str] = []
    superseded_failed_ids: list[str] = []
    delivered_inspiration_at: dict[str, datetime] = {}
    for task_id, task in latest.items():
        if not delivered_proactive_inspiration(task_id, task):
            continue
        scope = proactive_inspiration_scope(task)
        delivered_at = parse_timestamp(
            task.get("completed_at")
            or task.get("updated_at")
            or task.get("created_at")
        )
        if not scope or delivered_at is None:
            continue
        previous = delivered_inspiration_at.get(scope)
        if previous is None or delivered_at > previous:
            delivered_inspiration_at[scope] = delivered_at
    for task_id, task in latest.items():
        status = str(task.get("status") or "")
        delivered_proactive = delivered_proactive_inspiration(task_id, task)
        failed_at = parse_timestamp(
            task.get("completed_at")
            or task.get("updated_at")
            or task.get("created_at")
        )
        inspiration_scope = proactive_inspiration_scope(task)
        later_inspiration = delivered_inspiration_at.get(inspiration_scope)
        superseded_proactive = bool(
            status in {"worker_failed", "failed", "error"}
            and inspiration_scope
            and failed_at is not None
            and later_inspiration is not None
            and later_inspiration > failed_at
        )
        if superseded_proactive:
            superseded_failed_ids.append(task_id)
        if status in {"worker_failed", "failed", "error"} and not delivered_proactive:
            failed_age = (
                max(0.0, (now - failed_at).total_seconds())
                if failed_at is not None
                else 0.0
            )
            if not superseded_proactive and (
                failed_at is None or failed_age < failure_alert_seconds
            ):
                recent_failed_ids.append(task_id)
        if (
            str(task.get("coverage_status") or "") == "unresolved_after_retry"
            and not delivered_proactive
            and not superseded_proactive
        ):
            completed = parse_timestamp(
                task.get("completed_at")
                or task.get("updated_at")
                or task.get("created_at")
            )
            coverage_age = (
                max(0.0, (now - completed).total_seconds())
                if completed is not None
                else 0.0
            )
            if (
                status in ACTIVE_STATUSES
                or completed is None
                or coverage_age < coverage_alert_seconds
            ):
                coverage_unresolved_ids.append(task_id)
            else:
                historical_coverage_unresolved_ids.append(task_id)
                category = historical_coverage_category(task)
                historical_coverage_categories[category] = (
                    historical_coverage_categories.get(category, 0) + 1
                )
        if status not in ACTIVE_STATUSES:
            continue
        started = parse_timestamp(
            task.get("claimed_at")
            or task.get("started_at")
            or task.get("updated_at")
            or task.get("created_at")
        )
        age = max(0.0, (now - started).total_seconds()) if started else 0.0
        active.append({"id": task_id, "status": status, "age_seconds": int(age)})
        threshold = stale_pending_seconds if status == "pending" else stale_active_seconds
        if started and age >= threshold:
            stale_ids.append(task_id)
    return {
        "ok": not stale_ids and not coverage_unresolved_ids and not recent_failed_ids and invalid_lines == 0,
        "exists": True,
        "task_count": len(latest),
        "active": len(active),
        "pending": sum(1 for item in active if item["status"] == "pending"),
        "in_progress": sum(1 for item in active if item["status"] in IN_PROGRESS_STATUSES),
        "oldest_active_seconds": max((item["age_seconds"] for item in active), default=0),
        "stale_ids": stale_ids[:20],
        "coverage_unresolved_ids": coverage_unresolved_ids[:20],
        "recent_failed_ids": recent_failed_ids[:20],
        "superseded_failed_ids": superseded_failed_ids[:20],
        "historical_coverage_unresolved_count": len(
            historical_coverage_unresolved_ids
        ),
        "historical_coverage_unresolved_ids": historical_coverage_unresolved_ids[:20],
        "historical_coverage_categories": dict(
            sorted(historical_coverage_categories.items())
        ),
        "invalid_lines": invalid_lines,
    }


def delivered_proactive_inspiration(task_id: str, task: dict[str, Any]) -> bool:
    """Return true only for a fully delivered proactive inspiration task."""
    if not task_id.startswith("wecom-inspiration-"):
        return False
    if not isinstance(task.get("group_inspiration"), dict):
        return False
    delivery = task.get("wecom_delivery")
    if not isinstance(delivery, dict):
        return False
    sent_messages = delivery.get("sent_messages")
    pending_messages = delivery.get("pending_messages")
    return (
        str(delivery.get("status") or "").strip().casefold() == "sent"
        and isinstance(sent_messages, list)
        and bool(sent_messages)
        and (pending_messages is None or pending_messages == [])
    )


def proactive_inspiration_scope(task: dict[str, Any]) -> str:
    """Return the exact-chat scope for one optional scheduled inspiration."""

    if not isinstance(task.get("group_inspiration"), dict):
        return ""
    source = task.get("source") if isinstance(task.get("source"), dict) else {}
    return str(task.get("chat") or source.get("chat") or "").strip()


def historical_coverage_category(task: dict[str, Any]) -> str:
    status = str(task.get("status") or "").strip().casefold()
    if status in {"worker_failed", "failed", "error"}:
        return "worker_failed"
    if status in {
        "send_expired",
        "send_failed",
        "send_deferred_expired",
        "delivery_expired",
    }:
        return "delivery_expired"
    delivery = (
        task.get("wecom_delivery")
        if isinstance(task.get("wecom_delivery"), dict)
        else {}
    )
    if status == "done" or str(delivery.get("status") or "").casefold() == "sent":
        return "delivered_unverified"
    return "terminal_unverified"


def wechat_client_started_at(
    *,
    display: str | None = None,
    now: datetime | None = None,
) -> datetime | None:
    """Return the start time of the persisted WeChat client on one X display."""

    expected_display = display or os.environ.get("WECHAT_DISPLAY", ":97")
    current = now or utc_now()
    proc = run_command(["pgrep", "-f", r"^/usr/bin/wechat([[:space:]]|$)"], timeout=3)
    starts: list[datetime] = []
    for raw_pid in proc.stdout.split():
        if not raw_pid.isdigit():
            continue
        pid = int(raw_pid)
        try:
            environment = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if f"DISPLAY={expected_display}".encode() not in environment:
            continue
        details = process_details(pid)
        if details is None:
            continue
        starts.append(current - timedelta(seconds=details["elapsed_seconds"]))
    return min(starts) if starts else None


def recent_wechat_gui_timeout_health(
    path: Path = WECHAT_QUEUE,
    *,
    now: datetime | None = None,
    client_started_at: datetime | None = None,
    window_seconds: float = 900.0,
    scheduler_state_paths: tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    """Detect a completed GUI timeout against the currently running client.

    A timeout older than the current client process is resolved evidence and
    must not trigger another restart. One current timeout is enough to raise a
    health fault; the outer guard still requires repeated health checks before
    performing the profile-preserving restart.
    """

    current = now or utc_now()
    started = client_started_at
    if started is None:
        started = wechat_client_started_at(now=current)
    if scheduler_state_paths is None:
        scheduler_state_paths = (
            (WECHAT_ORGANIZER_DELIVERY,)
            if path == WECHAT_QUEUE
            else ()
        )
    queue_exists = path.exists()
    latest: dict[str, dict[str, Any]] = {}
    lines: list[str] = []
    if queue_exists:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return {
                "ok": False,
                "exists": True,
                "error": "unreadable",
                "client_started_at": started.isoformat(timespec="seconds") if started else "",
                "task_ids": [],
            }
    for line in lines:
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or task.get("task_id") or "")
        if task_id:
            latest[task_id] = task

    stalled: list[str] = []
    newest_timeout: datetime | None = None
    for task_id, task in latest.items():
        attempted = parse_timestamp(
            task.get("last_send_attempt_at")
            or task.get("send_retry_claimed_at")
            or task.get("completed_at")
        )
        if attempted is None or (current - attempted).total_seconds() > window_seconds:
            continue
        if started is not None and attempted <= started:
            continue
        fragments = [
            str(task.get("send_deferred_reason") or ""),
            *(str(item) for item in task.get("send_errors") or []),
        ]
        for item in task.get("file_send_errors") or []:
            if isinstance(item, dict):
                fragments.append(str(item.get("error") or ""))
            else:
                fragments.append(str(item))
        text = " ".join(fragments).lower()
        if "gui_send_timeout" not in text and "wechat_send_timeout" not in text:
            continue
        stalled.append(task_id)
        newest_timeout = max(newest_timeout, attempted) if newest_timeout else attempted
    for state_path in scheduler_state_paths:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(state, dict) or str(state.get("status") or "") != "delivery_failed":
            continue
        attempted = parse_timestamp(
            state.get("last_delivery_attempt_at")
            or state.get("updated_at")
        )
        if attempted is None or (current - attempted).total_seconds() > window_seconds:
            continue
        if started is not None and attempted <= started:
            continue
        send = state.get("send") if isinstance(state.get("send"), dict) else {}
        text = " ".join(str(item) for item in send.get("errors") or []).lower()
        if "gui_send_timeout" not in text and "wechat_send_timeout" not in text:
            continue
        stalled.append(f"scheduler:{state_path.stem}")
        newest_timeout = max(newest_timeout, attempted) if newest_timeout else attempted
    return {
        "ok": not stalled,
        "exists": queue_exists,
        "client_started_at": started.isoformat(timespec="seconds") if started else "",
        "newest_timeout_at": newest_timeout.isoformat(timespec="seconds") if newest_timeout else "",
        "task_ids": stalled[:20],
    }


def process_counts(wechat: dict[str, Any], wecom: dict[str, Any]) -> dict[str, int]:
    wechat_windows = wechat.get("windows", {})
    return {
        "wechat_direct_chatops": sum(
            1 for name in wechat_windows if name.startswith("direct-") and window_live(wechat, name)
        ),
        "wechat_worker": sum(
            1
            for name in wechat_windows
            if (name == "worker" or name.startswith("worker-")) and window_live(wechat, name)
        ),
        "wecom_worker": int(window_live(wecom, "worker")),
        "android_relay": int(window_live(wecom, "android-relay")),
    }


def agent_backend_runtime_status() -> dict[str, Any]:
    """Expose backend configuration drift without spending model tokens."""

    try:
        model_policy = json.loads(MODEL_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        model_policy = {}
    primary = str(model_policy.get("primary_backend") or "aginti").strip()
    configured_wecom = str(os.environ.get("WECOM_AGENT_BACKEND") or "").strip()
    configured_wechat = str(os.environ.get("WECHAT_AGENT_BACKEND") or "").strip()
    requested = configured_wecom or configured_wechat or primary
    forced = str(os.environ.get("WECHAT_AGENT_FORCE_BACKEND") or "").strip()
    effective = select_agent_backend({"agent_backend": requested})
    aginti_disabled = str(
        os.environ.get("WECHAT_AGENT_FORCE_DISABLE_AGINTI") or ""
    ).strip().casefold() in {"1", "true", "yes", "on"}
    return {
        "ok": not (effective == "aginti" and aginti_disabled),
        "primary_backend": primary,
        "requested_backend": requested,
        "effective_backend": effective,
        "override_active": bool(forced),
        "forced_backend": forced,
        "aginti_disabled": aginti_disabled,
    }


def build_snapshot(*, max_sender_seconds: float = 180.0) -> dict[str, Any]:
    wechat = tmux_snapshot(os.environ.get("WECHAT_SUPERVISOR_SESSION", "labcanvas-wechat"))
    wecom = tmux_snapshot(os.environ.get("WECOM_TMUX_SESSION", "labcanvas-wecom"))
    _, wechat_missing = expected_wechat_windows(wechat) if wechat["running"] else ([], ["session"])
    wecom_expected, wecom_missing = expected_wecom_windows(wecom) if wecom["running"] else ([], ["session"])
    android_expected = "android-relay" in wecom_expected or config_enabled(ANDROID_CONFIG)
    android = (
        probe_json_url("http://127.0.0.1:19581/health")
        if android_expected
        else {"ok": True, "enabled": False}
    )
    sender = sender_lock_health(max_holder_seconds=max_sender_seconds)
    gui_delivery = recent_wechat_gui_timeout_health()
    direct_monitors = direct_monitor_health()
    schedules = schedule_health()
    cli_transport = cli_transport_health()
    agent_failures = recent_terminal_agent_failures()
    agent_backend = agent_backend_runtime_status()
    queues = {
        "wechat": queue_health(WECHAT_QUEUE),
        "wecom": queue_health(WECOM_QUEUE),
    }
    issues: list[dict[str, str]] = []

    def issue(code: str, severity: str, detail: str) -> None:
        issues.append({"code": code, "severity": severity, "detail": detail})

    if not wechat["running"]:
        issue("wechat_session_missing", "critical", "WeChat tmux session is absent")
    elif wechat_missing:
        issue("wechat_windows_missing", "degraded", ",".join(wechat_missing))
    if not direct_monitors.get("ok"):
        issue(
            "wechat_direct_monitor_stalled",
            "critical",
            f"{len(direct_monitors.get('stale_configs') or [])} direct monitor heartbeat(s) stale",
        )
    if not wecom["running"]:
        issue("wecom_session_missing", "critical", "WeCom tmux session is absent")
    elif wecom_missing:
        issue("wecom_windows_missing", "degraded", ",".join(wecom_missing))
    if android_expected and not android.get("endpoint_reachable"):
        issue("android_endpoint_down", "degraded", "Android relay health endpoint is unavailable")
    elif android_expected and android_poll_failure_is_actionable(android):
        issue(
            "android_poll_stalled",
            "degraded",
            (
                f"surface={android.get('surface_state') or 'unknown'}, "
                f"failures={android.get('consecutive_poll_failures') or 0}, "
                f"error={android.get('last_poll_error') or 'none'}"
            ),
        )
    if not sender.get("ok"):
        issue("sender_lock_stuck", "degraded", str(sender.get("state") or "unknown"))
    if not gui_delivery.get("ok"):
        issue(
            "wechat_gui_delivery_stalled",
            "degraded",
            f"{len(gui_delivery.get('task_ids') or [])} current-client GUI timeout(s)",
        )
    if not schedules["echomind"]["running"]:
        issue("schedule_echomind_missing", "degraded", "EchoMind language scheduler is absent")
    elif schedules["echomind"]["heartbeat_age_seconds"] is None or (
        schedules["echomind"]["heartbeat_age_seconds"]
        > schedules["echomind"]["stale_after_seconds"]
    ):
        issue("schedule_echomind_stalled", "degraded", "EchoMind scheduler heartbeat is stale")
    elif schedules["echomind"]["pending_daily_pdf_actionable"]:
        issue(
            "schedule_echomind_daily_delivery_pending",
            "degraded",
            "EchoMind daily PDF is generated but not delivered",
        )
    elif schedules["echomind"]["pending_lesson_actionable"]:
        issue(
            "schedule_echomind_lesson_delivery_pending",
            "degraded",
            "EchoMind periodic lesson is generated but not delivered",
        )
    elif schedules["echomind"]["interval_seconds"] != ECHOMIND_INTERVAL_SECONDS:
        issue(
            "schedule_echomind_cadence",
            "degraded",
            f"expected {ECHOMIND_INTERVAL_SECONDS}s cadence",
        )
    if not schedules["career_daily"]["running"]:
        issue("schedule_career_missing", "degraded", "career daily scheduler is absent")
    elif schedules["career_daily"]["heartbeat_age_seconds"] is None or (
        schedules["career_daily"]["heartbeat_age_seconds"]
        > schedules["career_daily"]["stale_after_seconds"]
    ):
        issue(
            "schedule_career_stalled",
            "degraded",
            "career daily scheduler heartbeat is stale",
        )
    else:
        if schedules["career_daily"]["career_overdue"]:
            issue(
                "schedule_career_delivery_overdue",
                "degraded",
                "private DM career PDF is overdue",
            )
        if schedules["career_daily"]["organizer_overdue"]:
            issue(
                "schedule_memo_delivery_overdue",
                "degraded",
                "MEMO daily organizer PDF is overdue",
            )
    if not schedules["labagent_idle_inspiration"]["ok"]:
        issue("schedule_labagent_stalled", "degraded", "LabAgent idle-inspiration scheduler heartbeat is stale")
    if not agent_failures.get("ok"):
        issue(
            "agent_quota_exhausted",
            "critical",
            f"{agent_failures['quota_failure_count']} recent task(s) exhausted all backend fallbacks",
        )
    for name, status in queues.items():
        if status.get("stale_ids"):
            issue(f"{name}_queue_stale", "critical", f"{len(status['stale_ids'])} stale active task(s)")
        elif status.get("coverage_unresolved_ids"):
            issue(
                f"{name}_queue_message_unresolved",
                "degraded",
                f"{len(status['coverage_unresolved_ids'])} numbered message(s) remain unresolved after retry",
            )
        elif status.get("invalid_lines"):
            issue(f"{name}_queue_invalid", "degraded", f"{status['invalid_lines']} invalid JSONL line(s)")
    severity = "ok"
    if any(item["severity"] == "critical" for item in issues):
        severity = "critical"
    elif issues:
        severity = "degraded"
    return {
        "ok": not issues,
        "severity": severity,
        "checked_at": iso_now(),
        "issues": issues,
        "tmux": {
            "wechat": {
                "running": wechat["running"],
                "missing_windows": wechat_missing,
                "window_count": len(wechat.get("windows", {})),
            },
            "wecom": {
                "running": wecom["running"],
                "missing_windows": wecom_missing,
                "window_count": len(wecom.get("windows", {})),
            },
        },
        "android": android,
        "cli_transport": cli_transport,
        "direct_monitors": direct_monitors,
        "schedules": schedules,
        "agent_failures": agent_failures,
        "agent_backend": agent_backend,
        "sender_lock": sender,
        "wechat_gui_delivery": gui_delivery,
        "queues": queues,
        "processes": process_counts(wechat, wecom),
    }


def android_poll_failure_is_actionable(android: dict[str, Any]) -> bool:
    """Distinguish a bounded serialized GUI lane from a stalled relay."""

    if android.get("surface_state") == "anr":
        return True
    if android.get("poll_healthy"):
        return False
    error_text = str(android.get("last_poll_error") or "")
    serialized_busy = (
        "WECOM_ANDROID_BUSY" in error_text
        and bool(android.get("poll_in_progress"))
        and not bool(android.get("poll_stale"))
    )
    return not serialized_busy


def load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def update_fault_counts(state: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, int]:
    previous = state.get("fault_counts") if isinstance(state.get("fault_counts"), dict) else {}
    active = {item["code"] for item in snapshot.get("issues", [])}
    return {code: int(previous.get(code, 0)) + 1 for code in active}


def repair_due(
    code: str,
    state: dict[str, Any],
    *,
    consecutive_failures: int,
    cooldown_seconds: float,
    now: datetime,
) -> bool:
    if int((state.get("fault_counts") or {}).get(code, 0)) < consecutive_failures:
        return False
    repaired = (state.get("last_repair_at") or {}).get(code)
    repaired_at = parse_timestamp(repaired)
    return repaired_at is None or (now - repaired_at).total_seconds() >= cooldown_seconds


def run_repair(label: str, command: list[str]) -> dict[str, Any]:
    proc = run_command(command, timeout=180)
    detail = (proc.stdout or proc.stderr or "").strip().splitlines()
    return {
        "label": label,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "detail": detail[-1][:300] if detail else "",
    }


def android_poll_stall_requires_relay_restart(android: dict[str, Any]) -> bool:
    """Keep a live relay when only its bounded native-app recovery failed."""
    error_text = str(android.get("last_poll_error") or "").casefold()
    native_surface_blocked = any(
        marker in error_text
        for marker in (
            "did not reach the foreground",
            "android keyguard is locked",
            "authentication is in progress",
            "storage is critically low",
        )
    )
    return not (
        android.get("endpoint_reachable")
        and native_surface_blocked
        and not android.get("poll_stale")
        and not android.get("poll_in_progress")
    )


def perform_repairs(
    snapshot: dict[str, Any],
    state: dict[str, Any],
    *,
    consecutive_failures: int,
    cooldown_seconds: float,
    max_sender_seconds: float,
) -> list[dict[str, Any]]:
    now = utc_now()
    issue_codes = {item["code"] for item in snapshot.get("issues", [])}
    repairs: list[dict[str, Any]] = []
    wechat_faults = {"wechat_session_missing", "wechat_windows_missing"}
    wecom_faults = {"wecom_session_missing", "wecom_windows_missing"}
    if any(
        code in issue_codes
        and repair_due(
            code,
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
        for code in wechat_faults
    ):
        repairs.append(run_repair("wechat_missing_runtime", [str(WECHAT_SUPERVISOR), "ensure"]))
    if (
        "wechat_direct_monitor_stalled" in issue_codes
        and repair_due(
            "wechat_direct_monitor_stalled",
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
    ):
        repairs.append(run_repair("wechat_stalled_monitors", [str(WECHAT_SUPERVISOR), "reload-monitors"]))
    repaired_wecom = False
    if any(
        code in issue_codes
        and repair_due(
            code,
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
        for code in wecom_faults
    ):
        repairs.append(run_repair("wecom_missing_runtime", [str(WECOM_SUPERVISOR), "start"]))
        repaired_wecom = True
    if (
        not repaired_wecom
        and issue_codes.intersection({"android_endpoint_down", "android_poll_stalled"})
        and (
            "android_endpoint_down" in issue_codes
            or android_poll_stall_requires_relay_restart(snapshot.get("android") or {})
        )
        and repair_due(
            (
                "android_poll_stalled"
                if "android_poll_stalled" in issue_codes
                else "android_endpoint_down"
            ),
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
    ):
        repairs.append(run_repair("android_relay", [str(WECOM_SUPERVISOR), "android-restart"]))
    if (
        "sender_lock_stuck" in issue_codes
        and repair_due(
            "sender_lock_stuck",
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
    ):
        result = sender_lock_health(
            max_holder_seconds=max_sender_seconds,
            repair_orphans=True,
        )
        repairs.append(
            {
                "label": "orphaned_sender",
                "ok": not result.get("unknown_holder"),
                "terminated": result.get("terminated_orphans", []),
            }
        )
    if (
        "wechat_gui_delivery_stalled" in issue_codes
        and repair_due(
            "wechat_gui_delivery_stalled",
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
    ):
        repairs.append(
            run_repair(
                "wechat_input_stalled",
                [str(WECHAT_VIRTUAL_DESKTOP), "restart-client"],
            )
        )
    if any(
        code in issue_codes
        and repair_due(
            code,
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
        for code in {
            "schedule_echomind_missing",
            "schedule_echomind_cadence",
            "schedule_echomind_stalled",
            "schedule_echomind_daily_delivery_pending",
            "schedule_echomind_lesson_delivery_pending",
        }
    ):
        repairs.append(run_repair("echomind_schedule", [str(ECHOMIND_SCHEDULE_HELPER), "restart"]))
    career_issue_codes = {
        "schedule_career_missing",
        "schedule_career_stalled",
        "schedule_career_delivery_overdue",
        "schedule_memo_delivery_overdue",
    }
    if any(
        code in issue_codes
        and repair_due(
            code,
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
        for code in career_issue_codes
    ):
        repairs.append(
            run_repair(
                "career_schedule",
                [str(WECHAT_STACK), "restart-career"],
            )
        )
    if (
        "schedule_labagent_stalled" in issue_codes
        and repair_due(
            "schedule_labagent_stalled",
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
    ):
        repairs.append(run_repair("labagent_schedule", [str(WECOM_SUPERVISOR), "daily-restart"]))
    return repairs


def repair_agent_issue_codes(
    snapshot: dict[str, Any],
    state: dict[str, Any],
    *,
    consecutive_failures: int,
) -> list[str]:
    counts = state.get("fault_counts") if isinstance(state.get("fault_counts"), dict) else {}
    return sorted(
        {
            str(issue.get("code") or "")
            for issue in snapshot.get("issues", [])
            if str(issue.get("code") or "")
            and (
                issue.get("severity") == "critical"
                or str(issue.get("code") or "") in ALERTABLE_DEGRADED_CODES
            )
            and int(counts.get(str(issue.get("code") or ""), 0)) >= consecutive_failures
        }
    )


def repair_agent_due(
    snapshot: dict[str, Any],
    state: dict[str, Any],
    *,
    consecutive_failures: int,
    cooldown_seconds: float,
    now: datetime,
) -> tuple[bool, str, list[str]]:
    codes = repair_agent_issue_codes(
        snapshot,
        state,
        consecutive_failures=consecutive_failures,
    )
    if not codes:
        return False, "", []
    signature = hashlib.sha256("\n".join(codes).encode("utf-8")).hexdigest()
    attempted_at = parse_timestamp(state.get("last_repair_agent_attempt_at"))
    same_incident = signature == str(state.get("last_repair_agent_signature") or "")
    if (
        same_incident
        and attempted_at is not None
        and (now - attempted_at).total_seconds() < cooldown_seconds
    ):
        return False, signature, codes
    return True, signature, codes


def bounded_repair_context(
    snapshot: dict[str, Any],
    scripted_repairs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "checked_at": snapshot.get("checked_at"),
        "severity": snapshot.get("severity"),
        "issues": [
            {
                "code": str(item.get("code") or ""),
                "severity": str(item.get("severity") or ""),
                "detail": str(item.get("detail") or "")[:500],
            }
            for item in snapshot.get("issues", [])[:20]
        ],
        "tmux": snapshot.get("tmux"),
        "android": {
            key: (snapshot.get("android") or {}).get(key)
            for key in (
                "endpoint_reachable",
                "poll_healthy",
                "surface_state",
                "consecutive_poll_failures",
                "last_poll_error",
            )
        },
        "direct_monitors": snapshot.get("direct_monitors"),
        "schedules": snapshot.get("schedules"),
        "queues": snapshot.get("queues"),
        "scripted_repairs": scripted_repairs,
    }


def run_repair_agent(
    snapshot: dict[str, Any],
    scripted_repairs: list[dict[str, Any]],
    *,
    reasoning_effort: str = "medium",
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    context = json.dumps(
        bounded_repair_context(snapshot, scripted_repairs),
        ensure_ascii=False,
        indent=2,
    )
    prompt = f"""You are the persistent LabCanvas transport repair agent.

The deterministic health guard observed a repeated WeChat/WeCom runtime fault
that remained after normal scripted recovery. Diagnose and repair the live
runtime in {ROOT}. Reuse the repository's existing supervisors, health probes,
queue recovery commands, and tests. Inspect only bounded operational logs needed
for these issue codes. Do not read or quote chat content.

Allowed actions are local and reversible: inspect status/logs, restart an exact
dead or stalled tmux window, resume a durable task, clear an orphaned process
after proving it is orphaned, and run focused tests. Do not send chat messages,
publish anything, place orders, change credentials/accounts, bypass QR/CAPTCHA,
delete user data, rewrite unrelated code, or restart a healthy logged-in GUI.

Finish with concise evidence. If the issue is genuinely too complex for medium
reasoning and still unresolved, include the exact marker ESCALATE_HIGH once.

Health context:
{context}
"""
    result = run_agent_session(
        prompt,
        backend=select_agent_backend({}),
        chat_name=REPAIR_AGENT_CHAT,
        role=REPAIR_AGENT_ROLE,
        model=REPAIR_AGENT_MODEL,
        reasoning_effort=reasoning_effort,
        sandbox="workspace-write",
        timeout_seconds=timeout_seconds,
        workdir=ROOT,
        reuse=True,
        backend_config={
            "low_quota_spark": {"enabled": False},
            "agent_fallbacks": {
                "purchased_credit_retry": True,
                "fallback_to_aginti": True,
            },
        },
    )
    message = str(result.get("message") or "")
    return {
        "ok": bool(result.get("ok")),
        "backend": str(result.get("backend") or "codex"),
        "model": str(result.get("model") or REPAIR_AGENT_MODEL),
        "reasoning_effort": reasoning_effort,
        "thread_id": str(result.get("thread_id") or ""),
        "returncode": result.get("returncode"),
        "escalation_requested": "ESCALATE_HIGH" in message,
        "message_excerpt": message[-2000:],
        "stderr_tail": str(result.get("stderr_tail") or "")[-1000:],
    }


def run_repair_agent_with_escalation(
    snapshot: dict[str, Any],
    scripted_repairs: list[dict[str, Any]],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    medium = run_repair_agent(
        snapshot,
        scripted_repairs,
        reasoning_effort="medium",
        timeout_seconds=timeout_seconds,
    )
    if not medium.get("escalation_requested"):
        return medium
    high = run_repair_agent(
        snapshot,
        scripted_repairs,
        reasoning_effort="high",
        timeout_seconds=timeout_seconds,
    )
    return {"ok": bool(high.get("ok")), "medium": medium, "high": high, **high}


def snapshot_signature(snapshot: dict[str, Any]) -> str:
    queues = {}
    for name, status in (snapshot.get("queues") or {}).items():
        queues[name] = {
            "ok": status.get("ok"),
            "exists": status.get("exists"),
            "active": status.get("active"),
            "pending": status.get("pending"),
            "in_progress": status.get("in_progress"),
            "stale_ids": status.get("stale_ids"),
            "invalid_lines": status.get("invalid_lines"),
        }
    stable = {
        "severity": snapshot.get("severity"),
        "issues": snapshot.get("issues"),
        "tmux": snapshot.get("tmux"),
        "android": snapshot.get("android"),
        "direct_monitors": snapshot.get("direct_monitors"),
        "schedules": snapshot.get("schedules"),
        "agent_failures": snapshot.get("agent_failures"),
        "sender_lock": {
            "state": (snapshot.get("sender_lock") or {}).get("state"),
            "unknown_holder": (snapshot.get("sender_lock") or {}).get("unknown_holder"),
        },
        "queues": queues,
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def alertable_issue_codes(
    snapshot: dict[str, Any],
    state: dict[str, Any],
    *,
    consecutive_failures: int,
) -> list[str]:
    counts = state.get("fault_counts") if isinstance(state.get("fault_counts"), dict) else {}
    codes: list[str] = []
    for issue in snapshot.get("issues", []):
        code = str(issue.get("code") or "")
        serious = issue.get("severity") == "critical" or code in ALERTABLE_DEGRADED_CODES
        if serious and int(counts.get(code, 0)) >= consecutive_failures:
            codes.append(code)
    return sorted(set(codes))


def health_alert_message(codes: list[str], *, recovered: bool = False) -> str:
    if recovered:
        return "LabCanvas 健康恢复：WeChat/WeCom 传输、任务队列和定时任务已恢复正常。"
    descriptions = {
        "agent_quota_exhausted": "代理额度耗尽，且备用后端也未能完成任务",
        "android_endpoint_down": "WeCom Android 中继不可用",
        "android_poll_stalled": "WeCom Android 消息轮询或原生界面停滞",
        "schedule_career_delivery_overdue": "私聊每日职业分析 PDF 超时未交付",
        "schedule_career_missing": "每日分析定时任务未运行",
        "schedule_career_stalled": "每日职业分析定时任务心跳停止",
        "schedule_memo_delivery_overdue": "MEMO 每日完整整理 PDF 超时未交付",
        "schedule_echomind_cadence": "EchoMind 教学周期不是 6 小时",
        "schedule_echomind_daily_delivery_pending": "EchoMind 每日 PDF 已生成但尚未交付",
        "schedule_echomind_lesson_delivery_pending": "EchoMind 六小时课程已生成但尚未交付",
        "schedule_echomind_missing": "EchoMind 教学定时任务未运行",
        "schedule_echomind_stalled": "EchoMind 教学定时任务心跳停止",
        "schedule_labagent_stalled": "LabAgent 三小时空闲灵感任务心跳停止",
        "wechat_direct_monitor_stalled": "WeChat 群消息监视器心跳停止",
        "wechat_queue_stale": "WeChat 有长期停滞任务",
        "wechat_session_missing": "WeChat 自动化会话未运行",
        "wecom_queue_stale": "WeCom 有长期停滞任务",
        "wecom_session_missing": "WeCom 自动化会话未运行",
    }
    details = "；".join(descriptions.get(code, code) for code in codes)
    return f"LabCanvas 严重健康告警：{details}。系统已尝试自动修复；请查看本机 transport-health 状态。"


def send_health_alert(
    *,
    transport: str,
    chat: str,
    message: str,
    task_id: str,
) -> dict[str, Any]:
    normalized_transport = str(transport or "").strip().casefold()
    if normalized_transport == "wechat":
        proc = run_command(
            [
                sys.executable,
                str(WECHAT_GUI_SEND),
                "--target",
                chat,
                "--message",
                message,
                "--send",
                "--no-search",
            ],
            timeout=180,
        )
        payload = read_json_text(proc.stdout)
        return {
            "ok": proc.returncode == 0 and bool(payload.get("ok", True)),
            "returncode": proc.returncode,
            "error": str(payload.get("error") or proc.stderr or "")[:300],
        }
    if normalized_transport != "wecom-android":
        return {"ok": False, "error": f"unsupported alert transport: {transport}"}
    proc = run_command(
        [
            sys.executable,
            "-m",
            "agenticapp",
            "wecom",
            "android",
            "send",
            "--chat",
            chat,
            "--message",
            message,
            "--task-id",
            task_id,
            "--live",
            "--json",
        ],
        timeout=180,
    )
    payload = read_json_text(proc.stdout)
    return {
        "ok": proc.returncode == 0 and bool(payload.get("ok")),
        "returncode": proc.returncode,
        "error": str(payload.get("error") or proc.stderr or "")[:300],
    }


def read_json_text(value: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def maybe_alert(
    snapshot: dict[str, Any],
    state: dict[str, Any],
    *,
    transport: str,
    chat: str,
    consecutive_failures: int,
    cooldown_seconds: float,
) -> dict[str, Any] | None:
    if not transport or not chat:
        return None
    now = utc_now()
    codes = alertable_issue_codes(
        snapshot,
        state,
        consecutive_failures=consecutive_failures,
    )
    signature = hashlib.sha256("\n".join(codes).encode("utf-8")).hexdigest() if codes else ""
    active_signature = str(state.get("active_alert_signature") or "")
    if signature and signature == active_signature:
        return {"status": "deduplicated", "codes": codes}
    recovered = bool(active_signature and not signature)
    if not signature and not recovered:
        return None
    last_attempt = parse_timestamp(state.get("last_alert_attempt_at"))
    if last_attempt and (now - last_attempt).total_seconds() < cooldown_seconds:
        return {"status": "cooldown", "codes": codes, "recovered": recovered}
    sequence = int(state.get("alert_sequence") or 0) + 1
    event_signature = signature or f"recovered:{active_signature}"
    task_id = f"labcanvas-health-{sequence}-{hashlib.sha256(event_signature.encode()).hexdigest()[:12]}"
    state["last_alert_attempt_at"] = now.isoformat(timespec="seconds")
    result = send_health_alert(
        transport=transport,
        chat=chat,
        message=health_alert_message(codes, recovered=recovered),
        task_id=task_id,
    )
    state["alert_sequence"] = sequence
    state["last_alert_result"] = result
    if result.get("ok"):
        state["active_alert_signature"] = signature
        state["last_alert_at"] = now.isoformat(timespec="seconds")
        state["last_alert_codes"] = codes
    return {"status": "sent" if result.get("ok") else "failed", "codes": codes, "recovered": recovered, **result}


def one_cycle(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    snapshot = build_snapshot(max_sender_seconds=args.max_sender_age_seconds)
    state = load_state(args.state_path)
    state["fault_counts"] = update_fault_counts(state, snapshot)
    repairs: list[dict[str, Any]] = []
    if args.repair:
        repairs = perform_repairs(
            snapshot,
            state,
            consecutive_failures=args.repair_after_failures,
            cooldown_seconds=args.repair_cooldown_seconds,
            max_sender_seconds=args.max_sender_age_seconds,
        )
    if repairs:
        snapshot["repairs"] = repairs
        repaired_at = state.setdefault("last_repair_at", {})
        for repair in repairs:
            repaired_at[str(repair.get("label"))] = snapshot["checked_at"]
        # Map action labels back to the observed fault keys for cooldown checks.
        for issue in snapshot.get("issues", []):
            code = issue["code"]
            if code.startswith("wechat_") and any(item["label"] == "wechat_missing_runtime" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code.startswith("wecom_") and any(item["label"] == "wecom_missing_runtime" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code == "android_endpoint_down" and any(item["label"] == "android_relay" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code == "android_poll_stalled" and any(item["label"] == "android_relay" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code == "sender_lock_stuck" and any(item["label"] == "orphaned_sender" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code == "wechat_gui_delivery_stalled" and any(
                item["label"] == "wechat_input_stalled" for item in repairs
            ):
                repaired_at[code] = snapshot["checked_at"]
            if code == "wechat_direct_monitor_stalled" and any(item["label"] == "wechat_stalled_monitors" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code.startswith("schedule_echomind_") and any(item["label"] == "echomind_schedule" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code in {
                "schedule_career_missing",
                "schedule_career_stalled",
                "schedule_career_delivery_overdue",
                "schedule_memo_delivery_overdue",
            } and any(item["label"] == "career_schedule" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
        if args.repair_verify_delay_seconds > 0:
            time.sleep(args.repair_verify_delay_seconds)
        verified = build_snapshot(max_sender_seconds=args.max_sender_age_seconds)
        verified["repairs"] = repairs
        snapshot = verified
    repair_agent_result: dict[str, Any] | None = None
    if args.repair_agent and not snapshot.get("ok"):
        due, agent_signature, agent_codes = repair_agent_due(
            snapshot,
            state,
            consecutive_failures=args.repair_agent_after_failures,
            cooldown_seconds=args.repair_agent_cooldown_seconds,
            now=utc_now(),
        )
        if due:
            state["last_repair_agent_attempt_at"] = iso_now()
            state["last_repair_agent_signature"] = agent_signature
            state["last_repair_agent_codes"] = agent_codes
            repair_agent_result = run_repair_agent_with_escalation(
                snapshot,
                repairs,
                timeout_seconds=args.repair_agent_timeout_seconds,
            )
            state["last_repair_agent_result"] = repair_agent_result
            if args.repair_verify_delay_seconds > 0:
                time.sleep(args.repair_verify_delay_seconds)
            verified = build_snapshot(max_sender_seconds=args.max_sender_age_seconds)
            verified["repairs"] = repairs
            verified["repair_agent"] = repair_agent_result
            snapshot = verified
        elif agent_codes:
            snapshot["repair_agent"] = {
                "status": "cooldown",
                "codes": agent_codes,
            }
    recovered_after_repair = bool(repairs and snapshot.get("ok"))
    alert = None if recovered_after_repair else maybe_alert(
        snapshot,
        state,
        transport=args.alert_transport,
        chat=args.alert_chat,
        consecutive_failures=args.alert_after_failures,
        cooldown_seconds=args.alert_cooldown_seconds,
    )
    if alert:
        snapshot["alert"] = alert
    signature = snapshot_signature(snapshot)
    changed = signature != state.get("last_signature")
    state["last_signature"] = signature
    state["last_checked_at"] = snapshot["checked_at"]
    state["last_severity"] = snapshot["severity"]
    write_json(args.state_path, state)
    write_json(args.snapshot_path, snapshot)
    return snapshot, changed


def format_human(snapshot: dict[str, Any]) -> str:
    issues = ", ".join(item["code"] for item in snapshot.get("issues", [])) or "none"
    queues = snapshot.get("queues", {})
    return (
        f"transport-health severity={snapshot.get('severity')} issues={issues} "
        f"wechat_active={(queues.get('wechat') or {}).get('active', 0)} "
        f"wecom_active={(queues.get('wecom') or {}).get('active', 0)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument(
        "--repair-agent",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("WECHAT_STALL_REPAIR_AGENT", "0") == "1",
        help="Use a bounded persistent Codex repair turn only after repeated scripted recovery fails.",
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-lines", action="store_true")
    parser.add_argument("--changes-only", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--max-sender-age-seconds", type=float, default=180.0)
    parser.add_argument("--repair-after-failures", type=int, default=2)
    parser.add_argument("--repair-cooldown-seconds", type=float, default=300.0)
    parser.add_argument("--repair-verify-delay-seconds", type=float, default=2.0)
    parser.add_argument("--repair-agent-after-failures", type=int, default=4)
    parser.add_argument("--repair-agent-cooldown-seconds", type=float, default=21600.0)
    parser.add_argument("--repair-agent-timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--alert-transport",
        default=os.environ.get("LABCANVAS_HEALTH_ALERT_TRANSPORT", ""),
    )
    parser.add_argument(
        "--alert-chat",
        default=os.environ.get("LABCANVAS_HEALTH_ALERT_CHAT", ""),
    )
    parser.add_argument("--alert-after-failures", type=int, default=3)
    parser.add_argument("--alert-cooldown-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=ROOT / "output" / "transport-health" / "state.json",
    )
    parser.add_argument(
        "--snapshot-path",
        type=Path,
        default=ROOT / "output" / "transport-health" / "latest.json",
    )
    args = parser.parse_args()
    args.repair_after_failures = max(1, args.repair_after_failures)
    args.repair_agent_after_failures = max(1, args.repair_agent_after_failures)
    args.alert_after_failures = max(1, args.alert_after_failures)
    final: dict[str, Any] = {}
    while True:
        final, changed = one_cycle(args)
        if not args.changes_only or changed:
            if args.json or args.json_lines:
                print(json.dumps(final, ensure_ascii=False, separators=(",", ":")), flush=True)
            else:
                print(format_human(final), flush=True)
        if not args.loop:
            break
        time.sleep(max(5.0, args.interval_seconds))
    return 1 if args.strict and not final.get("ok") else 0


if __name__ == "__main__":
    raise SystemExit(main())
