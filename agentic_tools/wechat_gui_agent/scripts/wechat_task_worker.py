#!/usr/bin/env python3
"""Worker-side helper for slower WeChat chatops tasks."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from wechat_codex_sessions import run_codex_session
from wechat_mirror import DEFAULT_DB, record_event


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"
DEFAULT_SEND_TARGETS = PRIVATE / "wechat_send_targets.local.json"
EFFORT_ORDER = ["low", "medium", "high"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--chat", default="wechat-chat")
    parser.add_argument("--enqueue", help="Add a task to the private queue and exit.")
    parser.add_argument("--once", action="store_true", help="Process one pending task.")
    parser.add_argument("--loop", action="store_true", help="Continuously process pending tasks.")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--send", action="store_true", help="Send worker result back to WeChat.")
    parser.add_argument("--send-targets", type=Path, default=DEFAULT_SEND_TARGETS, help="Ignored JSON mapping chat names to GUI target specs.")
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
            processed = process_one(args.queue, args.chat, send=args.send, send_targets=args.send_targets, log_idle=not args.loop)
            if not args.loop:
                return 0
            if not processed:
                import time

                time.sleep(args.poll_seconds)
        return 0
    raise SystemExit("Use --enqueue, --once, or --loop")


def process_one(queue: Path, chat: str, *, send: bool, send_targets: Path = DEFAULT_SEND_TARGETS, log_idle: bool = True) -> bool:
    task = next_pending(queue)
    if not task:
        if log_idle:
            print(json.dumps({"status": "no-pending-task"}, ensure_ascii=False))
        return False
    result_text = run_worker_codex(task)
    result = parse_worker_result(result_text)
    target_chat = str(task.get("chat") or chat)
    send_errors = []
    if send:
        try:
            if result["message"]:
                send_message(result["message"], target_chat, send_targets)
            if result["confirmation"]:
                send_message(result["confirmation"], target_chat, send_targets)
            for file_path in result["files"]:
                send_file(Path(file_path), target_chat, send_targets)
        except Exception as exc:
            send_errors.append(str(exc))
    if send_errors:
        task["status"] = "send_failed"
        task["send_errors"] = send_errors
    else:
        task["status"] = "waiting_confirmation" if result["confirmation"] else "done"
    task["completed_at"] = datetime.now().isoformat(timespec="seconds")
    task["result"] = result
    rewrite_task(queue, task)
    if send_errors:
        event_status = "send-failed"
    elif result["confirmation"]:
        event_status = "waiting-confirmation-sent" if send else "waiting-confirmation"
    else:
        event_status = "done-sent" if send else "done"
    record_event(
        chat_name=task.get("chat", chat),
        action="worker_task",
        direction="outbound",
        message=result["confirmation"] or result["message"] or result_text,
        status=event_status,
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
    policy = choose_worker_policy(task)
    task["worker_policy"] = policy
    result = run_worker_codex_once(task, policy)
    next_policy = escalated_policy(policy, result)
    if next_policy:
        task["worker_policy"] = {**next_policy, "escalated_from": policy["reasoning_effort"]}
        result = run_worker_codex_once(task, next_policy)
    return result


def run_worker_codex_once(task: dict[str, Any], policy: dict[str, Any]) -> str:
    prompt = f"""You are the slower worker agent for a WeChat LabCanvas chat.
Handle the task using available local files/tools. Save downloaded or generated artifacts under the repo's ignored private/output folders when possible.

Return either plain text or this JSON shape:
{{
  "message": "concise message to send back",
  "files": ["/absolute/path/to/file.pdf", "/absolute/path/to/preview.png"],
  "confirmation": "optional question to ask before continuing"
}}

Use confirmation when an important choice, purchase, external send, deletion, privacy-sensitive action, or irreversible action needs approval.
If a download is blocked by login, CAPTCHA, bot check, consent page, or a site that needs human action, do not try to bypass it.
Open a human-assist browser in the isolated virtual desktop with:
PYTHONPATH=src python -m agenticapp wechat browser-assist --url "<url>" --json
Then return a confirmation telling the user to complete the manual step in noVNC and approve continuation.
If other external tools or files are not available, say exactly what is needed next.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}
"""
    result = run_codex_session(
        prompt,
        chat_name=str(task.get("chat") or "wechat-chat"),
        role="worker",
        model=str(policy["model"]),
        reasoning_effort=str(policy["reasoning_effort"]),
        sandbox=str(policy["sandbox"]),
        timeout_seconds=int(policy["timeout_seconds"]),
        workdir=ROOT,
        reuse=bool(policy.get("reuse_session", True)),
    )
    if not result["ok"]:
        return f"Worker failed: {str(result.get('stderr_tail') or result.get('message') or '').strip()[:1000]}"
    task["codex_session"] = {
        "role": "worker",
        "thread_id_short": str(result.get("thread_id") or "")[:8],
        "resumed": bool(result.get("resumed")),
        "fallback_started": bool(result.get("fallback_started")),
    }
    return str(result.get("message") or "").strip()


def choose_worker_policy(task: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(task, ensure_ascii=False).lower()
    high_keywords = [
        "deep research",
        "pcb",
        "kicad",
        "cad",
        "openscad",
        "blender",
        "render",
        "install",
        "github",
        "mcp",
        "commit",
        "push",
        "publish",
        "order",
        "jlc",
        "wenext",
        "labview",
        "full task",
        "完整",
        "下单",
        "电路板",
        "渲染",
        "安装",
    ]
    medium_keywords = [
        "paper",
        "pdf",
        "search",
        "summarize",
        "summary",
        "dataset",
        "figure",
        "diagram",
        "research",
        "nature",
        "hyperspectral",
        "论文",
        "总结",
        "搜索",
        "文献",
        "高光谱",
        "高光譜",
    ]
    if any(keyword in text for keyword in high_keywords):
        effort, timeout = "high", 600
    elif any(keyword in text for keyword in medium_keywords) or len(text) > 1200:
        effort, timeout = "medium", 300
    else:
        effort, timeout = "low", 120
    return {
        "model": "gpt-5.5",
        "reasoning_effort": effort,
        "sandbox": worker_sandbox(),
        "timeout_seconds": timeout,
    }


def worker_sandbox() -> str:
    raw = os.environ.get("WECHAT_WORKER_CODEX_SANDBOX", "danger-full-access").strip()
    aliases = {
        "full": "danger-full-access",
        "full-access": "danger-full-access",
        "danger": "danger-full-access",
        "workspace": "workspace-write",
    }
    return aliases.get(raw, raw or "danger-full-access")


def escalated_policy(policy: dict[str, Any], result: str) -> dict[str, Any] | None:
    text = str(result or "").lower()
    failure_markers = [
        "worker failed",
        "timed out",
        "cannot complete",
        "can't complete",
        "unable to complete",
        "i cannot",
        "i can't",
        "无法完成",
        "不能完成",
        "没有完成",
    ]
    if len(text.strip()) >= 80 and not any(marker in text for marker in failure_markers):
        return None
    effort = str(policy.get("reasoning_effort") or "medium")
    try:
        index = EFFORT_ORDER.index(effort)
    except ValueError:
        index = 1
    if index >= len(EFFORT_ORDER) - 1:
        return None
    next_effort = EFFORT_ORDER[index + 1]
    timeout = 300 if next_effort == "medium" else 600
    return {**policy, "reasoning_effort": next_effort, "timeout_seconds": timeout}


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
            confirmation = str(data.get("confirmation") or data.get("confirm") or "").strip()
            files = [str(Path(item).expanduser()) for item in data.get("files", []) if str(item).strip()]
            return {"message": message, "confirmation": confirmation, "files": files, "raw": text}
    except Exception:
        pass
    message_lines = []
    files = []
    for line in text.splitlines():
        if line.strip().upper().startswith("FILE:"):
            files.append(str(Path(line.split(":", 1)[1].strip()).expanduser()))
        else:
            message_lines.append(line)
    return {"message": "\n".join(message_lines).strip(), "confirmation": "", "files": files, "raw": text}


def send_message(message: str, chat: str, send_targets: Path) -> None:
    target = load_send_target(chat, send_targets)
    if target:
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": message, "targets": [target]}, handle, ensure_ascii=False)
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
                    "--targets-file",
                    str(target_file),
                    "--send",
                    "--mirror-db",
                    str(DEFAULT_DB),
                ],
                cwd=ROOT,
                check=True,
                timeout=60,
            )
        finally:
            target_file.unlink(missing_ok=True)
        return
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--chat",
            chat,
            "--message",
            message,
        ],
        cwd=ROOT,
        check=False,
    )


def send_file(file_path: Path, chat: str, send_targets: Path) -> None:
    target = load_send_target(chat, send_targets)
    if target:
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8", delete=False) as handle:
            target_file = Path(handle.name)
            json.dump({"message": "", "targets": [target]}, handle, ensure_ascii=False)
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_gui_send.py"),
                    "--targets-file",
                    str(target_file),
                ],
                cwd=ROOT,
                check=True,
                timeout=60,
            )
        finally:
            target_file.unlink(missing_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_chatops_bridge.py"),
            "--config",
            str(PRIVATE / "lazy-research-chatops.local.json"),
            "--chat",
            chat,
            "--file",
            str(file_path.expanduser().resolve()),
        ],
        cwd=ROOT,
        check=False,
    )


def load_send_target(chat: str, path: Path) -> dict[str, Any] | None:
    direct_target = load_direct_config_send_target(chat)
    registry_target = None
    if not path.exists():
        return direct_target
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return direct_target
    raw = data.get(chat) if isinstance(data, dict) else None
    if isinstance(raw, dict):
        registry_target = raw
    if direct_target and registry_target:
        merged = {**registry_target, **direct_target}
        if not merged.get("fallback_clicks") and registry_target.get("fallback_clicks"):
            merged["fallback_clicks"] = registry_target["fallback_clicks"]
        return merged
    return direct_target or registry_target


def load_direct_config_send_target(chat: str) -> dict[str, Any] | None:
    for config_path in PRIVATE.glob("*direct-chatops.local.json"):
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("chat_name") or "") != chat:
            continue
        target = data.get("send_target")
        if isinstance(target, dict):
            return target
    return None


if __name__ == "__main__":
    raise SystemExit(main())
