# LabVIEW MCP Tooling Reference

This reference lists the code, scripts, config files, and external tools used by the LabVIEW MCP integration for AgInTi LabCanvas.

## Repository Scripts

### `scripts/install_labview_linux.sh`

Installs Linux prerequisites, extracts a downloaded NI LabVIEW ZIP, installs the Ubuntu feed package that matches the host release, and installs the LabVIEW edition meta package.

Example:

```bash
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh --search-dir /home/lachlan/Downloads
```

Important behavior:

- Looks for `*labview*.zip` and `ni-labview*.deb`.
- Prefers `ubuntu2404` on Ubuntu 24.04.
- Prints candidate apt packages before installing.
- Does not download NI installers or store NI credentials.

### `scripts/probe_labview.sh`

Reports OS, NI/LabVIEW packages, launchers, likely install paths, and support packages.

Example:

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
```

Expected launcher output after install:

```text
labview: not in PATH
labview64: /usr/local/bin/labview64
LabVIEWCLI: /usr/local/bin/LabVIEWCLI
```

### `scripts/launch_labview.sh`

Launches LabVIEW from the first available Linux launcher. It defaults to `labview64`, then `labview`, then `/usr/local/natinst/LabVIEW-2026-64/labview`.

Examples:

```bash
agentic_tools/labview_mcp_agent/scripts/launch_labview.sh
LABVIEW_USE_XVFB=1 agentic_tools/labview_mcp_agent/scripts/launch_labview.sh
LABVIEW_BIN=/usr/local/natinst/LabVIEW-2026-64/labview agentic_tools/labview_mcp_agent/scripts/launch_labview.sh
```

### `scripts/install_mcp_candidate.sh`

Clones or updates known LabVIEW MCP candidate repositories under:

```text
~/.local/share/labview-mcp-agent/candidates
```

Recommended candidate:

```bash
agentic_tools/labview_mcp_agent/scripts/install_mcp_candidate.sh nineman
```

Current candidate path:

```text
/home/lachlan/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp
```

### `scripts/labview_http_mcp_bridge.py`

Bridges MCP stdio frames to a LabVIEW HTTP JSON-RPC endpoint.

Default endpoint:

```text
http://127.0.0.1:36987/mcp/server
```

Example:

```bash
python3 agentic_tools/labview_mcp_agent/scripts/labview_http_mcp_bridge.py \
  --url http://127.0.0.1:36987/mcp/server
```

Behavior:

- Reads `Content-Length` MCP stdio frames.
- POSTs each JSON-RPC payload to the LabVIEW endpoint.
- Emits response frames for requests with an `id`.
- Does not emit response frames for notifications.
- Returns JSON-RPC `-32000` errors when the LabVIEW endpoint is unavailable for request payloads.

### `scripts/test_mcp_bridge.py`

Standalone smoke test for `labview_http_mcp_bridge.py`.

Example:

```bash
python agentic_tools/labview_mcp_agent/scripts/test_mcp_bridge.py
```

It starts a mock LabVIEW HTTP endpoint and verifies forwarding, response framing, notification handling, and endpoint-unavailable diagnostics.

## Test Suite

The bridge smoke test is also wired into the repository unit tests:

```bash
PYTHONPATH=src python -m unittest tests.test_labview_mcp_bridge
PYTHONPATH=src python -m unittest discover -s tests
```

## Config Files

### `mcp.example.json`

Example MCP client server config for the bridge:

```json
{
  "mcpServers": {
    "labview-http": {
      "command": "python3",
      "args": [
        "agentic_tools/labview_mcp_agent/scripts/labview_http_mcp_bridge.py",
        "--url",
        "http://127.0.0.1:36987/mcp/server"
      ],
      "env": {}
    }
  }
}
```

Use an absolute script path if the MCP client starts outside the repository root.

### `config.example.json`

Human-readable local configuration template for LabVIEW launcher and MCP endpoint settings.

Key values:

- `labview.launcher`: `labview64`
- `labview.path`: `/usr/local/natinst/LabVIEW-2026-64/labview`
- `mcp.port`: `36987`
- `mcp.endpoint`: `/mcp/server`

## External Tools

### LabVIEW Community

Installed launcher:

```bash
labview64
```

Direct binary:

```text
/usr/local/natinst/LabVIEW-2026-64/labview
```

### LabVIEWCLI

Installed command:

```bash
LabVIEWCLI -help
```

Linux requires explicit LabVIEW path for operations that start LabVIEW:

```bash
LabVIEWCLI -LabVIEWPath /usr/local/natinst/LabVIEW-2026-64/labview -OperationName CloseLabVIEW
```

### nineman-YU LabVIEW MCP Candidate

Candidate VI entry point:

```text
/home/lachlan/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp/src/mcp_server_main.vi
```

Documented default HTTP endpoint:

```text
http://127.0.0.1:36987/mcp/server
```

Documented MCP methods:

- `initialize`
- `tools/list`
- `tools/call`
- `prompts/list`
- `prompts/get`
- `resources/list`
- `resources/read`
- `shutdown`

## Current Boundary

The Python bridge and MCP framing are tested. Full live MCP execution needs LabVIEW activated and the LabVIEW-side server VI running. Until then, `tools/list` against `127.0.0.1:36987` is expected to fail with an endpoint-unavailable error.
