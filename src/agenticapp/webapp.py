from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import threading
from typing import Any
import webbrowser

from .blender_render import BlenderRenderError, render_scene_spec
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
        if self.path == "/" or self.path.startswith("/?"):
            self.send_static("index.html")
        elif self.path.startswith("/static/"):
            self.send_static(self.path.removeprefix("/static/"))
        elif self.path == "/api/spec":
            self.send_json(default_spec_response())
        elif self.path == "/api/health":
            self.send_json({"ok": True})
        elif self.path == "/example-render":
            self.send_example_render()
        elif self.path.startswith("/artifacts/"):
            self.send_artifact(self.path.removeprefix("/artifacts/").split("?", 1)[0])
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
            if self.path == "/api/chat":
                payload = self.read_json()
                spec = payload.get("spec") or default_scene_spec()
                message = str(payload.get("message", ""))
                self.send_json(chat_update(spec, message))
            elif self.path == "/api/render":
                payload = self.read_json()
                spec = payload.get("spec") or default_scene_spec()
                self.send_json(render_web_scene(spec, self.storage_dir))
            elif self.path == "/api/plan":
                payload = self.read_json()
                spec = payload.get("spec") or default_scene_spec()
                self.send_json(plan_web_scene(spec, self.storage_dir))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (BlenderRenderError, ValueError, KeyError) as exc:
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
        content_type = "application/octet-stream"
        if path.suffix == ".png":
            content_type = "image/png"
        elif path.suffix == ".blend":
            content_type = "application/octet-stream"
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


def chat_update(spec: dict[str, Any], message: str) -> dict[str, Any]:
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
        updated.setdefault("render", {})["world_color"] = [0.78, 0.80, 0.82]
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

    if not actions:
        actions.append("Kept the scene structure and prepared it for preview.")

    validate_scene_spec(updated)
    return {
        "ok": True,
        "reply": " ".join(actions),
        "spec": updated,
        "actions": actions,
    }


def render_web_scene(spec: dict[str, Any], storage_dir: Path) -> dict[str, Any]:
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
    result.update(
        {
            "image_url": f"/artifacts/renders/{png.name}?v={stamp}",
            "blend_url": f"/artifacts/renders/{blend.name}?v={stamp}",
            "spec_url": f"/artifacts/specs/{spec_path.name}?v={stamp}",
        }
    )
    return result


def plan_web_scene(spec: dict[str, Any], storage_dir: Path) -> dict[str, Any]:
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
    optic_count = sum(1 for element in elements if element.get("type") in {"optic", "lcd_light_valve"})
    x = -126 + optic_count * 34
    material = "sample" if label == "Sample" else "glass"
    elements.append({"type": "optic", "name": label.lower().replace(" ", "_"), "x": x, "label": label, "material": material})


def ensure_camera(spec: dict[str, Any]) -> None:
    if any(element.get("type") == "event_camera" for element in spec.get("elements", [])):
        return
    spec.setdefault("elements", []).append({"type": "event_camera", "name": "camera", "x": 178, "label": "Camera"})
