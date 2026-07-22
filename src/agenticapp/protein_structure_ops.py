from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Any
from urllib import error, request


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PACKAGE_ROOT / "external" / "ProteinStructure"
DEFAULT_WORKSPACE = PACKAGE_ROOT.parent / "ProteinStructure"
SCRIPT_ROOT = SOURCE_ROOT / "scripts" / "alphafold_server"
BROWSER_STACK = (
    PACKAGE_ROOT
    / "agentic_tools"
    / "protein_structure_agent"
    / "scripts"
    / "alphafold_browser_stack.sh"
)
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_NOVNC_URL = (
    "http://127.0.0.1:6187/vnc.html?"
    "host=127.0.0.1&port=6187&autoconnect=1&resize=scale"
)


def add_protein_structure_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "protein",
        help="Reuse the ProteinStructure AlphaFold browser and analysis pipeline.",
    )
    commands = parser.add_subparsers(dest="protein_command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--workspace",
        default=str(DEFAULT_WORKSPACE),
        help="Artifact workspace. Default: sibling ../ProteinStructure.",
    )
    common.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    for action in ("start", "restart", "stop", "status", "fit"):
        command = commands.add_parser(action, parents=[common], help=f"{action.title()} the AlphaFold browser stack.")
        command.set_defaults(func=cmd_browser)

    screenshot = commands.add_parser("screenshot", parents=[common], help="Capture the visible AlphaFold noVNC desktop.")
    screenshot.add_argument("--output", default="", help="PNG destination under the workspace by default.")
    screenshot.set_defaults(func=cmd_screenshot)

    webgl = commands.add_parser("webgl", parents=[common], help="Run the existing AlphaFold WebGL readiness check.")
    webgl.set_defaults(func=cmd_webgl)

    open_page = commands.add_parser("open", parents=[common], help="Navigate the persistent browser to AlphaFold Server.")
    open_page.set_defaults(func=cmd_open)

    submit = commands.add_parser("submit", parents=[common], help="Submit protein FASTA jobs with the existing browser tool.")
    submit.add_argument("fastas", nargs="+")
    submit.add_argument("--dry-run", action="store_true")
    submit.add_argument("--log", default="")
    submit.set_defaults(func=cmd_submit)

    submit_json = commands.add_parser("submit-json", parents=[common], help="Submit AlphaFold JSON jobs with the existing browser tool.")
    submit_json.add_argument("json_files", nargs="+")
    submit_json.add_argument("--dry-run", action="store_true")
    submit_json.add_argument("--log", default="")
    submit_json.set_defaults(func=cmd_submit_json)

    submit_mixed = commands.add_parser("submit-mixed", parents=[common], help="Submit mixed-molecule JSON jobs with the existing browser tool.")
    submit_mixed.add_argument("json_files", nargs="+")
    submit_mixed.add_argument("--dry-run", action="store_true")
    submit_mixed.add_argument("--log", default="")
    submit_mixed.set_defaults(func=cmd_submit_mixed)

    poll = commands.add_parser("poll", parents=[common], help="Poll history and optionally download completed results.")
    poll.add_argument("--download", action="store_true")
    poll.add_argument("--only", action="append", default=[])
    poll.add_argument("--all-pages", action="store_true")
    poll.add_argument("--clear-local-form", action="store_true")
    poll.add_argument("--out-dir", default="")
    poll.add_argument("--history", default="")
    poll.add_argument("--name-map", default="")
    poll.add_argument("--log", default="")
    poll.set_defaults(func=cmd_poll)

    metrics = commands.add_parser("metrics", parents=[common], help="Extract compact or detailed metrics from downloaded result zips.")
    metrics.add_argument("--results-dir", default="references/alphafold_server_results")
    metrics.add_argument("--out", default="references/alphafold_server_results/result_metrics.tsv")
    metrics.add_argument("--out-dir", default="references/alphafold_server_results")
    metrics.add_argument("--all-models", action="store_true")
    metrics.add_argument("--detailed", action="store_true")
    metrics.set_defaults(func=cmd_metrics)

    render = commands.add_parser("render", parents=[common], help="Render existing AlphaFold figures and/or CIF backbones.")
    render.add_argument("kind", nargs="?", default="all", choices=["all", "figures", "backbones"])
    render.add_argument("--results-dir", default="references/alphafold_server_results")
    render.add_argument("--out-dir", default="alphafold-results/figures")
    render.add_argument("--model", type=int, default=0)
    render.set_defaults(func=cmd_render)

    capture = commands.add_parser("capture", parents=[common], help="Capture AlphaFold result pages with the existing CDP tool.")
    capture.add_argument("--out-dir", default="alphafold-results/screenshots")
    capture.add_argument("--local-name", action="append", default=[])
    capture.add_argument("--width", type=int, default=1440)
    capture.add_argument("--height", type=int, default=1000)
    capture.add_argument("--name-map", default="")
    capture.add_argument("--min-viewer-score", type=float, default=0.0)
    capture.add_argument("--viewer-timeout", type=float, default=45.0)
    capture.set_defaults(func=cmd_capture)

    runbook = commands.add_parser("runbook", parents=[common], help="Print the canonical ProteinStructure browser runbook path.")
    runbook.set_defaults(func=cmd_runbook)


def _workspace(args: argparse.Namespace) -> Path:
    return Path(args.workspace).expanduser().resolve()


def _ensure_layout(workspace: Path) -> None:
    if not SOURCE_ROOT.is_dir():
        raise ValueError(f"ProteinStructure submodule is missing: {SOURCE_ROOT}")
    if not SCRIPT_ROOT.is_dir():
        raise ValueError(f"AlphaFold scripts are missing: {SCRIPT_ROOT}")
    workspace.mkdir(parents=True, exist_ok=True)


def _probe_json(url: str) -> Any:
    try:
        with request.urlopen(url, timeout=3) as response:
            return json.load(response)
    except (OSError, error.URLError, json.JSONDecodeError):
        return None


def _probe_url(url: str) -> bool:
    try:
        with request.urlopen(url, timeout=3) as response:
            return 200 <= int(response.status) < 400
    except (OSError, error.URLError):
        return False


def _tmux_ready(session: str = "labcanvas-protein-structure") -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def browser_status(workspace: Path) -> dict[str, Any]:
    version = _probe_json(f"{DEFAULT_CDP_URL}/json/version")
    pages = _probe_json(f"{DEFAULT_CDP_URL}/json")
    page_rows = []
    if isinstance(pages, list):
        page_rows = [
            {
                "title": str(page.get("title") or ""),
                "url": str(page.get("url") or ""),
                "type": str(page.get("type") or ""),
            }
            for page in pages
            if isinstance(page, dict) and page.get("type") == "page"
        ]
    return {
        "ok": bool(version) and _probe_url(DEFAULT_NOVNC_URL),
        "source_root": str(SOURCE_ROOT),
        "workspace": str(workspace),
        "profile": str(Path.home() / ".cache" / "alphafold-server-chrome"),
        "tmux": _tmux_ready(),
        "cdp_url": DEFAULT_CDP_URL,
        "cdp_ready": bool(version),
        "browser": version or {},
        "pages": page_rows,
        "novnc_url": DEFAULT_NOVNC_URL,
        "novnc_ready": _probe_url(DEFAULT_NOVNC_URL),
    }


def _emit(payload: dict[str, Any], as_json: bool, label: str) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(label)
        if payload.get("novnc_url"):
            print(f"noVNC: {payload['novnc_url']}")
        if payload.get("workspace"):
            print(f"workspace: {payload['workspace']}")
    return 0 if payload.get("ok") else 1


def _run_existing(
    script_name: str,
    arguments: list[str],
    *,
    workspace: Path,
    as_json: bool,
) -> int:
    _ensure_layout(workspace)
    script = SCRIPT_ROOT / script_name
    if not script.is_file():
        raise ValueError(f"ProteinStructure script is missing: {script}")
    command = [os.environ.get("PYTHON", "python3"), str(script), *arguments]
    process = subprocess.run(command, cwd=workspace, capture_output=True, text=True, check=False)
    payload = {
        "ok": process.returncode == 0,
        "script": str(script),
        "workspace": str(workspace),
        "command": command,
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
    }
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if process.stdout:
            print(process.stdout, end="" if process.stdout.endswith("\n") else "\n")
        if process.stderr:
            print(process.stderr, end="" if process.stderr.endswith("\n") else "\n", file=os.sys.stderr)
    return process.returncode


def cmd_browser(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    _ensure_layout(workspace)
    env = {**os.environ, "PROTEIN_STRUCTURE_WORKSPACE": str(workspace)}
    process = subprocess.run(
        [str(BROWSER_STACK), args.protein_command],
        cwd=PACKAGE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = browser_status(workspace)
    payload.update(
        {
            "action": args.protein_command,
            "control_returncode": process.returncode,
            "control_stdout": process.stdout.strip(),
            "control_stderr": process.stderr.strip(),
        }
    )
    if args.protein_command == "stop":
        payload["ok"] = process.returncode == 0 and not payload["tmux"]
    else:
        payload["ok"] = process.returncode == 0 and (
            payload["ok"] if args.protein_command in {"start", "restart", "fit"} else True
        )
    return _emit(payload, args.json, f"ProteinStructure browser: {args.protein_command}")


def cmd_screenshot(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    _ensure_layout(workspace)
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else workspace / "alphafold-results" / "screenshots" / "labcanvas_alphafold_desktop.png"
    )
    env = {**os.environ, "PROTEIN_STRUCTURE_WORKSPACE": str(workspace)}
    process = subprocess.run(
        [str(BROWSER_STACK), "screenshot", str(output)],
        cwd=PACKAGE_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = {
        "ok": process.returncode == 0 and output.is_file() and output.stat().st_size > 0,
        "workspace": str(workspace),
        "screenshot": str(output),
        "returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
    }
    return _emit(payload, args.json, f"AlphaFold desktop screenshot: {output}")


def cmd_webgl(args: argparse.Namespace) -> int:
    return _run_existing("check_webgl.py", [], workspace=_workspace(args), as_json=args.json)


def cmd_open(args: argparse.Namespace) -> int:
    return _run_existing("open_alphafold.py", [], workspace=_workspace(args), as_json=args.json)


def _optional(arguments: list[str], flag: str, value: str) -> None:
    if value:
        arguments.extend([flag, value])


def cmd_submit(args: argparse.Namespace) -> int:
    values = [str(Path(value).expanduser().resolve()) for value in args.fastas]
    _optional(values, "--log", args.log)
    if args.dry_run:
        values.append("--dry-run")
    return _run_existing("submit_jobs.py", values, workspace=_workspace(args), as_json=args.json)


def cmd_submit_json(args: argparse.Namespace) -> int:
    values = [str(Path(value).expanduser().resolve()) for value in args.json_files]
    _optional(values, "--log", args.log)
    if args.dry_run:
        values.append("--dry-run")
    return _run_existing("submit_json_jobs.py", values, workspace=_workspace(args), as_json=args.json)


def cmd_submit_mixed(args: argparse.Namespace) -> int:
    values = [str(Path(value).expanduser().resolve()) for value in args.json_files]
    _optional(values, "--log", args.log)
    if args.dry_run:
        values.append("--dry-run")
    return _run_existing("submit_mixed_jobs.py", values, workspace=_workspace(args), as_json=args.json)


def cmd_poll(args: argparse.Namespace) -> int:
    values: list[str] = []
    for name in args.only:
        values.extend(["--only", name])
    for enabled, flag in (
        (args.download, "--download"),
        (args.all_pages, "--all-pages"),
        (args.clear_local_form, "--clear-local-form"),
    ):
        if enabled:
            values.append(flag)
    for flag, value in (
        ("--out-dir", args.out_dir),
        ("--history", args.history),
        ("--name-map", args.name_map),
        ("--log", args.log),
    ):
        _optional(values, flag, value)
    return _run_existing("poll_and_download.py", values, workspace=_workspace(args), as_json=args.json)


def cmd_metrics(args: argparse.Namespace) -> int:
    if args.detailed:
        values = ["--results-dir", args.results_dir, "--out-dir", args.out_dir]
        script = "extract_detailed_metrics.py"
    else:
        values = ["--results-dir", args.results_dir, "--out", args.out]
        if args.all_models:
            values.append("--all-models")
        script = "extract_metrics.py"
    return _run_existing(script, values, workspace=_workspace(args), as_json=args.json)


def cmd_render(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    scripts = []
    if args.kind in {"all", "figures"}:
        scripts.append("render_figures.py")
    if args.kind in {"all", "backbones"}:
        scripts.append("render_cif_backbones.py")
    result = 0
    for script in scripts:
        code = _run_existing(
            script,
            ["--results-dir", args.results_dir, "--out-dir", args.out_dir, "--model", str(args.model)],
            workspace=workspace,
            as_json=args.json,
        )
        result = result or code
    return result


def cmd_capture(args: argparse.Namespace) -> int:
    values = [
        "--out-dir",
        args.out_dir,
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--min-viewer-score",
        str(args.min_viewer_score),
        "--viewer-timeout",
        str(args.viewer_timeout),
    ]
    _optional(values, "--name-map", args.name_map)
    for name in args.local_name:
        values.extend(["--local-name", name])
    return _run_existing("capture_screenshots.py", values, workspace=_workspace(args), as_json=args.json)


def cmd_runbook(args: argparse.Namespace) -> int:
    path = SOURCE_ROOT / "references" / "alphafold_server_jobs" / "browser_automation_runbook.md"
    payload = {"ok": path.is_file(), "runbook": str(path), "workspace": str(_workspace(args))}
    return _emit(payload, args.json, str(path))
