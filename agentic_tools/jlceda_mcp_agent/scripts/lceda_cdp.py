#!/usr/bin/env python3
"""Small CDP helper for the local LCEDA Pro Electron app."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


def fetch_json(port: int, path: str) -> object:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def command_status(args: argparse.Namespace) -> int:
    targets = fetch_json(args.port, "/json/list")
    pages = []
    for target in targets:
        pages.append(
            {
                "id": target.get("id"),
                "type": target.get("type"),
                "title": target.get("title"),
                "url": target.get("url"),
            }
        )
    print(json.dumps({"ok": True, "port": args.port, "targets": pages}, ensure_ascii=False, indent=2))
    return 0


class CdpClient:
    def __init__(self, ws_url: str, origin: str):
        try:
            import websocket  # type: ignore
        except ImportError as exc:
            raise SystemExit("Install dependencies: pip install -r agentic_tools/jlceda_mcp_agent/requirements.txt") from exc
        self.ws = websocket.create_connection(ws_url, timeout=8, origin=origin)
        self.next_id = 1

    def call(self, method: str, params: dict | None = None) -> dict:
        msg_id = self.next_id
        self.next_id += 1
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = self.ws.recv()
            payload = json.loads(raw)
            if payload.get("id") == msg_id:
                if "error" in payload:
                    raise RuntimeError(f"{method}: {payload['error']}")
                return payload.get("result", {})

    def close(self) -> None:
        self.ws.close()


def choose_page(port: int) -> dict:
    targets = fetch_json(port, "/json/list")
    pages = [target for target in targets if target.get("type") == "page"]
    if not pages:
        raise SystemExit("No LCEDA page target found")
    for page in pages:
        title = page.get("title") or ""
        url = page.get("url") or ""
        if "嘉立创" in title or "LCEDA" in title or "client/editor" in url:
            return page
    return pages[0]


def runtime_eval(cdp: CdpClient, expression: str) -> object:
    result = cdp.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
    )
    remote = result.get("result", {})
    return remote.get("value")


def command_activate(args: argparse.Namespace) -> int:
    activation_file = Path(args.file).expanduser().resolve()
    if not activation_file.exists():
        raise SystemExit(f"Activation file not found: {activation_file}")

    page = choose_page(args.port)
    ws_url = page.get("webSocketDebuggerUrl")
    if not ws_url:
        raise SystemExit("Selected target does not expose a CDP websocket URL")

    cdp = CdpClient(ws_url, origin=f"http://127.0.0.1:{args.port}")
    try:
        cdp.call("DOM.enable")
        cdp.call("Runtime.enable")
        doc = cdp.call("DOM.getDocument", {"depth": -1, "pierce": True})
        root_id = doc["root"]["nodeId"]
        query = cdp.call(
            "DOM.querySelector",
            {
                "nodeId": root_id,
                "selector": "input.upload-input[type=file], input[type=file]",
            },
        )
        node_id = query.get("nodeId", 0)
        if not node_id:
            print(json.dumps({"ok": False, "reason": "no activation file input found; app may already be activated"}, ensure_ascii=False))
            return 1

        cdp.call("DOM.setFileInputFiles", {"nodeId": node_id, "files": [str(activation_file)]})
        time.sleep(0.5)
        snapshot = runtime_eval(
            cdp,
            """(() => ({
              title: document.title,
              url: location.href,
              textareaLength: document.querySelector('textarea.activateContent')?.value?.length || 0,
              buttons: Array.from(document.querySelectorAll('button')).map((b, i) => ({i, text: b.innerText.trim()})).slice(0, 20)
            }))()""",
        )
        clicked = runtime_eval(
            cdp,
            """(() => {
              const button = Array.from(document.querySelectorAll('button'))
                .find((b) => /激活/.test(b.innerText) && !/导入/.test(b.innerText));
              if (!button) return false;
              button.click();
              return true;
            })()""",
        )
        print(json.dumps({"ok": bool(clicked), "safeSnapshot": snapshot}, ensure_ascii=False, indent=2))
        return 0 if clicked else 1
    finally:
        cdp.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=51370)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--port", type=int, default=argparse.SUPPRESS)
    status.set_defaults(func=command_status)

    activate = sub.add_parser("activate")
    activate.add_argument("--port", type=int, default=argparse.SUPPRESS)
    activate.add_argument("--file", default="~/Downloads/lceda-pro-activation.txt")
    activate.set_defaults(func=command_activate)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
