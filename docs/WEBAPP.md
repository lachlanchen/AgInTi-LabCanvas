# Web App

AppAutoAction includes a local chat-and-preview workspace for 3D experiment design.

```bash
app-auto-action web --port 8787 --open
```

The app runs on `127.0.0.1` by default. If the requested port is busy, it chooses the next available port.

## Workflow

1. Chat to adjust the scene spec.
2. Review the JSON scene state.
3. Use Dry Run to validate output paths.
4. Use Render to launch Blender headless.
5. Preview the PNG and open the generated `.blend` or JSON spec.

The web app uses the same scene spec renderer documented in [SCENE_SPEC.md](SCENE_SPEC.md). It does not require API keys; chat edits are deterministic scene-spec mutations.

## API

| Route | Purpose |
|---|---|
| `GET /` | Static web app. |
| `GET /api/spec` | Load the default scene spec and preview image. |
| `POST /api/chat` | Apply a chat instruction to the current scene spec. |
| `POST /api/plan` | Validate and return a dry-run render plan. |
| `POST /api/render` | Render the current scene spec with Blender. |
| `GET /artifacts/...` | Serve generated PNG, `.blend`, and JSON artifacts. |

Generated files are written under `output/webapp/`.
