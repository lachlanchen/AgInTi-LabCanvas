# Repository Guidelines

## Project Structure & Module Organization

AgInTi LabCanvas is a small Python CLI and web package. Production code lives in `src/agenticapp/`: `cli.py` handles commands, `config.py` loads target registries, `adapters.py` dispatches instructions, `webapp.py` serves the local studio, `artifacts.py` tracks generated files, `paper_figures.py` builds SVG grids, `openscad_export.py` writes CAD proxies, and `backends.py` stores AgInTi/BioRender settings. Tests live in `tests/`. Static web assets live in `src/agenticapp/web/static/`.

## Build, Test, and Development Commands

- `PYTHONPATH=src python -m agenticapp list`: list configured Blender, BioRender, Unity, and Unreal targets.
- `labcanvas list`: run the installed console command.
- `PYTHONPATH=src python -m agenticapp doctor`: validate target configuration without sending commands.
- `PYTHONPATH=src python -m agenticapp dispatch blender "Create a cube" --dry-run`: inspect the JSON envelope for a target.
- `PYTHONPATH=src python -m agenticapp mcp-config`: emit MCP client configuration.
- `PYTHONPATH=src python -m agenticapp scene-template experiment-setup`: print a reusable 3D experiment scene spec.
- `PYTHONPATH=src python -m agenticapp render-scene examples/paper-optics-setup.scene.json --dry-run`: validate a scene spec and output paths.
- `PYTHONPATH=src python -m agenticapp web --port 8787`: start the local chat, canvas, and preview web app.
- `PYTHONPATH=src python -m agenticapp webapp start --port 19473`: start the studio in tmux.
- `PYTHONPATH=src python -m agenticapp studio figure-grid "optical icons 2x3" --rows 2 --cols 3`: run the same artifact action as the web canvas.
- `PYTHONPATH=src python -m agenticapp studio dispatch blender "Prepare an editable paper figure setup"`: dry-run a configured target and register the envelope as an artifact.
- `PYTHONPATH=src python -m agenticapp wechat worker --chat "懒人科研" enqueue "Use LabCanvas to render a PCB and CAD preview"`: enqueue slower WeChat backend work that can call CAD, PCB, Blender, and LabCanvas tools.
- `PYTHONPATH=src python -m agenticapp wechat selftest --suite all --json`: prove WeChat transport, routine contracts, Codex resume, and publish poststage repair work together.
- `PYTHONPATH=src python -m agenticapp wechat selftest --suite publish-poststage --json`: prove the WeChat worker can repair missing LazyEdit publish jobs, avoid duplicates, and pause on login blockers.
- `PYTHONPATH=src python -m unittest discover -s tests`: run the full test suite.
- `scripts/install_blender_portable.sh`: install a no-sudo Blender binary under `~/.local/share/labcanvas/blender`.
- `labcanvas --config configs/blender-local-command.example.json dispatch blender "Draw a building"`: run the local Blender bridge.
- `agentic_tools/labview_mcp_agent/scripts/probe_labview.sh`: check local LabVIEW/NI package state.
- `agentic_tools/labview_mcp_agent/scripts/install_mcp_candidate.sh nineman`: clone/update the recommended LabVIEW-hosted MCP toolkit outside git.
- `agentic_tools/labview_mcp_agent/scripts/install_labview_linux.sh --dry-run`: verify NI installer availability before attempting a proprietary LabVIEW install.

## Coding Style & Naming Conventions

Use Python 3.10+ and the standard library unless a dependency clearly improves the project. Follow PEP 8 with 4-space indentation. Use `snake_case` for modules, functions, and variables; use `PascalCase` for dataclasses and exceptions. Keep CLI output stable because tests and downstream scripts may parse it.

## Testing Guidelines

Use `unittest` for now. Name test files `test_*.py` and keep tests focused on behavior: config validation, dispatch envelope shape, transport behavior, and CLI return codes. Add regression tests when changing adapter semantics or target config parsing.
For scene rendering, test JSON validation and dry-run plans without requiring Blender; use a manual render check when changing `src/agenticapp/blender/scene_renderer.py`.
For web changes, keep tests focused on API behavior, artifact registration, and static startup; manually verify the browser layout with the local server.

## Figure Pipeline Rules

Paper figure generation must stay editable and atomic. Do not treat a generated bitmap as the final source of truth. Use image generation for overview concepts, then split figures into named parts with their own prompts, source files, tool settings, previews, and edit history. Prefer BioRender for academic assets, OpenSCAD for device geometry, Blender for rendered setups, LabVIEW for instrument/control workflows, and TeX for clipping and final assembly. Preserve part IDs and rebuild exports from manifests.

## WeChat Worker Tool Routing

Research chat messages that mention LabCanvas, AgInTi image generation, KiCad, Gerber, STEP/STL, CAD, PCB, Blender, figures, icons, or renders should be routed to the worker queue. The fast monitor should only ACK and enqueue. The worker may run `studio figure-grid`, `studio lab-task`, `render-scene`, AgInTi image generation, KiCad, OpenSCAD, and Blender commands, then return generated PNG/PDF/SVG/MP4/MOV/audio/STEP/STL/ZIP/KiCad artifacts in the `files` array so the GUI sender can deliver them to WeChat.
Video publishing requests should use `agentic_tools/wechat_gui_agent/skills/lazyedit-publish-workflow/SKILL.md`: resolve exact same-chat video media with `labcanvas wechat autopublish-video`, process/publish through LazyEdit's `scripts/lazyedit_publish.py`, monitor local and remote queues, and stop for human QR/CAPTCHA/login steps. Preserve the worker's video publish/subtitle context bundle as `--correction-prompt-file`, create a separate concise `--metadata-prompt-file`, and only return safe source-scoped media artifacts.
The tmux supervisor must launch `wechat_worker_guarded_loop.sh`, not the raw worker, so the publish-poststage self-test runs before the worker loop starts.
Treat WeChat as message transport only: nontrivial messages should become queued tasks with `task.routine` and `execution_contract`, then `wechat_task_worker.run_task_orchestrator` resumes the exact chat's Codex worker session through `wechat_codex_sessions.run_codex_session`.
When changing WeChat automation behavior, also update `agentic_tools/wechat_gui_agent/docs/ROBUST_EFFICIENT_OPERATIONS.md`. Treat it as the reliability contract for per-chat isolation, token-efficient routing, queue states, artifact delivery gates, and recovery playbooks.

## Commit & Pull Request Guidelines

Use concise imperative commit messages, such as `Add Unity target validation` or `Document BioRender MCP setup`. Pull requests should include a summary, testing performed, linked issues when applicable, and screenshots only for UI-facing changes.

## Security & Configuration Tips

Do not commit `labcanvas.targets.json`, `.aginti/.env`, or generated `output/` files; they may contain local endpoints, tokens, or bulky artifacts. Keep secrets in environment variables such as `BIORENDER_API_KEY`. Treat editor bridges as privileged automation surfaces: review dry-run payloads before enabling live dispatch.

## Agent-Specific Instructions

Before editing, inspect `git status` and preserve unrelated local changes. Prefer repository commands from this file over generic assumptions, and update `README.md` plus this guide whenever CLI behavior or target configuration changes.
