"""Pluggable agent backend for WeChat chatops.

Codex remains the default. Claude Code is selected only by config/env and uses
the same chat/role separation expected by the current router and worker.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import uuid
from typing import Any

from codex_quota_status import (
    codex_credits_available,
    current_status as current_codex_quota_status,
)
from file_lock import exclusive_lock
from wechat_codex_sessions import (
    DEFAULT_REGISTRY,
    ROOT,
    resolve_codex_binary,
    run_codex_session,
    run_process_group,
    session_key,
)


PRIVATE = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private"
CLAUDE_SESSION_DIR = PRIVATE / "claude_sessions"
CLAUDE_REGISTRY = CLAUDE_SESSION_DIR / "sessions.local.json"
CLAUDE_READONLY_BLOCK = "Bash,Edit,Write,MultiEdit,NotebookEdit"
DEFAULT_FALLBACK_MODEL = "gpt-5.6-sol"
DEFAULT_FALLBACK_REASONING_EFFORT = "low"
DEFAULT_LOW_QUOTA_SPARK_MODEL = "gpt-5.3-codex-spark"
DEFAULT_LOW_QUOTA_THRESHOLD_PERCENT = 25.0
LOW_QUOTA_SPARK_ROLES = frozenset({"fast", "route"})
AGINTI_SESSION_RE = re.compile(r"^Session:\s*(web-agent-[0-9A-Za-z-]+)\s*$", re.MULTILINE)
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
BACKEND_METADATA_LINE_RE = re.compile(
    r"^(?:Session|Provider|Model|Routing|Workspace|Sessions|Project session index|"
    r"Docker|Docker workspace|Docker env|Shell|Step budget|Surgical context):\s*.+$",
    re.IGNORECASE,
)
BARE_BACKEND_SESSION_RE = re.compile(
    r"^(?:web-agent-[0-9A-Za-z-]+|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$",
    re.IGNORECASE,
)
AGINTI_INTERNAL_REPORT_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:"
    r"scs(?:\s+hard)?\s+contract|definitive\s+blocker|internal\s+(?:plan|report)|"
    r"validator\s+(?:report|contract)|runtime\s+(?:report|contract)"
    r")\b"
)
AGINTI_INTERNAL_OUTPUT_LINE_RE = re.compile(
    r"(?im)^\s*(?:tool|output|artifact|step budget|surgical context)\s*:\s*.+$"
)
GENERIC_EXECUTION_EVIDENCE_REFUSAL_RE = re.compile(
    r"I could not verify that the requested action was executed.*?"
    r"Missing evidence categories:.*?"
    r"Retry with an enabled execution tool",
    re.IGNORECASE | re.DOTALL,
)
AGINTI_MANAGED_VALUE_ARGS = {
    "-s",
    "--safety",
    "--permission-mode",
    "--sandbox-mode",
    "--package-install-policy",
    "--task-profile",
    "--profile",
    "--cwd",
    "--scout-count",
    "--wrapper",
    "--preferred-wrapper",
}
AGINTI_MANAGED_FLAG_ARGS = {
    "--approve-package-installs",
    "--allow-shell",
    "--no-shell",
    "--allow-destructive",
    "--trusted-host-shell",
    "--allow-file-tools",
    "--allow-files",
    "--no-file-tools",
    "--no-files",
    "--allow-auxiliary-tools",
    "--allow-auxiliary",
    "--no-auxiliary-tools",
    "--no-auxiliary",
    "--mcp",
    "--allow-mcp",
    "--allow-mcp-tools",
    "--no-mcp",
    "--no-mcp-tools",
    "--parallel-scouts",
    "--no-parallel-scouts",
    "--allow-wrappers",
    "--docker-sandbox",
    "--scs",
    "--enable-scs",
    "--disable-scs",
    "--no-scs",
    "--web",
    "--chat",
    "--interactive",
}
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
MODEL_FAILURE_MARKERS = (
    "unknown model",
    "model not found",
    "invalid model",
    "unsupported model",
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
    fallback_model: str = "",
    fallback_reasoning_effort: str = "",
) -> dict[str, Any]:
    """Run one backend turn with system-level quota/unavailable fallback."""
    selected = normalize_backend(backend)
    config = backend_config or {}
    preferred_model, preferred_effort, quota_preference = quota_aware_codex_preference(
        backend=selected,
        model=model,
        reasoning_effort=reasoning_effort,
        role=role,
        backend_config=config,
    )
    attempt = {
        "backend": selected,
        "model": preferred_model,
        "reasoning_effort": preferred_effort,
        "sandbox": sandbox,
        "timeout_seconds": int(timeout_seconds),
        "role": role,
        "fallback_model": fallback_model,
        "fallback_reasoning_effort": fallback_reasoning_effort,
    }
    if quota_preference:
        attempt["quota_preference"] = quota_preference
    attempt_summaries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, bool]] = set()
    while True:
        signature = (
            str(attempt["backend"]),
            str(attempt.get("model") or ""),
            str(attempt.get("reasoning_effort") or ""),
            bool(attempt.get("credit_retry")),
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
        usable_message = user_facing_backend_message(result.get("message"))
        if (
            result.get("ok")
            and str(role or "").strip().casefold() in {"fast", "route"}
            and is_generic_execution_evidence_refusal(usable_message)
        ):
            result = {
                **result,
                "ok": False,
                "message": "",
                "reason": "invalid_conversational_evidence_refusal",
                "returncode": int(result.get("returncode") or 1),
                "stderr_tail": (
                    "Conversational fallback returned a generic execution-evidence "
                    "refusal instead of the requested chat or routing response."
                ),
            }
            usable_message = ""
        if result.get("ok") and usable_message:
            result["message"] = usable_message
            attempt_summaries.append(summarize_attempt(attempt, result))
            return attach_attempt_summary(result, attempt_summaries)
        if result.get("ok"):
            raw_message = str(result.get("message") or "")
            result = {
                **result,
                "ok": False,
                "message": "",
                "returncode": int(result.get("returncode") or 1),
                "reason": "empty_response",
                "stderr_tail": str(
                    result.get("stderr_tail")
                    or (
                        "Agent backend returned only internal runtime metadata."
                        if raw_message.strip()
                        else "Agent backend returned an empty response."
                    )
                ),
            }
        attempt_summaries.append(summarize_attempt(attempt, result))
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
    raw_top_level = config.get(selected)
    if isinstance(raw_top_level, dict):
        merged.update(raw_top_level)
    if selected == normalize_backend(primary_backend):
        meta_keys = {
            "_backends",
            "backends",
            "backend_configs",
            "fallbacks",
            "agent_fallbacks",
            "backend_fallbacks",
            "codex",
            "claude",
            "aginti",
        }
        merged.update({key: value for key, value in config.items() if key not in meta_keys})
    for key in ("fallbacks", "agent_fallbacks", "backend_fallbacks"):
        if key in config:
            merged.setdefault(key, config[key])
    return merged


def quota_aware_codex_preference(
    *,
    backend: str,
    model: str,
    reasoning_effort: str,
    role: str,
    backend_config: dict[str, Any],
) -> tuple[str, str, dict[str, Any] | None]:
    """Prefer Spark for automatic lightweight turns when normal quota is low.

    The decision is cache-only. A stale or missing quota snapshot leaves the
    caller's model unchanged, so routing never waits for a quota probe.
    """
    selected_model = str(model or "")
    selected_effort = str(reasoning_effort or "")
    if normalize_backend(backend) != "codex" or is_spark_model(selected_model):
        return selected_model, selected_effort, None
    fallback_config = fallback_config_dict(backend_config)
    enabled = fallback_config.get("prefer_spark_below_normal_quota")
    if enabled is None:
        enabled = str(role or "") in LOW_QUOTA_SPARK_ROLES
    if not bool(enabled):
        return selected_model, selected_effort, None
    configured_roles = fallback_config.get("low_quota_spark_roles")
    if isinstance(configured_roles, (list, tuple, set)):
        allowed_roles = {str(value).strip() for value in configured_roles if str(value).strip()}
        if allowed_roles and str(role or "") not in allowed_roles:
            return selected_model, selected_effort, None
    try:
        threshold = float(
            fallback_config.get("low_quota_threshold_percent")
            or os.environ.get("WECHAT_CODEX_SPARK_THRESHOLD_PERCENT")
            or DEFAULT_LOW_QUOTA_THRESHOLD_PERCENT
        )
        status = current_codex_quota_status(
            max_age_seconds=float(
                fallback_config.get("low_quota_cache_max_age_seconds") or 600
            ),
            threshold_percent=threshold,
            refresh=False,
        )
        remaining = float(status.get("remaining_percent"))
    except (TypeError, ValueError, OSError):
        return selected_model, selected_effort, None
    if not status.get("ok") or remaining >= threshold:
        return selected_model, selected_effort, None
    spark_model = str(
        fallback_config.get("low_quota_spark_model")
        or os.environ.get("WECHAT_CODEX_LOW_QUOTA_MODEL")
        or DEFAULT_LOW_QUOTA_SPARK_MODEL
    )
    spark_effort = str(
        fallback_config.get("low_quota_spark_reasoning_effort")
        or os.environ.get("WECHAT_CODEX_LOW_QUOTA_EFFORT")
        or "low"
    )
    return (
        spark_model,
        spark_effort,
        {
            "reason": "normal_codex_quota_below_threshold",
            "remaining_percent": remaining,
            "threshold_percent": threshold,
            "requested_model": selected_model,
        },
    )


def next_backend_attempt(
    attempt: dict[str, Any],
    result: dict[str, Any],
    *,
    backend_config: dict[str, Any],
) -> dict[str, Any] | None:
    if not backend_fallbacks_enabled(backend_config):
        return None
    failure_kind = classify_backend_failure(result)
    if failure_kind not in {"quota", "unavailable", "timeout", "empty", "model_unavailable"}:
        return None
    backend = normalize_backend(str(attempt.get("backend") or "codex"))
    if backend == "codex" and failure_kind == "model_unavailable":
        preferred_fallback = str(attempt.get("fallback_model") or fallback_model(backend_config))
        if preferred_fallback and preferred_fallback != str(attempt.get("model") or ""):
            return {
                **attempt,
                "backend": "codex",
                "model": preferred_fallback,
                "reasoning_effort": str(attempt.get("fallback_reasoning_effort") or attempt.get("reasoning_effort") or "low"),
                "fallback_reason": "preferred_model_unavailable",
                "model_fallback_used": True,
            }
    if backend == "codex" and is_spark_model(str(attempt.get("model") or "")) and failure_kind in {"quota", "empty"}:
        return {
            **attempt,
            "backend": "codex",
            "model": fallback_model(backend_config),
            "reasoning_effort": fallback_reasoning_effort(backend_config),
            "fallback_reason": f"spark_{failure_kind}",
        }
    if (
        backend == "codex"
        and failure_kind == "quota"
        and not bool(attempt.get("credit_retry"))
        and codex_credit_retry_enabled(backend_config)
        and purchased_codex_credits_available()
    ):
        return {
            **attempt,
            "credit_retry": True,
            "fallback_reason": "codex_purchased_credit_retry",
        }
    if backend != "aginti" and failure_kind == "timeout" and not fallback_on_timeout_enabled(backend_config):
        return None
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


def fallback_on_timeout_enabled(config: dict[str, Any]) -> bool:
    fallback_config = fallback_config_dict(config)
    return bool(
        fallback_config.get(
            "timeout_enabled",
            fallback_config.get("fallback_on_timeout", True),
        )
    )


def codex_credit_retry_enabled(config: dict[str, Any]) -> bool:
    fallback_config = fallback_config_dict(config)
    return bool(fallback_config.get("purchased_credit_retry", True))


def purchased_codex_credits_available() -> bool:
    try:
        return codex_credits_available(
            current_codex_quota_status(
                max_age_seconds=300,
                refresh=True,
            )
        )
    except Exception:
        return False


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
    if str(result.get("reason") or "") in {
        "empty_response",
        "invalid_conversational_evidence_refusal",
    }:
        return "empty"
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
    if any(marker in text for marker in MODEL_FAILURE_MARKERS):
        return "model_unavailable"
    if int(result.get("returncode") or 0) == 127 or any(marker in text for marker in UNAVAILABLE_FAILURE_MARKERS):
        return "unavailable"
    return "other"


def backend_result_has_content(result: dict[str, Any]) -> bool:
    return bool(user_facing_backend_message(result.get("message")))


def user_facing_backend_message(value: Any) -> str:
    """Return chat-safe agent content, rejecting runtime identifiers alone."""
    text = ANSI_ESCAPE_RE.sub("", str(value or "")).strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1 and (
        AGINTI_SESSION_RE.fullmatch(lines[0]) or BARE_BACKEND_SESSION_RE.fullmatch(lines[0])
    ):
        return ""
    if all(BACKEND_METADATA_LINE_RE.fullmatch(line) or line in {"Plan:", "Output:"} for line in lines):
        return ""
    return text


def is_generic_execution_evidence_refusal(value: Any) -> bool:
    """Detect AgInTi's task-execution guard leaking into conversational roles."""

    return bool(GENERIC_EXECUTION_EVIDENCE_REFUSAL_RE.search(str(value or "")))


def summarize_attempt(attempt: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend": normalize_backend(str(attempt.get("backend") or "")),
        "model": str(attempt.get("model") or ""),
        "reasoning_effort": str(attempt.get("reasoning_effort") or ""),
        "fallback_reason": str(attempt.get("fallback_reason") or ""),
        "credit_retry": bool(attempt.get("credit_retry")),
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
        proc = run_process_group(
            command,
            input=prompt,
            cwd=workdir,
            timeout=timeout_seconds,
            env=dict(os.environ),
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
    command = aginti_command(
        model=model,
        role=role,
        sandbox=sandbox,
        backend_config=backend_config,
    )
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
    resolved_executable = resolve_command_executable(executable)
    if not resolved_executable:
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
    command[0] = resolved_executable
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
    machine_mode = bool(backend_config.get("machine_mode", True))
    configured_prompt_mode = str(
        backend_config.get("prompt_mode") or os.environ.get("WECHAT_AGINTI_PROMPT_MODE") or ""
    ).strip()
    prompt_mode = configured_prompt_mode or ("stdin" if "--stdin" in command else "arg")
    run_command = list(command)
    stdin_text = wrapped_prompt
    if prompt_mode == "arg":
        run_command.append(wrapped_prompt)
        stdin_text = None
    invocation_started_at = datetime.now().timestamp()
    try:
        proc = run_process_group(
            run_command,
            input=stdin_text,
            cwd=aginti_workdir,
            timeout=timeout_seconds,
            env=dict(os.environ),
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
    stdout = proc.stdout or ""
    message, message_source = extract_aginti_user_message(
        stdout,
        backend_config=backend_config,
        expected_prompt=prompt,
        invocation_started_at=invocation_started_at,
    )
    contract_error = aginti_result_contract_error(message, expected_prompt=prompt) if message else ""
    if contract_error:
        message = ""
        message_source = contract_error
    ok = proc.returncode == 0 and bool(message)
    failure_detail = ""
    if not ok:
        failure_detail = contract_error or (
            aginti_machine_failure_reason(stdout)
            if machine_mode
            else user_facing_backend_message(proc.stderr)
        )
        failure_detail = failure_detail or message_source or "AgInTi returned no valid chat result."
    return {
        "ok": ok,
        "message": message,
        "thread_id": "",
        "returncode": proc.returncode,
        "stderr_tail": ((proc.stderr or "").strip() or failure_detail)[-2000:],
        "stdout_tail": "" if machine_mode else (proc.stdout or "")[-2000:],
        "resumed": False,
        "fallback_started": False,
        "backend": "aginti",
        "message_source": message_source,
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


def aginti_command(
    *,
    model: str,
    role: str,
    sandbox: str,
    backend_config: dict[str, Any],
) -> list[str]:
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
    machine_mode = bool(backend_config.get("machine_mode", True))
    raw_args = backend_config.get("args")
    if raw_args is None:
        raw_args = os.environ.get("WECHAT_AGINTI_ARGS") or ""
    if isinstance(raw_args, list):
        extra_args = [str(item) for item in raw_args if str(item).strip()]
    else:
        extra_args = shlex.split(str(raw_args))
    if machine_mode:
        command = [command[0], *strip_aginti_managed_args(command[1:])]
        extra_args = strip_aginti_managed_args(extra_args)
        if "run" not in command[1:]:
            command.append("run")
    command.extend(extra_args)
    if bool(backend_config.get("pass_role", False)):
        command.extend(["--role", role])
    configured_model = str(backend_config.get("model") or model or "").strip()
    if configured_model and bool(backend_config.get("pass_model_arg", False)):
        command.extend(["--model", configured_model])
    if machine_mode:
        command.extend(
            [
                "--stdin",
                "--json",
                "--no-auto-update",
                "--no-scs",
                "--task-profile",
                str(backend_config.get("task_profile") or "chatops"),
                "--no-parallel-scouts",
                "--package-install-policy",
                "block",
            ]
        )
        if not bool(backend_config.get("allow_mcp", False)):
            command.append("--no-mcp")
        command.extend(
            aginti_sandbox_args(
                role=role,
                sandbox=sandbox,
                backend_config=backend_config,
            )
        )
    return command


def strip_aginti_managed_args(args: list[str]) -> list[str]:
    """Prevent local extra args from overriding the fallback safety contract."""
    clean: list[str] = []
    index = 0
    while index < len(args):
        value = str(args[index])
        normalized = value.casefold()
        if normalized in AGINTI_MANAGED_VALUE_ARGS:
            index += 2
            continue
        if normalized in AGINTI_MANAGED_FLAG_ARGS:
            index += 1
            if normalized in {"--scs", "--enable-scs"} and index < len(args):
                optional = str(args[index]).strip().casefold()
                if optional in {
                    "on",
                    "off",
                    "auto",
                    "smart",
                    "true",
                    "false",
                    "yes",
                    "no",
                    "enable",
                    "disable",
                    "enabled",
                    "disabled",
                    "1",
                    "0",
                }:
                    index += 1
            continue
        clean.append(value)
        index += 1
    return clean


def aginti_sandbox_args(
    *,
    role: str,
    sandbox: str,
    backend_config: dict[str, Any],
) -> list[str]:
    explicit = str(backend_config.get("permission_mode") or "").strip().casefold()
    allow_danger = bool(backend_config.get("allow_dangerous_host", False))
    if explicit == "danger" and not allow_danger:
        explicit = "normal"
    if role in {"fast", "route"}:
        return [
            "--permission-mode",
            "safe",
            "--sandbox-mode",
            "host",
            "--no-shell",
            "--no-file-tools",
            "--no-auxiliary-tools",
        ]
    if explicit in {"safe", "normal", "danger"}:
        permission = explicit
    elif str(sandbox or "").strip().casefold() == "read-only":
        permission = "safe"
    else:
        permission = "normal"
    sandbox_mode = "docker-readonly" if permission == "safe" else "docker-workspace"
    if permission == "danger" and allow_danger:
        sandbox_mode = "host"
    return ["--permission-mode", permission, "--sandbox-mode", sandbox_mode]


def extract_aginti_user_message(
    stdout: str,
    *,
    backend_config: dict[str, Any],
    expected_prompt: str = "",
    invocation_started_at: float = 0.0,
) -> tuple[str, str]:
    """Extract the final assistant turn without forwarding AgInTi console logs."""
    text = ANSI_ESCAPE_RE.sub("", str(stdout or ""))
    machine_mode = bool(backend_config.get("machine_mode", True))
    if machine_mode:
        try:
            payload = json.loads(text.strip())
        except json.JSONDecodeError:
            return "", "invalid_machine_json"
        if not isinstance(payload, dict):
            return "", "invalid_machine_payload"
        if payload.get("ok") is not True:
            reason = " ".join(str(payload.get("reason") or "").split())[:300]
            return "", f"machine_failure:{reason or 'run_failed'}"
        message = user_facing_backend_message(payload.get("result"))
        return (message, "machine_json") if message else ("", "empty_machine_result")
    if not bool(backend_config.get("allow_legacy_output", False)):
        return "", "legacy_output_disabled"
    session_match = AGINTI_SESSION_RE.search(text)
    if session_match:
        session_id = session_match.group(1)
        for sessions_dir in aginti_session_dirs(text, backend_config):
            state_path = sessions_dir / session_id / "state.json"
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            messages = state.get("messages") if isinstance(state, dict) else None
            if not isinstance(messages, list):
                continue
            if not aginti_state_matches_invocation(
                messages,
                state_path,
                expected_prompt=expected_prompt,
                invocation_started_at=invocation_started_at,
            ):
                continue
            for item in reversed(messages):
                if not isinstance(item, dict) or str(item.get("role") or "") != "assistant":
                    continue
                message = user_facing_backend_message(item.get("content"))
                if message:
                    return message, "session_state"
    protocol = extract_agent_protocol_block(text)
    if protocol:
        return protocol, "stdout_protocol"
    return "", "unavailable"


def aginti_machine_failure_reason(stdout: str) -> str:
    try:
        payload = json.loads(ANSI_ESCAPE_RE.sub("", str(stdout or "")).strip())
    except json.JSONDecodeError:
        return "AgInTi machine output was not one valid JSON object."
    if not isinstance(payload, dict):
        return "AgInTi machine output had an invalid payload."
    reason = " ".join(str(payload.get("reason") or "").split())[:500]
    return reason or "AgInTi machine run failed."


def aginti_result_contract_error(message: str, *, expected_prompt: str) -> str:
    text = str(message or "").strip()
    if not text:
        return "empty_machine_result"
    if AGINTI_INTERNAL_REPORT_RE.search(text):
        return "internal_runtime_report_rejected"
    if AGINTI_INTERNAL_OUTPUT_LINE_RE.search(text):
        return "internal_tool_output_rejected"
    if "Return one strict JSON object and no prose" in str(expected_prompt or ""):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return "strict_json_contract_rejected"
        if not isinstance(payload, dict):
            return "strict_json_contract_rejected"
    return ""


def aginti_state_matches_invocation(
    messages: list[Any],
    state_path: Path,
    *,
    expected_prompt: str,
    invocation_started_at: float,
) -> bool:
    if invocation_started_at:
        try:
            if state_path.stat().st_mtime < invocation_started_at - 1.0:
                return False
        except OSError:
            return False
    prompt = str(expected_prompt or "").strip()
    if not prompt:
        return True
    return any(
        isinstance(item, dict)
        and str(item.get("role") or "") == "user"
        and prompt in str(item.get("content") or "")
        for item in messages
    )


def aginti_session_dirs(stdout: str, backend_config: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    for key in ("sessions_dir", "session_dir"):
        raw = str(backend_config.get(key) or "").strip()
        if raw:
            candidates.append(Path(raw).expanduser())
    for line in str(stdout or "").splitlines():
        if line.strip().startswith("Sessions:"):
            raw = line.split(":", 1)[1].strip()
            if raw:
                candidates.append(Path(raw).expanduser())
    candidates.append(Path.home() / ".agintiflow" / "sessions")
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def extract_agent_protocol_block(stdout: str) -> str:
    lines = str(stdout or "").splitlines()
    start = -1
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "NO_REPLY" or re.match(r"^(?:CHAT|ACK|TASK)\s*[:：]", stripped, re.IGNORECASE):
            start = index
    if start < 0:
        return ""
    selected: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if BACKEND_METADATA_LINE_RE.fullmatch(stripped) or stripped in {"Plan:", "Output:"}:
            break
        selected.append(line.rstrip())
    return user_facing_backend_message("\n".join(selected))


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
The exact current request below is the only task. Do not continue an old AgInTi session, reuse an unrelated artifact, or substitute a nearby workspace task.
Preserve the requested output shape exactly. If the original prompt asks for JSON, return only valid JSON. If it asks for CHAT:/ACK:/TASK:, follow that protocol.
Use the same source-isolation, safety, artifact-return, and chat-purpose rules in the original prompt. Do not invent unavailable files or claim browser/platform work completed without evidence.
Do not expose plans, SCS/validator contracts, runtime metadata, model/sandbox details, tool logs, stack traces, or internal diagnostics. For ordinary chat, answer directly without tools or files. For research, use traceable sources and distinguish evidence from inference. For artifact work, create only the requested current-task artifacts.
If you cannot complete the task from the available local tools/context, return one concise task-specific limitation and exact safe next action.

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


def resolve_command_executable(executable: str) -> str:
    """Resolve commands launched by boot services with an intentionally small PATH."""
    if not executable:
        return ""
    if "/" in executable:
        path = Path(executable).expanduser()
        return str(path.resolve()) if path.exists() and os.access(path, os.X_OK) else ""
    resolved = shutil.which(executable)
    if resolved:
        return resolved
    if executable != "aginti":
        return ""
    candidates = sorted(
        (Path.home() / ".nvm" / "versions" / "node").glob("*/bin/aginti"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        reverse=True,
    )
    return next(
        (str(path.resolve()) for path in candidates if path.is_file() and os.access(path, os.X_OK)),
        "",
    )


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
