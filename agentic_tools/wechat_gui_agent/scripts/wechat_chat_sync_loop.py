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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", default="", help="Comma-separated direct-chatops configs. Defaults to supervisor env.")
    parser.add_argument("--display", default=os.environ.get("WECHAT_DISPLAY", ":97"))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("WECHAT_CHAT_SYNC_INTERVAL", "45")))
    parser.add_argument("--pause", type=float, default=float(os.environ.get("WECHAT_CHAT_SYNC_PAUSE", "0.8")))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("WECHAT_CHAT_SYNC_TIMEOUT", "60")))
    parser.add_argument("--priority", default=os.environ.get("WECHAT_CHAT_SYNC_PRIORITY", ""), help="Comma-separated chat names to sync first.")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--only", action="append", default=[], help="Only sync a chat name. Repeatable.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F"))
    args = parser.parse_args()

    while True:
        results = sync_once(args)
        print(json.dumps({"checked_at": datetime.now().isoformat(timespec="seconds"), "results": results}, ensure_ascii=False), flush=True)
        if args.once or not args.loop:
            return 0 if all(item.get("ok") for item in results) else 1
        time.sleep(max(args.interval, 5.0))


def sync_once(args: argparse.Namespace) -> list[dict[str, Any]]:
    configs = prioritize_configs(discover_configs(args.configs), args.priority)
    only = {item.strip() for item in args.only if item.strip()}
    results: list[dict[str, Any]] = []
    for config_path in configs:
        try:
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
            results.append(open_chat_dry_run(args, chat_name, target))
            emit_target_event(results[-1])
        except Exception as exc:
            results.append({"config": str(config_path), "ok": False, "error": str(exc)[:500]})
            emit_target_event(results[-1])
    return results


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
            text=True,
            capture_output=True,
            timeout=max(args.timeout, args.pause * 20, 30.0),
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


if __name__ == "__main__":
    raise SystemExit(main())
