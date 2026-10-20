#!/usr/bin/env python3
"""Prepare Ubuntu intake cursors without replaying consumed Windows messages.

Run with receivers/workers stopped. This tool does not change transport selection,
launch a client, extract keys, send messages, or alter a task/delivery ledger.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3


def reconcile_cursor(rows, current_cursor, consumed_server_ids):
    """Advance only a contiguous prefix proved consumed in the other client."""
    cursor = current_cursor
    pending = []
    matched = 0
    for local_id, server_id in sorted(rows):
        if local_id <= current_cursor:
            continue
        consumed = str(server_id) not in {"", "0", "None"} and str(server_id) in consumed_server_ids
        if consumed:
            if pending:
                raise ValueError("Interleaved consumed/new messages require exact-row reconciliation")
            cursor = local_id
            matched += 1
        else:
            pending.append(local_id)
    return cursor, matched, pending


def plan_state(config, state, source, destination):
    table = config["message_table"]
    if not re.fullmatch(r"Msg_[a-fA-F0-9]{32}", table):
        raise ValueError("Invalid configured message table")
    updated = copy.deepcopy(state)
    cursors = updated.setdefault("message_db_cursors", {})
    if source.name not in cursors:
        raise ValueError("Missing source cursor; refusing to infer consumed history")
    with sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True) as conn:
        consumed = {
            str(row[0]) for row in conn.execute(
                f'SELECT server_id FROM "{table}" WHERE local_id <= ? AND server_id != 0',
                (cursors[source.name],),
            )
        }
    report = []
    shards = [p for p in destination.glob("message_*.db")
              if re.fullmatch(r"message_\d+\.db", p.name)]
    for db in sorted(shards, key=lambda p: int(p.stem.split("_")[-1])):
        with sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                continue
            rows = conn.execute(f'SELECT local_id,server_id FROM "{table}" ORDER BY local_id').fetchall()
        before = int(cursors.get(db.name, 0))
        after, matched, pending = reconcile_cursor(rows, before, consumed)
        cursors[db.name] = after
        report.append({"db": db.name, "before": before, "after": after,
                       "matched_consumed": matched, "pending": len(pending)})
    if not report:
        raise ValueError("No destination message table; refusing an empty cutover")
    updated["active_message_db"] = report[-1]["db"]
    updated["last_local_id"] = cursors[updated["active_message_db"]]
    return updated, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="append", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.backup_dir:
        parser.error("--apply requires a new --backup-dir")
    plans = []
    for path in args.config:
        config = json.loads(path.read_text())
        state_path = Path(config["state_path"])
        raw = state_path.read_bytes()
        state = json.loads(raw)
        if state.get("inflight_message_refs") or state.get("inflight_local_ids"):
            raise ValueError("An intake batch is in flight; finish it before cutover")
        updated, report = plan_state(config, state, args.source, args.destination)
        plans.append((state_path, raw, updated, {"config": path.name, "shards": report}))
    if args.apply:
        args.backup_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        for path, raw, _, _ in plans:
            if path.read_bytes() != raw:
                raise RuntimeError("Receiver state changed during planning; stop receivers first")
            backup = args.backup_dir / path.name
            backup.write_bytes(raw)
            backup.chmod(0o600)
        for path, _, updated, _ in plans:
            tmp = path.with_suffix(".cutover.tmp")
            tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
            tmp.chmod(0o600)
            tmp.replace(path)
        audit = args.backup_dir / "manifest.json"
        audit.write_text(json.dumps({
            "at": datetime.now(timezone.utc).isoformat(),
            "source": str(args.source), "destination": str(args.destination),
            "plans": [p[3] for p in plans],
        }, indent=2) + "\n")
        audit.chmod(0o600)
    print(json.dumps({"applied": args.apply, "plans": [p[3] for p in plans]}, indent=2))


if __name__ == "__main__":
    main()
