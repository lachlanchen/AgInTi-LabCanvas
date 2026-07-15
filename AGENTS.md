# Repository Guidelines

## Project Structure & Module Organization

AgInTi LabCanvas is a small Python CLI and web package. Production code lives in `src/agenticapp/`: `cli.py` handles commands, `workspace_agent.py` runs persistent tool-capable chat sessions and durable tasks, `knowledge/workspace_agent.md` packages cross-tool engineering knowledge, `config.py` loads target registries, `adapters.py` dispatches instructions, `webapp.py` serves the local studio, and `artifacts.py` tracks generated files. Tests live in `tests/`. Static web assets live in `src/agenticapp/web/static/`.

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
- `PYTHONPATH=src python -m agenticapp agent capabilities`: inspect integrated CAD, KiCad, Blender, TeX, WeChat, LabVIEW, figure, and bridge readiness.
- `PYTHONPATH=src python -m agenticapp agent chat "Design and render a C-mount holder"`: run a persistent direct agent turn with dynamic model/effort selection.
- `PYTHONPATH=src python -m agenticapp agent chat "Rebuild the exact Shapr part" --model gpt-5.6-sol --effort ultra`: explicitly use GPT-5.6 SOL with `xhigh` reasoning.
- `PYTHONPATH=src python -m agenticapp agent tasks`: list durable agent work and artifact status.
- `PYTHONPATH=src python -m agenticapp social project add --repo ../ZhJpBook --id pocketpolyglot`: register repository evidence for social campaigns.
- `PYTHONPATH=src python -m agenticapp social campaign create --project pocketpolyglot --name introduction --objective "Introduce the usable open-source Studio" --platform x --platform reddit:r/languagelearning --platform hackernews`: create a platform-specific campaign brief.
- `PYTHONPATH=src python -m agenticapp social draft generate CAMPAIGN_ID --dry-run --json`: inspect the Codex Ultra drafting contract without quota use or external writes.
- `PYTHONPATH=src python -m agenticapp social maintain CAMPAIGN_ID --integration x=POSTIZ_X_ID --days 30 --dry-run`: inspect the source-grounded analytics and follow-up contract without provider reads or model quota.
- `PYTHONPATH=src python -m agenticapp studio figure-grid "optical icons 2x3" --rows 2 --cols 3`: run the same artifact action as the web canvas.
- `PYTHONPATH=src python -m agenticapp studio dispatch blender "Prepare an editable paper figure setup"`: dry-run a configured target and register the envelope as an artifact.
- `PYTHONPATH=src python -m agenticapp wechat worker --chat "懒人科研" enqueue "Use LabCanvas to render a PCB and CAD preview"`: enqueue slower WeChat backend work that can call CAD, PCB, Blender, and LabCanvas tools.
- `PYTHONPATH=src python -m agenticapp wechat init-config --agent-backend claude --force`: write ignored WeChat config templates that opt into Claude Code; Codex remains the default backend.
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
For workspace-agent changes, mock the backend in unit tests. Test model selection, prompt contracts, task transitions, session isolation, cancellation, and artifact registration without spending live model quota; then run one small live smoke task when backend invocation changes.

## Workspace Agent Rules

The web and CLI must use the same `workspace_agent.py` runtime. Keep the web chat a direct transport to a persistent agent session; do not replace it with keyword-specific response branches. Domain-specific code remains useful as callable routines. Auto routing uses GPT-5.6 SOL for normal turns and maps the UI's Ultra setting to Codex `xhigh`. Preserve durable task records under ignored `output/`, return real artifacts to the canvas, and require explicit authorization for payment, manufacturing submission, public publication, credential changes, destructive deletion, or another irreversible external action.

## Figure Pipeline Rules

Paper figure generation must stay editable and atomic. Do not treat a generated bitmap as the final source of truth. Use image generation for overview concepts, then split figures into named parts with their own prompts, source files, tool settings, previews, and edit history. Prefer BioRender for academic assets, OpenSCAD for device geometry, Blender for rendered setups, LabVIEW for instrument/control workflows, and TeX for clipping and final assembly. Preserve part IDs and rebuild exports from manifests.

## Social Content Rules

Use `labcanvas social` for open-source project campaigns. Keep one persistent Codex session per project and store local campaign state under ignored `output/social/`. Ground drafts in registered repository evidence and adapt them independently for each platform; do not copy one advertisement everywhere or invent users, benchmarks, endorsements, or traction. Reddit requires a fresh review of the exact community rules. Hacker News is manual-only because its guidelines reject generated or AI-edited submission text: the agent may prepare verified facts and a human-author worksheet, but not final HN copy. Every external provider write requires both `--live` and a non-expired approval token bound to the exact title, body, target, media, settings, and publication metadata hash. Keep OAuth tokens in the provider-managed user store (Postiz uses `~/.postiz/credentials.json`) and API keys in `agentic_tools/social_content_agent/.private/` or environment variables; never put credentials in campaign exports or git.

## CAD Artifact Sync

For CAD designs, "Nutstore sync" means `/home/lachlan/Nutstore Files/Projects/LabCanvas`. After generating or revising a serious CAD design, copy the final `*_assembly.step` or `*_assembled.step` file to that folder by default, keeping the filename descriptive. Continue preserving the full source/artifact set in the design folder; the Nutstore copy is for Shapr3D/LabCanvas handoff.
Keep each CAD project in one design folder. For major regeneration runs, archive the previous root files under `runs/run-N-human-readable-info-YYYYMMDDTHHMMSSZ/` and keep the root `artifacts/` as the latest checked output. Do not create a sibling design folder for a small geometry fix unless the user explicitly asks for a separate variant.
When a CAD run is ready for 3D printing, create a timestamped run folder under the design, named like `runs/run-N-short-name-print-ready-YYYYMMDDTHHMMSSZ/`; do not leave print-ready files only in the root `artifacts/` folder. Also create a clean Nutstore subfolder named like `<design>/run-N-short-name-print-ready-YYYYMMDDTHHMMSSZ/`. Include `PRINT_THIS_*.stl`, `PRINT_THIS_*.step`, `PRINT_THIS_*.3mf`, separate part STEP files such as `bottom_part.step` and `top_part_180deg_print.step` when relevant, a manifest, README, and render PNGs for both the final single assembly and the exact direct-print layout. For large flat parts, default to removable anti-warp ears with side pulls plus diagonal full-corner pull tabs. After the 2026-07 dock print feedback, make these ears stronger/larger by default: use roughly 0.8-1.0 mm sacrificial thickness and larger tail pads unless the user explicitly prioritizes very easy removal.

## WeChat Worker Tool Routing

Research chat messages that mention LabCanvas, AgInTi image generation, KiCad, Gerber, STEP/STL, CAD, PCB, Blender, figures, icons, or renders should be routed to the worker queue. The fast monitor should only ACK and enqueue. The worker may run `studio figure-grid`, `studio lab-task`, `render-scene`, AgInTi image generation, KiCad, OpenSCAD, and Blender commands, then return generated PNG/PDF/SVG/MP4/MOV/audio/STEP/STL/ZIP/KiCad artifacts in the `files` array so the GUI sender can deliver them to WeChat.
ZIP, Word, PDF, and text attachments must pass through `wechat_document_reader.py` after exact same-chat source resolution. Parse DOCX as XML, extract PDFs with bounded `pdftotext` plus OCR fallback, and unpack ZIP files only with traversal, symlink, encryption, member-count, byte, depth, executable, and compression-ratio guards. Pass `agent_context_path` to the resumed worker so it answers from the content; do not stop at a checksum receipt when readable evidence exists.
For incoming images, use exact same-chat media resolution and Codex vision to answer naturally with what the image shows or means. Keep OCR, model names, dimensions, checksums, and fixed vision labels as private evidence; expose them only when the user explicitly asks for transcription or diagnostics.
For Gongzhonghao/mp.weixin and Shipinhao/Finder research, run the read-only `wechat_source_recovery.py` preflight. It uses the mobile WeChat user agent and private cache for `#js_content`, auto-discovers exact Shipinhao comment exports or a local `wx_channel` API, and emits exact-title/account/object-ID reconstruction queries. For Shipinhao video understanding, run `shipinhao_media_transcribe.py`; if the exact card URL expired, open the exact native card and use `shipinhao_gui_audio_capture.py` with title/author identity terms so feed auto-advance is trimmed and a private object-ID/hash manifest is produced. Never reload after binding the audio stream or reuse another card's capture. Do not open/focus an external browser or ask the user to verify a read-only source. If recovery remains incomplete, give an evidence-limited answer without pretending the full article/video was read. Posting comments or asking Yuanbao remains a separate explicit write action.
LALACHAN/Xiaoyunque story and video generation should follow `references/lalachan-story-video-handoff-for-wechat.md`: write the story and prompt first, upload actual reference image files in the documented order, monitor the browser generation to a verified MP4, send that MP4 back to the originating chat, and only copy to Nutstore or enter LazyEdit/public publishing when the current request asks for those stages.
Video publishing requests should use `agentic_tools/wechat_gui_agent/skills/lazyedit-publish-workflow/SKILL.md`: resolve exact same-chat video media with `labcanvas wechat autopublish-video`, process/publish through LazyEdit's `scripts/lazyedit_publish.py`, monitor local and remote queues, and stop for human QR/CAPTCHA/login steps. Preserve the worker's video publish/subtitle context bundle as `--correction-prompt-file`, create a separate concise `--metadata-prompt-file`, and only return safe source-scoped media artifacts.
The tmux supervisor must launch `wechat_worker_guarded_loop.sh`, not the raw worker, so the publish-poststage self-test runs before the worker loop starts.
Treat WeChat as message transport only: nontrivial messages should become queued tasks with `task.routine` and `execution_contract`, then `wechat_task_worker.run_task_orchestrator` resumes the exact chat's selected backend session through `wechat_agent_backend.run_agent_session`. Codex remains default; Claude Code is opt-in through `agent_backend`. Codex quota, backend-unavailable, and agent-turn timeout failures should degrade through the centralized fallback policy, including AgInTi when `agent_fallbacks.fallback_to_aginti=true`, rather than leaving a group silent.
When changing WeChat automation behavior, also update `agentic_tools/wechat_gui_agent/docs/ROBUST_EFFICIENT_OPERATIONS.md`. Treat it as the reliability contract for per-chat isolation, token-efficient routing, queue states, artifact delivery gates, and recovery playbooks.

## Commit & Pull Request Guidelines

Use concise imperative commit messages, such as `Add Unity target validation` or `Document BioRender MCP setup`. Pull requests should include a summary, testing performed, linked issues when applicable, and screenshots only for UI-facing changes.

## Security & Configuration Tips

Do not commit `labcanvas.targets.json`, `.aginti/.env`, or generated `output/` files; they may contain local endpoints, tokens, or bulky artifacts. Keep secrets in environment variables such as `BIORENDER_API_KEY`. Treat editor bridges as privileged automation surfaces: review dry-run payloads before enabling live dispatch.

## Agent-Specific Instructions

Before editing, inspect `git status` and preserve unrelated local changes. Prefer repository commands from this file over generic assumptions, and update `README.md` plus this guide whenever CLI behavior or target configuration changes.
