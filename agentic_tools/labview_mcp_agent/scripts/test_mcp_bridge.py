#!/usr/bin/env python3
"""Smoke-test the LabVIEW HTTP MCP bridge with a mock LabVIEW endpoint."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


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
        if body_end > len(data):
            raise AssertionError("Truncated MCP response body")
        frames.append(json.loads(data[body_start:body_end].decode("utf-8")))
        offset = body_end
    return frames


class MockLabVIEWHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests.append({"path": self.path, "payload": payload})

        request_id = payload.get("id")
        method = payload.get("method")
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "mock-labview", "version": "0.0-test"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Mock LabVIEW echo tool",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            }
        else:
            result = {}

        response = (
            b"{}"
            if request_id is None
            else json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}).encode("utf-8")
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_bridge(url: str, frames: list[dict[str, Any]]) -> subprocess.CompletedProcess[bytes]:
    bridge = Path(__file__).with_name("labview_http_mcp_bridge.py")
    stdin = b"".join(make_frame(frame) for frame in frames)
    return subprocess.run(
        [sys.executable, str(bridge), "--url", url, "--timeout", "2"],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


def test_forwarding() -> None:
    MockLabVIEWHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockLabVIEWHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/mcp/server"
        result = run_bridge(
            url,
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ],
        )
    finally:
        server.shutdown()
        server.server_close()

    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))

    frames = parse_frames(result.stdout)
    assert len(frames) == 2, frames
    assert frames[0]["id"] == 1, frames
    assert frames[0]["result"]["serverInfo"]["name"] == "mock-labview", frames
    assert frames[1]["id"] == 2, frames
    assert frames[1]["result"]["tools"][0]["name"] == "echo", frames
    assert [item["path"] for item in MockLabVIEWHandler.requests] == ["/mcp/server"] * 3
    assert [item["payload"]["method"] for item in MockLabVIEWHandler.requests] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]


def test_unavailable_endpoint_error() -> None:
    result = run_bridge(
        "http://127.0.0.1:1/mcp/server",
        [{"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}],
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    frames = parse_frames(result.stdout)
    assert len(frames) == 1, frames
    assert frames[0]["id"] == 99, frames
    assert frames[0]["error"]["code"] == -32000, frames
    assert "LabVIEW endpoint unavailable" in frames[0]["error"]["message"], frames


def test_unavailable_endpoint_notification_is_silent() -> None:
    result = run_bridge(
        "http://127.0.0.1:1/mcp/server",
        [{"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}],
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    assert result.stdout == b"", result.stdout


def main() -> int:
    test_forwarding()
    test_unavailable_endpoint_error()
    test_unavailable_endpoint_notification_is_silent()
    print("MCP bridge smoke test passed: forwarding, response framing, notification handling, endpoint errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
