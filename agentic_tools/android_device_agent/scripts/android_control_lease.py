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


class AndroidControlBusy(RuntimeError):
    """Raised when background Android work must yield to an explicit action."""


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


def cooperative_waiter_path(priority_path: Path) -> Path:
    """Keep fairness requests separate from explicit-action priority."""
    suffix = priority_path.suffix or ".json"
    return priority_path.with_name(f"{priority_path.stem}.cooperative{suffix}")


def read_active_cooperative_waiter(
    priority_path: Path,
    *,
    exclude_pid: int | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    return read_active_priority(
        cooperative_waiter_path(priority_path),
        exclude_pid=exclude_pid,
        now=now,
    )


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


@contextmanager
def passive_android_control(
    *,
    lock_path: Path,
    priority_path: Path,
    purpose: str,
) -> Iterator[dict[str, Any]]:
    """Acquire the shared GUI lane only when no explicit request is waiting.

    Passive screen readers must never publish their own priority claim or wait
    ahead of a user-requested send. The second priority check closes the race
    between the initial observation and acquiring the file lock.
    """
    active = read_active_priority(priority_path, exclude_pid=os.getpid())
    if active is not None:
        raise AndroidControlBusy(
            f"ANDROID_CONTROL_PRIORITY: {active.get('purpose') or 'explicit request'}"
        )
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AndroidControlBusy("ANDROID_CONTROL_BUSY: shared GUI lane is active") from exc
        try:
            active = read_active_priority(priority_path, exclude_pid=os.getpid())
            if active is not None:
                raise AndroidControlBusy(
                    f"ANDROID_CONTROL_PRIORITY: {active.get('purpose') or 'explicit request'}"
                )
            yield {"purpose": str(purpose or "passive_android_control")[:160]}
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def cooperative_android_control(
    *,
    lock_path: Path,
    priority_path: Path,
    purpose: str,
    timeout_seconds: float = 8.0,
) -> Iterator[dict[str, Any]]:
    """Wait fairly for the background GUI lane without outranking user work.

    A separate cooperative marker asks other passive pollers to yield at their
    next safe boundary. Explicit sends still use the distinct priority marker
    and always win. This closes flock reacquisition starvation without treating
    a recurring reader as a user-requested action.
    """
    timeout = max(0.1, float(timeout_seconds))
    deadline = time.monotonic() + timeout
    token = secrets.token_hex(12)
    waiter_path = cooperative_waiter_path(priority_path)
    waiter = write_priority(
        waiter_path,
        token=token,
        purpose=str(purpose or "cooperative_android_control")[:160],
        lease_seconds=timeout + 15.0,
    )
    waiter["kind"] = "cooperative"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with lock_path.open("a+", encoding="utf-8") as handle:
            while True:
                active = read_active_priority(priority_path, exclude_pid=os.getpid())
                if active is not None:
                    raise AndroidControlBusy(
                        f"ANDROID_CONTROL_PRIORITY: "
                        f"{active.get('purpose') or 'explicit request'}"
                    )
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise AndroidControlBusy(
                            f"ANDROID_CONTROL_BUSY: shared GUI lane exceeded {timeout:.1f}s"
                        ) from exc
                    time.sleep(0.1)
            try:
                active = read_active_priority(priority_path, exclude_pid=os.getpid())
                if active is not None:
                    raise AndroidControlBusy(
                        f"ANDROID_CONTROL_PRIORITY: "
                        f"{active.get('purpose') or 'explicit request'}"
                    )
                yield waiter
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        remove_priority(waiter_path, token=token)


@contextmanager
def serialized_android_clipboard(
    *,
    lock_path: Path,
    timeout_seconds: float = 5.0,
) -> Iterator[None]:
    """Serialize the host clipboard shared by physical and virtual scrcpy."""
    timeout = max(0.1, float(timeout_seconds))
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    deadline = time.monotonic() + timeout
    with lock_path.open("a+", encoding="utf-8") as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise AndroidControlBusy(
                        f"ANDROID_CLIPBOARD_BUSY: exceeded {timeout:.1f}s"
                    ) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command_name", required=True)
    run = subparsers.add_parser(
        "run",
        help="Run one explicit command while holding the shared Android GUI lane.",
    )
    cooperative = subparsers.add_parser(
        "run-cooperative",
        help="Run background maintenance fairly without outranking explicit work.",
    )
    for command_parser in (run, cooperative):
        command_parser.add_argument("--lock-path", type=Path, required=True)
        command_parser.add_argument("--priority-path", type=Path, required=True)
        command_parser.add_argument("--purpose", required=True)
        command_parser.add_argument("--timeout-seconds", type=float, default=90.0)
        command_parser.add_argument("argv", nargs=argparse.REMAINDER)
    run.add_argument("--lease-seconds", type=float, default=300.0)
    args = parser.parse_args()
    command = list(args.argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error(f"{args.command_name} requires a command after --")
    control = (
        cooperative_android_control(
            lock_path=args.lock_path.expanduser().resolve(),
            priority_path=args.priority_path.expanduser().resolve(),
            purpose=args.purpose,
            timeout_seconds=args.timeout_seconds,
        )
        if args.command_name == "run-cooperative"
        else priority_android_control(
            lock_path=args.lock_path.expanduser().resolve(),
            priority_path=args.priority_path.expanduser().resolve(),
            purpose=args.purpose,
            timeout_seconds=args.timeout_seconds,
            lease_seconds=args.lease_seconds,
        )
    )
    try:
        with control:
            completed = subprocess.run(command, check=False)
    except (AndroidControlBusy, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 75
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
