# LabVIEW MCP Candidate Research

Date checked: 2026-06-14.

## Summary

| Candidate | Stars | Fit | Notes |
| --- | ---: | --- | --- |
| `nineman-YU/Labview_mcp` | 1 | Best Linux route | LabVIEW-hosted JSON-RPC/MCP toolkit. README lists LabVIEW 2022 Q3 and 26.1 paths. |
| `CalmyJane/labview_assistant` | 14 | Windows-first | Python MCP server plus LabVIEW VIs. Uses `pywin32` and Windows COM automation. |
| `JanGoebel/labview_assistant` | 8 | Windows-first upstream/reference | Same experimental LabVIEW assistant idea; description warns it is not feature complete. |

## Recommended Path

Use `nineman-YU/Labview_mcp` when LabVIEW is installed locally. It runs the server inside LabVIEW and exposes JSON-RPC over HTTP, avoiding Windows-only COM automation.

Install/update the candidate:

```bash
agentic_tools/labview_mcp_agent/scripts/install_mcp_candidate.sh nineman
```

Default clone location:

```text
~/.local/share/labview-mcp-agent/candidates/nineman-YU--Labview_mcp
```

## Candidate Details

### nineman-YU/Labview_mcp

- URL: <https://github.com/nineman-YU/Labview_mcp>
- README claims support for LabVIEW 2022 Q3 and 26.1.
- Protocol: JSON-RPC 2.0 over HTTP POST.
- Default port documented by the repo: `36987`.
- Methods documented: `tools/list`, `tools/call`, `prompts/list`, `prompts/get`, `resources/list`, `resources/read`.
- LabVIEW 2022 Q3 dependencies: VIPM packages `illuminatedg_lib_ig_http_utils` and `jdp_science_jsontext`.
- LabVIEW 26.1 route: native HTTP and native JSON APIs, no external VIPM dependency according to its README.

### CalmyJane/labview_assistant

- URL: <https://github.com/CalmyJane/labview_assistant>
- Python package requires `mcp[cli]` and `pywin32`.
- `main.py` dispatches `win32com.client.Dispatch("LabVIEW.Application")`.
- Good reference for scripting VIs and object insertion, but not a direct Ubuntu solution.

### JanGoebel/labview_assistant

- URL: <https://github.com/JanGoebel/labview_assistant>
- Description: experimental MCP server for Claude Desktop or other MCP clients to create code in LabVIEW.
- Treat as upstream/reference until Linux support is proven.

## Integration Pattern for LabCanvas

1. Install LabVIEW and activate it locally.
2. Clone `nineman-YU/Labview_mcp`.
3. Open its LabVIEW project.
4. Run `src/mcp_server_main.vi` or the version-specific main VI.
5. Configure LabCanvas/Codex to call the HTTP MCP endpoint through a small bridge or MCP proxy.

Use `mcp.example.json` in this folder as the MCP client starting point.
