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
from typing import Any, Iterable, Iterator


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


def paid_codex_credits_allowed() -> bool:
    from .backends import load_model_policy

    return load_model_policy().get("codex", {}).get("allow_paid_credits") is True


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
    if observed <= 0 or not 0 <= time.time() - observed <= max(1.0, max_age_seconds):
        return False
    reset_at = (status.get("window") or {}).get("resets_at")
    return not isinstance(reset_at, (int, float)) or reset_at > time.time()


def mark_codex_account_runtime_unavailable(
    account: str,
    *,
    cache_path: Path = DEFAULT_POOL_CACHE,
    reason: str = "runtime_quota_rejection",
    ttl_seconds: float = 1800.0,
    quota_pool: str = "regular",
) -> None:
    if not ACCOUNT_RE.fullmatch(str(account or "")):
        return
    payload = load_account_pool_cache(cache_path)
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    status = accounts.get(account) if isinstance(accounts.get(account), dict) else {}
    status = dict(status)
    if quota_pool == "reserve":
        status["reserve_runtime_unavailable_until"] = time.time() + max(60.0, ttl_seconds)
    else:
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
        discovered = [name for name in discovered if name == pinned]
    allow_credits = paid_codex_credits_allowed()

    payload = load_account_pool_cache(cache_path)
    statuses = payload.get("accounts") if isinstance(payload.get("accounts"), dict) else {}
    ranked: list[tuple[tuple[Any, ...], str]] = []
    unknown: list[str] = []
    for order, account in enumerate(discovered):
        status = statuses.get(account) if isinstance(statuses.get(account), dict) else {}
        if float(status.get("runtime_unavailable_until") or 0) > time.time():
            continue
        if not status or not _status_is_fresh(status, max_age_seconds):
            if allow_credits:
                unknown.append(account)
            continue
        if (status.get("ok") and status.get("codex_available")
                and (allow_credits or float(status.get("remaining_percent") or 0) > 0)):
            ranked.append((_account_rank(status, order), account))
    ranked.sort(key=lambda item: item[0], reverse=True)
    # Unknown profiles may be tried only when the operator allows paid usage.
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
    reserves = codex_reserve_candidates(cache_path=cache_path, max_age_seconds=max_age_seconds)
    if reserves:
        status = dict(statuses[reserves[0]["account"]])
        reserve = status["reserve"]
        status.update({"normal_remaining_percent": status.get("remaining_percent"),
                       "remaining_percent": reserve["remaining_percent"],
                       "window": reserve.get("window", {}), "quota_pool": "reserve",
                       "model": reserve["model"], "codex_available": True})
        return status
    return {}


def codex_reserve_candidates(
    *,
    cache_path: Path = DEFAULT_POOL_CACHE,
    profile_root: Path = DEFAULT_PROFILE_ROOT,
    max_age_seconds: float = DEFAULT_CACHE_MAX_AGE_SECONDS,
) -> list[dict[str, str]]:
    """Use only an observed reserve allowance, never infer one from exhaustion."""
    if not account_pool_enabled():
        return []
    from .backends import load_model_policy

    policy = load_model_policy().get("codex", {})
    if not policy.get("reserve_enabled", False):
        return []
    reserve_model = str(policy.get("reserve_model") or "gpt-5.6-luna")
    statuses = load_account_pool_cache(cache_path).get("accounts", {})
    pinned = configured_pinned_account()
    now = time.time()
    candidates = []
    for account in discover_agentshell_accounts(profile_root):
        if pinned and pinned != account:
            continue
        status = statuses.get(account) or {}
        reserve = status.get("reserve") or {}
        age = now - float(status.get("observed_at_epoch") or 0)
        if not status.get("ok") or not 0 <= age <= max_age_seconds:
            continue
        # A quota rejection may precede the next cache refresh. It blocks the
        # normal pool, not the independently metered reserve pool.
        rejected = (
            float(status.get("runtime_unavailable_until") or 0) > now
            and status.get("runtime_unavailable_reason") == "runtime_quota_rejection"
        )
        if float(status.get("remaining_percent") or 0) > 0 and not rejected:
            continue
        if float(status.get("reserve_runtime_unavailable_until") or 0) > now:
            continue
        reset_at = (reserve.get("window") or {}).get("resets_at")
        if isinstance(reset_at, (int, float)) and reset_at <= now:
            continue
        if (reserve.get("model") != reserve_model or not reserve.get("available")
                or float(reserve.get("remaining_percent") or 0) <= 0):
            continue
        candidates.append((float(reserve["remaining_percent"]), account))
    candidates.sort(reverse=True)
    return [{"account": account, "model": reserve_model, "quota_pool": "reserve"}
            for _, account in candidates]


def codex_account_attempts(accounts: list[str], model: str) -> Iterator[dict[str, str]]:
    """Normal accounts first, then reserve after safe runtime quota rejections."""
    if not accounts:
        reserves = codex_reserve_candidates()
        if reserves:
            yield from reserves
            return
    for account in accounts or ([""] if paid_codex_credits_allowed() else []):
        yield {"account": account, "model": model, "quota_pool": "regular"}
    # Evaluate lazily: callers record quota rejection before asking for the
    # next attempt. They must stop iterating if an answer or tool has started.
    yield from codex_reserve_candidates()
