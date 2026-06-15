# Local LabVIEW Community Server Report - 2026-06-15

## Result

LabVIEW Community can run locally on a dedicated 24-bit Xvfb display. The previous blocker was the active TigerVNC desktop on `:10`, whose root window uses 32-bit depth and produced LabVIEW X11 `BadMatch` errors.

Working local display:

```bash
Xvfb :98 -screen 0 1920x1080x24 -ac
DISPLAY=:98 /usr/local/natinst/LabVIEW-2026-64/labview
```

The repository now has a repeatable launcher:

```bash
agentic_tools/labview_mcp_agent/scripts/start_labview_local_server.sh
```

## Observed Runtime State

- LabVIEW Community starts successfully on `:98`.
- The LabVIEW activation dialog appears on `:98`.
- LabVIEW opens the official local activation callback listener at `127.0.0.1:23520` after the activation button is clicked.
- `0.0.0.0:3363` is listening from LabVIEW after the local launcher writes VI Server preferences and starts LabVIEW on `:98`.
- `127.0.0.1:36987` is not listening yet, because the LabVIEW-hosted MCP VI has not been started.

The activation flow reached NI login, but NI returned a `500 Internal Server Error` after login. The page also stated that the NI user account profile must be completed on `ni.com` before activation can finish. After that failed browser flow, the callback listener closed until activation is started again from the LabVIEW dialog.

`LabVIEWCLI` can now launch against the local display without the old VI Server connection error. A non-destructive `AddTwoNumbers` CLI sample still timed out, which matches the visible Community activation dialog blocking useful execution until activation is complete.

## Local Configuration

VI Server preferences are written to:

```text
/home/lachlan/natinst/.config/LabVIEW-2026/labview.conf
```

The config includes localhost-only VI Server TCP settings for port `3363`. The listener is live on this machine, but LabVIEW Community must still complete official activation before CLI operations and the LabVIEW-hosted MCP VI can run normally.

## Next Steps

1. Complete the NI web account profile in a normal browser session.
2. Re-run:

```bash
agentic_tools/labview_mcp_agent/scripts/start_labview_local_server.sh
```

3. In the activation browser flow, log in to NI and allow the callback to `http://127.0.0.1:23520/`.
4. Confirm `127.0.0.1:3363` is listening.
5. Run the candidate VI:

```text
/home/lachlan/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp/src/mcp_server_main.vi
```

6. Confirm the LabVIEW MCP HTTP endpoint:

```text
http://127.0.0.1:36987/mcp/server
```
