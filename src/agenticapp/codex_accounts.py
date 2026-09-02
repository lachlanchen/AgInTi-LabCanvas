"""Quota-aware AgentShell account selection for Codex runtimes.

The selector is deliberately cache-only.  A separate read-only quota monitor
refreshes the cache, while request handling remains fast and cannot create or
modify AgentShell profiles.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_ROOT = Path(
    os.environ.get("LABCANVAS_AGENTSHELL_PROFILE_ROOT")
    or Path.home() / ".local" / "share" / "agentshell" / "profiles"
).expanduser()
DEFAULT_POOL_CACHE = Path(
    os.environ.get("LABCANVAS_CODEX_ACCOUNT_POOL_CACHE")
    or ROOT
    / "agentic_tools"
    / "wechat_gui_agent"
    / ".private"
    / "codex_account_pool.json"
).expanduser()
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
DEFAULT_CACHE_MAX_AGE_SECONDS = 300.0


def _split_names(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    values = value if not isinstance(value, str) else re.split(r"[,\s]+", value)
    result: list[str] = []
    for item in values:
        name = str(item or "").strip()
        if name and ACCOUNT_RE.fullmatch(name) and name not in result:
            result.append(name)
    return result


def configured_account_allowlist() -> list[str]:
    return _split_names(
        os.environ.get("WECHAT_CODEX_ACCOUNTS")
        or os.environ.get("LABCANVAS_CODEX_ACCOUNTS")
    )


def configured_pinned_account() -> str:
    value = str(
        os.environ.get("WECHAT_CODEX_ACCOUNT")
        or os.environ.get("LABCANVAS_CODEX_ACCOUNT")
        or ""
    ).strip()
    return value if ACCOUNT_RE.fullmatch(value) else ""


def account_pool_enabled() -> bool:
    value = str(os.environ.get("LABCANVAS_CODEX_ACCOUNT_POOL_ENABLED", "1"))
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def discover_agentshell_accounts(
    profile_root: Path = DEFAULT_PROFILE_ROOT,
    *,
    allowlist: Iterable[str] | str | None = None,
) -> list[str]:
    """Return existing saved profiles without invoking profile-management tools."""
    root = Path(profile_root).expanduser()
    allowed = _split_names(allowlist)
    if allowlist is None:
        allowed = configured_account_allowlist()
    allowed_set = set(allowed)
    try:
        children = sorted(root.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return []
    accounts = [
        child.name
        for child in children
        if child.is_dir()
        and ACCOUNT_RE.fullmatch(child.name)
        and (child / "profile.conf").is_file()
        and (not allowed_set or child.name in allowed_set)
    ]
    if allowed:
        order = {name: index for index, name in enumerate(allowed)}
        accounts.sort(key=lambda name: (order.get(name, len(order)), name.casefold()))
    return accounts


def resolve_agent_codex_binary() -> str:
    configured = str(os.environ.get("LABCANVAS_AGENT_CODEX_BIN") or "").strip()
    if configured:
        found = shutil.which(configured)
        candidate = Path(configured).expanduser()
        if found:
            return found
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    found = shutil.which("agent-codex")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "agent-codex"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate.resolve())
    return ""


def agentshell_codex_command(account: str, codex_args: Iterable[str]) -> list[str]:
    if not ACCOUNT_RE.fullmatch(str(account or "")):
        raise ValueError("Invalid AgentShell account name")
    executable = resolve_agent_codex_binary()
    if not executable:
        raise FileNotFoundError("agent-codex executable was not found")
    return [executable, "--account", account, *list(codex_args)]


def load_account_pool_cache(path: Path = DEFAULT_POOL_CACHE) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _decimal(value: Any) -> Decimal:
    try:
        return max(Decimal("0"), Decimal(str(value or "0")))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _status_is_fresh(status: dict[str, Any], max_age_seconds: float) -> bool:
    runtime_unavailable_until = float(status.get("runtime_unavailable_until") or 0)
    if runtime_unavailable_until > time.time():
        return False
    observed = float(status.get("observed_at_epoch") or 0)
    if observed <= 0 or time.time() - observed > max(1.0, max_age_seconds):
        return False
    reset_at = (status.get("window") or {}).get("resets_at")
    return not isinstance(reset_at, (int, float)) or reset_at > time.time()


def mark_codex_account_runtime_unavailable(
    account: str,
    *,
    cache_path: Path = DEFAULT_POOL_CACHE,
    reason: str = "runtime_quota_rejection",
    ttl_seconds: float = 1800.0,
) -> None:
    if not ACCOUNT_RE.fullmatch(str(account or "")):
        return
    payload = load_account_pool_cache(cache_path)
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    status = accounts.get(account) if isinstance(accounts.get(account), dict) else {}
    status = dict(status)
    status["codex_available"] = False
    status["runtime_unavailable_reason"] = reason
    status["runtime_unavailable_until"] = time.time() + max(60.0, ttl_seconds)
    accounts = dict(accounts)
    accounts[account] = status
    payload = dict(payload)
    payload["accounts"] = accounts
    payload["available_count"] = sum(
        1
        for value in accounts.values()
        if isinstance(value, dict)
        and value.get("codex_available")
        and float(value.get("runtime_unavailable_until") or 0) <= time.time()
    )
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _account_rank(status: dict[str, Any], order: int) -> tuple[Any, ...]:
    weekly = bool(status.get("weekly_quota_available"))
    remaining = float(status.get("remaining_percent") or 0)
    credits = status.get("credits") if isinstance(status.get("credits"), dict) else {}
    unlimited = bool(credits.get("unlimited"))
    balance = _decimal(credits.get("balance"))
    # Preserve weekly allocations before consuming purchased credits.
    return (weekly, remaining, unlimited, balance, -order)


def codex_account_candidates(
    *,
    cache_path: Path = DEFAULT_POOL_CACHE,
    profile_root: Path = DEFAULT_PROFILE_ROOT,
    max_age_seconds: float = DEFAULT_CACHE_MAX_AGE_SECONDS,
    exclude: Iterable[str] = (),
) -> list[str]:
    """Return usable profiles in failover order using only the private cache."""
    if not account_pool_enabled():
        return []
    discovered = discover_agentshell_accounts(profile_root)
    excluded = set(_split_names(exclude))
    discovered = [name for name in discovered if name not in excluded]
    pinned = configured_pinned_account()
    if pinned:
        return [pinned] if pinned in discovered else []

    payload = load_account_pool_cache(cache_path)
    statuses = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    ranked: list[tuple[tuple[Any, ...], str]] = []
    unknown: list[str] = []
    for order, account in enumerate(discovered):
        status = statuses.get(account) if isinstance(statuses.get(account), dict) else {}
        if float(status.get("runtime_unavailable_until") or 0) > time.time():
            continue
        if not status or not _status_is_fresh(status, max_age_seconds):
            unknown.append(account)
            continue
        if status.get("ok") and status.get("codex_available"):
            ranked.append((_account_rank(status, order), account))
    ranked.sort(key=lambda item: item[0], reverse=True)
    # Unknown profiles remain eligible after positively available profiles.
    return [account for _, account in ranked] + unknown


def best_cached_codex_status(
    *,
    cache_path: Path = DEFAULT_POOL_CACHE,
    max_age_seconds: float = DEFAULT_CACHE_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    payload = load_account_pool_cache(cache_path)
    statuses = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    candidates = codex_account_candidates(
        cache_path=cache_path,
        max_age_seconds=max_age_seconds,
    )
    for account in candidates:
        status = statuses.get(account)
        if isinstance(status, dict) and status.get("ok"):
            # Account identity stays private; callers need only quota state.
            return dict(status)
    return {}
