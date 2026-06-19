#!/usr/bin/env python3
"""Copy recently downloaded WeChat media/files into the local private mirror."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import re

from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DEST = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private" / "downloads"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat", required=True)
    parser.add_argument("--source", type=Path, action="append", default=[], help="WeChat download/cache directory. Repeatable.")
    parser.add_argument("--auto-source", action="store_true", help="Auto-discover local xwechat_files media folders.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--since-minutes", type=float, default=60)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-only", action="store_true", help="Print counts and errors instead of every copied file.")
    parser.add_argument("--record-empty", action="store_true", help="Record mirror events even when no files matched.")
    args = parser.parse_args()

    sources = list(args.source)
    if args.auto_source:
        sources.extend(discover_sources())
    sources = unique_existing_dirs(sources)
    if not sources:
        raise SystemExit("No media source directories. Pass --source or --auto-source.")

    cutoff = datetime.now() - timedelta(minutes=args.since_minutes)
    copied = []
    errors = []
    for source in sources:
        if not source.exists():
            continue
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                continue
            rel = safe_relative(source, path)
            target = args.dest / safe_component(args.chat) / source_bucket(source) / rel
            item = {"source": str(path), "target": str(target), "bytes": path.stat().st_size}
            copied.append(item)
            if not args.dry_run:
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists() and target.stat().st_size == path.stat().st_size:
                        item["status"] = "exists"
                        continue
                    shutil.copy2(path, target)
                    item["status"] = "copied"
                except OSError as exc:
                    item["status"] = "error"
                    item["error"] = str(exc)
                    errors.append(item)

    changed = [item for item in copied if item.get("status") in {"copied", "error"}]
    status = "dry-run" if args.dry_run else "copied-with-errors" if errors else "copied"
    if not (changed if not args.dry_run else copied) and not args.record_empty:
        payload = {"event_id": None, "status": "no-changes", "file_count": 0, "error_count": 0, "errors": []}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    event_id = record_event(
        chat_name=args.chat,
        action="media_sync",
        direction="inbound",
        status=status,
        db_path=args.db,
        message=json.dumps(copied if args.dry_run else changed, ensure_ascii=False),
        metadata={
            "source_count": len(sources),
            "sources": [str(path) for path in sources],
            "file_count": len(copied if args.dry_run else changed),
            "error_count": len(errors),
            "dest": str(args.dest),
            "layout": "<dest>/<chat>/<wechat-profile>/<category>/<relative-file>",
        },
    )
    if args.summary_only:
        payload = {"event_id": event_id, "status": status, "file_count": len(copied if args.dry_run else changed), "error_count": len(errors), "errors": errors}
    else:
        payload = {"event_id": event_id, "status": status, "files": copied if args.dry_run else changed, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def safe_relative(root: Path, path: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def discover_sources() -> list[Path]:
    base = Path.home() / "Documents" / "xwechat_files"
    candidates: list[Path] = []
    if not base.exists():
        return candidates
    for profile in base.iterdir():
        if not profile.is_dir():
            continue
        for relative in ("msg/file", "msg/video", "cache", "temp/ImageTemp"):
            path = profile / relative
            if path.is_dir():
                candidates.append(path)
    return candidates


def source_bucket(source: Path) -> Path:
    parts = source.expanduser().resolve().parts
    if "xwechat_files" in parts:
        index = parts.index("xwechat_files")
        profile = parts[index + 1] if len(parts) > index + 1 else "profile"
        relative = Path(*parts[index + 2 :]) if len(parts) > index + 2 else Path(source.name)
        return Path(safe_component(profile)) / Path(*[safe_component(part) for part in relative.parts])
    return Path(safe_component(source.name))


def safe_component(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "-", value.strip())
    return cleaned.strip("-") or "wechat"


def unique_existing_dirs(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if not resolved.is_dir() or resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
