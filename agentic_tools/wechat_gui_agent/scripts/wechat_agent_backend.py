"""Pluggable agent backend for WeChat chatops.

Codex remains the default. Claude Code is selected only by config/env and uses
the same chat/role separation expected by the current router and worker.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from typing import Any

from file_lock import exclusive_lock
from wechat_codex_sessions import DEFAULT_REGISTRY, ROOT, run_codex_session, session_key


PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
CLAUDE_SESSION_DIR = PRIVATE / "claude_sessions"
CLAUDE_REGISTRY = CLAUDE_SESSION_DIR / "sessions.local.json"
CLAUDE_READONLY_BLOCK = "Bash,Edit,Write,MultiEdit,NotebookEdit"


def select_agent_backend(config: dict[str, Any] | None = None) -> str:
    """Return `codex` or `claude`, defaulting to Codex for compatibility."""
    if isinstance(config, dict):
        value = config.get("agent_backend") or config.get("backend")
        if value:
            return normalize_backend(str(value))
    return normalize_backend(os.environ.get("WECHAT_AGENT_BACKEND") or "codex")


def normalize_backend(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "claude-code": "claude",
        "claude_code": "claude",
        "anthropic": "claude",
        "codex-cli": "codex",
        "openai": "codex",
    }
    return aliases.get(normalized, normalized if normalized in {"codex", "claude"} else "codex")


def backend_cli_name(backend: str) -> str:
    return "claude" if normalize_backend(backend) == "claude" else "codex"


def run_agent_session(
    prompt: str,
    *,
    backend: str,
    chat_name: str,
    role: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path = ROOT,
    reuse: bool = True,
    registry_path: Path = DEFAULT_REGISTRY,
    backend_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one backend turn and return the same shape as run_codex_session."""
    selected = normalize_backend(backend)
    if selected == "claude":
        claude_config = backend_config or {}
        return run_claude_session(
            prompt,
            chat_name=chat_name,
            role=role,
            model=model,
            sandbox=sandbox,
            timeout_seconds=configured_timeout(claude_config, role, timeout_seconds),
            workdir=workdir,
            reuse=reuse,
            backend_config=claude_config,
        )
    result = run_codex_session(
        prompt,
        chat_name=chat_name,
        role=role,
        model=model,
        reasoning_effort=reasoning_effort,
        sandbox=sandbox,
        timeout_seconds=timeout_seconds,
        workdir=workdir,
        reuse=reuse,
        registry_path=registry_path,
    )
    result["backend"] = "codex"
    return result


def run_claude_session(
    prompt: str,
    *,
    chat_name: str,
    role: str,
    model: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path,
    reuse: bool,
    backend_config: dict[str, Any],
) -> dict[str, Any]:
    session_id = claude_session_id(chat_name, role) if reuse else ""
    command = claude_command(
        role=role,
        model=claude_model(model, role=role, backend_config=backend_config),
        sandbox=sandbox,
        session_id=session_id,
        backend_config=backend_config,
    )
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
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "message": "Claude failed: timed out before completing the turn.",
            "thread_id": session_id,
            "returncode": 124,
            "stderr_tail": "timeout",
            "stdout_tail": "",
            "resumed": bool(session_id),
            "fallback_started": False,
            "backend": "claude",
        }
    message = (proc.stdout or "").strip()
    result = {
        "ok": proc.returncode == 0,
        "message": message,
        "thread_id": session_id,
        "returncode": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-2000:],
        "stdout_tail": (proc.stdout or "")[-2000:],
        "resumed": bool(session_id),
        "fallback_started": False,
        "backend": "claude",
    }
    if result["ok"] and session_id:
        update_claude_registry(chat_name, role, session_id, model, sandbox, workdir)
    return result


def claude_command(
    *,
    role: str,
    model: str,
    sandbox: str,
    session_id: str,
    backend_config: dict[str, Any],
) -> list[str]:
    binary = str(backend_config.get("bin") or os.environ.get("WECHAT_CLAUDE_BIN") or "claude")
    command = [binary, "--print", "--output-format", "text"]
    if model:
        command.extend(["--model", model])
    if session_id:
        command.extend(["--session-id", session_id])
    permission_mode = str(
        backend_config.get("permission_mode")
        or os.environ.get("WECHAT_CLAUDE_PERMISSION_MODE")
        or "bypassPermissions"
    ).strip()
    if permission_mode:
        command.extend(["--permission-mode", permission_mode])
    if sandbox == "read-only" or role in {"route", "fast"}:
        disallowed = str(
            backend_config.get("readonly_disallowed_tools")
            or os.environ.get("WECHAT_CLAUDE_READONLY_DISALLOWED_TOOLS")
            or CLAUDE_READONLY_BLOCK
        ).strip()
        if disallowed:
            command.extend(["--disallowedTools", disallowed])
    extra_args = backend_config.get("extra_args")
    if isinstance(extra_args, list):
        command.extend(str(item) for item in extra_args if str(item).strip())
    return command


def claude_model(codex_model: str, *, role: str, backend_config: dict[str, Any]) -> str:
    env_role = os.environ.get(f"WECHAT_CLAUDE_{role.upper()}_MODEL")
    configured = (
        backend_config.get(f"{role}_model")
        or backend_config.get("model")
        or env_role
        or os.environ.get("WECHAT_CLAUDE_MODEL")
        or ""
    )
    model = str(configured or "").strip()
    if model:
        return model
    # Codex model ids are not valid Claude model ids; leave model unset so the
    # installed Claude Code default applies.
    return "" if str(codex_model or "").startswith("gpt-") else str(codex_model or "").strip()


def configured_timeout(backend_config: dict[str, Any], role: str, fallback: int) -> int:
    raw = backend_config.get(f"{role}_timeout_seconds") or backend_config.get("timeout_seconds")
    if raw is None:
        return int(fallback)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return int(fallback)


def claude_session_id(chat_name: str, role: str) -> str:
    key = session_key(chat_name, role)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"labcanvas-wechat:{key}"))


def update_claude_registry(chat_name: str, role: str, session_id: str, model: str, sandbox: str, workdir: Path) -> None:
    CLAUDE_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = CLAUDE_REGISTRY.with_suffix(".lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        with exclusive_lock(lock):
            registry = load_json_dict(CLAUDE_REGISTRY)
            key = session_key(chat_name, role)
            previous = registry.get(key, {}) if isinstance(registry.get(key), dict) else {}
            registry[key] = {
                "thread_id": session_id,
                "chat_name": chat_name,
                "role": role,
                "model": model,
                "sandbox": sandbox,
                "workdir": str(workdir),
                "created_at": previous.get("created_at") or datetime.now().isoformat(timespec="seconds"),
                "last_used_at": datetime.now().isoformat(timespec="seconds"),
                "turn_count": int(previous.get("turn_count") or 0) + 1,
            }
            CLAUDE_REGISTRY.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            CLAUDE_REGISTRY.chmod(0o600)


def load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def backend_available(backend: str) -> str:
    selected = normalize_backend(backend)
    if selected == "claude":
        return shutil.which(os.environ.get("WECHAT_CLAUDE_BIN") or "claude") or ""
    return shutil.which("codex") or ""
