#!/usr/bin/env python3
"""Camera MCP simulator and local V4L2 capture endpoint.

This script is intentionally independent from LabVIEW. It gives AgInTi/Codex a
repeatable camera endpoint while the real LabVIEW VI MCP server is being
activated or debugged.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageStat


DEFAULT_OUTPUT_DIR = Path("output/labview_mcp_camera") / datetime.now().strftime("%Y-%m-%d")


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_output_path(path: str | Path | None, output_dir: Path, suffix: str) -> Path:
    if path:
        target = Path(path)
    else:
        target = output_dir / f"{suffix}_{timestamp_slug()}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def image_summary(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        stat = ImageStat.Stat(rgb)
        return {
            "path": str(path.resolve()),
            "width": rgb.width,
            "height": rgb.height,
            "mode": rgb.mode,
            "mean_rgb": [round(value, 2) for value in stat.mean],
        }


def create_simulator_frame(
    output: Path,
    width: int = 1280,
    height: int = 720,
    label: str = "AgInTi LabCanvas simulated camera",
) -> dict[str, Any]:
    image = Image.new("RGB", (width, height), (246, 248, 244))
    draw = ImageDraw.Draw(image)

    # Light gradient background.
    for y in range(height):
        tone = int(238 + 14 * y / max(height - 1, 1))
        draw.line([(0, y), (width, y)], fill=(tone, min(255, tone + 4), min(255, tone + 8)))

    grid = max(40, width // 20)
    for x in range(0, width, grid):
        draw.line([(x, 0), (x, height)], fill=(207, 214, 218), width=1)
    for y in range(0, height, grid):
        draw.line([(0, y), (width, y)], fill=(207, 214, 218), width=1)

    colors = [
        (225, 52, 62),
        (245, 166, 35),
        (245, 226, 78),
        (44, 177, 99),
        (43, 134, 238),
        (112, 82, 195),
    ]
    bar_width = width // len(colors)
    for index, color in enumerate(colors):
        x0 = index * bar_width
        x1 = width if index == len(colors) - 1 else (index + 1) * bar_width
        draw.rectangle([x0, 0, x1, height // 7], fill=color)

    cx = width // 2
    cy = height // 2
    radius = min(width, height) // 5
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(20, 20, 20), width=5)
    draw.line([(cx - radius - 60, cy), (cx + radius + 60, cy)], fill=(20, 20, 20), width=3)
    draw.line([(cx, cy - radius - 60), (cx, cy + radius + 60)], fill=(20, 20, 20), width=3)

    for offset, color in [(-260, colors[0]), (-130, colors[1]), (0, colors[3]), (130, colors[4]), (260, colors[5])]:
        draw.ellipse([cx + offset - 30, cy + radius + 55, cx + offset + 30, cy + radius + 115], fill=color)

    font = ImageFont.load_default()
    timestamp = datetime.now().isoformat(timespec="seconds")
    draw.rectangle([24, height - 92, width - 24, height - 24], fill=(255, 255, 255), outline=(32, 38, 44), width=2)
    draw.text((42, height - 76), label, fill=(20, 27, 32), font=font)
    draw.text((42, height - 52), f"{width}x{height} synthetic frame | {timestamp}", fill=(66, 74, 80), font=font)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    summary = image_summary(output)
    summary["source"] = "simulator"
    return summary


def capture_v4l2_frame(
    output: Path,
    device: str = "/dev/video0",
    width: int = 1280,
    height: int = 720,
    warmup_frames: int = 8,
) -> dict[str, Any]:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - exercised only on missing optional dep
        raise RuntimeError("OpenCV is required for V4L2 capture. Install opencv-python.") from exc

    capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open V4L2 camera device: {device}")

    try:
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        frame = None
        ok = False
        for _ in range(max(1, warmup_frames)):
            ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"Could not read a frame from {device}")
        output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output), frame):
            raise RuntimeError(f"Could not write captured frame: {output}")
    finally:
        capture.release()

    summary = image_summary(output)
    summary["source"] = "v4l2"
    summary["device"] = device
    return summary


def mcp_result(payload: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
        "isError": is_error,
    }


class CameraMcpHandler(BaseHTTPRequestHandler):
    output_dir = DEFAULT_OUTPUT_DIR
    default_device = "/dev/video0"
    default_width = 1280
    default_height = 720

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        response = self.handle_jsonrpc(payload)
        body = json.dumps(response, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_jsonrpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        if request_id is None:
            return {}

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "labcanvas-camera-simulator", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                }
            elif method == "tools/list":
                result = {"tools": self.tool_descriptions()}
            elif method == "tools/call":
                params = payload.get("params", {})
                result = self.call_tool(str(params.get("name", "")), params.get("arguments", {}) or {})
            else:
                return self.error_response(request_id, -32601, f"Unknown method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": mcp_result({"error": str(exc)}, is_error=True)}

    def tool_descriptions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "camera.capture_simulator",
                "description": "Generate a synthetic camera calibration frame.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "output": {"type": "string"},
                        "width": {"type": "integer", "default": self.default_width},
                        "height": {"type": "integer", "default": self.default_height},
                        "label": {"type": "string"},
                    },
                },
            },
            {
                "name": "camera.capture_v4l2",
                "description": "Capture one frame from a Linux V4L2 camera device such as /dev/video0.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "default": self.default_device},
                        "output": {"type": "string"},
                        "width": {"type": "integer", "default": self.default_width},
                        "height": {"type": "integer", "default": self.default_height},
                    },
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        width = int(arguments.get("width", self.default_width))
        height = int(arguments.get("height", self.default_height))
        if name == "camera.capture_simulator":
            output = ensure_output_path(arguments.get("output"), self.output_dir, "simulator_capture")
            summary = create_simulator_frame(output, width, height, str(arguments.get("label", "AgInTi LabCanvas simulated camera")))
            return mcp_result(summary)
        if name == "camera.capture_v4l2":
            device = str(arguments.get("device", self.default_device))
            suffix = f"{Path(device).name}_capture"
            output = ensure_output_path(arguments.get("output"), self.output_dir, suffix)
            summary = capture_v4l2_frame(output, device, width, height)
            return mcp_result(summary)
        return mcp_result({"error": f"Unknown tool: {name}"}, is_error=True)

    def error_response(self, request_id: object, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve(host: str, port: int, output_dir: Path, device: str, width: int, height: int) -> None:
    CameraMcpHandler.output_dir = output_dir
    CameraMcpHandler.default_device = device
    CameraMcpHandler.default_width = width
    CameraMcpHandler.default_height = height
    server = ThreadingHTTPServer((host, port), CameraMcpHandler)
    print(f"Camera MCP simulator listening at http://{host}:{server.server_port}/mcp/server", flush=True)
    server.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulator = subparsers.add_parser("capture-simulator", help="Generate one synthetic camera frame.")
    simulator.add_argument("--output", type=Path, default=None)
    simulator.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    simulator.add_argument("--width", type=int, default=1280)
    simulator.add_argument("--height", type=int, default=720)
    simulator.add_argument("--label", default="AgInTi LabCanvas simulated camera")

    v4l2 = subparsers.add_parser("capture-v4l2", help="Capture one frame from a V4L2 device.")
    v4l2.add_argument("--device", default="/dev/video0")
    v4l2.add_argument("--output", type=Path, default=None)
    v4l2.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    v4l2.add_argument("--width", type=int, default=1280)
    v4l2.add_argument("--height", type=int, default=720)

    server = subparsers.add_parser("serve", help="Serve the camera tools as a JSON-RPC MCP HTTP endpoint.")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=36988)
    server.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    server.add_argument("--device", default="/dev/video0")
    server.add_argument("--width", type=int, default=1280)
    server.add_argument("--height", type=int, default=720)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "capture-simulator":
        output = ensure_output_path(args.output, args.output_dir, "simulator_capture")
        print(json.dumps(create_simulator_frame(output, args.width, args.height, args.label), indent=2, sort_keys=True))
        return 0
    if args.command == "capture-v4l2":
        output = ensure_output_path(args.output, args.output_dir, f"{Path(args.device).name}_capture")
        print(json.dumps(capture_v4l2_frame(output, args.device, args.width, args.height), indent=2, sort_keys=True))
        return 0
    if args.command == "serve":
        serve(args.host, args.port, args.output_dir, args.device, args.width, args.height)
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
