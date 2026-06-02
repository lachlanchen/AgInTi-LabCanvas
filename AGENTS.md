# Repository Guidelines

## Project Structure & Module Organization

AppAutoAction is a small Python CLI package. Production code lives in `src/agenticapp/`, with `cli.py` handling commands, `config.py` loading target registries, and `adapters.py` dispatching instructions. Tests live in `tests/`. Example target configuration lives in `configs/targets.example.json`; copy it to `agenticapp.targets.json` for local overrides.

## Build, Test, and Development Commands

- `PYTHONPATH=src python -m agenticapp list`: list configured Blender, BioRender, Unity, and Unreal targets.
- `app-auto-action list`: run the installed console command.
- `PYTHONPATH=src python -m agenticapp doctor`: validate target configuration without sending commands.
- `PYTHONPATH=src python -m agenticapp dispatch blender "Create a cube" --dry-run`: inspect the JSON envelope for a target.
- `PYTHONPATH=src python -m agenticapp mcp-config`: emit MCP client configuration.
- `PYTHONPATH=src python -m agenticapp scene-template experiment-setup`: print a reusable 3D experiment scene spec.
- `PYTHONPATH=src python -m agenticapp render-scene examples/paper-optics-setup.scene.json --dry-run`: validate a scene spec and output paths.
- `PYTHONPATH=src python -m agenticapp web --port 8787`: start the local chat-and-preview web app.
- `PYTHONPATH=src python -m unittest discover -s tests`: run the full test suite.
- `scripts/install_blender_portable.sh`: install a no-sudo Blender binary under `~/.local/share/appautoaction/blender`.
- `app-auto-action --config configs/blender-local-command.example.json dispatch blender "Draw a building"`: run the local Blender bridge.

## Coding Style & Naming Conventions

Use Python 3.10+ and the standard library unless a dependency clearly improves the project. Follow PEP 8 with 4-space indentation. Use `snake_case` for modules, functions, and variables; use `PascalCase` for dataclasses and exceptions. Keep CLI output stable because tests and downstream scripts may parse it.

## Testing Guidelines

Use `unittest` for now. Name test files `test_*.py` and keep tests focused on behavior: config validation, dispatch envelope shape, transport behavior, and CLI return codes. Add regression tests when changing adapter semantics or target config parsing.
For scene rendering, test JSON validation and dry-run plans without requiring Blender; use a manual render check when changing `src/agenticapp/blender/scene_renderer.py`.
For web changes, keep tests focused on API behavior and static startup; manually verify the browser layout with the local server.

## Commit & Pull Request Guidelines

Use concise imperative commit messages, such as `Add Unity target validation` or `Document BioRender MCP setup`. Pull requests should include a summary, testing performed, linked issues when applicable, and screenshots only for UI-facing changes.

## Security & Configuration Tips

Do not commit `agenticapp.targets.json`; it may contain local endpoints or tokens. Keep secrets in environment variables such as `BIORENDER_API_KEY`. Treat editor bridges as privileged automation surfaces: review dry-run payloads before enabling live dispatch.

## Agent-Specific Instructions

Before editing, inspect `git status` and preserve unrelated local changes. Prefer repository commands from this file over generic assumptions, and update `README.md` plus this guide whenever CLI behavior or target configuration changes.
