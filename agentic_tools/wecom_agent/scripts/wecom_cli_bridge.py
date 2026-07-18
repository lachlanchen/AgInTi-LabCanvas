#!/usr/bin/env python3
"""Poll external WeCom groups through Tencent's official wecom-cli message API.

This transport is intentionally independent from personal-WeChat automation. It
uses a separately authorized WeCom CLI profile, keeps raw identifiers in ignored
private state, and hands normalized events to the existing WeCom ingress.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
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
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_CONFIG = PRIVATE / "wecom_cli_bridge.local.json"
DEFAULT_STATE_DB = PRIVATE / "wecom_cli_bridge.local.sqlite"
DEFAULT_AUTH_DIR = PRIVATE / "wecom-cli-message-config"
DEFAULT_RUNTIME = PRIVATE / "wecom-cli-runtime" / "node_modules" / ".bin" / "wecom-cli"
DEFAULT_TMP_DIR = PRIVATE / "wecom-cli-media"
DEFAULT_EVENT_ROOT = PRIVATE / "wecom-cli-events"
DEFAULT_QUEUE = PRIVATE / "wecom_task_queue.jsonl"
INGEST_SCRIPT = TOOL_ROOT / "scripts" / "wecom_ingest.py"
MAX_CHAT_PAGES = 20
MAX_MESSAGE_PAGES = 20
MAX_INBOUND_BYTES = 100 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="Create or update ignored bridge configuration.")
    initialize.add_argument("--chat", action="append", dest="chats", default=[])
    initialize.add_argument("--force", action="store_true")
    initialize.add_argument("--json", action="store_true")

    for name, help_text in (
        ("probe", "Check official CLI authorization and msg capability."),
        ("status", "Show redacted bridge state."),
        ("once", "Run one bounded discovery and intake cycle."),
        ("loop", "Run polling and the localhost delivery API."),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "init":
        payload = initialize_config(args.config, args.chats, force=args.force)
    else:
        config = load_config(args.config)
        bridge = WeComCliBridge(config, config_path=args.config)
        if args.command == "probe":
            payload = bridge.probe()
        elif args.command == "status":
            payload = bridge.status()
        elif args.command == "once":
            payload = bridge.poll_once()
        else:
            bridge.serve_forever()
            return 0
    print_payload(payload, args.json)
    return 0 if payload.get("ok") else 1


def initialize_config(path: Path, chats: list[str], *, force: bool = False) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if path.is_file() and not force:
        existing = load_config(path)
    target_groups = unique_nonempty([*(existing.get("target_groups") or []), *chats])
    if not target_groups:
        target_groups = ["AgentTest"]
    payload = {
        "schema_version": 1,
        "enabled": True,
        "target_groups": target_groups,
        "account_id": str(existing.get("account_id") or "external"),
        "poll_seconds": bounded_float(existing.get("poll_seconds"), 4.0, 2.0, 300.0),
        "debounce_seconds": bounded_float(existing.get("debounce_seconds"), 3.0, 0.0, 30.0),
        "lookback_seconds": bounded_int(existing.get("lookback_seconds"), 86400, 60, 7 * 86400),
        "max_message_age_seconds": bounded_int(existing.get("max_message_age_seconds"), 1800, 30, 86400),
        "max_batch_messages": bounded_int(existing.get("max_batch_messages"), 8, 1, 30),
        "initial_backfill": str(existing.get("initial_backfill") or "latest"),
        "local_api_host": "127.0.0.1",
        "local_api_port": bounded_int(existing.get("local_api_port"), 19579, 1024, 65535),
        "local_api_token": str(existing.get("local_api_token") or secrets.token_hex(32)),
        "cli_path": str(existing.get("cli_path") or DEFAULT_RUNTIME),
        "auth_config_dir": str(existing.get("auth_config_dir") or DEFAULT_AUTH_DIR),
        "tmp_dir": str(existing.get("tmp_dir") or DEFAULT_TMP_DIR),
        "state_db": str(existing.get("state_db") or DEFAULT_STATE_DB),
        "event_root": str(existing.get("event_root") or DEFAULT_EVENT_ROOT),
        "queue": str(existing.get("queue") or DEFAULT_QUEUE),
        "self_userids": unique_nonempty(existing.get("self_userids") or []),
    }
    write_private_json(path, payload)
    return {
        "ok": True,
        "config_path": str(path),
        "target_groups": target_groups,
        "local_api_url": f"http://127.0.0.1:{payload['local_api_port']}",
    }


class WeComCliBridge:
    def __init__(self, config: dict[str, Any], *, config_path: Path = DEFAULT_CONFIG) -> None:
        self.config = config
        self.config_path = config_path.resolve()
        self.cli_path = Path(str(config.get("cli_path") or DEFAULT_RUNTIME)).expanduser().resolve()
        self.auth_dir = Path(str(config.get("auth_config_dir") or DEFAULT_AUTH_DIR)).expanduser().resolve()
        self.tmp_dir = Path(str(config.get("tmp_dir") or DEFAULT_TMP_DIR)).expanduser().resolve()
        self.state_db = Path(str(config.get("state_db") or DEFAULT_STATE_DB)).expanduser().resolve()
        self.event_root = Path(str(config.get("event_root") or DEFAULT_EVENT_ROOT)).expanduser().resolve()
        self.queue = Path(str(config.get("queue") or DEFAULT_QUEUE)).expanduser().resolve()
        self.target_groups = unique_nonempty(config.get("target_groups") or [])
        self.self_userids = set(unique_nonempty(config.get("self_userids") or []))
        self._stop = threading.Event()
        self._poll_lock = threading.Lock()
        self.tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.event_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        init_state_db(self.state_db)

    def probe(self) -> dict[str, Any]:
        checks = {
            "cli_installed": self.cli_path.is_file() and os.access(self.cli_path, os.X_OK),
            "auth_profile": (self.auth_dir / "bot.enc").is_file(),
            "message_config": (self.auth_dir / "mcp_config.enc").is_file(),
            "target_group_count": len(self.target_groups),
        }
        if not checks["cli_installed"] or not checks["auth_profile"]:
            return {"ok": False, "checks": checks, "error": "official WeCom CLI is not installed or QR-bound"}
        try:
            proc = self.run_cli(["msg", "--help"], timeout=30)
            checks["msg_permission"] = proc.returncode == 0
            error_text = (proc.stderr or proc.stdout).strip()
        except Exception as exc:
            checks["msg_permission"] = False
            error_text = f"{type(exc).__name__}: {str(exc)[:300]}"
        return {
            "ok": bool(checks.get("msg_permission")),
            "checks": checks,
            "error": "" if checks.get("msg_permission") else redact_cli_error(error_text),
        }

    def status(self) -> dict[str, Any]:
        init_state_db(self.state_db)
        with sqlite3.connect(self.state_db) as conn:
            target_count = int(conn.execute("SELECT COUNT(*) FROM target_chats").fetchone()[0])
            seen_count = int(conn.execute("SELECT COUNT(*) FROM seen_messages").fetchone()[0])
            latest = conn.execute("SELECT value FROM runtime WHERE key = 'last_poll_at'").fetchone()
            last_error = conn.execute("SELECT value FROM runtime WHERE key = 'last_error'").fetchone()
        return {
            "ok": True,
            "enabled": bool(self.config.get("enabled", True)),
            "target_groups": self.target_groups,
            "resolved_target_count": target_count,
            "seen_message_count": seen_count,
            "last_poll_at": str(latest[0]) if latest else "",
            "last_error": redact_cli_error(str(last_error[0])) if last_error else "",
            "local_api_url": f"http://127.0.0.1:{bounded_int(self.config.get('local_api_port'), 19579, 1024, 65535)}",
            "transport": "wecom_cli_only",
            "personal_wechat_fallback": False,
        }

    def poll_once(self) -> dict[str, Any]:
        if not self._poll_lock.acquire(blocking=False):
            return {"ok": True, "skipped": "poll_already_running", "processed": 0}
        try:
            result = self._poll_once()
            set_runtime(self.state_db, "last_poll_at", datetime.now().isoformat(timespec="seconds"))
            set_runtime(self.state_db, "last_error", "")
            return result
        except Exception as exc:
            message = f"{type(exc).__name__}: {str(exc)[:1000]}"
            set_runtime(self.state_db, "last_error", message)
            return {"ok": False, "processed": 0, "error": redact_cli_error(message)}
        finally:
            self._poll_lock.release()

    def _poll_once(self) -> dict[str, Any]:
        if not self.target_groups:
            raise RuntimeError("no target_groups are configured")
        now = datetime.now()
        begin = now - timedelta(seconds=bounded_int(self.config.get("lookback_seconds"), 86400, 60, 7 * 86400))
        chats = self.fetch_all("get_msg_chat_list", {"begin_time": fmt_time(begin), "end_time": fmt_time(now)}, "chats", MAX_CHAT_PAGES)
        matches = resolve_exact_target_chats(chats, self.target_groups)
        processed = 0
        seeded = 0
        replies = 0
        errors: list[dict[str, str]] = []
        for target_name in self.target_groups:
            candidates = matches.get(target_name, [])
            if len(candidates) != 1:
                errors.append({
                    "target": target_name,
                    "error": "not_found" if not candidates else "ambiguous_exact_name",
                })
                continue
            chat = candidates[0]
            chat_id = str(chat.get("chat_id") or "").strip()
            if not chat_id:
                errors.append({"target": target_name, "error": "missing_chat_id"})
                continue
            chat_hash = short_hash(chat_id)
            remember_target_chat(self.state_db, target_name, chat_id, chat_hash)
            first_resolution = not chat_has_seen_messages(self.state_db, chat_hash)
            messages = self.fetch_all(
                "get_message",
                {
                    "chat_type": 2,
                    "chatid": chat_id,
                    "begin_time": fmt_time(begin),
                    "end_time": fmt_time(now),
                },
                "messages",
                MAX_MESSAGE_PAGES,
            )
            outcome = self.process_chat_messages(
                target_name=target_name,
                chat_id=chat_id,
                chat_hash=chat_hash,
                messages=messages,
                now=now,
                first_resolution=first_resolution,
            )
            processed += int(outcome.get("processed") or 0)
            seeded += int(outcome.get("seeded") or 0)
            replies += int(outcome.get("replies") or 0)
            if outcome.get("error"):
                errors.append({"target": target_name, "error": str(outcome["error"])[:300]})
        return {
            "ok": not errors,
            "processed": processed,
            "seeded": seeded,
            "replies": replies,
            "resolved_targets": sum(1 for values in matches.values() if len(values) == 1),
            "errors": errors,
        }

    def process_chat_messages(
        self,
        *,
        target_name: str,
        chat_id: str,
        chat_hash: str,
        messages: list[dict[str, Any]],
        now: datetime,
        first_resolution: bool,
    ) -> dict[str, Any]:
        ordered = sorted((item for item in messages if isinstance(item, dict)), key=message_sort_key)
        candidates: list[tuple[str, dict[str, Any]]] = []
        seeded = 0
        max_age = bounded_int(self.config.get("max_message_age_seconds"), 1800, 30, 86400)
        for message in ordered:
            fingerprint = message_fingerprint(chat_id, message)
            if seen_message(self.state_db, fingerprint):
                continue
            if not message_has_supported_content(message):
                remember_seen(self.state_db, fingerprint, chat_hash, message, "unsupported")
                seeded += 1
                continue
            if self.is_outbound_message(chat_hash, message):
                remember_seen(self.state_db, fingerprint, chat_hash, message, "outbound")
                seeded += 1
                continue
            sent_at = parse_time(message.get("send_time"))
            if sent_at and (now - sent_at).total_seconds() > max_age:
                remember_seen(self.state_db, fingerprint, chat_hash, message, "stale")
                seeded += 1
                continue
            candidates.append((fingerprint, message))

        if not candidates:
            return {"processed": 0, "seeded": seeded, "replies": 0}
        newest_time = parse_time(candidates[-1][1].get("send_time"))
        debounce = bounded_float(self.config.get("debounce_seconds"), 3.0, 0.0, 30.0)
        if newest_time and (now - newest_time).total_seconds() < debounce:
            return {"processed": 0, "seeded": seeded, "replies": 0, "waiting_for_debounce": True}

        max_batch = bounded_int(self.config.get("max_batch_messages"), 8, 1, 30)
        if first_resolution and str(self.config.get("initial_backfill") or "latest") == "latest":
            for fingerprint, message in candidates[:-1]:
                remember_seen(self.state_db, fingerprint, chat_hash, message, "initial_seed")
                seeded += 1
            candidates = candidates[-1:]
        elif len(candidates) > max_batch:
            for fingerprint, message in candidates[:-max_batch]:
                remember_seen(self.state_db, fingerprint, chat_hash, message, "overflow_seed")
                seeded += 1
            candidates = candidates[-max_batch:]

        event = self.build_event(target_name, chat_id, chat_hash, candidates)
        event_dir = self.event_root / datetime.now().strftime("%Y%m%d") / chat_hash / short_hash(event["message_id"])
        event_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        event["attachments"] = self.download_batch_media(candidates, event_dir)
        event_path = event_dir / "event.json"
        write_private_json(event_path, event)
        result = self.invoke_ingest(event_path)
        response = str(result.get("reply") or result.get("ack") or "").strip()
        replies = 0
        if response:
            self.send_text(chat_id, chat_hash, response, task_id=f"ingress:{event['message_id']}")
            replies = 1
        for fingerprint, message in candidates:
            remember_seen(self.state_db, fingerprint, chat_hash, message, "processed")
        return {"processed": len(candidates), "seeded": seeded, "replies": replies, "queued": bool(result.get("queued"))}

    def build_event(
        self,
        target_name: str,
        chat_id: str,
        chat_hash: str,
        candidates: list[tuple[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        messages = [item for _, item in candidates]
        text_parts: list[str] = []
        for index, message in enumerate(messages, start=1):
            text = message_text(message)
            if text:
                prefix = f"[Message {index}] " if len(messages) > 1 else ""
                text_parts.append(prefix + text)
        latest = messages[-1]
        identity = ":".join(fingerprint for fingerprint, _ in candidates)
        return {
            "schema_version": 1,
            "transport": "wecom",
            "transport_channel": "wecom_cli",
            "account_id": str(self.config.get("account_id") or "external"),
            "message_id": f"cli:{short_hash(identity)}",
            "chat_id": chat_id,
            "chat_name": target_name,
            "chat_type": "group",
            "sender_userid": f"member:{short_hash(latest.get('userid') or 'external-member')}",
            "authorization_role": "group_member",
            "irreversible_actions_allowed": False,
            "create_time": int((parse_time(latest.get("send_time")) or datetime.now()).timestamp()),
            "msgtype": str(latest.get("msgtype") or "text"),
            "text": "\n".join(text_parts).strip(),
            "quote_text": "",
            "attachments": [],
            "source_message_count": len(messages),
            "chat_hash": chat_hash,
            "received_at": datetime.now().isoformat(timespec="seconds"),
        }

    def download_batch_media(
        self,
        candidates: list[tuple[str, dict[str, Any]]],
        event_dir: Path,
    ) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        for _, message in candidates:
            kind = str(message.get("msgtype") or "").strip().casefold()
            if kind not in {"image", "file", "voice", "video"}:
                continue
            body = message.get(kind) if isinstance(message.get(kind), dict) else {}
            media_id = str(body.get("media_id") or "").strip()
            if not media_id:
                continue
            response = self.call_tool("get_msg_media", {"media_id": media_id}, timeout=130)
            item = response.get("media_item") if isinstance(response.get("media_item"), dict) else {}
            source = Path(str(item.get("local_path") or "")).expanduser().resolve()
            if not source.is_file() or source.is_symlink():
                raise RuntimeError(f"official WeCom CLI returned an unreadable {kind} attachment")
            size = source.stat().st_size
            if size <= 0 or size > MAX_INBOUND_BYTES:
                raise RuntimeError(f"official WeCom {kind} attachment has invalid size")
            requested_name = str(item.get("name") or body.get("name") or source.name)
            filename = normalized_media_filename(requested_name, str(item.get("content_type") or ""), kind)
            target = unique_path(event_dir, filename)
            shutil.copy2(source, target)
            target.chmod(0o600)
            attachments.append({
                "kind": kind,
                "filename": target.name,
                "path": str(target),
                "size_bytes": target.stat().st_size,
            })
        return attachments

    def fetch_all(
        self,
        method: str,
        base_args: dict[str, Any],
        list_key: str,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(max_pages):
            payload = dict(base_args)
            if cursor:
                payload["cursor"] = cursor
            response = self.call_tool(method, payload)
            values = response.get(list_key) if isinstance(response.get(list_key), list) else []
            result.extend(item for item in values if isinstance(item, dict))
            cursor = str(response.get("next_cursor") or "").strip()
            has_more = bool(response.get("has_more")) or bool(cursor)
            if not has_more or not cursor:
                break
        return result

    def call_tool(self, method: str, arguments: dict[str, Any], *, timeout: int = 40) -> dict[str, Any]:
        proc = self.run_cli(["msg", method, json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))], timeout=timeout)
        payload = parse_cli_json(proc.stdout)
        if proc.returncode != 0:
            raise RuntimeError(redact_cli_error(proc.stderr or proc.stdout or f"wecom-cli exited {proc.returncode}"))
        if not isinstance(payload, dict):
            raise RuntimeError("official WeCom CLI returned no JSON object")
        if int(payload.get("errcode") or 0) != 0:
            raise RuntimeError(f"WeCom msg API error {payload.get('errcode')}: {str(payload.get('errmsg') or '')[:300]}")
        return payload

    def run_cli(self, arguments: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        if not self.cli_path.is_file():
            raise RuntimeError(f"official WeCom CLI is not installed at {self.cli_path}")
        env = {
            **os.environ,
            "WECOM_CLI_CONFIG_DIR": str(self.auth_dir),
            "WECOM_CLI_TMP_DIR": str(self.tmp_dir),
        }
        return subprocess.run(
            [str(self.cli_path), *arguments],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def invoke_ingest(self, event_path: Path) -> dict[str, Any]:
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
        proc = subprocess.run(
            [sys.executable, str(INGEST_SCRIPT), "--event-file", str(event_path), "--queue", str(self.queue), "--json"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        payload = parse_cli_json(proc.stdout)
        if proc.returncode != 0 or not isinstance(payload, dict) or not payload.get("ok"):
            detail = payload.get("error") if isinstance(payload, dict) else proc.stderr or proc.stdout
            raise RuntimeError(f"WeCom ingress failed: {str(detail)[:800]}")
        return payload

    def is_outbound_message(self, chat_hash: str, message: dict[str, Any]) -> bool:
        if message.get("is_self") is True or message.get("from_me") is True:
            return True
        if str(message.get("direction") or "").strip().casefold() in {"outbound", "sent", "self"}:
            return True
        userid = str(message.get("userid") or "").strip()
        if userid and userid in self.self_userids:
            return True
        text = message_text(message)
        if not text:
            return False
        sent_at = parse_time(message.get("send_time"))
        return outbound_text_seen(self.state_db, chat_hash, text, sent_at)

    def send_text(self, chat_id: str, chat_hash: str, text: str, *, task_id: str) -> dict[str, Any]:
        chunks = chunk_utf8(text, 1900)
        sent: list[int] = []
        for index, chunk in enumerate(chunks):
            delivery_key = short_hash(f"{task_id}:{index}:{chunk}")
            if delivery_done(self.state_db, delivery_key, chat_hash):
                continue
            response = self.call_tool(
                "send_message",
                {"chat_type": 2, "chatid": chat_id, "msgtype": "text", "text": {"content": chunk}},
            )
            remember_outbound(self.state_db, delivery_key, chat_hash, chunk)
            sent.append(len(chunk.encode("utf-8")))
            if int(response.get("errcode") or 0) != 0:
                raise RuntimeError(f"official WeCom send failed: {response.get('errmsg')}")
        return {"ok": True, "sent_messages": sent, "sent_files": [], "errors": []}

    def serve_forever(self) -> None:
        host = "127.0.0.1"
        port = bounded_int(self.config.get("local_api_port"), 19579, 1024, 65535)
        server = ThreadingHTTPServer((host, port), make_api_handler(self))
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, name="wecom-cli-local-api", daemon=True)
        thread.start()
        print(json.dumps({"ok": True, "event": "started", "transport": "wecom_cli_only", "local_api_port": port}), flush=True)
        interval = bounded_float(self.config.get("poll_seconds"), 4.0, 2.0, 300.0)
        try:
            while not self._stop.is_set():
                result = self.poll_once()
                if not result.get("ok") or result.get("processed"):
                    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
                self._stop.wait(interval)
        finally:
            server.shutdown()
            server.server_close()


def make_api_handler(bridge: WeComCliBridge):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LabCanvasWeComCli/1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self.write_json(404, {"ok": False, "error": "not found"})
                return
            self.write_json(200, bridge.status())

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/send":
                self.write_json(404, {"ok": False, "error": "not found"})
                return
            expected = f"Bearer {bridge.config.get('local_api_token') or ''}"
            if not secrets.compare_digest(str(self.headers.get("Authorization") or ""), expected):
                self.write_json(401, {"ok": False, "error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length < 0 or length > 1024 * 1024:
                    self.write_json(413, {"ok": False, "error": "request body too large"})
                    return
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                chat_id = str(payload.get("chat_id") or "").strip()
                chat_hash = short_hash(chat_id)
                if not target_chat_allowed(bridge.state_db, chat_id, chat_hash, bridge.target_groups):
                    self.write_json(403, {"ok": False, "error": "refusing send to an unresolved external WeCom target"})
                    return
                files = [str(item) for item in payload.get("files") or []]
                result = bridge.send_text(
                    chat_id,
                    chat_hash,
                    str(payload.get("message") or ""),
                    task_id=str(payload.get("task_id") or f"adhoc:{short_hash(chat_id)}"),
                )
                if files:
                    result["ok"] = False
                    result["errors"] = [{"kind": "file", "error": "official wecom-cli msg currently supports text delivery only"}]
                self.write_json(200, result)
            except Exception as exc:
                self.write_json(500, {"ok": False, "error": redact_cli_error(f"{type(exc).__name__}: {str(exc)[:500]}")})

        def write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def init_state_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS target_chats (
                chat_name TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                chat_hash TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_messages (
                fingerprint TEXT PRIMARY KEY,
                chat_hash TEXT NOT NULL,
                send_time TEXT,
                status TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outbound (
                delivery_key TEXT PRIMARY KEY,
                chat_hash TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                sent_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS runtime (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wecom_cli_outbound_match ON outbound(chat_hash, content_hash, sent_at)")


def resolve_exact_target_chats(chats: list[dict[str, Any]], target_names: list[str]) -> dict[str, list[dict[str, Any]]]:
    unique: dict[str, dict[str, dict[str, Any]]] = {name: {} for name in target_names}
    for chat in chats:
        name = str(chat.get("chat_name") or "").strip()
        chat_id = str(chat.get("chat_id") or "").strip()
        if name in unique and chat_id:
            unique[name][chat_id] = chat
    return {name: list(items.values()) for name, items in unique.items()}


def remember_target_chat(path: Path, chat_name: str, chat_id: str, chat_hash: str) -> bool:
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT chat_id FROM target_chats WHERE chat_name = ?", (chat_name,)).fetchone()
        if row and not secrets.compare_digest(str(row[0]), chat_id):
            raise RuntimeError(f"exact WeCom target {chat_name!r} changed identity; refusing automatic rebind")
        conn.execute(
            """
            INSERT INTO target_chats(chat_name, chat_id, chat_hash, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_name) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (chat_name, chat_id, chat_hash, now, now),
        )
    return row is None


def target_chat_allowed(path: Path, chat_id: str, chat_hash: str, target_names: list[str]) -> bool:
    if not chat_id:
        return False
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT chat_name, chat_id FROM target_chats WHERE chat_hash = ?",
            (chat_hash,),
        ).fetchone()
    return bool(row and row[0] in target_names and secrets.compare_digest(str(row[1]), chat_id))


def message_fingerprint(chat_id: str, message: dict[str, Any]) -> str:
    kind = str(message.get("msgtype") or "unknown")
    body = message.get(kind) if isinstance(message.get(kind), dict) else {}
    identity = {
        "chat": chat_id,
        "userid": str(message.get("userid") or ""),
        "send_time": str(message.get("send_time") or ""),
        "msgtype": kind,
        "text": message_text(message),
        "media_id": str(body.get("media_id") or ""),
        "name": str(body.get("name") or ""),
    }
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def seen_message(path: Path, fingerprint: str) -> bool:
    with sqlite3.connect(path) as conn:
        return bool(conn.execute("SELECT 1 FROM seen_messages WHERE fingerprint = ?", (fingerprint,)).fetchone())


def chat_has_seen_messages(path: Path, chat_hash: str) -> bool:
    with sqlite3.connect(path) as conn:
        return bool(conn.execute("SELECT 1 FROM seen_messages WHERE chat_hash = ? LIMIT 1", (chat_hash,)).fetchone())


def remember_seen(path: Path, fingerprint: str, chat_hash: str, message: dict[str, Any], status: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_messages(fingerprint, chat_hash, send_time, status, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (fingerprint, chat_hash, str(message.get("send_time") or ""), status, datetime.now().isoformat(timespec="seconds")),
        )


def remember_outbound(path: Path, delivery_key: str, chat_hash: str, content: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO outbound(delivery_key, chat_hash, content_hash, sent_at) VALUES (?, ?, ?, ?)",
            (delivery_key, chat_hash, short_hash(content), datetime.now().isoformat(timespec="seconds")),
        )


def delivery_done(path: Path, delivery_key: str, chat_hash: str) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT chat_hash FROM outbound WHERE delivery_key = ?", (delivery_key,)).fetchone()
    return bool(row and secrets.compare_digest(str(row[0]), chat_hash))


def outbound_text_seen(path: Path, chat_hash: str, content: str, sent_at: datetime | None) -> bool:
    if not sent_at:
        return False
    begin = (sent_at - timedelta(minutes=5)).isoformat(timespec="seconds")
    end = (sent_at + timedelta(minutes=5)).isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT 1 FROM outbound WHERE chat_hash = ? AND content_hash = ? AND sent_at BETWEEN ? AND ? LIMIT 1",
            (chat_hash, short_hash(content), begin, end),
        ).fetchone()
    return bool(row)


def set_runtime(path: Path, key: str, value: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT OR REPLACE INTO runtime(key, value) VALUES (?, ?)", (key, value))


def message_text(message: dict[str, Any]) -> str:
    body = message.get("text") if isinstance(message.get("text"), dict) else {}
    return str(body.get("content") or "").strip()


def message_has_supported_content(message: dict[str, Any]) -> bool:
    kind = str(message.get("msgtype") or "").strip().casefold()
    if kind == "text":
        return bool(message_text(message))
    if kind not in {"image", "file", "voice", "video"}:
        return False
    body = message.get(kind) if isinstance(message.get(kind), dict) else {}
    return bool(str(body.get("media_id") or "").strip())


def message_sort_key(message: dict[str, Any]) -> tuple[datetime, str]:
    return (parse_time(message.get("send_time")) or datetime.min, message_fingerprint("sort", message))


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def fmt_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def parse_cli_json(text: str) -> dict[str, Any] | None:
    source = str(text or "").strip()
    try:
        value = json.loads(source)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, character in enumerate(source):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(source[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing ignored WeCom CLI bridge config: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WeCom CLI bridge config must be a JSON object")
    return value


def write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def normalized_media_filename(name: str, content_type: str, kind: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", Path(str(name or "")).name).strip("._") or kind
    expected = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) if content_type else None
    if not Path(safe).suffix and expected:
        safe += expected
    return safe[:180]


def unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def chunk_utf8(text: str, max_bytes: int) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for character in value:
        encoded = len(character.encode("utf-8"))
        if current and size + encoded > max_bytes:
            chunks.append("".join(current))
            current = []
            size = 0
        current.append(character)
        size += encoded
    if current:
        chunks.append("".join(current))
    return chunks


def redact_cli_error(value: str) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"(scode=)[^&\s]+", r"\1[redacted]", text, flags=re.I)
    text = re.sub(
        r"((?:chat|user|media|bot)[_-]?id\s*[:=]\s*)\S+",
        r"\1[redacted]",
        text,
        flags=re.I,
    )
    return text[:500]


def short_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def unique_nonempty(values: Any) -> list[str]:
    result: list[str] = []
    for value in values if isinstance(values, (list, tuple, set)) else [values]:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


def bounded_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def bounded_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif payload.get("ok"):
        print("WeCom CLI bridge command completed.")
    else:
        print(payload.get("error") or json.dumps(payload, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
