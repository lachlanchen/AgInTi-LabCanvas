# KiCad MCP Research

Date: 2026-06-08

## Installed Local Baseline

- KiCad: `10.0.3`
- KiCad CLI: `kicad-cli` in `PATH`
- Python for `pcbnew`: `/usr/bin/python3` or a venv created with `--system-site-packages`
- Installed MCP server: `Seeed-Studio/kicad-mcp-server`
- Local path: `/home/lachlan/.local/share/appautoaction/mcp/kicad-mcp-server`
- Verified revision: `748de12`

MCP command shape:

```json
{
  "mcpServers": {
    "kicad": {
      "type": "stdio",
      "command": "/home/lachlan/.local/share/appautoaction/mcp/kicad-mcp-server/.venv/bin/python",
      "args": ["-m", "kicad_mcp_server"],
      "cwd": "/home/lachlan/.local/share/appautoaction/mcp/kicad-mcp-server"
    }
  }
}
```

Install pattern used:

```bash
git clone https://github.com/Seeed-Studio/kicad-mcp-server ~/.local/share/appautoaction/mcp/kicad-mcp-server
/usr/bin/python3 -m venv --system-site-packages ~/.local/share/appautoaction/mcp/kicad-mcp-server/.venv
~/.local/share/appautoaction/mcp/kicad-mcp-server/.venv/bin/python -m pip install -e ~/.local/share/appautoaction/mcp/kicad-mcp-server
```

## GitHub Options

- `Seeed-Studio/kicad-mcp-server`: KiCad 8+ / 9+ / 10 compatible analysis and validation server using `pcbnew` plus `kicad-cli`. Best fit for headless repo work and CI-friendly validation.
- `belaszalontai/kipilot-mcp`: KiCad 10 live-GUI IPC server. Best fit when KiCad PCB Editor is open and the user wants guarded live edits through the official IPC path.
- `mixelpixx/KiCAD-MCP-Server`: broad natural-language PCB workflow server with project setup, schematic editing, routing, DRC/ERC, export, and JLCPCB/Freerouting integrations.
- `lamaalrajih/kicad-mcp`: Python MCP server for KiCad project inspection, project management, DRC, BOM, and visualization workflows.

## Workflow Notes

For deterministic agent-generated boards, prefer file generation plus `kicad-cli pcb drc`, `export step`, `export gerbers`, `export drill`, and `render`. Use live MCP/IPC tools when a human wants to see edits in an open KiCad GUI session.

Sources:

- https://github.com/Seeed-Studio/kicad-mcp-server
- https://github.com/belaszalontai/kipilot-mcp
- https://github.com/mixelpixx/KiCAD-MCP-Server
- https://github.com/lamaalrajih/kicad-mcp
