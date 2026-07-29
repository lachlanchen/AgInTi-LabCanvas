from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any
from urllib import error, parse, request


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MUSIA_ROOT = PACKAGE_ROOT.parent / "Musia"
DEFAULT_REGISTRY = PACKAGE_ROOT / "output" / "musia" / "session_registry.json"
DEFAULT_STUDIO_URL = "http://127.0.0.1:8767"
TERMINAL_JOB_STATUSES = {"completed", "error", "failed", "fallback", "timeout", "canceled"}


def add_musia_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "music",
        help="Reuse Musia Studio for persistent music and music-video work.",
    )
    commands = parser.add_subparsers(dest="music_command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--musia-root", default=str(DEFAULT_MUSIA_ROOT))
    common.add_argument("--studio-url", default="")
    common.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    common.add_argument("--json", action="store_true")

    for action in ("start", "status", "doctor"):
        command = commands.add_parser(action, parents=[common])
        command.set_defaults(func=cmd_service)

    submit = commands.add_parser(
        "submit",
        parents=[common],
        help="Submit one message to a source-scoped persistent Musia Studio session.",
    )
    submit.add_argument("prompt", nargs="+")
    submit.add_argument("--source-scope", default="cli-default")
    submit.add_argument("--task-id", default="")
    submit.add_argument("--title", default="LabCanvas music")
    submit.add_argument("--mode", choices=["auto", "chat", "worker"], default="worker")
    submit.add_argument("--working-dir", default="")
    submit.add_argument("--wait", action="store_true")
    submit.add_argument("--poll-seconds", type=float, default=5.0)
    submit.add_argument("--timeout", type=float, default=10800.0)
    submit.add_argument(
        "--new-revision",
        action="store_true",
        help="Create a new job after an existing task id only when a revision is explicitly authorized.",
    )
    submit.add_argument("--dry-run", action="store_true")
    submit.set_defaults(func=cmd_submit)

    job = commands.add_parser("job", parents=[common], help="Read one durable Musia Studio job.")
    job.add_argument("job_id")
    job.set_defaults(func=cmd_job)

    wait = commands.add_parser("wait", parents=[common], help="Wait for one durable Musia Studio job.")
    wait.add_argument("job_id")
    wait.add_argument("--poll-seconds", type=float, default=5.0)
    wait.add_argument("--timeout", type=float, default=10800.0)
    wait.set_defaults(func=cmd_wait)

    artifacts = commands.add_parser(
        "artifacts",
        parents=[common],
        help="List artifacts registered to one source-scoped Musia Studio session.",
    )
    artifacts.add_argument("--source-scope", default="cli-default")
    artifacts.add_argument("--session-id", default="")
    artifacts.set_defaults(func=cmd_artifacts)

    artifact = commands.add_parser(
        "artifact",
        parents=[common],
        help="Download one exact registered Musia artifact by id.",
    )
    artifact.add_argument("artifact_id")
    artifact.add_argument("--source-scope", default="cli-default")
    artifact.add_argument("--session-id", default="")
    artifact.add_argument("--output-dir", required=True)
    artifact.set_defaults(func=cmd_artifact)

    mv_pack = commands.add_parser(
        "mv-pack",
        parents=[common],
        help="Delegate a reviewed song-to-Xiaoyunque handoff pack to Musia.",
    )
    mv_pack.add_argument("--audio", required=True)
    mv_pack.add_argument("--title", default="")
    mv_pack.add_argument("--slug", default="")
    mv_pack.add_argument("--output-dir", default="")
    mv_pack.add_argument("--duration", type=float)
    mv_pack.add_argument("--start", type=float)
    mv_pack.add_argument("--ratio", default="")
    mv_pack.add_argument("--mood", default="")
    mv_pack.add_argument("--scene", default="")
    mv_pack.add_argument("--copy-references", action="store_true")
    mv_pack.add_argument("--dry-run", action="store_true")
    mv_pack.set_defaults(func=cmd_mv_pack)


def _root(args: argparse.Namespace) -> Path:
    return Path(args.musia_root).expanduser().resolve()


def _registry(args: argparse.Namespace) -> Path:
    return Path(args.registry).expanduser().resolve()


def studio_url(root: Path, configured: str = "") -> str:
    explicit = str(configured or os.environ.get("LABCANVAS_MUSIA_STUDIO_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    port_file = root / "data" / "runs" / "musia-studio-server.port"
    if port_file.is_file():
        try:
            port = int(port_file.read_text(encoding="utf-8").strip())
            if 1 <= port <= 65535:
                return f"http://127.0.0.1:{port}"
        except (OSError, ValueError):
            pass
    return DEFAULT_STUDIO_URL


def _request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> Any:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise ValueError(f"Musia Studio HTTP {exc.code}: {detail}") from exc
    except (OSError, error.URLError, json.JSONDecodeError) as exc:
        raise ValueError(f"Musia Studio request failed: {exc}") from exc


def _tmux_ready(session: str = "musia-studio") -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def service_status(root: Path, base_url: str) -> dict[str, Any]:
    setup: dict[str, Any] = {}
    error_text = ""
    try:
        response = _request_json(base_url, "/api/setup", timeout=3.0)
        if isinstance(response, dict):
            setup = response
    except ValueError as exc:
        error_text = str(exc)
    return {
        "ok": bool(setup),
        "musia_root": str(root),
        "studio_url": base_url,
        "tmux": _tmux_ready(),
        "setup": setup,
        "error": error_text,
    }


def start_studio(root: Path, base_url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    status = service_status(root, base_url)
    if status["ok"]:
        status["reused"] = True
        return status
    entrypoint = root / "bin" / "musia.js"
    if not entrypoint.is_file():
        raise ValueError(f"Musia CLI is missing: {entrypoint}")
    process = subprocess.run(
        ["node", str(entrypoint), "studio", "--tmux"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    deadline = time.monotonic() + max(1.0, timeout)
    while time.monotonic() < deadline:
        status = service_status(root, base_url)
        if status["ok"]:
            status.update(
                {
                    "reused": False,
                    "start_returncode": process.returncode,
                    "start_stdout": process.stdout.strip(),
                    "start_stderr": process.stderr.strip(),
                }
            )
            return status
        time.sleep(0.5)
    raise ValueError(
        "Musia Studio did not become ready: "
        f"returncode={process.returncode}, stderr={process.stderr.strip()[:300]}"
    )


def scope_key(source_scope: str) -> str:
    normalized = str(source_scope or "cli-default").strip() or "cli-default"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "sessions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "sessions": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "sessions": {}}
    payload.setdefault("version", 1)
    payload.setdefault("sessions", {})
    return payload


def _save_registry(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _session_rows(base_url: str) -> list[dict[str, Any]]:
    response = _request_json(base_url, "/api/chat/sessions")
    return [row for row in response if isinstance(row, dict)] if isinstance(response, list) else []


def ensure_session(
    *,
    root: Path,
    base_url: str,
    registry_path: Path,
    source_scope: str,
    title: str,
    working_dir: str = "",
) -> dict[str, Any]:
    key = scope_key(source_scope)
    registry = _load_registry(registry_path)
    sessions = registry.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
        registry["sessions"] = sessions
    stored = sessions.get(key) if isinstance(sessions.get(key), dict) else {}
    stored_id = str(stored.get("session_id") or "")
    if stored_id:
        for row in _session_rows(base_url):
            if str(row.get("id") or "") == stored_id:
                return row

    resolved_working_dir = (
        Path(working_dir).expanduser().resolve()
        if working_dir
        else (root / "data" / "labcanvas_sessions" / key).resolve()
    )
    resolved_working_dir.mkdir(parents=True, exist_ok=True)
    created = _request_json(
        base_url,
        "/api/chat/sessions",
        method="POST",
        payload={
            "title": f"{title.strip() or 'LabCanvas music'} [{key[:8]}]",
            "working_dir": str(resolved_working_dir),
        },
    )
    if not isinstance(created, dict) or not created.get("id"):
        raise ValueError("Musia Studio did not return a session id")
    sessions[key] = {
        "session_id": str(created["id"]),
        "working_dir": str(resolved_working_dir),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_registry(registry_path, registry)
    return created


def submit_task(
    *,
    root: Path,
    base_url: str,
    registry_path: Path,
    source_scope: str,
    prompt: str,
    task_id: str = "",
    title: str = "LabCanvas music",
    mode: str = "worker",
    working_dir: str = "",
    new_revision: bool = False,
) -> dict[str, Any]:
    start_studio(root, base_url)
    session = ensure_session(
        root=root,
        base_url=base_url,
        registry_path=registry_path,
        source_scope=source_scope,
        title=title,
        working_dir=working_dir,
    )
    message = str(prompt).strip()
    if task_id:
        message = f"LabCanvas task id: {task_id}\n\n{message}"
    task_key = idempotency_key(source_scope, task_id) if task_id else ""
    prompt_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
    registry = _load_registry(registry_path)
    tasks = registry.get("tasks")
    if not isinstance(tasks, dict):
        tasks = {}
        registry["tasks"] = tasks
    prior = tasks.get(task_key) if task_key and isinstance(tasks.get(task_key), dict) else {}
    if prior and not new_revision:
        prior_job_id = str(prior.get("job_id") or "")
        try:
            prior_job = load_job(base_url, prior_job_id) if prior_job_id else {}
        except ValueError:
            prior_job = {}
        if prior_job:
            return {
                "mode": str(prior.get("mode") or mode),
                "session_id": str(prior.get("session_id") or session["id"]),
                "job": prior_job,
                "reused_task": str(prior.get("prompt_hash") or "") == prompt_hash,
                "revision_required": str(prior.get("prompt_hash") or "") != prompt_hash,
                "submitted": False,
            }
    response = _request_json(
        base_url,
        "/api/chat/send",
        method="POST",
        payload={
            "session_id": str(session["id"]),
            "message": message,
            "mode": mode,
            "working_dir": str(session.get("working_dir") or ""),
        },
        timeout=30.0,
    )
    if not isinstance(response, dict):
        raise ValueError("Musia Studio returned an invalid submit response")
    job = response.get("job") if isinstance(response.get("job"), dict) else {}
    if task_key and job.get("id"):
        prior_revisions = (
            list(prior.get("revisions") or [])
            if isinstance(prior, dict)
            else []
        )
        if prior and new_revision:
            prior_revisions.append(
                {
                    "job_id": str(prior.get("job_id") or ""),
                    "prompt_hash": str(prior.get("prompt_hash") or ""),
                    "replaced_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        tasks[task_key] = {
            "session_id": str(response.get("session_id") or session["id"]),
            "job_id": str(job["id"]),
            "mode": str(response.get("mode") or mode),
            "prompt_hash": prompt_hash,
            "revisions": prior_revisions[-10:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_registry(registry_path, registry)
    response["submitted"] = True
    response["reused_task"] = False
    response["revision_required"] = False
    return response


def idempotency_key(source_scope: str, task_id: str) -> str:
    material = f"{scope_key(source_scope)}:{str(task_id or '').strip()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def load_job(base_url: str, job_id: str) -> dict[str, Any]:
    response = _request_json(
        base_url,
        f"/api/job?id={parse.quote(str(job_id), safe='')}",
    )
    if not isinstance(response, dict):
        raise ValueError("Musia Studio returned an invalid job response")
    return response


def wait_for_job(
    base_url: str,
    job_id: str,
    *,
    poll_seconds: float = 5.0,
    timeout: float = 10800.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, timeout)
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = load_job(base_url, job_id)
        if str(last.get("status") or "").casefold() in TERMINAL_JOB_STATUSES:
            return last
        time.sleep(max(0.2, poll_seconds))
    return {
        **last,
        "status": "wait_timeout",
        "job_id": job_id,
        "wait_timeout_seconds": timeout,
    }


def session_id_for_scope(registry_path: Path, source_scope: str) -> str:
    sessions = _load_registry(registry_path).get("sessions")
    if not isinstance(sessions, dict):
        return ""
    row = sessions.get(scope_key(source_scope))
    return str(row.get("session_id") or "") if isinstance(row, dict) else ""


def list_session_artifacts(base_url: str, session_id: str) -> dict[str, Any]:
    response = _request_json(
        base_url,
        f"/api/artifacts?session_id={parse.quote(str(session_id), safe='')}",
    )
    if not isinstance(response, dict):
        raise ValueError("Musia Studio returned an invalid artifact response")
    return response


def download_session_artifact(
    base_url: str,
    session_id: str,
    artifact_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    endpoint = (
        f"{base_url.rstrip('/')}/api/artifact/file?"
        f"session_id={parse.quote(str(session_id), safe='')}&"
        f"artifact_id={parse.quote(str(artifact_id), safe='')}"
    )
    try:
        with request.urlopen(endpoint, timeout=60.0) as response:
            disposition = str(response.headers.get("Content-Disposition") or "")
            filename = artifact_download_filename(disposition, artifact_id)
            body = response.read()
            content_type = str(response.headers.get("Content-Type") or "")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise ValueError(f"Musia artifact HTTP {exc.code}: {detail}") from exc
    except (OSError, error.URLError) as exc:
        raise ValueError(f"Musia artifact download failed: {exc}") from exc
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = (output_dir / filename).resolve()
    if target.parent != output_dir:
        raise ValueError("Musia artifact filename escaped the output directory")
    temporary = target.with_suffix(target.suffix + ".part")
    temporary.write_bytes(body)
    temporary.replace(target)
    return {
        "artifact_id": str(artifact_id),
        "session_id": str(session_id),
        "filename": filename,
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "sha256": hashlib.sha256(body).hexdigest(),
        "content_type": content_type,
    }


def artifact_download_filename(disposition: str, artifact_id: str) -> str:
    match = re.search(
        r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)",
        str(disposition or ""),
        flags=re.IGNORECASE,
    )
    raw = parse.unquote(next((group for group in match.groups() if group), "")) if match else ""
    name = Path(raw).name if raw else f"musia-artifact-{artifact_id}"
    return name if name not in {"", ".", ".."} else f"musia-artifact-{artifact_id}"


def build_mv_pack_command(root: Path, args: argparse.Namespace) -> list[str]:
    command = [
        "node",
        str(root / "bin" / "musia.js"),
        "mv-pack",
        "--audio",
        str(Path(args.audio).expanduser().resolve()),
    ]
    options = (
        ("--title", args.title),
        ("--slug", args.slug),
        ("--output-dir", args.output_dir),
        ("--duration", args.duration),
        ("--start", args.start),
        ("--ratio", args.ratio),
        ("--mood", args.mood),
        ("--scene", args.scene),
    )
    for flag, value in options:
        if value is not None and str(value) != "":
            command.extend([flag, str(value)])
    if args.copy_references:
        command.append("--copy-references")
    return command


def _emit(payload: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload.get("message") or payload.get("status") or ("ok" if payload.get("ok") else "failed"))
        if payload.get("studio_url"):
            print(f"studio: {payload['studio_url']}")
        if payload.get("session_id"):
            print(f"session: {payload['session_id']}")
        if payload.get("job_id"):
            print(f"job: {payload['job_id']}")
    return 0 if payload.get("ok") else 1


def cmd_service(args: argparse.Namespace) -> int:
    root = _root(args)
    base_url = studio_url(root, args.studio_url)
    if args.music_command == "start":
        payload = start_studio(root, base_url)
    else:
        payload = service_status(root, base_url)
        payload["doctor"] = args.music_command == "doctor"
        if args.music_command == "doctor":
            payload["cli_ready"] = (root / "bin" / "musia.js").is_file()
            payload["registry"] = str(_registry(args))
            payload["ok"] = bool(payload["ok"] and payload["cli_ready"])
    return _emit(payload, as_json=args.json)


def cmd_submit(args: argparse.Namespace) -> int:
    root = _root(args)
    base_url = studio_url(root, args.studio_url)
    prompt = " ".join(args.prompt).strip()
    if args.dry_run:
        payload = {
            "ok": True,
            "dry_run": True,
            "studio_url": base_url,
            "source_scope_key": scope_key(args.source_scope),
            "mode": args.mode,
            "task_id": args.task_id,
            "new_revision": bool(args.new_revision),
            "prompt": prompt,
        }
        return _emit(payload, as_json=args.json)
    result = submit_task(
        root=root,
        base_url=base_url,
        registry_path=_registry(args),
        source_scope=args.source_scope,
        prompt=prompt,
        task_id=args.task_id,
        title=args.title,
        mode=args.mode,
        working_dir=args.working_dir,
        new_revision=bool(args.new_revision),
    )
    job = result.get("job") if isinstance(result.get("job"), dict) else {}
    if args.wait and job.get("id"):
        job = wait_for_job(
            base_url,
            str(job["id"]),
            poll_seconds=args.poll_seconds,
            timeout=args.timeout,
        )
    session_id = str(result.get("session_id") or "")
    artifacts = list_session_artifacts(base_url, session_id) if args.wait and session_id else {}
    payload = {
        "ok": not args.wait or str(job.get("status") or "").casefold() == "completed",
        "studio_url": base_url,
        "session_id": session_id,
        "job_id": str(job.get("id") or ""),
        "mode": str(result.get("mode") or args.mode),
        "submitted": bool(result.get("submitted")),
        "reused_task": bool(result.get("reused_task")),
        "revision_required": bool(result.get("revision_required")),
        "job": job,
        "artifacts": artifacts,
    }
    return _emit(payload, as_json=args.json)


def cmd_job(args: argparse.Namespace) -> int:
    base_url = studio_url(_root(args), args.studio_url)
    job = load_job(base_url, args.job_id)
    return _emit(
        {
            "ok": True,
            "studio_url": base_url,
            "job_id": args.job_id,
            "status": str(job.get("status") or ""),
            "job": job,
        },
        as_json=args.json,
    )


def cmd_wait(args: argparse.Namespace) -> int:
    base_url = studio_url(_root(args), args.studio_url)
    job = wait_for_job(
        base_url,
        args.job_id,
        poll_seconds=args.poll_seconds,
        timeout=args.timeout,
    )
    return _emit(
        {
            "ok": str(job.get("status") or "").casefold() == "completed",
            "studio_url": base_url,
            "job_id": args.job_id,
            "status": str(job.get("status") or ""),
            "job": job,
        },
        as_json=args.json,
    )


def cmd_artifacts(args: argparse.Namespace) -> int:
    base_url = studio_url(_root(args), args.studio_url)
    session_id = str(args.session_id or "") or session_id_for_scope(
        _registry(args),
        args.source_scope,
    )
    if not session_id:
        raise ValueError("No Musia Studio session exists for this source scope")
    artifacts = list_session_artifacts(base_url, session_id)
    return _emit(
        {
            "ok": True,
            "studio_url": base_url,
            "session_id": session_id,
            "artifacts": artifacts,
        },
        as_json=args.json,
    )


def cmd_artifact(args: argparse.Namespace) -> int:
    base_url = studio_url(_root(args), args.studio_url)
    session_id = str(args.session_id or "") or session_id_for_scope(
        _registry(args),
        args.source_scope,
    )
    if not session_id:
        raise ValueError("No Musia Studio session exists for this source scope")
    downloaded = download_session_artifact(
        base_url,
        session_id,
        args.artifact_id,
        Path(args.output_dir),
    )
    return _emit(
        {
            "ok": True,
            "studio_url": base_url,
            **downloaded,
        },
        as_json=args.json,
    )


def cmd_mv_pack(args: argparse.Namespace) -> int:
    root = _root(args)
    command = build_mv_pack_command(root, args)
    if args.dry_run:
        return _emit(
            {
                "ok": True,
                "dry_run": True,
                "command": command,
            },
            as_json=args.json,
        )
    process = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return _emit(
        {
            "ok": process.returncode == 0,
            "command": command,
            "returncode": process.returncode,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
        },
        as_json=args.json,
    )
