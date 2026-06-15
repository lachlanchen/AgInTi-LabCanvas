# LabVIEW MCP Agent

This folder documents and scripts the LabVIEW path for AgInTi LabCanvas. It covers three layers:

1. Install/check LabVIEW on this Ubuntu workstation.
2. Clone and prepare a LabVIEW MCP candidate.
3. Expose the resulting LabVIEW automation path to Codex/AgInTi through MCP configuration.

LabVIEW itself is proprietary NI software. The scripts can install dependencies and consume a downloaded NI Linux installer package, but they cannot bypass NI login, license, or entitlement checks.

## Status on This Machine

- OS: Ubuntu 24.04.4 LTS, x86_64.
- Already present: `xvfb`, `libopenal1`, `libncurses6`.
- Installed: LabVIEW 2026 Q1 Community via NI Ubuntu 24.04 feed.
- Main launcher: `/usr/local/bin/labview64`.
- CLI launcher: `/usr/local/bin/LabVIEWCLI`.
- First GUI launch may still require NI activation/sign-in.

## Quick Commands

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh --dry-run
agentic_tools/labview_mcp_agent/scripts/install_mcp_candidate.sh nineman
agentic_tools/labview_mcp_agent/scripts/launch_labview.sh
agentic_tools/labview_mcp_agent/scripts/start_labview_local_server.sh
python agentic_tools/labview_mcp_agent/scripts/test_mcp_bridge.py
LabVIEWCLI -help
```

After downloading a Linux LabVIEW installer from NI, place the `.zip` or `.deb` in `~/Downloads` and run:

```bash
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh
```

## Recommended MCP Candidate

Use `nineman-YU/Labview_mcp` first for Linux. It hosts an MCP server from LabVIEW via JSON-RPC over HTTP and documents LabVIEW 2022 Q3 and 26.1 paths.

`CalmyJane/labview_assistant` and `JanGoebel/labview_assistant` are useful references, but their Python bridge imports `pywin32` and uses Windows COM (`LabVIEW.Application`), so they are not the default Linux route.

## Files

- `docs/LABVIEW_LINUX_SETUP.md` - installation notes and current machine status.
- `docs/POST_INSTALL_REPORT_2026-06-14.md` - completed install audit trail and maintenance notes.
- `docs/MCP_BRIDGE_TEST_REPORT_2026-06-14.md` - MCP bridge smoke-test results and live-server boundary.
- `docs/TOOLING_REFERENCE.md` - scripts, configs, external tools, and usage commands.
- `docs/MCP_CANDIDATES.md` - GitHub research and recommendation.
- `scripts/install_labview_linux.sh` - dependency and NI feed installer.
- `scripts/install_mcp_candidate.sh` - clone/update MCP candidates under `~/.local/share/labview-mcp-agent`.
- `scripts/configure_labview_local_server.sh` - write local VI Server preferences for LabVIEW Community.
- `scripts/start_labview_local_server.sh` - start a dedicated 24-bit local Xvfb display and LabVIEW Community.
- `scripts/labview_http_mcp_bridge.py` - stdio MCP frame bridge to a LabVIEW HTTP JSON-RPC endpoint.
- `scripts/test_mcp_bridge.py` - mock-endpoint smoke test for the MCP bridge.
- `scripts/camera_mcp_simulator.py` - camera MCP endpoint with simulator and V4L2 capture tools.
- `scripts/test_camera_mcp_simulator.py` - smoke test for camera MCP tools through the bridge.
- `scripts/probe_labview.sh` - local health check.
- `scripts/launch_labview.sh` - launch helper with optional Xvfb support.
- `mcp.example.json` - example MCP client configuration.

## Camera MCP Test Endpoint

This machine currently exposes a Logitech C922 as `/dev/video0`. Use the simulator endpoint for repeatable camera tests while the LabVIEW VI server is not running:

```bash
python agentic_tools/labview_mcp_agent/scripts/camera_mcp_simulator.py serve \
  --host 127.0.0.1 --port 36988 --device /dev/video0
```

Then point the bridge at `http://127.0.0.1:36988/mcp/server`. The tools are `camera.capture_simulator` and `camera.capture_v4l2`.

## Local Community Server

The default remote desktop is TigerVNC `:10` with a 32-bit root visual, which can trigger LabVIEW X11 `BadMatch` errors. Use the local 24-bit display launcher instead:

```bash
agentic_tools/labview_mcp_agent/scripts/start_labview_local_server.sh
```

It configures VI Server preferences, starts Xvfb on `:98`, launches LabVIEW Community, and reports the activation callback, VI Server, and MCP HTTP ports. LabVIEW Community still must be activated through the official NI account flow before `LabVIEWCLI` and the LabVIEW-hosted MCP VI can run.
