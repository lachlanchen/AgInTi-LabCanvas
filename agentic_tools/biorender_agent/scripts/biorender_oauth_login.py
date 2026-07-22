#!/usr/bin/env python3
"""Authorize BioRender MCP in the dedicated browser and save a private token."""

from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
from threading import Event
import time
from urllib import parse, request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLIENT_FILE = ROOT / ".private" / "oauth-client.local.json"
DEFAULT_TOKEN_FILE = ROOT / ".private" / "oauth-token.local.json"
DEFAULT_BROWSER_OPENER = Path(__file__).with_name("open_biorender_url.py")
AUTHORITY = "https://mcp.services.biorender.com"
RESOURCE = "https://mcp.services.biorender.com"
REDIRECT_URI = "http://127.0.0.1:1455/callback"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def load_client(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("OAuth client file must contain an object")
    required = ("client_id", "client_secret")
    if not all(str(payload.get(key) or "").strip() for key in required):
        raise ValueError("OAuth client file is missing client_id or client_secret")
    return payload


def write_private_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        query = parse.parse_qs(parse.urlsplit(self.path).query)
        if self.path.split("?", 1)[0] != "/callback":
            self.send_error(404)
            return
        self.server.callback = {
            "code": str(query.get("code", [""])[0]),
            "state": str(query.get("state", [""])[0]),
            "error": str(query.get("error", [""])[0]),
        }
        body = b"BioRender MCP authorization received. You can close this tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.server.received.set()

    def log_message(self, fmt: str, *args: object) -> None:
        return


def exchange_code(
    *, client: dict[str, object], code: str, verifier: str, redirect_uri: str
) -> dict[str, object]:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": str(client["client_id"]),
        "client_secret": str(client["client_secret"]),
        "code_verifier": verifier,
        "resource": RESOURCE,
    }
    token_request = request.Request(
        f"{AUTHORITY}/oauth/token",
        data=parse.urlencode(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "AgInTi-LabCanvas-BioRender-OAuth/1",
        },
        method="POST",
    )
    with request.urlopen(token_request, timeout=30) as response:
        token = json.loads(response.read().decode("utf-8"))
    if not isinstance(token, dict) or not token.get("access_token"):
        raise RuntimeError("BioRender token endpoint returned no access token")
    token["obtained_at"] = int(time.time())
    token["expires_at"] = int(time.time()) + int(token.get("expires_in") or 3600)
    return token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-file", type=Path, default=DEFAULT_CLIENT_FILE)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--browser-opener", type=Path, default=DEFAULT_BROWSER_OPENER)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = load_client(args.client_file.expanduser().resolve())
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    query = parse.urlencode(
        {
            "response_type": "code",
            "client_id": str(client["client_id"]),
            "redirect_uri": REDIRECT_URI,
            "scope": "profile email openid offline_access",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": RESOURCE,
        }
    )
    server = ThreadingHTTPServer(("127.0.0.1", 1455), CallbackHandler)
    server.timeout = 0.5
    server.received = Event()
    server.callback = {}
    try:
        subprocess.run(
            [str(args.browser_opener.expanduser().resolve()), f"{AUTHORITY}/oauth/authorize?{query}"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + max(10.0, min(args.timeout, 600.0))
        while not server.received.is_set() and time.monotonic() < deadline:
            server.handle_request()
        callback = server.callback
    finally:
        server.server_close()
    if not callback or callback.get("state") != state:
        raise RuntimeError("BioRender OAuth callback was missing or failed state validation")
    if callback.get("error") or not callback.get("code"):
        raise RuntimeError("BioRender OAuth authorization was rejected")
    token = exchange_code(
        client=client,
        code=str(callback["code"]),
        verifier=verifier,
        redirect_uri=REDIRECT_URI,
    )
    token_file = args.token_file.expanduser().resolve()
    write_private_json(token_file, token)
    subprocess.run(
        [
            str(args.browser_opener.expanduser().resolve()),
            "https://app.biorender.com/gallery/illustrations",
            "--close-callbacks",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    print(json.dumps({"ok": True, "authenticated": True, "token_file": str(token_file)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
