from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Any


BIORENDER_MCP_URL = "https://mcp.services.biorender.com/mcp"

DEFAULT_BACKEND_SETTINGS: dict[str, Any] = {
    "agent": {
        "enabled": True,
        "backend": "auto",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "auto",
        "mode": "execute",
        "dynamic_routing": True,
        "fallback_to_aginti": True,
    },
    "aginti": {
        "enabled": True,
        "command": "aginti",
        "workspace": ".",
        "image_provider": "grsai",
        "image_model": "nano-banana-2",
        "image_size": "1K",
        "dry_run": True,
    },
    "biorender": {
        "enabled": False,
        "mcp_url": BIORENDER_MCP_URL,
        "auth_env": "BIORENDER_API_KEY",
        "open_url": "https://app.biorender.com/",
    },
    "writing": {
        "enabled": True,
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        "temperature": 0.75,
        "max_tokens": 480,
        "timeout_seconds": 60,
    },
    "toolchain": {
        "blender": True,
        "openscad": True,
        "cad": True,
        "kicad": True,
        "tex": True,
        "wechat": True,
        "labview": True,
        "aginti_image": True,
        "biorender": False,
        "target_registry": True,
    },
    "figure": {
        "rows": 2,
        "cols": 3,
        "cell_size": 240,
        "border": 4,
    },
}


def load_backend_settings(path: str | Path) -> dict[str, Any]:
    settings_path = Path(path)
    if not settings_path.exists():
        return default_backend_settings()
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Backend settings must be a JSON object")
    return merge_settings(default_backend_settings(), data)


def save_backend_settings(path: str | Path, settings: dict[str, Any]) -> dict[str, Any]:
    merged = merge_settings(default_backend_settings(), settings)
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return merged


def default_backend_settings() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_BACKEND_SETTINGS))


def merge_settings(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


def backend_status(settings: dict[str, Any], project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    agent = settings.get("agent", {}) if isinstance(settings.get("agent"), dict) else {}
    aginti = settings.get("aginti", {}) if isinstance(settings.get("aginti"), dict) else {}
    biorender = settings.get("biorender", {}) if isinstance(settings.get("biorender"), dict) else {}
    writing = settings.get("writing", {}) if isinstance(settings.get("writing"), dict) else {}
    aginti_command = str(aginti.get("command") or "aginti")
    workspace = _resolve_from_root(root, str(aginti.get("workspace") or "."))
    biorender_env = str(biorender.get("auth_env") or "BIORENDER_API_KEY")
    writing_key_env = str(writing.get("api_key_env") or "DEEPSEEK_API_KEY")
    return {
        "ok": True,
        "agent": {
            "enabled": bool(agent.get("enabled", True)),
            "backend": str(agent.get("backend") or "auto"),
            "model": str(agent.get("model") or "gpt-5.6-sol"),
            "reasoning_effort": str(agent.get("reasoning_effort") or "auto"),
            "mode": str(agent.get("mode") or "execute"),
            "dynamic_routing": bool(agent.get("dynamic_routing", True)),
            "codex_path": _resolve_codex_binary(),
        },
        "aginti": {
            "enabled": bool(aginti.get("enabled", True)),
            "command": aginti_command,
            "command_path": shutil.which(shlex.split(aginti_command)[0] if shlex.split(aginti_command) else aginti_command) or "",
            "workspace": str(workspace),
            "workspace_exists": workspace.exists(),
            "image_provider": str(aginti.get("image_provider") or "grsai"),
            "image_model": str(aginti.get("image_model") or "nano-banana-2"),
            "dry_run": bool(aginti.get("dry_run", True)),
        },
        "biorender": {
            "enabled": bool(biorender.get("enabled", False)),
            "mcp_url": str(biorender.get("mcp_url") or BIORENDER_MCP_URL),
            "auth_env": biorender_env,
            "auth_env_present": bool(os.environ.get(biorender_env)),
            "open_url": str(biorender.get("open_url") or "https://app.biorender.com/"),
        },
        "writing": {
            "enabled": bool(writing.get("enabled", True)),
            "provider": str(writing.get("provider") or "deepseek"),
            "base_url": str(writing.get("base_url") or "https://api.deepseek.com"),
            "model": str(writing.get("model") or "deepseek-v4-flash"),
            "api_key_env": writing_key_env,
            "api_key_env_present": bool(os.environ.get(writing_key_env)),
        },
        "toolchain": settings.get("toolchain", {}),
    }


def run_aginti_image_request(
    prompt: str,
    output_dir: str | Path,
    *,
    settings: dict[str, Any],
    project_root: str | Path,
    output_stem: str = "paper-grid-icons",
    timeout: float = 90,
) -> dict[str, Any]:
    aginti = settings.get("aginti", {}) if isinstance(settings.get("aginti"), dict) else {}
    if not bool(aginti.get("enabled", True)):
        return {"ok": False, "blocked": True, "reason": "AgInTi backend is disabled."}
    command = shlex.split(str(aginti.get("command") or "aginti"))
    if not command:
        return {"ok": False, "blocked": True, "reason": "AgInTi command is empty."}
    if shutil.which(command[0]) is None:
        return {"ok": False, "blocked": True, "reason": f"AgInTi command not found: {command[0]}"}

    root = Path(project_root).resolve()
    requested_output = Path(output_dir)
    if requested_output.is_absolute():
        try:
            output_arg = requested_output.resolve().relative_to(root).as_posix()
        except ValueError:
            output_arg = str(requested_output)
    else:
        output_arg = requested_output.as_posix()
    args = [
        *command,
        "image",
        "--json",
        "--provider",
        str(aginti.get("image_provider") or "grsai"),
        "--model",
        str(aginti.get("image_model") or "nano-banana-2"),
        "--format",
        "png",
        "--image-size",
        str(aginti.get("image_size") or "1K"),
        "--output-dir",
        output_arg,
        "--output-stem",
        output_stem,
    ]
    if bool(aginti.get("dry_run", True)):
        args.append("--dry-run")
    args.append(prompt)

    process = subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=timeout, check=False)
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": process.stdout.strip(), "stderr": process.stderr.strip()}
    payload["command"] = redact_command(args)
    payload["returncode"] = process.returncode
    if process.returncode != 0:
        payload.setdefault("ok", False)
        payload.setdefault("error", process.stderr.strip() or "AgInTi image command failed.")
    return payload


def redact_command(args: list[str]) -> list[str]:
    return ["<prompt>" if index == len(args) - 1 else value for index, value in enumerate(args)]


def _resolve_from_root(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def _resolve_codex_binary() -> str:
    configured = os.environ.get("LABCANVAS_CODEX_BIN") or os.environ.get("CODEX_BIN") or ""
    if configured:
        found = shutil.which(configured)
        if found:
            return found
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    candidates = sorted((Path.home() / ".nvm" / "versions" / "node").glob("*/bin/codex"), reverse=True)
    found = shutil.which("codex")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""
