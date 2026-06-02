from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
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
    parser = argparse.ArgumentParser(prog="agenticapp", description="Route agent instructions to design-tool targets.")
    parser.add_argument("--version", action="version", version=f"agenticapp {__version__}")
    parser.add_argument("--config", help="Path to target registry JSON. Defaults to agenticapp.targets.json or configs/targets.example.json.")
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


def _load(args: argparse.Namespace) -> AppConfig:
    return load_config(args.config)


def _load_payload(raw: str) -> dict[str, Any]:
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("--payload must decode to a JSON object")
    return payload


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
