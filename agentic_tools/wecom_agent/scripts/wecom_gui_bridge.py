#!/usr/bin/env python3
"""Relay allowlisted external WeCom groups through the isolated Wine client.

Tencent's AI bot and ``wecom-cli msg`` transports remain preferred. This
separate fallback is used only when the tenant does not grant external-group
message permission. It never reads or controls personal WeChat.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
from typing import Any
from urllib import parse

from wecom_contract import LABAGENT_GUIDE_VERSION, labagent_welcome_message

try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - runtime doctor reports this clearly.
    Image = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_CONFIG = PRIVATE / "wecom_gui_bridge.local.json"
DEFAULT_STATE_DB = PRIVATE / "wecom_gui_bridge.local.sqlite"
DEFAULT_EVENT_ROOT = PRIVATE / "wecom-gui-events"
DEFAULT_QUEUE = PRIVATE / "wecom_task_queue.jsonl"
INGEST_SCRIPT = TOOL_ROOT / "scripts" / "wecom_ingest.py"
RECONNECT_OUTBOX_SCRIPT = TOOL_ROOT / "scripts" / "wecom_reconnect_outbox.py"
CLIPBOARD_SOURCE = TOOL_ROOT / "native" / "wecom_clipboard_utf8.c"
CLIPBOARD_EXE = PRIVATE / "bin" / "wecom_clipboard_utf8.exe"
WIN32_INPUT_SOURCE = TOOL_ROOT / "native" / "wecom_win32_input.c"
WIN32_INPUT_EXE = PRIVATE / "bin" / "wecom_win32_input.exe"
DEFAULT_PREFIX = PRIVATE / "wineprefix"
MAX_API_BODY = 2 * 1024 * 1024
SAFE_SEND_EXTENSIONS = {
    ".3mf", ".blend", ".csv", ".docx", ".dxf", ".gif", ".jpeg", ".jpg",
    ".json", ".kicad_pcb", ".kicad_sch", ".md", ".mov", ".mp3", ".mp4",
    ".pdf", ".png", ".step", ".stl", ".svg", ".txt", ".wav",
    ".xlsx", ".zip",
}
FILE_PICKER_TITLES = ("Select file/folder", "Select file")


@dataclass(frozen=True)
class Window:
    wid: str
    x: int
    y: int
    width: int
    height: int


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="Create ignored GUI relay configuration.")
    initialize.add_argument("--chat", action="append", dest="chats", default=[])
    initialize.add_argument("--force", action="store_true")
    search = initialize.add_mutually_exclusive_group()
    search.add_argument("--allow-search-fallback", action="store_true", default=None)
    search.add_argument("--no-search-fallback", action="store_false", dest="allow_search_fallback")
    initialize.add_argument("--json", action="store_true")

    for name, help_text in (
        ("status", "Show redacted GUI relay state."),
        ("once", "Run one bounded OCR intake cycle."),
        ("loop", "Run polling and the localhost delivery API."),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true")

    send = subparsers.add_parser("send", help="Send text to one exact allowlisted group.")
    send.add_argument("--chat", required=True)
    send.add_argument("--message", default="")
    send.add_argument("--file", action="append", dest="files", type=Path, default=[])
    send.add_argument("--task-id", default="manual")
    send.add_argument("--live", action="store_true", help="Actually click WeCom Send.")
    send.add_argument("--json", action="store_true")

    guide = subparsers.add_parser("guide", help="Send the idempotent LabAgent task guide.")
    guide.add_argument("--chat", required=True)
    guide.add_argument("--live", action="store_true", help="Actually click WeCom Send.")
    guide.add_argument("--json", action="store_true")

    messages = subparsers.add_parser("messages", help="Read the latest normalized inbound snapshot.")
    messages.add_argument("--chat", required=True)
    messages.add_argument("--after", type=int, default=0, help="Return messages after this cursor.")
    messages.add_argument("--limit", type=int, default=100)
    messages.add_argument("--json", action="store_true")

    chats = subparsers.add_parser("chats", help="List exact allowlisted GUI relay targets.")
    chats.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "init":
        payload = initialize_config(
            args.config,
            args.chats,
            force=args.force,
            allow_search_fallback=args.allow_search_fallback,
        )
    else:
        bridge = WeComGuiBridge(load_config(args.config), config_path=args.config)
        if args.command == "status":
            payload = bridge.status()
        elif args.command == "once":
            payload = bridge.poll_once()
        elif args.command == "send":
            if args.chat not in bridge.target_groups:
                payload = {"ok": False, "error": "chat is not allowlisted"}
            elif not args.message.strip() and not args.files:
                payload = {"ok": False, "error": "send requires --message and/or --file"}
            elif not args.live:
                payload = {
                    "ok": True,
                    "dry_run": True,
                    "chat": args.chat,
                    "message_bytes": len(args.message.encode("utf-8")),
                    "files": [str(path.expanduser().resolve()) for path in args.files],
                }
            else:
                payload = bridge.send(
                    args.chat,
                    args.message,
                    args.files,
                    task_id=args.task_id,
                )
        elif args.command == "guide":
            if args.chat not in bridge.target_groups:
                payload = {"ok": False, "error": "chat is not allowlisted"}
            elif not args.live:
                payload = {
                    "ok": True,
                    "dry_run": True,
                    "chat": args.chat,
                    "guide_version": LABAGENT_GUIDE_VERSION,
                    "message_bytes": len(labagent_welcome_message().encode("utf-8")),
                }
            else:
                payload = bridge.send_text(
                    args.chat,
                    labagent_welcome_message(),
                    task_id=f"labagent-guide:{LABAGENT_GUIDE_VERSION}:{args.chat}",
                )
        elif args.command == "messages":
            payload = bridge.read_messages(args.chat, after=args.after, limit=args.limit)
        elif args.command == "chats":
            payload = bridge.list_chats()
        else:
            bridge.serve_forever()
            return 0
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") else 1


def initialize_config(
    path: Path,
    chats: list[str],
    *,
    force: bool = False,
    allow_search_fallback: bool | None = None,
) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if path.is_file() and not force:
        existing = load_config(path)
    target_groups = unique_nonempty([*(existing.get("target_groups") or []), *chats])
    if not target_groups:
        target_groups = ["LabAgent"]
    payload = {
        "schema_version": 1,
        "enabled": True,
        "target_groups": target_groups,
        "account_id": str(existing.get("account_id") or "external-gui"),
        "display": str(existing.get("display") or ":92"),
        "wineprefix": str(existing.get("wineprefix") or DEFAULT_PREFIX),
        "poll_seconds": bounded_float(existing.get("poll_seconds"), 4.0, 2.0, 120.0),
        "passive_poll_enabled": bool(existing.get("passive_poll_enabled", True)),
        "active_rescan_seconds": bounded_float(
            existing.get("active_rescan_seconds"), 180.0, 30.0, 3600.0
        ),
        "action_pause_seconds": bounded_float(existing.get("action_pause_seconds"), 0.8, 0.2, 5.0),
        "failure_backoff_seconds": bounded_float(
            existing.get("failure_backoff_seconds"), 30.0, 5.0, 900.0
        ),
        "max_failure_backoff_seconds": bounded_float(
            existing.get("max_failure_backoff_seconds"), 300.0, 30.0, 3600.0
        ),
        "local_api_host": "127.0.0.1",
        "local_api_port": bounded_int(existing.get("local_api_port"), 19580, 1024, 65535),
        "local_api_token": str(existing.get("local_api_token") or secrets.token_hex(32)),
        "state_db": str(existing.get("state_db") or DEFAULT_STATE_DB),
        "event_root": str(existing.get("event_root") or DEFAULT_EVENT_ROOT),
        "queue": str(existing.get("queue") or DEFAULT_QUEUE),
        "initial_backfill": "seed",
        "allow_search_fallback": (
            bool(existing.get("allow_search_fallback", False))
            if allow_search_fallback is None
            else bool(allow_search_fallback)
        ),
        "max_send_file_bytes": bounded_int(
            existing.get("max_send_file_bytes"), 100 * 1024 * 1024, 1, 1024 * 1024 * 1024
        ),
        "recover_expired_on_reconnect": bool(existing.get("recover_expired_on_reconnect", True)),
        "reconnect_recovery_max_age_seconds": bounded_int(
            existing.get("reconnect_recovery_max_age_seconds"), 12 * 60 * 60, 0, 7 * 24 * 60 * 60
        ),
        "reconnect_recovery_limit": bounded_int(existing.get("reconnect_recovery_limit"), 1, 0, 20),
        "reconnect_stabilization_seconds": bounded_float(
            existing.get("reconnect_stabilization_seconds"), 120.0, 10.0, 3600.0
        ),
        "auth_quarantine_seconds": bounded_float(
            existing.get("auth_quarantine_seconds"), 300.0, 30.0, 24 * 60 * 60.0
        ),
        "auth_recovery_stabilization_seconds": bounded_float(
            existing.get("auth_recovery_stabilization_seconds"), 60.0, 10.0, 3600.0
        ),
        "allow_verified_file_send_during_device_warning": bool(
            existing.get("allow_verified_file_send_during_device_warning", False)
        ),
        "send_min_interval_seconds": bounded_float(
            existing.get("send_min_interval_seconds"), 12.0, 0.0, 300.0
        ),
        "file_send_min_interval_seconds": bounded_float(
            existing.get("file_send_min_interval_seconds"), 30.0, 0.0, 900.0
        ),
        "composer_input_backend": (
            "native"
            if str(existing.get("composer_input_backend") or "").casefold() == "native"
            else "xdotool"
        ),
    }
    write_private_json(path, payload)
    return {
        "ok": True,
        "config_path": str(path),
        "target_groups": target_groups,
        "allow_search_fallback": payload["allow_search_fallback"],
        "local_api_url": f"http://127.0.0.1:{payload['local_api_port']}",
    }


class WeComGuiBridge:
    def __init__(self, config: dict[str, Any], *, config_path: Path = DEFAULT_CONFIG) -> None:
        self.config = config
        self.config_path = config_path.resolve()
        self.display = str(config.get("display") or ":92")
        self.prefix = Path(str(config.get("wineprefix") or DEFAULT_PREFIX)).expanduser().resolve()
        self.state_db = Path(str(config.get("state_db") or DEFAULT_STATE_DB)).expanduser().resolve()
        self.event_root = Path(str(config.get("event_root") or DEFAULT_EVENT_ROOT)).expanduser().resolve()
        self.queue = Path(str(config.get("queue") or DEFAULT_QUEUE)).expanduser().resolve()
        self.target_groups = unique_nonempty(config.get("target_groups") or [])
        self.pause = bounded_float(config.get("action_pause_seconds"), 0.8, 0.2, 5.0)
        self.lock_path = PRIVATE / "wecom_gui_bridge.lock"
        self.runtime_dir = self.event_root / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._stop = threading.Event()
        self._poll_lock = threading.Lock()
        self._client_was_visible = False
        self._poll_cursor = 0
        self._active_scan_remaining = 0
        self._chat_failures: dict[str, int] = {}
        self._chat_retry_at: dict[str, float] = {}
        init_state_db(self.state_db)

    def status(self) -> dict[str, Any]:
        window = self.find_window(required=False)
        with sqlite3.connect(self.state_db) as conn:
            rows = conn.execute(
                "SELECT chat_name, updated_at FROM snapshots ORDER BY chat_name"
            ).fetchall()
            runtime = dict(
                conn.execute(
                    "SELECT key, value FROM runtime WHERE key IN "
                    "('auth_blocker', 'auth_quarantine_until_epoch', 'chat_ready', "
                    "'last_error', 'last_poll_at', 'last_ready_at', 'last_active_poll_epoch')"
                ).fetchall()
            )
        last_error = str(runtime.get("last_error") or "")[:500]
        auth_blocker = str(runtime.get("auth_blocker") or "")[:200]
        ready_chats = [
            chat
            for chat in self.target_groups
            if get_runtime(self.state_db, f"chat_ready:{safe_slug(chat)}") == "1"
        ]
        security_cooldown = seconds_until_epoch(runtime.get("auth_quarantine_until_epoch"))
        chat_ready = (
            bool(window)
            and len(ready_chats) == len(self.target_groups)
            and not auth_blocker
            and security_cooldown <= 0
        )
        closed_loop_state = (
            "ready"
            if chat_ready
            else "degraded_ready"
            if window and ready_chats and not auth_blocker and security_cooldown <= 0
            else "security_verification_required"
            if auth_blocker or security_cooldown > 0
            else "chat_verification_pending"
            if window
            else "login_required"
        )
        return {
            "ok": True,
            "api_version": 1,
            "enabled": bool(self.config.get("enabled", True)),
            "client_visible": bool(window),
            "chat_ready": chat_ready,
            "ready_chat_count": len(ready_chats),
            "closed_loop_state": closed_loop_state,
            "display": self.display,
            "target_groups": self.target_groups,
            "seeded_groups": [{"chat": row[0], "updated_at": row[1]} for row in rows],
            "auth_blocker": auth_blocker,
            "security_cooldown_remaining_seconds": security_cooldown,
            "last_error": last_error,
            "last_poll_at": str(runtime.get("last_poll_at") or ""),
            "last_ready_at": str(runtime.get("last_ready_at") or ""),
            "last_active_poll_epoch": str(runtime.get("last_active_poll_epoch") or ""),
            "passive_poll_enabled": bool(self.config.get("passive_poll_enabled", True)),
            "local_api_url": f"http://127.0.0.1:{bounded_int(self.config.get('local_api_port'), 19580, 1024, 65535)}",
            "transport": "wecom_gui_only",
            "personal_wechat_fallback": False,
            "capabilities": {
                "list_chats": "GET /v1/chats",
                "read_messages": "GET /v1/messages?chat_id=gui:<name>&after=<cursor>&limit=<n>",
                "send": "POST /v1/send",
                "text": True,
                "files": True,
                "cursor_reads": True,
                "idempotent_sends": True,
            },
        }

    def health(self) -> dict[str, Any]:
        status = self.status()
        return {
            "ok": bool(status.get("ok")),
            "api_version": status.get("api_version"),
            "client_visible": status.get("client_visible"),
            "chat_ready": status.get("chat_ready"),
            "closed_loop_state": status.get("closed_loop_state"),
            "transport": status.get("transport"),
            "capabilities": status.get("capabilities"),
        }

    def poll_once(self) -> dict[str, Any]:
        if not self._poll_lock.acquire(blocking=False):
            return {"ok": True, "skipped": "poll_already_running", "processed": 0}
        try:
            security_pause = self.security_pause_state()
            if security_pause:
                set_runtime(self.state_db, "last_poll_at", now_iso())
                return {
                    "ok": True,
                    "skipped": "security_quarantine",
                    "processed": 0,
                    **security_pause,
                }
            selected = self.next_due_chat()
            if selected is None:
                set_runtime(self.state_db, "last_poll_at", now_iso())
                return {"ok": True, "skipped": "chat_failure_backoff", "processed": 0}
            with self.serialized_gui():
                outcomes = [self.poll_chat(selected)]
            errors = [item for item in outcomes if not item.get("ok")]
            processed = sum(int(item.get("processed") or 0) for item in outcomes)
            if errors:
                self.defer_failed_chat(selected)
            else:
                self._chat_failures.pop(selected, None)
                self._chat_retry_at.pop(selected, None)
            set_runtime(self.state_db, "last_poll_at", now_iso())
            set_runtime(self.state_db, "last_error", "" if not errors else json.dumps(errors, ensure_ascii=False)[:1000])
            set_runtime(self.state_db, f"chat_ready:{safe_slug(selected)}", "0" if errors else "1")
            if not errors:
                set_runtime(self.state_db, "last_ready_at", now_iso())
                set_runtime(self.state_db, "last_active_poll_epoch", str(time.time()))
            return {"ok": not errors, "processed": processed, "groups": outcomes}
        except Exception as exc:
            message = f"{type(exc).__name__}: {str(exc)[:800]}"
            set_runtime(self.state_db, "last_poll_at", now_iso())
            set_runtime(self.state_db, "last_error", message)
            selected = locals().get("selected")
            if isinstance(selected, str):
                self.defer_failed_chat(selected)
                set_runtime(self.state_db, f"chat_ready:{safe_slug(selected)}", "0")
            if "WECOM_GUI_AUTH_REQUIRED:" in message:
                self.activate_auth_quarantine(
                    message.split("WECOM_GUI_AUTH_REQUIRED:", 1)[1].strip()[:200]
                )
            return {"ok": False, "processed": 0, "error": message}
        finally:
            self._poll_lock.release()

    def poll_cycle(self) -> dict[str, Any]:
        """Observe passively and touch the GUI only after a visible change."""
        window = self.find_window(required=False)
        if window is None:
            self._client_was_visible = False
            self._active_scan_remaining = 0
            set_runtime(self.state_db, "reconnect_ready_since_epoch", "")
            set_runtime(self.state_db, "last_poll_at", now_iso())
            return {"ok": False, "processed": 0, "error": "WeCom client is not visible"}

        with self.serialized_gui():
            screenshot = self.capture_screen("passive-state-check")
            signature = self.passive_screen_signature(screenshot, window)
            previous = get_runtime(self.state_db, "passive_screen_signature")
            changed = not previous or not secrets.compare_digest(previous, signature)
            stored_blocker = get_runtime(self.state_db, "auth_blocker")
            if changed or stored_blocker or self.auth_quarantine_remaining() > 0:
                blocker = self.detect_auth_blocker_from_screen(window, screenshot)
                if blocker:
                    self.activate_auth_quarantine(blocker)
                    set_runtime(self.state_db, "passive_screen_signature", signature)
                    set_runtime(self.state_db, "last_poll_at", now_iso())
                    return {
                        "ok": True,
                        "skipped": "security_quarantine",
                        "processed": 0,
                        **self.security_pause_state(),
                    }
                recovery = self.advance_auth_recovery()
                if recovery is not None:
                    set_runtime(self.state_db, "passive_screen_signature", signature)
                    set_runtime(self.state_db, "last_poll_at", now_iso())
                    return recovery
            set_runtime(self.state_db, "passive_screen_signature", signature)

        last_active = runtime_float(self.state_db, "last_active_poll_epoch")
        rescan_seconds = bounded_float(
            self.config.get("active_rescan_seconds"), 180.0, 30.0, 3600.0
        )
        periodic_rescan_due = last_active <= 0 or time.time() - last_active >= rescan_seconds
        if (changed or periodic_rescan_due) and self._active_scan_remaining <= 0:
            self._active_scan_remaining = max(1, len(self.target_groups))
        if self._active_scan_remaining <= 0:
            set_runtime(self.state_db, "last_poll_at", now_iso())
            return {"ok": True, "skipped": "screen_unchanged", "processed": 0}

        result = self.poll_once()
        if result.get("groups"):
            self._active_scan_remaining = max(0, self._active_scan_remaining - 1)
            self.record_passive_screen_signature()
        return result

    def passive_screen_signature(self, screenshot: Path, window: Window) -> str:
        if Image is None:
            return sha256_file(screenshot)
        with Image.open(screenshot).convert("L") as image:
            # Exclude the composer and desktop clock. Conversation-list unread
            # badges and the visible chat tail remain inside this stable region.
            observed = image.crop(
                (
                    window.x + int(window.width * 0.05),
                    window.y + int(window.height * 0.08),
                    window.x + int(window.width * 0.86),
                    window.y + int(window.height * 0.74),
                )
            )
            observed = observed.resize((96, 64), Image.Resampling.BILINEAR)
            quantized = bytes((value // 16) * 16 for value in observed.tobytes())
        return hashlib.sha256(quantized).hexdigest()

    def record_passive_screen_signature(self) -> None:
        window = self.find_window(required=False)
        if window is None:
            return
        with self.serialized_gui():
            screenshot = self.capture_screen("passive-state-baseline")
            signature = self.passive_screen_signature(screenshot, window)
            set_runtime(self.state_db, "passive_screen_signature", signature)

    def activate_auth_quarantine(self, blocker: str) -> None:
        now = time.time()
        current_until = runtime_float(self.state_db, "auth_quarantine_until_epoch")
        config = getattr(self, "config", {})
        duration = bounded_float(
            config.get("auth_quarantine_seconds"), 300.0, 30.0, 24 * 60 * 60.0
        )
        if current_until <= now:
            current_until = now + duration
        set_runtime(self.state_db, "auth_blocker", str(blocker)[:200])
        set_runtime(self.state_db, "auth_quarantine_until_epoch", str(current_until))
        set_runtime(self.state_db, "auth_recovery_candidate_since_epoch", "")
        set_runtime(self.state_db, "reconnect_ready_since_epoch", "")
        for chat in self.target_groups:
            set_runtime(self.state_db, f"chat_ready:{safe_slug(chat)}", "0")
        self._client_was_visible = False
        self._active_scan_remaining = 0

    def auth_quarantine_remaining(self) -> int:
        return seconds_until_epoch(get_runtime(self.state_db, "auth_quarantine_until_epoch"))

    def security_pause_state(self) -> dict[str, Any]:
        blocker = get_runtime(self.state_db, "auth_blocker")
        remaining = self.auth_quarantine_remaining()
        if not blocker and remaining <= 0:
            return {}
        return {
            "auth_blocker": blocker or "security_cooldown",
            "security_cooldown_remaining_seconds": remaining,
        }

    def blocker_prevents_operation(self, blocker: str, operation: str) -> bool:
        if not blocker:
            return False
        return not (
            operation == "file"
            and blocker == "device_environment_abnormal"
            and bool(
                getattr(self, "config", {}).get(
                    "allow_verified_file_send_during_device_warning", False
                )
            )
        )

    def require_gui_input_allowed(self, operation: str = "text") -> None:
        state = self.security_pause_state()
        if state:
            blocker = str(state.get("auth_blocker") or "")
            if not self.blocker_prevents_operation(blocker, operation):
                return
            raise RuntimeError(
                "WECOM_GUI_AUTH_REQUIRED: "
                f"{state['auth_blocker']} (cooldown {state['security_cooldown_remaining_seconds']}s)"
            )

    def advance_auth_recovery(self) -> dict[str, Any] | None:
        state = self.security_pause_state()
        if not state:
            return None
        remaining = int(state.get("security_cooldown_remaining_seconds") or 0)
        if remaining > 0:
            set_runtime(self.state_db, "auth_recovery_candidate_since_epoch", "")
            return {"ok": True, "skipped": "security_quarantine", "processed": 0, **state}
        now = time.time()
        candidate = runtime_float(self.state_db, "auth_recovery_candidate_since_epoch")
        if candidate <= 0:
            set_runtime(self.state_db, "auth_recovery_candidate_since_epoch", str(now))
            candidate = now
        stabilization = bounded_float(
            getattr(self, "config", {}).get("auth_recovery_stabilization_seconds"),
            60.0,
            10.0,
            3600.0,
        )
        stable_for = max(0.0, now - candidate)
        if stable_for < stabilization:
            return {
                "ok": True,
                "skipped": "auth_recovery_stabilizing",
                "processed": 0,
                "stabilization_remaining_seconds": int(stabilization - stable_for + 0.999),
            }
        set_runtime(self.state_db, "auth_blocker", "")
        set_runtime(self.state_db, "auth_quarantine_until_epoch", "")
        set_runtime(self.state_db, "auth_recovery_candidate_since_epoch", "")
        self._active_scan_remaining = max(1, len(self.target_groups))
        return None

    def next_due_chat(self) -> str | None:
        if not self.target_groups:
            return None
        now = time.monotonic()
        count = len(self.target_groups)
        for offset in range(count):
            index = (self._poll_cursor + offset) % count
            chat = self.target_groups[index]
            if now >= self._chat_retry_at.get(chat, 0.0):
                self._poll_cursor = (index + 1) % count
                return chat
        return None

    def defer_failed_chat(self, chat: str) -> None:
        failures = self._chat_failures.get(chat, 0) + 1
        self._chat_failures[chat] = failures
        base = bounded_float(self.config.get("failure_backoff_seconds"), 30.0, 5.0, 900.0)
        maximum = bounded_float(
            self.config.get("max_failure_backoff_seconds"), 300.0, 30.0, 3600.0
        )
        self._chat_retry_at[chat] = time.monotonic() + min(maximum, base * (2 ** (failures - 1)))

    def poll_chat(self, chat: str) -> dict[str, Any]:
        window = self.ensure_chat(chat)
        self.scroll_chat_to_bottom(window)
        screenshot = self.capture_screen(f"poll-{safe_slug(chat)}")
        records, crop_path = self.extract_inbound_records(screenshot, window, chat)
        inbound = [str(record.get("text") or "") for record in records]
        old = load_snapshot(self.state_db, chat)
        image_hash = sha256_file(crop_path)
        if old is None:
            save_snapshot(self.state_db, chat, inbound, image_hash)
            return {"ok": True, "chat": chat, "processed": 0, "seeded": len(inbound)}
        if not inbound:
            return {"ok": True, "chat": chat, "processed": 0, "preserved": len(old[0])}
        new_messages, overlap = new_message_suffix(old[0], inbound)
        if not new_messages:
            save_snapshot(self.state_db, chat, inbound, image_hash)
            return {"ok": True, "chat": chat, "processed": 0, "overlap": overlap}
        if overlap == 0 and old[0]:
            reused = [
                current
                for current in inbound
                if any(similar_text(current, prior) >= 0.82 for prior in old[0])
            ]
            if reused:
                return {
                    "ok": False,
                    "chat": chat,
                    "processed": 0,
                    "error": "OCR viewport changed ambiguously; refusing replay of previously seen text",
                }
        new_records = records[-len(new_messages) :]
        queued = False
        replied = False
        pending_replies: list[tuple[str, str]] = []
        for batch in coalesce_sender_records(new_records):
            batch_messages = [str(record.get("text") or "") for record in batch]
            sender_label = str(batch[0].get("sender_label") or "")
            sender_fingerprint = str(batch[0].get("sender_fingerprint") or "")
            sender_confidence = str(batch[0].get("sender_confidence") or "unresolved")
            event_path = self.build_event(
                chat,
                batch_messages,
                image_hash,
                sender_label=sender_label,
                sender_fingerprint=sender_fingerprint,
                sender_confidence=sender_confidence,
            )
            record_inbound_messages(self.state_db, chat, batch_messages, event_path, image_hash)
            try:
                result = self.invoke_ingest(event_path)
            except Exception as exc:
                mark_event_ingest(
                    self.state_db,
                    event_path,
                    status="failed",
                    error=f"{type(exc).__name__}: {str(exc)[:500]}",
                )
                raise
            mark_event_ingest(self.state_db, event_path, status="ingested")
            queued = queued or bool(result.get("queued"))
            response = str(result.get("reply") or result.get("ack") or "").strip()
            if response:
                pending_replies.append((response, f"ingress:{event_path.parent.name}"))

        # Ingest is the durable boundary. Checkpoint the inbound viewport before
        # any GUI send so an uncertain send result cannot replay the request and
        # emit the same acknowledgement again on the next poll.
        save_snapshot(self.state_db, chat, inbound, image_hash)
        for response, task_id in pending_replies:
            self.send_text_locked(chat, response, task_id=task_id)
            replied = True
        return {
            "ok": True,
            "chat": chat,
            "processed": len(new_messages),
            "queued": queued,
            "replied": replied,
        }

    def scroll_chat_to_bottom(self, window: Window) -> None:
        """Keep polling on the live tail so old viewport history is not replayed."""
        command = [
            "mousemove",
            str(window.x + int(window.width * 0.62)),
            str(window.y + int(window.height * 0.52)),
        ]
        for _ in range(24):
            command.extend(["click", "5"])
        self.run_xdotool(command)
        time.sleep(0.20)

    def send_text(self, chat: str, text: str, *, task_id: str) -> dict[str, Any]:
        if chat not in self.target_groups:
            raise RuntimeError("refusing send to a non-allowlisted WeCom GUI group")
        with self.serialized_gui():
            try:
                return self.send_text_locked(chat, text, task_id=task_id)
            except Exception as exc:
                self.quarantine_from_exception(exc)
                raise

    def send_files(self, chat: str, paths: list[Path], *, task_id: str) -> dict[str, Any]:
        if chat not in self.target_groups:
            raise RuntimeError("refusing file send to a non-allowlisted WeCom GUI group")
        with self.serialized_gui():
            result = self.send_files_locked(chat, paths, task_id=task_id)
            self.quarantine_from_send_result(result)
            return result

    def send(
        self,
        chat: str,
        text: str,
        paths: list[Path],
        *,
        task_id: str,
    ) -> dict[str, Any]:
        if chat not in self.target_groups:
            raise RuntimeError("refusing send to a non-allowlisted WeCom GUI group")
        with self.serialized_gui():
            try:
                pause_state = self.security_pause_state()
                blocker = str(pause_state.get("auth_blocker") or "")
                if paths and blocker and not self.blocker_prevents_operation(blocker, "file"):
                    file_result = self.send_files_locked(chat, paths, task_id=task_id)
                    text_result = empty_send_result()
                    if text.strip():
                        text_result = {
                            "ok": False,
                            "sent_messages": [],
                            "sent_files": [],
                            "errors": [
                                {
                                    "error": (
                                        "RuntimeError: WECOM_GUI_AUTH_REQUIRED: "
                                        f"{blocker}"
                                    )
                                }
                            ],
                        }
                    result = merge_send_results(text_result, file_result)
                    self.quarantine_from_send_result(result)
                    return result
                text_result = (
                    self.send_text_locked(chat, text, task_id=task_id)
                    if text.strip()
                    else empty_send_result()
                )
                file_result = (
                    self.send_files_locked(chat, paths, task_id=task_id)
                    if paths
                    else empty_send_result()
                )
                result = merge_send_results(text_result, file_result)
                self.quarantine_from_send_result(result)
                return result
            except Exception as exc:
                self.quarantine_from_exception(exc)
                raise

    def quarantine_from_send_result(self, result: dict[str, Any]) -> None:
        for error in result.get("errors") or []:
            self.quarantine_from_exception(str(error.get("error") or ""))

    def quarantine_from_exception(self, error: Any) -> None:
        message = str(error)
        marker = "WECOM_GUI_AUTH_REQUIRED:"
        if marker in message:
            self.activate_auth_quarantine(message.split(marker, 1)[1].strip()[:200])

    def list_chats(self) -> dict[str, Any]:
        return {
            "ok": True,
            "transport": "wecom_gui",
            "chats": [
                {"chat_id": f"gui:{chat}", "chat_name": chat, "chat_type": "group"}
                for chat in self.target_groups
            ],
        }

    def read_messages(self, chat: str, *, after: int = 0, limit: int = 100) -> dict[str, Any]:
        if chat not in self.target_groups:
            return {"ok": False, "error": "chat is not allowlisted"}
        snapshot = load_snapshot(self.state_db, chat)
        cursor = max(0, int(after))
        bounded_limit = bounded_int(limit, 100, 1, 500)
        items = read_inbound_messages(self.state_db, chat, after=cursor, limit=bounded_limit)
        next_cursor = int(items[-1]["cursor"]) if items else cursor
        has_more = inbound_messages_exist_after(self.state_db, chat, next_cursor)
        return {
            "ok": True,
            "chat": chat,
            "chat_id": f"gui:{chat}",
            "messages": [str(item["text"]) for item in items],
            "items": items,
            "cursor": next_cursor,
            "has_more": has_more,
            "visible_snapshot": snapshot[0] if snapshot else [],
            "seeded": snapshot is not None,
        }

    def delivery_status(
        self,
        chat: str,
        text: str,
        paths: list[Path],
        *,
        task_id: str,
    ) -> dict[str, Any]:
        """Resolve exact text/file components from the durable GUI ledger."""
        if chat not in self.target_groups:
            raise RuntimeError("refusing delivery status for a non-allowlisted WeCom GUI group")
        sent_messages: list[str] = []
        pending_messages: list[str] = []
        for index, chunk in enumerate(chunk_text(text, 1800)):
            delivery_key = short_hash(f"{chat}:{task_id}:{index}:{chunk}")
            target = sent_messages if delivery_done(self.state_db, delivery_key, chat) else pending_messages
            target.append(chunk)

        sent_files: list[str] = []
        pending_files: list[str] = []
        for index, source in enumerate(paths):
            path = self.validate_send_file(source)
            stat = path.stat()
            delivery_key = short_hash(
                f"{chat}:{task_id}:file:{index}:{path}:{stat.st_size}:{stat.st_mtime_ns}"
            )
            target = sent_files if delivery_done(self.state_db, delivery_key, chat) else pending_files
            target.append(str(path))

        complete = not pending_messages and not pending_files
        return {
            "ok": True,
            "complete": complete,
            "transport": "wecom_gui",
            "sent_messages": sent_messages,
            "pending_messages": pending_messages,
            "mentioned_users": [],
            "sent_files": sent_files,
            "sent_file_count": len(sent_files),
            "pending_files": pending_files,
        }

    def send_text_locked(self, chat: str, text: str, *, task_id: str) -> dict[str, Any]:
        chunks = chunk_text(text, 1800)
        sent: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            delivery_key = short_hash(f"{chat}:{task_id}:{index}:{chunk}")
            if delivery_done(self.state_db, delivery_key, chat):
                continue
            self.pace_gui_send("text")
            self.ensure_chat(chat)
            window = self.find_window()
            self.set_clipboard(chunk)
            # Keep replacement and paste in one xdotool key command. Wine can
            # otherwise drop focus between short-lived key processes even
            # though CF_UNICODETEXT itself is correct.
            self.composer_keys(window, "ctrl+a", "ctrl+v")
            time.sleep(max(0.25, self.pause / 2))
            composed = self.capture_screen(f"composed-{delivery_key}")
            if not self.composer_text_matches(window, chunk, delivery_key):
                self.clear_composer(window)
                raise RuntimeError(
                    "WECOM_GUI_COMPOSE_UNVERIFIED: composer did not contain the exact Unicode message"
                )
            self.composer_keys(window, "alt+s")
            time.sleep(self.pause)
            if not self.composer_is_empty(window, delivery_key):
                raise RuntimeError("WECOM_GUI_SEND_UNCERTAIN: composer did not clear after Send")
            sent_screen = self.capture_screen(f"sent-{delivery_key}")
            remember_delivery(self.state_db, delivery_key, chat, chunk)
            sent.append(
                {
                    "bytes": len(chunk.encode("utf-8")),
                    "verified": True,
                    "composed_evidence": str(composed),
                    "sent_evidence": str(sent_screen),
                }
            )
        return {"ok": True, "sent_messages": sent, "sent_files": [], "errors": []}

    def send_files_locked(self, chat: str, paths: list[Path], *, task_id: str) -> dict[str, Any]:
        sent_files: list[str] = []
        errors: list[dict[str, str]] = []
        for index, source in enumerate(paths):
            staging_dir: Path | None = None
            try:
                path = self.validate_send_file(source)
                stat = path.stat()
                delivery_key = short_hash(f"{chat}:{task_id}:file:{index}:{path}:{stat.st_size}:{stat.st_mtime_ns}")
                if delivery_done(self.state_db, delivery_key, chat):
                    sent_files.append(str(path))
                    continue
                self.pace_gui_send("file")
                self.ensure_chat(chat, operation="file")
                window = self.find_window()
                before_screen = self.capture_screen(f"file-before-{delivery_key}")
                before_text = self.read_chat_history_text(before_screen, window, delivery_key)
                staged, staging_dir = self.stage_send_file(path, delivery_key)
                picker_evidence = self.compose_staged_file_with_picker(
                    window,
                    staged,
                    staging_dir,
                    delivery_key,
                )
                window = self.ensure_chat(chat, operation="file")
                composed = self.capture_screen(f"file-composed-picker-{delivery_key}")
                if not self.composer_contains_filename(composed, window, staged.name, delivery_key):
                    raise RuntimeError(
                        "WECOM_GUI_COMPOSE_UNVERIFIED: WeCom did not compose the exact staged artifact"
                    )
                self.composer_keys(window, "alt+s")
                sent_screen = self.wait_for_file_in_history(
                    window,
                    staged.name,
                    before_text=before_text,
                    delivery_key=delivery_key,
                )
                remember_delivery(self.state_db, delivery_key, chat, str(path))
                sent_files.append(str(path))
                set_runtime(
                    self.state_db,
                    f"delivery_evidence:{delivery_key}",
                    json.dumps(
                        {
                            "picker": str(picker_evidence),
                            "composer": str(composed),
                            "history": str(sent_screen),
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception as exc:
                errors.append({"path": str(source), "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            finally:
                if staging_dir is not None:
                    shutil.rmtree(staging_dir, ignore_errors=True)
        return {"ok": not errors, "sent_messages": [], "sent_files": sent_files, "errors": errors}

    def pace_gui_send(self, kind: str) -> None:
        """Space GUI attempts without making callers retry against the desktop."""
        if kind not in {"text", "file"}:
            raise ValueError("unsupported WeCom GUI send kind")
        self.require_gui_input_allowed(kind)
        config = getattr(self, "config", {})
        minimum = bounded_float(config.get("send_min_interval_seconds"), 12.0, 0.0, 300.0)
        now = time.time()
        delays = [minimum - (now - runtime_float(self.state_db, "last_gui_send_attempt_epoch"))]
        if kind == "file":
            file_minimum = bounded_float(
                config.get("file_send_min_interval_seconds"), 30.0, 0.0, 900.0
            )
            delays.append(
                file_minimum - (now - runtime_float(self.state_db, "last_gui_file_send_attempt_epoch"))
            )
        delay = max(0.0, *delays)
        if delay > 0:
            time.sleep(delay)
        self.require_gui_input_allowed(kind)
        attempted_at = str(time.time())
        set_runtime(self.state_db, "last_gui_send_attempt_epoch", attempted_at)
        if kind == "file":
            set_runtime(self.state_db, "last_gui_file_send_attempt_epoch", attempted_at)

    def validate_send_file(self, source: Path) -> Path:
        path = source.expanduser().resolve()
        if not path.is_file():
            raise RuntimeError("artifact does not exist or is not a regular file")
        if not path.is_relative_to(ROOT):
            raise RuntimeError("artifact is outside the LabCanvas repository")
        relative = path.relative_to(ROOT)
        if any(part in {".git", ".private"} for part in relative.parts):
            raise RuntimeError("private repository paths cannot be sent")
        if path.suffix.casefold() not in SAFE_SEND_EXTENSIONS:
            raise RuntimeError(f"artifact extension is not allowlisted: {path.suffix}")
        max_bytes = bounded_int(self.config.get("max_send_file_bytes"), 100 * 1024 * 1024, 1, 1024 * 1024 * 1024)
        if path.stat().st_size > max_bytes:
            raise RuntimeError("artifact exceeds the configured WeCom GUI size limit")
        return path

    def ensure_chat(self, chat: str, *, operation: str = "text") -> Window:
        if chat not in self.target_groups:
            raise RuntimeError("chat is not allowlisted")
        window = self.find_window()
        blocker = self.detect_auth_blocker(window)
        if self.blocker_prevents_operation(blocker, operation):
            raise RuntimeError(f"WECOM_GUI_AUTH_REQUIRED: {blocker}")
        # A bubble-copy probe can leave a context menu open. Dismiss it with a
        # neutral pointer click; Escape can close the main WeCom window when no
        # popup owns the key.
        self.dismiss_transient_overlays(window)
        if self.current_title_matches(window, chat):
            return window
        current_chat = self.current_allowlisted_chat(window, exclude=chat)
        if self.open_from_visible_list(window, chat):
            window = self.find_window()
            if self.current_title_matches(window, chat):
                return window
            if current_chat and self.open_from_visible_list_keyboard(window, current_chat, chat):
                window = self.find_window()
                if self.current_title_matches(window, chat):
                    return window
            raise RuntimeError(f"visible WeCom conversation did not open exact chat {chat!r}")
        if not bool(self.config.get("allow_search_fallback", False)):
            raise RuntimeError(f"exact WeCom chat {chat!r} is not visible; search fallback is disabled")
        self.click(window.x + int(window.width * 0.18), window.y + int(window.height * 0.06))
        self.key("ctrl+a")
        self.set_clipboard(chat)
        self.key("ctrl+v")
        time.sleep(self.pause)
        self.click(window.x + int(window.width * 0.20), window.y + int(window.height * 0.33))
        time.sleep(self.pause)
        # Selecting a Wine-rendered search result opens the chat behind the
        # search layer. Close its exact native window before title verification.
        # The nearby main-toolbar `+` opens Start Group Chat, so it must never
        # be used as an approximate close target.
        self.close_stale_native_overlays()
        time.sleep(max(0.25, self.pause / 2))
        window = self.find_window()
        if not self.current_title_matches(window, chat):
            raise RuntimeError(f"exact WeCom GUI chat title did not match {chat!r}")
        return window

    def detect_auth_blocker(self, window: Window) -> str:
        screenshot = self.capture_screen("auth-state-check")
        return self.detect_auth_blocker_from_screen(window, screenshot)

    def detect_auth_blocker_from_screen(self, window: Window, screenshot: Path) -> str:
        crop = self.crop(
            screenshot,
            (window.x, window.y, window.width, window.height),
            self.runtime_dir / "auth-state-check.png",
        )
        observed = normalize_text(self.ocr(crop, psm=11)).casefold()
        patterns = (
            ("device_environment_abnormal", ("deviceenvironmentisabnormal", "环境异常")),
            ("security_verification_required", ("securityverification", "安全验证")),
            ("qr_login_required", ("scantheqrcode", "loadingqrcode", "扫码登录", "二维码登录")),
        )
        for label, needles in patterns:
            if any(normalize_text(needle).casefold() in observed for needle in needles):
                return label
        return ""

    def open_from_visible_list(self, window: Window, chat: str) -> bool:
        screenshot = self.capture_screen("conversation-list-check")
        list_box = self.conversation_list_box(window)
        crop_path = self.crop(
            screenshot,
            list_box,
            self.runtime_dir / "conversation-list-check.png",
        )
        match = self.find_ocr_line(crop_path, chat, scale=3)
        if match is None:
            return False
        self.click(
            list_box[0] + int(match["center_x"]),
            list_box[1] + int(match["center_y"]),
        )
        time.sleep(self.pause)
        return True

    def conversation_list_box(self, window: Window) -> tuple[int, int, int, int]:
        """Return the complete visible conversation-list surface."""
        return (
            window.x + int(window.width * 0.06),
            window.y + int(window.height * 0.07),
            int(window.width * 0.255),
            int(window.height * 0.84),
        )

    def current_allowlisted_chat(self, window: Window, *, exclude: str = "") -> str:
        for candidate in self.target_groups:
            if candidate == exclude:
                continue
            if self.current_title_matches(window, candidate):
                return candidate
        return ""

    def open_from_visible_list_keyboard(
        self,
        window: Window,
        current_chat: str,
        target_chat: str,
    ) -> bool:
        """Navigate between visible rows when Wine ignores a pointer selection."""
        screenshot = self.capture_screen("conversation-keyboard-fallback")
        list_box = self.conversation_list_box(window)
        crop_path = self.crop(
            screenshot,
            list_box,
            self.runtime_dir / "conversation-keyboard-fallback.png",
        )
        target = self.find_ocr_line(crop_path, target_chat, scale=3)
        current_center_y = self.selected_conversation_center_y(crop_path)
        if current_center_y is None:
            current = self.find_ocr_line(crop_path, current_chat, scale=3)
            current_center_y = float(current["center_y"]) if current is not None else None
        if current_center_y is None or target is None:
            return False
        delta = float(target["center_y"]) - current_center_y
        row_height = max(40.0, float(window.height) * 0.11)
        steps = int(round(abs(delta) / row_height))
        if steps < 1 or steps > 12:
            return False
        direction = "Down" if delta > 0 else "Up"
        list_left, list_top, list_width, _list_height = list_box
        command = [
            "mousemove",
            str(list_left + int(list_width * 0.50)),
            str(list_top + int(current_center_y)),
            "click",
            "1",
        ]
        for _ in range(steps):
            command.extend(["key", "--clearmodifiers", direction])
        command.extend(["key", "--clearmodifiers", "Return"])
        self.run_xdotool(command)
        time.sleep(self.pause)
        return True

    def selected_conversation_center_y(self, path: Path) -> float | None:
        """Locate WeCom's vivid-blue selected row without trusting its OCR text."""
        if Image is None:
            raise RuntimeError("Pillow is required for WeCom GUI conversation selection")
        with Image.open(path).convert("RGB") as image:
            width, height = image.size
            row_counts: list[int] = []
            for y in range(height):
                count = 0
                for red, green, blue in (image.getpixel((x, y)) for x in range(width)):
                    if (
                        20 <= red <= 120
                        and 95 <= green <= 190
                        and 210 <= blue <= 255
                        and blue - green >= 45
                    ):
                        count += 1
                row_counts.append(count)

        minimum = max(24, int(width * 0.20))
        bands: list[tuple[int, int, int]] = []
        start: int | None = None
        score = 0
        for y, count in enumerate([*row_counts, 0]):
            if count >= minimum:
                if start is None:
                    start = y
                    score = 0
                score += count
                continue
            if start is not None:
                bands.append((start, y - 1, score))
                start = None
                score = 0
        if not bands:
            return None
        top, bottom, _score = max(bands, key=lambda item: item[2])
        if bottom - top + 1 < 12:
            return None
        return (top + bottom) / 2.0

    def find_ocr_line(self, path: Path, target: str, *, scale: int = 3) -> dict[str, Any] | None:
        if Image is None or ImageOps is None or ImageFilter is None:
            raise RuntimeError("Pillow is required for WeCom GUI conversation selection")
        prepared = self.runtime_dir / f"{path.stem}-ocr.png"
        with Image.open(path).convert("L") as image:
            image = ImageOps.autocontrast(image)
            image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
            image = image.filter(ImageFilter.SHARPEN)
            image.save(prepared)
        proc = subprocess.run(
            ["tesseract", str(prepared), "stdout", "-l", "chi_sim+eng", "--psm", "11", "tsv"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"tesseract failed: {proc.stderr[:300]}")
        grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        for row in parse_tesseract_tsv(proc.stdout):
            text = str(row.get("text") or "").strip()
            if row.get("level") != "5" or not text:
                continue
            key = (str(row.get("block_num")), str(row.get("par_num")), str(row.get("line_num")))
            grouped.setdefault(key, []).append(row)
        wanted = normalize_text(target)
        candidates: list[dict[str, Any]] = []
        for words in grouped.values():
            words.sort(key=lambda item: int(item.get("left") or 0))
            line = join_ocr_words([str(item.get("text") or "") for item in words])
            match_units: list[tuple[str, list[dict[str, str]]]] = [(line, words)]
            match_units.extend((str(word.get("text") or ""), [word]) for word in words)
            for value, unit_words in match_units:
                normalized = normalize_text(value)
                similarity = SequenceMatcher(None, normalized, wanted).ratio()
                visual_identity = ocr_visual_identity_matches(normalized, wanted)
                if normalized != wanted and not visual_identity and similarity < 0.90:
                    continue
                effective_similarity = 1.0 if visual_identity else similarity
                left = min(int(item.get("left") or 0) for item in unit_words)
                top = min(int(item.get("top") or 0) for item in unit_words)
                right = max(int(item.get("left") or 0) + int(item.get("width") or 0) for item in unit_words)
                bottom = max(int(item.get("top") or 0) + int(item.get("height") or 0) for item in unit_words)
                candidates.append(
                    {
                        "text": value,
                        "similarity": effective_similarity,
                        "center_x": ((left + right) / 2) / scale,
                        "center_y": ((top + bottom) / 2) / scale,
                    }
                )
        if not candidates:
            return None
        candidates.sort(key=lambda item: (float(item["similarity"]), -float(item["center_y"])), reverse=True)
        best = candidates[0]
        if (
            len(candidates) > 1
            and candidates[1]["similarity"] == best["similarity"]
            and (
                abs(float(candidates[1]["center_x"]) - float(best["center_x"])) > 10
                or abs(float(candidates[1]["center_y"]) - float(best["center_y"])) > 10
            )
        ):
            raise RuntimeError(f"ambiguous visible WeCom conversation match for {target!r}")
        return best

    def current_title_matches(self, window: Window, chat: str) -> bool:
        screenshot = self.capture_screen("title-check")
        title_crop = self.crop(
            screenshot,
            (
                window.x + int(window.width * 0.325),
                window.y + int(window.height * 0.03),
                int(window.width * 0.20),
                max(30, int(window.height * 0.06)),
            ),
            self.runtime_dir / "title-check.png",
        )
        return self.find_ocr_line(title_crop, chat, scale=3) is not None

    def extract_inbound_messages(
        self,
        screenshot: Path,
        window: Window,
        chat: str,
    ) -> tuple[list[str], Path]:
        records, crop_path = self.extract_inbound_records(screenshot, window, chat)
        return [str(record.get("text") or "") for record in records], crop_path

    def extract_inbound_records(
        self,
        screenshot: Path,
        window: Window,
        chat: str,
    ) -> tuple[list[dict[str, str]], Path]:
        crop_path = self.runtime_dir / f"messages-{safe_slug(chat)}.png"
        left = window.x + int(window.width * 0.325)
        top = window.y + int(window.height * 0.12)
        crop = self.crop(
            screenshot,
            (
                left,
                top,
                int(window.width * 0.50),
                int(window.height * 0.62),
            ),
            crop_path,
        )
        return self.extract_bubble_records(crop, chat, screen_origin=(left, top)), crop_path

    def extract_bubble_texts(
        self,
        path: Path,
        chat: str,
        *,
        screen_origin: tuple[int, int] | None = None,
    ) -> list[str]:
        return [
            str(record.get("text") or "")
            for record in self.extract_bubble_records(path, chat, screen_origin=screen_origin)
        ]

    def extract_bubble_records(
        self,
        path: Path,
        chat: str,
        *,
        screen_origin: tuple[int, int] | None = None,
    ) -> list[dict[str, str]]:
        if Image is None:
            raise RuntimeError("Pillow is required for WeCom GUI bubble extraction")
        with Image.open(path).convert("RGB") as image:
            image_width, image_height = image.size
            regions = [
                region
                for region in find_color_regions(image, (228, 231, 235), tolerance=8)
                if region[2] - region[0] >= 40 and region[3] - region[1] >= 20 and region[4] >= 300
            ]
        records: list[dict[str, str]] = []
        last_sender = ""
        last_sender_fingerprint = ""
        for index, (left, top, right, bottom, _area) in enumerate(regions):
            sender, sender_fingerprint = self.extract_sender_identity(
                path,
                left=left,
                top=top,
                image_width=image_width,
                image_height=image_height,
                label=f"{safe_slug(chat)}-{index}",
            )
            if sender:
                last_sender = sender
                last_sender_fingerprint = sender_fingerprint
            else:
                sender = last_sender
                sender_fingerprint = last_sender_fingerprint
            text = ""
            if screen_origin is not None:
                exact = self.copy_text_bubble(
                    screen_origin[0] + (left + right) // 2,
                    screen_origin[1] + (top + bottom) // 2,
                    probe_id=f"{safe_slug(chat)}-{index}",
                )
                if exact:
                    text = exact
            if not text:
                bubble = self.crop(
                    path,
                    (left, top, right - left, bottom - top),
                    self.runtime_dir / f"bubble-{safe_slug(chat)}-{index}.png",
                )
                psm = 7 if bottom - top <= 45 else 6
                text = self.ocr_scaled(
                    bubble,
                    scale=4,
                    psm=psm,
                    threshold=178,
                    prefer_han=True,
                ).strip()
            if normalize_text(text):
                records.append(
                    {
                        "text": text,
                        "sender_label": sender,
                        "sender_fingerprint": sender_fingerprint,
                        "sender_confidence": (
                            "visual_fingerprint" if sender_fingerprint else "unresolved"
                        ),
                    }
                )
        return records

    def extract_sender_identity(
        self,
        path: Path,
        *,
        left: int,
        top: int,
        image_width: int,
        image_height: int,
        label: str,
    ) -> tuple[str, str]:
        if top < 12:
            return "", ""
        name_left = max(0, left - 8)
        name_top = max(0, top - 38)
        name_right = min(image_width, left + 230)
        name_bottom = min(image_height, max(name_top + 12, top - 2))
        if name_right <= name_left or name_bottom <= name_top:
            return "", ""
        sender_crop = self.crop(
            path,
            (name_left, name_top, name_right - name_left, name_bottom - name_top),
            self.runtime_dir / f"sender-{safe_slug(label)}.png",
        )
        observed = self.ocr_scaled(
            sender_crop,
            scale=4,
            psm=7,
            threshold=170,
            prefer_han=True,
        )
        return canonical_sender_label(observed), sender_visual_fingerprint(sender_crop)

    def copy_text_bubble(self, x: int, y: int, *, probe_id: str) -> str:
        """Copy one visible WeCom text bubble through its native context menu."""
        sentinel = f"__LABCANVAS_WECOM_COPY_PROBE_{safe_slug(probe_id)}__"
        copied = ""
        try:
            self.set_clipboard(sentinel)
            self.right_click(x, y)
            time.sleep(0.20)
            # Copy is the first menu item in both Chinese and English WeCom.
            # Keyboard selection avoids fragile pixel offsets and DPI changes.
            self.key("Home")
            self.key("Return")
            time.sleep(0.20)
            copied = canonical_clipboard_text(self.get_clipboard())
        except Exception:
            return ""
        finally:
            window = self.find_window(required=False)
            if window is not None:
                self.dismiss_transient_overlays(window)
        if not copied or copied == sentinel:
            return ""
        return copied[:12000]

    def build_event(
        self,
        chat: str,
        messages: list[str],
        image_hash: str,
        *,
        sender_label: str = "",
        sender_fingerprint: str = "",
        sender_confidence: str = "unresolved",
    ) -> Path:
        normalized_sender = canonical_sender_label(sender_label)
        normalized_fingerprint = re.sub(r"[^0-9a-f]", "", sender_fingerprint.casefold())[:64]
        identity = json.dumps(
            {
                "chat": chat,
                "messages": messages,
                "image": image_hash,
                "sender": normalized_sender,
                "sender_fingerprint": normalized_fingerprint,
            },
            ensure_ascii=False,
        )
        event_id = short_hash(identity)
        event_dir = self.event_root / datetime.now().strftime("%Y%m%d") / safe_slug(chat) / event_id
        event_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        text = "\n".join(
            (f"[Message {index}] {message}" if len(messages) > 1 else message)
            for index, message in enumerate(messages, start=1)
        )
        event = {
            "schema_version": 1,
            "transport": "wecom",
            "transport_channel": "wecom_gui",
            "account_id": str(self.config.get("account_id") or "external-gui"),
            "message_id": f"gui:{event_id}",
            "chat_id": f"gui:{chat}",
            "chat_name": chat,
            "chat_type": "group",
            "sender_userid": (
                f"external-member:{short_hash(normalized_fingerprint)}"
                if normalized_fingerprint
                else f"external-member:{short_hash(normalized_sender)}"
                if normalized_sender
                else f"external-member:unresolved:{event_id[:8]}"
            ),
            "sender_display": normalized_sender,
            "sender_identity_confidence": (
                sender_confidence
                if normalized_fingerprint or normalized_sender
                else "unresolved"
            ),
            "authorization_role": "group_member",
            "irreversible_actions_allowed": False,
            "create_time": int(time.time()),
            "msgtype": "text",
            "text": text,
            "quote_text": "",
            "attachments": [],
            "source_message_count": len(messages),
            "received_at": now_iso(),
        }
        path = event_dir / "event.json"
        write_private_json(path, event)
        return path

    def invoke_ingest(self, event_path: Path) -> dict[str, Any]:
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
        }
        proc = subprocess.run(
            [sys.executable, str(INGEST_SCRIPT), "--event-file", str(event_path), "--queue", str(self.queue), "--json"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        payload = parse_json(proc.stdout)
        if proc.returncode != 0 or not isinstance(payload, dict) or not payload.get("ok"):
            detail = payload.get("error") if isinstance(payload, dict) else proc.stderr or proc.stdout
            raise RuntimeError(f"WeCom GUI ingress failed: {str(detail)[:800]}")
        return payload

    def recover_expired_outbox(self) -> dict[str, Any]:
        if not bool(self.config.get("recover_expired_on_reconnect", True)):
            return {"ok": True, "recovered_count": 0, "disabled": True}
        max_age = bounded_int(
            self.config.get("reconnect_recovery_max_age_seconds"),
            12 * 60 * 60,
            0,
            7 * 24 * 60 * 60,
        )
        limit = bounded_int(self.config.get("reconnect_recovery_limit"), 1, 0, 20)
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep),
        }
        proc = subprocess.run(
            [
                sys.executable,
                str(RECONNECT_OUTBOX_SCRIPT),
                "--queue",
                str(self.queue),
                "--max-age-seconds",
                str(max_age),
                "--limit",
                str(limit),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        payload = parse_json(proc.stdout)
        if proc.returncode != 0 or not isinstance(payload, dict) or not payload.get("ok"):
            detail = payload.get("error") if isinstance(payload, dict) else proc.stderr or proc.stdout
            raise RuntimeError(f"WeCom reconnect outbox recovery failed: {str(detail)[:800]}")
        set_runtime(self.state_db, "last_reconnect_recovery", json.dumps(payload, ensure_ascii=False)[:4000])
        return payload

    def recover_outbox_after_ready_poll(
        self,
        *,
        client_visible: bool,
        poll_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Recover deferred work only after exact-chat GUI readiness is proven."""
        if not client_visible:
            self._client_was_visible = False
            set_runtime(self.state_db, "reconnect_ready_since_epoch", "")
            return {"ok": True, "recovered_count": 0, "skipped": "client_not_visible"}
        if not poll_result.get("ok"):
            # A full-size cached/post-login window is not enough. Keep the
            # reconnect edge armed until every allowlisted chat can be opened
            # and title-verified by the normal poll path.
            self._client_was_visible = False
            set_runtime(self.state_db, "reconnect_ready_since_epoch", "")
            return {"ok": True, "recovered_count": 0, "skipped": "chat_poll_not_ready"}
        if poll_result.get("skipped") in {
            "security_quarantine",
            "auth_recovery_stabilizing",
            "chat_failure_backoff",
            "poll_already_running",
        }:
            return {"ok": True, "recovered_count": 0, "skipped": str(poll_result["skipped"])}
        if self.security_pause_state():
            return {"ok": True, "recovered_count": 0, "skipped": "security_quarantine"}
        if not all(
            get_runtime(self.state_db, f"chat_ready:{safe_slug(chat)}") == "1"
            for chat in self.target_groups
        ):
            self._client_was_visible = False
            set_runtime(self.state_db, "reconnect_ready_since_epoch", "")
            return {"ok": True, "recovered_count": 0, "skipped": "all_chats_not_ready"}
        if self._client_was_visible:
            return {"ok": True, "recovered_count": 0, "skipped": "already_ready"}
        now = time.time()
        ready_since = runtime_float(self.state_db, "reconnect_ready_since_epoch")
        if ready_since <= 0:
            set_runtime(self.state_db, "reconnect_ready_since_epoch", str(now))
            ready_since = now
        stabilization = bounded_float(
            self.config.get("reconnect_stabilization_seconds"), 120.0, 10.0, 3600.0
        )
        stable_for = max(0.0, now - ready_since)
        if stable_for < stabilization:
            return {
                "ok": True,
                "recovered_count": 0,
                "skipped": "reconnect_stabilizing",
                "stabilization_remaining_seconds": int(stabilization - stable_for + 0.999),
            }
        try:
            recovered = self.recover_expired_outbox()
        except Exception as exc:
            recovered = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:800]}"}
            set_runtime(self.state_db, "last_reconnect_recovery_error", recovered["error"])
        self._client_was_visible = bool(recovered.get("ok"))
        return recovered

    def find_window(self, *, required: bool = True) -> Window | None:
        proc = self.run_xdotool(["search", "--onlyvisible", "--name", "^WeCom$"], check=False)
        candidates: list[Window] = []
        for wid in [line.strip() for line in proc.stdout.splitlines() if line.strip()]:
            geometry = self.run_xdotool(["getwindowgeometry", "--shell", wid], check=False).stdout
            values = parse_shell_values(geometry)
            try:
                window = Window(
                    wid=wid,
                    x=int(values["X"]),
                    y=int(values["Y"]),
                    width=int(values["WIDTH"]),
                    height=int(values["HEIGHT"]),
                )
            except (KeyError, ValueError):
                continue
            if window.width >= 700 and window.height >= 500:
                candidates.append(window)
        if candidates:
            return max(candidates, key=lambda item: item.width * item.height)
        if required:
            raise RuntimeError(f"no logged-in WeCom window is visible on DISPLAY={self.display}")
        return None

    def set_clipboard(self, text: str) -> None:
        ensure_clipboard_helper()
        env = self.gui_env()
        proc = subprocess.run(
            ["wine", str(CLIPBOARD_EXE)],
            input=text.encode("utf-8"),
            env=env,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Wine clipboard helper failed: {proc.stderr.decode(errors='replace')[:300]}")

    def get_clipboard(self) -> str:
        ensure_clipboard_helper()
        last_error = ""
        for _attempt in range(10):
            proc = subprocess.run(
                ["wine", str(CLIPBOARD_EXE), "--read"],
                env=self.gui_env(),
                capture_output=True,
                timeout=20,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.decode("utf-8", errors="strict")
            last_error = proc.stderr.decode(errors="replace")[:300]
            time.sleep(0.05)
        raise RuntimeError(f"Wine clipboard readback failed: {last_error}")

    def set_file_clipboard(self, paths: list[Path]) -> list[str]:
        ensure_clipboard_helper()
        windows_paths = [self.windows_path(path) for path in paths]
        proc = subprocess.run(
            ["wine", str(CLIPBOARD_EXE), "--files"],
            input=("\n".join(windows_paths) + "\n").encode("utf-8"),
            env=self.gui_env(),
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Wine file clipboard helper failed: {proc.stderr.decode(errors='replace')[:300]}")
        readback = subprocess.run(
            ["wine", str(CLIPBOARD_EXE), "--read-files"],
            env=self.gui_env(),
            capture_output=True,
            timeout=20,
            check=False,
        )
        observed = [
            line.strip()
            for line in readback.stdout.decode("utf-8", errors="strict").splitlines()
            if line.strip()
        ]
        if readback.returncode != 0 or [item.casefold() for item in observed] != [
            item.casefold() for item in windows_paths
        ]:
            raise RuntimeError("WECOM_GUI_FILE_CLIPBOARD_UNVERIFIED: clipboard file list did not round-trip")
        return observed

    def composer_text_matches(self, window: Window, expected: str, delivery_key: str) -> bool:
        sentinel = f"__LABCANVAS_COMPOSER_PROBE_{delivery_key}__"
        self.set_clipboard(sentinel)
        self.composer_keys(window, "ctrl+a", "ctrl+c")
        time.sleep(max(0.2, self.pause / 3))
        observed = self.get_clipboard()
        return canonical_composer_text(observed) == canonical_composer_text(expected)

    def composer_is_empty(self, window: Window, delivery_key: str) -> bool:
        sentinel = f"__LABCANVAS_EMPTY_PROBE_{delivery_key}__"
        self.set_clipboard(sentinel)
        self.composer_keys(window, "ctrl+a", "ctrl+c")
        time.sleep(max(0.2, self.pause / 3))
        observed = canonical_clipboard_text(self.get_clipboard())
        return observed in {"", sentinel}

    def clear_composer(self, window: Window) -> None:
        self.composer_keys(window, "ctrl+a", "BackSpace")

    def stage_send_file(self, source: Path, delivery_key: str) -> tuple[Path, Path]:
        staging_dir = self.prefix / "drive_c" / "labcanvas_wecom_send" / delivery_key
        shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        staged = staging_dir / source.name
        try:
            os.link(source, staged)
        except OSError:
            shutil.copy2(source, staged)
        return staged, staging_dir

    def compose_staged_file_with_picker(
        self,
        wecom: Window,
        staged_file: Path,
        staging_dir: Path,
        delivery_key: str,
    ) -> Path:
        staged_files = [path for path in staging_dir.iterdir() if path.is_file()]
        if len(staged_files) != 1 or staged_files[0].resolve() != staged_file.resolve():
            raise RuntimeError("isolated WeCom staging folder must contain exactly one file")
        stale_picker = self.find_file_picker()
        if stale_picker is not None:
            self.close_window(stale_picker.wid)
            time.sleep(max(0.25, self.pause / 2))

        # The native picker only stages the file. The caller verifies the
        # composer and then clicks the separate WeCom Send button.
        self.run_win32_click(
            wecom.x + int(wecom.width * 0.572),
            wecom.y + int(wecom.height * 0.797),
        )
        time.sleep(max(0.25, self.pause / 2))
        self.click(wecom.x + int(wecom.width * 0.607), wecom.y + int(wecom.height * 0.846))
        time.sleep(max(0.25, self.pause / 2))
        self.click(wecom.x + int(wecom.width * 0.789), wecom.y + int(wecom.height * 0.849))

        picker = self.wait_for_file_picker(timeout=15.0)
        try:
            self.set_clipboard(self.windows_path(staging_dir))
            self.click(
                picker.x + int(picker.width * 0.56),
                picker.y + int(picker.height * 0.91),
            )
            self.run_xdotool(["key", "--clearmodifiers", "ctrl+a", "ctrl+v", "Return"])

            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                picker = self.find_file_picker() or picker
                if self.picker_contains_filename(picker, staged_file.name, delivery_key):
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError(
                    "WECOM_GUI_PICKER_UNVERIFIED: native picker did not show the exact staged artifact"
                )

            self.click(
                picker.x + int(picker.width * 0.36),
                picker.y + int(picker.height * 0.13),
            )
            time.sleep(max(0.25, self.pause / 2))
            selected_evidence = self.capture_screen(f"file-picker-selected-{delivery_key}")
            if not self.picker_filename_field_matches(picker, staged_file.name, delivery_key):
                raise RuntimeError(
                    "WECOM_GUI_PICKER_UNVERIFIED: File name field did not equal the exact artifact"
                )

            self.click(
                picker.x + int(picker.width * 0.85),
                picker.y + int(picker.height * 0.96),
            )
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                if self.find_file_picker() is None:
                    return selected_evidence
                time.sleep(0.25)
            raise RuntimeError("WECOM_GUI_PICKER_UNCERTAIN: native picker did not close after staging")
        except Exception:
            active_picker = self.find_file_picker()
            if active_picker is not None:
                self.close_window(active_picker.wid)
            raise

    def find_file_picker(self) -> Window | None:
        for title in FILE_PICKER_TITLES:
            window = self.find_named_window(title)
            if window is not None:
                return window
        return None

    def wait_for_file_picker(self, *, timeout: float) -> Window:
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            window = self.find_file_picker()
            if window is not None:
                return window
            time.sleep(0.25)
        raise RuntimeError(
            "native WeCom file picker did not appear: " + " or ".join(FILE_PICKER_TITLES)
        )

    def wait_for_named_window(self, title: str, *, timeout: float) -> Window:
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            window = self.find_named_window(title)
            if window is not None:
                return window
            time.sleep(0.25)
        raise RuntimeError(f"native WeCom window did not appear: {title}")

    def picker_contains_filename(
        self,
        picker: Window,
        filename: str,
        label: str,
    ) -> bool:
        screenshot = self.capture_screen(f"file-picker-{safe_slug(label)}")
        title_height = min(24, picker.height // 10)
        body = self.crop(
            screenshot,
            (
                picker.x,
                picker.y + title_height,
                picker.width,
                max(80, picker.height - title_height),
            ),
            self.runtime_dir / f"file-picker-{safe_slug(label)}-body.png",
        )
        return filename_matches_ocr(filename, self.ocr_scaled(body, scale=3, psm=11))

    def picker_filename_field_matches(
        self,
        picker: Window,
        filename: str,
        delivery_key: str,
    ) -> bool:
        sentinel = f"__LABCANVAS_PICKER_PROBE_{delivery_key}__"
        self.set_clipboard(sentinel)
        self.click(
            picker.x + int(picker.width * 0.56),
            picker.y + int(picker.height * 0.91),
        )
        self.run_xdotool(["key", "--clearmodifiers", "ctrl+a", "ctrl+c"])
        time.sleep(max(0.2, self.pause / 3))
        observed = canonical_clipboard_text(self.get_clipboard()).strip('"')
        observed_name = re.split(r"[\\/]", observed)[-1]
        return secrets.compare_digest(observed_name.casefold(), filename.casefold())

    def windows_path(self, path: Path) -> str:
        proc = subprocess.run(
            ["winepath", "-w", str(path)],
            env=self.gui_env(),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        value = proc.stdout.strip()
        if proc.returncode != 0 or not value:
            raise RuntimeError(f"winepath failed for {path}: {proc.stderr[:200]}")
        return value

    def composer_contains_filename(
        self,
        screenshot: Path,
        window: Window,
        filename: str,
        delivery_key: str,
    ) -> bool:
        crop = self.crop(
            screenshot,
            (
                window.x + int(window.width * 0.325),
                window.y + int(window.height * 0.73),
                int(window.width * 0.51),
                int(window.height * 0.25),
            ),
            self.runtime_dir / f"file-composer-{delivery_key}.png",
        )
        return filename_matches_ocr(filename, self.ocr_scaled(crop, scale=3, psm=11))

    def read_chat_history_text(self, screenshot: Path, window: Window, label: str) -> str:
        crop = self.crop(
            screenshot,
            (
                window.x + int(window.width * 0.325),
                window.y + int(window.height * 0.12),
                int(window.width * 0.51),
                int(window.height * 0.62),
            ),
            self.runtime_dir / f"file-history-{safe_slug(label)}.png",
        )
        return self.ocr_scaled(crop, scale=3, psm=11)

    def wait_for_file_in_history(
        self,
        window: Window,
        filename: str,
        *,
        before_text: str,
        delivery_key: str,
    ) -> Path:
        before_count = filename_ocr_count(filename, before_text)
        deadline = time.monotonic() + 20
        latest: Path | None = None
        while time.monotonic() < deadline:
            time.sleep(1.0)
            blocker = self.detect_auth_blocker(window)
            if self.blocker_prevents_operation(blocker, "file"):
                raise RuntimeError(f"WECOM_GUI_AUTH_REQUIRED: {blocker}")
            latest = self.capture_screen(f"file-sent-{delivery_key}")
            after_text = self.read_chat_history_text(latest, window, f"after-{delivery_key}")
            if filename_ocr_count(filename, after_text) > before_count:
                return latest
        raise RuntimeError(
            "WECOM_GUI_SEND_UNCERTAIN: WeCom did not show the exact artifact in chat history after Send"
        )

    def ocr_scaled(
        self,
        path: Path,
        *,
        scale: int,
        psm: int,
        threshold: int | None = None,
        prefer_han: bool = False,
    ) -> str:
        if Image is None or ImageOps is None or ImageFilter is None:
            raise RuntimeError("Pillow is required for WeCom GUI attachment verification")
        prepared = self.runtime_dir / f"{path.stem}-scaled-ocr.png"
        with Image.open(path).convert("L") as image:
            image = ImageOps.autocontrast(image)
            image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
            image = image.filter(ImageFilter.SHARPEN)
            if threshold is not None:
                image = image.point(lambda value: 255 if value >= threshold else 0)
            image.save(prepared)
        combined = self.ocr(prepared, psm=psm)
        if not prefer_han:
            return combined
        chinese = self.ocr(prepared, psm=psm, language="chi_sim")
        english_identifiers = self.ocr(
            prepared,
            psm=psm,
            language="eng",
            config=("-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._/-"),
        )
        return choose_ocr_variant(combined, chinese, english_identifiers)

    def find_named_window(self, title: str) -> Window | None:
        proc = self.run_xdotool(
            ["search", "--onlyvisible", "--name", f"^{re.escape(title)}$"],
            check=False,
        )
        for wid in [line.strip() for line in proc.stdout.splitlines() if line.strip()]:
            window = self.window_geometry(wid)
            if window is not None and window.width >= 400 and window.height >= 250:
                return window
        return None

    def window_geometry(self, wid: str) -> Window | None:
        geometry = self.run_xdotool(["getwindowgeometry", "--shell", wid], check=False).stdout
        values = parse_shell_values(geometry)
        try:
            return Window(
                wid=wid,
                x=int(values["X"]),
                y=int(values["Y"]),
                width=int(values["WIDTH"]),
                height=int(values["HEIGHT"]),
            )
        except (KeyError, ValueError):
            return None

    def close_window(self, wid: str) -> None:
        self.run_xdotool(["windowclose", wid], check=False)

    def capture_screen(self, label: str) -> Path:
        path = self.runtime_dir / f"{safe_slug(label)}.png"
        proc = subprocess.run(
            ["import", "-window", "root", str(path)],
            env=self.gui_env(),
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0 or not path.is_file():
            raise RuntimeError(f"WeCom screenshot failed: {proc.stderr.decode(errors='replace')[:300]}")
        path.chmod(0o600)
        return path

    def crop(self, source: Path, box: tuple[int, int, int, int], target: Path) -> Path:
        if Image is None:
            raise RuntimeError("Pillow is required for WeCom GUI screenshots")
        left, top, width, height = box
        with Image.open(source) as image:
            image.crop((left, top, left + width, top + height)).save(target)
        target.chmod(0o600)
        return target

    def ocr(
        self,
        path: Path,
        *,
        psm: int,
        language: str = "chi_sim+eng",
        config: tuple[str, ...] = (),
    ) -> str:
        proc = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", language, "--psm", str(psm), *config],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"tesseract failed: {proc.stderr[:300]}")
        return proc.stdout.strip()

    def click(self, x: int, y: int) -> None:
        self.run_xdotool(["mousemove", str(x), str(y), "click", "1"])

    def right_click(self, x: int, y: int) -> None:
        self.run_xdotool(["mousemove", str(x), str(y), "click", "3"])

    def key(self, keys: str) -> None:
        self.run_xdotool(["key", "--clearmodifiers", keys])

    def dismiss_transient_overlays(self, window: Window) -> None:
        # Search and failed-file windows are native top-level Wine windows.
        # Clicking the main Electron surface cannot dismiss them and leaves
        # every subsequent exact-title check blocked. The helper closes only
        # exact allowlisted WeCom modal/search classes owned by this process.
        self.close_stale_native_overlays()
        self.click(
            window.x + int(window.width * 0.58),
            window.y + int(window.height * 0.08),
        )
        time.sleep(0.05)

    def close_stale_native_overlays(self) -> None:
        ensure_win32_input_helper()
        proc = subprocess.run(
            ["wine", str(WIN32_INPUT_EXE), "--close-stale-modals"],
            env=self.gui_env(),
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            detail = proc.stderr.decode(errors="replace")[:300]
            raise RuntimeError(f"Wine stale WeCom overlay cleanup failed: {detail}")

    def composer_keys(self, window: Window, *keys: str) -> None:
        # Wine renders this Electron composer as synchronized layered windows.
        # The left side is stable even when the right-side layer captures black.
        x = window.x + int(window.width * 0.40)
        y = window.y + int(window.height * 0.87)
        self.click(x, y)
        config = getattr(self, "config", {})
        if str(config.get("composer_input_backend") or "xdotool").casefold() == "native":
            normalized = tuple(value.casefold() for value in keys)
            native_actions = {
                ("ctrl+a", "ctrl+v"): ("--clear", "--paste"),
                ("ctrl+v",): ("--paste",),
                ("ctrl+a", "ctrl+c"): ("--copy-all",),
                ("ctrl+a", "backspace"): ("--clear",),
            }.get(normalized)
            if native_actions is not None:
                for action in native_actions:
                    self.run_win32_input(action)
                return
        self.run_xdotool(["key", "--clearmodifiers", *keys])

    def run_win32_input(self, action: str) -> None:
        ensure_win32_input_helper()
        proc = subprocess.run(
            ["wine", str(WIN32_INPUT_EXE), action],
            env=self.gui_env(),
            capture_output=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            detail = proc.stderr.decode(errors="replace")[:300]
            raise RuntimeError(f"Wine SendInput helper failed for {action}: {detail}")

    def run_win32_click(self, x: int, y: int) -> None:
        ensure_win32_input_helper()

        def invoke(*args: str) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                ["wine", str(WIN32_INPUT_EXE), *args],
                env=self.gui_env(),
                capture_output=True,
                timeout=20,
                check=False,
            )

        proc = invoke("--click", str(x), str(y))
        if proc.returncode == 4:
            self.close_stale_native_overlays()
            time.sleep(max(0.25, self.pause / 2))
            proc = invoke("--click", str(x), str(y))
        if proc.returncode != 0:
            detail = proc.stderr.decode(errors="replace")[:300]
            raise RuntimeError(f"Wine SendInput click failed at {x},{y}: {detail}")

    def run_xdotool(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["xdotool", *args],
            env=self.gui_env(),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"xdotool {' '.join(args[:2])} failed: {proc.stderr[:300]}")
        return proc

    def gui_env(self) -> dict[str, str]:
        return {
            **os.environ,
            "DISPLAY": self.display,
            "XAUTHORITY": "",
            "WINEPREFIX": str(self.prefix),
            "WINEDEBUG": "-all",
        }

    def serialized_gui(self):
        return GuiLock(self.lock_path)

    def serve_forever(self) -> None:
        host = "127.0.0.1"
        port = bounded_int(self.config.get("local_api_port"), 19580, 1024, 65535)
        server = ThreadingHTTPServer((host, port), make_api_handler(self))
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, name="wecom-gui-api", daemon=True)
        thread.start()
        print(json.dumps({"ok": True, "event": "started", "transport": "wecom_gui_only", "port": port}), flush=True)
        interval = bounded_float(self.config.get("poll_seconds"), 4.0, 2.0, 120.0)
        try:
            while not self._stop.is_set():
                client_visible = self.find_window(required=False) is not None
                result = (
                    self.poll_cycle()
                    if bool(self.config.get("passive_poll_enabled", True))
                    else self.poll_once()
                )
                if not result.get("ok") or result.get("processed"):
                    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
                recovered = self.recover_outbox_after_ready_poll(
                    client_visible=client_visible,
                    poll_result=result,
                )
                if not recovered.get("ok") or recovered.get("recovered_count"):
                    print(json.dumps({"event": "reconnect_outbox_recovery", **recovered}, ensure_ascii=False), flush=True)
                self._stop.wait(interval)
        finally:
            server.shutdown()
            server.server_close()


class GuiLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "GuiLock":
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.handle = self.path.open("w", encoding="utf-8")
        fcntl.flock(self.handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()


def make_api_handler(bridge: WeComGuiBridge):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LabCanvasWeComGui/1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = parse.urlparse(self.path)
            if parsed.path == "/health":
                self.write_json(200, bridge.health())
                return
            if parsed.path not in {"/v1/chats", "/v1/messages"}:
                self.write_json(404, {"ok": False, "error": "not found"})
                return
            if not self.authorized():
                self.write_json(401, {"ok": False, "error": "unauthorized"})
                return
            if parsed.path == "/v1/chats":
                self.write_json(200, bridge.list_chats())
                return
            values = parse.parse_qs(parsed.query)
            chat_id = str((values.get("chat_id") or [""])[0]).strip()
            chat = chat_id.removeprefix("gui:") if chat_id.startswith("gui:") else ""
            if chat not in bridge.target_groups or not secrets.compare_digest(chat_id, f"gui:{chat}"):
                self.write_json(403, {"ok": False, "error": "refusing non-allowlisted WeCom GUI target"})
                return
            try:
                after = max(0, int((values.get("after") or ["0"])[0]))
                limit = bounded_int((values.get("limit") or ["100"])[0], 100, 1, 500)
            except ValueError:
                self.write_json(400, {"ok": False, "error": "after must be a non-negative integer"})
                return
            self.write_json(200, bridge.read_messages(chat, after=after, limit=limit))

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/v1/send", "/v1/delivery-status"}:
                self.write_json(404, {"ok": False, "error": "not found"})
                return
            if not self.authorized():
                self.write_json(401, {"ok": False, "error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length < 0 or length > MAX_API_BODY:
                    self.write_json(413, {"ok": False, "error": "request body too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                chat_id = str(payload.get("chat_id") or "").strip()
                chat = chat_id.removeprefix("gui:") if chat_id.startswith("gui:") else ""
                if chat not in bridge.target_groups or not secrets.compare_digest(chat_id, f"gui:{chat}"):
                    self.write_json(403, {"ok": False, "error": "refusing non-allowlisted WeCom GUI target"})
                    return
                raw_files = payload.get("files") or []
                if not isinstance(raw_files, list) or len(raw_files) > 16:
                    self.write_json(400, {"ok": False, "error": "files must be a list with at most 16 entries"})
                    return
                files = [Path(str(item)) for item in raw_files]
                task_id = str(payload.get("task_id") or "api").strip()[:256] or "api"
                message = str(payload.get("message") or "")
                if not message.strip() and not files:
                    self.write_json(400, {"ok": False, "error": "send requires message and/or files"})
                    return
                if self.path == "/v1/delivery-status":
                    result = bridge.delivery_status(chat, message, files, task_id=task_id)
                else:
                    result = bridge.send(chat, message, files, task_id=task_id)
                self.write_json(200, result)
            except Exception as exc:
                self.write_json(500, {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"})

        def write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self) -> bool:
            expected = f"Bearer {bridge.config.get('local_api_token') or ''}"
            return secrets.compare_digest(str(self.headers.get("Authorization") or ""), expected)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def ensure_clipboard_helper() -> None:
    if not CLIPBOARD_SOURCE.is_file():
        raise RuntimeError(f"missing clipboard helper source: {CLIPBOARD_SOURCE}")
    if CLIPBOARD_EXE.is_file() and CLIPBOARD_EXE.stat().st_mtime >= CLIPBOARD_SOURCE.stat().st_mtime:
        return
    compiler = "x86_64-w64-mingw32-gcc"
    CLIPBOARD_EXE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    proc = subprocess.run(
        [
            compiler,
            "-O2",
            "-Wall",
            "-Wextra",
            "-mwindows",
            "-o",
            str(CLIPBOARD_EXE),
            str(CLIPBOARD_SOURCE),
            "-lshell32",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"failed to build Wine clipboard helper: {proc.stderr[:500]}")


def ensure_win32_input_helper() -> None:
    if (
        WIN32_INPUT_EXE.is_file()
        and WIN32_INPUT_EXE.stat().st_mtime >= WIN32_INPUT_SOURCE.stat().st_mtime
    ):
        return
    if not WIN32_INPUT_SOURCE.is_file():
        raise RuntimeError(f"missing Wine SendInput helper source: {WIN32_INPUT_SOURCE}")
    compiler = "x86_64-w64-mingw32-gcc"
    WIN32_INPUT_EXE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    proc = subprocess.run(
        [
            compiler,
            "-O2",
            "-Wall",
            "-Wextra",
            "-mwindows",
            "-o",
            str(WIN32_INPUT_EXE),
            str(WIN32_INPUT_SOURCE),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"failed to build Wine SendInput helper: {proc.stderr[:500]}")


def init_state_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshots ("
            "chat_name TEXT PRIMARY KEY, inbound_json TEXT NOT NULL, image_hash TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS deliveries ("
            "delivery_key TEXT PRIMARY KEY, chat_name TEXT NOT NULL, content_hash TEXT NOT NULL, sent_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS inbound_messages ("
            "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "message_id TEXT UNIQUE NOT NULL, "
            "chat_name TEXT NOT NULL, "
            "text TEXT NOT NULL, "
            "observed_at TEXT NOT NULL, "
            "event_path TEXT NOT NULL, "
            "image_hash TEXT NOT NULL, "
            "ingest_status TEXT NOT NULL DEFAULT 'observed', "
            "ingested_at TEXT NOT NULL DEFAULT '', "
            "ingest_error TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS inbound_messages_chat_sequence "
            "ON inbound_messages(chat_name, sequence)"
        )
        conn.execute("CREATE TABLE IF NOT EXISTS runtime (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def record_inbound_messages(
    path: Path,
    chat: str,
    messages: list[str],
    event_path: Path,
    image_hash: str,
) -> list[str]:
    event_id = event_path.parent.name
    observed_at = now_iso()
    message_ids: list[str] = []
    with sqlite3.connect(path) as conn:
        for index, text in enumerate(messages, start=1):
            message_id = f"gui:{event_id}:{index}"
            conn.execute(
                "INSERT OR IGNORE INTO inbound_messages("
                "message_id, chat_name, text, observed_at, event_path, image_hash"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, chat, str(text), observed_at, str(event_path), image_hash),
            )
            message_ids.append(message_id)
    return message_ids


def mark_event_ingest(path: Path, event_path: Path, *, status: str, error: str = "") -> None:
    if status not in {"ingested", "failed"}:
        raise ValueError("invalid GUI event ingest status")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE inbound_messages SET ingest_status = ?, ingested_at = ?, ingest_error = ? "
            "WHERE event_path = ?",
            (status, now_iso(), str(error), str(event_path)),
        )


def read_inbound_messages(path: Path, chat: str, *, after: int, limit: int) -> list[dict[str, Any]]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT sequence, message_id, text, observed_at, ingest_status "
            "FROM inbound_messages WHERE chat_name = ? AND sequence > ? "
            "ORDER BY sequence ASC LIMIT ?",
            (chat, max(0, int(after)), bounded_int(limit, 100, 1, 500)),
        ).fetchall()
    return [
        {
            "cursor": int(row[0]),
            "message_id": str(row[1]),
            "text": str(row[2]),
            "observed_at": str(row[3]),
            "ingest_status": str(row[4]),
            "transport": "wecom_gui",
            "chat_id": f"gui:{chat}",
        }
        for row in rows
    ]


def inbound_messages_exist_after(path: Path, chat: str, cursor: int) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT 1 FROM inbound_messages WHERE chat_name = ? AND sequence > ? LIMIT 1",
            (chat, max(0, int(cursor))),
        ).fetchone()
    return row is not None


def empty_send_result() -> dict[str, Any]:
    return {"ok": True, "sent_messages": [], "sent_files": [], "errors": []}


def merge_send_results(*results: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": all(bool(result.get("ok")) for result in results),
        "sent_messages": [item for result in results for item in result.get("sent_messages") or []],
        "sent_files": [item for result in results for item in result.get("sent_files") or []],
        "errors": [item for result in results for item in result.get("errors") or []],
    }


def load_snapshot(path: Path, chat: str) -> tuple[list[str], str] | None:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT inbound_json, image_hash FROM snapshots WHERE chat_name = ?", (chat,)
        ).fetchone()
    if not row:
        return None
    value = json.loads(str(row[0]))
    return ([str(item) for item in value] if isinstance(value, list) else [], str(row[1]))


def save_snapshot(path: Path, chat: str, messages: list[str], image_hash: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshots(chat_name, inbound_json, image_hash, updated_at) VALUES (?, ?, ?, ?)",
            (chat, json.dumps(messages, ensure_ascii=False), image_hash, now_iso()),
        )


def delivery_done(path: Path, key: str, chat: str) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT chat_name FROM deliveries WHERE delivery_key = ?", (key,)
        ).fetchone()
    return bool(row and secrets.compare_digest(str(row[0]), chat))


def remember_delivery(path: Path, key: str, chat: str, text: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO deliveries(delivery_key, chat_name, content_hash, sent_at) VALUES (?, ?, ?, ?)",
            (key, chat, short_hash(text), now_iso()),
        )


def set_runtime(path: Path, key: str, value: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT OR REPLACE INTO runtime(key, value) VALUES (?, ?)", (key, value))


def get_runtime(path: Path, key: str) -> str:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT value FROM runtime WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else ""


def runtime_float(path: Path, key: str) -> float:
    try:
        return float(get_runtime(path, key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def seconds_until_epoch(value: Any, *, now: float | None = None) -> int:
    try:
        target = float(value or 0.0)
    except (TypeError, ValueError):
        return 0
    if target <= 0:
        return 0
    remaining = target - (time.time() if now is None else now)
    return max(0, int(remaining + 0.999))


def find_color_regions(
    image: Any,
    target: tuple[int, int, int],
    *,
    tolerance: int,
) -> list[tuple[int, int, int, int, int]]:
    width, height = image.size
    pixels = image.load()
    seen = bytearray(width * height)
    regions: list[tuple[int, int, int, int, int]] = []

    def matches(x: int, y: int) -> bool:
        pixel = pixels[x, y][:3]
        return max(abs(int(pixel[index]) - target[index]) for index in range(3)) <= tolerance

    for y in range(height):
        for x in range(width):
            offset = y * width + x
            if seen[offset]:
                continue
            seen[offset] = 1
            if not matches(x, y):
                continue
            stack = [(x, y)]
            left = right = x
            top = bottom = y
            area = 0
            while stack:
                current_x, current_y = stack.pop()
                area += 1
                left = min(left, current_x)
                right = max(right, current_x)
                top = min(top, current_y)
                bottom = max(bottom, current_y)
                for next_x, next_y in (
                    (current_x - 1, current_y),
                    (current_x + 1, current_y),
                    (current_x, current_y - 1),
                    (current_x, current_y + 1),
                ):
                    if not (0 <= next_x < width and 0 <= next_y < height):
                        continue
                    next_offset = next_y * width + next_x
                    if seen[next_offset]:
                        continue
                    seen[next_offset] = 1
                    if matches(next_x, next_y):
                        stack.append((next_x, next_y))
            regions.append((left, top, right + 1, bottom + 1, area))
    return sorted(regions, key=lambda item: (item[1], item[0]))


def join_ocr_words(words: list[str]) -> str:
    result = ""
    for word in [item.strip() for item in words if item.strip()]:
        if not result:
            result = word
        elif result[-1:].isascii() and word[:1].isascii() and result[-1:].isalnum() and word[:1].isalnum():
            result += " " + word
        else:
            result += word
    return result


def parse_tesseract_tsv(value: str) -> list[dict[str, str]]:
    lines = str(value or "").splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        fields = line.split("\t", len(header) - 1)
        if len(fields) != len(header):
            continue
        rows.append(dict(zip(header, fields)))
    return rows


def new_message_suffix(old: list[str], new: list[str]) -> tuple[list[str], int]:
    if not old:
        return (new, 0)
    limit = min(len(old), len(new))
    for overlap in range(limit, 0, -1):
        old_tail = old[-overlap:]
        new_head = new[:overlap]
        if all(similar_text(left, right) >= 0.82 for left, right in zip(old_tail, new_head)):
            return (new[overlap:], overlap)
    if len(old) == len(new) and all(similar_text(left, right) >= 0.82 for left, right in zip(old, new)):
        return ([], len(old))
    return (new, 0)


def coalesce_sender_records(records: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    batches: list[list[dict[str, str]]] = []
    for record in records:
        sender = str(record.get("sender_fingerprint") or "") or canonical_sender_label(
            record.get("sender_label") or ""
        )
        if batches:
            previous = str(batches[-1][0].get("sender_fingerprint") or "") or canonical_sender_label(
                batches[-1][0].get("sender_label") or ""
            )
            if sender and sender == previous:
                batches[-1].append(record)
                continue
        batches.append([record])
    return batches


def canonical_sender_label(value: Any) -> str:
    label = canonical_clipboard_text(str(value or ""))
    label = re.sub(r"\s*@\s*", "@", label)
    label = re.sub(r"@we\s*chat\b", "@WeChat", label, flags=re.IGNORECASE)
    label = re.sub(r"\s+", " ", label).strip(" |:：·-")
    if not label or len(label) > 96:
        return ""
    if re.fullmatch(r"\d{1,2}:\d{2}(?:\s*[AP]M)?", label, flags=re.IGNORECASE):
        return ""
    if not re.search(r"[0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff]", label):
        return ""
    return label


def sender_visual_fingerprint(path: Path) -> str:
    if Image is None or ImageOps is None:
        return ""
    try:
        with Image.open(path).convert("L") as image:
            image = ImageOps.autocontrast(image)
            ink = ImageOps.invert(image).point(lambda value: 255 if value >= 35 else 0)
            bounds = ink.getbbox()
            if bounds is None:
                return ""
            image = image.crop(bounds).resize((160, 32), Image.Resampling.LANCZOS)
            normalized = image.point(lambda value: 255 if value >= 190 else 0)
            return hashlib.sha256(normalized.tobytes()).hexdigest()
    except (OSError, ValueError):
        return ""


def similar_text(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def ocr_visual_identity_matches(observed: str, expected: str) -> bool:
    """Accept a same-length ASCII title with only bounded OCR substitutions."""
    left = normalize_text(observed)
    right = normalize_text(expected)
    if not left or len(left) != len(right) or not left.isascii() or not right.isascii():
        return False
    if not left.isalnum() or not right.isalnum():
        return False
    substitutions = {
        ("0", "o"),
        ("1", "i"),
        ("1", "l"),
        ("4", "a"),
        ("5", "s"),
        ("8", "b"),
    }
    return all(actual == wanted or (actual, wanted) in substitutions for actual, wanted in zip(left, right))


def canonical_clipboard_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\x00").strip()


def canonical_composer_text(value: str) -> str:
    # WeCom's rich editor represents one pasted paragraph break as multiple
    # newline code points when copied back. Preserve all non-newline content and
    # spaces while treating that editor-only expansion as equivalent.
    return re.sub(r"\n+", "\n", canonical_clipboard_text(value))


def contains_han(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", str(value or "")))


def choose_ocr_variant(combined: str, chinese: str, english_identifiers: str = "") -> str:
    selected = chinese if contains_han(chinese) and not contains_han(combined) else combined
    return restore_digit_bearing_identifiers(selected, english_identifiers)


def restore_digit_bearing_identifiers(text: str, english_ocr: str) -> str:
    """Recover uppercase scientific IDs when mixed OCR turns `1` into `l`.

    This is deliberately conservative: the English-only pass must contain at
    least two digits, at least two uppercase letters, and a token that differs
    from the mixed-language token only by common `1/l/I` confusions.
    """
    if not contains_han(text):
        return text
    english_tokens = re.findall(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9._/-]{2,31})(?![A-Za-z0-9])", english_ocr)
    candidates = [
        token
        for token in english_tokens
        if sum(char.isdigit() for char in token) >= 2
        and sum(char.isupper() for char in token) >= 2
        and all(not char.isalpha() or char.isupper() for char in token)
    ]
    if not candidates:
        return text

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        matches = [candidate for candidate in candidates if ocr_identifier_confusable_key(candidate) == ocr_identifier_confusable_key(token)]
        return matches[0] if len(matches) == 1 else token

    return re.sub(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9._/-]{2,31})(?![A-Za-z0-9])", replace, text)


def ocr_identifier_confusable_key(value: str) -> str:
    return "".join("1" if char in {"1", "l", "I"} else char for char in str(value).casefold())


def filename_identity_terms(filename: str) -> list[str]:
    path = Path(str(filename))
    stem = normalize_text(path.stem)
    suffix = normalize_text(path.suffix.lstrip("."))
    terms: list[str] = []
    if len(stem) >= 8:
        # WeCom truncates long composer/history labels after roughly twelve
        # visible characters. Exact identity is already proven in the isolated
        # native picker; this shorter prefix verifies that its attachment card
        # actually appeared without trusting a neighboring file.
        terms.append(stem[: min(12, len(stem))])
    elif stem:
        terms.append(stem + suffix)
    if len(stem) >= 16:
        terms.append(stem[-8:] + suffix)
    return unique_nonempty(terms)


def filename_ocr_count(filename: str, ocr_text: str) -> int:
    normalized = normalize_text(ocr_text)
    terms = filename_identity_terms(filename)
    direct = max((normalized.count(term) for term in terms), default=0)
    confusable = ocr_identifier_confusable_key(normalized)
    normalized_terms = [ocr_identifier_confusable_key(term) for term in terms]
    return max(direct, max((confusable.count(term) for term in normalized_terms), default=0))


def filename_matches_ocr(filename: str, ocr_text: str) -> bool:
    return filename_ocr_count(filename, ocr_text) > 0


def chunk_text(text: str, max_chars: int) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    limit = max(240, int(max_chars))
    if len(value) <= limit:
        return [value]
    body_limit = max(200, limit - 16)
    raw_parts: list[str] = []
    remainder = value
    while len(remainder) > body_limit:
        floor = max(1, int(body_limit * 0.55))
        cut = -1
        for marker in (
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            ". ",
            "! ",
            "? ",
            "；",
            "; ",
            "，",
            ", ",
        ):
            candidate = remainder.rfind(marker, floor, body_limit + 1)
            if candidate >= floor:
                cut = max(cut, candidate + len(marker))
        if cut < floor:
            cut = body_limit
        part = remainder[:cut].strip()
        if part:
            raw_parts.append(part)
        remainder = remainder[cut:].strip()
    if remainder:
        raw_parts.append(remainder)
    if len(raw_parts) <= 1:
        return raw_parts or [value]
    total = len(raw_parts)
    return [
        f"[{index}/{total}]\n{part}"
        for index, part in enumerate(raw_parts, start=1)
    ]


def parse_shell_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def parse_json(text: str) -> dict[str, Any] | None:
    source = str(text or "").strip()
    try:
        value = json.loads(source)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing ignored WeCom GUI config: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WeCom GUI config must be a JSON object")
    return value


def write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def unique_nonempty(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    return max(minimum, min(maximum, result))


def bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    return max(minimum, min(maximum, result))


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-._")
    return slug[:80] or short_hash(value)


def short_hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
