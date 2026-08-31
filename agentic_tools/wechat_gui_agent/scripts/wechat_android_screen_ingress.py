#!/usr/bin/env python3
"""Recover self-authored WeChat text from the dedicated Android display.

The notification bridge covers messages from other people. WeChat does not
notify the account about messages authored by that same account on another
device, so this companion watches the allowlisted chat list for visual changes
and copies new outgoing text through WeChat's native Copy action. It never uses
OCR as the message payload and seeds existing visible history before importing.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
ANDROID_SCRIPTS = ROOT / "agentic_tools" / "android_device_agent" / "scripts"
if str(ANDROID_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ANDROID_SCRIPTS))

from android_control_lease import (
    AndroidControlBusy,
    cooperative_android_control,
    passive_android_control,
    serialized_android_clipboard,
)
from wechat_android_ingress import (
    DEFAULT_DB,
    DEFAULT_TARGETS,
    build_routes,
    ensure_message_table,
    load_configs,
    load_targets,
    resolve_serial,
)
from wechat_android_send import (
    AndroidWechatError,
    AndroidWechatSender,
    DEFAULT_CLIPBOARD_LOCK,
    DEFAULT_PRIORITY,
    DEFAULT_STATE_DB,
    OcrLine,
    enhanced_ocr_lines,
    find_action_line,
    image_size,
    matching_target_lines,
    merge_chat_title_fragments,
    normalize_text,
    ocr_lines,
    target_aliases,
)


DEFAULT_OUTPUT = ROOT / "output" / "wechat_android_screen_ingress"
OUTGOING_GREEN = (149, 236, 105)
COPY_LABELS = ("复制", "複製", "Copy")
SELECT_ALL_LABELS = ("全选", "全選", "Select all", "Select All")


class AndroidScreenIngressError(RuntimeError):
    """Raised when exact-chat screen intake cannot be proved."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", ""))
    parser.add_argument("--configs", default=os.environ.get("WECHAT_DIRECT_CONFIGS", ""))
    parser.add_argument("--targets-file", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--send-state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--interval", type=float, default=4.0)
    parser.add_argument(
        "--audit-interval",
        type=float,
        default=float(os.environ.get("WECHAT_ANDROID_SCREEN_ROUTE_AUDIT_SECONDS", "180")),
        help="Periodically open one unchanged route so same-account messages cannot be hidden by a stale chat-row signature.",
    )
    parser.add_argument("--max-bubbles", type=int, default=8)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    serial = resolve_serial(args.adb, args.serial)
    scanner = AndroidWechatScreenIngress(
        adb=args.adb,
        serial=serial,
        configs=load_configs(args.configs),
        targets=load_targets(args.targets_file),
        db_path=args.db.expanduser().resolve(),
        send_state_db=args.send_state_db.expanduser().resolve(),
        output_dir=args.output_dir.expanduser().resolve(),
        max_bubbles=max(1, min(16, int(args.max_bubbles))),
        audit_interval_seconds=max(30.0, float(args.audit_interval)),
    )
    if args.status:
        print(json.dumps(scanner.status(), ensure_ascii=False, indent=2))
        return 0

    while True:
        result = scanner.run_once()
        if result.get("imported") or result.get("seeded") or result.get("error"):
            print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.loop:
            return 0 if result.get("ok") else 1
        time.sleep(max(1.0, float(args.interval)))


class AndroidWechatScreenIngress:
    def __init__(
        self,
        *,
        adb: str,
        serial: str,
        configs: list[dict[str, Any]],
        targets: dict[str, Any],
        db_path: Path,
        send_state_db: Path,
        output_dir: Path,
        max_bubbles: int = 8,
        audit_interval_seconds: float = 180.0,
    ) -> None:
        self.adb = adb
        self.serial = serial
        self.configs = configs
        self.targets = targets
        self.db_path = db_path
        self.send_state_db = send_state_db
        self.output_dir = output_dir
        self.max_bubbles = max_bubbles
        self.audit_interval_seconds = max(30.0, float(audit_interval_seconds))
        self.display = os.environ.get("WECHAT_ANDROID_DISPLAY", ":99")
        self.routes = screen_routes(configs, targets)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with sqlite_connection(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS Name2Id (user_name TEXT UNIQUE)")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS AndroidIngressSeen ("
                "item_key TEXT PRIMARY KEY, event_sequence INTEGER NOT NULL, "
                "status TEXT NOT NULL, config_id TEXT NOT NULL DEFAULT '', "
                "seen_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS AndroidScreenRoutes ("
                "config_id TEXT PRIMARY KEY, chat_name TEXT NOT NULL, "
                "row_signature TEXT NOT NULL DEFAULT '', "
                "snapshot_json TEXT NOT NULL DEFAULT '[]', initialized INTEGER NOT NULL DEFAULT 0, "
                "updated_at TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS AndroidScreenMeta ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS AndroidScreenOutboundConsumed ("
                "component_key TEXT PRIMARY KEY, consumed_at TEXT NOT NULL)"
            )
            for route in self.routes:
                ensure_message_table(conn, route["message_table"])
                conn.execute(
                    "INSERT OR IGNORE INTO AndroidScreenRoutes("
                    "config_id,chat_name,row_signature,snapshot_json,initialized,updated_at"
                    ") VALUES(?,?,?,? ,0,?)",
                    (route["config_id"], route["chat_name"], "", "[]", utc_now()),
                )
        os.chmod(self.db_path, 0o600)

    def status(self) -> dict[str, Any]:
        with sqlite_connection(self.db_path) as conn:
            seeded = int(
                conn.execute(
                    "SELECT COUNT(*) FROM AndroidScreenRoutes WHERE initialized = 1"
                ).fetchone()[0]
            )
            imported = int(
                conn.execute(
                    "SELECT COUNT(*) FROM AndroidIngressSeen WHERE status = 'screen_imported'"
                ).fetchone()[0]
            )
        last_success = self.meta("last_success_at")
        success_age = timestamp_age_seconds(last_success)
        health_max_gap = max(
            30.0,
            float(os.environ.get("WECHAT_ANDROID_SCREEN_HEALTH_MAX_GAP", "90")),
        )
        catchup_overdue = success_age is None or success_age > health_max_gap
        return {
            "ok": (
                bool(self.routes)
                and seeded == len(self.routes)
                and not self.meta("last_error")
                and not catchup_overdue
            ),
            "routes": len(self.routes),
            "seeded_routes": seeded,
            "imported": imported,
            "last_poll_at": self.meta("last_poll_at"),
            "last_success_at": last_success,
            "last_success_age_seconds": success_age,
            "catchup_overdue": catchup_overdue,
            "last_error": self.meta("last_error"),
            "deferred_routes": self.deferred_route_count(),
            "transport": "wechat_android_screen_self_text",
        }

    def run_once(self) -> dict[str, Any]:
        if not self.routes:
            return self.fail("no screen-ingress routes are configured")
        navigator = self.sender_for(self.routes[0], task_id="screen-ingress-nav")
        try:
            with passive_android_control(
                lock_path=navigator.device_lock_path(),
                priority_path=DEFAULT_PRIORITY,
                purpose="personal_wechat_screen_ingress",
            ):
                result = self.run_with_restore(navigator)
        except AndroidControlBusy:
            if not self.preemption_due():
                self.set_meta("last_poll_at", utc_now())
                return safe_result(skipped="android_control_busy")
            try:
                with cooperative_android_control(
                    lock_path=navigator.device_lock_path(),
                    priority_path=DEFAULT_PRIORITY,
                    purpose="personal_wechat_screen_ingress",
                    timeout_seconds=float(
                        os.environ.get("WECHAT_ANDROID_SCREEN_LOCK_TIMEOUT", "30")
                    ),
                ):
                    result = self.run_with_restore(navigator)
            except (AndroidControlBusy, TimeoutError):
                self.set_meta("last_poll_at", utc_now())
                return safe_result(skipped="android_control_busy")
            except (
                AndroidScreenIngressError,
                AndroidWechatError,
                OSError,
                sqlite3.Error,
                subprocess.SubprocessError,
            ) as exc:
                return self.fail(f"{type(exc).__name__}: {str(exc)[:500]}")
        except (
            AndroidScreenIngressError,
            AndroidWechatError,
            OSError,
            sqlite3.Error,
            subprocess.SubprocessError,
        ) as exc:
            return self.fail(f"{type(exc).__name__}: {str(exc)[:500]}")
        now = utc_now()
        self.set_meta("last_poll_at", now)
        self.set_meta("last_success_at", now)
        self.set_meta("last_error", "")
        return result

    def run_with_restore(self, navigator: AndroidWechatSender) -> dict[str, Any]:
        try:
            return self.run_locked(navigator)
        finally:
            try:
                navigator.restore_wecom()
            except (AndroidWechatError, OSError, subprocess.SubprocessError):
                pass

    def preemption_due(self) -> bool:
        last_success = self.meta("last_success_at")
        if not last_success:
            return True
        try:
            observed = datetime.fromisoformat(last_success)
        except ValueError:
            return True
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        maximum_gap = max(
            10.0,
            float(os.environ.get("WECHAT_ANDROID_SCREEN_MAX_GAP", "30")),
        )
        return (datetime.now(timezone.utc) - observed).total_seconds() >= maximum_gap

    def run_locked(self, navigator: AndroidWechatSender) -> dict[str, Any]:
        current = navigator.screenshot("current")
        current_signature = stable_screen_signature(current)
        previous_signature = self.meta("chat_list_signature")
        if (
            previous_signature
            and current_signature == previous_signature
            and self.all_routes_seeded()
            and not self.any_route_retry_due()
            and not self.any_route_audit_due()
        ):
            return safe_result(skipped="chat_list_unchanged")

        chat_list, rows = self.ensure_chat_list(navigator, current)
        row_signatures = {
            route["config_id"]: chat_row_signature(chat_list, rows[route["config_id"]])
            for route in self.routes
            if route["config_id"] in rows
        }
        route = self.next_route(row_signatures)
        if route is None:
            deferred_routes = self.deferred_route_count(row_signatures)
            if deferred_routes:
                self.set_meta("chat_list_signature", stable_screen_signature(chat_list))
                return safe_result(
                    skipped="route_retry_backoff",
                    deferred_routes=deferred_routes,
                )
            self.save_row_signatures(row_signatures)
            self.set_meta("chat_list_signature", stable_screen_signature(chat_list))
            return safe_result(skipped="no_changed_route")

        line = rows.get(route["config_id"])
        if line is None:
            raise AndroidScreenIngressError(
                f"exact allowlisted chat is not visible: {route['chat_name']}"
            )
        sender = self.sender_for(route, task_id=f"screen-ingress-{route['config_id']}")
        if not sender.open_target_line(line):
            retry_after = self.defer_route(
                route["config_id"],
                row_signatures[route["config_id"]],
            )
            self.set_meta("chat_list_signature", stable_screen_signature(chat_list))
            return safe_result(
                skipped="exact_title_guard_deferred",
                deferred_routes=self.deferred_route_count(row_signatures),
                retry_after_seconds=retry_after,
            )
        self.clear_route_defer(route["config_id"])
        conversation = sender.screenshot("conversation-tail")
        texts = self.copy_visible_outgoing_texts(sender, conversation)
        state = self.route_state(route["config_id"])
        previous = state["snapshot"]
        seeded = not state["initialized"]
        new_messages = [] if seeded else new_visible_messages(previous, texts)
        imported = 0
        outbound_echoes = 0
        for index, text in enumerate(new_messages):
            if self.recorded_outbound_echo(route, text):
                outbound_echoes += 1
                continue
            if self.insert_message(route, text, index=index):
                imported += 1
        self.save_route_state(
            route,
            row_signature=row_signatures[route["config_id"]],
            snapshot=texts,
            initialized=True,
        )
        self.set_meta(f"route_audited:{route['config_id']}", utc_now())

        sender.keyevent(4, check=False)
        time.sleep(0.5)
        final_list, final_rows = self.ensure_chat_list(sender)
        final_signatures = {
            item["config_id"]: chat_row_signature(final_list, final_rows[item["config_id"]])
            for item in self.routes
            if item["config_id"] in final_rows
        }
        processed_signature = final_signatures.get(route["config_id"])
        if processed_signature:
            self.save_row_signatures(
                {route["config_id"]: processed_signature},
                preserve_processed_snapshot=True,
            )
        self.set_meta("chat_list_signature", stable_screen_signature(final_list))
        return safe_result(
            chat=route["chat_name"],
            seeded=1 if seeded else 0,
            visible=len(texts),
            imported=imported,
            outbound_echoes=outbound_echoes,
        )

    def sender_for(self, route: dict[str, Any], *, task_id: str) -> AndroidWechatSender:
        return AndroidWechatSender(
            adb=self.adb,
            serial=self.serial,
            target=route["target"],
            task_id=task_id,
            state_db=self.send_state_db,
            output_dir=self.output_dir / datetime.now().strftime("%F"),
            max_list_pages=2,
        )

    def ensure_chat_list(
        self,
        sender: AndroidWechatSender,
        screenshot: Path | None = None,
    ) -> tuple[Path, dict[str, OcrLine]]:
        if screenshot is not None:
            rows = route_rows(screenshot, self.routes)
            if len(rows) >= min(2, len(self.routes)):
                return screenshot, rows
        sender.wake_and_launch()
        current = None
        for attempt in range(7):
            current = current or sender.screenshot(f"chat-list-probe-{attempt}")
            rows = route_rows(current, self.routes)
            if len(rows) >= min(2, len(self.routes)):
                return current, rows
            sender.keyevent(4, check=False)
            time.sleep(0.45)
            current = sender.screenshot(f"chat-list-back-{attempt}")
        raise AndroidScreenIngressError("personal WeChat chat list was not recoverable")

    def next_route(self, row_signatures: dict[str, str]) -> dict[str, Any] | None:
        states = {route["config_id"]: self.route_state(route["config_id"]) for route in self.routes}
        for route in self.routes:
            config_id = route["config_id"]
            signature = row_signatures.get(config_id, "")
            if (
                signature
                and not states[config_id]["initialized"]
                and not self.route_retry_deferred(config_id, signature)
            ):
                return route
        for route in self.routes:
            config_id = route["config_id"]
            if config_id not in row_signatures:
                continue
            previous = states[config_id]["row_signature"]
            if (
                previous
                and previous != row_signatures[config_id]
                and not self.route_retry_deferred(
                    config_id, row_signatures[config_id]
                )
            ):
                return route
        for route in self.routes:
            config_id = route["config_id"]
            if (
                config_id in row_signatures
                and self.route_audit_due(config_id)
                and not self.route_retry_deferred(config_id, row_signatures[config_id])
            ):
                return route
        return None

    def route_audit_due(self, config_id: str) -> bool:
        observed = self.meta(f"route_audited:{config_id}")
        age = timestamp_age_seconds(observed)
        return age is None or age >= self.audit_interval_seconds

    def any_route_audit_due(self) -> bool:
        return any(
            self.route_audit_due(route["config_id"])
            for route in self.routes
        )

    def route_retry_state(self, config_id: str) -> dict[str, Any]:
        try:
            payload = json.loads(self.meta(f"route_retry:{config_id}") or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def route_retry_deferred(self, config_id: str, signature: str) -> bool:
        state = self.route_retry_state(config_id)
        if str(state.get("signature") or "") != str(signature or ""):
            return False
        try:
            return float(state.get("next_attempt_at") or 0) > time.time()
        except (TypeError, ValueError):
            return False

    def any_route_retry_due(self) -> bool:
        now = time.time()
        for route in self.routes:
            state = self.route_retry_state(route["config_id"])
            try:
                next_attempt = float(state.get("next_attempt_at") or 0)
            except (TypeError, ValueError):
                continue
            if state.get("signature") and 0 < next_attempt <= now:
                return True
        return False

    def deferred_route_count(
        self,
        row_signatures: dict[str, str] | None = None,
    ) -> int:
        count = 0
        for route in self.routes:
            config_id = route["config_id"]
            state = self.route_retry_state(config_id)
            signature = str(state.get("signature") or "")
            if not signature:
                continue
            if row_signatures is not None and row_signatures.get(config_id) != signature:
                continue
            try:
                next_attempt = float(state.get("next_attempt_at") or 0)
            except (TypeError, ValueError):
                continue
            if next_attempt > time.time():
                count += 1
        return count

    def defer_route(self, config_id: str, signature: str) -> int:
        previous = self.route_retry_state(config_id)
        same_signature = str(previous.get("signature") or "") == signature
        try:
            previous_count = int(previous.get("failure_count") or 0)
        except (TypeError, ValueError):
            previous_count = 0
        failure_count = previous_count + 1 if same_signature else 1
        base = max(
            5,
            int(float(os.environ.get("WECHAT_ANDROID_SCREEN_ROUTE_RETRY_BASE", "15"))),
        )
        delay = min(300, base * (2 ** min(4, failure_count - 1)))
        self.set_meta(
            f"route_retry:{config_id}",
            json.dumps(
                {
                    "signature": signature,
                    "failure_count": failure_count,
                    "next_attempt_at": time.time() + delay,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        return delay

    def clear_route_defer(self, config_id: str) -> None:
        self.set_meta(f"route_retry:{config_id}", "")

    def all_routes_seeded(self) -> bool:
        with sqlite_connection(self.db_path) as conn:
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM AndroidScreenRoutes WHERE initialized = 1"
                ).fetchone()[0]
            )
        return count == len(self.routes)

    def copy_visible_outgoing_texts(
        self,
        sender: AndroidWechatSender,
        screenshot: Path,
    ) -> list[str]:
        regions = find_outgoing_bubbles(screenshot)[-self.max_bubbles :]
        texts = []
        for index, region in enumerate(regions):
            text = self.copy_bubble(sender, region, probe_id=str(index))
            if text:
                texts.append(text)
        return texts

    def copy_bubble(
        self,
        sender: AndroidWechatSender,
        region: tuple[int, int, int, int, int],
        *,
        probe_id: str,
    ) -> str:
        left, top, right, bottom, _area = region
        sentinel = f"__LABCANVAS_WECHAT_COPY_{os.getpid()}_{probe_id}_{time.time_ns()}__"
        with serialized_android_clipboard(
            lock_path=DEFAULT_CLIPBOARD_LOCK,
            timeout_seconds=2.0,
        ):
            set_x_clipboard(self.display, sentinel)
            sender.swipe(
                int((left + right) / 2),
                int((top + bottom) / 2),
                int((left + right) / 2),
                int((top + bottom) / 2),
                850,
            )
            time.sleep(0.55)
            menu = sender.screenshot(f"copy-menu-{probe_id}")
            box = dark_menu_box(menu)
            select_all = menu_action(menu, box, SELECT_ALL_LABELS)
            if select_all is not None:
                sender.tap(select_all.center_x, select_all.center_y)
                time.sleep(0.35)
                menu = sender.screenshot(f"copy-menu-selected-all-{probe_id}")
                box = dark_menu_box(menu)
            action = copy_action(menu, box)
            if action is None:
                sender.keyevent(4, check=False)
                time.sleep(0.2)
                return ""
            sender.tap(action.center_x, action.center_y)
            time.sleep(0.45)
            copied = get_x_clipboard(self.display)
        if not copied or copied == sentinel:
            return ""
        copied = copied.replace("\r\n", "\n").replace("\r", "\n").strip()
        return copied[:64000]

    def route_state(self, config_id: str) -> dict[str, Any]:
        with sqlite_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT row_signature,snapshot_json,initialized FROM AndroidScreenRoutes "
                "WHERE config_id = ?",
                (config_id,),
            ).fetchone()
        if not row:
            return {"row_signature": "", "snapshot": [], "initialized": False}
        try:
            snapshot = json.loads(row[1])
        except json.JSONDecodeError:
            snapshot = []
        return {
            "row_signature": str(row[0] or ""),
            "snapshot": [str(item) for item in snapshot if str(item).strip()]
            if isinstance(snapshot, list)
            else [],
            "initialized": bool(row[2]),
        }

    def save_route_state(
        self,
        route: dict[str, Any],
        *,
        row_signature: str,
        snapshot: list[str],
        initialized: bool,
    ) -> None:
        with sqlite_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE AndroidScreenRoutes SET row_signature=?,snapshot_json=?,"
                "initialized=?,updated_at=? WHERE config_id=?",
                (
                    row_signature,
                    json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                    1 if initialized else 0,
                    utc_now(),
                    route["config_id"],
                ),
            )

    def save_row_signatures(
        self,
        signatures: dict[str, str],
        *,
        preserve_processed_snapshot: bool = False,
    ) -> None:
        del preserve_processed_snapshot
        with sqlite_connection(self.db_path) as conn:
            for config_id, signature in signatures.items():
                conn.execute(
                    "UPDATE AndroidScreenRoutes SET row_signature=?,updated_at=? "
                    "WHERE config_id=?",
                    (signature, utc_now(), config_id),
                )

    def insert_message(self, route: dict[str, Any], content: str, *, index: int) -> bool:
        sequence = int(self.meta("sequence") or 0) + 1
        self.set_meta("sequence", str(sequence))
        identity = json.dumps(
            {
                "config": route["config_id"],
                "sequence": sequence,
                "index": index,
                "content": content,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        item_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        sender = str(route.get("self_wxid") or "wechat-self")
        table = route["message_table"]
        with sqlite_connection(self.db_path, timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute(
                "SELECT 1 FROM AndroidIngressSeen WHERE item_key = ?", (item_key,)
            ).fetchone():
                return False
            conn.execute("INSERT OR IGNORE INTO Name2Id(user_name) VALUES (?)", (sender,))
            sender_row = conn.execute(
                "SELECT rowid FROM Name2Id WHERE user_name = ?", (sender,)
            ).fetchone()
            next_local = int(
                conn.execute(f"SELECT COALESCE(MAX(local_id), 0) + 1 FROM {table}").fetchone()[0]
            )
            conn.execute(
                f"INSERT INTO {table}(local_id,server_id,local_type,real_sender_id,create_time,"
                "status,message_content,compress_content,WCDB_CT_message_content) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    next_local,
                    "android-screen-" + item_key[:32],
                    1,
                    int(sender_row[0]),
                    int(time.time()) + index,
                    3,
                    content,
                    None,
                    0,
                ),
            )
            conn.execute(
                "INSERT INTO AndroidIngressSeen(item_key,event_sequence,status,config_id,seen_at) "
                "VALUES(?,?,?,?,?)",
                (item_key, sequence, "screen_imported", route["config_id"], utc_now()),
            )
        return True

    def recorded_outbound_echo(self, route: dict[str, Any], text: str) -> bool:
        if not self.send_state_db.exists():
            return False
        digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
        try:
            with sqlite_connection(self.send_state_db) as conn:
                rows = conn.execute(
                    "SELECT component_key,chat FROM components "
                    "WHERE kind='text' AND status='sent' "
                    "AND value_hash=? ORDER BY updated_at DESC LIMIT 20",
                    (digest,),
                ).fetchall()
        except sqlite3.Error:
            return False
        aliases = target_aliases(route["target"])
        for component_key, chat in rows:
            if not any(
                normalize_text(chat) == normalize_text(alias) for alias in aliases
            ):
                continue
            with sqlite_connection(self.db_path) as conn:
                before = conn.total_changes
                conn.execute(
                    "INSERT OR IGNORE INTO AndroidScreenOutboundConsumed("
                    "component_key,consumed_at) VALUES(?,?)",
                    (str(component_key), utc_now()),
                )
                if conn.total_changes > before:
                    return True
        return False

    def meta(self, key: str) -> str:
        with sqlite_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM AndroidScreenMeta WHERE key=?", (key,)
            ).fetchone()
        return str(row[0]) if row else ""

    def set_meta(self, key: str, value: str) -> None:
        with sqlite_connection(self.db_path) as conn:
            conn.execute(
                "INSERT INTO AndroidScreenMeta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def fail(self, message: str) -> dict[str, Any]:
        self.set_meta("last_poll_at", utc_now())
        self.set_meta("last_error", message[:500])
        return safe_result(ok=False, error=message[:500])


def screen_routes(
    configs: list[dict[str, Any]], targets: dict[str, Any]
) -> list[dict[str, Any]]:
    configs_by_id = {str(config.get("config_id") or ""): config for config in configs}
    result = []
    for route in build_routes(configs, targets):
        config = configs_by_id.get(route["config_id"], {})
        chat_name = str(route["chat_name"])
        send_target = str(config.get("send_target") or chat_name)
        target = targets.get(send_target) or targets.get(chat_name)
        if not isinstance(target, dict):
            continue
        item = dict(route)
        item["target"] = {**target, "name": str(target.get("name") or send_target)}
        item["self_wxid"] = str(config.get("self_wxid") or "")
        result.append(item)
    return result


def route_rows(path: Path, routes: list[dict[str, Any]]) -> dict[str, OcrLine]:
    width, height = image_size(path)
    raw = ocr_lines(path)
    rows = route_rows_from_lines(raw, routes, width=width, height=height)
    if len(rows) >= min(2, len(routes)):
        return rows
    enhanced = enhanced_ocr_lines(path)
    return route_rows_from_lines(
        [*raw, *enhanced], routes, width=width, height=height
    )


def route_rows_from_lines(
    lines: list[OcrLine],
    routes: list[dict[str, Any]],
    *,
    width: int,
    height: int,
) -> dict[str, OcrLine]:
    candidates = [*lines, *merge_chat_title_fragments(lines)]
    result: dict[str, OcrLine] = {}
    claimed_y: list[int] = []
    for route in routes:
        matched = matching_target_lines(candidates, tuple(route["aliases"]))
        matched = [
            line
            for line in matched
            if int(height * 0.08) <= line.center_y <= int(height * 0.88)
            and line.left <= int(width * 0.82)
        ]
        exact_aliases = {
            normalize_text(alias)
            for alias in route["aliases"]
            if normalize_text(alias)
        }
        matched.sort(
            key=lambda line: (
                0 if normalize_text(line.text) in exact_aliases else 1,
                -(line.bottom - line.top),
                line.top,
                line.left,
            )
        )
        selected = next(
            (line for line in matched if all(abs(line.center_y - y) > 20 for y in claimed_y)),
            None,
        )
        if selected is not None:
            result[route["config_id"]] = selected
            claimed_y.append(selected.center_y)
    return result


def stable_screen_signature(path: Path) -> str:
    with Image.open(path).convert("L") as image:
        width, height = image.size
        observed = image.crop((0, int(height * 0.09), width, int(height * 0.89)))
        observed = observed.resize((96, 128), Image.Resampling.BILINEAR)
        values = np.asarray(observed, dtype=np.uint8)
        quantized = ((values // 16) * 16).tobytes()
    return hashlib.sha256(quantized).hexdigest()


def chat_row_signature(path: Path, line: OcrLine) -> str:
    with Image.open(path).convert("L") as image:
        width, height = image.size
        top = max(int(height * 0.08), line.top - 24)
        bottom = min(int(height * 0.90), line.bottom + 95)
        observed = image.crop((15, top, width - 15, bottom))
        observed = observed.resize((160, 28), Image.Resampling.BILINEAR)
        values = np.asarray(observed, dtype=np.uint8)
        quantized = ((values // 16) * 16).tobytes()
    return hashlib.sha256(quantized).hexdigest()


def find_outgoing_bubbles(path: Path) -> list[tuple[int, int, int, int, int]]:
    with Image.open(path).convert("RGB") as image:
        pixels = np.asarray(image, dtype=np.int16)
    height, width, _channels = pixels.shape
    target = np.asarray(OUTGOING_GREEN, dtype=np.int16)
    mask = np.max(np.abs(pixels - target), axis=2) <= 9
    mask[: int(height * 0.12), :] = False
    mask[int(height * 0.90) :, :] = False
    row_counts = mask.sum(axis=1)
    active_rows = np.flatnonzero(row_counts >= max(18, int(width * 0.016)))
    groups = consecutive_groups(active_rows)
    regions = []
    for top, bottom in groups:
        selected = mask[top : bottom + 1]
        ys, xs = np.nonzero(selected)
        if not len(xs):
            continue
        left = int(xs.min())
        right = int(xs.max()) + 1
        actual_top = top + int(ys.min())
        actual_bottom = top + int(ys.max()) + 1
        area = int(selected.sum())
        if (
            area >= 1200
            and right - left >= 70
            and actual_bottom - actual_top >= 28
            and right >= int(width * 0.60)
            and left >= int(width * 0.08)
        ):
            regions.append((left, actual_top, right, actual_bottom, area))
    return regions


def consecutive_groups(values: np.ndarray) -> list[tuple[int, int]]:
    if not len(values):
        return []
    groups = []
    start = previous = int(values[0])
    for raw in values[1:]:
        value = int(raw)
        if value > previous + 1:
            groups.append((start, previous))
            start = value
        previous = value
    groups.append((start, previous))
    return groups


def dark_menu_box(path: Path) -> tuple[int, int, int, int] | None:
    with Image.open(path).convert("RGB") as image:
        pixels = np.asarray(image, dtype=np.int16)
    height, width, _channels = pixels.shape
    channel_spread = pixels.max(axis=2) - pixels.min(axis=2)
    mean = pixels.mean(axis=2)
    mask = (channel_spread <= 8) & (mean >= 45) & (mean <= 95)
    row_counts = mask.sum(axis=1)
    active = np.flatnonzero(row_counts >= int(width * 0.35))
    boxes = []
    for top, bottom in consecutive_groups(active):
        selected = mask[top : bottom + 1]
        ys, xs = np.nonzero(selected)
        if not len(xs):
            continue
        left = int(xs.min())
        right = int(xs.max()) + 1
        actual_bottom = top + int(ys.max()) + 1
        if right - left >= int(width * 0.45) and actual_bottom - top >= 120:
            boxes.append((left, top, right, actual_bottom))
    return max(boxes, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), default=None)


def copy_action(path: Path, box: tuple[int, int, int, int] | None) -> OcrLine | None:
    return menu_action(path, box, COPY_LABELS)


def menu_action(
    path: Path,
    box: tuple[int, int, int, int] | None,
    labels: tuple[str, ...],
) -> OcrLine | None:
    if box is None:
        return None
    left, top, right, bottom = box
    candidates = [
        line
        for line in ocr_lines(path)
        if left <= line.center_x <= right and top <= line.center_y <= bottom
    ]
    return find_action_line(candidates, labels)


def set_x_clipboard(display: str, value: str) -> None:
    env = {**os.environ, "DISPLAY": display}
    proc = subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=value,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
        env=env,
    )
    if proc.returncode != 0:
        raise AndroidScreenIngressError("physical scrcpy clipboard is unavailable")


def get_x_clipboard(display: str) -> str:
    env = {**os.environ, "DISPLAY": display}
    proc = subprocess.run(
        ["xclip", "-selection", "clipboard", "-o"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
        env=env,
    )
    return proc.stdout if proc.returncode == 0 else ""


def new_visible_messages(previous: list[str], current: list[str]) -> list[str]:
    if not current or current == previous:
        return []
    maximum = min(len(previous), len(current))
    for overlap in range(maximum, 0, -1):
        if previous[-overlap:] == current[:overlap]:
            return current[overlap:]
    remaining = Counter(previous)
    new = []
    for text in current:
        if remaining[text] > 0:
            remaining[text] -= 1
        else:
            new.append(text)
    return new


@contextmanager
def sqlite_connection(
    path: Path,
    *,
    timeout: float = 5.0,
) -> Any:
    """Commit or roll back like sqlite's context manager, then really close."""
    connection = sqlite3.connect(path, timeout=timeout)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def timestamp_age_seconds(value: str) -> float | None:
    if not value:
        return None
    try:
        observed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - observed).total_seconds())


def safe_result(**values: Any) -> dict[str, Any]:
    result = {
        "ok": True,
        "seeded": 0,
        "visible": 0,
        "imported": 0,
        "outbound_echoes": 0,
        "skipped": "",
    }
    result.update(values)
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
