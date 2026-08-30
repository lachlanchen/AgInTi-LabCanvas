#!/usr/bin/env python3
"""Bound generated WeChat transcripts and transient GUI evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / "output" / "wechat_gui_agent"
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
ATTEMPT_SCREENSHOT = re.compile(
    r"^\d{2}-.+-\d{6}-\d{6}-(?P<stage>.+)\.png$"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-log-mib", type=float, default=16.0)
    parser.add_argument("--keep-log-mib", type=float, default=8.0)
    parser.add_argument("--log-retention-days", type=float, default=14.0)
    parser.add_argument("--attempt-evidence-days", type=float, default=1.0)
    parser.add_argument("--sent-evidence-days", type=float, default=30.0)
    parser.add_argument("--diagnostic-evidence-days", type=float, default=14.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=float, default=300.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    while True:
        result = maintain_output(
            args.root,
            max_log_bytes=max(1, int(args.max_log_mib * 1024 * 1024)),
            keep_log_bytes=max(1, int(args.keep_log_mib * 1024 * 1024)),
            log_retention_seconds=max(0.0, args.log_retention_days * 86400),
            attempt_retention_seconds=max(0.0, args.attempt_evidence_days * 86400),
            sent_retention_seconds=max(0.0, args.sent_evidence_days * 86400),
            diagnostic_retention_seconds=max(0.0, args.diagnostic_evidence_days * 86400),
        )
        if args.json or result["removed_files"] or result["trimmed_logs"] or result["errors"]:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.loop:
            return 0 if not result["errors"] else 1
        time.sleep(max(30.0, args.interval))


def maintain_output(
    root: Path,
    *,
    max_log_bytes: int,
    keep_log_bytes: int,
    log_retention_seconds: float,
    attempt_retention_seconds: float,
    sent_retention_seconds: float,
    diagnostic_retention_seconds: float,
    now: float | None = None,
) -> dict[str, Any]:
    current_time = time.time() if now is None else now
    result: dict[str, Any] = {
        "checked_at": datetime.fromtimestamp(current_time).isoformat(timespec="seconds"),
        "root": str(root),
        "removed_files": 0,
        "removed_bytes": 0,
        "trimmed_logs": 0,
        "trimmed_bytes": 0,
        "errors": [],
    }
    if not root.exists():
        return result

    PRIVATE.mkdir(parents=True, exist_ok=True)
    lock_path = PRIVATE / "wechat_output_retention.lock"
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return result
        log_paths = tuple(root.rglob("*.log"))
        log_identities = {
            file_identity(stat)
            for path in log_paths
            if (stat := safe_stat(path)) is not None
            and log_retention_seconds
            and max(0.0, current_time - stat.st_mtime) > log_retention_seconds
        }
        open_files = open_file_identities(log_identities)
        for path in log_paths:
            maintain_log(
                path,
                result,
                now=current_time,
                max_bytes=max_log_bytes,
                keep_bytes=min(keep_log_bytes, max_log_bytes),
                retention_seconds=log_retention_seconds,
                open_files=open_files,
            )
        for path in root.rglob("*.png"):
            maintain_screenshot(
                path,
                result,
                now=current_time,
                attempt_retention_seconds=attempt_retention_seconds,
                sent_retention_seconds=sent_retention_seconds,
                diagnostic_retention_seconds=diagnostic_retention_seconds,
            )
        fcntl.flock(lock, fcntl.LOCK_UN)
    return result


def maintain_log(
    path: Path,
    result: dict[str, Any],
    *,
    now: float,
    max_bytes: int,
    keep_bytes: int,
    retention_seconds: float,
    open_files: set[tuple[int, int]],
) -> None:
    try:
        stat = path.stat()
        age = max(0.0, now - stat.st_mtime)
        if retention_seconds and age > retention_seconds:
            if file_identity(stat) in open_files:
                if stat.st_size > keep_bytes:
                    trim_and_record_log(path, stat.st_size, keep_bytes, result)
                return
            remove_generated_file(path, stat.st_size, result)
            return
        if stat.st_size <= max_bytes:
            return
        trim_and_record_log(path, stat.st_size, keep_bytes, result)
    except OSError as exc:
        result["errors"].append({"path": str(path), "error": str(exc)[:300]})


def trim_log_tail_in_place(path: Path, keep_bytes: int) -> None:
    with path.open("r+b") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - keep_bytes)
        handle.seek(start)
        tail = handle.read()
        if start and b"\n" in tail:
            tail = tail.split(b"\n", 1)[1]
        handle.seek(0)
        handle.write(tail)
        handle.truncate()


def trim_and_record_log(
    path: Path,
    original_size: int,
    keep_bytes: int,
    result: dict[str, Any],
) -> None:
    trim_log_tail_in_place(path, keep_bytes)
    new_size = path.stat().st_size
    result["trimmed_logs"] += 1
    result["trimmed_bytes"] += max(0, original_size - new_size)


def file_identity(stat: os.stat_result) -> tuple[int, int]:
    return (int(stat.st_dev), int(stat.st_ino))


def safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def open_file_identities(
    candidates: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Return candidate inodes currently held open by any visible process."""
    identities: set[tuple[int, int]] = set()
    if not candidates:
        return identities
    proc = Path("/proc")
    try:
        process_dirs = tuple(path for path in proc.iterdir() if path.name.isdigit())
    except OSError:
        return identities
    for process_dir in process_dirs:
        fd_dir = process_dir / "fd"
        try:
            file_descriptors = tuple(fd_dir.iterdir())
        except OSError:
            continue
        for descriptor in file_descriptors:
            try:
                identity = file_identity(descriptor.stat())
            except OSError:
                continue
            if identity in candidates:
                identities.add(identity)
                if identities == candidates:
                    return identities
    return identities


def maintain_screenshot(
    path: Path,
    result: dict[str, Any],
    *,
    now: float,
    attempt_retention_seconds: float,
    sent_retention_seconds: float,
    diagnostic_retention_seconds: float,
) -> None:
    name = path.name
    retention: float | None = None
    if ATTEMPT_SCREENSHOT.match(name):
        retention = sent_retention_seconds if name.endswith("-sent.png") else attempt_retention_seconds
    elif name.startswith("unlock-watchdog-desktop-locked-"):
        retention = diagnostic_retention_seconds
    elif name.startswith("chat-sync-latest-failure-"):
        retention = diagnostic_retention_seconds
    if retention is None:
        return
    try:
        stat = path.stat()
        if max(0.0, now - stat.st_mtime) > retention:
            remove_generated_file(path, stat.st_size, result)
    except OSError as exc:
        result["errors"].append({"path": str(path), "error": str(exc)[:300]})


def remove_generated_file(path: Path, size: int, result: dict[str, Any]) -> None:
    path.unlink(missing_ok=True)
    result["removed_files"] += 1
    result["removed_bytes"] += max(0, size)


if __name__ == "__main__":
    raise SystemExit(main())
