from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib import request

from . import __version__
from .adapters import DispatchError, dispatch_target
from .blender_render import BlenderRenderError, render_scene_spec
from .config import AppConfig, Target, load_config
from .scene_spec import built_in_scene_template


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (BlenderRenderError, DispatchError, ValueError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labcanvas", description="Route agent instructions to design-tool targets.")
    parser.add_argument("--version", action="version", version=f"labcanvas {__version__}")
    parser.add_argument(
        "--config",
        help="Path to target registry JSON. Defaults to labcanvas.targets.json, agenticapp.targets.json, or configs/targets.example.json.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List configured targets.")
    list_parser.set_defaults(func=cmd_list)

    doctor_parser = subparsers.add_parser("doctor", help="Validate target registry and optional live endpoints.")
    doctor_parser.add_argument("--probe", action="store_true", help="Probe HTTP endpoints with a GET request.")
    doctor_parser.set_defaults(func=cmd_doctor)

    dispatch_parser = subparsers.add_parser("dispatch", help="Dispatch an instruction to one target.")
    dispatch_parser.add_argument("target", help="Target name, such as blender, unity, unreal, or biorender.")
    dispatch_parser.add_argument("instruction", help="Natural-language instruction for the target bridge.")
    dispatch_parser.add_argument("--payload", default="{}", help="JSON object payload, or @path to read JSON from a file.")
    dispatch_parser.add_argument("--dry-run", action="store_true", help="Print the envelope without sending it.")
    dispatch_parser.add_argument("--timeout", type=float, default=30, help="Transport timeout in seconds.")
    dispatch_parser.set_defaults(func=cmd_dispatch)

    mcp_parser = subparsers.add_parser("mcp-config", help="Emit MCP client configuration for targets with MCP metadata.")
    mcp_parser.add_argument("--only", action="append", default=[], help="Limit output to a target name. Repeatable.")
    mcp_parser.set_defaults(func=cmd_mcp_config)

    template_parser = subparsers.add_parser("scene-template", help="Print or write a reusable 3D scene spec template.")
    template_parser.add_argument("template", nargs="?", default="experiment-setup", help="Template name. Default: experiment-setup.")
    template_parser.add_argument("--output", help="Write the JSON template to this path instead of stdout.")
    template_parser.set_defaults(func=cmd_scene_template)

    render_parser = subparsers.add_parser("render-scene", help="Render a JSON scene spec with Blender.")
    render_parser.add_argument("spec", help="Path to a scene spec JSON file.")
    render_parser.add_argument("--output-dir", help="Directory for generated .blend and .png artifacts.")
    render_parser.add_argument("--blender-bin", help="Path to Blender executable. Defaults to BLENDER_BIN, PATH, or portable install.")
    render_parser.add_argument("--dry-run", action="store_true", help="Validate and print the render plan without launching Blender.")
    render_parser.add_argument("--timeout", type=float, default=180, help="Blender timeout in seconds.")
    render_parser.set_defaults(func=cmd_render_scene)

    web_parser = subparsers.add_parser("web", help="Start the local chat-and-preview web app.")
    web_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1.")
    web_parser.add_argument("--port", type=int, default=8787, help="Bind port. Uses the next free port if busy.")
    web_parser.add_argument("--open", action="store_true", help="Open the app in the default browser.")
    web_parser.set_defaults(func=cmd_web)

    webapp_parser = subparsers.add_parser("webapp", help="Control the local studio web app in a tmux session.")
    webapp_parser.add_argument("action", nargs="?", default="status", choices=["start", "stop", "restart", "status"], help="Web app action.")
    webapp_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1.")
    webapp_parser.add_argument("--port", type=int, default=19473, help="Preferred high port for tmux web app. Default: 19473.")
    webapp_parser.add_argument("--session", default="labcanvas-web", help="tmux session name. Default: labcanvas-web.")
    webapp_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    webapp_parser.set_defaults(func=cmd_webapp)

    studio_parser = subparsers.add_parser("studio", help="Run paper figure studio actions from the CLI.")
    studio_subparsers = studio_parser.add_subparsers(dest="studio_command", required=True)
    studio_common = argparse.ArgumentParser(add_help=False)
    studio_common.add_argument("--storage-dir", default="output/webapp", help="Artifact storage directory. Default: output/webapp.")

    studio_status = studio_subparsers.add_parser("status", parents=[studio_common], help="Show backend, target, and artifact status.")
    studio_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_status.set_defaults(func=cmd_studio_status)

    studio_artifacts = studio_subparsers.add_parser("artifacts", parents=[studio_common], help="List studio artifacts.")
    studio_artifacts.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_artifacts.set_defaults(func=cmd_studio_artifacts)

    studio_targets = studio_subparsers.add_parser("targets", parents=[studio_common], help="List configured registry targets.")
    studio_targets.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_targets.set_defaults(func=cmd_studio_targets)

    studio_settings = studio_subparsers.add_parser("settings", parents=[studio_common], help="Show backend settings and detected status.")
    studio_settings.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_settings.set_defaults(func=cmd_studio_settings)

    studio_figure = studio_subparsers.add_parser("figure-grid", parents=[studio_common], help="Generate an exact SVG figure grid artifact.")
    studio_figure.add_argument("prompt", nargs="+", help="Figure prompt.")
    studio_figure.add_argument("--rows", type=int, help="Grid rows.")
    studio_figure.add_argument("--cols", type=int, help="Grid columns.")
    studio_figure.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_figure.set_defaults(func=cmd_studio_figure_grid)

    studio_biorender = studio_subparsers.add_parser(
        "biorender-figure",
        parents=[studio_common],
        help="Plan or generate an editable publication figure through BioRender MCP.",
    )
    studio_biorender.add_argument("prompt", nargs="+", help="Scientific purpose and content of the figure.")
    studio_biorender.add_argument("--title", default="Publication figure")
    studio_biorender.add_argument("--panel", action="append", default=[], help="Panel as 'A: description'. Repeatable.")
    studio_biorender.add_argument("--template-id", default="", help="Optional BioRender template id used as editable canvas context.")
    studio_biorender.add_argument("--mcp-url", default="http://127.0.0.1:19682/mcp")
    studio_biorender.add_argument("--run-id", default="", help="Stable run id for idempotent artifact paths.")
    studio_biorender.add_argument("--live", action="store_true", help="Create the real BioRender figure; otherwise write a dry-run manifest and prompt.")
    studio_biorender.add_argument("--timeout", type=float, default=900.0)
    studio_biorender.add_argument("--request-timeout", type=float, default=330.0, help="Per-MCP-request timeout for slow BioRender generation calls.")
    studio_biorender.add_argument("--poll-seconds", type=float, default=5.0)
    studio_biorender.add_argument("--min-width", type=int, default=1200)
    studio_biorender.add_argument("--min-height", type=int, default=700)
    studio_biorender.add_argument("--no-cdp-export", action="store_true", help="Keep the MCP preview and skip visible 300-DPI browser export.")
    studio_biorender.add_argument("--cdp-url", default="http://127.0.0.1:9389")
    studio_biorender.add_argument("--export-timeout", type=float, default=240.0)
    studio_biorender.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_biorender.set_defaults(func=cmd_studio_biorender_figure)

    studio_openscad = studio_subparsers.add_parser("openscad", parents=[studio_common], help="Export a scene spec to OpenSCAD and register the artifact.")
    studio_openscad.add_argument("spec", help="Path to a scene spec JSON file.")
    studio_openscad.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_openscad.set_defaults(func=cmd_studio_openscad)

    studio_lab_task = studio_subparsers.add_parser("lab-task", parents=[studio_common], help="Plan or execute a reusable PCB/CAD generation task.")
    studio_lab_task.add_argument("prompt", nargs="+", help="Task prompt, such as 'prepare Lumileds PCB and C-mount CAD'.")
    studio_lab_task.add_argument("--mode", choices=["auto", "pcb", "cad", "mixed"], default="auto", help="Workflow family to select. Default: auto.")
    studio_lab_task.add_argument("--execute", action="store_true", help="Run safe local steps marked for default execution. Does not submit manufacturing orders.")
    studio_lab_task.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_lab_task.set_defaults(func=cmd_studio_lab_task)

    studio_dispatch = studio_subparsers.add_parser("dispatch", parents=[studio_common], help="Dry-run or send an instruction to a configured target.")
    studio_dispatch.add_argument("target", help="Target name, such as blender, biorender, unity, or unreal.")
    studio_dispatch.add_argument("instruction", help="Instruction for the target bridge.")
    studio_dispatch.add_argument("--payload", default="{}", help="JSON object payload, or @path to read JSON from a file.")
    studio_dispatch.add_argument("--live", action="store_true", help="Send to the target instead of dry-run.")
    studio_dispatch.add_argument("--timeout", type=float, default=30, help="Transport timeout in seconds.")
    studio_dispatch.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    studio_dispatch.set_defaults(func=cmd_studio_dispatch)

    agent_parser = subparsers.add_parser("agent", help="Chat with the persistent tool-capable LabCanvas workspace agent.")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_common = argparse.ArgumentParser(add_help=False)
    agent_common.add_argument("--storage-dir", default="output/webapp", help="Agent task and artifact storage. Default: output/webapp.")

    agent_chat = agent_subparsers.add_parser("chat", parents=[agent_common], help="Send one turn to a persistent LabCanvas agent session.")
    agent_chat.add_argument("prompt", nargs="+", help="Natural-language task or follow-up message.")
    agent_chat.add_argument("--conversation", default="cli-default", help="Stable conversation id used to resume one Codex session.")
    agent_chat.add_argument("--backend", choices=["auto", "codex", "aginti"], default="auto", help="Agent backend. Default: auto.")
    agent_chat.add_argument("--model", default="auto", help="Model id or auto. 'sol' aliases gpt-5.6-sol.")
    agent_chat.add_argument("--effort", choices=["auto", "low", "medium", "high", "ultra", "xhigh"], default="auto", help="Reasoning effort. Ultra aliases xhigh.")
    agent_chat.add_argument("--mode", choices=["execute", "plan"], default="execute", help="Execute tools or inspect and plan only.")
    agent_chat.add_argument("--timeout", type=int, help="Override the dynamic task timeout in seconds.")
    agent_chat.add_argument("--no-aginti-fallback", action="store_true", help="Do not fall back to AgInTi if Codex is unavailable or times out.")
    agent_chat.add_argument("--detach", action="store_true", help="Return the task id immediately instead of waiting.")
    agent_chat.add_argument("--dry-run", action="store_true", help="Show selected policy and prompt contract without launching an agent.")
    agent_chat.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    agent_chat.set_defaults(func=cmd_agent_chat)

    agent_capabilities = agent_subparsers.add_parser("capabilities", parents=[agent_common], help="Show available integrated tool families.")
    agent_capabilities.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    agent_capabilities.set_defaults(func=cmd_agent_capabilities)

    agent_tasks = agent_subparsers.add_parser("tasks", parents=[agent_common], help="List recent durable agent tasks.")
    agent_tasks.add_argument("--limit", type=int, default=30, help="Maximum task count. Default: 30.")
    agent_tasks.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    agent_tasks.set_defaults(func=cmd_agent_tasks)

    agent_status = agent_subparsers.add_parser("status", parents=[agent_common], help="Show one agent task.")
    agent_status.add_argument("task_id", help="Agent task id.")
    agent_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    agent_status.set_defaults(func=cmd_agent_status)

    agent_cancel = agent_subparsers.add_parser("cancel", parents=[agent_common], help="Cancel one running agent task.")
    agent_cancel.add_argument("task_id", help="Agent task id.")
    agent_cancel.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    agent_cancel.set_defaults(func=cmd_agent_cancel)

    grant_parser = subparsers.add_parser("grant", help="Create and run durable evidence-grounded grant projects.")
    grant_subparsers = grant_parser.add_subparsers(dest="grant_command", required=True)

    grant_init = grant_subparsers.add_parser("init", help="Create a dedicated grant goal workspace.")
    grant_init.add_argument("objective", nargs="+", help="Concrete grant-writing objective.")
    grant_init.add_argument("--title", default="Research Grant Proposal")
    grant_init.add_argument("--project-dir", default="", help="Project directory. Defaults under ignored output/grants/.")
    grant_init.add_argument("--task-id", default="")
    grant_init.add_argument("--chat", default="")
    grant_init.add_argument("--json", action="store_true")
    grant_init.set_defaults(func=cmd_grant_init)

    grant_run = grant_subparsers.add_parser("run", help="Run the persistent Codex grant agent from a goal workspace.")
    grant_run.add_argument("objective", nargs="+", help="Concrete grant-writing objective.")
    grant_run.add_argument("--title", default="Research Grant Proposal")
    grant_run.add_argument("--project-dir", default="", help="Project directory. Defaults under ignored output/grants/.")
    grant_run.add_argument("--storage-dir", default="output/webapp")
    grant_run.add_argument("--conversation", default="", help="Stable conversation id. Defaults to the grant project id.")
    grant_run.add_argument("--model", default="gpt-5.6-sol")
    grant_run.add_argument(
        "--effort",
        choices=["low", "medium", "high", "ultra", "xhigh"],
        default="medium",
        help="Reasoning effort; Ultra aliases xhigh.",
    )
    grant_run.add_argument("--timeout", type=int, default=10800)
    grant_run.add_argument("--detach", action="store_true")
    grant_run.add_argument("--dry-run", action="store_true")
    grant_run.add_argument("--json", action="store_true")
    grant_run.set_defaults(func=cmd_grant_run)

    grant_compile = grant_subparsers.add_parser("compile", help="Compile proposal.tex in a grant workspace.")
    grant_compile.add_argument("--project-dir", required=True)
    grant_compile.add_argument("--timeout", type=int, default=300)
    grant_compile.add_argument("--json", action="store_true")
    grant_compile.set_defaults(func=cmd_grant_compile)

    grant_validate = grant_subparsers.add_parser("validate", help="Validate grant source, PDF, and editable figure artifacts.")
    grant_validate.add_argument("--project-dir", required=True)
    grant_validate.add_argument("--json", action="store_true")
    grant_validate.set_defaults(func=cmd_grant_validate)

    presentation_parser = subparsers.add_parser(
        "presentation",
        help="Create, build, render, and validate editable PowerPoint decks.",
    )
    presentation_subparsers = presentation_parser.add_subparsers(
        dest="presentation_command",
        required=True,
    )

    presentation_init = presentation_subparsers.add_parser(
        "init",
        help="Create a manifest-driven presentation workspace.",
    )
    presentation_init.add_argument("title", nargs="+")
    presentation_init.add_argument("--objective", default="")
    presentation_init.add_argument(
        "--theme",
        choices=["bright_scientific", "clean_editorial"],
        default="bright_scientific",
    )
    presentation_init.add_argument("--output-dir", required=True)
    presentation_init.add_argument("--json", action="store_true")
    presentation_init.set_defaults(func=cmd_presentation_init)

    presentation_build = presentation_subparsers.add_parser(
        "build",
        help="Build an editable PPTX from a presentation manifest.",
    )
    presentation_build.add_argument("manifest")
    presentation_build.add_argument("--output-dir", default="")
    presentation_build.add_argument(
        "--render",
        action="store_true",
        help="Also render PDF and PNG previews with LibreOffice.",
    )
    presentation_build.add_argument("--timeout", type=float, default=180)
    presentation_build.add_argument("--json", action="store_true")
    presentation_build.set_defaults(func=cmd_presentation_build)

    presentation_validate = presentation_subparsers.add_parser(
        "validate",
        help="Validate slide structure and generated-image policy.",
    )
    presentation_validate.add_argument("manifest")
    presentation_validate.add_argument("--json", action="store_true")
    presentation_validate.set_defaults(func=cmd_presentation_validate)

    worker_parser = subparsers.add_parser("_agent-worker", help=argparse.SUPPRESS)
    worker_parser.add_argument("--task-id", required=True)
    worker_parser.add_argument("--storage-dir", required=True)
    worker_parser.add_argument("--root", required=True)
    worker_parser.set_defaults(func=cmd_agent_worker)

    from .wechat_ops import add_wechat_parser
    from .wecom_ops import add_wecom_parser
    from .social_ops import add_social_parser
    from .protein_structure_ops import add_protein_structure_parser
    from .musia_ops import add_musia_parser

    add_wechat_parser(subparsers)
    add_wecom_parser(subparsers)
    add_social_parser(subparsers)
    add_protein_structure_parser(subparsers)
    add_musia_parser(subparsers)
    return parser


def cmd_list(args: argparse.Namespace) -> int:
    config = _load(args)
    rows = [("NAME", "KIND", "TRANSPORT", "ENABLED", "DESCRIPTION")]
    for target in config.targets:
        rows.append(
            (
                target.name,
                target.kind,
                str(target.transport.get("type", "noop")),
                "yes" if target.enabled else "no",
                target.description,
            )
        )
    _print_table(rows)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = _load(args)
    failures = 0
    for target in config.targets:
        ok, message = _check_target(target, probe=bool(args.probe))
        marker = "ok" if ok else "fail"
        print(f"{marker:4} {target.name}: {message}")
        failures += 0 if ok else 1
    return 1 if failures else 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    config = _load(args)
    target = config.get_target(args.target)
    payload = _load_payload(args.payload)
    result = dispatch_target(target, args.instruction, payload, dry_run=args.dry_run, timeout=args.timeout)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


def cmd_mcp_config(args: argparse.Namespace) -> int:
    config = _load(args)
    only = set(args.only)
    servers: dict[str, Any] = {}
    for target in config.targets:
        if only and target.name not in only:
            continue
        if target.mcp:
            servers[target.name] = target.mcp
    print(json.dumps({"mcpServers": servers}, indent=2, sort_keys=True))
    return 0


def cmd_scene_template(args: argparse.Namespace) -> int:
    template = built_in_scene_template(args.template)
    payload = json.dumps(template, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(payload)
    return 0


def cmd_render_scene(args: argparse.Namespace) -> int:
    result = render_scene_spec(
        args.spec,
        args.output_dir,
        blender_bin=args.blender_bin,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    from .webapp import run_web_app

    run_web_app(args.host, args.port, open_browser=args.open)
    return 0


def cmd_webapp(args: argparse.Namespace) -> int:
    if args.action in {"stop", "restart"}:
        stopped = _tmux_stop(args.session)
        if args.action == "stop":
            payload = {"ok": True, "action": "stop", "stopped": stopped, "session": args.session}
            _print_payload(payload, args.json, f"webapp: {'stopped' if stopped else 'not running'}")
            return 0

    if args.action in {"start", "restart"}:
        payload = _tmux_start(args.session, args.host, args.port)
        _print_payload(payload, args.json, f"webapp: {payload.get('url', '')} {payload.get('status', '')}")
        return 0 if payload.get("ok") else 1

    payload = _tmux_status(args.session)
    _print_payload(payload, args.json, f"webapp: {payload.get('url', '') or 'not running'} {payload.get('status', '')}")
    return 0 if payload.get("ok") else 1


def cmd_studio_status(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactStore
    from .backends import backend_status, load_backend_settings
    from .webapp import target_list_response

    storage_dir = Path(args.storage_dir)
    settings = load_backend_settings(storage_dir / "settings.json")
    artifacts = ArtifactStore(storage_dir).bundle()
    payload = {
        "ok": True,
        "storage_dir": str(storage_dir.resolve()),
        "artifact_count": len(artifacts["items"]),
        "selected_artifact_id": artifacts.get("selected_id", ""),
        "backends": backend_status(settings, Path.cwd()),
        "targets": target_list_response()["targets"],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"storage: {payload['storage_dir']}")
        print(f"artifacts: {payload['artifact_count']} selected={payload['selected_artifact_id'] or '(none)'}")
        print(f"aginti: {payload['backends']['aginti']['command_path'] or 'missing'}")
        print(f"biorender: {payload['backends']['biorender']['mcp_url']}")
        print("targets: " + ", ".join(target["name"] for target in payload["targets"]))
    return 0


def cmd_studio_artifacts(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactStore

    payload = ArtifactStore(Path(args.storage_dir)).bundle()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        rows = [("KIND", "SOURCE", "TITLE", "PATH")]
        for item in payload["items"]:
            rows.append((item["kind"], item["source"], item["title"], item["path"]))
        _print_table(rows)
    return 0


def cmd_studio_targets(args: argparse.Namespace) -> int:
    from .webapp import target_list_response

    payload = target_list_response()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        rows = [("NAME", "KIND", "TRANSPORT", "ENABLED")]
        for target in payload["targets"]:
            rows.append((target["name"], target["kind"], target["transport"], "yes" if target["enabled"] else "no"))
        _print_table(rows)
    return 0


def cmd_studio_settings(args: argparse.Namespace) -> int:
    from .backends import backend_status, load_backend_settings

    settings = load_backend_settings(Path(args.storage_dir) / "settings.json")
    payload = {"ok": True, "settings": settings, "status": backend_status(settings, Path.cwd())}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"aginti: {payload['status']['aginti']['command']} -> {payload['status']['aginti']['command_path'] or 'missing'}")
        print(f"biorender: {payload['status']['biorender']['mcp_url']} env={payload['status']['biorender']['auth_env']}")
        print("toolchain: " + ", ".join(key for key, enabled in payload["settings"].get("toolchain", {}).items() if enabled))
    return 0


def cmd_studio_figure_grid(args: argparse.Namespace) -> int:
    from .backends import load_backend_settings
    from .webapp import generate_web_figure_grid

    storage_dir = Path(args.storage_dir)
    payload: dict[str, Any] = {"prompt": " ".join(args.prompt)}
    if args.rows:
        payload["rows"] = args.rows
    if args.cols:
        payload["cols"] = args.cols
    result = generate_web_figure_grid(payload, storage_dir, load_backend_settings(storage_dir / "settings.json"))
    _print_payload(result, args.json, f"figure-grid: {result['figure_url']} rows={result['rows']} cols={result['cols']}")
    return 0 if result.get("ok") else 1


def cmd_studio_biorender_figure(args: argparse.Namespace) -> int:
    from .biorender_figures import run_biorender_figure

    result = run_biorender_figure(
        {
            "prompt": " ".join(args.prompt),
            "title": args.title,
            "panels": args.panel,
            "template_id": args.template_id,
            "mcp_url": args.mcp_url,
            "run_id": args.run_id,
            "live": args.live,
            "timeout_seconds": args.timeout,
            "request_timeout": args.request_timeout,
            "poll_seconds": args.poll_seconds,
            "min_width": args.min_width,
            "min_height": args.min_height,
            "cdp_export": not args.no_cdp_export,
            "cdp_url": args.cdp_url,
            "export_timeout": args.export_timeout,
        },
        Path(args.storage_dir),
    )
    artifact = result.get("artifact") or {}
    _print_payload(result, args.json, f"biorender-figure: {result['status']} -> {artifact.get('url', '')}")
    return 0 if result.get("ok") else 1


def cmd_studio_openscad(args: argparse.Namespace) -> int:
    from .scene_spec import load_scene_spec
    from .webapp import export_web_openscad

    result = export_web_openscad(load_scene_spec(args.spec), Path(args.storage_dir))
    _print_payload(result, args.json, f"openscad: {result['artifact']['url']}")
    return 0 if result.get("ok") else 1


def cmd_studio_lab_task(args: argparse.Namespace) -> int:
    from .lab_tasks import run_lab_task

    result = run_lab_task(
        {
            "prompt": " ".join(args.prompt),
            "mode": args.mode,
            "execute": args.execute,
        },
        Path(args.storage_dir),
    )
    _print_payload(result, args.json, f"lab-task: {result['task']['kind']} -> {result['artifact']['url']}")
    return 0 if result.get("ok") else 1


def cmd_studio_dispatch(args: argparse.Namespace) -> int:
    from .webapp import dispatch_web_target

    result = dispatch_web_target(
        {
            "target": args.target,
            "instruction": args.instruction,
            "payload": _load_payload(args.payload),
            "dry_run": not args.live,
            "timeout": args.timeout,
        },
        Path(args.storage_dir),
    )
    _print_payload(result, args.json, f"dispatch: {result['dispatch']['target']} {result['dispatch']['status']} -> {result['artifact']['url']}")
    return 0 if result.get("ok") else 1


def cmd_agent_chat(args: argparse.Namespace) -> int:
    from .workspace_agent import build_agent_prompt, create_agent_task, select_agent_policy, wait_for_task

    message = " ".join(args.prompt).strip()
    storage_dir = Path(args.storage_dir)
    payload = {
        "message": message,
        "conversation_id": args.conversation,
        "backend": args.backend,
        "model": args.model,
        "effort": args.effort,
        "mode": args.mode,
        "fallback_to_aginti": not args.no_aginti_fallback,
    }
    if args.timeout:
        payload["timeout_seconds"] = args.timeout
    if args.dry_run:
        policy = select_agent_policy(message, model=args.model, effort=args.effort, mode=args.mode, backend=args.backend)
        result = {
            "ok": True,
            "dry_run": True,
            "policy": policy,
            "prompt": build_agent_prompt(
                message,
                root=Path.cwd(),
                task_dir=storage_dir / "agent" / "dry-run",
                policy=policy,
                conversation_id=args.conversation,
            ),
        }
    else:
        result = create_agent_task(payload, storage_dir, root=Path.cwd(), launch=True)
        if not args.detach:
            policy_timeout = float(result["task"]["policy"]["timeout_seconds"])
            attempts = 2 if result["task"]["policy"].get("fallback_to_aginti", True) else 1
            timeout = policy_timeout * attempts + 60
            result = wait_for_task(result["task"]["id"], storage_dir, timeout=timeout)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.dry_run:
        policy = result["policy"]
        print(f"agent: {policy['backend']} {policy['model']} {policy['effort_label']} ({policy['mode']})")
    elif args.detach:
        print(f"agent task: {result['task']['id']} ({result['task']['status']})")
    else:
        print(result["task"].get("reply") or result["task"].get("error") or result["task"]["status"])
    return 0 if result.get("ok") else 1


def cmd_agent_capabilities(args: argparse.Namespace) -> int:
    from .workspace_agent import capability_response

    storage_dir = Path(args.storage_dir)
    result = capability_response(Path.cwd(), storage_dir / "settings.json")
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        rows = [("READY", "CAPABILITY", "OUTPUTS")]
        for item in result["capabilities"]:
            rows.append(("yes" if item["ready"] else "no", item["title"], ", ".join(item["outputs"])))
        _print_table(rows)
    return 0


def cmd_agent_tasks(args: argparse.Namespace) -> int:
    from .workspace_agent import task_list_response

    result = task_list_response(args.storage_dir, args.limit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        rows = [("STATUS", "MODEL", "EFFORT", "TASK", "MESSAGE")]
        for task in result["tasks"]:
            policy = task.get("policy", {})
            rows.append((task["status"], str(policy.get("model") or ""), str(policy.get("effort_label") or ""), task["id"], task["message"][:72]))
        _print_table(rows)
    return 0


def cmd_agent_status(args: argparse.Namespace) -> int:
    from .workspace_agent import task_response

    result = task_response(args.task_id, args.storage_dir)
    _print_payload(result, args.json, f"agent task: {result['task']['status']} {result['task'].get('reply') or result['task'].get('error') or ''}")
    return 0 if result.get("ok") else 1


def cmd_agent_cancel(args: argparse.Namespace) -> int:
    from .workspace_agent import cancel_agent_task

    result = cancel_agent_task(args.task_id, args.storage_dir)
    _print_payload(result, args.json, f"agent task: {result['task']['id']} canceled")
    return 0


def cmd_grant_init(args: argparse.Namespace) -> int:
    from .grants import default_project_dir, initialize_grant_workspace

    objective = " ".join(args.objective).strip()
    project_dir = Path(args.project_dir).expanduser() if args.project_dir else default_project_dir(args.title, root=Path.cwd())
    result = initialize_grant_workspace(
        project_dir,
        title=args.title,
        objective=objective,
        task_id=args.task_id,
        chat=args.chat,
    )
    _print_payload(result, args.json, f"grant workspace: {result['project_dir']}")
    return 0


def cmd_grant_run(args: argparse.Namespace) -> int:
    from .grants import default_project_dir, initialize_grant_workspace
    from .workspace_agent import build_agent_prompt, create_agent_task, select_agent_policy, wait_for_task

    objective = " ".join(args.objective).strip()
    project_dir = Path(args.project_dir).expanduser() if args.project_dir else default_project_dir(args.title, root=Path.cwd())
    workspace = initialize_grant_workspace(project_dir, title=args.title, objective=objective)
    goal_prompt = Path(workspace["prompt_path"]).read_text(encoding="utf-8")
    conversation = args.conversation or f"grant-{workspace['goal'].get('project_id') or project_dir.name}"
    storage_dir = Path(args.storage_dir)
    payload = {
        "message": goal_prompt,
        "conversation_id": conversation,
        "backend": "codex",
        "model": args.model,
        "effort": args.effort,
        "mode": "execute",
        "timeout_seconds": args.timeout,
        "fallback_to_aginti": True,
        "context": {"grant_workspace": workspace},
    }
    if args.dry_run:
        policy = select_agent_policy(goal_prompt, model=args.model, effort=args.effort, mode="execute", backend="codex")
        result = {
            "ok": True,
            "dry_run": True,
            "workspace": workspace,
            "policy": policy,
            "prompt": build_agent_prompt(
                goal_prompt,
                root=Path.cwd(),
                task_dir=storage_dir / "agent" / "grant-dry-run",
                policy=policy,
                conversation_id=conversation,
                context={"grant_workspace": workspace},
            ),
        }
    else:
        result = create_agent_task(payload, storage_dir, root=Path.cwd(), launch=True)
        result["workspace"] = workspace
        if not args.detach:
            result = wait_for_task(result["task"]["id"], storage_dir, timeout=float(args.timeout) + 120)
            result["workspace"] = workspace
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.dry_run:
        print(f"grant dry run: {workspace['project_dir']}")
    elif args.detach:
        print(f"grant task: {result['task']['id']} ({result['task']['status']})")
    else:
        print(result["task"].get("reply") or result["task"].get("error") or result["task"]["status"])
    return 0 if result.get("ok") else 1


def cmd_grant_compile(args: argparse.Namespace) -> int:
    from .grants import compile_grant

    result = compile_grant(args.project_dir, timeout=args.timeout)
    _print_payload(result, args.json, result.get("pdf") or result.get("error") or "grant compile failed")
    return 0 if result.get("ok") else 1


def cmd_grant_validate(args: argparse.Namespace) -> int:
    from .grants import validate_grant_workspace

    result = validate_grant_workspace(args.project_dir)
    _print_payload(result, args.json, f"grant validation: {'ok' if result.get('ok') else 'failed'}")
    return 0 if result.get("ok") else 1


def cmd_presentation_init(args: argparse.Namespace) -> int:
    from .presentations import initialize_presentation_workspace

    result = initialize_presentation_workspace(
        args.output_dir,
        title=" ".join(args.title).strip(),
        objective=args.objective,
        theme=args.theme,
    )
    _print_payload(
        result,
        args.json,
        f"presentation workspace: {result['project_dir']}",
    )
    return 0


def cmd_presentation_build(args: argparse.Namespace) -> int:
    from .presentations import build_presentation

    result = build_presentation(
        args.manifest,
        output_dir=args.output_dir or None,
        render=args.render,
        timeout=args.timeout,
    )
    _print_payload(
        result,
        args.json,
        result.get("pptx") or "; ".join(result.get("validation", {}).get("errors", [])),
    )
    return 0 if result.get("ok") else 1


def cmd_presentation_validate(args: argparse.Namespace) -> int:
    from .presentations import load_manifest, validate_manifest

    manifest, manifest_path = load_manifest(args.manifest)
    result = validate_manifest(manifest, manifest_path.parent)
    _print_payload(
        result,
        args.json,
        f"presentation validation: {'ok' if result.get('ok') else 'failed'}",
    )
    return 0 if result.get("ok") else 1


def cmd_agent_worker(args: argparse.Namespace) -> int:
    from .workspace_agent import run_agent_task

    result = run_agent_task(args.task_id, args.storage_dir, root=args.root)
    return 0 if result.get("ok") else 1


def _load(args: argparse.Namespace) -> AppConfig:
    return load_config(args.config)


def _load_payload(raw: str) -> dict[str, Any]:
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--payload must decode to a JSON object")
    return payload


def _print_payload(payload: dict[str, Any], as_json: bool, summary: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(summary)


def _tmux_status(session: str) -> dict[str, Any]:
    if shutil.which("tmux") is None:
        return {"ok": False, "status": "missing-tmux", "session": session, "url": ""}
    check = subprocess.run(["tmux", "has-session", "-t", session], capture_output=True, text=True, check=False)
    if check.returncode != 0:
        return {"ok": False, "status": "not-running", "session": session, "url": ""}
    capture = subprocess.run(["tmux", "capture-pane", "-pt", session], capture_output=True, text=True, check=False)
    url = _first_url(capture.stdout)
    return {"ok": True, "status": "running", "session": session, "url": url}


def _tmux_start(session: str, host: str, port: int) -> dict[str, Any]:
    status = _tmux_status(session)
    if status["ok"]:
        return status
    if shutil.which("tmux") is None:
        return {"ok": False, "status": "missing-tmux", "session": session, "url": ""}
    command = _webapp_command(host, port)
    subprocess.run(["tmux", "new-session", "-d", "-s", session, "-c", str(Path.cwd()), command], check=True)
    time.sleep(0.6)
    return _tmux_status(session)


def _tmux_stop(session: str) -> bool:
    if shutil.which("tmux") is None:
        return False
    check = subprocess.run(["tmux", "has-session", "-t", session], capture_output=True, text=True, check=False)
    if check.returncode != 0:
        return False
    subprocess.run(["tmux", "kill-session", "-t", session], check=False)
    return True


def _webapp_command(host: str, port: int) -> str:
    command = [sys.executable, "-m", "agenticapp", "web", "--host", host, "--port", str(port)]
    path_parts = []
    module_src_dir = Path(__file__).resolve().parents[1]
    if module_src_dir.is_dir():
        path_parts.append(str(module_src_dir))
    cwd_src_dir = (Path.cwd() / "src").resolve()
    if cwd_src_dir.is_dir() and str(cwd_src_dir) not in path_parts:
        path_parts.append(str(cwd_src_dir))
    prefix = f"PYTHONPATH={shlex.quote(':'.join(path_parts))}:${{PYTHONPATH:-}} " if path_parts else ""
    return prefix + shlex.join(command)


def _first_url(text: str) -> str:
    for chunk in text.split():
        if chunk.startswith("http://") or chunk.startswith("https://"):
            return chunk.strip()
    return ""


def _check_target(target: Target, *, probe: bool) -> tuple[bool, str]:
    transport_type = str(target.transport.get("type", "noop"))
    if not target.enabled:
        return True, "disabled"
    if transport_type == "http_json":
        url = str(target.transport.get("url", "")).strip()
        if not url:
            return False, "missing transport.url"
        if not probe:
            return True, f"http_json configured at {url}"
        try:
            with request.urlopen(url, timeout=3) as response:
                return True, f"endpoint answered HTTP {response.status}"
        except Exception as exc:  # noqa: BLE001 - report the probe failure plainly.
            return False, f"endpoint probe failed: {exc}"
    if transport_type == "local_command":
        command = target.transport.get("command")
        first = command[0] if isinstance(command, list) and command else command
        if not first:
            return False, "missing transport.command"
        if shutil.which(str(first)) is None:
            return False, f"command not found: {first}"
        return True, f"command found: {first}"
    if transport_type == "browser":
        url = str(target.transport.get("url", "")).strip()
        return (True, f"browser launch configured at {url}") if url else (False, "missing transport.url")
    if transport_type == "noop":
        return True, "noop transport"
    return False, f"unsupported transport type {transport_type!r}"


def _print_table(rows: list[tuple[str, ...]]) -> None:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    for row_index, row in enumerate(rows):
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            print("  ".join("-" * width for width in widths))
