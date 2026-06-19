#!/usr/bin/env python3
"""Direct WeChat chatops using decrypted local DB rows plus GUI reply sending."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any

import zstandard as zstd

from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_CONFIG = PRIVATE / "lazy-research-direct-chatops.local.json"
DEFAULT_STATE = PRIVATE / "lazy-research-direct-chatops.state.json"
DECRYPTED = PRIVATE / "wechat_decrypt" / "decrypted"
VENV_PYTHON = PRIVATE / "wechat_decrypt" / ".venv" / "bin" / "python"
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--send", action="store_true", help="Send Codex replies back through WeChat GUI.")
    parser.add_argument("--no-decrypt", action="store_true", help="Use the current decrypted DB cache.")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--worker-queue", type=Path, default=DEFAULT_QUEUE, help="Private JSONL queue for slower worker tasks.")
    args = parser.parse_args()

    config = load_config(args.config)
    config["worker_queue"] = str(args.worker_queue)
    while True:
        state = load_state(args.state)
        result = run_once(config, state, send=args.send, no_decrypt=args.no_decrypt)
        save_state(args.state, result["state"])
        print(json.dumps({k: v for k, v in result.items() if k != "state"}, ensure_ascii=False, indent=2), flush=True)
        if not args.loop:
            return 0
        time.sleep(args.poll_seconds)


def load_config(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.setdefault("chat_name", "wechat-chat")
    raw.setdefault("chatroom_id", "")
    raw.setdefault("message_table", "")
    raw.setdefault("self_wxid", "")
    raw.setdefault("trigger_prefixes", ["@lachchen", "＠lachchen", "@codex", "codex:"])
    raw.setdefault("mirror_db", str(DEFAULT_DB))
    raw.setdefault("codex", {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "read-only"})
    raw.setdefault("max_reply_chars", 1200)
    if not raw["message_table"]:
        raise SystemExit(f"Missing message_table in private config: {path}")
    return raw


def refresh_decrypted_store() -> None:
    command = [str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)), str(PRIVATE / "external" / "wechat-decrypt" / "decrypt_db.py")]
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())


def run_once(config: dict[str, Any], state: dict[str, Any], *, send: bool, no_decrypt: bool) -> dict[str, Any]:
    if not no_decrypt:
        refresh_decrypted_store()

    new_rows = read_new_messages(config, state)
    for row in new_rows:
        sync_row_to_mirror(config, row)

    response_sent = None
    task_enqueued = None
    trigger_row = next((row for row in new_rows if should_respond(config, state, row)), None)
    if trigger_row:
        response = run_codex(config, trigger_row, new_rows)
        routed = parse_fast_response(response)
        if routed["task"]:
            task = enqueue_worker_task(config, trigger_row, routed["task"], context_rows=new_rows)
            task_enqueued = task["id"]
        reply_text = routed["chat"] or routed["ack"]
        if reply_text and reply_text != "NO_REPLY":
            status = "dry-run-response"
            screenshot = None
            if send:
                screenshot = send_gui_message(config, reply_text)
                status = "sent"
            record_event(
                chat_name=config["chat_name"],
                action="direct_codex_reply",
                direction="outbound",
                message=reply_text,
                status=status,
                db_path=Path(config.get("mirror_db", DEFAULT_DB)),
                screenshot_path=screenshot,
                metadata={
                    "source_server_id": trigger_row["server_id"],
                    "source_local_id": trigger_row["local_id"],
                    "worker_task_id": task_enqueued,
                },
            )
            state.setdefault("responded_server_ids", []).append(str(trigger_row["server_id"]))
            response_sent = reply_text

    if new_rows:
        state["last_local_id"] = max(row["local_id"] for row in new_rows)
        state["last_seen_at"] = datetime.now().isoformat(timespec="seconds")
    return {"new_rows": len(new_rows), "response_sent": response_sent, "task_enqueued": task_enqueued, "state": state}


def read_new_messages(config: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    db_path = DECRYPTED / "message" / "message_0.db"
    contact_db = DECRYPTED / "contact" / "contact.db"
    last_local_id = int(state.get("last_local_id", 0))
    name_map = load_name_map(db_path)
    contact_map = load_contact_map(contact_db)
    table = config["message_table"]
    rows = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            f"""
            SELECT local_id, server_id, local_type, real_sender_id, create_time,
                   status, message_content, compress_content
            FROM {table}
            WHERE local_id > ?
            ORDER BY local_id
            """,
            (last_local_id,),
        ):
            sender = name_map.get(row["real_sender_id"], str(row["real_sender_id"]))
            rows.append(
                {
                    "local_id": row["local_id"],
                    "server_id": row["server_id"],
                    "local_type": row["local_type"],
                    "real_sender_id": row["real_sender_id"],
                    "sender": sender,
                    "sender_display": contact_map.get(sender, sender),
                    "create_time": row["create_time"],
                    "status": row["status"],
                    "content": decode_content(row["message_content"], row["compress_content"]),
                }
            )
    return rows


def load_name_map(db_path: Path) -> dict[int, str]:
    with sqlite3.connect(db_path) as conn:
        return {rowid: name for rowid, name in conn.execute("SELECT rowid, user_name FROM Name2Id")}


def load_contact_map(db_path: Path) -> dict[str, str]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as conn:
        return {
            username: (remark or nick or alias or username)
            for username, alias, remark, nick in conn.execute("SELECT username, alias, remark, nick_name FROM contact")
        }


def decode_content(message_content: Any, compress_content: Any) -> str:
    for value in (message_content, compress_content):
        if value is None or value == "":
            continue
        if isinstance(value, bytes):
            try:
                return zstd.ZstdDecompressor().decompress(value).decode("utf-8", errors="replace")
            except Exception:
                try:
                    return value.decode("utf-8", errors="replace")
                except Exception:
                    return f"<binary:{len(value)}>"
        return str(value)
    return ""


def sync_row_to_mirror(config: dict[str, Any], row: dict[str, Any]) -> None:
    content = row["content"]
    self_wxid = str(config.get("self_wxid") or "")
    direction = "outbound" if self_wxid and row["sender"] == self_wxid else "inbound"
    record_event(
        chat_name=config["chat_name"],
        action="direct_message",
        direction=direction,
        message=content,
        status="synced",
        db_path=Path(config.get("mirror_db", DEFAULT_DB)),
        metadata=row,
    )


def should_respond(config: dict[str, Any], state: dict[str, Any], row: dict[str, Any]) -> bool:
    self_wxid = str(config.get("self_wxid") or "")
    if self_wxid and row["sender"] == self_wxid:
        return False
    if str(row["server_id"]) in set(state.get("responded_server_ids", [])):
        return False
    text = row["content"]
    return any(prefix in text for prefix in config["trigger_prefixes"])


def run_codex(config: dict[str, Any], row: dict[str, Any], context_rows: list[dict[str, Any]]) -> str:
    codex = config["codex"]
    context = "\n".join(
        f"- local_id={item['local_id']} sender={item['sender_display']} content={item['content']}"
        for item in context_rows[-8:]
    )
    prompt = f"""You are the fast chat agent for WeChat group {config['chat_name']} as lachchen/LabCanvas.
Triggered direct database message:
sender={row['sender']} display={row['sender_display']}
content={row['content']}

Recent direct database context:
{context}

Choose one response shape:
1. CHAT: <one concise helpful chat message>
2. ACK: <one short confirmation for chat>
   TASK: <precise backend task for the worker agent>
3. NO_REPLY

Use ACK+TASK for slower work such as searching/downloading papers, rendering, CAD/PCB work, file conversion, GitHub/MCP work, or anything that will take more than a few seconds.
Do not mention database, OCR, decrypted messages, or automation internals.
"""
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as out:
        output_path = Path(out.name)
    command = [
        "codex",
        "exec",
        "-m",
        codex.get("model", "gpt-5.5"),
        "-c",
        f'model_reasoning_effort="{codex.get("reasoning_effort", "medium")}"',
        "--sandbox",
        codex.get("sandbox", "read-only"),
        "-C",
        str(ROOT),
        "-o",
        str(output_path),
        prompt,
    ]
    subprocess.run(command, capture_output=True, text=True, check=False, timeout=int(codex.get("timeout_seconds", 180)))
    response = output_path.read_text(encoding="utf-8", errors="replace").strip()
    output_path.unlink(missing_ok=True)
    return response[: int(config.get("max_reply_chars", 1200))]


def parse_fast_response(response: str) -> dict[str, str]:
    text = response.strip()
    if not text or text == "NO_REPLY":
        return {"chat": "NO_REPLY", "ack": "", "task": ""}
    routed = {"chat": "", "ack": "", "task": ""}
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("CHAT:"):
            current = "chat"
            routed[current] = stripped.split(":", 1)[1].strip()
        elif upper.startswith("ACK:"):
            current = "ack"
            routed[current] = stripped.split(":", 1)[1].strip()
        elif upper.startswith("TASK:"):
            current = "task"
            routed[current] = stripped.split(":", 1)[1].strip()
        elif current:
            routed[current] = (routed[current] + "\n" + stripped).strip()
        elif not routed["chat"]:
            routed["chat"] = stripped
    if not routed["chat"] and not routed["ack"] and not routed["task"]:
        routed["chat"] = text
    return routed


def enqueue_worker_task(
    config: dict[str, Any],
    row: dict[str, Any],
    task_text: str,
    *,
    context_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    queue = Path(config.get("worker_queue") or DEFAULT_QUEUE)
    queue.parent.mkdir(parents=True, exist_ok=True)
    task = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S") + f"-{row['local_id']}",
        "chat": config["chat_name"],
        "request": task_text,
        "status": "pending",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "server_id": row["server_id"],
            "local_id": row["local_id"],
            "sender": row["sender"],
            "sender_display": row["sender_display"],
        },
        "context": [
            {
                "local_id": item["local_id"],
                "sender": item["sender"],
                "sender_display": item["sender_display"],
                "content": item["content"],
            }
            for item in context_rows[-8:]
        ],
    }
    with queue.open("a", encoding="utf-8") as f:
        f.write(json.dumps(task, ensure_ascii=False) + "\n")
    record_event(
        chat_name=config["chat_name"],
        action="worker_enqueue",
        direction="internal",
        message=task_text,
        status="queued",
        db_path=Path(config.get("mirror_db", DEFAULT_DB)),
        metadata=task,
    )
    return task


def send_gui_message(config: dict[str, Any], message: str) -> str:
    command = [
        sys.executable,
        str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
        "--config",
        str(PRIVATE / "lazy-research-chatops.local.json"),
        "--message",
        message,
    ]
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    try:
        return json.loads(proc.stdout)["screenshot"]
    except Exception:
        return ""


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
