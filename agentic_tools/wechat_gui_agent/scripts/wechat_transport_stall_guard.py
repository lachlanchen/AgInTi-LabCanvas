#!/usr/bin/env python3
"""Observe and safely repair LabCanvas WeChat/WeCom transport liveness.

The guard never reads chat text and never restarts a healthy client. Repairs are
limited to missing/dead tmux workers and a failed Android relay endpoint after
the same fault has been observed repeatedly.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
WECHAT_PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
WECOM_PRIVATE = ROOT / "agentic_tools" / "wecom_agent" / ".private"
SEND_LOCK = WECHAT_PRIVATE / "wechat_gui_send.lock"
WECHAT_QUEUE = WECHAT_PRIVATE / "wechat_task_queue.jsonl"
WECOM_QUEUE = WECOM_PRIVATE / "wecom_task_queue.jsonl"
WECHAT_SUPERVISOR = (
    ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_supervisor_tmux.sh"
)
WECOM_SUPERVISOR = ROOT / "agentic_tools" / "wecom_agent" / "scripts" / "wecom_tmux.sh"
ANDROID_CONFIG = WECOM_PRIVATE / "wecom_android_bridge.local.json"
GUI_CONFIG = WECOM_PRIVATE / "wecom_gui_bridge.local.json"
CLI_CONFIG = WECOM_PRIVATE / "wecom_cli_bridge.local.json"
CLI_TRANSPORT_STATE = WECOM_PRIVATE / "wecom_cli_transport.local.json"
ECHOMIND_SCHEDULE_STATE = WECHAT_PRIVATE / "echomind-language-schedule.state.json"
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
ECHOMIND_INTERVAL_SECONDS = 3 * 60 * 60
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
    "schedule_career_missing",
    "schedule_echomind_cadence",
    "schedule_echomind_missing",
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
        return {"ok": False, "error": last_error}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_payload"}
    return {
        "ok": bool(payload.get("ok")),
        "device_authorized": bool(payload.get("device_authorized")),
        "wecom_foreground": bool(payload.get("wecom_foreground")),
        "transport": str(payload.get("transport") or ""),
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
        healthy = heartbeat is not None and age is not None and age <= threshold
        monitors.append(
            {
                "config": config_path.name,
                "ok": healthy,
                "heartbeat_age_seconds": int(age) if age is not None else None,
                "stale_after_seconds": int(threshold),
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


def schedule_health() -> dict[str, Any]:
    echo_state = read_json(ECHOMIND_SCHEDULE_STATE)
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
    return {
        "ok": echomind_running and career_running and interval == ECHOMIND_INTERVAL_SECONDS,
        "echomind": {
            "running": echomind_running,
            "interval_seconds": interval,
            "expected_interval_seconds": ECHOMIND_INTERVAL_SECONDS,
        },
        "career_daily": {"running": career_running},
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
    for task_id, task in latest.items():
        status = str(task.get("status") or "")
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
        "ok": not stale_ids and invalid_lines == 0,
        "exists": True,
        "task_count": len(latest),
        "active": len(active),
        "pending": sum(1 for item in active if item["status"] == "pending"),
        "in_progress": sum(1 for item in active if item["status"] in IN_PROGRESS_STATUSES),
        "oldest_active_seconds": max((item["age_seconds"] for item in active), default=0),
        "stale_ids": stale_ids[:20],
        "invalid_lines": invalid_lines,
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
    direct_monitors = direct_monitor_health()
    schedules = schedule_health()
    cli_transport = cli_transport_health()
    agent_failures = recent_terminal_agent_failures()
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
    if android_expected and not android.get("ok"):
        issue("android_endpoint_down", "degraded", "Android relay health endpoint is unavailable")
    if not sender.get("ok"):
        issue("sender_lock_stuck", "degraded", str(sender.get("state") or "unknown"))
    if not schedules["echomind"]["running"]:
        issue("schedule_echomind_missing", "degraded", "EchoMind language scheduler is absent")
    elif schedules["echomind"]["interval_seconds"] != ECHOMIND_INTERVAL_SECONDS:
        issue(
            "schedule_echomind_cadence",
            "degraded",
            f"expected {ECHOMIND_INTERVAL_SECONDS}s cadence",
        )
    if not schedules["career_daily"]["running"]:
        issue("schedule_career_missing", "degraded", "career daily scheduler is absent")
    if not agent_failures.get("ok"):
        issue(
            "agent_quota_exhausted",
            "critical",
            f"{agent_failures['quota_failure_count']} recent task(s) exhausted all backend fallbacks",
        )
    for name, status in queues.items():
        if status.get("stale_ids"):
            issue(f"{name}_queue_stale", "critical", f"{len(status['stale_ids'])} stale active task(s)")
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
        "sender_lock": sender,
        "queues": queues,
        "processes": process_counts(wechat, wecom),
    }


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
        and "android_endpoint_down" in issue_codes
        and repair_due(
            "android_endpoint_down",
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
    if any(
        code in issue_codes
        and repair_due(
            code,
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
        for code in {"schedule_echomind_missing", "schedule_echomind_cadence"}
    ):
        repairs.append(run_repair("echomind_schedule", [str(ECHOMIND_SCHEDULE_HELPER), "restart"]))
    if (
        "schedule_career_missing" in issue_codes
        and repair_due(
            "schedule_career_missing",
            state,
            consecutive_failures=consecutive_failures,
            cooldown_seconds=cooldown_seconds,
            now=now,
        )
    ):
        repairs.append(run_repair("career_schedule", [str(WECHAT_STACK), "start"]))
    return repairs


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
        "schedule_career_missing": "每日分析定时任务未运行",
        "schedule_echomind_cadence": "EchoMind 教学周期不是 3 小时",
        "schedule_echomind_missing": "EchoMind 教学定时任务未运行",
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
    if transport != "wecom-android":
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
            if code == "sender_lock_stuck" and any(item["label"] == "orphaned_sender" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code == "wechat_direct_monitor_stalled" and any(item["label"] == "wechat_stalled_monitors" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code.startswith("schedule_echomind_") and any(item["label"] == "echomind_schedule" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
            if code == "schedule_career_missing" and any(item["label"] == "career_schedule" for item in repairs):
                repaired_at[code] = snapshot["checked_at"]
    repair_succeeded = any(item.get("ok") for item in repairs)
    alert = None if repair_succeeded else maybe_alert(
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
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--json-lines", action="store_true")
    parser.add_argument("--changes-only", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--max-sender-age-seconds", type=float, default=180.0)
    parser.add_argument("--repair-after-failures", type=int, default=2)
    parser.add_argument("--repair-cooldown-seconds", type=float, default=300.0)
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
