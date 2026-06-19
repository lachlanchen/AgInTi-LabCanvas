#!/usr/bin/env python3
"""Copy recently downloaded WeChat media/files into the local private mirror."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil

from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEST = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private" / "downloads"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", required=True)
    parser.add_argument("--source", type=Path, action="append", required=True, help="WeChat download/cache directory. Repeatable.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--since-minutes", type=float, default=60)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cutoff = datetime.now() - timedelta(minutes=args.since_minutes)
    copied = []
    for source in args.source:
        if not source.exists():
            continue
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                continue
            rel = safe_relative(source, path)
            target = args.dest / source.name / rel
            copied.append({"source": str(path), "target": str(target), "bytes": path.stat().st_size})
            if not args.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)

    status = "dry-run" if args.dry_run else "copied"
    event_id = record_event(
        chat_name=args.chat,
        action="media_sync",
        direction="inbound",
        status=status,
        db_path=args.db,
        message=json.dumps(copied, ensure_ascii=False),
        metadata={"source_count": len(args.source), "file_count": len(copied), "dest": str(args.dest)},
    )
    print(json.dumps({"event_id": event_id, "status": status, "files": copied}, ensure_ascii=False, indent=2))
    return 0


def safe_relative(root: Path, path: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


if __name__ == "__main__":
    raise SystemExit(main())
