from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
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
CODEX_SESSION_KEY_RE = re.compile(r"^v2:[0-9a-z_.-]+-[0-9a-f]{12}:[0-9a-z_.-]+$")


def add_wechat_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("wechat", help="Control WeChat GUI/direct chatops automation.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON where supported.")
    nested = parser.add_subparsers(dest="wechat_command", required=True)

    status = nested.add_parser("status", help="Show desktop, tmux, and private config status.")
    status.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    status.set_defaults(func=cmd_status)

    health = nested.add_parser("health", help="Check direct monitor state, self-message guards, and DB catch-up.")
    health.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    health.set_defaults(func=cmd_health)

    doctor = nested.add_parser("doctor", help="Check local commands and WeChat tool files.")
    doctor.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    doctor.set_defaults(func=cmd_doctor)

    control = nested.add_parser("control-map", help="Show safe WeChat control surfaces, guardrails, and reference projects.")
    control.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    control.set_defaults(func=cmd_control_map)

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

    browser = nested.add_parser("browser-assist", help="Open a browser in the isolated virtual desktop for manual login/CAPTCHA/download help.")
    browser.add_argument("--url", default="about:blank")
    browser.add_argument("--display", default=DEFAULT_DISPLAY)
    browser.add_argument("--browser")
    browser.add_argument("--dry-run", action="store_true")
    browser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    browser.set_defaults(func=cmd_browser_assist)

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

    memory = nested.add_parser("memory", help="Initialize or summarize the private organized WeChat memory database.")
    memory.add_argument("action", choices=["init", "summary"], nargs="?", default="summary")
    memory.add_argument("--db", type=Path, default=PRIVATE / "wechat_memory.sqlite")
    memory.add_argument("--chat", default="")
    memory.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    memory.set_defaults(func=cmd_memory)

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
    media.add_argument("--since-epoch", type=float)
    media.add_argument("--until-epoch", type=float)
    media.add_argument("--match-token", action="append", default=[])
    media.add_argument("--dry-run", action="store_true")
    media.add_argument("--summary-only", action="store_true")
    media.add_argument("--record-empty", action="store_true")
    media.set_defaults(func=cmd_media_sync)

    autopub = nested.add_parser("autopublish-video", help="Copy the latest mirrored WeChat video to Nutstore AutoPublish.")
    autopub.add_argument("--chat", action="append", default=[], help="Chat/group name to search. Repeatable. Defaults to all mirrored chats.")
    autopub.add_argument("--source", type=Path, help="Explicit local video path. Bypasses the mirror query.")
    autopub.add_argument("--db", type=Path, default=PRIVATE / "wechat_mirror.sqlite")
    autopub.add_argument(
        "--dest",
        type=Path,
        default=Path(os.environ.get("LABCANVAS_AUTOPUBLISH_DIR", "/home/lachlan/Nutstore Files/AutoPublish/AutoPublish")),
    )
    autopub.add_argument("--title", default="", help="Output basename. _COMPLETED is appended if missing.")
    autopub.add_argument("--match-token", action="append", default=[])
    autopub.add_argument("--message-local-id", action="append", type=int, default=[], help="Use an exact WeChat video message local_id. Repeatable.")
    autopub.add_argument("--since-minutes", type=float, default=180)
    autopub.add_argument("--limit", type=int, default=10)
    autopub.add_argument("--sync", action="store_true", help="Run media-sync before selecting the video.")
    autopub.add_argument("--fetch-gui", action="store_true", help="Open WeChat and click the latest video to force the client to cache it.")
    autopub.add_argument("--fetch-timeout", type=float, default=90)
    autopub.add_argument("--display", default=DEFAULT_DISPLAY)
    autopub.add_argument("--video-click", default="", help="Relative x,y click inside the WeChat window for the latest visible video.")
    autopub.add_argument("--no-auto-source", action="store_true")
    autopub.add_argument("--replace", action="store_true")
    autopub.add_argument("--list", action="store_true")
    autopub.add_argument("--dry-run", action="store_true")
    autopub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    autopub.set_defaults(func=cmd_autopublish_video)

    backend = nested.add_parser("backend", help="Control optional external WeChat decrypt/MCP receive backends.")
    backend.add_argument(
        "action",
        choices=["install", "status", "probe", "init-config", "find-keys", "decrypt", "monitor", "monitor-web", "api-history", "mcp-server", "mcp-config"],
    )
    backend.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    backend.add_argument("--external", type=Path, default=PRIVATE / "external" / "wechat-decrypt")
    backend.add_argument("--db-dir", type=Path)
    backend.add_argument("--chat", default="wechat-chat")
    backend.add_argument("--repo", default="https://github.com/ylytdeng/wechat-decrypt.git")
    backend.add_argument("--update", action="store_true")
    backend.add_argument("--skip-deps", action="store_true")
    backend.add_argument("--incremental", action="store_true")
    backend.add_argument("--dry-run", action="store_true")
    backend.add_argument("--host", default="127.0.0.1")
    backend.add_argument("--port", type=int, default=5678)
    backend.add_argument("--limit", type=int, default=20)
    backend.add_argument("--filter-chat", default="")
    backend.add_argument("--since", type=int, default=0)
    backend.add_argument("--raw", action="store_true")
    backend.set_defaults(func=cmd_backend)

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
        "external_backend": external_backend_summary(),
        "codex_sessions": codex_session_summary(),
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


def cmd_health(args: argparse.Namespace) -> int:
    payload = direct_monitor_health()
    summary = f"wechat health: {payload['caught_up_groups']}/{payload['group_count']} caught up"
    if not payload["ok"]:
        summary += " (attention needed)"
    print_payload(payload, args.json, summary)
    return 0 if payload["ok"] else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    commands = ["tmux", "Xvfb", "x11vnc", "websockify", "xdotool", "xclip", "import", "tesseract", "codex"]
    checks = {name: shutil.which(name) or "" for name in commands}
    scripts = {
        path.name: path.exists()
        for path in (
            SCRIPTS / "wechat_virtual_desktop.sh",
            SCRIPTS / "wechat_supervisor_tmux.sh",
            SCRIPTS / "wechat_direct_chatops.py",
            SCRIPTS / "wechat_direct_backend.py",
            SCRIPTS / "wechat_task_worker.py",
            SCRIPTS / "wechat_chatops_bridge.py",
            SCRIPTS / "wechat_browser_assist.py",
            SCRIPTS / "wechat_media_sync.py",
        )
    }
    missing = [name for name, found in checks.items() if not found]
    payload = {"ok": not missing and all(scripts.values()), "commands": checks, "scripts": scripts, "missing": missing}
    print_payload(payload, args.json, "wechat doctor: " + ("ok" if payload["ok"] else "missing " + ", ".join(missing)))
    return 0 if payload["ok"] else 1


def cmd_control_map(args: argparse.Namespace) -> int:
    payload = control_map_payload()
    print_payload(payload, args.json, f"wechat control-map: {payload['score']['label']} {payload['score']['ready_layers']}/{payload['score']['total_layers']} layers ready")
    return 0


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
        "codex": {"model": "gpt-5.5", "reasoning_effort": "low", "sandbox": "read-only", "workdir": str(PACKAGE_ROOT), "timeout_seconds": 60},
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
        "ignore_self_messages": True,
        "trigger_local_types": [1],
        "chat_purpose": "research",
        "analysis_mode": "",
        "silent_danger_enabled": True,
        "auto_media_sync_on_task": True,
        "media_sync_since_minutes": 180,
        "media_sync_context_window_seconds": 300,
        "media_sync_timeout_seconds": 20,
        "immediate_ack_enabled": True,
        "immediate_ack_text": "收到，我先处理，完成后把结果发回来。",
        "slow_task_keywords": ["download", "pdf", "paper", "论文", "下載", "下载", "render", "cad", "pcb", "aginti", "imagegen", "image generation", "kicad", "gerber", "step", "stl", "3d", "labcanvas", "overview", "figure", "figure grid", "icons", "file", "image"],
        "poll_seconds": 0.8,
        "catchup_poll_seconds": 0.1,
        "codex": {"model": "gpt-5.5", "reasoning_effort": "low", "sandbox": "read-only", "timeout_seconds": 30},
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


def cmd_browser_assist(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(SCRIPTS / "wechat_browser_assist.py"),
        "--url",
        args.url,
        "--display",
        args.display,
    ]
    if args.browser:
        command += ["--browser", args.browser]
    if args.dry_run:
        command.append("--dry-run")
    if args.json:
        command.append("--json")
    proc = run_command(command, capture=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    return proc.returncode


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


def cmd_memory(args: argparse.Namespace) -> int:
    command = [sys.executable, str(SCRIPTS / "wechat_memory.py"), args.action, "--db", str(args.db)]
    if args.chat:
        command += ["--chat", args.chat]
    if getattr(args, "json", False):
        command.append("--json")
    proc = run_command(command, capture=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    return proc.returncode


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
    if args.since_epoch is not None:
        command += ["--since-epoch", str(args.since_epoch)]
    if args.until_epoch is not None:
        command += ["--until-epoch", str(args.until_epoch)]
    for token in args.match_token:
        command += ["--match-token", str(token)]
    for source in args.source:
        command += ["--source", str(source)]
    if args.auto_source:
        command.append("--auto-source")
    if args.dry_run:
        command.append("--dry-run")
    if args.summary_only:
        command.append("--summary-only")
    if args.record_empty:
        command.append("--record-empty")
    return run_command(command, capture=False).returncode


def cmd_autopublish_video(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(SCRIPTS / "wechat_autopublish_video.py"),
        "--db",
        str(args.db),
        "--dest",
        str(args.dest),
        "--since-minutes",
        str(args.since_minutes),
        "--limit",
        str(args.limit),
    ]
    for chat in args.chat:
        command += ["--chat", str(chat)]
    if args.source:
        command += ["--source", str(args.source)]
    if args.title:
        command += ["--title", args.title]
    for token in args.match_token:
        command += ["--match-token", str(token)]
    for local_id in args.message_local_id:
        command += ["--message-local-id", str(local_id)]
    if args.sync:
        command.append("--sync")
    if args.fetch_gui:
        command.append("--fetch-gui")
        command += ["--fetch-timeout", str(args.fetch_timeout), "--display", args.display]
    if args.video_click:
        command += ["--video-click", args.video_click]
    if args.no_auto_source:
        command.append("--no-auto-source")
    if args.replace:
        command.append("--replace")
    if args.list:
        command.append("--list")
    if args.dry_run:
        command.append("--dry-run")
    if getattr(args, "json", False):
        command.append("--json")
    return run_command(command, capture=False).returncode


def cmd_backend(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(SCRIPTS / "wechat_direct_backend.py"),
        "--chat",
        args.chat,
        "--external",
        str(args.external),
    ]
    if getattr(args, "json", False):
        command.append("--json")
    if args.db_dir:
        command += ["--db-dir", str(args.db_dir)]
    if args.action == "install":
        command += ["install", "--repo", args.repo]
        if args.update:
            command.append("--update")
        if args.skip_deps:
            command.append("--skip-deps")
    elif args.action == "decrypt":
        command.append("decrypt")
        if args.incremental:
            command.append("--incremental")
        if args.dry_run:
            command.append("--dry-run")
    elif args.action == "monitor-web":
        command += ["monitor-web", "--host", args.host, "--port", str(args.port)]
    elif args.action == "api-history":
        command += ["api-history", "--port", str(args.port), "--limit", str(args.limit), "--since", str(args.since)]
        if args.filter_chat:
            command += ["--chat", args.filter_chat]
        if args.raw:
            command.append("--raw")
    else:
        command.append(args.action)
    proc = run_command(command, capture=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    return proc.returncode


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


def direct_monitor_health() -> dict[str, Any]:
    configs = discover_direct_monitor_configs()
    groups = [direct_config_health(path) for path in configs]
    separation = direct_config_separation_summary(configs)
    backend = external_backend_summary()
    caught_up = sum(1 for item in groups if item.get("caught_up"))
    ok = bool(groups) and all(item.get("ok") for item in groups) and bool(backend.get("ok")) and bool(separation.get("ok"))
    return {
        "ok": ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "group_count": len(groups),
        "caught_up_groups": caught_up,
        "separation": separation,
        "external_backend": backend,
        "groups": groups,
        "notes": [
            "private chatroom ids, wxids, message-table names, and DB paths are intentionally omitted",
            "set WECHAT_DIRECT_CONFIGS in .private/wechat_supervisor.local.env to control monitored groups",
        ],
    }


def direct_config_separation_summary(paths: list[Path]) -> dict[str, Any]:
    records: list[dict[str, str]] = []
    missing_send_title_guard: list[str] = []
    unreadable: list[str] = []
    for path in paths:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unreadable.append(path.name)
            continue
        config_name = path.name
        if not has_send_title_guard(config.get("send_target")):
            missing_send_title_guard.append(config_name)
        records.append(
            {
                "config_name": config_name,
                "chat_name": str(config.get("chat_name") or ""),
                "message_table": str(config.get("message_table") or ""),
                "state_path": normalized_private_path_key(str(config.get("state_path") or "")),
            }
        )
    duplicate_state = duplicate_config_groups(records, "state_path")
    duplicate_table = duplicate_config_groups(records, "message_table")
    duplicate_chat = duplicate_config_groups(records, "chat_name")
    ok = not unreadable and not missing_send_title_guard and not duplicate_state and not duplicate_table and not duplicate_chat
    return {
        "ok": ok,
        "private_values_redacted": True,
        "config_count": len(paths),
        "checked_config_count": len(records),
        "unreadable_config_count": len(unreadable),
        "missing_send_title_guard_count": len(missing_send_title_guard),
        "duplicate_state_path_count": len(duplicate_state),
        "duplicate_message_table_count": len(duplicate_table),
        "duplicate_chat_name_count": len(duplicate_chat),
        "unreadable_configs": unreadable,
        "missing_send_title_guard_configs": missing_send_title_guard,
        "duplicate_state_path_configs": duplicate_state,
        "duplicate_message_table_configs": duplicate_table,
        "duplicate_chat_name_configs": duplicate_chat,
    }


def normalized_private_path_key(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = PACKAGE_ROOT / path
    return str(path)


def duplicate_config_groups(records: list[dict[str, str]], field: str) -> list[list[str]]:
    grouped: dict[str, list[str]] = {}
    for record in records:
        value = record.get(field, "")
        if not value:
            continue
        grouped.setdefault(value, []).append(record["config_name"])
    return [sorted(names) for names in grouped.values() if len(names) > 1]


def external_backend_summary() -> dict[str, Any]:
    proc = run_command([sys.executable, str(SCRIPTS / "wechat_direct_backend.py"), "--json", "status"], capture=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "status": "status-unreadable",
            "returncode": proc.returncode,
            "private_paths_redacted": True,
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": "status-invalid",
            "returncode": proc.returncode,
            "private_paths_redacted": True,
        }
    allowed = {
        "ok",
        "status",
        "external_exists",
        "external_git",
        "venv_python_exists",
        "db_dir_exists",
        "message_db_exists",
        "source_db_count",
        "config_exists",
        "keys_file_exists",
        "keys_file_mtime",
        "decrypted_dir_exists",
        "decrypted_db_count",
        "decrypted_message_db_exists",
        "scripts",
        "monitor_web",
        "private_paths_redacted",
        "checked_at",
    }
    summary = {key: payload[key] for key in allowed if key in payload}
    summary["returncode"] = proc.returncode
    return summary


def codex_session_summary() -> dict[str, Any]:
    registry = PRIVATE / "codex_sessions" / "sessions.local.json"
    if not registry.exists():
        return {"ok": True, "path_exists": False, "count": 0, "items": []}
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "path_exists": True, "count": 0, "items": []}
    items = []
    thread_counts: dict[str, int] = {}
    if isinstance(data, dict):
        for key, value in sorted(data.items()):
            if not isinstance(value, dict):
                continue
            thread_id = str(value.get("thread_id") or "")
            if thread_id:
                thread_counts[thread_id] = thread_counts.get(thread_id, 0) + 1
            items.append(
                {
                    "key": key,
                    "legacy_key": not bool(CODEX_SESSION_KEY_RE.fullmatch(key)),
                    "chat_name": value.get("chat_name", ""),
                    "role": value.get("role", ""),
                    "thread_id_short": thread_id[:8] if thread_id else "",
                    "model": value.get("model", ""),
                    "reasoning_effort": value.get("reasoning_effort", ""),
                    "turn_count": int(value.get("turn_count") or 0),
                    "last_used_at": value.get("last_used_at", ""),
                    "last_resumed": bool(value.get("last_resumed")),
                    "last_fallback_started": bool(value.get("last_fallback_started")),
                }
            )
    legacy_count = sum(1 for item in items if item["legacy_key"])
    duplicate_thread_count = 0
    for item in items:
        record = data.get(item["key"], {}) if isinstance(data, dict) else {}
        thread_id = str(record.get("thread_id") or "") if isinstance(record, dict) else ""
        duplicate = bool(thread_id and thread_counts.get(thread_id, 0) > 1)
        item["thread_id_duplicate"] = duplicate
        if duplicate:
            duplicate_thread_count += 1
    return {
        "ok": legacy_count == 0 and duplicate_thread_count == 0,
        "path_exists": True,
        "count": len(items),
        "legacy_count": legacy_count,
        "duplicate_thread_entry_count": duplicate_thread_count,
        "items": items,
    }


def discover_direct_monitor_configs() -> list[Path]:
    env_path = PRIVATE / "wechat_supervisor.local.env"
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export ") :].strip()
            key, raw_value = stripped.split("=", 1)
            key = key.strip()
            try:
                parsed = shlex.split(raw_value, comments=False, posix=True)
                values[key] = parsed[0] if parsed else ""
            except ValueError:
                values[key] = raw_value.strip().strip("'\"")
    raw_configs = values.get("WECHAT_DIRECT_CONFIGS") or os.environ.get("WECHAT_DIRECT_CONFIGS", "")
    paths: list[Path] = []
    if raw_configs:
        paths = [Path(item.strip()) for item in raw_configs.split(",") if item.strip()]
    else:
        raw_config = values.get("WECHAT_DIRECT_CONFIG") or os.environ.get("WECHAT_DIRECT_CONFIG", "")
        if raw_config:
            paths = [Path(raw_config)]
        elif DEFAULT_DIRECT_CONFIG.exists():
            paths = [DEFAULT_DIRECT_CONFIG]
    resolved = []
    seen: set[Path] = set()
    for path in paths:
        candidate = path if path.is_absolute() else PACKAGE_ROOT / path
        if candidate in seen:
            continue
        seen.add(candidate)
        resolved.append(candidate)
    return resolved


def direct_config_health(path: Path) -> dict[str, Any]:
    base = {
        "config_name": path.name,
        "config_exists": path.exists(),
        "ok": False,
        "caught_up": False,
    }
    if not path.exists():
        return {**base, "error": "config-missing"}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {**base, "error": str(exc)}

    raw_state_path = str(config.get("state_path") or "").strip()
    state_path = Path(raw_state_path) if raw_state_path else None
    if state_path and not state_path.is_absolute():
        state_path = PACKAGE_ROOT / state_path
    state_last = 0
    state: dict[str, Any] = {}
    state_exists = state_path.exists() if state_path else False
    if state_exists:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state_last = int(state.get("last_local_id") or 0)
        except (OSError, json.JSONDecodeError, ValueError):
            state_last = 0

    latest = latest_direct_db_local_id(str(config.get("message_table") or ""))
    has_guarded_target = has_send_title_guard(config.get("send_target"))
    codex = config.get("codex") if isinstance(config.get("codex"), dict) else {}
    organizer = config.get("organizer") if isinstance(config.get("organizer"), dict) else {}
    caught_up = latest.get("ok") and state_last >= int(latest.get("latest_local_id") or 0)
    ok = bool(
        state_exists
        and latest.get("ok")
        and caught_up
        and bool(config.get("ignore_self_messages", True))
        and not bool(config.get("respond_to_self", False))
        and has_guarded_target
    )
    return {
        **base,
        "ok": ok,
        "chat_name": str(config.get("chat_name") or path.stem),
        "state_exists": state_exists,
        "state_last_local_id": state_last,
        "db_latest_local_id": latest.get("latest_local_id"),
        "db_latest_at": latest.get("latest_at", ""),
        "db_latest_age_seconds": latest.get("age_seconds"),
        "db_stale": bool((latest.get("age_seconds") or 0) > int(config.get("stale_warning_seconds", 1800))),
        "caught_up": bool(caught_up),
        "respond_to_all": bool(config.get("respond_to_all", False)),
        "respond_to_self": bool(config.get("respond_to_self", False)),
        "ignore_self_messages": bool(config.get("ignore_self_messages", True)),
        "chat_purpose": str(config.get("chat_purpose") or ""),
        "analysis_mode": str(config.get("analysis_mode") or ""),
        "organizer_enabled": bool(organizer.get("enabled", False)),
        "organizer_capture_unclassified": bool(organizer.get("capture_unclassified", True)),
        "poll_seconds": float(config.get("poll_seconds", 0.8)),
        "catchup_poll_seconds": float(config.get("catchup_poll_seconds", 0.1)),
        "codex_model": str(codex.get("model") or "gpt-5.5"),
        "codex_reasoning_effort": str(codex.get("reasoning_effort") or "low"),
        "codex_timeout_seconds": int(codex.get("timeout_seconds") or 60),
        "last_seen_at": str(state.get("last_seen_at") or ""),
        "last_loop_at": str(state.get("last_loop_at") or ""),
        "last_loop_metrics": sanitize_loop_metrics(state.get("last_loop_metrics")),
        "send_target_has_title_guard": has_guarded_target,
        "db_status": latest.get("status", "ok"),
    }


def sanitize_loop_metrics(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    allowed = {
        "started_at",
        "decrypt_ms",
        "read_ms",
        "context_ms",
        "codex_ms",
        "send_ms",
        "total_ms",
        "organizer_ms",
        "organizer_status",
        "organizer_messages",
        "organizer_items",
        "organizer_error",
    }
    return {key: raw[key] for key in allowed if key in raw}


def latest_direct_db_local_id(table: str) -> dict[str, Any]:
    db_path = PRIVATE / "wechat_decrypt" / "decrypted" / "message" / "message_0.db"
    if not db_path.exists():
        return {"ok": False, "status": "decrypted-db-missing", "latest_local_id": None, "latest_at": "", "age_seconds": None}
    if not is_safe_sql_identifier(table):
        return {"ok": False, "status": "message-table-invalid", "latest_local_id": None, "latest_at": "", "age_seconds": None}
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(f'SELECT MAX(local_id), MAX(create_time) FROM "{table}"').fetchone()
    except sqlite3.Error:
        return {"ok": False, "status": "message-table-unreadable", "latest_local_id": None, "latest_at": "", "age_seconds": None}
    latest_time = int(row[1] or 0)
    latest_at = datetime.fromtimestamp(latest_time).isoformat(timespec="seconds") if latest_time else ""
    age_seconds = int(datetime.now().timestamp() - latest_time) if latest_time else None
    return {"ok": True, "status": "ok", "latest_local_id": int(row[0] or 0), "latest_at": latest_at, "age_seconds": age_seconds}


def is_safe_sql_identifier(value: str) -> bool:
    return bool(value) and all(ch.isalnum() or ch == "_" for ch in value)


def has_send_title_guard(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    return bool(str(raw.get("expected_title") or raw.get("title") or raw.get("name") or "").strip())


def control_map_payload() -> dict[str, Any]:
    status = status_payload()
    health = direct_monitor_health()
    layer_specs = [
        {
            "id": "isolated_gui",
            "name": "Isolated official GUI control",
            "goal": "Drive the real Linux WeChat client through Xvfb/noVNC, xdotool, xclip, screenshots, OCR, and title guards.",
            "ready": status["desktop"]["status"] == "ready",
            "commands": [
                "labcanvas wechat desktop start",
                "labcanvas wechat send --message 'ping'",
                "labcanvas wechat browser-assist --url https://example.com --json",
            ],
            "failure_mode": "If OCR/title guard is ambiguous, fail closed and ask for human confirmation.",
        },
        {
            "id": "direct_receive",
            "name": "Direct receive and state mirror",
            "goal": "Poll the user's own local message cache/decrypted mirror, coalesce bursts, ignore self messages, and maintain per-chat state.",
            "ready": bool(health.get("ok")) and int(health.get("group_count") or 0) > 0,
            "commands": [
                "labcanvas wechat health --json",
                "labcanvas wechat hold start",
            ],
            "failure_mode": "If a chat config is stale or duplicated, do not route messages until health is green.",
        },
        {
            "id": "media_sync",
            "name": "Attachment and media resolver",
            "goal": "Copy same-chat files/images/videos from xwechat_files into ignored private storage and bind them to source local_id rows.",
            "ready": bool(status["mirror"].get("exists")) and len(status.get("media_sources") or []) > 0,
            "commands": [
                "labcanvas wechat media-sync --chat '<chat>' --auto-source --since-minutes 60",
                "labcanvas wechat autopublish-video --chat '<chat>' --message-local-id 14 --sync --fetch-gui --json",
            ],
            "failure_mode": "If exact media is missing, ask for resend/opening the source; never borrow nearby media.",
        },
        {
            "id": "agent_queue",
            "name": "Agent queue and deterministic workers",
            "goal": "Route simple replies fast, queue slow work, atomically claim tasks, reuse per-chat sessions, and run deterministic exact-video publishing.",
            "ready": status["sessions"]["supervisor"]["running"] and status["queue"]["exists"],
            "commands": [
                "labcanvas wechat queue --json",
                "labcanvas wechat worker once --send",
            ],
            "failure_mode": "If a worker crashes, stale in-progress claims are reclaimed; irreversible actions still require explicit approval.",
        },
        {
            "id": "observability",
            "name": "Event log, screenshots, and replay evidence",
            "goal": "Record mirrored messages, outbound sends, task state, GUI screenshots, and queue transitions without committing private data.",
            "ready": bool(status["mirror"].get("exists")) and int(status["mirror"].get("event_count") or 0) > 0,
            "commands": [
                "labcanvas wechat status --json",
                "labcanvas wechat memory summary --chat '<chat>' --json",
            ],
            "failure_mode": "Logs are local/private; public docs must use placeholders and summaries only.",
        },
        {
            "id": "official_or_bridge_apis",
            "name": "Optional bridge APIs",
            "goal": "Evaluate Wechaty, MCP, ACP, Docker GUI, or platform-specific accessibility bridges when they are more stable than screen control.",
            "ready": False,
            "commands": [
                "Review the reference_projects list before adding a new backend.",
            ],
            "failure_mode": "Use only consented accounts and maintained projects; keep the GUI path as the fallback.",
        },
    ]
    blocked = [
        {
            "id": "packet_mitm",
            "name": "Wireshark/TLS MITM/private protocol replay",
            "reason": "Unreliable against encrypted apps and not acceptable for automation that could expose credentials, session tokens, or private traffic.",
            "allowed_alternative": "Use GUI state, local owned-data mirrors, official APIs, or human-assisted browser sessions.",
        },
        {
            "id": "session_or_key_theft",
            "name": "Session extraction, credential theft, or bypassing login/CAPTCHA",
            "reason": "This crosses from automation into unauthorized access. The tool must ask the user to log in or confirm manually.",
            "allowed_alternative": "Open noVNC/browser-assist and wait for the account owner.",
        },
        {
            "id": "cross_chat_media_guessing",
            "name": "Using nearby files or another chat's media",
            "reason": "It causes crosstalk and wrong actions.",
            "allowed_alternative": "Exact local_id/server_id/media-token matching with fail-closed behavior.",
        },
    ]
    ready_layers = sum(1 for layer in layer_specs if layer["ready"])
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "score": {
            "ready_layers": ready_layers,
            "total_layers": len(layer_specs),
            "label": "high-control" if ready_layers >= 5 else "partial-control" if ready_layers >= 3 else "bootstrap-needed",
        },
        "principle": "Make WeChat observable and controllable through owned, consented surfaces; do not bypass encryption, authentication, or platform abuse protections.",
        "layers": layer_specs,
        "blocked_methods": blocked,
        "reference_projects": wechat_reference_projects(),
        "next_hardening_steps": [
            "Add per-action screenshot before/after diff assertions for every GUI sender action.",
            "Add a UI state machine for compose box, attachment modal, chat search, and group settings pages.",
            "Keep one send lock across all GUI actions and expose lock owner/age in health output.",
            "Add media manifest rows keyed by chat_name, local_id, server_id, md5, size, and path.",
            "Add optional bridge backends behind capability flags, never as a replacement for the safe GUI fallback.",
        ],
    }


def wechat_reference_projects() -> list[dict[str, str]]:
    return [
        {
            "name": "wechaty/wechaty",
            "url": "https://github.com/wechaty/wechaty",
            "use": "Cross-platform conversational RPA SDK; useful as a design reference for bot event APIs and adapters.",
            "risk": "May depend on puppet/provider availability and login constraints.",
        },
        {
            "name": "BiboyQG/WeChat-MCP",
            "url": "https://github.com/BiboyQG/WeChat-MCP",
            "use": "MCP/accessibility/screen-capture pattern for exposing WeChat actions as agent tools.",
            "risk": "Platform-specific; keep title guards and GUI fallback.",
        },
        {
            "name": "thisnick/agent-wechat",
            "url": "https://github.com/thisnick/agent-wechat",
            "use": "Dockerized RPA controller pattern with API/CLI surfaces.",
            "risk": "Container GUI reliability and account login state still need supervision.",
        },
        {
            "name": "huohuoer/wechat-cli",
            "url": "https://github.com/huohuoer/wechat-cli",
            "use": "Local WeChat data query pattern for LLM integration.",
            "risk": "Use only with the owner's local data and private configs.",
        },
        {
            "name": "ylytdeng/wechat-decrypt",
            "url": "https://github.com/ylytdeng/wechat-decrypt",
            "use": "Owned-data decrypt/monitor backend pattern already used as an optional receive backend.",
            "risk": "Sensitive private data; never commit keys, DBs, or raw chat logs.",
        },
        {
            "name": "formulahendry/wechat-acp",
            "url": "https://github.com/formulahendry/wechat-acp",
            "use": "ACP bridge pattern for forwarding messages to agent runtimes.",
            "risk": "Validate protocol, auth, and account-safety assumptions before integration.",
        },
        {
            "name": "leeguooooo/wechat-use",
            "url": "https://github.com/leeguooooo/wechat-use",
            "use": "macOS background send/agent skill pattern; useful if adding a macOS backend.",
            "risk": "Not a Linux replacement; treat as separate backend.",
        },
    ]


def discover_media_sources() -> list[Path]:
    base = Path.home() / "Documents" / "xwechat_files"
    if not base.exists():
        return []
    sources = []
    seen = set()
    for profile in base.iterdir():
        if not profile.is_dir():
            continue
        for relative in ("msg/file", "msg/video", "msg/attach", "cache", "temp/ImageTemp", "temp/ImageUtils"):
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
    panes = tmux_session_panes(session)
    return {"session": session, "running": True, "status": "running", "panes": panes}


def tmux_session_panes(session: str) -> list[str]:
    windows = run_command(["tmux", "list-windows", "-t", session, "-F", "#{window_id}\t#{window_name}"], capture=True)
    panes: list[str] = []
    for line in windows.stdout.splitlines():
        if "\t" not in line:
            continue
        window_id, window_name = line.split("\t", 1)
        proc = run_command(["tmux", "list-panes", "-t", window_id, "-F", "#{pane_index}: #{pane_current_command} #{pane_pid}"], capture=True)
        for pane in proc.stdout.splitlines():
            panes.append(f"{window_name}.{pane}")
    return panes


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
