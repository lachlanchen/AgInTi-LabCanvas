from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from typing import Any
from urllib import error, parse, request


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = PACKAGE_ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_ENV = PRIVATE / "wecom.local.env"
SUPERVISOR = TOOL_ROOT / "scripts" / "wecom_tmux.sh"
ADMIN_BROWSER = TOOL_ROOT / "scripts" / "wecom_admin_browser.sh"
WINDOWS_CLIENT = TOOL_ROOT / "scripts" / "wecom_windows_client.sh"
DAILY_RESEARCH = TOOL_ROOT / "scripts" / "wecom_daily_research.py"
MEMBER_KNOWLEDGE = TOOL_ROOT / "scripts" / "wecom_member_knowledge.py"
EXTERNAL_BRIDGE = TOOL_ROOT / "scripts" / "wecom_cli_bridge.py"
EXTERNAL_GUARD = TOOL_ROOT / "scripts" / "wecom_cli_transport_guard.py"
WECOM_WORKER = TOOL_ROOT / "scripts" / "wecom_worker_loop.sh"
EXTERNAL_CONFIG = PRIVATE / "wecom_cli_bridge.local.json"
EXTERNAL_RUNTIME = PRIVATE / "wecom-cli-runtime"
GUI_BRIDGE = TOOL_ROOT / "scripts" / "wecom_gui_bridge.py"
GUI_CONFIG = PRIVATE / "wecom_gui_bridge.local.json"
ANDROID_BRIDGE = TOOL_ROOT / "scripts" / "wecom_android_bridge.py"
ANDROID_CONFIG = PRIVATE / "wecom_android_bridge.local.json"
DEFAULT_API_URL = "http://127.0.0.1:19578"


def add_wecom_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("wecom", help="Control the official WeCom AI Bot WebSocket bridge.")
    nested = parser.add_subparsers(dest="wecom_command", required=True)

    init_config = nested.add_parser("init-config", help="Create an ignored private BotID/Secret config template.")
    init_config.add_argument("--force", action="store_true")
    init_config.add_argument("--json", action="store_true")
    init_config.set_defaults(func=cmd_init_config)

    install = nested.add_parser("install", help="Install the pinned official WeCom Node SDK locally.")
    install.add_argument("--json", action="store_true")
    install.set_defaults(func=cmd_install)

    doctor = nested.add_parser("doctor", help="Validate SDK, private config, local API, and tmux state.")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    gateway = nested.add_parser("gateway", help="Start or stop the WeCom gateway and LabCanvas worker in tmux.")
    gateway.add_argument("action", nargs="?", default="status", choices=["start", "stop", "restart", "status"])
    gateway.add_argument("--json", action="store_true")
    gateway.set_defaults(func=cmd_gateway)

    admin = nested.add_parser("admin", help="Open the WeCom admin console in the shared noVNC browser.")
    admin.add_argument("--json", action="store_true")
    admin.set_defaults(func=cmd_admin)

    client = nested.add_parser("client", help="Manage the isolated official WeCom desktop enrollment client.")
    client.add_argument("action", nargs="?", default="status", choices=["status", "download", "install", "start", "fit"])
    client.add_argument("--json", action="store_true")
    client.set_defaults(func=cmd_client)

    daily = nested.add_parser("daily", help="Inspect or run per-group #daily research scheduling.")
    daily.add_argument("action", nargs="?", default="status", choices=["status", "run"])
    daily.add_argument("--force", action="store_true", help="Run today's due action now without duplicating it.")
    daily.add_argument("--json", action="store_true")
    daily.set_defaults(func=cmd_daily)

    knowledge = nested.add_parser("knowledge", help="Inspect and sync private per-member research knowledge.")
    knowledge.add_argument("action", nargs="?", default="status", choices=["status", "sync", "search", "export"])
    knowledge.add_argument("--member-key", default="")
    knowledge.add_argument("--chat", default="")
    knowledge.add_argument("--kind", default="")
    knowledge.add_argument("--query", default="")
    knowledge.add_argument("--limit", type=int, default=25)
    knowledge.add_argument("--output-dir", default="")
    knowledge.add_argument("--json", action="store_true")
    knowledge.set_defaults(func=cmd_knowledge)

    external = nested.add_parser("external", help="Control the separate official WeCom external-group transport.")
    external.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["init", "install", "authorize", "bind", "probe", "status", "once", "restart"],
    )
    external.add_argument("--chat", action="append", dest="chats", default=[])
    external.add_argument("--force", action="store_true")
    external.add_argument("--json", action="store_true")
    external.set_defaults(func=cmd_external)

    gui = nested.add_parser("gui", help="Control the allowlisted external-group WeCom desktop relay.")
    gui.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["init", "status", "once", "chats", "messages", "send", "guide", "restart"],
    )
    gui.add_argument("--chat", default="")
    gui.add_argument("--message", default="")
    gui.add_argument("--file", action="append", dest="files", default=[])
    gui.add_argument("--after", type=int, default=0)
    gui.add_argument("--limit", type=int, default=100)
    gui.add_argument("--task-id", default="manual")
    gui.add_argument("--live", action="store_true")
    gui.add_argument("--force", action="store_true")
    search = gui.add_mutually_exclusive_group()
    search.add_argument("--allow-search-fallback", action="store_true", default=None)
    search.add_argument("--no-search-fallback", action="store_false", dest="allow_search_fallback")
    gui.add_argument("--json", action="store_true")
    gui.set_defaults(func=cmd_gui)

    android = nested.add_parser(
        "android",
        help="Control the allowlisted MIX 2S WeCom transport and fallback API.",
    )
    android.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["init", "status", "chats", "open", "messages", "send", "start", "restart"],
    )
    android.add_argument("--chat", action="append", dest="chats", default=[])
    android.add_argument("--message", default="")
    android.add_argument("--mention", action="append", dest="mentions", default=[])
    android.add_argument("--file", action="append", dest="files", default=[])
    android.add_argument("--task-id", default="manual")
    android.add_argument("--serial", default="")
    android.add_argument("--enqueue", action="store_true")
    android.add_argument("--live", action="store_true")
    android.add_argument("--force", action="store_true")
    android.add_argument("--json", action="store_true")
    android.set_defaults(func=cmd_android)


def cmd_init_config(args: argparse.Namespace) -> int:
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if DEFAULT_ENV.exists() and not args.force:
        payload = {"ok": True, "created": False, "path": str(DEFAULT_ENV), "reason": "exists"}
        print_payload(payload, args.json)
        return 0
    token = secrets.token_hex(32)
    content = f"""# Private local WeCom AI Bot configuration. Never commit this file.
WECOM_ACCOUNT_ID=default
WECOM_BOT_ID=
WECOM_BOT_SECRET=

# Localhost-only delivery API shared by the Node gateway and Python worker.
WECOM_LOCAL_API_PORT=19578
WECOM_LOCAL_API_URL=http://127.0.0.1:19578
WECOM_LOCAL_API_TOKEN={token}

# owner: pair the first sender, then accept only that userid plus allowlist.
# allowlist: accept only WECOM_ALLOWED_USERIDS. all: accept every visible user.
WECOM_ACCESS_MODE=owner
WECOM_PAIR_FIRST_USER=1
WECOM_ALLOWED_USERIDS=
# In owner mode, the owner enrolls a group on first use; members of that group
# may request safe work while irreversible actions remain owner/allowlist-only.
WECOM_GROUP_MEMBER_ACCESS=trusted

WECOM_AGENT_BACKEND=codex
WECOM_ROUTE_MODEL=gpt-5.6-sol
WECOM_ROUTE_EFFORT=low
WECOM_ROUTE_TIMEOUT_SECONDS=35
# Fast chat and routing stay low-effort. Durable research/design/file tasks use
# the same model at high reasoning inside the isolated WeCom worker process.
WECHAT_WORKER_CODEX_MODEL=gpt-5.6-sol
WECHAT_WORKER_MIN_EFFORT=low
WECHAT_WORKER_MAX_EFFORT=xhigh
WECOM_PENDING_TTL_SECONDS=3600
WECOM_TASK_QUEUE={TOOL_ROOT / '.private' / 'wecom_task_queue.jsonl'}
WECOM_MIRROR_DB={PACKAGE_ROOT / 'output' / 'wecom' / 'wecom_mirror.sqlite'}
WECOM_AGINTI_COMMAND=aginti
WECOM_AGINTI_WORKSPACE=../Agent/AgInTiFlow

# Per-group #daily research scheduler. Times use WECOM_DAILY_TIMEZONE.
WECOM_DAILY_RESEARCH_TIME=06:00
WECOM_DAILY_TOPIC_PROMPT_TIME=05:45
WECOM_DAILY_TIMEZONE=Asia/Hong_Kong
WECOM_DAILY_POLL_SECONDS=30
WECOM_DAILY_AUTO_ENROLL=1

# Private per-member papers, files, interests, ideas, and agent conclusions.
WECOM_MEMBER_KNOWLEDGE_DB={TOOL_ROOT / '.private' / 'wecom_member_knowledge.sqlite'}
WECOM_MEMBER_ARCHIVE_ROOT={PACKAGE_ROOT / 'output' / 'wecom' / 'member_knowledge'}
WECOM_KNOWLEDGE_POLL_SECONDS=5
"""
    DEFAULT_ENV.write_text(content, encoding="utf-8")
    DEFAULT_ENV.chmod(0o600)
    payload = {"ok": True, "created": True, "path": str(DEFAULT_ENV)}
    print_payload(payload, args.json)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    npm = shutil.which("npm")
    if not npm:
        payload = {"ok": False, "error": "npm was not found"}
        print_payload(payload, args.json)
        return 1
    proc = subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=TOOL_ROOT, capture_output=True, text=True, check=False)
    payload = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }
    print_payload(payload, args.json)
    return 0 if payload["ok"] else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    config = read_env_file(DEFAULT_ENV)
    checks = {
        "node": command_version("node", "--version"),
        "npm": command_version("npm", "--version"),
        "official_sdk": (TOOL_ROOT / "node_modules" / "@wecom" / "aibot-node-sdk" / "package.json").is_file(),
        "private_config": DEFAULT_ENV.is_file(),
        "bot_id_configured": bool(config.get("WECOM_BOT_ID")),
        "bot_secret_configured": bool(config.get("WECOM_BOT_SECRET")),
        "local_api_token_configured": bool(config.get("WECOM_LOCAL_API_TOKEN")),
        "supervisor_script": SUPERVISOR.is_file() and os.access(SUPERVISOR, os.X_OK),
        "ingress_script": (TOOL_ROOT / "scripts" / "wecom_ingest.py").is_file(),
        "daily_research_script": DAILY_RESEARCH.is_file() and os.access(DAILY_RESEARCH, os.X_OK),
        "member_knowledge_script": MEMBER_KNOWLEDGE.is_file(),
        "external_bridge_script": EXTERNAL_BRIDGE.is_file(),
        "external_guard_script": EXTERNAL_GUARD.is_file(),
        "wecom_worker_script": WECOM_WORKER.is_file() and os.access(WECOM_WORKER, os.X_OK),
        "local_api": probe_health(config.get("WECOM_LOCAL_API_URL") or DEFAULT_API_URL),
        "tmux": tmux_status(config.get("WECOM_TMUX_SESSION") or "labcanvas-wecom"),
    }
    required = (
        bool(checks["node"]),
        bool(checks["npm"]),
        checks["official_sdk"],
        checks["private_config"],
        checks["bot_id_configured"],
        checks["bot_secret_configured"],
        checks["local_api_token_configured"],
        checks["supervisor_script"],
        checks["ingress_script"],
        checks["daily_research_script"],
        checks["member_knowledge_script"],
        checks["wecom_worker_script"],
    )
    payload = {"ok": all(required), "checks": checks, "config_path": str(DEFAULT_ENV)}
    print_payload(payload, args.json)
    return 0 if payload["ok"] else 1


def cmd_gateway(args: argparse.Namespace) -> int:
    proc = subprocess.run([str(SUPERVISOR), args.action], cwd=PACKAGE_ROOT, capture_output=True, text=True, check=False)
    config = read_env_file(DEFAULT_ENV)
    payload = {
        "ok": proc.returncode == 0,
        "action": args.action,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "health": probe_health(config.get("WECOM_LOCAL_API_URL") or DEFAULT_API_URL),
    }
    print_payload(payload, args.json)
    return 0 if payload["ok"] else 1


def cmd_admin(args: argparse.Namespace) -> int:
    proc = subprocess.run([str(ADMIN_BROWSER)], cwd=PACKAGE_ROOT, capture_output=True, text=True, check=False)
    default_port = os.environ.get("WECOM_ADMIN_NOVNC_PORT", "6133")
    default_url = (
        f"http://127.0.0.1:{default_port}/vnc.html?"
        f"host=127.0.0.1&port={default_port}&autoconnect=1&resize=scale"
    )
    reported_url = next(
        (
            line.removeprefix("noVNC:").strip()
            for line in proc.stdout.splitlines()
            if line.strip().startswith("noVNC:")
        ),
        default_url,
    )
    payload = {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "novnc_url": reported_url,
    }
    print_payload(payload, args.json)
    return 0 if payload["ok"] else 1


def cmd_client(args: argparse.Namespace) -> int:
    proc = subprocess.run(
        [str(WINDOWS_CLIENT), args.action, "--json"],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": "WeCom desktop helper returned invalid JSON",
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        }
    print_payload(payload, args.json)
    return 0 if proc.returncode == 0 and payload.get("ok") else 1


def cmd_daily(args: argparse.Namespace) -> int:
    command = [sys.executable, str(DAILY_RESEARCH), args.action, "--json"]
    if args.action == "run" and args.force:
        command.append("--force")
    config = read_env_file(DEFAULT_ENV)
    env = {**os.environ, **config}
    pythonpath = [str(PACKAGE_ROOT / "src"), env.get("PYTHONPATH", "")]
    env["PYTHONPATH"] = os.pathsep.join(item for item in pythonpath if item)
    proc = subprocess.run(command, cwd=PACKAGE_ROOT, env=env, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": "daily research command returned invalid JSON",
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        }
    print_payload(payload, args.json)
    return 0 if proc.returncode == 0 and payload.get("ok") else 1


def cmd_knowledge(args: argparse.Namespace) -> int:
    command = [sys.executable, str(MEMBER_KNOWLEDGE), args.action]
    if args.action == "search":
        command.append(args.query)
        if args.member_key:
            command.extend(["--member-key", args.member_key])
        if args.chat:
            command.extend(["--chat", args.chat])
        if args.kind:
            command.extend(["--kind", args.kind])
        command.extend(["--limit", str(max(1, min(200, args.limit)))])
    elif args.action == "export":
        if not args.member_key:
            payload = {"ok": False, "error": "--member-key is required for export"}
            print_payload(payload, args.json)
            return 2
        command.extend(["--member-key", args.member_key])
        if args.output_dir:
            command.extend(["--output-dir", args.output_dir])
    command.append("--json")
    config = read_env_file(DEFAULT_ENV)
    env = {**os.environ, **config}
    proc = subprocess.run(command, cwd=PACKAGE_ROOT, env=env, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": "member knowledge command returned invalid JSON",
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        }
    print_payload(payload, args.json)
    return 0 if proc.returncode == 0 and payload.get("ok") else 1


def cmd_external(args: argparse.Namespace) -> int:
    if args.action == "install":
        npm = shutil.which("npm")
        if not npm:
            payload = {"ok": False, "error": "npm was not found"}
        else:
            EXTERNAL_RUNTIME.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(
                [npm, "install", "--no-audit", "--no-fund", "--prefix", str(EXTERNAL_RUNTIME), "@wecom/cli@0.1.9"],
                cwd=PACKAGE_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-1000:],
                "stderr_tail": proc.stderr[-1000:],
            }
        print_payload(payload, args.json)
        return 0 if payload.get("ok") else 1

    if args.action == "bind":
        payload = bind_external_cli_profile()
        print_payload(payload, args.json)
        return 0 if payload.get("ok") else 1

    if args.action == "authorize":
        browser = subprocess.run(
            [str(ADMIN_BROWSER)],
            cwd=PACKAGE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        supervisor = subprocess.run(
            [str(SUPERVISOR), "external-restart"],
            cwd=PACKAGE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {
            "ok": browser.returncode == 0 and supervisor.returncode == 0,
            "state": "authorization_guard_started",
            "novnc_url": admin_novnc_url(),
            "tmux_stdout": supervisor.stdout.strip(),
            "error": (browser.stderr or supervisor.stderr).strip(),
        }
        print_payload(payload, args.json)
        return 0 if payload["ok"] else 1

    if args.action == "restart":
        proc = subprocess.run(
            [str(SUPERVISOR), "external-restart"],
            cwd=PACKAGE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {"ok": proc.returncode == 0, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
        print_payload(payload, args.json)
        return 0 if payload["ok"] else 1

    if args.action == "status":
        command = [
            sys.executable,
            str(EXTERNAL_GUARD),
            "--config",
            str(EXTERNAL_CONFIG),
            "status",
            "--json",
        ]
        proc = subprocess.run(command, cwd=PACKAGE_ROOT, capture_output=True, text=True, check=False)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "error": "external WeCom guard returned invalid JSON",
                "stdout_tail": proc.stdout[-1000:],
                "stderr_tail": proc.stderr[-1000:],
            }
        else:
            payload["ok"] = proc.returncode == 0 and bool(payload.get("configured"))
        print_payload(payload, args.json)
        return 0 if payload.get("ok") else 1

    command = [sys.executable, str(EXTERNAL_BRIDGE), "--config", str(EXTERNAL_CONFIG), args.action, "--json"]
    if args.action == "init":
        for chat in args.chats:
            command.extend(["--chat", chat])
        if args.force:
            command.append("--force")
    proc = subprocess.run(command, cwd=PACKAGE_ROOT, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": "external WeCom command returned invalid JSON",
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        }
    print_payload(payload, args.json)
    return 0 if proc.returncode == 0 and payload.get("ok") else 1


def cmd_gui(args: argparse.Namespace) -> int:
    if args.action == "restart":
        proc = subprocess.run(
            [str(SUPERVISOR), "gui-restart"],
            cwd=PACKAGE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {"ok": proc.returncode == 0, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
        print_payload(payload, args.json)
        return 0 if payload["ok"] else 1

    command = [sys.executable, str(GUI_BRIDGE), "--config", str(GUI_CONFIG), args.action]
    if args.action == "init":
        if args.chat:
            command.extend(["--chat", args.chat])
        if args.force:
            command.append("--force")
        search_fallback = getattr(args, "allow_search_fallback", None)
        if search_fallback is True:
            command.append("--allow-search-fallback")
        elif search_fallback is False:
            command.append("--no-search-fallback")
    elif args.action in {"messages", "send", "guide"}:
        if not args.chat:
            payload = {"ok": False, "error": f"--chat is required for wecom gui {args.action}"}
            print_payload(payload, args.json)
            return 2
        command.extend(["--chat", args.chat])
        if args.action == "messages":
            command.extend(["--after", str(max(0, args.after)), "--limit", str(args.limit)])
        if args.action == "send":
            if not args.message.strip() and not args.files:
                payload = {"ok": False, "error": "wecom gui send requires --message and/or --file"}
                print_payload(payload, args.json)
                return 2
            command.extend(["--message", args.message, "--task-id", args.task_id])
            for path in args.files:
                command.extend(["--file", str(Path(path).expanduser())])
            if args.live:
                command.append("--live")
            if args.force:
                command.append("--force-resend")
        if args.action == "guide" and args.live:
            command.append("--live")
    command.append("--json")
    proc = subprocess.run(command, cwd=PACKAGE_ROOT, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": "WeCom GUI command returned invalid JSON",
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        }
    print_payload(payload, args.json)
    return 0 if proc.returncode == 0 and payload.get("ok") else 1


def cmd_android(args: argparse.Namespace) -> int:
    if args.action in {"start", "restart"}:
        action = "android-restart" if args.action == "restart" else "android-start"
        proc = subprocess.run(
            [str(SUPERVISOR), action],
            cwd=PACKAGE_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
        print_payload(payload, args.json)
        return 0 if payload["ok"] else 1

    command = [sys.executable, str(ANDROID_BRIDGE), "--config", str(ANDROID_CONFIG), args.action]
    if args.action == "init":
        for chat in args.chats:
            command.extend(["--chat", chat])
        if args.serial:
            command.extend(["--serial", args.serial])
        if args.force:
            command.append("--force")
    elif args.action in {"open", "messages", "send"}:
        if len(args.chats) != 1:
            payload = {"ok": False, "error": f"wecom android {args.action} requires exactly one --chat"}
            print_payload(payload, args.json)
            return 2
        command.extend(["--chat", args.chats[0]])
        if args.action == "messages" and args.enqueue:
            command.append("--enqueue")
        if args.action == "send":
            if not args.message.strip() and not args.files:
                payload = {"ok": False, "error": "wecom android send requires --message and/or --file"}
                print_payload(payload, args.json)
                return 2
            command.extend(["--message", args.message, "--task-id", args.task_id])
            for mention in args.mentions:
                command.extend(["--mention", mention])
            for path in args.files:
                command.extend(["--file", str(Path(path).expanduser())])
            if args.live:
                command.append("--live")
    command.append("--json")
    proc = subprocess.run(command, cwd=PACKAGE_ROOT, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": "WeCom Android command returned invalid JSON",
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        }
    print_payload(payload, args.json)
    return 0 if proc.returncode == 0 and payload.get("ok") else 1


def bind_external_cli_profile() -> dict[str, Any]:
    cli = EXTERNAL_RUNTIME / "node_modules" / ".bin" / "wecom-cli"
    if not cli.is_file():
        return {"ok": False, "error": "official WeCom CLI is not installed; run `labcanvas wecom external install`"}
    browser = subprocess.run([str(ADMIN_BROWSER)], cwd=PACKAGE_ROOT, capture_output=True, text=True, check=False)
    if browser.returncode != 0:
        return {"ok": False, "error": "dedicated WeCom admin browser could not be started"}
    auth_dir = PRIVATE / "wecom-cli-message-config"
    env = {**os.environ, "WECOM_CLI_CONFIG_DIR": str(auth_dir)}
    process = subprocess.Popen(
        [str(cli), "init", "--noninteractive", "--no-open"],
        cwd=PACKAGE_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    qr_url = ""
    prefix = "https://work.weixin.qq.com/ai/qc/gen?"
    assert process.stdout is not None
    for line in process.stdout:
        match = re.search(r"https://work\.weixin\.qq\.com/ai/qc/gen\?[^\s]+", line)
        if match:
            qr_url = match.group(0).strip()
            break
    if not qr_url:
        process.kill()
        process.wait(timeout=5)
        return {"ok": False, "error": "official WeCom CLI did not provide an authorization QR URL"}
    if not qr_url.startswith(prefix):
        process.kill()
        process.wait(timeout=5)
        return {"ok": False, "error": "refusing unexpected WeCom authorization URL"}
    try:
        page_id = open_cdp_tab(qr_url, int(os.environ.get("WECOM_ADMIN_CDP_PORT", "9353")))
        _, _ = process.communicate(timeout=310)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        return {"ok": False, "error": "WeCom QR authorization timed out", "novnc_url": admin_novnc_url()}
    except (error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        process.kill()
        process.wait(timeout=5)
        return {"ok": False, "error": f"authorization browser failed: {type(exc).__name__}"}
    return {
        "ok": process.returncode == 0,
        "bound": process.returncode == 0,
        "page": page_id,
        "novnc_url": admin_novnc_url(),
        "error": "" if process.returncode == 0 else "WeCom did not complete QR authorization",
    }


def open_cdp_tab(url: str, port: int) -> str:
    with request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
        pages = json.loads(response.read().decode("utf-8"))
    for page in pages if isinstance(pages, list) else []:
        if "/ai/qc/gen" not in str(page.get("url") or ""):
            continue
        old_page_id = str(page.get("id") or "")
        if old_page_id:
            try:
                with request.urlopen(f"http://127.0.0.1:{port}/json/close/{old_page_id}", timeout=5):
                    pass
            except error.URLError:
                pass
    endpoint = f"http://127.0.0.1:{port}/json/new?{parse.quote(url, safe='')}"
    with request.urlopen(request.Request(endpoint, method="PUT"), timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    page_id = str(payload.get("id") or "")
    if not page_id:
        raise ValueError("CDP did not return a page id")
    with request.urlopen(f"http://127.0.0.1:{port}/json/activate/{page_id}", timeout=5):
        pass
    return page_id


def admin_novnc_url() -> str:
    port = os.environ.get("WECOM_ADMIN_NOVNC_PORT", "6133")
    return f"http://127.0.0.1:{port}/vnc.html?host=127.0.0.1&port={port}&autoconnect=1&resize=scale"


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        result[key] = value.strip().strip("\"'")
    return result


def command_version(command: str, flag: str) -> str:
    executable = shutil.which(command)
    if not executable:
        return ""
    proc = subprocess.run([executable, flag], capture_output=True, text=True, check=False)
    return (proc.stdout or proc.stderr).strip() if proc.returncode == 0 else ""


def probe_health(base_url: str) -> dict[str, Any]:
    if not (base_url.startswith("http://127.0.0.1:") or base_url.startswith("http://localhost:")):
        return {"ok": False, "error": "non-local URL refused"}
    try:
        with request.urlopen(base_url.rstrip("/") + "/health", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {"ok": False, "error": "invalid response"}
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def tmux_status(session: str) -> dict[str, Any]:
    tmux = shutil.which("tmux")
    if not tmux:
        return {"running": False, "error": "tmux not found"}
    proc = subprocess.run([tmux, "has-session", "-t", session], capture_output=True, text=True, check=False)
    return {"running": proc.returncode == 0, "session": session}


def print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if payload.get("ok"):
        print(payload.get("stdout") or payload.get("path") or "WeCom command completed.")
    else:
        print(payload.get("stderr") or payload.get("error") or json.dumps(payload, ensure_ascii=False), file=sys.stderr)
