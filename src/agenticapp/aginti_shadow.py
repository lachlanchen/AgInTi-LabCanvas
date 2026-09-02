"""Private, non-delivering AgInTi reviews of completed Codex task turns."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ROOT = ROOT / "agentic_tools" / "wechat_gui_agent" / ".private" / "aginti_shadow"
PENDING_DIR = PRIVATE_ROOT / "pending"
RESULT_DIR = PRIVATE_ROOT / "results"
ELIGIBLE_ROLES = {"worker", "research", "daily", "career_daily", "daily_organizer", "workspace"}
SENSITIVE_MARKERS = (
    "password=",
    "api_key=",
    "access_token=",
    "refresh_token=",
    "private key",
    "BEGIN OPENSSH PRIVATE KEY",
)
_BACKGROUND_PROCESSES: list[subprocess.Popen[str]] = []


def shadow_enabled() -> bool:
    value = str(os.environ.get("LABCANVAS_AGINTI_SHADOW_ENABLED", "1"))
    return value.strip().casefold() not in {"0", "false", "no", "off"}


def eligible_for_shadow(prompt: str, result: dict[str, Any], role: str) -> bool:
    if not shadow_enabled() or role not in ELIGIBLE_ROLES or not result.get("ok"):
        return False
    text = str(prompt or "")
    return not any(marker.casefold() in text.casefold() for marker in SENSITIVE_MARKERS)


def enqueue_codex_shadow_review(
    prompt: str,
    result: dict[str, Any],
    *,
    role: str,
    launch: bool = False,
) -> dict[str, Any]:
    """Queue a bounded review packet; never expose it to a chat transport."""
    if not eligible_for_shadow(prompt, result, role):
        return {"queued": False, "reason": "not_eligible"}
    observed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    digest = hashlib.sha256(
        (observed + "\0" + prompt + "\0" + str(result.get("message") or "")).encode("utf-8")
    ).hexdigest()[:20]
    payload = {
        "version": 1,
        "id": digest,
        "created_at": observed,
        "role": role,
        "source_backend": "codex",
        "prompt": str(prompt or "")[-12000:],
        "codex_result": str(result.get("message") or "")[-12000:],
        "contract": {
            "execute_tools": False,
            "send_output": False,
            "external_actions": False,
        },
    }
    PENDING_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = PENDING_DIR / f"{digest}.json"
    _write_private_json(path, payload)
    if launch:
        _launch_processor()
    return {"queued": True, "id": digest}


def process_one() -> dict[str, Any]:
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (PRIVATE_ROOT / "processor.lock").open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ok": True, "processed": False, "reason": "already_running"}
        return _process_one_locked()


def _process_one_locked() -> dict[str, Any]:
    pending = sorted(PENDING_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime) if PENDING_DIR.exists() else []
    if not pending:
        return {"ok": True, "processed": False}
    path = pending[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return {"ok": False, "processed": False, "reason": "invalid_packet"}
    executable = shutil.which("aginti")
    if not executable:
        return {"ok": False, "processed": False, "reason": "aginti_not_found"}
    review_prompt = _review_prompt(payload)
    command = [
        executable,
        "--no-auto-update",
        "--provider",
        str(os.environ.get("LABCANVAS_AGINTI_SHADOW_PROVIDER") or "deepseek"),
        "--routing",
        "fast",
        "--main-reasoning",
        "low",
        "--sandbox-mode",
        "docker-readonly",
        "--no-shell",
        "--no-file-tools",
        "--no-web-search",
        "--no-mcp",
        "--no-parallel-scouts",
        "--no-auxiliary-tools",
        "--no-scs",
        review_prompt,
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=max(30, int(os.environ.get("LABCANVAS_AGINTI_SHADOW_TIMEOUT_SECONDS", "180"))),
            check=False,
        )
        raw_review = (proc.stdout or "")[-16000:]
        parsed_review = _extract_review_json(raw_review)
        review = {
            **payload,
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "review": parsed_review,
            "raw_review_tail": raw_review[-4000:] if not parsed_review else "",
            "error": (proc.stderr or "")[-2000:] if proc.returncode else "",
        }
    except subprocess.TimeoutExpired:
        review = {
            **payload,
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": False,
            "returncode": 124,
            "review": "",
            "error": "shadow review timed out",
        }
    RESULT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_private_json(RESULT_DIR / path.name, review)
    path.unlink(missing_ok=True)
    return {"ok": bool(review["ok"]), "processed": True, "id": payload.get("id")}


def _review_prompt(payload: dict[str, Any]) -> str:
    return f"""You are privately evaluating AgInTi against a completed Codex task.
Do not call tools, access files, change state, or address the end user. Analyze only the bounded text below.
Return concise JSON with keys: task_understanding, strengths, missed_requirements, safer_or_faster_approach, reusable_agent_improvements.

TASK ROLE: {payload.get('role')}
TASK:
{payload.get('prompt')}

CODEX RESULT:
{payload.get('codex_result')}
"""


def _launch_processor() -> None:
    _BACKGROUND_PROCESSES[:] = [
        process for process in _BACKGROUND_PROCESSES if process.poll() is None
    ]
    process = subprocess.Popen(
        [sys.executable, "-m", "agenticapp.aginti_shadow", "once"],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    _BACKGROUND_PROCESSES.append(process)


def _extract_review_json(value: str) -> dict[str, Any]:
    required = {
        "task_understanding",
        "strengths",
        "missed_requirements",
        "safer_or_faster_approach",
        "reusable_agent_improvements",
    }
    for line in reversed(str(value or "").splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and required.issubset(payload):
            return {key: payload.get(key) for key in sorted(required)}
    return {}


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"once", "loop"}:
        print("usage: python -m agenticapp.aginti_shadow once|loop", file=sys.stderr)
        return 2
    if sys.argv[1] == "loop":
        interval = max(5.0, float(os.environ.get("LABCANVAS_AGINTI_SHADOW_POLL_SECONDS", "20")))
        while True:
            process_one()
            time.sleep(interval)
    result = process_one()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
