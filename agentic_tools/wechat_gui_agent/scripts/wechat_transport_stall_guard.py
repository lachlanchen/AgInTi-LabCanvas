#!/usr/bin/env python3
"""Recover stale WeChat/WeCom transport work without touching chat content."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
SEND_LOCK = PRIVATE / "wechat_gui_send.lock"


def processes(pattern: str) -> list[int]:
    out = subprocess.run(["pgrep", "-f", pattern], text=True, capture_output=True, check=False).stdout
    return [int(x) for x in out.split() if x.isdigit() and int(x) != os.getpid()]


def recover_stale_sender(max_age: float) -> str:
    if not SEND_LOCK.exists():
        return "sender_lock=absent"
    age = time.time() - SEND_LOCK.stat().st_mtime
    if age < max_age:
        return f"sender_lock=active age={age:.1f}s"
    killed = []
    for pid in processes(r"wechat_gui_send\.py"):
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except ProcessLookupError:
            pass
    return f"sender_lock=stale age={age:.1f}s terminated={killed}"


def check() -> dict[str, object]:
    return {
        "wechat_direct_chatops": len(processes(r"wechat_direct_chatops\.py.*--loop")),
        "wechat_worker": len(processes(r"wechat_task_worker\.py.*--loop")),
        "wecom_worker": len(processes(r"wechat_task_worker\.py.*wecom_task_queue.*--loop")),
        "android_relay": len(processes(r"wecom_android_bridge\.py.*serve")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--max-sender-age-seconds", type=float, default=120.0)
    args = parser.parse_args()
    while True:
        print({"check": check(), "recovery": recover_stale_sender(args.max_sender_age_seconds)}, flush=True)
        if not args.loop:
            return 0
        time.sleep(max(5.0, args.interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
