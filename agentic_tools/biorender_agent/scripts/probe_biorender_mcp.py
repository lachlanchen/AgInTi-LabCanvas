#!/usr/bin/env python3
"""Run an authenticated initialize/tools-list probe against BioRender MCP."""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib import request


DEFAULT_URL = "http://127.0.0.1:19682/mcp"
PROTOCOL_VERSION = "2025-06-18"


def parse_mcp_body(body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    if text.startswith("{"):
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    for line in reversed(data_lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("MCP response was neither JSON nor a JSON SSE data event")


def post_rpc(url: str, payload: dict[str, Any], *, session_id: str = "") -> tuple[dict[str, Any], str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "User-Agent": "AgInTi-LabCanvas-BioRender-Probe/1",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = request.urlopen(
        request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        ),
        timeout=30,
    )
    with response:
        body = response.read()
        next_session = response.headers.get("Mcp-Session-Id", session_id)
    return parse_mcp_body(body), next_session


def probe(url: str) -> dict[str, Any]:
    initialized, session_id = post_rpc(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "labcanvas-biorender-probe", "version": "1.0"},
            },
        },
    )
    if initialized.get("error"):
        raise RuntimeError(f"BioRender MCP initialize failed: {initialized['error']}")
    post_rpc(
        url,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        session_id=session_id,
    )
    tools_payload, _ = post_rpc(
        url,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        session_id=session_id,
    )
    if tools_payload.get("error"):
        raise RuntimeError(f"BioRender MCP tools/list failed: {tools_payload['error']}")
    tools = ((tools_payload.get("result") or {}).get("tools") or [])
    names = [str(tool.get("name") or "") for tool in tools if isinstance(tool, dict)]
    return {
        "ok": bool(names),
        "authenticated": bool(names),
        "server": ((initialized.get("result") or {}).get("serverInfo") or {}),
        "protocol_version": ((initialized.get("result") or {}).get("protocolVersion") or ""),
        "tool_count": len(names),
        "tools": names,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = probe(args.url)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"BioRender MCP ready: {result['tool_count']} tools")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
