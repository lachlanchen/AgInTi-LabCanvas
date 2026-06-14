# Live Setup Log - 2026-06-14

## Host Check

Command:

```bash
agentic_tools/labview_mcp_agent/scripts/probe_labview.sh
```

Result:

- Ubuntu 24.04.4 LTS, x86_64.
- No NI/LabVIEW dpkg packages found.
- `labview` is not in `PATH`.
- `xvfb`, `libopenal1`, and `libncurses6` are installed.

## Installer Check

Command:

```bash
agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh --dry-run
```

Result:

- The script found no LabVIEW `.zip` or `.deb` installer in `/home/lachlan/Downloads`.
- This is the current blocker for completing the LabVIEW IDE installation.
- Once the NI Linux installer is downloaded, rerun the same script without `--dry-run`.

## MCP Candidate Install

Command:

```bash
agentic_tools/labview_mcp_agent/scripts/install_mcp_candidate.sh nineman
```

Result:

- Cloned `https://github.com/nineman-YU/Labview_mcp.git`.
- Local path:

```text
/home/lachlan/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp
```

## Next Manual Boundary

1. Download LabVIEW Linux installer from NI while logged in.
2. Run `install_labview_linux.sh`.
3. Activate LabVIEW.
4. Open the cloned `Labview_mcp` project and run its server VI.
5. Use `mcp.example.json` or `labview_http_mcp_bridge.py` to connect a normal MCP client.
