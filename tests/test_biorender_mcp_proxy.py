import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "agentic_tools" / "biorender_agent" / "scripts" / "biorender_mcp_proxy.py"
PROBE_SCRIPT = ROOT / "agentic_tools" / "biorender_agent" / "scripts" / "probe_biorender_mcp.py"
OPEN_SCRIPT = ROOT / "agentic_tools" / "biorender_agent" / "scripts" / "open_biorender_url.py"


def load_proxy():
    spec = importlib.util.spec_from_file_location("biorender_mcp_proxy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_probe():
    spec = importlib.util.spec_from_file_location("biorender_mcp_probe", PROBE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_opener():
    spec = importlib.util.spec_from_file_location("biorender_browser_opener", OPEN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BioRenderMcpProxyTests(unittest.TestCase):
    def test_browser_opener_identifies_only_private_oauth_callback(self):
        opener = load_opener()

        self.assertTrue(opener.is_oauth_callback_url("http://127.0.0.1:1455/callback?code=private"))
        self.assertTrue(opener.is_oauth_callback_url("http://localhost:1455/callback?state=private"))
        self.assertFalse(opener.is_oauth_callback_url("http://127.0.0.1:1455/other"))
        self.assertFalse(opener.is_oauth_callback_url("https://app.biorender.com/gallery/illustrations"))

    def test_probe_parser_accepts_json_and_sse(self):
        probe = load_probe()

        direct = probe.parse_mcp_body(b'{"jsonrpc":"2.0","id":1,"result":{}}')
        streamed = probe.parse_mcp_body(
            b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n\n'
        )

        self.assertEqual(direct["id"], 1)
        self.assertEqual(streamed["id"], 2)

    def test_protected_resource_document_names_local_resource(self):
        proxy = load_proxy()

        payload = proxy.protected_resource_document("http://127.0.0.1:19682/mcp")

        self.assertEqual(payload["resource"], "http://127.0.0.1:19682/mcp")
        self.assertEqual(
            payload["authorization_servers"],
            ["http://127.0.0.1:19682/mcp"],
        )
        self.assertIn("offline_access", payload["scopes_supported"])

    def test_authorization_server_document_keeps_official_endpoints(self):
        proxy = load_proxy()

        payload = proxy.authorization_server_document(
            "http://127.0.0.1:19682/mcp",
            "https://mcp.services.biorender.com",
        )

        self.assertEqual(payload["issuer"], "http://127.0.0.1:19682/mcp")
        self.assertEqual(
            payload["authorization_endpoint"],
            "https://mcp.services.biorender.com/oauth/authorize",
        )
        self.assertEqual(
            payload["registration_endpoint"],
            "https://mcp.services.biorender.com/oauth/register",
        )

    def test_authenticate_header_points_to_local_metadata(self):
        proxy = load_proxy()

        value = proxy.patched_authenticate_header(
            "http://127.0.0.1:19682/.well-known/oauth-protected-resource"
        )

        self.assertEqual(
            value,
            'Bearer resource_metadata="http://127.0.0.1:19682/.well-known/oauth-protected-resource"',
        )

    def test_forwarded_headers_preserve_authorization_but_drop_hop_by_hop(self):
        proxy = load_proxy()

        headers = proxy.forwarded_request_headers(
            [
                ("Authorization", "Bearer private"),
                ("Mcp-Session-Id", "session"),
                ("Content-Length", "123"),
                ("Connection", "keep-alive"),
                ("Host", "localhost"),
            ]
        )

        self.assertEqual(headers["Authorization"], "Bearer private")
        self.assertEqual(headers["Mcp-Session-Id"], "session")
        self.assertNotIn("Content-Length", headers)
        self.assertNotIn("Connection", headers)
        self.assertNotIn("Host", headers)

    def test_proxy_rewrites_discovery_and_forwards_authorized_body(self):
        proxy = load_proxy()

        class UpstreamHandler(BaseHTTPRequestHandler):
            received_authorization = ""
            received_body = b""

            def do_GET(self):  # noqa: N802
                self.send_response(401)
                self.send_header(
                    "WWW-Authenticate",
                    'Bearer resource_metadata="https://wrong.example/metadata"',
                )
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                type(self).received_authorization = self.headers.get("Authorization", "")
                type(self).received_body = self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, fmt, *args):
                return

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        upstream_thread = Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        upstream_url = f"http://127.0.0.1:{upstream.server_port}/mcp"
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        token_file = Path(private.name) / "token.json"
        client_file = Path(private.name) / "client.json"
        token_file.write_text(
            json.dumps({"access_token": "injected-token", "token_type": "Bearer"}),
            encoding="utf-8",
        )
        client_file.write_text("{}", encoding="utf-8")
        server = proxy.BioRenderProxyServer(
            ("127.0.0.1", 0),
            upstream=upstream_url,
            authority="https://mcp.services.biorender.com",
            token_file=token_file,
            client_file=client_file,
            upstream_timeout=5,
            verbose=False,
        )
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(error.HTTPError) as caught:
                request.urlopen(f"{base}/mcp", timeout=5)
            self.assertEqual(caught.exception.code, 401)
            self.assertEqual(
                caught.exception.headers["WWW-Authenticate"],
                f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource"',
            )
            self.assertEqual(len(caught.exception.headers.get_all("Content-Type")), 1)

            metadata = request.urlopen(
                f"{base}/.well-known/oauth-protected-resource", timeout=5
            ).read()
            self.assertIn(b'"authorization_servers"', metadata)

            authorization_metadata = request.urlopen(
                f"{base}/.well-known/oauth-authorization-server/mcp", timeout=5
            ).read()
            self.assertIn(b'"authorization_endpoint"', authorization_metadata)
            self.assertIn(base.encode("utf-8") + b'/mcp', authorization_metadata)

            post = request.Request(
                f"{base}/mcp",
                data=b'{"jsonrpc":"2.0"}',
                headers={"Authorization": "Bearer test-token"},
                method="POST",
            )
            response = request.urlopen(post, timeout=5)
            self.assertEqual(response.read(), b'{"ok":true}')
            self.assertEqual(UpstreamHandler.received_authorization, "Bearer test-token")
            self.assertEqual(UpstreamHandler.received_body, b'{"jsonrpc":"2.0"}')

            post_without_auth = request.Request(
                f"{base}/mcp",
                data=b'{"jsonrpc":"2.0","id":2}',
                method="POST",
            )
            response = request.urlopen(post_without_auth, timeout=5)
            self.assertEqual(response.read(), b'{"ok":true}')
            self.assertEqual(
                UpstreamHandler.received_authorization,
                "Bearer injected-token",
            )
        finally:
            server.shutdown()
            server.server_close()
            upstream.shutdown()
            upstream.server_close()


if __name__ == "__main__":
    unittest.main()
