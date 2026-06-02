# AgenticApp

AgenticApp is a lightweight control hub for routing agent instructions to creative and scientific design tools. It is designed to sit between an agent such as Codex, AgInTiFlow, Claude, or another MCP client and tool-specific bridges for Blender, BioRender, Unity, and Unreal Engine.

The app does not replace the editor plugins. It keeps a target registry, validates bridge configuration, sends JSON instruction envelopes to local adapters, and emits MCP client configuration.

## Current Targets

- Blender: local HTTP bridge or Blender MCP add-on.
- Unity: local HTTP bridge or Unity MCP package.
- Unreal: local HTTP bridge, Unreal MCP plugin, or Python remote execution proxy.
- BioRender: official remote MCP endpoint with browser-launch fallback.

## Quick Start

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp mcp-config
```

To customize endpoints, copy `configs/targets.example.json` to `agenticapp.targets.json` and edit the `transport` and `mcp` blocks.

## Dispatch Envelope

HTTP and command transports receive the same JSON shape:

```json
{
  "target": "blender",
  "kind": "blender",
  "instruction": "Create a red cube at the origin",
  "payload": {},
  "metadata": {
    "source": "agenticapp"
  }
}
```

## Bridge Notes

Use `http_json` when a local editor bridge accepts `POST` requests. Use `local_command` when a bridge is a script or CLI that reads JSON from standard input. Use `browser` only for tools that need a manual or hosted UI handoff.

BioRender automation should go through its MCP connector or documented APIs. Avoid browser scraping unless you have explicit permission and a stable workflow.
