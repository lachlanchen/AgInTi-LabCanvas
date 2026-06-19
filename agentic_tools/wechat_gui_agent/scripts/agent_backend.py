"""Pluggable agent backend for the WeChat chatops scripts.

Historically these scripts shelled out to the Codex CLI (`codex exec`). This
module keeps Codex working while adding the Claude Code CLI (`claude -p`) as an
alternative, selected per-config or via the ``WECHAT_AGENT_BACKEND`` env var.

Both backends take a single prompt string and return the model's text output.
The helpers never prompt interactively, so they are safe to run head-less inside
the tmux supervisor panes.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Tools the read-only monitor must never be able to invoke, even via prompt
# injection from an untrusted group message. ``--disallowedTools`` is a hard
# block in Claude Code regardless of the permission mode.
_CLAUDE_READONLY_BLOCK = "Bash Edit Write MultiEdit NotebookEdit"


def select_backend(config: dict[str, Any] | None = None) -> str:
    """Resolve the agent backend name ("codex" or "claude")."""
    if config:
        value = config.get("agent_backend") or config.get("backend")
        if value:
            return str(value).strip().lower()
    return (os.environ.get("WECHAT_AGENT_BACKEND") or "codex").strip().lower()


def run_agent(
    prompt: str,
    *,
    backend: str,
    cwd: Path,
    timeout: int,
    writable: bool = False,
    model: str = "",
    reasoning: str = "low",
) -> str:
    """Run the configured agent and return its text output (or "" on failure)."""
    if backend == "claude":
        return _run_claude(prompt, cwd=cwd, timeout=timeout, writable=writable, model=model)
    return _run_codex(
        prompt, cwd=cwd, timeout=timeout, writable=writable, model=model, reasoning=reasoning
    )


def _run_codex(
    prompt: str,
    *,
    cwd: Path,
    timeout: int,
    writable: bool,
    model: str,
    reasoning: str,
) -> str:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as out:
        output_path = Path(out.name)
    command = [
        "codex",
        "exec",
        "-m",
        model or "gpt-5.5",
        "-c",
        f'model_reasoning_effort="{reasoning}"',
        "--sandbox",
        "workspace-write" if writable else "read-only",
        "-C",
        str(cwd),
        "-o",
        str(output_path),
        prompt,
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
        if proc.returncode != 0:
            return ""
        return output_path.read_text(encoding="utf-8", errors="replace").strip()
    except subprocess.TimeoutExpired:
        return ""
    finally:
        output_path.unlink(missing_ok=True)


def _run_claude(
    prompt: str,
    *,
    cwd: Path,
    timeout: int,
    writable: bool,
    model: str,
) -> str:
    command = ["claude", "-p", prompt, "--output-format", "text"]
    if model:
        command += ["--model", model]
    # bypassPermissions never prompts, so the head-less panes never hang. For the
    # read-only monitor we additionally hard-block mutating/exec tools.
    command += ["--permission-mode", "bypassPermissions"]
    if not writable:
        command += ["--disallowedTools", _CLAUDE_READONLY_BLOCK]
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout, cwd=str(cwd)
        )
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()
