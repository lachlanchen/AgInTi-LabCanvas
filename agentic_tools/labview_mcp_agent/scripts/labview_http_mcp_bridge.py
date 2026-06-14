#!/usr/bin/env python3
"""Forward stdio MCP JSON-RPC frames to a LabVIEW HTTP JSON-RPC endpoint."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def read_frame() -> dict | None:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            return None
        header += chunk

    length = None
    for raw_line in header.decode("ascii", errors="replace").split("\r\n"):
        if raw_line.lower().startswith("content-length:"):
            length = int(raw_line.split(":", 1)[1].strip())
            break
    if length is None:
        raise RuntimeError("Missing Content-Length header")

    body = sys.stdin.buffer.read(length)
    if len(body) != length:
        return None
    return json.loads(body.decode("utf-8"))


def write_frame(payload: dict) -> None:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def post_json(url: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    if not raw:
        return {"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}
    return json.loads(raw.decode("utf-8"))


def error_response(request_id: object, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:36987/mcp/server",
        help="LabVIEW HTTP JSON-RPC endpoint.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    while True:
        try:
            payload = read_frame()
            if payload is None:
                return 0
            request_id = payload.get("id")
            response = post_json(args.url, payload, args.timeout)
            if request_id is not None:
                write_frame(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            write_frame(error_response(locals().get("request_id", None), -32000, f"LabVIEW endpoint unavailable: {exc}"))
        except Exception as exc:  # Keep the MCP process alive for client diagnostics.
            write_frame(error_response(locals().get("request_id", None), -32603, str(exc)))


if __name__ == "__main__":
    raise SystemExit(main())
