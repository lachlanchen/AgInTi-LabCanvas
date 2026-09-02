#!/usr/bin/env python3
"""Small private registry for reusable Codex exec sessions per WeChat group."""

from __future__ import annotations

from datetime import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from file_lock import fcntl_compat as fcntl


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agenticapp.codex_accounts import (  # noqa: E402
    agentshell_codex_command,
    codex_account_candidates,
    mark_codex_account_runtime_unavailable,
)

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
    key = session_key(chat_name, role)
    execution_lock_path = session_execution_lock_path(registry_path, key)
    execution_lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize one exact chat/role thread, while allowing unrelated chats and
    # lightweight router turns to run concurrently. The registry lock below is
    # deliberately held only for short read/write transactions.
    with execution_lock_path.open("w", encoding="utf-8") as execution_lock:
        fcntl.flock(execution_lock, fcntl.LOCK_EX)
        previous_id = read_registered_thread_id(registry_path, key) if reuse else ""
        session_rotated = bool(
            previous_id
            and registered_session_exceeds_turn_limit(registry_path, key, role)
        )
        if session_rotated:
            previous_id = ""
        slot = acquire_codex_concurrency_slot(
            registry_path,
            timeout_seconds=timeout_seconds,
        )
        if slot is None:
            result = codex_slot_timeout_result(previous_id)
        else:
            try:
                result = run_codex_across_accounts(
                    prompt,
                    thread_id=previous_id,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    sandbox=sandbox,
                    timeout_seconds=timeout_seconds,
                    workdir=workdir,
                    web_search=codex_web_search_enabled(role),
                )
            finally:
                release_codex_concurrency_slot(slot)
        if previous_id and not result["ok"] and codex_saved_thread_unavailable(result):
            slot = acquire_codex_concurrency_slot(
                registry_path,
                timeout_seconds=timeout_seconds,
            )
            if slot is None:
                fallback = codex_slot_timeout_result(previous_id)
            else:
                try:
                    fallback = run_codex_across_accounts(
                        prompt,
                        thread_id="",
                        model=model,
                        reasoning_effort=reasoning_effort,
                        sandbox=sandbox,
                        timeout_seconds=timeout_seconds,
                        workdir=workdir,
                        web_search=codex_web_search_enabled(role),
                    )
                finally:
                    release_codex_concurrency_slot(slot)
            fallback["resumed"] = False
            fallback["fallback_started"] = True
            result = fallback
        else:
            result["resumed"] = bool(previous_id)
            result["fallback_started"] = False
        result["session_rotated"] = session_rotated
        if result.get("ok") and result.get("thread_id"):
            result["registry_persisted"] = persist_session_result(
                registry_path,
                key,
                chat_name,
                role,
                result,
                model,
                reasoning_effort,
                sandbox,
                workdir,
            )
        fcntl.flock(execution_lock, fcntl.LOCK_UN)
    return result


def run_codex_with_startup_retries(
    prompt: str,
    *,
    thread_id: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path,
    web_search: bool,
    agentshell_account: str = "",
) -> dict[str, Any]:
    """Retry only failures proven to occur before a Codex turn starts."""
    max_retries = max(0, int(os.environ.get("WECHAT_CODEX_STARTUP_RETRIES", "2")))
    base_delay = max(
        0.0,
        float(os.environ.get("WECHAT_CODEX_STARTUP_RETRY_DELAY_SECONDS", "1.5")),
    )
    retry_reasons: list[str] = []
    result: dict[str, Any] = {}
    for retry_index in range(max_retries + 1):
        result = run_codex_once(
            prompt,
            thread_id=thread_id,
            model=model,
            reasoning_effort=reasoning_effort,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
            web_search=web_search,
            agentshell_account=agentshell_account,
        )
        if not codex_startup_retryable(result) or retry_index >= max_retries:
            break
        retry_reasons.append(codex_startup_failure_reason(result))
        if base_delay:
            time.sleep(base_delay * (retry_index + 1))
    result["startup_retry_count"] = len(retry_reasons)
    if retry_reasons:
        result["startup_retry_reasons"] = retry_reasons
    return result


def run_codex_across_accounts(
    prompt: str,
    *,
    thread_id: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path,
    web_search: bool,
) -> dict[str, Any]:
    """Try cached available accounts, but only before a turn or tool starts."""
    accounts = codex_account_candidates()
    attempts: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    for account in accounts or [""]:
        result = run_codex_with_startup_retries(
            prompt,
            thread_id=thread_id,
            model=model,
            reasoning_effort=reasoning_effort,
            sandbox=sandbox,
            timeout_seconds=timeout_seconds,
            workdir=workdir,
            web_search=web_search,
            agentshell_account=account,
        )
        result["agentshell_account"] = account
        attempts.append(
            {
                "account": account,
                "ok": bool(result.get("ok")),
                "returncode": result.get("returncode"),
                "execution_started": bool(result.get("execution_started")),
                "tool_activity": bool(result.get("tool_activity")),
            }
        )
        if account and codex_account_quota_rejected(result):
            mark_codex_account_runtime_unavailable(account)
        if result.get("ok") or not codex_account_switch_retryable(result):
            break
    result["account_attempts"] = attempts
    result["account_failover_count"] = max(0, len(attempts) - 1)
    return result


def codex_account_switch_retryable(result: dict[str, Any]) -> bool:
    # Codex emits turn.started before the server can reject quota.  Rotation is
    # still safe until a tool item appears; the replacement resumes the same
    # shared-history thread and cannot duplicate an external side effect.
    if result.get("ok") or result.get("tool_activity"):
        return False
    text = " ".join(
        str(result.get(key) or "")
        for key in ("message", "stderr_tail", "stdout_tail", "error")
    ).casefold()
    return any(
        marker in text
        for marker in (
            "usage limit",
            "rate limit",
            "quota",
            "insufficient credit",
            "out of credits",
            "failed to refresh available models",
            "failed to connect",
            "transport channel closed",
            "connection reset before headers",
        )
    )


def codex_account_quota_rejected(result: dict[str, Any]) -> bool:
    if result.get("ok") or result.get("tool_activity"):
        return False
    text = " ".join(
        str(result.get(key) or "")
        for key in ("message", "stderr_tail", "stdout_tail", "error")
    ).casefold()
    return any(
        marker in text
        for marker in ("usage limit", "rate limit", "quota", "insufficient credit", "out of credits")
    )


def codex_slot_timeout_result(thread_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "message": "Codex failed: timed out waiting for an execution slot.",
        "thread_id": thread_id,
        "returncode": 124,
        "stderr_tail": "codex concurrency slot timeout",
        "stdout_tail": "",
        "execution_started": False,
        "tool_activity": False,
    }


def acquire_codex_concurrency_slot(
    registry_path: Path,
    *,
    timeout_seconds: int,
) -> Any | None:
    """Bound concurrent Codex CLIs across worker processes without global serialization."""
    try:
        slot_count = max(1, int(os.environ.get("WECHAT_CODEX_MAX_CONCURRENCY", "2")))
    except ValueError:
        slot_count = 2
    try:
        wait_seconds = max(
            1.0,
            float(
                os.environ.get(
                    "WECHAT_CODEX_CONCURRENCY_WAIT_SECONDS",
                    str(timeout_seconds),
                )
            ),
        )
    except ValueError:
        wait_seconds = float(max(1, timeout_seconds))
    slot_dir = registry_path.parent / "concurrency-slots"
    slot_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    while True:
        for index in range(slot_count):
            handle = (slot_dir / f"slot-{index}.lock").open("w", encoding="utf-8")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError) as exc:
                handle.close()
                if isinstance(exc, OSError) and exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                continue
            return handle
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


def release_codex_concurrency_slot(handle: Any) -> None:
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


def codex_saved_thread_unavailable(result: dict[str, Any]) -> bool:
    if result.get("ok") or result.get("execution_started") or result.get("tool_activity"):
        return False
    text = " ".join(
        str(result.get(key) or "")
        for key in ("message", "stderr_tail", "stdout_tail")
    ).casefold()
    return any(
        marker in text
        for marker in (
            "no saved session found",
            "thread not found",
            "conversation not found",
            "unknown thread",
        )
    )


def codex_startup_retryable(result: dict[str, Any]) -> bool:
    if result.get("ok") or result.get("execution_started") or result.get("tool_activity"):
        return False
    if str(result.get("message") or "").strip():
        return False
    return bool(codex_startup_failure_reason(result))


def codex_startup_failure_reason(result: dict[str, Any]) -> str:
    text = " ".join(
        str(result.get(key) or "")
        for key in ("stderr_tail", "stdout_tail")
    ).casefold()
    markers = (
        "failed to refresh available models",
        "timeout waiting for child process to exit",
        "failed to connect to websocket",
        "failed to connect to responses_websocket",
        "connection reset before headers",
        "transport channel closed",
    )
    return next((marker for marker in markers if marker in text), "")


def registry_lock_path(registry_path: Path) -> Path:
    return registry_path.with_suffix(".lock")


def session_execution_lock_path(registry_path: Path, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return registry_path.parent / "execution-locks" / f"{digest}.lock"


def read_registered_thread_id(registry_path: Path, key: str) -> str:
    lock_path = registry_lock_path(registry_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        if not acquire_exclusive_lock(lock):
            return ""
        registry = load_registry(registry_path)
        thread_id = str(registry.get(key, {}).get("thread_id") or "")
        fcntl.flock(lock, fcntl.LOCK_UN)
    return thread_id


def registered_session_exceeds_turn_limit(
    registry_path: Path,
    key: str,
    role: str,
) -> bool:
    """Rotate long-lived Codex threads before resume latency becomes unstable."""

    normalized_role = re.sub(r"[^0-9A-Za-z]+", "_", str(role or "")).strip("_").upper()
    role_env = f"WECHAT_CODEX_SESSION_MAX_TURNS_{normalized_role}" if normalized_role else ""
    default_limit = "96" if str(role or "").strip() == "worker" else "192"
    raw_limit = (os.environ.get(role_env) if role_env else "") or os.environ.get(
        "WECHAT_CODEX_SESSION_MAX_TURNS",
        default_limit,
    )
    try:
        limit = max(1, int(raw_limit))
    except (TypeError, ValueError):
        limit = int(default_limit)
    lock_path = registry_lock_path(registry_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        if not acquire_exclusive_lock(lock):
            return False
        entry = load_registry(registry_path).get(key, {})
        fcntl.flock(lock, fcntl.LOCK_UN)
    if not isinstance(entry, dict):
        return False
    try:
        turn_count = int(entry.get("turn_count") or 0)
    except (TypeError, ValueError):
        turn_count = 0
    return turn_count >= limit


def persist_session_result(
    registry_path: Path,
    key: str,
    chat_name: str,
    role: str,
    result: dict[str, Any],
    model: str,
    reasoning_effort: str,
    sandbox: str,
    workdir: Path,
) -> bool:
    lock_path = registry_lock_path(registry_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock:
        if not acquire_exclusive_lock(lock):
            return False
        registry = load_registry(registry_path)
        update_registry(
            registry,
            key,
            chat_name,
            role,
            result,
            model,
            reasoning_effort,
            sandbox,
            workdir,
        )
        save_registry(registry_path, registry)
        fcntl.flock(lock, fcntl.LOCK_UN)
    return True


def acquire_exclusive_lock(handle: Any, *, timeout_seconds: float | None = None) -> bool:
    """Acquire a short registry lock without stalling incoming chat messages."""
    if timeout_seconds is None:
        timeout_seconds = float(os.environ.get("WECHAT_CODEX_REGISTRY_LOCK_TIMEOUT_SECONDS", "2"))
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError) as exc:
            if isinstance(exc, OSError) and exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


def run_codex_once(
    prompt: str,
    *,
    thread_id: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    workdir: Path,
    web_search: bool = False,
    agentshell_account: str = "",
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as out:
        output_path = Path(out.name)
    codex_bin = resolve_codex_binary()
    if not codex_bin:
        output_path.unlink(missing_ok=True)
        return {
            "ok": False,
            "message": "Codex failed: codex executable was not found in PATH or known local install locations.",
            "thread_id": thread_id,
            "returncode": 127,
            "stderr_tail": "codex executable not found",
            "stdout_tail": "",
            "execution_started": False,
            "tool_activity": False,
        }
    try:
        command = (
            agentshell_codex_command(agentshell_account, [])
            if agentshell_account
            else [codex_bin]
        )
    except (FileNotFoundError, ValueError) as exc:
        output_path.unlink(missing_ok=True)
        return {
            "ok": False,
            "message": f"Codex failed: {exc}",
            "thread_id": thread_id,
            "returncode": 127,
            "stderr_tail": str(exc),
            "stdout_tail": "",
            "execution_started": False,
            "tool_activity": False,
        }
    if web_search:
        # `--search` is a global Codex option and must precede `exec`.
        command.append("--search")
    command += [
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
        proc = run_process_group(
            command,
            input=prompt,
            cwd=workdir,
            timeout=timeout_seconds,
            env=codex_subprocess_env(codex_bin),
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
            **codex_event_evidence(proc.stdout),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.output or "")
        stderr = str(exc.stderr or "")
        return {
            "ok": False,
            "message": "Codex failed: timed out before completing the turn.",
            "thread_id": thread_id,
            "returncode": 124,
            "stderr_tail": (stderr or "timeout")[-2000:],
            "stdout_tail": stdout[-2000:],
            **codex_event_evidence(stdout),
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "message": f"Codex failed: executable not found: {exc.filename or codex_bin}",
            "thread_id": thread_id,
            "returncode": 127,
            "stderr_tail": str(exc),
            "stdout_tail": "",
            "execution_started": False,
            "tool_activity": False,
        }
    finally:
        output_path.unlink(missing_ok=True)


def run_process_group(
    command: list[str],
    *,
    input: str | None,
    cwd: Path,
    timeout: int,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run an agent in its own process group and never orphan descendants."""
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        start_new_session=True,
    )
    previous_handlers: dict[int, Any] = {}

    def terminate_for_parent_signal(signum: int, _frame: Any) -> None:
        terminate_process_group(proc)
        raise SystemExit(128 + int(signum))

    for parent_signal in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        try:
            previous_handlers[parent_signal] = signal.getsignal(parent_signal)
            signal.signal(parent_signal, terminate_for_parent_signal)
        except ValueError:
            # Signal handlers can only be installed by the main thread. The
            # BaseException cleanup below still protects embedded callers.
            previous_handlers.clear()
            break
    try:
        stdout, stderr = proc.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        terminate_process_group(proc)
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output=stdout,
            stderr=stderr,
        ) from exc
    except BaseException:
        terminate_process_group(proc)
        raise
    finally:
        for parent_signal, previous in previous_handlers.items():
            signal.signal(parent_signal, previous)
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def terminate_process_group(proc: subprocess.Popen[str], *, grace_seconds: float = 2.0) -> None:
    """Terminate a wrapper and all native agent descendants without orphans."""
    if proc.poll() is not None:
        return
    try:
        process_group = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        return
    proc.wait(timeout=grace_seconds)


def codex_web_search_enabled(role: str) -> bool:
    """Enable native Responses web search for evidence-gathering turns."""
    configured = os.environ.get("WECHAT_CODEX_WEB_SEARCH")
    if configured is not None:
        return configured.strip().casefold() not in {"0", "false", "no", "off"}
    return str(role or "").strip().casefold() in {
        "worker",
        "research",
        "daily",
        "career_daily",
        "daily_organizer",
    }


def resolve_codex_binary() -> str:
    configured = os.environ.get("WECHAT_CODEX_BIN") or os.environ.get("CODEX_BIN") or ""
    candidates: list[Path] = []
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_absolute() or "/" in configured:
            candidates.append(configured_path)
        else:
            found = shutil.which(configured)
            if found:
                return found
    home = Path.home()
    # tmux/restart-wrapper environments can put ~/bin ahead of nvm. On this
    # workstation ~/bin/codex is a compatibility wrapper that fails unless the
    # real Node-installed Codex is already in PATH, so prefer concrete nvm
    # installs before a generic PATH lookup.
    candidates.extend(sorted((home / ".nvm" / "versions" / "node").glob("*/bin/codex"), reverse=True))
    found = shutil.which("codex")
    if found:
        candidates.append(Path(found))
    candidates.extend(
        [
            home / ".local" / "bin" / "codex",
            Path("/usr/local/bin/codex"),
            home / "bin" / "codex",
        ]
    )
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def codex_subprocess_env(codex_bin: str) -> dict[str, str]:
    env = os.environ.copy()
    bin_dir = str(Path(codex_bin).expanduser().parent)
    current_path = env.get("PATH", "")
    if bin_dir and bin_dir not in current_path.split(os.pathsep):
        env["PATH"] = bin_dir + os.pathsep + current_path
    return env


def parse_thread_id(events: str) -> str:
    for line in str(events or "").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("type") == "thread.started":
            return str(item.get("thread_id") or "")
    return ""


def codex_event_evidence(events: str) -> dict[str, bool]:
    execution_started = False
    tool_activity = False
    for line in str(events or "").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        if event_type.startswith("turn.") or event_type.startswith("item."):
            execution_started = True
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = str(item.get("type") or "").casefold()
        if item_type and item_type not in {"agent_message", "reasoning", "plan"}:
            tool_activity = True
    return {
        "execution_started": execution_started,
        "tool_activity": tool_activity,
    }


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
    same_thread = str(previous.get("thread_id") or "") == str(result.get("thread_id") or "")
    now = datetime.now().isoformat(timespec="seconds")
    registry[key] = {
        "thread_id": result["thread_id"],
        "chat_name": chat_name,
        "role": role,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "sandbox": sandbox,
        "workdir": str(workdir),
        "created_at": (previous.get("created_at") or now) if same_thread else now,
        "last_used_at": now,
        "turn_count": (int(previous.get("turn_count") or 0) + 1) if same_thread else 1,
        "last_resumed": bool(result.get("resumed")),
        "last_fallback_started": bool(result.get("fallback_started")),
        "last_agentshell_account": str(result.get("agentshell_account") or ""),
    }
