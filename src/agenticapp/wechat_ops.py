from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = PACKAGE_ROOT / "agentic_tools" / "wechat_gui_agent"
SCRIPTS = TOOL_ROOT / "scripts"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_DIRECT_CONFIG = PRIVATE / "lazy-research-direct-chatops.local.json"
DEFAULT_CHAT_CONFIG = PRIVATE / "lazy-research-chatops.local.json"
DEFAULT_QUEUE = PRIVATE / "wechat_task_queue.jsonl"
DEFAULT_DISPLAY = ":97"
DEFAULT_VNC_PORT = 5917
DEFAULT_NOVNC_PORT = 6107


def add_wechat_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("wechat", help="Control WeChat GUI/direct chatops automation.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON where supported.")
    nested = parser.add_subparsers(dest="wechat_command", required=True)

    status = nested.add_parser("status", help="Show desktop, tmux, and private config status.")
    status.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    status.set_defaults(func=cmd_status)

    doctor = nested.add_parser("doctor", help="Check local commands and WeChat tool files.")
    doctor.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    doctor.set_defaults(func=cmd_doctor)

    init_config = nested.add_parser("init-config", help="Write ignored private config templates.")
    init_config.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    init_config.add_argument("--chat", default="wechat-chat")
    init_config.add_argument("--display", default=DEFAULT_DISPLAY)
    init_config.add_argument("--chatroom-id", default="")
    init_config.add_argument("--message-table", default="")
    init_config.add_argument("--self-wxid", default="")
    init_config.add_argument("--force", action="store_true")
    init_config.set_defaults(func=cmd_init_config)

    desktop = nested.add_parser("desktop", help="Start or inspect the isolated WeChat desktop.")
    desktop.add_argument("action", choices=["start", "status"], nargs="?", default="status")
    desktop.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    desktop.set_defaults(func=cmd_desktop)

    monitor = nested.add_parser("monitor", help="Control the fast direct chat monitor tmux session.")
    monitor.add_argument("action", choices=["start", "stop", "restart", "status", "once"], nargs="?", default="status")
    monitor.add_argument("--config", type=Path, default=DEFAULT_DIRECT_CONFIG)
    monitor.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    monitor.add_argument("--send", action="store_true", help="Allow live replies for one-shot mode.")
    monitor.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    monitor.set_defaults(func=cmd_monitor)

    hold = nested.add_parser("hold", help="Control the full tmux supervisor: desktop, fast monitor, worker, media sync.")
    hold.add_argument("action", choices=["start", "stop", "restart", "status"], nargs="?", default="start")
    hold.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    hold.set_defaults(func=cmd_hold)

    stack = nested.add_parser("stack", help="Control the WeChat supervisor plus LabCanvas web control panel.")
    stack.add_argument("action", choices=["start", "stop", "restart", "status"], nargs="?", default="start")
    stack.add_argument("--web-port", type=int, default=19474)
    stack.add_argument("--web-session", default="labcanvas-web-wechat")
    stack.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    stack.set_defaults(func=cmd_stack)

    send = nested.add_parser("send", help="Send a message or file to the currently visible chat.")
    send.add_argument("--config", type=Path, default=DEFAULT_CHAT_CONFIG)
    send.add_argument("--message")
    send.add_argument("--file", type=Path)
    send.set_defaults(func=cmd_send)

    worker = nested.add_parser("worker", help="Enqueue or process slower backend tasks.")
    worker.add_argument("action", choices=["enqueue", "once", "loop"])
    worker.add_argument("request", nargs="*", help="Task text for enqueue.")
    worker.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    worker.add_argument("--chat", default="wechat-chat")
    worker.add_argument("--send", action="store_true")
    worker.set_defaults(func=cmd_worker)

    queue = nested.add_parser("queue", help="Inspect the private worker queue.")
    queue.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    queue.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    queue.add_argument("--limit", type=int, default=10)
    queue.set_defaults(func=cmd_queue)

    approve = nested.add_parser("approve", help="Approve a worker task that is waiting for confirmation.")
    approve.add_argument("task_id", nargs="?", help="Task id. Defaults to the newest waiting_confirmation task.")
    approve.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    approve.add_argument("--note", default="")
    approve.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    approve.set_defaults(func=cmd_approve)

    reject = nested.add_parser("reject", help="Reject/cancel a worker task that is waiting for confirmation.")
    reject.add_argument("task_id", nargs="?", help="Task id. Defaults to the newest waiting_confirmation task.")
    reject.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    reject.add_argument("--note", default="")
    reject.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    reject.set_defaults(func=cmd_reject)

    media = nested.add_parser("media-sync", help="Copy recent WeChat downloads/cache files into the private workspace.")
    media.add_argument("--chat", required=True)
    media.add_argument("--source", action="append", type=Path, default=[])
    media.add_argument("--auto-source", action="store_true", help="Auto-discover local xwechat_files media folders.")
    media.add_argument("--since-minutes", type=float, default=60)
    media.add_argument("--dry-run", action="store_true")
    media.add_argument("--summary-only", action="store_true")
    media.set_defaults(func=cmd_media_sync)

    rename = nested.add_parser("rename", help="Best-effort group rename through the visible WeChat GUI.")
    rename.add_argument("--chat", default="wechat-chat")
    rename.add_argument("--name", required=True)
    rename.add_argument("--display", default=DEFAULT_DISPLAY)
    rename.add_argument("--dry-run", action="store_true")
    rename.set_defaults(func=cmd_rename)

    alias = nested.add_parser("alias", help="Set this account's in-group alias through WeChat group settings.")
    alias.add_argument("--chat", default="wechat-chat")
    alias.add_argument("--name", required=True)
    alias.add_argument("--display", default=DEFAULT_DISPLAY)
    alias.add_argument("--dry-run", action="store_true")
    alias.add_argument("--skip-ocr-guard", action="store_true")
    alias.set_defaults(func=cmd_alias)

    create_group = nested.add_parser("create-group", help="Create a WeChat group by selecting searched contacts.")
    create_group.add_argument("--display", default=DEFAULT_DISPLAY)
    create_group.add_argument("--plan", type=Path)
    create_group.add_argument("--member-query", action="append", default=[])
    create_group.add_argument("--search-box")
    create_group.add_argument("--search-result-checkbox")
    create_group.add_argument("--create", action="store_true")
    create_group.set_defaults(func=cmd_create_group)

    install = nested.add_parser("install-user-scripts", help="Install small launch wrappers into ~/scripts.")
    install.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    install.set_defaults(func=cmd_install_user_scripts)


def status_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "tool_root": str(TOOL_ROOT),
        "private_dir_exists": PRIVATE.exists(),
        "chat_config_exists": DEFAULT_CHAT_CONFIG.exists(),
        "direct_config_exists": DEFAULT_DIRECT_CONFIG.exists(),
        "desktop": desktop_status(),
        "sessions": {
            "supervisor": tmux_status("labcanvas-wechat"),
            "direct_monitor": tmux_status("labcanvas-wechat-direct-chatops"),
            "gui_monitor": tmux_status("labcanvas-wechat-chatops"),
        },
        "queue": queue_summary(DEFAULT_QUEUE),
        "mirror": mirror_summary(PRIVATE / "wechat_mirror.sqlite"),
        "media_sources": [str(path) for path in discover_media_sources()],
        "novnc_url": f"http://127.0.0.1:{DEFAULT_NOVNC_PORT}/vnc_lite.html?host=127.0.0.1&port={DEFAULT_NOVNC_PORT}&autoconnect=1&resize=remote",
    }


def run_wechat_action(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if action == "status":
        return status_payload()
    if action == "start-hold":
        proc = run_command([str(SCRIPTS / "wechat_supervisor_tmux.sh"), "start"], capture=True)
        result = status_payload()
        result.update({"action": action, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "returncode": proc.returncode})
        return result
    if action == "start-stack":
        proc = run_command([str(SCRIPTS / "wechat_stack_tmux.sh"), "start"], capture=True)
        result = status_payload()
        result.update({"action": action, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "returncode": proc.returncode})
        return result
    if action == "stop-hold":
        proc = run_command([str(SCRIPTS / "wechat_supervisor_tmux.sh"), "stop"], capture=True)
        result = status_payload()
        result.update({"action": action, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "returncode": proc.returncode})
        return result
    if action == "send-message":
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ValueError("message is required")
        proc = run_command(
            [sys.executable, str(SCRIPTS / "wechat_chatops_bridge.py"), "--config", str(DEFAULT_CHAT_CONFIG), "--message", message],
            capture=True,
        )
        return {"ok": proc.returncode == 0, "action": action, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
    if action == "worker-once":
        proc = run_command([sys.executable, str(SCRIPTS / "wechat_task_worker.py"), "--queue", str(DEFAULT_QUEUE), "--once", "--send"], capture=True)
        result = status_payload()
        result.update({"action": action, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip(), "returncode": proc.returncode})
        return result
    if action in {"approve-next", "reject-next"}:
        decision = "approve" if action == "approve-next" else "reject"
        note = str(payload.get("note") or "").strip()
        task = update_waiting_task(DEFAULT_QUEUE, None, decision=decision, note=note)
        result = status_payload()
        result.update({"action": action, "task": task})
        return result
    return {"ok": False, "error": f"Unsupported WeChat action: {action}"}


def cmd_status(args: argparse.Namespace) -> int:
    payload = status_payload()
    print_payload(payload, args.json, f"wechat: {payload['desktop']['status']} {payload['novnc_url']}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    commands = ["tmux", "Xvfb", "x11vnc", "websockify", "xdotool", "xclip", "import", "tesseract", "codex"]
    checks = {name: shutil.which(name) or "" for name in commands}
    scripts = {
        path.name: path.exists()
        for path in (
            SCRIPTS / "wechat_virtual_desktop.sh",
            SCRIPTS / "wechat_supervisor_tmux.sh",
            SCRIPTS / "wechat_direct_chatops.py",
            SCRIPTS / "wechat_task_worker.py",
            SCRIPTS / "wechat_chatops_bridge.py",
            SCRIPTS / "wechat_media_sync.py",
        )
    }
    missing = [name for name, found in checks.items() if not found]
    payload = {"ok": not missing and all(scripts.values()), "commands": checks, "scripts": scripts, "missing": missing}
    print_payload(payload, args.json, "wechat doctor: " + ("ok" if payload["ok"] else "missing " + ", ".join(missing)))
    return 0 if payload["ok"] else 1


def cmd_init_config(args: argparse.Namespace) -> int:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    chat_config = {
        "chat_name": args.chat,
        "display": args.display,
        "poll_seconds": 8,
        "reply_enabled": True,
        "respond_to_all": False,
        "trigger_prefixes": ["@lachchen", "＠lachchen", "@codex", "codex:"],
        "max_reply_chars": 1200,
        "state_path": str(PRIVATE / f"{safe_slug(args.chat)}-chatops.state.json"),
        "db_path": str(PRIVATE / "wechat_mirror.sqlite"),
        "output_dir": str(PACKAGE_ROOT / "output" / "wechat_gui_agent" / datetime.now().strftime("%F")),
        "codex": {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "read-only", "workdir": str(PACKAGE_ROOT)},
    }
    direct_config = {
        "chat_name": args.chat,
        "chatroom_id": args.chatroom_id,
        "message_table": args.message_table,
        "self_wxid": args.self_wxid,
        "trigger_prefixes": ["@lachchen", "＠lachchen", "@codex", "codex:"],
        "mirror_db": str(PRIVATE / "wechat_mirror.sqlite"),
        "max_reply_chars": 1200,
        "respond_to_all": False,
        "respond_to_self": False,
        "trigger_local_types": [1],
        "chat_purpose": "research",
        "analysis_mode": "",
        "silent_danger_enabled": True,
        "immediate_ack_enabled": True,
        "immediate_ack_text": "收到，我先处理，完成后把结果发回来。",
        "slow_task_keywords": ["download", "pdf", "paper", "论文", "下載", "下载", "render", "cad", "pcb", "figure", "file", "image"],
        "codex": {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "read-only", "timeout_seconds": 180},
    }
    written = []
    for path, data in ((DEFAULT_CHAT_CONFIG, chat_config), (DEFAULT_DIRECT_CONFIG, direct_config)):
        if path.exists() and not args.force:
            continue
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
        written.append(str(path))
    print_payload({"ok": True, "written": written}, args.json, "wechat init-config: " + (", ".join(written) or "kept existing files"))
    return 0


def cmd_desktop(args: argparse.Namespace) -> int:
    if args.action == "start":
        proc = run_command([str(SCRIPTS / "wechat_virtual_desktop.sh")], capture=True)
        if args.json:
            print(json.dumps({"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr, "desktop": desktop_status()}, indent=2))
        else:
            print(proc.stdout, end="")
            if proc.stderr:
                print(proc.stderr, file=sys.stderr, end="")
        return proc.returncode
    payload = desktop_status()
    print_payload(payload, args.json, f"wechat desktop: {payload['status']} {payload.get('novnc_url', '')}")
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    if args.action in {"start", "restart"}:
        if args.action == "restart":
            kill_tmux("labcanvas-wechat-direct-chatops")
        proc = run_command([str(SCRIPTS / "wechat_direct_chatops_tmux.sh"), str(args.config)], capture=True)
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, end="")
        return proc.returncode
    if args.action == "stop":
        stopped = kill_tmux("labcanvas-wechat-direct-chatops")
        print("stopped" if stopped else "not running")
        return 0
    if args.action == "once":
        command = [sys.executable, str(SCRIPTS / "wechat_direct_chatops.py"), "--config", str(args.config), "--worker-queue", str(args.queue)]
        if args.send:
            command.append("--send")
        return run_command(command, capture=False).returncode
    payload = tmux_status("labcanvas-wechat-direct-chatops")
    print_payload(payload, args.json, f"wechat monitor: {payload['status']}")
    return 0 if payload["running"] else 1


def cmd_hold(args: argparse.Namespace) -> int:
    proc = run_command([str(SCRIPTS / "wechat_supervisor_tmux.sh"), args.action], capture=True)
    if args.json:
        print(json.dumps({"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr, "status": status_payload()}, indent=2))
    else:
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, end="")
    return proc.returncode


def cmd_stack(args: argparse.Namespace) -> int:
    env = os.environ.copy()
    env["WECHAT_WEB_PORT"] = str(args.web_port)
    env["WECHAT_WEB_SESSION"] = args.web_session
    proc = run_command([str(SCRIPTS / "wechat_stack_tmux.sh"), args.action], capture=True, env=env)
    web_status = labcanvas_web_status(args.web_session)
    payload = {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "wechat": status_payload(),
        "webapp": web_status,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, end="")
        if web_status.get("url"):
            print(f"webapp: {web_status['url']}")
    return proc.returncode


def cmd_send(args: argparse.Namespace) -> int:
    if not args.message and not args.file:
        raise SystemExit("Use --message or --file")
    command = [sys.executable, str(SCRIPTS / "wechat_chatops_bridge.py"), "--config", str(args.config)]
    if args.message:
        command += ["--message", args.message]
    if args.file:
        command += ["--file", str(args.file)]
    return run_command(command, capture=False).returncode


def cmd_worker(args: argparse.Namespace) -> int:
    command = [sys.executable, str(SCRIPTS / "wechat_task_worker.py"), "--queue", str(args.queue), "--chat", args.chat]
    if args.action == "enqueue":
        command += ["--enqueue", " ".join(args.request).strip()]
    elif args.action == "once":
        command.append("--once")
    elif args.action == "loop":
        command.append("--loop")
    if args.send:
        command.append("--send")
    return run_command(command, capture=False).returncode


def cmd_queue(args: argparse.Namespace) -> int:
    payload = queue_summary(args.queue, limit=args.limit)
    print_payload(payload, args.json, f"queue: pending={payload['counts'].get('pending', 0)} total={payload['total']}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    task = update_waiting_task(args.queue, args.task_id, decision="approve", note=args.note)
    print_payload({"ok": True, "task": task}, args.json, f"approved task: {task['id']}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    task = update_waiting_task(args.queue, args.task_id, decision="reject", note=args.note)
    print_payload({"ok": True, "task": task}, args.json, f"rejected task: {task['id']}")
    return 0


def cmd_media_sync(args: argparse.Namespace) -> int:
    command = [sys.executable, str(SCRIPTS / "wechat_media_sync.py"), "--chat", args.chat, "--since-minutes", str(args.since_minutes)]
    for source in args.source:
        command += ["--source", str(source)]
    if args.auto_source:
        command.append("--auto-source")
    if args.dry_run:
        command.append("--dry-run")
    if args.summary_only:
        command.append("--summary-only")
    return run_command(command, capture=False).returncode


def cmd_rename(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(SCRIPTS / "wechat_group_admin.py"),
        "--display",
        args.display,
        "--chat",
        args.chat,
        "--rename",
        args.name,
    ]
    if args.dry_run:
        command.append("--dry-run")
    return run_command(command, capture=False).returncode


def cmd_alias(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(SCRIPTS / "wechat_group_admin.py"),
        "--display",
        args.display,
        "--chat",
        args.chat,
        "--my-alias",
        args.name,
    ]
    if args.dry_run:
        command.append("--dry-run")
    if args.skip_ocr_guard:
        command.append("--skip-ocr-guard")
    return run_command(command, capture=False).returncode


def cmd_create_group(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(SCRIPTS / "wechat_group_create.py"),
        "--display",
        args.display,
    ]
    if args.plan:
        command += ["--plan", str(args.plan)]
    for query in args.member_query:
        command += ["--member-query", query]
    if args.search_box:
        command += ["--search-box", args.search_box]
    if args.search_result_checkbox:
        command += ["--search-result-checkbox", args.search_result_checkbox]
    if args.create:
        command.append("--create")
    return run_command(command, capture=False).returncode


def cmd_install_user_scripts(args: argparse.Namespace) -> int:
    scripts_dir = Path.home() / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    wrapper = scripts_dir / "labcanvas-wechat-hold.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "cd " + shlex.quote(str(PACKAGE_ROOT)) + "\n"
        "if command -v labcanvas >/dev/null 2>&1; then\n"
        "  exec labcanvas wechat hold \"${1:-start}\"\n"
        "fi\n"
        "export PYTHONPATH=" + shlex.quote(str(PACKAGE_ROOT / "src")) + ":${PYTHONPATH:-}\n"
        "exec python3 -m agenticapp wechat hold \"${1:-start}\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    create_wrapper = scripts_dir / "create-labcanvas-wechat-tmux.sh"
    create_wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "cd " + shlex.quote(str(PACKAGE_ROOT)) + "\n"
        "export WECHAT_SUPERVISOR_SESSION=${WECHAT_SUPERVISOR_SESSION:-labcanvas-wechat}\n"
        "export WECHAT_MEDIA_SYNC_INTERVAL=${WECHAT_MEDIA_SYNC_INTERVAL:-30}\n"
        "export PYTHONPATH=" + shlex.quote(str(PACKAGE_ROOT / "src")) + ":${PYTHONPATH:-}\n"
        "exec python3 -m agenticapp wechat hold start\n",
        encoding="utf-8",
    )
    create_wrapper.chmod(0o755)
    stack_wrapper = scripts_dir / "create-labcanvas-wechat-stack.sh"
    stack_wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "cd " + shlex.quote(str(PACKAGE_ROOT)) + "\n"
        "export WECHAT_SUPERVISOR_SESSION=${WECHAT_SUPERVISOR_SESSION:-labcanvas-wechat}\n"
        "export WECHAT_WEB_SESSION=${WECHAT_WEB_SESSION:-labcanvas-web-wechat}\n"
        "export WECHAT_WEB_PORT=${WECHAT_WEB_PORT:-19474}\n"
        "export PYTHONPATH=" + shlex.quote(str(PACKAGE_ROOT / "src")) + ":${PYTHONPATH:-}\n"
        "exec python3 -m agenticapp wechat stack \"${1:-start}\"\n",
        encoding="utf-8",
    )
    stack_wrapper.chmod(0o755)
    print_payload(
        {"ok": True, "installed": [str(wrapper), str(create_wrapper), str(stack_wrapper)]},
        args.json,
        f"installed {wrapper}, {create_wrapper}, and {stack_wrapper}",
    )
    return 0


def update_waiting_task(path: Path, task_id: str | None, *, decision: str, note: str = "") -> dict[str, Any]:
    tasks = read_jsonl(path)
    if not tasks:
        raise ValueError(f"No task queue found at {path}")
    target_index = None
    if task_id:
        for index, task in enumerate(tasks):
            if str(task.get("id")) == task_id:
                target_index = index
                break
    else:
        for index in range(len(tasks) - 1, -1, -1):
            if tasks[index].get("status") == "waiting_confirmation":
                target_index = index
                break
    if target_index is None:
        raise ValueError("No matching waiting_confirmation task found")
    task = tasks[target_index]
    if decision == "approve":
        task["status"] = "pending"
        task["approved_at"] = datetime.now().isoformat(timespec="seconds")
        task["approval_note"] = note
        if note:
            task["request"] = f"{task.get('request', '')}\n\nUser approval note: {note}".strip()
    elif decision == "reject":
        task["status"] = "canceled"
        task["canceled_at"] = datetime.now().isoformat(timespec="seconds")
        task["cancel_note"] = note
    else:
        raise ValueError(f"Unsupported decision: {decision}")
    tasks[target_index] = task
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in tasks), encoding="utf-8")
    return task


def queue_summary(path: Path, *, limit: int = 8) -> dict[str, Any]:
    tasks = read_jsonl(path)
    counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    recent = []
    for task in tasks[-limit:]:
        recent.append(
            {
                "id": task.get("id", ""),
                "chat": task.get("chat", ""),
                "status": task.get("status", ""),
                "created_at": task.get("created_at", ""),
                "completed_at": task.get("completed_at", ""),
                "request": str(task.get("request") or "")[:240],
            }
        )
    return {"ok": True, "path": str(path), "exists": path.exists(), "total": len(tasks), "counts": counts, "recent": recent}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def mirror_summary(path: Path, *, limit: int = 8) -> dict[str, Any]:
    if not path.exists():
        return {"ok": True, "path": str(path), "exists": False, "message_count": 0, "event_count": 0, "recent": []}
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            message_count = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
            event_count = conn.execute("SELECT count(*) FROM events").fetchone()[0]
            recent = [
                {
                    "id": row["id"],
                    "observed_at": row["observed_at"],
                    "chat": row["chat"],
                    "direction": row["direction"],
                    "status": row["status"],
                    "body": row["body"][:240],
                }
                for row in conn.execute(
                    """
                    SELECT messages.id, messages.observed_at, chats.name AS chat, messages.direction,
                           messages.status, replace(messages.body, char(10), ' ') AS body
                    FROM messages
                    JOIN chats ON chats.id = messages.chat_id
                    ORDER BY messages.id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            ]
    except sqlite3.Error as exc:
        return {"ok": False, "path": str(path), "exists": True, "error": str(exc), "recent": []}
    return {
        "ok": True,
        "path": str(path),
        "exists": True,
        "message_count": int(message_count),
        "event_count": int(event_count),
        "recent": recent,
    }


def discover_media_sources() -> list[Path]:
    base = Path.home() / "Documents" / "xwechat_files"
    if not base.exists():
        return []
    sources = []
    seen = set()
    for profile in base.iterdir():
        if not profile.is_dir():
            continue
        for relative in ("msg/file", "msg/video", "cache", "temp/ImageTemp"):
            path = profile / relative
            if not path.is_dir():
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            sources.append(resolved)
    return sorted(sources)


def desktop_status() -> dict[str, Any]:
    display_ok = run_command(["xdpyinfo"], capture=True, env=display_env(DEFAULT_DISPLAY)).returncode == 0
    wechat_window = run_command(["xdotool", "search", "--onlyvisible", "--class", "wechat"], capture=True, env=display_env(DEFAULT_DISPLAY))
    ports = {str(port): port_listening(port) for port in (DEFAULT_VNC_PORT, DEFAULT_NOVNC_PORT)}
    status = "ready" if display_ok and wechat_window.returncode == 0 and ports[str(DEFAULT_NOVNC_PORT)] else "partial" if display_ok else "offline"
    return {
        "status": status,
        "display": DEFAULT_DISPLAY,
        "display_ok": display_ok,
        "wechat_window": wechat_window.stdout.split(),
        "ports": ports,
        "novnc_url": f"http://127.0.0.1:{DEFAULT_NOVNC_PORT}/vnc_lite.html?host=127.0.0.1&port={DEFAULT_NOVNC_PORT}&autoconnect=1&resize=remote",
    }


def tmux_status(session: str) -> dict[str, Any]:
    if shutil.which("tmux") is None:
        return {"session": session, "running": False, "status": "missing-tmux"}
    check = run_command(["tmux", "has-session", "-t", session], capture=True)
    if check.returncode != 0:
        return {"session": session, "running": False, "status": "not-running"}
    panes = run_command(["tmux", "list-panes", "-t", session, "-F", "#{pane_index}: #{pane_current_command} #{pane_pid}"], capture=True)
    return {"session": session, "running": True, "status": "running", "panes": panes.stdout.splitlines()}


def labcanvas_web_status(session: str) -> dict[str, Any]:
    proc = run_command([sys.executable, "-m", "agenticapp", "webapp", "status", "--session", session, "--json"], capture=True)
    if proc.returncode != 0 and not proc.stdout.strip():
        return {"ok": False, "status": "not-running", "session": session, "url": "", "stderr": proc.stderr.strip()}
    try:
        payload = json.loads(proc.stdout)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    return {"ok": proc.returncode == 0, "status": "unknown", "session": session, "url": "", "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def kill_tmux(session: str) -> bool:
    if shutil.which("tmux") is None:
        return False
    if run_command(["tmux", "has-session", "-t", session], capture=True).returncode != 0:
        return False
    run_command(["tmux", "kill-session", "-t", session], capture=True)
    return True


def port_listening(port: int) -> bool:
    proc = run_command(["ss", "-ltn"], capture=True)
    if proc.returncode != 0:
        return False
    return any(line.split()[3].endswith(f":{port}") for line in proc.stdout.splitlines() if len(line.split()) >= 4)


def display_env(display: str) -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = display
    env["XAUTHORITY"] = env.get("XAUTHORITY", "")
    return env


def run_command(command: list[str], *, capture: bool, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {"cwd": PACKAGE_ROOT, "env": env or os.environ.copy(), "text": True, "check": False}
    if capture:
        kwargs.update({"capture_output": True})
    try:
        return subprocess.run(command, **kwargs)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def print_payload(payload: dict[str, Any], as_json: bool, summary: str) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(summary)


def safe_slug(value: str) -> str:
    keep = [char.lower() if char.isalnum() else "-" for char in value]
    return "-".join("".join(keep).strip("-").split("-")) or "wechat"
