#!/usr/bin/env python3
"""Keep configured WeChat chats materialized in the Linux client.

The direct DB monitor is fast and cheap, but some Linux WeChat builds only
materialize inactive chat rows after the desktop client opens that chat. This
loop cycles configured send targets through the existing guarded GUI opener in
dry-run mode. It never sends a message.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
SUPERVISOR_ENV = PRIVATE / "wechat_supervisor.local.env"
GUI_SEND = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"
SEND_LANE_ACTIVE_STATUSES = {
    "pending",
    "in_progress",
    "send_retrying",
    "send_deferred_artifact",
    "send_deferred_locked",
    "generation_waiting",
    "generation_poststage_pending",
}
SEND_LANE_RETRY_REASONS = {
    "gui_send_busy",
    "gui_send_timeout",
    "wechat_entry_required",
    "wechat_locked",
    "title_guard_blank",
    "required_artifact_delivery",
    "required_artifact_delivery_before_poststage",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", default="", help="Comma-separated direct-chatops configs. Defaults to supervisor env.")
    parser.add_argument("--display", default=os.environ.get("WECHAT_DISPLAY", ":97"))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("WECHAT_CHAT_SYNC_INTERVAL", "45")))
    parser.add_argument("--pause", type=float, default=float(os.environ.get("WECHAT_CHAT_SYNC_PAUSE", "0.8")))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("WECHAT_CHAT_SYNC_TIMEOUT", "60")))
    parser.add_argument(
        "--max-targets-per-cycle",
        type=int,
        default=int(os.environ.get("WECHAT_CHAT_SYNC_MAX_TARGETS_PER_CYCLE", "0") or "0"),
        help="Maximum chats to dry-open per sync pass. 0 means no limit.",
    )
    parser.add_argument(
        "--failure-backoff",
        type=float,
        default=env_float("WECHAT_CHAT_SYNC_FAILURE_BACKOFF_SECONDS", 300.0),
        help="Seconds to skip a chat after a retryable dry-open failure such as timeout or noisy title OCR.",
    )
    parser.add_argument("--priority", default=os.environ.get("WECHAT_CHAT_SYNC_PRIORITY", ""), help="Comma-separated chat names to sync first.")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--only", action="append", default=[], help="Only sync a chat name. Repeatable.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F"))
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path(os.environ.get("WECHAT_WORKER_QUEUE", str(DEFAULT_QUEUE))),
        help="Worker queue used to avoid taking the GUI send lock while replies are pending.",
    )
    parser.add_argument(
        "--yield-to-queue",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("WECHAT_CHAT_SYNC_YIELD_TO_QUEUE", "1") != "0",
        help="Skip dry-open sync while worker replies or artifact sends need the GUI send lane.",
    )
    args = parser.parse_args()

    failure_backoff_until: dict[str, float] = {}
    while True:
        results = sync_once(args, failure_backoff_until=failure_backoff_until)
        print(json.dumps({"checked_at": datetime.now().isoformat(timespec="seconds"), "results": results}, ensure_ascii=False), flush=True)
        if args.once or not args.loop:
            return 0 if all(item.get("ok") for item in results) else 1
        time.sleep(max(args.interval, 5.0))


def sync_once(args: argparse.Namespace, failure_backoff_until: dict[str, float] | None = None) -> list[dict[str, Any]]:
    if getattr(args, "yield_to_queue", True):
        send_lane = queue_send_lane_busy(Path(args.queue))
        if send_lane["busy"]:
            result = send_lane_reserved_result(args, send_lane)
            emit_target_event(result)
            return [result]

    configs = prioritize_configs(discover_configs(args.configs), args.priority)
    max_targets = max(0, int(getattr(args, "max_targets_per_cycle", 0) or 0))
    opened_or_attempted = 0
    only = {item.strip() for item in args.only if item.strip()}
    results: list[dict[str, Any]] = []
    for config_path in configs:
        try:
            if getattr(args, "yield_to_queue", True):
                send_lane = queue_send_lane_busy(Path(args.queue))
                if send_lane["busy"]:
                    results.append(send_lane_reserved_result(args, send_lane))
                    emit_target_event(results[-1])
                    break
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if config.get("desktop_sync_watch") is False:
                results.append({"config": str(config_path), "ok": True, "skipped": "desktop_sync_watch_false"})
                emit_target_event(results[-1])
                continue
            target = target_from_config(config)
            chat_name = str(config.get("chat_name") or target.get("name") or config_path.stem)
            if only and chat_name not in only and str(target.get("name") or "") not in only:
                results.append({"config": str(config_path), "chat": chat_name, "ok": True, "skipped": "not_selected"})
                emit_target_event(results[-1])
                continue
            if max_targets and opened_or_attempted >= max_targets:
                results.append({"config": str(config_path), "chat": chat_name, "ok": True, "skipped": "max_targets_per_cycle"})
                emit_target_event(results[-1])
                continue
            backoff_result = chat_sync_backoff_result(chat_name, failure_backoff_until)
            if backoff_result:
                results.append(backoff_result)
                emit_target_event(results[-1])
                continue
            opened_or_attempted += 1
            result = open_chat_dry_run(args, chat_name, target)
            apply_chat_sync_backoff(args, chat_name, result, failure_backoff_until)
            results.append(result)
            emit_target_event(results[-1])
        except Exception as exc:
            results.append({"config": str(config_path), "ok": False, "error": str(exc)[:500]})
            emit_target_event(results[-1])
    return results


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def chat_sync_backoff_result(chat_name: str, failure_backoff_until: dict[str, float] | None) -> dict[str, Any] | None:
    if not failure_backoff_until:
        return None
    retry_at = failure_backoff_until.get(chat_name)
    if not retry_at:
        return None
    now = time.time()
    if now >= retry_at:
        failure_backoff_until.pop(chat_name, None)
        return None
    return {
        "chat": chat_name,
        "ok": True,
        "skipped": "failure_backoff",
        "seconds_remaining": round(retry_at - now, 1),
        "retry_at": datetime.fromtimestamp(retry_at).isoformat(timespec="seconds"),
    }


def apply_chat_sync_backoff(
    args: argparse.Namespace,
    chat_name: str,
    result: dict[str, Any],
    failure_backoff_until: dict[str, float] | None,
) -> None:
    if failure_backoff_until is None:
        return
    if result.get("ok"):
        failure_backoff_until.pop(chat_name, None)
        return
    if not chat_sync_failure_retryable(result):
        return
    seconds = max(0.0, float(getattr(args, "failure_backoff", 300.0)))
    if seconds <= 0:
        return
    retry_at = time.time() + seconds
    failure_backoff_until[chat_name] = retry_at
    result["failure_backoff_seconds"] = seconds
    result["retry_at"] = datetime.fromtimestamp(retry_at).isoformat(timespec="seconds")


def chat_sync_failure_retryable(result: dict[str, Any]) -> bool:
    try:
        if int(result.get("returncode", -999)) == 124:
            return True
    except (TypeError, ValueError):
        pass
    text = " ".join(
        str(result.get(key) or "")
        for key in ("stderr_tail", "stdout_tail", "error")
    ).lower()
    retryable_markers = (
        "wechat_send_timeout",
        "opened chat title guard failed",
        "title guard failed",
        "ocr=",
        "wechat_locked",
    )
    return any(marker in text for marker in retryable_markers)


def send_lane_reserved_result(args: argparse.Namespace, send_lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": "send_lane_reserved",
        "queue": str(args.queue),
        "active": send_lane["active"],
    }


def queue_send_lane_busy(queue_path: Path) -> dict[str, Any]:
    """Return active queue rows that should get first use of the GUI sender."""
    if not queue_path.exists():
        return {"busy": False, "active": []}
    active: list[dict[str, Any]] = []
    try:
        lines = queue_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"busy": True, "active": [{"id": "", "status": "queue_read_error", "reason": str(exc)[:200]}]}
    for line in lines:
        if not line.strip():
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = str(task.get("status") or "")
        reason = str(task.get("send_deferred_reason") or "")
        is_send_retry = status in {"send_deferred_artifact", "send_deferred_locked"} and reason in SEND_LANE_RETRY_REASONS
        is_active = status in SEND_LANE_ACTIVE_STATUSES and status not in {"send_deferred_artifact", "send_deferred_locked"}
        if not (is_active or is_send_retry):
            continue
        active.append(
            {
                "id": str(task.get("id") or ""),
                "chat": str(task.get("chat") or ""),
                "status": status,
                "reason": reason,
            }
        )
    return {"busy": bool(active), "active": active[:12]}


def discover_configs(raw_configs: str) -> list[Path]:
    if not raw_configs:
        raw_configs = parse_env_file(SUPERVISOR_ENV).get("WECHAT_DIRECT_CONFIGS", "")
    paths: list[Path] = []
    for item in raw_configs.split(","):
        item = item.strip()
        if not item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = ROOT / path
        paths.append(path)
    return paths


def prioritize_configs(paths: list[Path], raw_priority: str) -> list[Path]:
    priority = [item.strip() for item in raw_priority.split(",") if item.strip()]
    if not priority:
        return paths
    priority_index = {name: index for index, name in enumerate(priority)}

    def key(path: Path) -> tuple[int, int]:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
            target = target_from_config(config)
            names = [str(config.get("chat_name") or ""), str(target.get("name") or "")]
        except Exception:
            names = []
        ranks = [priority_index[name] for name in names if name in priority_index]
        return (min(ranks) if ranks else len(priority_index), paths.index(path))

    return sorted(paths, key=key)


def emit_target_event(result: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "event": "chat_sync_target",
                "checked_at": datetime.now().isoformat(timespec="seconds"),
                "result": result,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        key, raw_value = stripped.split("=", 1)
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
            values[key.strip()] = parsed[0] if parsed else ""
        except ValueError:
            values[key.strip()] = raw_value.strip().strip("'\"")
    return values


def target_from_config(config: dict[str, Any]) -> dict[str, Any]:
    chat_name = str(config.get("chat_name") or "wechat-chat")
    raw_target = config.get("send_target")
    target = dict(raw_target) if isinstance(raw_target, dict) else {}
    target.setdefault("name", chat_name)
    target.setdefault("query", chat_name)
    target.setdefault("expected_title", chat_name)
    return target


def open_chat_dry_run(args: argparse.Namespace, chat_name: str, target: dict[str, Any]) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="wechat-chat-sync-", encoding="utf-8", delete=False) as fh:
        json.dump({"targets": [target], "message": ""}, fh, ensure_ascii=False)
        targets_file = Path(fh.name)
    try:
        env = chat_sync_gui_send_env(args)
        proc = subprocess.run(
            [
                sys.executable,
                str(GUI_SEND),
                "--display",
                args.display,
                "--targets-file",
                str(targets_file),
                "--prefer-current",
                "--no-search",
                "--pause",
                str(args.pause),
                "--output-dir",
                str(args.output_dir),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=chat_sync_subprocess_timeout(args),
            check=False,
        )
    finally:
        targets_file.unlink(missing_ok=True)
    result: dict[str, Any] = {"chat": chat_name, "ok": proc.returncode == 0, "returncode": proc.returncode}
    if proc.stdout.strip():
        result["stdout_tail"] = proc.stdout.strip()[-1000:]
    if proc.stderr.strip():
        result["stderr_tail"] = proc.stderr.strip()[-1000:]
    return result


def chat_sync_gui_send_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    default_max = max(20, int(float(args.timeout)) - 5)
    max_seconds = max(8, min(int(args.timeout), int(os.environ.get("WECHAT_CHAT_SYNC_GUI_SEND_MAX_SECONDS", str(default_max)))))
    title_retry = max(1.0, min(float(os.environ.get("WECHAT_CHAT_SYNC_TITLE_RETRY_SECONDS", "2.0")), float(max_seconds) / 2))
    env.setdefault("WECHAT_GUI_SEND_MAX_SECONDS", str(max_seconds))
    env.setdefault("WECHAT_TITLE_RETRY_SECONDS", str(title_retry))
    env.setdefault("WECHAT_INITIAL_TITLE_WAIT", os.environ.get("WECHAT_CHAT_SYNC_INITIAL_TITLE_WAIT", "0.4"))
    return env


def chat_sync_subprocess_timeout(args: argparse.Namespace) -> float:
    max_seconds = float(chat_sync_gui_send_env(args).get("WECHAT_GUI_SEND_MAX_SECONDS", "18"))
    return max(max_seconds + 5.0, args.pause * 12, 12.0)


if __name__ == "__main__":
    raise SystemExit(main())
