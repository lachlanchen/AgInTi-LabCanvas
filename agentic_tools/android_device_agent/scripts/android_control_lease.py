#!/usr/bin/env python3
"""Cross-process priority and locking for one shared Android GUI device."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Any, Iterator


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_active_priority(
    path: Path,
    *,
    exclude_pid: int | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Return a live priority claim, discarding expired or dead owners."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        pid = int(payload.get("pid") or 0)
        expires_at = float(payload.get("expires_at") or 0.0)
    except (TypeError, ValueError):
        return None
    current = time.time() if now is None else float(now)
    if pid == int(exclude_pid or -1):
        return None
    if expires_at <= current or not process_is_alive(pid):
        remove_priority(path, token=str(payload.get("token") or ""))
        return None
    return payload


def write_priority(
    path: Path,
    *,
    token: str,
    purpose: str,
    lease_seconds: float,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = time.time()
    payload = {
        "version": 1,
        "token": token,
        "pid": os.getpid(),
        "purpose": str(purpose or "explicit_android_control")[:160],
        "created_at": now,
        "expires_at": now + max(5.0, float(lease_seconds)),
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{token}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return payload


def remove_priority(path: Path, *, token: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(payload, dict) and str(payload.get("token") or "") == token:
        path.unlink(missing_ok=True)


@contextmanager
def priority_android_control(
    *,
    lock_path: Path,
    priority_path: Path,
    purpose: str,
    timeout_seconds: float = 90.0,
    lease_seconds: float = 300.0,
) -> Iterator[dict[str, Any]]:
    """Announce an explicit request, then acquire the shared Android GUI lane."""
    timeout = max(0.1, float(timeout_seconds))
    token = secrets.token_hex(12)
    payload = write_priority(
        priority_path,
        token=token,
        purpose=purpose,
        lease_seconds=max(lease_seconds, timeout + 30.0),
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    deadline = time.monotonic() + timeout
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"ANDROID_CONTROL_BUSY: shared GUI lane exceeded {timeout:.1f}s"
                        ) from exc
                    time.sleep(0.1)
            yield payload
        finally:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                remove_priority(priority_path, token=token)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command_name", required=True)
    run = subparsers.add_parser(
        "run",
        help="Run one command while holding the shared Android GUI lane.",
    )
    run.add_argument("--lock-path", type=Path, required=True)
    run.add_argument("--priority-path", type=Path, required=True)
    run.add_argument("--purpose", required=True)
    run.add_argument("--timeout-seconds", type=float, default=90.0)
    run.add_argument("--lease-seconds", type=float, default=300.0)
    run.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("run requires a command after --")
    with priority_android_control(
        lock_path=args.lock_path.expanduser().resolve(),
        priority_path=args.priority_path.expanduser().resolve(),
        purpose=args.purpose,
        timeout_seconds=args.timeout_seconds,
        lease_seconds=args.lease_seconds,
    ):
        completed = subprocess.run(command, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
