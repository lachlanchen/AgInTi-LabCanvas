# Paper Figure Studio

The web app turns AppAutoAction into a small studio for academic setup figures. It uses a bright theme by default, with a top-bar toggle for dark mode. The studio combines deterministic layout, 3D rendering, CAD export, and backend handoff without requiring API keys for the local demo.

## Artifact Canvas

The center panel is the artifact canvas. Every generated file is registered in `output/webapp/artifacts.json` and appears in the selectable rail. Image artifacts preview directly; text, JSON, and OpenSCAD artifacts open in a readable code view.

Current artifact sources:

- `paper-figure`: exact SVG grids with black panel boundaries.
- `aginti`: redacted image-generation prompt, request payload, and manifest.
- `openscad`: simplified `.scad` mechanical layout proxy.
- `blender`: rendered PNG and `.blend` scene files.
- `scene-spec`: JSON source-of-truth files.

## Figure Grids

Use the canvas controls or chat:

```text
Generate a 3x4 paper figure grid for cell assay icons
```

The grid generator writes an SVG with fixed integer panel boundaries. `rows`, `cols`, `cell_size`, and `border` come from backend settings unless overridden by the request.

## AgInTi Backend

AgInTi is configured in the Backends panel. Defaults:

```json
{
  "command": "aginti",
  "workspace": "../Agent/AgInTiFlow",
  "image_provider": "grsai",
  "image_model": "nano-banana-2",
  "dry_run": true
}
```

Dry run prepares the same payload shape as real image generation without calling the provider. Disable dry run only when the desired provider key is configured and the user intends to spend a live image call.

## BioRender Settings

BioRender is configured as a remote MCP handoff, not as scraping automation. The documented connector URL is:

```text
https://mcp.services.biorender.com/mcp
```

Store credentials in an environment variable such as `BIORENDER_API_KEY`; the web app stores only the variable name.

## Tool Support

| Tool | Studio support | Notes |
| --- | --- | --- |
| Blender | Active local render workflow | Produces PNG and `.blend` artifacts from the scene spec. |
| OpenSCAD | Active local export workflow | Produces a simplified `.scad` layout proxy. |
| AgInTi image generation | Active dry-run workflow by default | Writes redacted prompts, request payloads, and manifests; live image calls need provider keys. |
| BioRender | Configured MCP handoff | Uses the official remote MCP endpoint and browser handoff; credentials stay in env vars. |
| Unity/Unreal/other registry targets | Studio dry-run dispatch plus CLI/registry support | Add endpoints in `agenticapp.targets.json`; the Backends panel can dry-run any configured target and save the result to the canvas. |

## OpenSCAD And Blender

OpenSCAD export creates a simple CAD proxy from the scene spec for mechanical planning. Blender render creates the publication-style visual output. Use OpenSCAD to inspect layout constraints, then Render to produce the final PNG and `.blend`.
