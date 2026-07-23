#!/usr/bin/env python3
"""Read and cache Codex account rate limits through the official app server."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE = Path(
    os.environ.get("LABCANVAS_CODEX_QUOTA_CACHE")
    or ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / ".private"
    / "codex_quota_status.json"
).expanduser().resolve()
DEFAULT_THRESHOLD_PERCENT = 5.0
DEFAULT_CACHE_MAX_AGE_SECONDS = 180.0


class QuotaProbeError(RuntimeError):
    """The local Codex rate-limit snapshot could not be read safely."""


def now_epoch() -> float:
    return time.time()


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load_cached_status(path: Path = DEFAULT_CACHE) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_codex_bin(
    codex_bin: str | None = None,
    *,
    home: Path | None = None,
) -> str:
    configured = codex_bin or os.environ.get("CODEX_BIN")
    if configured:
        resolved = shutil.which(configured)
        candidate = Path(configured).expanduser()
        if resolved:
            return resolved
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    resolved = shutil.which("codex")
    if resolved:
        return resolved
    user_home = (home or Path.home()).expanduser().resolve()
    candidates = [
        user_home / ".local" / "bin" / "codex",
        user_home / ".npm-global" / "bin" / "codex",
        user_home / ".volta" / "bin" / "codex",
    ]
    nvm_candidates = list(
        (user_home / ".nvm" / "versions" / "node").glob("*/bin/codex")
    )
    nvm_candidates.sort(
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    for candidate in [*candidates, *nvm_candidates]:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    raise QuotaProbeError("Codex CLI is not installed")


def _read_response(
    messages: queue.Queue[dict[str, Any] | BaseException | None],
    process: subprocess.Popen[str],
    request_id: int,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            remaining = max(0.01, deadline - time.monotonic())
            message = messages.get(timeout=min(0.25, remaining))
        except queue.Empty:
            if process.poll() is not None:
                raise QuotaProbeError(
                    f"Codex app server exited with code {process.returncode}"
                )
            continue
        if isinstance(message, BaseException):
            raise QuotaProbeError(f"Codex app-server reader failed: {message}")
        if message is None:
            raise QuotaProbeError("Codex app server closed before returning quota")
        if message.get("id") != request_id:
            continue
        if message.get("error") is not None:
            raise QuotaProbeError("Codex app server rejected the quota request")
        result = message.get("result")
        if not isinstance(result, dict):
            raise QuotaProbeError("Codex app server returned an invalid quota payload")
        return result
    raise QuotaProbeError("Codex quota read timed out")


def read_rate_limits_from_app_server(
    *,
    timeout_seconds: float = 8.0,
    codex_bin: str | None = None,
) -> dict[str, Any]:
    """Call the read-only account/rateLimits/read app-server method."""
    executable = resolve_codex_bin(codex_bin)
    process = subprocess.Popen(
        [executable, "app-server", "--disable", "hooks", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        start_new_session=(os.name == "posix"),
        env=os.environ.copy(),
    )
    messages: queue.Queue[dict[str, Any] | BaseException | None] = queue.Queue()

    def read_stdout() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    messages.put(value)
        except BaseException as exc:  # pragma: no cover - defensive pipe boundary
            messages.put(exc)
        finally:
            messages.put(None)

    threading.Thread(target=read_stdout, daemon=True).start()

    def send(payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise QuotaProbeError("Codex app-server input is unavailable")
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.flush()

    try:
        send(
            {
                "method": "initialize",
                "id": 1,
                "params": {
                    "clientInfo": {
                        "name": "labcanvas-quota-monitor",
                        "title": "LabCanvas Codex Quota Monitor",
                        "version": "1.0.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            }
        )
        _read_response(messages, process, 1, timeout_seconds=timeout_seconds)
        send({"method": "initialized", "params": {}})
        send(
            {
                "method": "account/rateLimits/read",
                "id": 2,
                "params": {},
            }
        )
        return _read_response(messages, process, 2, timeout_seconds=timeout_seconds)
    except (BrokenPipeError, OSError) as exc:
        raise QuotaProbeError(f"Codex quota transport failed: {exc}") from exc
    finally:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def normalize_rate_limit_response(
    response: dict[str, Any],
    *,
    threshold_percent: float = DEFAULT_THRESHOLD_PERCENT,
    observed_at: float | None = None,
) -> dict[str, Any]:
    """Select the normal Codex bucket and its most depleted rolling window."""
    snapshots = response.get("rateLimitsByLimitId")
    snapshot = snapshots.get("codex") if isinstance(snapshots, dict) else None
    if not isinstance(snapshot, dict):
        snapshot = response.get("rateLimits")
    if not isinstance(snapshot, dict):
        raise QuotaProbeError("Codex quota response has no normal Codex bucket")

    windows: list[dict[str, Any]] = []
    for name in ("primary", "secondary"):
        value = snapshot.get(name)
        if not isinstance(value, dict):
            continue
        used = value.get("usedPercent")
        if not isinstance(used, (int, float)):
            continue
        remaining = max(0.0, min(100.0, 100.0 - float(used)))
        windows.append(
            {
                "name": name,
                "used_percent": float(used),
                "remaining_percent": remaining,
                "window_duration_mins": value.get("windowDurationMins"),
                "resets_at": value.get("resetsAt"),
            }
        )
    if not windows:
        raise QuotaProbeError("Codex quota response has no metered window")
    active = min(windows, key=lambda item: float(item["remaining_percent"]))
    observed = now_epoch() if observed_at is None else float(observed_at)
    credits = snapshot.get("credits")
    credits = credits if isinstance(credits, dict) else {}
    remaining = float(active["remaining_percent"])
    return {
        "ok": True,
        "source": "codex_app_server_account_rate_limits",
        "observed_at_epoch": observed,
        "observed_at": datetime.fromtimestamp(
            observed, timezone.utc
        ).isoformat(timespec="seconds"),
        "limit_id": str(snapshot.get("limitId") or "codex"),
        "limit_name": str(snapshot.get("limitName") or "Codex"),
        "plan_type": str(snapshot.get("planType") or ""),
        "window": active,
        "windows": windows,
        "remaining_percent": remaining,
        "used_percent": float(active["used_percent"]),
        "threshold_percent": float(threshold_percent),
        "warning": remaining < float(threshold_percent),
        "credits": {
            "has_credits": bool(credits.get("hasCredits")),
            "unlimited": bool(credits.get("unlimited")),
            "balance": str(credits.get("balance") or ""),
        },
    }


def probe_status(
    *,
    cache_path: Path = DEFAULT_CACHE,
    threshold_percent: float = DEFAULT_THRESHOLD_PERCENT,
    timeout_seconds: float = 8.0,
    reader: Callable[..., dict[str, Any]] = read_rate_limits_from_app_server,
) -> dict[str, Any]:
    try:
        response = reader(timeout_seconds=timeout_seconds)
        status = normalize_rate_limit_response(
            response,
            threshold_percent=threshold_percent,
        )
    except Exception as exc:
        status = {
            "ok": False,
            "source": "codex_app_server_account_rate_limits",
            "observed_at_epoch": now_epoch(),
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
    write_private_json(cache_path, status)
    return status


def current_status(
    *,
    cache_path: Path = DEFAULT_CACHE,
    max_age_seconds: float = DEFAULT_CACHE_MAX_AGE_SECONDS,
    threshold_percent: float = DEFAULT_THRESHOLD_PERCENT,
    refresh: bool = True,
) -> dict[str, Any]:
    cached = load_cached_status(cache_path)
    age = now_epoch() - float(cached.get("observed_at_epoch") or 0)
    reset_at = (cached.get("window") or {}).get("resets_at")
    reset_is_future = not isinstance(reset_at, (int, float)) or reset_at > now_epoch()
    if cached.get("ok") and age <= max_age_seconds and reset_is_future:
        cached = dict(cached)
        remaining = float(cached.get("remaining_percent") or 0)
        cached["threshold_percent"] = float(threshold_percent)
        cached["warning"] = remaining < float(threshold_percent)
        return cached
    if not refresh:
        return {}
    return probe_status(
        cache_path=cache_path,
        threshold_percent=threshold_percent,
    )


def request_uses_cjk(text: str) -> bool:
    return any(
        "\u3400" <= character <= "\u9fff"
        or "\u3040" <= character <= "\u30ff"
        for character in text
    )


def format_warning(status: dict[str, Any], *, request_text: str = "") -> str:
    if not status.get("ok") or not status.get("warning"):
        return ""
    remaining = float(status.get("remaining_percent") or 0)
    threshold = float(status.get("threshold_percent") or DEFAULT_THRESHOLD_PERCENT)
    reset_at = (status.get("window") or {}).get("resets_at")
    reset_text = ""
    if isinstance(reset_at, (int, float)) and reset_at > 0:
        reset_text = datetime.fromtimestamp(reset_at).astimezone().strftime(
            "%Y-%m-%d %H:%M %Z"
        )
    remaining_text = f"{remaining:g}%"
    threshold_text = f"{threshold:g}%"
    if request_uses_cjk(request_text):
        reset_clause = f"，预计 {reset_text} 重置" if reset_text else ""
        return (
            f"额度提醒：Codex 当前额度仅剩 {remaining_text}，低于 "
            f"{threshold_text}{reset_clause}。本次任务仍会继续，额度耗尽时会尝试备用后端。"
        )
    reset_clause = f"; expected reset: {reset_text}" if reset_text else ""
    return (
        f"Quota notice: Codex has {remaining_text} remaining, below "
        f"{threshold_text}{reset_clause}. This request will continue and the "
        "configured fallback backend will be tried if Codex is exhausted."
    )


def quota_warning_for_request(request_text: str) -> str:
    try:
        threshold = float(
            os.environ.get(
                "LABCANVAS_CODEX_QUOTA_WARNING_THRESHOLD_PERCENT",
                str(DEFAULT_THRESHOLD_PERCENT),
            )
        )
        max_age = float(
            os.environ.get(
                "LABCANVAS_CODEX_QUOTA_CACHE_MAX_AGE_SECONDS",
                str(DEFAULT_CACHE_MAX_AGE_SECONDS),
            )
        )
        status = current_status(
            max_age_seconds=max(5.0, max_age),
            threshold_percent=max(0.0, min(100.0, threshold)),
        )
        return format_warning(status, request_text=request_text)
    except Exception:
        # Quota observability must never block a chat request.
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("probe", "status", "loop"),
        nargs="?",
        default="status",
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--threshold-percent",
        type=float,
        default=DEFAULT_THRESHOLD_PERCENT,
    )
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument(
        "--max-age-seconds",
        type=float,
        default=DEFAULT_CACHE_MAX_AGE_SECONDS,
    )
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "loop":
        while True:
            status = probe_status(
                cache_path=args.cache,
                threshold_percent=args.threshold_percent,
                timeout_seconds=args.timeout_seconds,
            )
            if args.json:
                print(json.dumps(status, ensure_ascii=False), flush=True)
            time.sleep(max(15.0, args.interval_seconds))

    status = (
        probe_status(
            cache_path=args.cache,
            threshold_percent=args.threshold_percent,
            timeout_seconds=args.timeout_seconds,
        )
        if args.command == "probe"
        else current_status(
            cache_path=args.cache,
            max_age_seconds=args.max_age_seconds,
            threshold_percent=args.threshold_percent,
        )
    )
    print(json.dumps(status, ensure_ascii=False, indent=2 if args.json else None))
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
