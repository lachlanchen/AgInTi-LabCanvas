"""Pluggable, session-isolated agent backend for WeChat and WeCom chatops."""

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
MODEL_POLICY_PATH = ROOT / "configs" / "model-policy.json"
CLAUDE_SESSION_DIR = PRIVATE / "claude_sessions"
CLAUDE_REGISTRY = CLAUDE_SESSION_DIR / "sessions.local.json"
AGINTI_SESSION_DIR = PRIVATE / "aginti_sessions"
AGINTI_REGISTRY = AGINTI_SESSION_DIR / "sessions.local.json"
CLAUDE_READONLY_BLOCK = "Bash,Edit,Write,MultiEdit,NotebookEdit"
DEFAULT_FALLBACK_MODEL = "gpt-5.6-sol"
DEFAULT_FALLBACK_REASONING_EFFORT = "low"
DEFAULT_LOW_QUOTA_SPARK_MODEL = "gpt-5.3-codex-spark"
DEFAULT_LOW_QUOTA_THRESHOLD_PERCENT = 25.0
LOW_QUOTA_SPARK_ROLES = frozenset({"fast", "route"})
DEFAULT_AGINTI_PROVIDER_CHAIN = ("deepseek", "localllm")
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
    "--provider",
    "--model",
    "--routing",
    "--session-id",
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
    "--stdin",
    "--json",
    "--no-auto-update",
}
QUOTA_FAILURE_MARKERS = (
    "402",
    "429",
    "billing hard limit",
    "capacity",
    "credit balance",
    "credits exhausted",
    "insufficient_quota",
    "insufficient balance",
    "insufficient funds",
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
    "failed to refresh available models",
    "timeout waiting for child process to exit",
    "failed to connect to websocket",
    "failed to connect to responses_websocket",
)
AGINTI_PROVIDER_PREFLIGHT_FAILURE_MARKERS = (
    "401",
    "402",
    "403",
    "429",
    "api key",
    "authentication",
    "context budget",
    "context window",
    "connection refused",
    "credits exhausted",
    "econnrefused",
    "envelope exceeds",
    "fetch failed",
    "insufficient_quota",
    "insufficient balance",
    "insufficient funds",
    "invalid api key",
    "localllm_context_budget_exceeded",
    "missing key",
    "model not found",
    "not configured",
    "out of quota",
    "provider unavailable",
    "quota",
    "rate limit",
    "service unavailable",
    "temporarily unavailable",
    "unauthorized",
)


def select_agent_backend(config: dict[str, Any] | None = None) -> str:
    """Return an explicit backend or the shared LabCanvas production primary."""
    forced = str(os.environ.get("WECHAT_AGENT_FORCE_BACKEND") or "").strip()
    if forced:
        return normalize_backend(forced)
    if isinstance(config, dict):
        value = config.get("agent_backend") or config.get("backend")
        if value:
            return normalize_backend(str(value))
    configured = str(os.environ.get("WECHAT_AGENT_BACKEND") or "").strip()
    if configured:
        return normalize_backend(configured)
    try:
        policy = json.loads(MODEL_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        policy = {}
    return normalize_backend(str(policy.get("primary_backend") or "aginti"))


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
    return aliases.get(normalized, normalized if normalized in {"codex", "claude", "aginti"} else "aginti")


def agent_context_model(
    backend: str,
    requested_model: str = "",
    *,
    backend_config: dict[str, Any] | None = None,
) -> str:
    """Return the safest model window used to build a backend-neutral prompt."""

    selected = normalize_backend(backend)
    if selected != "aginti":
        return str(requested_model or "").strip() or DEFAULT_FALLBACK_MODEL

    config = backend_config or {}
    try:
        policy = json.loads(MODEL_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        policy = {}
    aginti_policy = policy.get("aginti") if isinstance(policy, dict) else {}
    aginti_policy = aginti_policy if isinstance(aginti_policy, dict) else {}
    policy_models = aginti_policy.get("provider_models")
    policy_models = policy_models if isinstance(policy_models, dict) else {}
    configured_models = config.get("provider_models")
    configured_models = configured_models if isinstance(configured_models, dict) else {}
    memory_policy = policy.get("memory") if isinstance(policy, dict) else {}
    memory_policy = memory_policy if isinstance(memory_policy, dict) else {}
    windows = memory_policy.get("context_window_tokens")
    windows = windows if isinstance(windows, dict) else {}

    candidates: list[tuple[int, str]] = []
    for provider in aginti_provider_chain(config):
        model = str(
            configured_models.get(provider)
            or policy_models.get(provider)
            or provider
        ).strip()
        aliases = (model.casefold(), provider.casefold(), "default")
        window = next(
            (
                int(windows[alias])
                for alias in aliases
                if alias in windows and str(windows[alias]).isdigit()
            ),
            32768,
        )
        candidates.append((window, model))
    if not candidates:
        return "localllm-fast"
    return min(candidates, key=lambda item: (item[0], item[1]))[1]


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
    backend_prompts: dict[str, str] | None = None,
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
        attempt_prompt = prompt_for_backend(
            prompt,
            str(attempt.get("backend") or selected),
            backend_prompts,
        )
        result = run_single_backend_attempt(
            attempt_prompt,
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
            and is_response_only_agent_role(role)
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


def prompt_for_backend(
    default_prompt: str,
    backend: str,
    backend_prompts: dict[str, str] | None,
) -> str:
    """Return a backend-sized prompt without changing the task or fallback plan."""

    if not isinstance(backend_prompts, dict):
        return default_prompt
    selected = normalize_backend(backend)
    candidate = backend_prompts.get(selected)
    return str(candidate) if candidate is not None else default_prompt


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
            reuse=reuse,
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
    try:
        policy = json.loads(MODEL_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        policy = {}
    policy_backend = policy.get(selected) if isinstance(policy, dict) else None
    if isinstance(policy_backend, dict):
        merged.update(policy_backend)
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
    # A backend switch after a tool started can repeat an unknown side effect.
    # Keep the exact task resumable instead of replaying it on another model.
    if result.get("tool_activity"):
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
    forced_off = str(os.environ.get("WECHAT_AGENT_FORCE_DISABLE_AGINTI") or "").strip()
    if forced_off.casefold() in {"1", "true", "yes", "on"}:
        return False
    explicit = str(os.environ.get("WECHAT_AGENT_FALLBACK_TO_AGINTI") or "").strip()
    if explicit:
        return explicit.casefold() not in {"0", "false", "no", "off"}
    fallback_config = fallback_config_dict(config)
    for key in ("aginti_enabled", "fallback_to_aginti"):
        if key in fallback_config:
            return bool(fallback_config[key])
    return False


def fallback_on_timeout_enabled(config: dict[str, Any]) -> bool:
    explicit = str(os.environ.get("WECHAT_AGENT_FALLBACK_ON_TIMEOUT") or "").strip()
    if explicit:
        return explicit.casefold() not in {"0", "false", "no", "off"}
    fallback_config = fallback_config_dict(config)
    return bool(
        fallback_config.get(
            "timeout_enabled",
            fallback_config.get("fallback_on_timeout", False),
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
    reuse: bool = True,
    backend_config: dict[str, Any],
) -> dict[str, Any]:
    if os.environ.get("WECHAT_AGINTI_REUSE_SESSIONS", "1") == "0":
        reuse = False
    AGINTI_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    key = session_key(chat_name, role)
    execution_lock_path = aginti_execution_lock_path(key)
    execution_lock_path.parent.mkdir(parents=True, exist_ok=True)
    with execution_lock_path.open("w", encoding="utf-8") as execution_lock:
        with exclusive_lock(execution_lock):
            previous_id = read_aginti_session_id(key) if reuse else ""
            context_session_rotated = False
            if (
                previous_id
                and aginti_session_context_oversized(previous_id, backend_config)
            ):
                clear_aginti_session_id(key, expected_session_id=previous_id)
                previous_id = ""
                context_session_rotated = True
            new_session_id = "" if previous_id else f"web-agent-labcanvas-{uuid.uuid4()}"
            result = run_aginti_provider_chain(
                prompt,
                chat_name=chat_name,
                role=role,
                model=model,
                reasoning_effort=reasoning_effort,
                sandbox=sandbox,
                timeout_seconds=timeout_seconds,
                workdir=workdir,
                backend_config=backend_config,
                previous_id=previous_id,
                new_session_id=new_session_id,
            )
            recovery_reason = ""
            if previous_id and aginti_missing_session_result(result):
                recovery_reason = "missing_session"
            elif (
                previous_id
                and aginti_context_exhausted_result(result)
            ):
                recovery_reason = "context_exhausted"
            if recovery_reason:
                clear_aginti_session_id(key, expected_session_id=previous_id)
                new_session_id = f"web-agent-labcanvas-{uuid.uuid4()}" if reuse else ""
                result = run_aginti_provider_chain(
                    prompt,
                    chat_name=chat_name,
                    role=role,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    sandbox=sandbox,
                    timeout_seconds=timeout_seconds,
                    workdir=workdir,
                    backend_config=backend_config,
                    previous_id="",
                    new_session_id=new_session_id,
                )
                result["fallback_started"] = True
                if recovery_reason == "missing_session":
                    result["stale_session_recovered"] = True
                else:
                    result["context_session_recovered"] = True
            if context_session_rotated:
                result["context_session_rotated"] = True
            if reuse and result.get("ok") and result.get("thread_id"):
                persist_aginti_session(
                    key,
                    chat_name=chat_name,
                    role=role,
                    result=result,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    sandbox=sandbox,
                    workdir=workdir,
                )
            return result


def run_aginti_provider_chain(
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
    previous_id: str,
    new_session_id: str,
) -> dict[str, Any]:
    provider_attempts: list[dict[str, Any]] = []
    providers = aginti_provider_chain(backend_config)
    result: dict[str, Any] = {
        "ok": False,
        "message": "AgInTi failed: no provider was configured.",
        "thread_id": previous_id or new_session_id,
        "returncode": 1,
        "stderr_tail": "no AgInTi provider configured",
        "stdout_tail": "",
        "resumed": bool(previous_id),
        "fallback_started": False,
        "backend": "aginti",
    }
    chain_session_id = previous_id or new_session_id
    next_provider_prompt = prompt
    for index, provider in enumerate(providers):
        continue_existing = bool(previous_id or index > 0)
        result = run_aginti_provider_once(
            next_provider_prompt,
            chat_name=chat_name,
            role=role,
            model=model,
            reasoning_effort=reasoning_effort,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
            backend_config=backend_config,
            provider=provider,
            session_id=chain_session_id if continue_existing else "",
            new_session_id="" if continue_existing else chain_session_id,
        )
        if index > 0 and not previous_id and aginti_missing_session_result(result):
            result = run_aginti_provider_once(
                prompt,
                chat_name=chat_name,
                role=role,
                model=model,
                reasoning_effort=reasoning_effort,
                sandbox=sandbox,
                timeout_seconds=timeout_seconds,
                workdir=workdir,
                backend_config=backend_config,
                provider=provider,
                session_id="",
                new_session_id=chain_session_id,
            )
            result["missing_fallback_session_recovered"] = True
        chain_session_id = str(result.get("thread_id") or chain_session_id)
        retry_mode = aginti_provider_retry_mode(result)
        provider_attempts.append(
            {
                "provider": provider,
                "ok": bool(result.get("ok")),
                "returncode": result.get("returncode"),
                "failure_kind": classify_backend_failure(result),
                "retry_safe": bool(retry_mode),
                "retry_mode": retry_mode,
                "continued_same_session": continue_existing,
            }
        )
        result["resumed"] = bool(previous_id)
        result["fallback_continued_same_session"] = bool(index > 0)
        result["provider"] = provider
        result["provider_attempts"] = provider_attempts
        if result.get("ok"):
            return result
        if index + 1 >= len(providers) or not retry_mode:
            return result
        next_provider_prompt = (
            aginti_provider_pre_inference_prompt(prompt)
            if retry_mode == "replay_current_request"
            else aginti_provider_handoff_prompt()
        )
    return result


def run_aginti_provider_once(
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
    provider: str,
    session_id: str = "",
    new_session_id: str = "",
) -> dict[str, Any]:
    """Run one explicit AgInTi provider without replaying task side effects."""

    command = aginti_command(
        model=model,
        role=role,
        reasoning_effort=reasoning_effort,
        sandbox=sandbox,
        backend_config=backend_config,
        provider=provider,
        session_id=session_id,
        new_session_id=new_session_id,
    )
    if not command:
        return {
            "ok": False,
            "message": "AgInTi failed: command is empty.",
            "thread_id": session_id or new_session_id,
            "returncode": 127,
            "stderr_tail": "aginti command is empty",
            "stdout_tail": "",
            "resumed": bool(session_id),
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
        backend_config.get("prompt_mode") or aginti_env_value("PROMPT_MODE")
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
            "thread_id": session_id or new_session_id,
            "returncode": 127,
            "stderr_tail": str(exc),
            "stdout_tail": "",
            "resumed": bool(session_id),
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
    message = normalize_aginti_strict_json_message(
        message,
        expected_prompt=prompt,
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
    machine_session_id = aginti_machine_session_id(stdout)
    return {
        "ok": ok,
        "message": message,
        "thread_id": machine_session_id or session_id or new_session_id,
        "returncode": proc.returncode,
        "stderr_tail": ((proc.stderr or "").strip() or failure_detail)[-2000:],
        "stdout_tail": "" if machine_mode else (proc.stdout or "")[-2000:],
        "resumed": bool(session_id),
        "fallback_started": False,
        "backend": "aginti",
        "message_source": message_source,
    }


def aginti_env_value(suffix: str) -> str:
    """Read the shared backend setting from either transport environment."""

    normalized = str(suffix or "").strip().upper()
    if not normalized:
        return ""
    configured_empty = False
    for prefix in ("WECHAT", "WECOM", "LABCANVAS"):
        value = os.environ.get(f"{prefix}_AGINTI_{normalized}")
        if value is None:
            continue
        if str(value).strip():
            return value
        configured_empty = True
    if configured_empty:
        return ""
    return ""


def aginti_localllm_complete_marker(
    backend_config: dict[str, Any],
) -> Path | None:
    """Return the optional marker that re-enables LocalLLM after maintenance."""

    raw = str(
        aginti_env_value("LOCALLLM_COMPLETE_MARKER")
        or backend_config.get("localllm_complete_marker")
        or ""
    ).strip()
    if not raw:
        return None
    marker = Path(raw).expanduser()
    if not marker.is_absolute():
        marker = ROOT / marker
    return marker.resolve()


def aginti_provider_chain(backend_config: dict[str, Any]) -> list[str]:
    # An operator override is authoritative during provider maintenance; task
    # defaults must not silently re-enable a fenced provider.
    raw: Any = aginti_env_value("PROVIDER_CHAIN").strip()
    if not raw:
        raw = backend_config.get("provider_chain") or backend_config.get("providers")
    if raw is None:
        explicit = str(
            backend_config.get("provider")
            or aginti_env_value("PROVIDER")
            or ""
        ).strip()
        raw = [explicit] if explicit else list(DEFAULT_AGINTI_PROVIDER_CHAIN)
    if isinstance(raw, str):
        values = re.split(r"[,\s]+", raw)
    elif isinstance(raw, (list, tuple)):
        values = [str(item) for item in raw]
    else:
        values = []
    providers: list[str] = []
    for value in values:
        provider = str(value or "").strip().casefold()
        if provider and provider not in providers:
            providers.append(provider)
    providers = providers or list(DEFAULT_AGINTI_PROVIDER_CHAIN)
    marker = aginti_localllm_complete_marker(backend_config)
    if marker is not None and not marker.is_file():
        providers = [provider for provider in providers if provider != "localllm"]
        # Maintenance must not turn LabCanvas into a silent no-provider system.
        # DeepSeek remains the online AgInTi route until the marker appears.
        if not providers:
            providers = ["deepseek"]
    return providers


def aginti_provider_retry_is_safe(result: dict[str, Any]) -> bool:
    """Retry another provider only for failures known to precede task execution."""

    return bool(aginti_provider_retry_mode(result))


def aginti_provider_retry_mode(result: dict[str, Any]) -> str:
    """Choose exact-request replay only when the failed provider never inferred."""

    returncode = int(result.get("returncode") or 0)
    if result.get("ok") or returncode == 127:
        return ""
    if user_facing_backend_message(result.get("message")):
        return ""
    text = " ".join(
        str(result.get(key) or "")
        for key in ("stderr_tail", "stdout_tail", "reason", "message_source")
    ).casefold()
    if returncode == 124 or "timeout" in text or "timed out" in text:
        return "resume_durable_state" if result.get("thread_id") else ""
    if any(marker in text for marker in AGINTI_PROVIDER_PREFLIGHT_FAILURE_MARKERS):
        return "replay_current_request"
    if any(
        reason in text
        for reason in (
            "empty_model_response",
            "invalid_machine_json",
            "model_did_not_execute",
            "model_timeout",
            "provider_unavailable",
            "tool_contract_violation",
        )
    ):
        return "resume_durable_state" if result.get("thread_id") else ""
    return ""


def aginti_provider_pre_inference_prompt(prompt: str) -> str:
    """Carry the exact request across a provider failure proven pre-inference."""

    return (
        "Provider handoff after a verified pre-inference failure: the previous provider "
        "did not infer, call tools, or execute side effects. Treat the exact current request "
        "below as authoritative even if older session history discusses a similar task. "
        "Do not revive or answer the older request.\n\n"
        f"Exact current request:\n{prompt}"
    )


def aginti_provider_handoff_prompt() -> str:
    return (
        "Provider handoff: resume the exact durable goal and current session state. "
        "Inspect existing tool evidence before acting, preserve every user requirement, do not repeat completed side effects, "
        "and finish the smallest remaining work with a concise verified chat response or concrete blocker."
    )


def aginti_missing_session_result(result: dict[str, Any]) -> bool:
    text = " ".join(
        str(result.get(key) or "")
        for key in ("stderr_tail", "stdout_tail", "reason", "message_source")
    ).casefold()
    return "no saved session found" in text


def aginti_context_exhausted_result(result: dict[str, Any]) -> bool:
    """Detect provider refusal before inference because session history is too large."""

    text = " ".join(
        str(result.get(key) or "")
        for key in ("stderr_tail", "stdout_tail", "reason", "message_source", "message")
    ).casefold()
    return any(
        marker in text
        for marker in (
            "context_budget_exceeded",
            "context window",
            "envelope exceeds",
            "maximum context length",
            "reduce the length of the messages",
        )
    )


def aginti_session_context_oversized(
    session_id: str,
    backend_config: dict[str, Any],
) -> bool:
    """Retire an oversized or repeatedly compacted reusable AgInTi session."""

    raw_limit = (
        backend_config.get("response_session_max_chars")
        or aginti_env_value("RESPONSE_SESSION_MAX_CHARS")
        or "400000"
    )
    try:
        limit = max(10000, int(raw_limit))
    except (TypeError, ValueError):
        limit = 400000
    raw_compaction_limit = (
        backend_config.get("response_session_max_compactions")
        or aginti_env_value("RESPONSE_SESSION_MAX_COMPACTIONS")
        or "24"
    )
    raw_stagnation_limit = (
        backend_config.get("response_session_max_stagnation_epoch")
        or aginti_env_value("RESPONSE_SESSION_MAX_STAGNATION_EPOCH")
        or "96"
    )
    try:
        compaction_limit = max(1, int(raw_compaction_limit))
    except (TypeError, ValueError):
        compaction_limit = 24
    try:
        stagnation_limit = max(8, int(raw_stagnation_limit))
    except (TypeError, ValueError):
        stagnation_limit = 96
    for directory in aginti_session_dirs("", backend_config):
        state_path = directory / session_id / "state.json"
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meta = payload.get("meta") if isinstance(payload, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        context_budget = meta.get("contextBudget")
        context_budget = context_budget if isinstance(context_budget, dict) else {}
        try:
            compactions = int(context_budget.get("compactions") or 0)
        except (TypeError, ValueError):
            compactions = 0
        if compactions > compaction_limit:
            return True
        tool_loop = meta.get("toolLoop")
        tool_loop = tool_loop if isinstance(tool_loop, dict) else {}
        try:
            stagnation_epoch = int(tool_loop.get("stagnationEpoch") or 0)
        except (TypeError, ValueError):
            stagnation_epoch = 0
        if stagnation_epoch > stagnation_limit:
            return True
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            continue
        total = 0
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content", "")
            if isinstance(content, str):
                total += len(content)
            else:
                try:
                    total += len(json.dumps(content, ensure_ascii=False))
                except (TypeError, ValueError):
                    total += len(str(content))
            if total > limit:
                return True
    return False


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
    reasoning_effort: str = "",
    sandbox: str,
    backend_config: dict[str, Any],
    provider: str = "",
    session_id: str = "",
    new_session_id: str = "",
) -> list[str]:
    raw_command = (
        backend_config.get("command")
        or backend_config.get("bin")
        or aginti_env_value("COMMAND")
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
        raw_args = aginti_env_value("ARGS")
    if isinstance(raw_args, list):
        extra_args = [str(item) for item in raw_args if str(item).strip()]
    else:
        extra_args = shlex.split(str(raw_args))
    if machine_mode:
        command = [command[0], *strip_aginti_managed_args(command[1:])]
        extra_args = strip_aginti_managed_args(extra_args)
        if command[1:2] == ["run"]:
            del command[1]
        elif command[1:2] == ["resume"]:
            del command[1:3]
        if session_id:
            command.extend(["resume", session_id])
        else:
            command.append("run")
            if new_session_id:
                command.extend(["--session-id", new_session_id])
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
                "--routing",
                "manual",
                "--no-scs",
                "--task-profile",
                aginti_task_profile(role, backend_config),
                "--no-parallel-scouts",
            ]
        )
        command.extend(
            aginti_package_install_args(
                role=role,
                sandbox=sandbox,
                backend_config=backend_config,
            )
        )
        selected_provider = str(provider or aginti_provider_chain(backend_config)[0]).strip()
        if selected_provider:
            command.extend(["--provider", selected_provider])
        provider_model = aginti_provider_model(
            selected_provider,
            requested_model=configured_model,
            reasoning_effort=reasoning_effort,
            backend_config=backend_config,
        )
        if provider_model:
            command.extend(["--model", provider_model])
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


def aginti_provider_model(
    provider: str,
    *,
    requested_model: str,
    reasoning_effort: str,
    backend_config: dict[str, Any],
) -> str:
    """Resolve an explicit provider model without forcing fast models on real work."""

    selected_provider = str(provider or "").strip().casefold()
    requested = str(requested_model or "").strip()
    compatible = (
        (selected_provider == "openai" and (requested.startswith("gpt-") or requested == "auto-code-review"))
        or (selected_provider == "deepseek" and requested.startswith("deepseek"))
        or (selected_provider == "localllm" and requested.startswith("localllm"))
    )
    if requested not in {"", "auto", "provider-default", "aginti"} and compatible:
        return requested

    effort = str(reasoning_effort or "low").strip().casefold()
    if effort in {"max", "ultra"}:
        effort = "xhigh"
    by_effort = backend_config.get("provider_models_by_effort")
    by_effort = by_effort if isinstance(by_effort, dict) else {}
    provider_efforts = by_effort.get(selected_provider)
    provider_efforts = provider_efforts if isinstance(provider_efforts, dict) else {}
    effort_model = str(
        provider_efforts.get(effort)
        or provider_efforts.get("default")
        or ""
    ).strip()
    if effort_model:
        return effort_model

    provider_models = backend_config.get("provider_models")
    provider_models = provider_models if isinstance(provider_models, dict) else {}
    return str(provider_models.get(selected_provider) or "").strip()


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
    explicit_sandbox = str(backend_config.get("sandbox_mode") or "").strip().casefold()
    allow_danger = bool(backend_config.get("allow_dangerous_host", False))
    allow_host_workspace = bool(backend_config.get("allow_host_workspace", False))
    if explicit == "danger" and not allow_danger:
        explicit = "normal"
    if is_response_only_agent_role(role):
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
    if explicit_sandbox in {"docker-readonly", "docker-workspace"}:
        sandbox_mode = explicit_sandbox
    elif explicit_sandbox == "host" and allow_host_workspace:
        sandbox_mode = "host"
    if permission == "danger" and allow_danger:
        sandbox_mode = "host"
    return ["--permission-mode", permission, "--sandbox-mode", sandbox_mode]


def aginti_package_install_args(
    *,
    role: str,
    sandbox: str,
    backend_config: dict[str, Any],
) -> list[str]:
    """Keep response turns read-only while making normal workers executable.

    AgInTi uses package-install approval as the trust gate for broad commands in
    its Docker workspace. Forcing that policy to ``block`` on every worker also
    blocks ordinary project-local validation such as Python, TeX, and LabCanvas
    CLI commands. Worker setup remains contained in Docker; host and destructive
    actions are still governed by the separate sandbox and action gates.
    """
    explicit = str(backend_config.get("package_install_policy") or "").strip().casefold()
    if explicit not in {"allow", "block", "prompt"}:
        explicit = ""
    read_only = (
        is_response_only_agent_role(role)
        or str(sandbox or "").strip().casefold() == "read-only"
        or str(backend_config.get("permission_mode") or "").strip().casefold() == "safe"
    )
    policy = explicit or ("block" if read_only else "allow")
    args = ["--package-install-policy", policy]
    if policy == "allow":
        args.append("--approve-package-installs")
    return args


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
        if payload.get("ok") is not True or bool(payload.get("stopped")) or bool(payload.get("failed")):
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


def aginti_machine_session_id(stdout: str) -> str:
    try:
        payload = json.loads(ANSI_ESCAPE_RE.sub("", str(stdout or "")).strip())
    except json.JSONDecodeError:
        return ""
    return str(payload.get("sessionId") or "") if isinstance(payload, dict) else ""


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
        if extract_aginti_json_object(text) is None:
            return "strict_json_contract_rejected"
    return ""


def normalize_aginti_strict_json_message(
    message: str,
    *,
    expected_prompt: str,
) -> str:
    """Canonicalize one fenced/wrapped JSON result before worker parsing."""

    text = str(message or "").strip()
    if "Return one strict JSON object and no prose" not in str(expected_prompt or ""):
        return text
    payload = extract_aginti_json_object(text)
    if payload is None:
        return text
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def extract_aginti_json_object(text: str) -> dict[str, Any] | None:
    """Extract one JSON object while rejecting arbitrary unstructured output."""

    stripped = str(text or "").strip()
    if not stripped:
        return None
    candidates = [stripped]
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            stripped,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return payload
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                payload, _end = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return None


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
    raw = str(
        backend_config.get("workspace") or aginti_env_value("WORKSPACE")
    ).strip()
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
    if is_response_only_agent_role(role):
        mode = (
            "chat-response"
            if is_conversational_agent_role(role)
            else "host-managed-response"
        )
        return f"""You are AgInTi, the response-only reasoning backend for LabCanvas chat automation.
AGINTI_EVIDENCE_SCOPE_JSON: {{"mode":"{mode}","request":"Return the requested text only; no external action is requested."}}
This turn is complete when you return the requested text. Do not use tools, browse, create or inspect files, or demand execution evidence. The LabCanvas host performs any later compilation, validation, persistence, and delivery outside this turn.
Treat the exact current request as authoritative. Preserve its output shape exactly: return only JSON when it asks for JSON, only LaTeX body text when it asks for a LaTeX body, and only the finished chat response when it asks for chat text.
Use relevant same-chat context, but never continue an unrelated task or expose plans, runtime metadata, model details, tool logs, stack traces, or internal diagnostics. Do not add a setup confirmation or claim an external action occurred.

Chat: {chat_name}
Role: {role}

Original prompt:
{prompt}
"""
    evidence_scope = ""
    if "AGINTI_EVIDENCE_SCOPE_JSON:" not in prompt:
        scoped_request = str(
            backend_config.get("evidence_scope_request") or prompt
        ).strip()
        evidence_scope_data = {"mode": "task", "request": scoped_request}
        artifact_root = str(
            backend_config.get("evidence_scope_artifact_root") or ""
        ).strip()
        if artifact_root:
            evidence_scope_data["artifact_root"] = artifact_root
        evidence_scope_payload = json.dumps(
            evidence_scope_data, ensure_ascii=False, separators=(",", ":")
        )
        evidence_scope = f"AGINTI_EVIDENCE_SCOPE_JSON: {evidence_scope_payload}\n"
    return f"""You are AgInTi, the primary reasoning and tool agent for LabCanvas chat automation.
{evidence_scope}Treat the exact current request as the authoritative continuation of this chat. Use relevant same-chat session memory and repository instructions, but never continue an unrelated task, reuse an unrelated artifact, or substitute a nearby workspace request.
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


def is_conversational_agent_role(role: str) -> bool:
    normalized = str(role or "").strip().casefold().replace("_", "-")
    return normalized in {"fast", "route"} or normalized.startswith(
        ("fast-", "route-", "peer-", "chat-")
    )


def is_response_only_agent_role(role: str) -> bool:
    normalized = str(role or "").strip().casefold().replace("_", "-")
    if is_conversational_agent_role(normalized):
        return True
    exact_roles = {
        "career-daily",
        "career-research",
        "completion-audit",
        "daily-language-pdf",
        "daily-organizer",
        "scheduled-language-editor",
        "scheduled-language-teacher",
    }
    role_families = (
        "career-daily-",
        "career-research-",
        "daily-organizer-",
        "daily-language-pdf-",
        "translate-",
        "translation-",
    )
    return normalized in exact_roles or normalized.startswith(role_families)


def aginti_task_profile(role: str, backend_config: dict[str, Any]) -> str:
    explicit = str(backend_config.get("task_profile") or "").strip()
    if explicit:
        return explicit
    return "chatops" if is_response_only_agent_role(role) else "auto"


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


def aginti_execution_lock_path(key: str) -> Path:
    digest = uuid.uuid5(uuid.NAMESPACE_URL, f"labcanvas-aginti:{key}").hex
    return AGINTI_SESSION_DIR / "execution-locks" / f"{digest}.lock"


def read_aginti_session_id(key: str) -> str:
    AGINTI_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = AGINTI_REGISTRY.with_suffix(".lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        with exclusive_lock(lock):
            registry = load_json_dict(AGINTI_REGISTRY)
            entry = registry.get(key) if isinstance(registry.get(key), dict) else {}
            return str(entry.get("thread_id") or "")


def persist_aginti_session(
    key: str,
    *,
    chat_name: str,
    role: str,
    result: dict[str, Any],
    model: str,
    reasoning_effort: str,
    sandbox: str,
    workdir: Path,
) -> None:
    AGINTI_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = AGINTI_REGISTRY.with_suffix(".lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        with exclusive_lock(lock):
            registry = load_json_dict(AGINTI_REGISTRY)
            previous = registry.get(key, {}) if isinstance(registry.get(key), dict) else {}
            registry[key] = {
                "thread_id": str(result.get("thread_id") or ""),
                "chat_name": chat_name,
                "role": role,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "sandbox": sandbox,
                "workdir": str(workdir),
                "provider": str(result.get("provider") or ""),
                "created_at": previous.get("created_at") or datetime.now().isoformat(timespec="seconds"),
                "last_used_at": datetime.now().isoformat(timespec="seconds"),
                "turn_count": int(previous.get("turn_count") or 0) + 1,
            }
            write_private_json_atomic(AGINTI_REGISTRY, registry)


def clear_aginti_session_id(key: str, *, expected_session_id: str) -> None:
    lock_path = AGINTI_REGISTRY.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        with exclusive_lock(lock):
            registry = load_json_dict(AGINTI_REGISTRY)
            entry = registry.get(key) if isinstance(registry.get(key), dict) else {}
            if str(entry.get("thread_id") or "") != expected_session_id:
                return
            registry.pop(key, None)
            write_private_json_atomic(AGINTI_REGISTRY, registry)


def write_private_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    os.replace(temporary, path)


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
    if selected == "aginti":
        raw = os.environ.get("WECHAT_AGINTI_COMMAND") or os.environ.get("WECOM_AGINTI_COMMAND") or "aginti"
        command = shlex.split(raw)
        return resolve_command_executable(command[0]) if command else ""
    return resolve_codex_binary()
