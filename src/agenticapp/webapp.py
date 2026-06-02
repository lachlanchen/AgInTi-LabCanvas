from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import threading
from typing import Any
import webbrowser

from .adapters import DispatchError, dispatch_target
from .artifacts import ArtifactStore, content_type_for_path
from .backends import backend_status, load_backend_settings, run_aginti_image_request, save_backend_settings
from .blender_render import BlenderRenderError, render_scene_spec
from .config import load_config
from .openscad_export import export_scene_to_openscad
from .paper_figures import generate_icon_grid, parse_grid_size
from .scene_spec import built_in_scene_template, slugify, validate_scene_spec


ROOT = Path.cwd()
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
    return ThreadingHTTPServer((host, bind_port), AppAutoActionHandler)


def first_available_port(host: str, start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port found from {start} to {start + 49}")


class AppAutoActionHandler(BaseHTTPRequestHandler):
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
            self.send_head_for_file(ROOT / "examples" / "renders" / "paper-optics-setup.png", "image/png")
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
            elif route == "/api/dispatch":
                payload = self.read_json()
                self.send_json(dispatch_web_target(payload, self.storage_dir))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (BlenderRenderError, DispatchError, ValueError, KeyError) as exc:
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
        path = ROOT / "examples" / "renders" / "paper-optics-setup.png"
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
    preview = ROOT / "examples" / "renders" / "paper-optics-setup.png"
    preview_url = None
    if preview.exists():
        preview_url = "/example-render"
    return {"ok": True, "spec": spec, "preview_url": preview_url}


def default_scene_spec() -> dict[str, Any]:
    example = ROOT / "examples" / "paper-optics-setup.scene.json"
    if example.exists():
        return json.loads(example.read_text(encoding="utf-8"))
    return built_in_scene_template("experiment-setup")


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
