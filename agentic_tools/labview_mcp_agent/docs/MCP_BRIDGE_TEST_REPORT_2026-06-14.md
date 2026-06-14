# LabVIEW MCP Bridge Test Report - 2026-06-14

This report records what was tested after installing LabVIEW 2026 Q1 Community and adding the LabVIEW MCP bridge tooling.

## Scope

Tested locally:

- Python stdio MCP frame parsing and response framing.
- Forwarding JSON-RPC payloads from MCP stdio to a LabVIEW-style HTTP endpoint.
- JSON-RPC request behavior for `initialize` and `tools/list`.
- Notification forwarding for `notifications/initialized`.
- Error response behavior when the LabVIEW HTTP endpoint is unavailable.
- Silent failure behavior for endpoint errors on notifications.
- Installed `LabVIEWCLI` command availability.

Not fully tested yet:

- Live `nineman-YU/Labview_mcp` VI server inside LabVIEW.
- Real LabVIEW tool calls through `src/mcp_server_main.vi`.

The live server test requires LabVIEW first-launch activation/sign-in and a running LabVIEW MCP server VI.

## Commands Run

Bridge smoke test:

```bash
python agentic_tools/labview_mcp_agent/scripts/test_mcp_bridge.py
```

Result:

```text
MCP bridge smoke test passed: forwarding, response framing, notification handling, endpoint errors.
```

Python syntax check:

```bash
python -m py_compile \
  agentic_tools/labview_mcp_agent/scripts/labview_http_mcp_bridge.py \
  agentic_tools/labview_mcp_agent/scripts/test_mcp_bridge.py \
  tests/test_labview_mcp_bridge.py
```

LabVIEW CLI check:

```bash
LabVIEWCLI -help
```

Confirmed `LabVIEWCLI` exposes `RunVI`, `CloseLabVIEW`, `-Headless`, `-LabVIEWPath`, and `-PortNumber`.

Linux operation-specific check:

```bash
LabVIEWCLI -LabVIEWPath /usr/local/natinst/LabVIEW-2026-64/labview -OperationName RunVI -Help
```

Observed behavior:

- LabVIEW launched successfully according to `/tmp/lvtemporary_711730.log`.
- No operation-specific help body was printed in this environment.

## Mock Endpoint Behavior

The smoke test starts an in-process HTTP server that emulates a LabVIEW MCP endpoint at:

```text
http://127.0.0.1:<dynamic-port>/mcp/server
```

The test sends three MCP stdio frames through `labview_http_mcp_bridge.py`:

- `initialize`, request id `1`
- `notifications/initialized`, no request id
- `tools/list`, request id `2`

Expected result:

- Two MCP stdio response frames are emitted, one for each request.
- No response frame is emitted for the notification.
- The mock endpoint receives all three payloads at `/mcp/server`.
- The `tools/list` result includes a mock `echo` tool.

The test also sends a request to an unavailable endpoint and verifies a JSON-RPC error:

```json
{"code": -32000, "message": "LabVIEW endpoint unavailable: ..."}
```

For an unavailable endpoint notification, the bridge emits no response frame.

## Live MCP Server Procedure

After LabVIEW activation:

1. Launch LabVIEW:

```bash
labview64
```

2. Open the cloned candidate:

```text
/home/lachlan/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp/src/mcp_server_main.vi
```

3. Run the VI so it listens on the documented default endpoint:

```text
http://127.0.0.1:36987/mcp/server
```

4. Test the bridge against the live VI server with an MCP client config based on:

```text
agentic_tools/labview_mcp_agent/mcp.example.json
```

5. Minimal manual HTTP probe once the VI is running:

```bash
curl -sS -X POST http://127.0.0.1:36987/mcp/server \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Status

The repository bridge path is tested and working. The remaining boundary is not Python/MCP code; it is the LabVIEW-side VI server lifecycle and activation state.

Current live endpoint check:

```bash
python - <<'PY'
import json, urllib.request
url = "http://127.0.0.1:36987/mcp/server"
payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=2) as response:
    print(response.status, response.read().decode())
PY
```

Result on 2026-06-14:

```text
LIVE_ENDPOINT_UNAVAILABLE URLError <urlopen error [Errno 111] Connection refused>
```

Port check:

```bash
ss -ltnp | rg ':36987'
```

Result: no listener on port `36987`.
