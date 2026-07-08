"""Pluggable agent backend for WeChat chatops.

Codex remains the default. Claude Code is selected only by config/env and uses
the same chat/role separation expected by the current router and worker.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import uuid
from typing import Any

from file_lock import exclusive_lock
from wechat_codex_sessions import DEFAULT_REGISTRY, ROOT, resolve_codex_binary, run_codex_session, session_key


PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
CLAUDE_SESSION_DIR = PRIVATE / "claude_sessions"
CLAUDE_REGISTRY = CLAUDE_SESSION_DIR / "sessions.local.json"
CLAUDE_READONLY_BLOCK = "Bash,Edit,Write,MultiEdit,NotebookEdit"
DEFAULT_FALLBACK_MODEL = "gpt-5.5"
DEFAULT_FALLBACK_REASONING_EFFORT = "low"
QUOTA_FAILURE_MARKERS = (
    "429",
    "billing hard limit",
    "capacity",
    "credit balance",
    "credits exhausted",
    "insufficient_quota",
    "model quota",
    "out of quota",
    "quota",
    "rate limit",
    "rate_limit",
    "resource_exhausted",
    "too many requests",
    "usage limit",
)
UNAVAILABLE_FAILURE_MARKERS = (
    "command not found",
    "connection refused",
    "could not connect",
    "executable not found",
    "executable was not found",
    "no such file or directory",
    "not found in path",
    "service unavailable",
    "temporarily unavailable",
)


def select_agent_backend(config: dict[str, Any] | None = None) -> str:
    """Return the selected agent backend, defaulting to Codex."""
    if isinstance(config, dict):
        value = config.get("agent_backend") or config.get("backend")
        if value:
            return normalize_backend(str(value))
    return normalize_backend(os.environ.get("WECHAT_AGENT_BACKEND") or "codex")


def normalize_backend(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "aginti-flow": "aginti",
        "agintiflow": "aginti",
        "labcanvas": "aginti",
        "claude-code": "claude",
        "claude_code": "claude",
        "anthropic": "claude",
        "codex-cli": "codex",
        "openai": "codex",
    }
    return aliases.get(normalized, normalized if normalized in {"codex", "claude", "aginti"} else "codex")


def backend_cli_name(backend: str) -> str:
    selected = normalize_backend(backend)
    if selected == "claude":
        return "claude"
    if selected == "aginti":
        return "aginti"
    return "codex"


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
    """Run one backend turn with system-level quota/unavailable fallback."""
    selected = normalize_backend(backend)
    config = backend_config or {}
    attempt = {
        "backend": selected,
        "model": str(model or ""),
        "reasoning_effort": str(reasoning_effort or ""),
        "sandbox": sandbox,
        "timeout_seconds": int(timeout_seconds),
    }
    attempt_summaries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    while True:
        signature = (
            str(attempt["backend"]),
            str(attempt.get("model") or ""),
            str(attempt.get("reasoning_effort") or ""),
        )
        if signature in seen:
            result = {
                "ok": False,
                "message": "Agent backend failed: fallback plan loop detected.",
                "thread_id": "",
                "returncode": 1,
                "stderr_tail": "fallback plan loop detected",
                "stdout_tail": "",
                "backend": str(attempt["backend"]),
                "model": str(attempt.get("model") or ""),
            }
            return attach_attempt_summary(result, attempt_summaries)
        seen.add(signature)
        result = run_single_backend_attempt(
            prompt,
            attempt=attempt,
            primary_backend=selected,
            chat_name=chat_name,
            role=role,
            workdir=workdir,
            reuse=reuse,
            registry_path=registry_path,
            backend_config=config,
        )
        attempt_summaries.append(summarize_attempt(attempt, result))
        if result.get("ok"):
            return attach_attempt_summary(result, attempt_summaries)
        next_attempt = next_backend_attempt(attempt, result, backend_config=config)
        if next_attempt is None:
            return attach_attempt_summary(result, attempt_summaries)
        attempt = next_attempt


def run_single_backend_attempt(
    prompt: str,
    *,
    attempt: dict[str, Any],
    primary_backend: str,
    chat_name: str,
    role: str,
    workdir: Path,
    reuse: bool,
    registry_path: Path,
    backend_config: dict[str, Any],
) -> dict[str, Any]:
    selected = normalize_backend(str(attempt.get("backend") or "codex"))
    selected_config = backend_specific_config(backend_config, selected, primary_backend=primary_backend)
    model = str(attempt.get("model") or "")
    reasoning_effort = str(attempt.get("reasoning_effort") or "")
    timeout_seconds = int(attempt.get("timeout_seconds") or 1)
    sandbox = str(attempt.get("sandbox") or "read-only")
    if selected == "claude":
        result = run_claude_session(
            prompt,
            chat_name=chat_name,
            role=role,
            model=model,
            sandbox=sandbox,
            timeout_seconds=configured_timeout(selected_config, role, timeout_seconds),
            workdir=workdir,
            reuse=reuse,
            backend_config=selected_config,
        )
    elif selected == "aginti":
        result = run_aginti_session(
            prompt,
            chat_name=chat_name,
            role=role,
            model=model,
            reasoning_effort=reasoning_effort,
            sandbox=sandbox,
            timeout_seconds=configured_timeout(selected_config, role, timeout_seconds),
            workdir=workdir,
            backend_config=selected_config,
        )
    else:
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
    result["backend"] = selected
    result["model"] = model
    result["reasoning_effort"] = reasoning_effort
    return result


def backend_specific_config(config: dict[str, Any], backend: str, *, primary_backend: str) -> dict[str, Any]:
    selected = normalize_backend(backend)
    merged: dict[str, Any] = {}
    for key in ("_backends", "backends", "backend_configs"):
        container = config.get(key)
        if isinstance(container, dict):
            raw = container.get(selected)
            if isinstance(raw, dict):
                merged.update(raw)
    if selected == normalize_backend(primary_backend):
        meta_keys = {
            "_backends",
            "backends",
            "backend_configs",
            "fallbacks",
            "agent_fallbacks",
            "backend_fallbacks",
        }
        merged.update({key: value for key, value in config.items() if key not in meta_keys})
    for key in ("fallbacks", "agent_fallbacks", "backend_fallbacks"):
        if key in config:
            merged.setdefault(key, config[key])
    return merged


def next_backend_attempt(
    attempt: dict[str, Any],
    result: dict[str, Any],
    *,
    backend_config: dict[str, Any],
) -> dict[str, Any] | None:
    if not backend_fallbacks_enabled(backend_config):
        return None
    failure_kind = classify_backend_failure(result)
    if failure_kind not in {"quota", "unavailable"}:
        return None
    backend = normalize_backend(str(attempt.get("backend") or "codex"))
    if backend == "codex" and is_spark_model(str(attempt.get("model") or "")) and failure_kind == "quota":
        return {
            **attempt,
            "backend": "codex",
            "model": fallback_model(backend_config),
            "reasoning_effort": fallback_reasoning_effort(backend_config),
            "fallback_reason": "spark_quota",
        }
    if backend != "aginti" and fallback_to_aginti_enabled(backend_config):
        aginti_config = backend_specific_config(backend_config, "aginti", primary_backend=backend)
        return {
            **attempt,
            "backend": "aginti",
            "model": str(aginti_config.get("model") or aginti_config.get("agent_model") or "aginti"),
            "reasoning_effort": str(aginti_config.get("reasoning_effort") or attempt.get("reasoning_effort") or "low"),
            "timeout_seconds": configured_timeout(
                aginti_config,
                str(attempt.get("role") or ""),
                int(attempt.get("timeout_seconds") or 60),
            ),
            "fallback_reason": f"{backend}_{failure_kind}",
        }
    return None


def backend_fallbacks_enabled(config: dict[str, Any]) -> bool:
    if os.environ.get("WECHAT_AGENT_BACKEND_FALLBACKS", "1") == "0":
        return False
    fallback_config = fallback_config_dict(config)
    return bool(fallback_config.get("enabled", True))


def fallback_to_aginti_enabled(config: dict[str, Any]) -> bool:
    fallback_config = fallback_config_dict(config)
    return bool(
        fallback_config.get(
            "aginti_enabled",
            fallback_config.get("fallback_to_aginti", True),
        )
    )


def fallback_model(config: dict[str, Any]) -> str:
    fallback_config = fallback_config_dict(config)
    return str(
        fallback_config.get("codex_model")
        or fallback_config.get("quota_fallback_model")
        or os.environ.get("WECHAT_CODEX_QUOTA_FALLBACK_MODEL")
        or DEFAULT_FALLBACK_MODEL
    )


def fallback_reasoning_effort(config: dict[str, Any]) -> str:
    fallback_config = fallback_config_dict(config)
    return str(
        fallback_config.get("codex_reasoning_effort")
        or fallback_config.get("quota_fallback_reasoning_effort")
        or os.environ.get("WECHAT_CODEX_QUOTA_FALLBACK_EFFORT")
        or DEFAULT_FALLBACK_REASONING_EFFORT
    )


def fallback_config_dict(config: dict[str, Any]) -> dict[str, Any]:
    for key in ("fallbacks", "agent_fallbacks", "backend_fallbacks"):
        raw = config.get(key)
        if isinstance(raw, dict):
            return raw
    return {}


def is_spark_model(model: str) -> bool:
    return "spark" in str(model or "").lower()


def classify_backend_failure(result: dict[str, Any]) -> str:
    if result.get("ok"):
        return ""
    if int(result.get("returncode") or 0) == 124:
        return "timeout"
    text = " ".join(
        str(result.get(key) or "")
        for key in ("message", "stderr_tail", "stdout_tail", "error", "reason")
    ).casefold()
    if any(marker in text for marker in QUOTA_FAILURE_MARKERS):
        return "quota"
    if int(result.get("returncode") or 0) == 127 or any(marker in text for marker in UNAVAILABLE_FAILURE_MARKERS):
        return "unavailable"
    return "other"


def summarize_attempt(attempt: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend": normalize_backend(str(attempt.get("backend") or "")),
        "model": str(attempt.get("model") or ""),
        "reasoning_effort": str(attempt.get("reasoning_effort") or ""),
        "fallback_reason": str(attempt.get("fallback_reason") or ""),
        "ok": bool(result.get("ok")),
        "failure_kind": classify_backend_failure(result),
        "returncode": result.get("returncode"),
        "stderr_tail": str(result.get("stderr_tail") or "")[-500:],
    }


def attach_attempt_summary(result: dict[str, Any], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    if attempts:
        result["backend_attempts"] = attempts
        result["backend_fallback_used"] = len(attempts) > 1
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


def run_aginti_session(
    prompt: str,
    *,
    chat_name: str,
    role: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path,
    backend_config: dict[str, Any],
) -> dict[str, Any]:
    command = aginti_command(model=model, role=role, backend_config=backend_config)
    if not command:
        return {
            "ok": False,
            "message": "AgInTi failed: command is empty.",
            "thread_id": "",
            "returncode": 127,
            "stderr_tail": "aginti command is empty",
            "stdout_tail": "",
            "resumed": False,
            "fallback_started": False,
            "backend": "aginti",
        }
    executable = command[0]
    if not command_available(executable):
        return {
            "ok": False,
            "message": f"AgInTi failed: command not found: {executable}",
            "thread_id": "",
            "returncode": 127,
            "stderr_tail": f"command not found: {executable}",
            "stdout_tail": "",
            "resumed": False,
            "fallback_started": False,
            "backend": "aginti",
        }
    aginti_workdir = aginti_workdir_from_config(backend_config, workdir)
    wrapped_prompt = aginti_prompt(
        prompt,
        chat_name=chat_name,
        role=role,
        model=model,
        reasoning_effort=reasoning_effort,
        sandbox=sandbox,
        backend_config=backend_config,
    )
    prompt_mode = str(backend_config.get("prompt_mode") or os.environ.get("WECHAT_AGINTI_PROMPT_MODE") or "stdin").strip()
    run_command = list(command)
    stdin_text = wrapped_prompt
    if prompt_mode == "arg":
        run_command.append(wrapped_prompt)
        stdin_text = None
    try:
        proc = subprocess.run(
            run_command,
            input=stdin_text,
            cwd=aginti_workdir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "message": "AgInTi failed: timed out before completing the turn.",
            "thread_id": "",
            "returncode": 124,
            "stderr_tail": "timeout",
            "stdout_tail": "",
            "resumed": False,
            "fallback_started": False,
            "backend": "aginti",
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "message": f"AgInTi failed: executable not found: {exc.filename or executable}",
            "thread_id": "",
            "returncode": 127,
            "stderr_tail": str(exc),
            "stdout_tail": "",
            "resumed": False,
            "fallback_started": False,
            "backend": "aginti",
        }
    message = (proc.stdout or "").strip()
    if not message and proc.returncode != 0:
        message = (proc.stderr or "").strip()
    return {
        "ok": proc.returncode == 0,
        "message": message,
        "thread_id": "",
        "returncode": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-2000:],
        "stdout_tail": (proc.stdout or "")[-2000:],
        "resumed": False,
        "fallback_started": False,
        "backend": "aginti",
    }


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


def aginti_command(*, model: str, role: str, backend_config: dict[str, Any]) -> list[str]:
    raw_command = (
        backend_config.get("command")
        or backend_config.get("bin")
        or os.environ.get("WECHAT_AGINTI_COMMAND")
        or "aginti"
    )
    if isinstance(raw_command, list):
        command = [str(item) for item in raw_command if str(item).strip()]
    else:
        command = shlex.split(str(raw_command))
    if not command:
        return []
    raw_args = backend_config.get("args")
    if raw_args is None:
        raw_args = os.environ.get("WECHAT_AGINTI_ARGS") or "agent run --stdin"
    if isinstance(raw_args, list):
        command.extend(str(item) for item in raw_args if str(item).strip())
    else:
        command.extend(shlex.split(str(raw_args)))
    if bool(backend_config.get("pass_role", False)):
        command.extend(["--role", role])
    configured_model = str(backend_config.get("model") or model or "").strip()
    if configured_model and bool(backend_config.get("pass_model_arg", False)):
        command.extend(["--model", configured_model])
    return command


def aginti_workdir_from_config(backend_config: dict[str, Any], fallback: Path) -> Path:
    raw = str(backend_config.get("workspace") or os.environ.get("WECHAT_AGINTI_WORKSPACE") or "").strip()
    if not raw:
        return fallback
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (fallback / path).resolve()
    return path if path.exists() else fallback


def aginti_prompt(
    prompt: str,
    *,
    chat_name: str,
    role: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    backend_config: dict[str, Any],
) -> str:
    if not bool(backend_config.get("wrap_prompt", True)):
        return prompt
    return f"""You are AgInTi acting as a fallback backend for LabCanvas WeChat automation.
Preserve the requested output shape exactly. If the original prompt asks for JSON, return only valid JSON. If it asks for CHAT:/ACK:/TASK:, follow that protocol.
Use the same source-isolation, safety, artifact-return, and chat-purpose rules in the original prompt. Do not invent unavailable files or claim browser/platform work completed without evidence.
If you cannot complete the task from the available local tools/context, return a concise blocker and the exact next action.

Chat: {chat_name}
Role: {role}
Requested model: {model}
Reasoning effort: {reasoning_effort}
Sandbox: {sandbox}

Original prompt:
{prompt}
"""


def command_available(executable: str) -> bool:
    if not executable:
        return False
    if "/" in executable:
        path = Path(executable).expanduser()
        return path.exists() and os.access(path, os.X_OK)
    return shutil.which(executable) is not None


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
    return resolve_codex_binary()
