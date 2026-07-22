#!/usr/bin/env python3
"""Local OAuth-discovery compatibility proxy for BioRender's official MCP.

BioRender currently advertises its authorization-server metadata URL directly
in ``WWW-Authenticate``. MCP clients that require protected-resource metadata
reject that response before OAuth starts. This localhost-only proxy supplies
the missing protected-resource document and otherwise forwards MCP traffic
without storing credentials or access tokens.
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from threading import Lock
import time
from typing import Iterable
from urllib import error, parse, request


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19682
DEFAULT_UPSTREAM = "https://mcp.services.biorender.com/mcp"
DEFAULT_AUTHORITY = "https://mcp.services.biorender.com"
PRIVATE_DIR = Path(__file__).resolve().parents[1] / ".private"
DEFAULT_TOKEN_FILE = PRIVATE_DIR / "oauth-token.local.json"
DEFAULT_CLIENT_FILE = PRIVATE_DIR / "oauth-client.local.json"
MAX_REQUEST_BYTES = 16 * 1024 * 1024
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def protected_resource_document(resource: str) -> dict[str, object]:
    return {
        "resource": resource,
        "authorization_servers": [resource],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "bearer_methods_supported": ["header"],
    }


class TokenStore:
    """Read and refresh a private BioRender OAuth token without logging it."""

    def __init__(self, token_file: Path, client_file: Path, authority: str) -> None:
        self.token_file = token_file
        self.client_file = client_file
        self.authority = authority.rstrip("/")
        self._lock = Lock()

    def authorization_header(self, *, force_refresh: bool = False) -> str:
        with self._lock:
            token = self._load(self.token_file)
            if not token:
                return ""
            expires_at = float(token.get("expires_at") or 0)
            should_refresh = force_refresh or (
                bool(token.get("refresh_token")) and expires_at and expires_at <= time.time() + 60
            )
            if should_refresh:
                try:
                    refreshed = self._refresh(token)
                except (OSError, ValueError, error.URLError, TimeoutError, json.JSONDecodeError):
                    refreshed = {}
                if refreshed:
                    token = refreshed
            access_token = str(token.get("access_token") or "").strip()
            token_type = str(token.get("token_type") or "Bearer").strip() or "Bearer"
            return f"{token_type} {access_token}" if access_token else ""

    def _refresh(self, token: dict[str, object]) -> dict[str, object]:
        refresh_token = str(token.get("refresh_token") or "").strip()
        client = self._load(self.client_file)
        client_id = str(client.get("client_id") or "").strip()
        client_secret = str(client.get("client_secret") or "").strip()
        if not (refresh_token and client_id and client_secret):
            return {}
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        response = request.urlopen(
            request.Request(
                f"{self.authority}/oauth/token",
                data=parse.urlencode(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": "AgInTi-LabCanvas-BioRender-OAuth/1",
                },
                method="POST",
            ),
            timeout=30,
        )
        with response:
            refreshed = json.loads(response.read().decode("utf-8"))
        if not isinstance(refreshed, dict) or not refreshed.get("access_token"):
            return {}
        if not refreshed.get("refresh_token"):
            refreshed["refresh_token"] = refresh_token
        refreshed["obtained_at"] = int(time.time())
        refreshed["expires_at"] = int(time.time()) + int(refreshed.get("expires_in") or 3600)
        self._write_private(self.token_file, refreshed)
        return refreshed

    @staticmethod
    def _load(path: Path) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _write_private(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(path)


def authorization_server_document(issuer: str, authority: str) -> dict[str, object]:
    authority = authority.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{authority}/oauth/authorize",
        "token_endpoint": f"{authority}/oauth/token",
        "registration_endpoint": f"{authority}/oauth/register",
        "scopes_supported": ["profile", "email", "openid", "offline_access"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
    }


def patched_authenticate_header(metadata_url: str) -> str:
    return f'Bearer resource_metadata="{metadata_url}"'


def forwarded_request_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in headers:
        lowered = name.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered in {"host", "content-length"}:
            continue
        result[name] = value
    result.setdefault("User-Agent", "AgInTi-LabCanvas-BioRender-MCP/1")
    return result


class BioRenderProxyHandler(BaseHTTPRequestHandler):
    server_version = "LabCanvasBioRenderMCP/1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/.well-known/oauth-protected-resource":
            self.write_json(
                HTTPStatus.OK,
                protected_resource_document(self.server.resource_url),
            )
            return
        if "oauth-authorization-server" in self.path or "openid-configuration" in self.path:
            self.write_json(
                HTTPStatus.OK,
                authorization_server_document(
                    self.server.resource_url,
                    self.server.authority,
                ),
            )
            return
        self.forward()

    def do_POST(self) -> None:  # noqa: N802
        self.forward()

    def do_DELETE(self) -> None:  # noqa: N802
        self.forward()

    def forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > MAX_REQUEST_BYTES:
            self.write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
            return
        body = self.rfile.read(length) if length else None
        headers = forwarded_request_headers(self.headers.items())
        if "Authorization" not in headers:
            authorization = self.server.token_store.authorization_header()
            if authorization:
                headers["Authorization"] = authorization
        upstream = request.Request(self.server.upstream, data=body, headers=headers, method=self.command)
        try:
            response = request.urlopen(upstream, timeout=self.server.upstream_timeout)
        except error.HTTPError as exc:
            if exc.code == HTTPStatus.UNAUTHORIZED and "Authorization" in headers:
                refreshed = self.server.token_store.authorization_header(force_refresh=True)
                if refreshed:
                    headers["Authorization"] = refreshed
                    retry = request.Request(
                        self.server.upstream,
                        data=body,
                        headers=headers,
                        method=self.command,
                    )
                    try:
                        response = request.urlopen(retry, timeout=self.server.upstream_timeout)
                    except error.HTTPError as retry_exc:
                        self.write_upstream(retry_exc.code, retry_exc.headers.items(), retry_exc.read())
                        return
                    with response:
                        self.write_upstream(response.status, response.headers.items(), response.read())
                    return
            self.write_upstream(exc.code, exc.headers.items(), exc.read())
            return
        except (error.URLError, TimeoutError) as exc:
            self.write_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": "biorender upstream unavailable", "detail": str(exc)[:300]},
            )
            return
        with response:
            self.write_upstream(response.status, response.headers.items(), response.read())

    def write_upstream(
        self,
        status: int,
        headers: Iterable[tuple[str, str]],
        body: bytes,
    ) -> None:
        self.send_response(status)
        content_type = "application/octet-stream"
        for name, value in headers:
            lowered = name.lower()
            if lowered == "content-type":
                content_type = value
                continue
            if lowered in HOP_BY_HOP_HEADERS or lowered in {
                "content-length",
                "www-authenticate",
                "date",
                "server",
            }:
                continue
            self.send_header(name, value)
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_header(
                "WWW-Authenticate",
                patched_authenticate_header(self.server.metadata_url),
            )
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def write_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt: str, *args: object) -> None:
        if self.server.verbose:
            super().log_message(fmt, *args)


class BioRenderProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        upstream: str,
        authority: str,
        token_file: Path,
        client_file: Path,
        upstream_timeout: float,
        verbose: bool,
    ) -> None:
        super().__init__(address, BioRenderProxyHandler)
        host, port = self.server_address[:2]
        self.upstream = upstream
        self.authority = authority.rstrip("/")
        self.token_store = TokenStore(token_file, client_file, self.authority)
        self.resource_url = f"http://{host}:{port}/mcp"
        self.metadata_url = (
            f"http://{host}:{port}/.well-known/oauth-protected-resource"
        )
        self.upstream_timeout = upstream_timeout
        self.verbose = verbose


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    parser.add_argument("--authority", default=DEFAULT_AUTHORITY)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--client-file", type=Path, default=DEFAULT_CLIENT_FILE)
    parser.add_argument("--upstream-timeout", type=float, default=300.0)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing to expose the BioRender compatibility proxy remotely.", file=sys.stderr)
        return 2
    server = BioRenderProxyServer(
        (args.host, args.port),
        upstream=args.upstream,
        authority=args.authority,
        token_file=args.token_file.expanduser().resolve(),
        client_file=args.client_file.expanduser().resolve(),
        upstream_timeout=max(1.0, min(args.upstream_timeout, 300.0)),
        verbose=args.verbose,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "event": "started",
                "resource_url": server.resource_url,
                "metadata_url": server.metadata_url,
                "upstream": server.upstream,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
