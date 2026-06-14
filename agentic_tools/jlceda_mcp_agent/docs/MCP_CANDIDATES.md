# JLCEDA / EasyEDA MCP Candidates

## Recommended First: hyl64/jlcmcp

- URL: <https://github.com/hyl64/jlcmcp>
- Description: JLCEDA MCP server with direct PCB/schematic tools.
- Language/license: TypeScript, MIT.
- Local install path used here: `~/.local/share/appautoaction/mcp/jlcmcp`
- Build result: MCP server compiled to `dist/index.js`; bridge extension built
  to `jlc-bridge/build/jlc-bridge.eext` and `.lcex`.
- Smoke result on 2026-06-14: `tools/list` returned server `jlceda`
  version `0.1.0` with 38 tools. The upstream README currently describes 39
  tools, so trust the local smoke test for the installed checkout.

Architecture:

```text
AI IDE -> MCP stdio server -> WebSocket gateway -> jlc-bridge extension -> LCEDA Pro
```

Useful tools include PCB state, screenshot, DRC, component move/batch move,
track/via routing, copper pours, keepouts, silkscreen layout, differential
pairs, equal-length groups, schematic state/netlist/DRC, impedance calculation,
and trace-width calculation.

Current caveat: the repository provides the MCP server and LCEDA extension, but
real editing still depends on a gateway endpoint at
`ws://127.0.0.1:18800/ws/bridge` and the `jlc-bridge` extension running inside
LCEDA.

## Alternative: sengbin/JLCEDA-MCP

- URL: <https://github.com/sengbin/JLCEDA-MCP>
- Description: local JLCEDA MCP debugging workflow.
- Language/license: TypeScript, Apache-2.0.
- Shape: two extensions, one inside JLCEDA and one inside VS Code/Cursor.

This is a good option when the desired workflow is VS Code/Cursor centered and
the main needs are schematic read/review, component select, and placement.

## Reference/Early Work: Spectoda/easyeda-mcp

- URL: <https://github.com/Spectoda/easyeda-mcp>
- Description: MCP bridge concept for EasyEDA Pro, sourcing, manufacturing
  export, and JLCPCB order workflows.
- Language/license: TypeScript, Apache-2.0.

This is useful for architecture ideas, but it is much less complete than
`hyl64/jlcmcp` for direct LCEDA board manipulation.

## Practical Agent Path

1. Launch activated LCEDA Pro with CDP on port `51370`.
2. Build `hyl64/jlcmcp` with `install_jlcmcp.sh`.
3. Install `jlc-bridge/build/jlc-bridge.eext` in LCEDA Pro's extension manager.
4. Start or configure the gateway on port `18800`.
5. Add the `dist/index.js` MCP entry to Codex/Claude/Cursor.
6. Smoke test `tools/list`, then call `pcb_ping` before making PCB edits.
