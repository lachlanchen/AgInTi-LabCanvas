#!/usr/bin/env python3
"""Smoke-test the camera MCP simulator through the LabVIEW HTTP MCP bridge."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from camera_mcp_simulator import CameraMcpHandler  # noqa: E402


def make_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def parse_frames(data: bytes) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    offset = 0
    while offset < len(data):
        header_end = data.find(b"\r\n\r\n", offset)
        if header_end < 0:
            raise AssertionError(f"Missing MCP header terminator near byte {offset}")
        header = data[offset:header_end].decode("ascii")
        length = None
        for line in header.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise AssertionError(f"Missing Content-Length header: {header!r}")
        body_start = header_end + 4
        body_end = body_start + length
        frames.append(json.loads(data[body_start:body_end].decode("utf-8")))
        offset = body_end
    return frames


def run_bridge(url: str, frames: list[dict[str, Any]]) -> subprocess.CompletedProcess[bytes]:
    bridge = SCRIPT_DIR / "labview_http_mcp_bridge.py"
    stdin = b"".join(make_frame(frame) for frame in frames)
    return subprocess.run(
        [sys.executable, str(bridge), "--url", url, "--timeout", "5"],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tempdir:
        output_dir = Path(tempdir)
        CameraMcpHandler.output_dir = output_dir
        server = ThreadingHTTPServer(("127.0.0.1", 0), CameraMcpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            output = output_dir / "simulator.png"
            url = f"http://127.0.0.1:{server.server_port}/mcp/server"
            result = run_bridge(
                url,
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "camera.capture_simulator",
                            "arguments": {"output": str(output), "width": 640, "height": 360},
                        },
                    },
                ],
            )
        finally:
            server.shutdown()
            server.server_close()

        if result.returncode != 0:
            raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
        frames = parse_frames(result.stdout)
        assert frames[0]["result"]["serverInfo"]["name"] == "labcanvas-camera-simulator", frames
        assert any(tool["name"] == "camera.capture_simulator" for tool in frames[1]["result"]["tools"]), frames
        assert output.exists(), output
        payload = json.loads(frames[2]["result"]["content"][0]["text"])
        assert payload["source"] == "simulator", payload
        assert payload["width"] == 640, payload
        assert payload["height"] == 360, payload

    print("Camera MCP simulator smoke test passed: initialize, tools/list, tools/call, image output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
