# JLCEDA MCP Agent

Local tooling for installing JLCEDA/LCEDA Pro, keeping it launchable with a
stable Chrome DevTools port, and preparing MCP-based PCB automation.

## Current Local Setup

- App archive: `~/Downloads/lceda-pro-linux-x64-3.2.149.zip`
- Local install: `~/.local/opt/lceda-pro-3.2.149/lceda-pro`
- Wrapper: `~/.local/bin/lceda-pro`
- CDP launch port: `51370`
- User data: `~/Documents/LCEDA-Pro` and `~/.config/LCEDA-Pro`
- Activation: applied locally from `~/Downloads/lceda-pro-activation.txt`; do not
  commit activation files or copied license data.

## Commands

Install or repair the local app wrapper:

```bash
agentic_tools/jlceda_mcp_agent/scripts/install_lceda_pro_local.sh \
  ~/Downloads/lceda-pro-linux-x64-3.2.149.zip
```

Launch LCEDA with a reusable CDP port:

```bash
agentic_tools/jlceda_mcp_agent/scripts/launch_lceda_pro.sh --restart --port 51370
agentic_tools/jlceda_mcp_agent/scripts/launch_lceda_pro.sh --status
```

Inspect the running Electron targets:

```bash
python3 agentic_tools/jlceda_mcp_agent/scripts/lceda_cdp.py status --port 51370
```

Install/build the strongest MCP candidate:

```bash
agentic_tools/jlceda_mcp_agent/scripts/install_jlcmcp.sh
```

This clones `hyl64/jlcmcp` to `~/.local/share/appautoaction/mcp/jlcmcp`,
builds the MCP server, builds `jlc-bridge.eext`, and runs a protocol smoke test.

## MCP Wiring

Use this MCP client entry after `install_jlcmcp.sh` succeeds:

```json
{
  "mcpServers": {
    "jlceda": {
      "command": "node",
      "args": ["/home/lachlan/.local/share/appautoaction/mcp/jlcmcp/dist/index.js"],
      "env": {
        "GATEWAY_WS_URL": "ws://127.0.0.1:18800/ws/bridge"
      }
    }
  }
}
```

Real board editing also requires the `jlc-bridge` extension installed inside
LCEDA Pro and a gateway process listening on `ws://127.0.0.1:18800/ws/bridge`.
Without that bridge, the MCP server can list tools but cannot move components,
route tracks, or read the active PCB.

## References

- [LCEDA local setup](docs/LCEDA_PRO_LOCAL_SETUP.md)
- [MCP candidates](docs/MCP_CANDIDATES.md)
