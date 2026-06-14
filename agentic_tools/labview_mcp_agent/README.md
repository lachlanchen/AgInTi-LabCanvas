# LabVIEW MCP Agent

This folder documents and scripts the LabVIEW path for AgInTi LabCanvas. It covers three layers:

1. Install/check LabVIEW on this Ubuntu workstation.
2. Clone and prepare a LabVIEW MCP candidate.
3. Expose the resulting LabVIEW automation path to Codex/AgInTi through MCP configuration.

LabVIEW itself is proprietary NI software. The scripts can install dependencies and consume a downloaded NI Linux installer package, but they cannot bypass NI login, license, or entitlement checks.

## Status on This Machine

- OS: Ubuntu 24.04.4 LTS, x86_64.
- Already present: `xvfb`, `libopenal1`, `libncurses6`.
- Not installed yet: LabVIEW / NI feed packages.
- No LabVIEW installer was found in `/home/lachlan/Downloads` during setup.

## Quick Commands

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh --dry-run
agentic_tools/labview_mcp_agent/scripts/install_mcp_candidate.sh nineman
agentic_tools/labview_mcp_agent/scripts/launch_labview.sh
```

After downloading a Linux LabVIEW installer from NI, place the `.zip` or `.deb` in `~/Downloads` and run:

```bash
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh
```

## Recommended MCP Candidate

Use `nineman-YU/Labview_mcp` first for Linux. It hosts an MCP server from LabVIEW via JSON-RPC over HTTP and documents LabVIEW 2022 Q3 and 26.1 paths.

`CalmyJane/labview_assistant` and `JanGoebel/labview_assistant` are useful references, but their Python bridge imports `pywin32` and uses Windows COM (`LabVIEW.Application`), so they are not the default Linux route.

## Files

- `docs/LABVIEW_LINUX_SETUP.md` - installation notes and current blocker.
- `docs/MCP_CANDIDATES.md` - GitHub research and recommendation.
- `scripts/install_labview_linux.sh` - dependency and NI feed installer.
- `scripts/install_mcp_candidate.sh` - clone/update MCP candidates under `~/.local/share/labview-mcp-agent`.
- `scripts/labview_http_mcp_bridge.py` - stdio MCP frame bridge to a LabVIEW HTTP JSON-RPC endpoint.
- `scripts/probe_labview.sh` - local health check.
- `scripts/launch_labview.sh` - launch helper with optional Xvfb support.
- `mcp.example.json` - example MCP client configuration.
