from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from typing import Any
from urllib import error, request


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = PACKAGE_ROOT / "agentic_tools" / "wecom_agent"
PRIVATE = TOOL_ROOT / ".private"
DEFAULT_ENV = PRIVATE / "wecom.local.env"
SUPERVISOR = TOOL_ROOT / "scripts" / "wecom_tmux.sh"
ADMIN_BROWSER = TOOL_ROOT / "scripts" / "wecom_admin_browser.sh"
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

WECOM_AGENT_BACKEND=codex
WECOM_ROUTE_MODEL=gpt-5.6-sol
WECOM_ROUTE_EFFORT=low
WECOM_ROUTE_TIMEOUT_SECONDS=35
WECOM_PENDING_TTL_SECONDS=3600
WECOM_TASK_QUEUE={TOOL_ROOT / '.private' / 'wecom_task_queue.jsonl'}
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
