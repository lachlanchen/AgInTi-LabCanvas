from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import re
import socket
import threading
from typing import Any
from urllib import error as urlerror, request as urlrequest
import webbrowser

from .adapters import DispatchError, dispatch_target
from .artifacts import ArtifactStore, content_type_for_path
from .backends import backend_status, load_backend_settings, run_aginti_image_request, save_backend_settings
from .blender_render import BlenderRenderError, render_scene_spec
from .config import load_config
from .lab_tasks import looks_like_lab_task_prompt, run_lab_task
from .openscad_export import export_scene_to_openscad
from .paper_figures import generate_icon_grid, parse_grid_size
from .scene_spec import built_in_scene_template, slugify, validate_scene_spec
from .workspace_agent import (
    build_agent_prompt,
    cancel_agent_task,
    capability_response,
    create_agent_task,
    select_agent_policy,
    task_list_response,
    task_response,
)


ROOT = Path.cwd()
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


def run_web_app(host: str = "127.0.0.1", port: int = 8787, *, open_browser: bool = False) -> str:
    server = create_server(host, port)
    url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        print(url, flush=True)
        server.serve_forever()
    finally:
        server.server_close()
    return url


def create_server(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    if port == 0:
        bind_port = 0
    else:
        bind_port = first_available_port(host, port)
    return ThreadingHTTPServer((host, bind_port), LabCanvasHandler)


def first_available_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port found from {start} to {start + 49}")


class LabCanvasHandler(BaseHTTPRequestHandler):
    storage_dir = ROOT / "output" / "webapp"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        route = self.path.split("?", 1)[0]
        if self.path == "/" or self.path.startswith("/?"):
            self.send_static("index.html")
        elif route.startswith("/static/"):
            self.send_static(route.removeprefix("/static/"))
        elif route == "/api/spec":
            self.send_json(default_spec_response())
        elif route == "/api/health":
            self.send_json({"ok": True})
        elif route == "/api/artifacts":
            self.send_json(ArtifactStore(self.storage_dir).bundle())
        elif route == "/api/targets":
            self.send_json(target_list_response())
        elif route in {"/api/settings", "/api/backends"}:
            settings = load_backend_settings(self.settings_path())
            self.send_json({"ok": True, "settings": settings, "status": backend_status(settings, ROOT)})
        elif route == "/api/wechat/status":
            from .wechat_ops import status_payload

            self.send_json(status_payload())
        elif route == "/api/agent/capabilities":
            self.send_json(capability_response(ROOT, self.settings_path()))
        elif route == "/api/agent/tasks":
            self.send_json(task_list_response(self.storage_dir))
        elif route.startswith("/api/agent/tasks/"):
            task_id = route.removeprefix("/api/agent/tasks/").strip("/")
            self.send_json(task_response(task_id, self.storage_dir))
        elif route == "/example-render":
            self.send_example_render()
        elif route.startswith("/artifacts/"):
            self.send_artifact(route.removeprefix("/artifacts/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        if self.path == "/" or self.path.startswith("/?"):
            self.send_head_for_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif self.path == "/example-render":
            self.send_head_for_file(example_path("examples/renders/paper-optics-setup.png"), "image/png")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        try:
            route = self.path.split("?", 1)[0]
            if route == "/api/chat":
                payload = self.read_json()
                spec = payload.get("spec") or default_scene_spec()
                message = str(payload.get("message", ""))
                settings = load_backend_settings(self.settings_path())
                self.send_json(chat_update(spec, message, storage_dir=self.storage_dir, settings=settings))
            elif route == "/api/agent/chat":
                payload = self.read_json()
                settings = load_backend_settings(self.settings_path())
                self.send_json(run_web_agent_chat(payload, self.storage_dir, settings=settings))
            elif route == "/api/writing/next-paragraph":
                payload = self.read_json()
                settings = load_backend_settings(self.settings_path())
                self.send_json(run_web_next_paragraph(payload, settings=settings))
            elif route == "/api/render":
                payload = self.read_json()
                spec = payload.get("spec") or default_scene_spec()
                self.send_json(render_web_scene(spec, self.storage_dir))
            elif route == "/api/plan":
                payload = self.read_json()
                spec = payload.get("spec") or default_scene_spec()
                self.send_json(plan_web_scene(spec, self.storage_dir))
            elif route == "/api/settings":
                payload = self.read_json()
                settings = sanitize_settings(payload.get("settings") if "settings" in payload else payload)
                saved = save_backend_settings(self.settings_path(), settings)
                self.send_json({"ok": True, "settings": saved, "status": backend_status(saved, ROOT)})
            elif route == "/api/figure-grid":
                payload = self.read_json()
                settings = load_backend_settings(self.settings_path())
                self.send_json(generate_web_figure_grid(payload, self.storage_dir, settings))
            elif route == "/api/openscad-export":
                payload = self.read_json()
                spec = payload.get("spec") or default_scene_spec()
                self.send_json(export_web_openscad(spec, self.storage_dir))
            elif route == "/api/lab-task":
                payload = self.read_json()
                self.send_json(run_web_lab_task(payload, self.storage_dir))
            elif route == "/api/dispatch":
                payload = self.read_json()
                self.send_json(dispatch_web_target(payload, self.storage_dir))
            elif route == "/api/wechat/action":
                from .wechat_ops import run_wechat_action

                payload = self.read_json()
                action = str(payload.get("action") or "status")
                self.send_json(run_wechat_action(action, payload))
            elif route == "/api/wechat/send":
                from .wechat_ops import send_wechat_message_api

                payload = self.read_json()
                self.send_json(
                    send_wechat_message_api(
                        message=str(payload.get("message") or ""),
                        chat=str(payload.get("chat") or ""),
                        target=payload.get("target") if isinstance(payload.get("target"), dict) else None,
                        target_name=str(payload.get("target") or ""),
                        dry_run=bool(payload.get("dry_run", False)),
                        allow_search=bool(payload.get("allow_search", False)) if "allow_search" in payload else None,
                    )
                )
            elif route.startswith("/api/agent/tasks/") and route.endswith("/cancel"):
                task_id = route.removeprefix("/api/agent/tasks/").removesuffix("/cancel").strip("/")
                self.send_json(cancel_agent_task(task_id, self.storage_dir))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (BlenderRenderError, DispatchError, ValueError, KeyError, OSError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Request body must be a JSON object")
        return data

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, name: str) -> None:
        path = (STATIC_DIR / name).resolve()
        if not path.is_file() or STATIC_DIR.resolve() not in path.parents:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8"
        if path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif path.suffix == ".svg":
            content_type = "image/svg+xml; charset=utf-8"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_artifact(self, relative: str) -> None:
        path = (self.storage_dir / relative).resolve()
        if not path.is_file() or self.storage_dir.resolve() not in path.parents:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = content_type_for_path(path)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_example_render(self) -> None:
        path = example_path("examples/renders/paper-optics-setup.png")
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_head_for_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def settings_path(self) -> Path:
        return self.storage_dir / "settings.json"


def default_spec_response() -> dict[str, Any]:
    spec = default_scene_spec()
    preview = example_path("examples/renders/paper-optics-setup.png")
    preview_url = None
    if preview.exists():
        preview_url = "/example-render"
    return {"ok": True, "spec": spec, "preview_url": preview_url}


def default_scene_spec() -> dict[str, Any]:
    example = example_path("examples/paper-optics-setup.scene.json")
    if example.exists():
        return json.loads(example.read_text(encoding="utf-8"))
    return built_in_scene_template("experiment-setup")


def example_path(relative: str) -> Path:
    worktree_path = ROOT / relative
    if worktree_path.exists():
        return worktree_path
    return PACKAGE_ROOT / relative


def chat_update(
    spec: dict[str, Any],
    message: str,
    *,
    storage_dir: Path | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = deepcopy(spec)
    validate_scene_spec(updated)
    text = message.strip()
    lowered = text.lower()
    actions: list[str] = []

    title = extract_quoted(text) if any(word in lowered for word in ("title", "name", "caption")) else None
    if title:
        updated["title"] = title
        updated["slug"] = slugify(title)
        update_label(updated, "title", title)
        actions.append(f"Renamed the scene to {title!r}.")

    if "v-spice" in lowered or "vspice" in lowered:
        updated["title"] = "V-SPICE experiment setup"
        updated["slug"] = "v-spice-experiment-setup"
        update_label(updated, "title", "V-SPICE experiment setup")
        actions.append("Applied a V-SPICE title.")

    if any(word in lowered for word in ("vivid", "brighter", "bright", "colorful", "colourful")):
        updated.setdefault("render", {})["world_color"] = [0.90, 0.93, 0.96]
        updated["render"]["exposure"] = 0.08
        updated.setdefault("materials", {}).setdefault("beam", {})["color"] = [1.0, 0.42, 0.08, 0.48]
        updated["materials"]["beam"]["alpha"] = 0.48
        actions.append("Brightened the background and optical beam.")

    if "blue" in lowered:
        updated.setdefault("materials", {}).setdefault("beam", {})["color"] = [0.1, 0.45, 1.0, 0.42]
        updated["materials"]["beam"]["alpha"] = 0.42
        actions.append("Changed the beam accent to blue.")

    if "laser" in lowered:
        replace_or_add_led(updated, "Laser")
        actions.append("Changed the source label to Laser.")
    elif "led" in lowered:
        replace_or_add_led(updated, "LED")
        actions.append("Kept the source as an LED.")

    for keyword, label in (
        ("filter", "Filter"),
        ("lens", "Lens"),
        ("polarizer", "Polarizer"),
        ("sample", "Sample"),
        ("detector", "Detector"),
    ):
        if f"add {keyword}" in lowered or f"insert {keyword}" in lowered:
            add_optic_element(updated, label)
            actions.append(f"Added {label}.")

    if "camera" in lowered and ("add" in lowered or "larger" in lowered):
        ensure_camera(updated)
        actions.append("Ensured the camera stage is present.")

    artifact_bundle: dict[str, Any] | None = None
    if storage_dir and any(word in lowered for word in ("grid", "figure", "icons", "panels")):
        figure = generate_web_figure_grid({"prompt": text}, storage_dir, settings or load_backend_settings(storage_dir / "settings.json"))
        artifact_bundle = figure.get("artifacts")
        actions.append(f"Generated a {figure['rows']}x{figure['cols']} paper figure grid artifact.")

    if storage_dir and ("openscad" in lowered or "open scad" in lowered or "cad export" in lowered):
        export = export_web_openscad(updated, storage_dir)
        artifact_bundle = export.get("artifacts")
        actions.append("Exported the scene as an OpenSCAD planning artifact.")

    if storage_dir and looks_like_lab_task_prompt(text):
        lab_task = run_web_lab_task({"prompt": text, "mode": "auto", "execute": False}, storage_dir)
        artifact_bundle = lab_task.get("artifacts")
        actions.append(lab_task["reply"])

    if "biorender" in lowered:
        actions.append("BioRender settings are ready for the official MCP connector endpoint.")

    if not actions:
        actions.append("Kept the scene structure and prepared it for preview.")

    validate_scene_spec(updated)
    response = {
        "ok": True,
        "reply": " ".join(actions),
        "spec": updated,
        "actions": actions,
    }
    if artifact_bundle:
        response["artifacts"] = artifact_bundle
    return response


def render_web_scene(spec: dict[str, Any], storage_dir: Path) -> dict[str, Any]:
    storage_dir = Path(storage_dir).resolve()
    validate_scene_spec(spec)
    spec_dir = storage_dir / "specs"
    output_dir = storage_dir / "renders"
    spec_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(str(spec.get("slug") or spec.get("title") or "web-scene"))
    spec["slug"] = slug
    spec_path = spec_dir / f"{slug}.scene.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = render_scene_spec(spec_path, output_dir)
    png = Path(result["plan"]["png"])
    blend = Path(result["plan"]["blend"])
    stamp = int(png.stat().st_mtime) if png.exists() else 0
    store = ArtifactStore(storage_dir)
    image_item = store.register(png, title=f"Render: {result['plan']['title']}", kind="image", source="blender", preview="Headless Blender PNG render.")
    store.register(blend, title=f"Blend: {result['plan']['title']}", kind="model", source="blender", preview="Generated Blender scene file.", selected=False)
    store.register(spec_path, title=f"Scene spec: {result['plan']['title']}", kind="json", source="scene-spec", preview="JSON source of truth for the render.", selected=False)
    result.update(
        {
            "image_url": f"/artifacts/renders/{png.name}?v={stamp}",
            "blend_url": f"/artifacts/renders/{blend.name}?v={stamp}",
            "spec_url": f"/artifacts/specs/{spec_path.name}?v={stamp}",
            "artifact": image_item,
            "artifacts": store.bundle(),
        }
    )
    return result


def plan_web_scene(spec: dict[str, Any], storage_dir: Path) -> dict[str, Any]:
    storage_dir = Path(storage_dir).resolve()
    validate_scene_spec(spec)
    spec_dir = storage_dir / "specs"
    output_dir = storage_dir / "renders"
    spec_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(str(spec.get("slug") or spec.get("title") or "web-scene"))
    planned = deepcopy(spec)
    planned["slug"] = slug
    spec_path = spec_dir / f"{slug}.scene.json"
    spec_path.write_text(json.dumps(planned, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = render_scene_spec(spec_path, output_dir, dry_run=True)
    result["message"] = "Render plan is valid."
    return result


def target_list_response() -> dict[str, Any]:
    config = load_config()
    targets = [
        {
            "name": target.name,
            "kind": target.kind,
            "description": target.description,
            "transport": str(target.transport.get("type", "noop")),
            "enabled": target.enabled,
        }
        for target in config.targets
    ]
    return {"ok": True, "targets": targets}


def dispatch_web_target(payload: dict[str, Any], storage_dir: Path) -> dict[str, Any]:
    storage_dir = Path(storage_dir).resolve()
    target_name = str(payload.get("target") or "").strip()
    instruction = str(payload.get("instruction") or "").strip()
    dry_run = bool(payload.get("dry_run", True))
    timeout = float(payload.get("timeout") or 30)
    extra_payload = payload.get("payload") or {}
    if not isinstance(extra_payload, dict):
        raise ValueError("payload must be a JSON object")
    config = load_config()
    target = config.get_target(target_name)
    result = dispatch_target(target, instruction, extra_payload, dry_run=dry_run, timeout=timeout)
    output_dir = storage_dir / "dispatch"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = output_dir / f"{stamp}-{slugify(target.name)}.dispatch.json"
    output.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    store = ArtifactStore(storage_dir)
    item = store.register(
        output,
        title=f"Dispatch: {target.name}",
        kind="json",
        source="target-registry",
        preview=f"{result.status} via {result.transport}: {instruction[:96]}",
    )
    return {"ok": result.ok, "dispatch": result.to_dict(), "artifact": item, "artifacts": store.bundle()}


def generate_web_figure_grid(payload: dict[str, Any], storage_dir: Path, settings: dict[str, Any]) -> dict[str, Any]:
    storage_dir = Path(storage_dir).resolve()
    prompt = str(payload.get("prompt") or "scientific paper figure icons for an experiment setup")
    figure_settings = settings.get("figure", {}) if isinstance(settings.get("figure"), dict) else {}
    default_rows = int(figure_settings.get("rows") or 2)
    default_cols = int(figure_settings.get("cols") or 3)
    parsed_rows, parsed_cols = parse_grid_size(prompt, default_rows, default_cols)
    rows = int(payload.get("rows") or parsed_rows)
    cols = int(payload.get("cols") or parsed_cols)
    labels = payload.get("labels")
    if labels is not None and not isinstance(labels, list):
        raise ValueError("labels must be a list when provided")

    result = generate_icon_grid(
        prompt,
        storage_dir / "figures",
        rows=rows,
        cols=cols,
        cell_size=int(figure_settings.get("cell_size") or 240),
        border=int(figure_settings.get("border") or 4),
        labels=[str(label) for label in labels] if labels else None,
    )
    store = ArtifactStore(storage_dir)
    figure_item = store.register(
        result.path,
        title=f"Figure grid: {result.title}",
        kind="image",
        source="paper-figure",
        preview=f"Exact {result.rows}x{result.cols} SVG grid with black panel boundaries.",
    )

    aginti_prompt = (
        "Generate a clean set of no-text scientific icon concepts for a paper figure. "
        f"Topic: {prompt}. Keep each icon isolated, consistent, publication-safe, and suitable for a {result.rows}x{result.cols} panel grid."
    )
    aginti_result = run_aginti_image_request(
        aginti_prompt,
        storage_dir / "aginti" / result.path.stem,
        settings=settings,
        project_root=ROOT,
        output_stem=result.path.stem,
    )
    register_aginti_outputs(store, aginti_result)
    return {
        "ok": True,
        "rows": result.rows,
        "cols": result.cols,
        "figure": result.to_dict(),
        "figure_url": figure_item["url"],
        "artifact": figure_item,
        "artifacts": store.bundle(),
        "aginti": aginti_result,
    }


def export_web_openscad(spec: dict[str, Any], storage_dir: Path) -> dict[str, Any]:
    storage_dir = Path(storage_dir).resolve()
    result = export_scene_to_openscad(spec, storage_dir / "openscad")
    store = ArtifactStore(storage_dir)
    item = store.register(
        result.path,
        title=f"OpenSCAD: {result.title}",
        kind="openscad",
        source="openscad",
        preview="Simplified CAD proxy for mechanical layout planning.",
    )
    return {"ok": True, "export": result.to_dict(), "artifact": item, "artifacts": store.bundle()}


def run_web_lab_task(payload: dict[str, Any], storage_dir: Path) -> dict[str, Any]:
    return run_lab_task(payload, storage_dir, root=ROOT)


def run_web_agent_chat(payload: dict[str, Any], storage_dir: Path, *, settings: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message") or payload.get("prompt") or "").strip()
    if not message:
        raise ValueError("Agent chat message cannot be empty")
    agent_settings = settings.get("agent", {}) if isinstance(settings.get("agent"), dict) else {}
    prepared = dict(payload)
    if str(prepared.get("model") or "auto") == "auto" and not bool(agent_settings.get("dynamic_routing", True)):
        prepared["model"] = str(agent_settings.get("model") or "auto")
    if str(prepared.get("backend") or "auto") == "auto":
        prepared["backend"] = str(agent_settings.get("backend") or "auto")
    if not prepared.get("mode"):
        prepared["mode"] = str(agent_settings.get("mode") or "execute")
    prepared.setdefault("fallback_to_aginti", bool(agent_settings.get("fallback_to_aginti", True)))
    if bool(payload.get("dry_run", False)):
        policy = select_agent_policy(
            message,
            model=str(prepared.get("model") or "auto"),
            effort=str(prepared.get("effort") or "auto"),
            mode=str(prepared.get("mode") or "execute"),
            backend=str(prepared.get("backend") or "auto"),
        )
        return {
            "ok": True,
            "dry_run": True,
            "policy": policy,
            "prompt": build_agent_prompt(
                message,
                root=ROOT,
                task_dir=storage_dir / "agent" / "dry-run",
                policy=policy,
                conversation_id=str(prepared.get("conversation_id") or "web-default"),
                context=prepared.get("context") if isinstance(prepared.get("context"), dict) else {},
            ),
        }
    return create_agent_task(prepared, storage_dir, root=ROOT, launch=True)


def run_web_next_paragraph(
    payload: dict[str, Any],
    *,
    settings: dict[str, Any],
    deepseek_runner: Any | None = None,
) -> dict[str, Any]:
    messages = build_next_paragraph_messages(payload)
    if bool(payload.get("dry_run", False)):
        return {"ok": True, "dry_run": True, "messages": messages, "paragraph": ""}
    runner = deepseek_runner or run_deepseek_chat_completion
    raw = str(runner(messages, settings=settings) or "")
    paragraph = sanitize_next_paragraph(raw)
    if not paragraph:
        raise ValueError("DeepSeek returned no usable paragraph.")
    writing = settings.get("writing", {}) if isinstance(settings.get("writing"), dict) else {}
    return {
        "ok": True,
        "paragraph": paragraph,
        "model": str(writing.get("model") or "deepseek-v4-flash"),
    }


def build_next_paragraph_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    action = str(payload.get("action") or "next").strip().lower()
    action_text = {
        "next": "写全文自然延续的下一段。",
        "rewrite": "重写上一版草稿，但仍然只输出这一段。",
        "adjust": "按本轮方向调整上一版草稿，但仍然只输出这一段。",
    }.get(action, "写全文自然延续的下一段。")
    previous = str(payload.get("previous_draft") or "").strip()
    user_prompt = f"""请根据下面的完整上下文工作。

【全文】
{_context_value(payload, "full_text", "（正文为空，从第一段开始。）")}

【设定】
{_context_value(payload, "setting", "（未提供。）")}

【人物】
{_context_value(payload, "characters", "（未提供。）")}

【资料】
{_context_value(payload, "materials", "（未提供。）")}

【写作目标】
{_context_value(payload, "goal", "（未提供。）")}

【本轮方向】
{_context_value(payload, "direction", "（自然延续。）")}

【上一版草稿】
{previous or "（无。）"}

【本轮动作】
{action_text}

只输出最终段落本身。"""
    return [
        {
            "role": "system",
            "content": (
                "你是一个专用“下一段写作器”。每轮都会收到全文、设定、人物、资料、写作目标和本轮方向。"
                "你的唯一任务是写出下一个自然段。强制规则：只输出一个自然段；不要标题、列表、编号、提纲、解释、"
                "总结、Markdown、引号包装或多个候选；不要改写全文；不要提前跳到后续章节。"
            ),
        },
        {"role": "user", "content": user_prompt},
    ]


def run_deepseek_chat_completion(messages: list[dict[str, str]], *, settings: dict[str, Any]) -> str:
    writing = settings.get("writing", {}) if isinstance(settings.get("writing"), dict) else {}
    if not bool(writing.get("enabled", True)):
        raise ValueError("Writing backend is disabled.")
    provider = str(writing.get("provider") or "deepseek").strip().lower()
    if provider != "deepseek":
        raise ValueError(f"Unsupported writing backend: {provider}")
    api_key_env = str(writing.get("api_key_env") or "DEEPSEEK_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"DeepSeek API key is missing. Set {api_key_env} in the server environment.")
    base_url = str(writing.get("base_url") or "https://api.deepseek.com").rstrip("/")
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    body = json.dumps(
        {
            "model": str(writing.get("model") or "deepseek-v4-flash"),
            "messages": messages,
            "stream": False,
            "temperature": float(writing.get("temperature") or 0.75),
            "max_tokens": int(writing.get("max_tokens") or 480),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urlrequest.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    timeout = int(writing.get("timeout_seconds") or 60)
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise ValueError(f"DeepSeek API request failed: HTTP {exc.code} {detail}") from exc
    except urlerror.URLError as exc:
        raise ValueError(f"DeepSeek API request failed: {exc.reason}") from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise ValueError("DeepSeek API response did not include choices.")
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    return str(message.get("content") or first.get("text") or "")


def sanitize_next_paragraph(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    for block in re.split(r"\n\s*\n+", cleaned):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        candidate = " ".join(lines)
        candidate = re.sub(r"^(?:下一段|正文|草稿|输出|段落)\s*[:：]\s*", "", candidate).strip()
        candidate = re.sub(r"^(?:[-*•]|\d+[.)、])\s*", "", candidate).strip()
        candidate = candidate.strip(" \t\"'“”‘’")
        if candidate:
            return candidate
    return ""


def _context_value(payload: dict[str, Any], key: str, fallback: str) -> str:
    value = str(payload.get(key) or "").strip()
    return value or fallback


def register_aginti_outputs(store: ArtifactStore, result: dict[str, Any]) -> None:
    for key, title, kind in (
        ("promptPath", "AgInTi image prompt", "text"),
        ("requestPayloadPath", "AgInTi image request", "json"),
        ("manifestPath", "AgInTi image manifest", "json"),
    ):
        raw = result.get(key)
        if not raw:
            continue
        path = Path(str(raw))
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            store.register(path, title=title, kind=kind, source="aginti", preview=str(result.get("summary") or ""), selected=False)
    image_paths = result.get("imagePaths") or result.get("images") or []
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    if isinstance(image_paths, list):
        for raw in image_paths:
            path = Path(str(raw))
            if not path.is_absolute():
                path = ROOT / path
            if path.exists():
                store.register(path, title="AgInTi generated image", kind="image", source="aginti", preview=str(result.get("summary") or ""), selected=False)


def sanitize_settings(settings: Any) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise ValueError("settings must be a JSON object")
    blocked = {"api_key", "apikey", "token", "secret", "password"}

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items() if key.lower() not in blocked}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return scrub(settings)


def extract_quoted(text: str) -> str | None:
    match = re.search(r'"([^"]+)"|\'([^\']+)\'', text)
    if not match:
        return None
    return (match.group(1) or match.group(2)).strip() or None


def update_label(spec: dict[str, Any], name: str, text: str) -> None:
    for element in spec.get("elements", []):
        if element.get("type") == "label" and element.get("name") == name:
            element["text"] = text
            return
    spec.setdefault("elements", []).append(
        {"type": "label", "name": name, "text": text, "location": [0, -78, 22], "size": 9, "rotation": [75, 0, 0], "material": "white"}
    )


def replace_or_add_led(spec: dict[str, Any], label: str) -> None:
    for element in spec.get("elements", []):
        if element.get("type") == "led_source":
            element["label"] = label
            element["name"] = label.lower()
            return
    spec.setdefault("elements", []).insert(3, {"type": "led_source", "name": label.lower(), "x": -178, "label": label})


def add_optic_element(spec: dict[str, Any], label: str) -> None:
    elements = spec.setdefault("elements", [])
    if any(element.get("label") == label for element in elements):
        return
    occupied = [
        float(element["x"])
        for element in elements
        if element.get("type") in {"led_source", "optic", "lcd_light_valve", "event_camera"} and "x" in element
    ]
    x = next((slot for slot in [-100, -48, 16, 68, 124] if all(abs(slot - used) >= 24 for used in occupied)), max(occupied or [0]) + 34)
    material = "sample" if label == "Sample" else "glass"
    elements.append({"type": "optic", "name": label.lower().replace(" ", "_"), "x": x, "label": label, "material": material})


def ensure_camera(spec: dict[str, Any]) -> None:
    if any(element.get("type") == "event_camera" for element in spec.get("elements", [])):
        return
    spec.setdefault("elements", []).append({"type": "event_camera", "name": "camera", "x": 178, "label": "Camera"})
