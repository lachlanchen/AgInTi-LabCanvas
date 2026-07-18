#!/usr/bin/env python3
"""Keep the official WeCom external-group authorization and bridge alive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any
from urllib import error, parse, request


ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = ROOT / "agentic_tools" / "wecom_agent"
PRIVATE_ROOT = TOOL_ROOT / ".private"
DEFAULT_CONFIG = PRIVATE_ROOT / "wecom_cli_bridge.local.json"
DEFAULT_STATUS = PRIVATE_ROOT / "wecom_cli_transport.local.json"
BRIDGE = TOOL_ROOT / "scripts" / "wecom_cli_bridge.py"
QR_PREFIX = "https://work.weixin.qq.com/ai/qc/gen?"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS)
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=int(os.environ.get("WECOM_ADMIN_CDP_PORT", "9353")),
    )
    parser.add_argument("--retry-seconds", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("action", nargs="?", default="loop", choices=["loop", "once", "status"])
    args = parser.parse_args()

    config = load_config(args.config)
    if args.action == "status":
        payload = transport_status(config, args.status_path)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if payload["configured"] else 1

    if args.action == "once":
        result = run_once(config, args.status_path, args.cdp_port)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1

    install_signal_handlers()
    try:
        while True:
            result = run_once(config, args.status_path, args.cdp_port)
            if result.get("stopped"):
                return 0
            time.sleep(max(1.0, args.retry_seconds))
    except KeyboardInterrupt:
        write_status(
            args.status_path,
            {"state": "guard_stopped", "last_error": ""},
        )
        return 0


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing external WeCom config: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid external WeCom config: {path}")
    payload["_config_path"] = str(path.resolve())
    return payload


def profile_ready(config: dict[str, Any]) -> bool:
    auth_dir = Path(str(config.get("auth_config_dir") or "")).expanduser()
    if not auth_dir.is_absolute():
        auth_dir = (ROOT / auth_dir).resolve()
    required = ("bot.enc", "mcp_config.enc", ".encryption_key")
    return all((auth_dir / name).is_file() for name in required)


def transport_status(config: dict[str, Any], status_path: Path = DEFAULT_STATUS) -> dict[str, Any]:
    persisted: dict[str, Any] = {}
    if status_path.is_file():
        try:
            value = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                persisted = value
        except (OSError, json.JSONDecodeError):
            persisted = {}
    return {
        "configured": bool(config.get("enabled", True)),
        "profile_ready": profile_ready(config),
        "target_group_count": len(config.get("target_groups") or []),
        "state": str(persisted.get("state") or "not_started"),
        "last_transition": str(persisted.get("last_transition") or ""),
        "last_error": str(persisted.get("last_error") or ""),
        "novnc_url": admin_novnc_url(),
    }


def run_once(config: dict[str, Any], status_path: Path, cdp_port: int) -> dict[str, Any]:
    if not config.get("enabled", True):
        result = {"ok": True, "stopped": True, "state": "disabled"}
        write_status(status_path, result)
        return result
    if profile_ready(config):
        return run_bridge(config, status_path)
    return run_authorization(config, status_path, cdp_port)


def run_bridge(config: dict[str, Any], status_path: Path) -> dict[str, Any]:
    config_path = str(config["_config_path"])
    write_status(status_path, {"state": "bridge_starting", "last_error": ""})
    process = subprocess.Popen(
        [sys.executable, str(BRIDGE), "--config", config_path, "loop"],
        cwd=ROOT,
    )
    write_status(status_path, {"state": "bridge_running", "last_error": ""})
    try:
        returncode = process.wait()
    except KeyboardInterrupt:
        stop_process(process)
        result = {
            "ok": True,
            "stopped": True,
            "state": "bridge_stopped",
            "last_error": "",
        }
        write_status(status_path, result)
        return result
    result = {
        "ok": returncode == 0,
        "state": "bridge_stopped" if returncode == 0 else "bridge_failed",
        "returncode": returncode,
        "last_error": "" if returncode == 0 else f"external bridge exited with {returncode}",
    }
    write_status(status_path, result)
    return result


def run_authorization(config: dict[str, Any], status_path: Path, cdp_port: int) -> dict[str, Any]:
    cli_path = Path(str(config.get("cli_path") or "")).expanduser()
    auth_dir = Path(str(config.get("auth_config_dir") or "")).expanduser()
    if not cli_path.is_file():
        result = {
            "ok": False,
            "state": "missing_cli",
            "last_error": "official WeCom CLI is not installed",
        }
        write_status(status_path, result)
        return result
    auth_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = {**os.environ, "WECOM_CLI_CONFIG_DIR": str(auth_dir.resolve())}
    process = subprocess.Popen(
        [str(cli_path), "init", "--noninteractive", "--no-open"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    qr_url = read_qr_url(process)
    if not qr_url:
        stop_process(process)
        result = {
            "ok": False,
            "state": "authorization_failed",
            "last_error": "WeCom CLI did not return an authorization URL",
        }
        write_status(status_path, result)
        return result
    try:
        page_id = open_cdp_tab(qr_url, cdp_port)
    except (error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        stop_process(process)
        result = {
            "ok": False,
            "state": "authorization_browser_failed",
            "last_error": f"{type(exc).__name__}: {str(exc)[:160]}",
        }
        write_status(status_path, result)
        return result

    waiting = {
        "state": "waiting_for_qr_scan",
        "last_error": "",
        "qr_fingerprint": hashlib.sha256(qr_url.encode("utf-8")).hexdigest()[:16],
        "page_id": page_id,
        "novnc_url": admin_novnc_url(),
    }
    write_status(status_path, waiting)
    try:
        returncode = process.wait()
    except KeyboardInterrupt:
        stop_process(process)
        result = {
            "ok": True,
            "stopped": True,
            "state": "authorization_stopped",
            "last_error": "",
            "novnc_url": admin_novnc_url(),
        }
        write_status(status_path, result)
        return result
    ready = profile_ready(config)
    result = {
        "ok": returncode == 0 and ready,
        "state": "authorized" if returncode == 0 and ready else "authorization_expired",
        "returncode": returncode,
        "last_error": (
            ""
            if returncode == 0 and ready
            else "authorization was not completed before the official QR expired"
        ),
        "novnc_url": admin_novnc_url(),
    }
    write_status(status_path, result)
    return result


def read_qr_url(process: subprocess.Popen[str]) -> str:
    if process.stdout is None:
        return ""
    for line in process.stdout:
        match = re.search(r"https://work\.weixin\.qq\.com/ai/qc/gen\?[^\s]+", line)
        if not match:
            continue
        url = match.group(0).strip()
        return url if url.startswith(QR_PREFIX) else ""
    return ""


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def install_signal_handlers() -> None:
    def interrupt(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)


def open_cdp_tab(url: str, port: int) -> str:
    if not url.startswith(QR_PREFIX):
        raise ValueError("unexpected WeCom QR URL")
    with request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
        pages = json.loads(response.read().decode("utf-8"))
    for page in pages if isinstance(pages, list) else []:
        if "/ai/qc/gen" not in str(page.get("url") or ""):
            continue
        page_id = str(page.get("id") or "")
        if not page_id:
            continue
        try:
            with request.urlopen(f"http://127.0.0.1:{port}/json/close/{page_id}", timeout=5):
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


def write_status(path: Path, updates: dict[str, Any]) -> None:
    current: dict[str, Any] = {}
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                current = value
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(updates)
    current["last_transition"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)


def admin_novnc_url() -> str:
    port = os.environ.get("WECOM_ADMIN_NOVNC_PORT", "6133")
    return f"http://127.0.0.1:{port}/vnc.html?host=127.0.0.1&port={port}&autoconnect=1&resize=scale"


if __name__ == "__main__":
    raise SystemExit(main())
