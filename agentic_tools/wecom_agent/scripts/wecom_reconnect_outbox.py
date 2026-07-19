#!/usr/bin/env python3
"""Recover a bounded recent WeCom outbox through the shared worker contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SHARED_WORKER = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_task_worker.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--max-age-seconds", type=int, default=12 * 60 * 60)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(SHARED_WORKER),
            "--queue",
            str(args.queue.expanduser().resolve()),
            "--recover-expired-transport",
            "wecom",
            "--recovery-max-age-seconds",
            str(max(0, args.max_age_seconds)),
            "--recovery-limit",
            str(max(0, args.limit)),
        ],
        cwd=ROOT,
        env=env,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
