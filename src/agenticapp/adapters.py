from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import subprocess
from typing import Any
from urllib import parse, request
import webbrowser

from .config import Target, expand_env


class DispatchError(RuntimeError):
    """Raised when a target cannot accept a dispatch."""


@dataclass(frozen=True)
class DispatchResult:
    target: str
    transport: str
    ok: bool
    status: str
    response: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "transport": self.transport,
            "ok": self.ok,
            "status": self.status,
            "response": self.response,
        }


def build_envelope(target: Target, instruction: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    instruction = instruction.strip()
    if not instruction:
        raise DispatchError("Instruction cannot be empty")
    return {
        "target": target.name,
        "kind": target.kind,
        "instruction": instruction,
        "payload": payload or {},
        "metadata": {
            "source": "agenticapp",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def dispatch_target(
    target: Target,
    instruction: str,
    payload: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    timeout: float = 30,
) -> DispatchResult:
    if not target.enabled:
        raise DispatchError(f"Target {target.name!r} is disabled")

    envelope = build_envelope(target, instruction, payload)
    transport = expand_env(target.transport)
    transport_type = str(transport.get("type", "noop"))
    if dry_run:
        return DispatchResult(target.name, transport_type, True, "dry-run", envelope)
    if transport_type == "http_json":
        return _dispatch_http_json(target, transport, envelope, timeout)
    if transport_type == "local_command":
        return _dispatch_local_command(target, transport, envelope, timeout)
    if transport_type == "browser":
        return _dispatch_browser(target, transport, envelope)
    if transport_type == "noop":
        return DispatchResult(target.name, "noop", True, "noop", envelope)
    raise DispatchError(f"Unsupported transport type {transport_type!r} for target {target.name!r}")


def _dispatch_http_json(
    target: Target, transport: dict[str, Any], envelope: dict[str, Any], timeout: float
) -> DispatchResult:
    url = str(transport.get("url", "")).strip()
    if not url:
        raise DispatchError(f"Target {target.name!r} http_json transport requires 'url'")
    headers = {"Content-Type": "application/json", **dict(transport.get("headers") or {})}
    body = json.dumps(envelope).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = _parse_json_or_text(raw)
            return DispatchResult(target.name, "http_json", True, str(response.status), parsed)
    except Exception as exc:  # noqa: BLE001 - preserve stdlib transport errors.
        raise DispatchError(f"HTTP dispatch to {target.name!r} failed: {exc}") from exc


def _dispatch_local_command(
    target: Target, transport: dict[str, Any], envelope: dict[str, Any], timeout: float
) -> DispatchResult:
    command = transport.get("command")
    if isinstance(command, str):
        command = [command]
    if not isinstance(command, list) or not command:
        raise DispatchError(f"Target {target.name!r} local_command transport requires command list")
    proc = subprocess.run(
        [str(part) for part in command],
        input=json.dumps(envelope),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    response = {
        "stdout": _parse_json_or_text(proc.stdout),
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }
    return DispatchResult(target.name, "local_command", proc.returncode == 0, str(proc.returncode), response)


def _dispatch_browser(target: Target, transport: dict[str, Any], envelope: dict[str, Any]) -> DispatchResult:
    url = str(transport.get("url", "")).strip()
    if not url:
        raise DispatchError(f"Target {target.name!r} browser transport requires 'url'")
    query_name = str(transport.get("instruction_param", "agentic_instruction"))
    delimiter = "&" if parse.urlparse(url).query else "?"
    launch_url = f"{url}{delimiter}{parse.urlencode({query_name: envelope['instruction']})}"
    opened = webbrowser.open(launch_url)
    return DispatchResult(target.name, "browser", bool(opened), "opened" if opened else "not-opened", launch_url)


def _parse_json_or_text(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw
