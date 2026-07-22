# BioRender Agent Bridge

LabCanvas combines BioRender's official MCP server with a dedicated observable
Chrome/noVNC profile. MCP handles authenticated template and icon search;
Chrome/CDP remains available for OAuth enrollment and editable canvas work.

## Private Enrollment

Never commit credentials, OAuth clients, tokens, screenshots, or exports. Local
state belongs under `agentic_tools/biorender_agent/.private/`, which is ignored
by git. Create the OAuth client file as mode `0600`:

```json
{
  "client_id": "private client id",
  "client_secret": "private client secret"
}
```

Save it as `.private/oauth-client.local.json`, start the dedicated browser, and
authorize once:

```bash
agentic_tools/biorender_agent/scripts/start_biorender_browser.sh
python agentic_tools/biorender_agent/scripts/biorender_oauth_login.py
```

The OAuth helper uses PKCE, validates callback state, and writes a mode-`0600`
token to `.private/oauth-token.local.json`. The localhost proxy injects and
refreshes that private token without logging it.

## Start And Verify

Start or reuse the browser and MCP proxy in tmux, then run a real MCP
`initialize` and `tools/list` probe:

```bash
agentic_tools/biorender_agent/scripts/start_biorender_stack.sh
python agentic_tools/biorender_agent/scripts/probe_biorender_mcp.py --json
```

Endpoints:

- MCP: `http://127.0.0.1:19682/mcp`
- CDP: `http://127.0.0.1:9389`
- noVNC: `http://127.0.0.1:6189/vnc.html?host=127.0.0.1&port=6189&autoconnect=1&resize=scale`
- tmux: `labcanvas-biorender-mcp`

Register the local MCP endpoint when needed:

```bash
codex mcp add biorender --url http://127.0.0.1:19682/mcp
```

BioRender's dynamic client-registration endpoint can be blocked by its edge
security. LabCanvas therefore bootstraps OAuth from the ignored client file and
uses the local proxy instead of depending on `codex mcp login`. Do not report
the bridge as ready from an HTTP health check alone: the protocol probe must
return authenticated tools, or the dedicated browser must show a logged-in
gallery/canvas.
