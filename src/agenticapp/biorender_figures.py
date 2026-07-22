from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
from typing import Any, Callable
from urllib import request

from .artifacts import ArtifactStore
from .scene_spec import slugify


DEFAULT_MCP_URL = "http://127.0.0.1:19682/mcp"
ROOT = Path(__file__).resolve().parents[2]
CDP_EXPORT_SCRIPT = ROOT / "agentic_tools" / "biorender_agent" / "scripts" / "export_biorender_figure.py"
PROTOCOL_VERSION = "2025-06-18"
TERMINAL_PREVIEW_STATES = {"completed", "failed", "content_moderation_error"}


class BioRenderFigureError(RuntimeError):
    pass


@dataclass
class BioRenderMcpClient:
    url: str = DEFAULT_MCP_URL
    timeout: float = 60.0
    session_id: str = ""
    request_id: int = 0

    def initialize(self) -> dict[str, Any]:
        payload = self.rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "labcanvas-biorender-figure", "version": "1.0"},
            },
        )
        self.rpc("notifications/initialized", {}, notification=True)
        return payload

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.rpc("tools/call", {"name": name, "arguments": arguments})

    def rpc(self, method: str, params: dict[str, Any], *, notification: bool = False) -> dict[str, Any]:
        self.request_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = self.request_id
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": "AgInTi-LabCanvas-BioRender-Figure/1",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        response = request.urlopen(
            request.Request(
                self.url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            ),
            timeout=self.timeout,
        )
        with response:
            body = response.read()
            self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
        result = parse_mcp_body(body)
        if isinstance(result.get("error"), dict):
            message = str(result["error"].get("message") or result["error"])
            raise BioRenderFigureError(f"BioRender MCP {method} failed: {message}")
        return result


def parse_mcp_body(body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    if text.startswith("{"):
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    for line in reversed([line[5:].strip() for line in text.splitlines() if line.startswith("data:")]):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise BioRenderFigureError("BioRender MCP returned neither JSON nor a JSON SSE event")


def normalize_panels(values: Any) -> list[dict[str, str]]:
    panels: list[dict[str, str]] = []
    if not isinstance(values, list):
        return panels
    for index, value in enumerate(values):
        if isinstance(value, dict):
            panel_id = str(value.get("id") or chr(ord("A") + index)).strip().upper()
            title = str(value.get("title") or value.get("description") or "").strip()
            description = str(value.get("description") or title).strip()
        else:
            raw = str(value or "").strip()
            head, separator, tail = raw.partition(":")
            panel_id = head.strip().upper() if separator and len(head.strip()) <= 3 else chr(ord("A") + index)
            title = tail.strip() if separator else raw
            description = title
        if description:
            panels.append({"id": panel_id, "title": title or description, "description": description})
    return panels


def build_nature_figure_prompt(spec: dict[str, Any]) -> str:
    title = str(spec.get("title") or "Scientific mechanism and experimental roadmap").strip()
    subject = str(spec.get("prompt") or "").strip()
    panels = normalize_panels(spec.get("panels"))
    panel_text = "\n".join(
        f"Panel {panel['id']} — {panel['title']}: {panel['description']}" for panel in panels
    ) or "Use one coherent left-to-right mechanism and experimental workflow."
    return f"""Create an editable, publication-grade BioRender scientific figure titled \"{title}\".

Scientific purpose:
{subject}

Panel plan:
{panel_text}

Visual and scientific requirements:
- Nature-style clarity: white background, restrained teal/coral/gold/blue accents, dark charcoal text, no gradients or decorative effects.
- Use a strict aligned grid with equal outer margins, consistent panel widths, baseline-aligned headings, even gutters, and generous whitespace.
- Make the reading order unambiguous from left to right and top to bottom; use short orthogonal arrows and avoid crossing connectors.
- Use biologically accurate BioRender assets and consistent scale. Distinguish neural tissue, endothelial cells, pericytes, astrocytes, microglia, ECM, lumen, and perfusion by shape and color, not by dense prose.
- Keep labels concise and fully inside their panels. Use one sans-serif font family, three type levels, and no tiny text.
- Clearly label hypotheses, failure modes, interventions, and readouts. Do not imply experimental results or numerical effects that were not supplied.
- Preserve every panel as editable BioRender objects. Avoid a photographic or painterly overview.
- Produce one landscape figure suitable for a high-impact review or research proposal, visually balanced and immediately understandable at column width.
""".strip()


def run_biorender_figure(
    payload: dict[str, Any],
    storage_dir: Path,
    *,
    client: BioRenderMcpClient | Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    storage_dir = storage_dir.expanduser().resolve()
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("BioRender figure prompt is required")
    title = str(payload.get("title") or "Publication figure").strip()
    panels = normalize_panels(payload.get("panels"))
    run_id = str(payload.get("run_id") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = storage_dir / "biorender" / f"{slugify(title)}-{slugify(run_id)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "schema_version": 1,
        "title": title,
        "prompt": prompt,
        "panels": panels,
        "template_id": str(payload.get("template_id") or "").strip(),
        "editable_source": "BioRender MCP custom figure session",
        "layout_contract": {
            "grid_aligned": True,
            "equal_margins": True,
            "consistent_gutters": True,
            "orthogonal_non_crossing_connectors": True,
            "restrained_nature_palette": True,
        },
    }
    generated_prompt = build_nature_figure_prompt(spec)
    prompt_path = run_dir / "figure-prompt.md"
    manifest_path = run_dir / "figure-manifest.json"
    prompt_path.write_text(generated_prompt + "\n", encoding="utf-8")
    write_manifest(manifest_path, {**spec, "status": "planned", "prompt_path": str(prompt_path)})

    if not bool(payload.get("live")):
        return register_biorender_artifacts(
            storage_dir,
            manifest_path,
            prompt_path,
            image_path=None,
            summary={**spec, "status": "dry_run", "run_dir": str(run_dir)},
        )

    client = client or BioRenderMcpClient(
        url=str(payload.get("mcp_url") or DEFAULT_MCP_URL),
        timeout=max(10.0, float(payload.get("request_timeout") or 330.0)),
    )
    client.initialize()
    create_args: dict[str, Any] = {"prompt": generated_prompt}
    if spec["template_id"]:
        create_args["canvasContext"] = {"type": "template", "templateId": spec["template_id"]}
    created = client.call_tool("custom-figure-create-session", create_args)
    created_data = tool_data(created)
    session_id = find_string(created_data, "sessionId", "session_id")
    job_id = find_string(created_data, "jobId", "job_id")
    if not session_id or not job_id:
        raise BioRenderFigureError("BioRender did not return a custom-figure session and preview job")

    timeout_seconds = max(30.0, float(payload.get("timeout_seconds") or 900.0))
    poll_seconds = max(0.2, float(payload.get("poll_seconds") or 5.0))
    deadline = time.monotonic() + timeout_seconds
    job_status = "pending"
    job_payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        job_payload = client.call_tool("custom-figure-get-preview-job", {"jobId": job_id})
        job_status = find_status(tool_data(job_payload)) or "pending"
        if job_status in TERMINAL_PREVIEW_STATES:
            break
        sleep(poll_seconds)
    if job_status != "completed":
        raise BioRenderFigureError(f"BioRender preview ended with status {job_status}")

    session_payload = client.call_tool(
        "custom-figure-get-session",
        {"sessionId": session_id, "includeImages": True, "maxImages": 1},
    )
    image_bytes, mime = extract_mcp_image(session_payload)
    if not image_bytes:
        raise BioRenderFigureError("BioRender session completed without a preview image")
    suffix = ".png" if mime == "image/png" else ".jpg" if mime in {"image/jpeg", "image/jpg"} else ".bin"
    preview_path = run_dir / f"{slugify(title)}-mcp-preview{suffix}"
    preview_path.write_bytes(image_bytes)
    width, height = image_dimensions(image_bytes, mime)
    min_width = max(1, int(payload.get("min_width") or 1200))
    min_height = max(1, int(payload.get("min_height") or 700))
    quality = {
        "readable_image": bool(width and height),
        "width": width,
        "height": height,
        "size_bytes": len(image_bytes),
        "minimum_width": min_width,
        "minimum_height": min_height,
        "dimensions_pass": width >= min_width and height >= min_height,
        "landscape_pass": width > height,
    }
    if not quality["readable_image"]:
        raise BioRenderFigureError("BioRender preview is not a readable PNG/JPEG image")

    client.call_tool("custom-figure-confirm-preview", {"jobId": job_id})
    session_data = tool_data(session_payload)
    editor_url = find_string(session_data, "url")
    figure_id = find_string(session_data, "figureId", "figure_id")
    image_path = preview_path
    print_export: dict[str, Any] = {}
    if bool(payload.get("cdp_export", True)) and editor_url:
        print_export = export_biorender_print_png(
            editor_url,
            run_dir / f"{slugify(title)}-300dpi.png",
            cdp_url=str(payload.get("cdp_url") or "http://127.0.0.1:9389"),
            timeout_seconds=max(30.0, float(payload.get("export_timeout") or 240.0)),
            screenshot_dir=run_dir / "browser-checks",
        )
        exported = Path(str(print_export.get("output") or ""))
        if print_export.get("ok") and exported.is_file():
            image_path = exported
            width = int(print_export.get("width") or width)
            height = int(print_export.get("height") or height)
            quality.update(
                {
                    "width": width,
                    "height": height,
                    "size_bytes": int(print_export.get("size_bytes") or image_path.stat().st_size),
                    "dimensions_pass": width >= min_width and height >= min_height,
                    "landscape_pass": width > height,
                    "print_export_300dpi": True,
                }
            )
    summary = {
        **spec,
        "status": "completed" if quality["dimensions_pass"] and quality["landscape_pass"] else "quality_review_required",
        "run_dir": str(run_dir),
        "session_id": session_id,
        "job_id": job_id,
        "figure_id": figure_id,
        "editor_url": editor_url,
        "image_path": str(image_path),
        "mcp_preview_path": str(preview_path),
        "print_export": print_export,
        "quality": quality,
    }
    write_manifest(manifest_path, summary)
    return register_biorender_artifacts(storage_dir, manifest_path, prompt_path, image_path=image_path, summary=summary)


def export_biorender_print_png(
    editor_url: str,
    output: Path,
    *,
    cdp_url: str,
    timeout_seconds: float,
    screenshot_dir: Path,
) -> dict[str, Any]:
    if not CDP_EXPORT_SCRIPT.is_file():
        return {"ok": False, "error": "BioRender CDP export helper is missing"}
    command = [
        sys.executable,
        str(CDP_EXPORT_SCRIPT),
        "--editor-url",
        editor_url,
        "--output",
        str(output),
        "--cdp-url",
        cdp_url,
        "--timeout",
        str(timeout_seconds),
        "--screenshot-dir",
        str(screenshot_dir),
        "--json",
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "error": (proc.stderr or proc.stdout or "invalid export response")[:700]}
    return payload if isinstance(payload, dict) else {"ok": False, "error": "invalid export response"}


def tool_data(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    structured = result.get("structuredContent") if isinstance(result.get("structuredContent"), dict) else {}
    if structured:
        return structured
    for item in result.get("content") or []:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        try:
            value = json.loads(str(item.get("text") or ""))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return result


def find_string(value: Any, *keys: str) -> str:
    wanted = set(keys)
    if isinstance(value, dict):
        for key, child in value.items():
            if key in wanted and isinstance(child, (str, int)) and str(child).strip():
                return str(child).strip()
        for child in value.values():
            found = find_string(child, *keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_string(child, *keys)
            if found:
                return found
    return ""


def find_status(value: Any) -> str:
    status = find_string(value, "status", "state").lower()
    aliases = {"succeeded": "completed", "success": "completed", "done": "completed"}
    return aliases.get(status, status)


def extract_mcp_image(response: dict[str, Any]) -> tuple[bytes, str]:
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    for item in result.get("content") or []:
        if not isinstance(item, dict) or item.get("type") != "image":
            continue
        encoded = str(item.get("data") or item.get("imageBase64") or "")
        if encoded:
            return base64.b64decode(encoded), str(item.get("mimeType") or "image/png")
    structured = result.get("structuredContent") if isinstance(result.get("structuredContent"), dict) else {}
    encoded = find_string(structured, "imageBase64")
    if encoded:
        return base64.b64decode(encoded), find_string(structured, "mimeType") or "image/png"
    return b"", ""


def image_dimensions(data: bytes, mime: str) -> tuple[int, int]:
    if mime == "image/png" and len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", data[16:24])
    if mime in {"image/jpeg", "image/jpg"} and data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(data):
                break
            length = struct.unpack(">H", data[index:index + 2])[0]
            if marker in range(0xC0, 0xC4) and index + 7 <= len(data):
                height, width = struct.unpack(">HH", data[index + 3:index + 7])
                return width, height
            index += max(2, length)
    return 0, 0


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def register_biorender_artifacts(
    storage_dir: Path,
    manifest_path: Path,
    prompt_path: Path,
    *,
    image_path: Path | None,
    summary: dict[str, Any],
) -> dict[str, Any]:
    store = ArtifactStore(storage_dir)
    manifest_item = store.register(
        manifest_path,
        title=f"BioRender manifest: {summary['title']}",
        kind="json",
        source="biorender-figure",
        preview="Editable panel plan, generation identity, and quality gates.",
        selected=image_path is None,
    )
    prompt_item = store.register(
        prompt_path,
        title=f"BioRender prompt: {summary['title']}",
        kind="text",
        source="biorender-figure",
        preview="Exact reusable MCP figure prompt.",
        selected=False,
    )
    image_item = None
    if image_path is not None:
        image_item = store.register(
            image_path,
            title=summary["title"],
            kind="image",
            source="biorender-figure",
            preview="Editable BioRender figure preview.",
            selected=True,
        )
    return {
        "ok": summary.get("status") in {"completed", "dry_run", "quality_review_required"},
        "status": summary.get("status"),
        "figure": summary,
        "artifact": image_item or manifest_item,
        "manifest_artifact": manifest_item,
        "prompt_artifact": prompt_item,
        "artifacts": store.bundle(),
    }
