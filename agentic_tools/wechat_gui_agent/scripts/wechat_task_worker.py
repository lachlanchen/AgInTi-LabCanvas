#!/usr/bin/env python3
"""Worker-side helper for slower WeChat chatops tasks."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--chat", default="懒人科研")
    parser.add_argument("--enqueue", help="Add a task to the private queue and exit.")
    parser.add_argument("--once", action="store_true", help="Process one pending task.")
    parser.add_argument("--loop", action="store_true", help="Continuously process pending tasks.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--send", action="store_true", help="Send worker result back to WeChat.")
    args = parser.parse_args()

    if args.enqueue:
        task = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "chat": args.chat,
            "request": args.enqueue,
            "status": "pending",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        append_jsonl(args.queue, task)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    if args.once or args.loop:
        while True:
            processed = process_one(args.queue, args.chat, send=args.send)
            if not args.loop:
                return 0
            if not processed:
                import time

                time.sleep(args.poll_seconds)
        return 0
    raise SystemExit("Use --enqueue, --once, or --loop")


def process_one(queue: Path, chat: str, *, send: bool) -> bool:
    task = next_pending(queue)
    if not task:
        print(json.dumps({"status": "no-pending-task"}, ensure_ascii=False))
        return False
    result_text = run_worker_codex(task)
    result = parse_worker_result(result_text)
    if send:
        if result["message"]:
            send_message(result["message"])
        for file_path in result["files"]:
            send_file(Path(file_path))
    task["status"] = "done"
    task["completed_at"] = datetime.now().isoformat(timespec="seconds")
    task["result"] = result
    rewrite_task(queue, task)
    record_event(
        chat_name=task.get("chat", chat),
        action="worker_task",
        direction="outbound",
        message=result["message"] or result_text,
        status="done-sent" if send else "done",
        db_path=DEFAULT_DB,
        metadata=task,
    )
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return True


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_tasks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def next_pending(path: Path) -> dict[str, Any] | None:
    return next((task for task in read_tasks(path) if task.get("status") == "pending"), None)


def rewrite_task(path: Path, updated: dict[str, Any]) -> None:
    tasks = read_tasks(path)
    for index, task in enumerate(tasks):
        if task.get("id") == updated.get("id"):
            tasks[index] = updated
            break
    path.write_text("".join(json.dumps(task, ensure_ascii=False) + "\n" for task in tasks), encoding="utf-8")


def run_worker_codex(task: dict[str, Any]) -> str:
    prompt = f"""You are the slower worker agent for a WeChat LabCanvas chat.
Handle the task using available local files/tools. Save downloaded or generated artifacts under the repo's ignored private/output folders when possible.

Return either plain text or this JSON shape:
{{
  "message": "concise message to send back",
  "files": ["/absolute/path/to/file.pdf", "/absolute/path/to/preview.png"]
}}

If the task needs external tools or files that are not available, say exactly what is needed next.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}
"""
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as out:
        output_path = Path(out.name)
    command = [
        "codex",
        "exec",
        "-m",
        "gpt-5.5",
        "-c",
        'model_reasoning_effort="medium"',
        "--sandbox",
        "workspace-write",
        "-C",
        str(ROOT),
        "-o",
        str(output_path),
        prompt,
    ]
    subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)
    result = output_path.read_text(encoding="utf-8", errors="replace").strip()
    output_path.unlink(missing_ok=True)
    return result


def parse_worker_result(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            message = str(data.get("message") or "").strip()
            files = [str(Path(item).expanduser()) for item in data.get("files", []) if str(item).strip()]
            return {"message": message, "files": files, "raw": text}
    except Exception:
        pass
    message_lines = []
    files = []
    for line in text.splitlines():
        if line.strip().upper().startswith("FILE:"):
            files.append(str(Path(line.split(":", 1)[1].strip()).expanduser()))
        else:
            message_lines.append(line)
    return {"message": "\n".join(message_lines).strip(), "files": files, "raw": text}


def send_message(message: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--message",
            message,
        ],
        cwd=ROOT,
        check=False,
    )


def send_file(file_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--file",
            str(file_path.expanduser().resolve()),
        ],
        cwd=ROOT,
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
