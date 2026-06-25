#!/usr/bin/env python3
"""Small private registry for reusable Codex exec sessions per WeChat group."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from file_lock import fcntl_compat as fcntl


ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
SESSION_DIR = PRIVATE / "codex_sessions"
DEFAULT_REGISTRY = SESSION_DIR / "sessions.local.json"
SESSION_KEY_VERSION = "v2"
SESSION_KEY_DIGEST_LENGTH = 12
CURRENT_SESSION_KEY_RE = re.compile(r"^v2:[0-9a-z_.-]+-[0-9a-f]{12}:[0-9a-z_.-]+$")


def run_codex_session(
    prompt: str,
    *,
    chat_name: str,
    role: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path = ROOT,
    reuse: bool = True,
    registry_path: Path = DEFAULT_REGISTRY,
) -> dict[str, Any]:
    """Run Codex, resuming the remembered chat/role thread when available."""
    if os.environ.get("WECHAT_CODEX_REUSE_SESSIONS", "1") == "0":
        reuse = False
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = registry_path.with_suffix(".lock")
    key = session_key(chat_name, role)
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        registry = load_registry(registry_path)
        previous_id = str(registry.get(key, {}).get("thread_id") or "") if reuse else ""
        result = run_codex_once(
            prompt,
            thread_id=previous_id,
            model=model,
            reasoning_effort=reasoning_effort,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
        )
        if previous_id and not result["ok"] and result.get("returncode") != 124:
            fallback = run_codex_once(
                prompt,
                thread_id="",
                model=model,
                reasoning_effort=reasoning_effort,
                sandbox=sandbox,
                timeout_seconds=timeout_seconds,
                workdir=workdir,
            )
            fallback["resumed"] = False
            fallback["fallback_started"] = True
            result = fallback
        else:
            result["resumed"] = bool(previous_id)
            result["fallback_started"] = False
        if result.get("ok") and result.get("thread_id"):
            update_registry(registry, key, chat_name, role, result, model, reasoning_effort, sandbox, workdir)
            save_registry(registry_path, registry)
        fcntl.flock(lock, fcntl.LOCK_UN)
    return result


def run_codex_once(
    prompt: str,
    *,
    thread_id: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as out:
        output_path = Path(out.name)
    command = [
        "codex",
        "exec",
        "--json",
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--sandbox",
        sandbox,
        "-C",
        str(workdir),
        "-o",
        str(output_path),
    ]
    if thread_id:
        command += ["resume", thread_id, "-"]
    else:
        command.append("-")
    try:
        proc = subprocess.run(
            command,
            input=prompt,
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        message = output_path.read_text(encoding="utf-8", errors="replace").strip() if output_path.exists() else ""
        parsed_thread_id = parse_thread_id(proc.stdout) or thread_id
        return {
            "ok": proc.returncode == 0,
            "message": message,
            "thread_id": parsed_thread_id,
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-2000:],
            "stdout_tail": (proc.stdout or "")[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "message": "Codex failed: timed out before completing the turn.",
            "thread_id": thread_id,
            "returncode": 124,
            "stderr_tail": "timeout",
            "stdout_tail": "",
        }
    finally:
        output_path.unlink(missing_ok=True)


def parse_thread_id(events: str) -> str:
    for line in str(events or "").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("type") == "thread.started":
            return str(item.get("thread_id") or "")
    return ""


def session_key(chat_name: str, role: str) -> str:
    """Return a collision-resistant key for one exact WeChat chat and role."""
    chat_text = str(chat_name or "").strip()
    digest = hashlib.sha256(chat_text.encode("utf-8")).hexdigest()[:SESSION_KEY_DIGEST_LENGTH]
    return f"{SESSION_KEY_VERSION}:{safe_slug(chat_text)}-{digest}:{safe_slug(role)}"


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_.-]+", "-", str(value or "").strip()).strip("-").lower()
    return slug or "chat"


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: value
        for key, value in data.items()
        if CURRENT_SESSION_KEY_RE.fullmatch(str(key)) and isinstance(value, dict)
    }


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def update_registry(
    registry: dict[str, Any],
    key: str,
    chat_name: str,
    role: str,
    result: dict[str, Any],
    model: str,
    reasoning_effort: str,
    sandbox: str,
    workdir: Path,
) -> None:
    previous = registry.get(key, {}) if isinstance(registry.get(key), dict) else {}
    registry[key] = {
        "thread_id": result["thread_id"],
        "chat_name": chat_name,
        "role": role,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "sandbox": sandbox,
        "workdir": str(workdir),
        "created_at": previous.get("created_at") or datetime.now().isoformat(timespec="seconds"),
        "last_used_at": datetime.now().isoformat(timespec="seconds"),
        "turn_count": int(previous.get("turn_count") or 0) + 1,
        "last_resumed": bool(result.get("resumed")),
        "last_fallback_started": bool(result.get("fallback_started")),
    }
