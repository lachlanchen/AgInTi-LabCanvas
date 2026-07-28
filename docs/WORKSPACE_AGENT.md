# LabCanvas Workspace Agent

LabCanvas now exposes one persistent, tool-capable agent through both the web
studio and CLI. The web chat is a direct transport to the agent, not a keyword
router. Focused APIs such as scene rendering, figure grids, target dispatch,
and WeChat controls remain available as fast routines the agent can call.

## Capabilities

The packaged capability contract covers:

- parametric CAD and Shapr3D-compatible STEP handoff;
- KiCad PCB generation, ERC/DRC, Gerbers, STEP, and renders;
- Blender scenes, engineering renders, and `.blend` artifacts;
- TeX reports, papers, diagrams, and compiled PDFs;
- WeChat status, messages, files, queues, and worker routines;
- LabVIEW/MCP, camera, and isolated virtual-desktop workflows;
- AgInTi image generation, BioRender, Unity, Unreal, and target bridges.

The agent receives a compact packaged knowledge file at
`src/agenticapp/knowledge/workspace_agent.md` and links to measured repository
evidence such as the Shapr3D batch history, OpenHI thread/fit tables, Shapr STEP
repair lessons, and cage-print feedback. It still inspects the actual source
design before changing geometry.

## Web Chat

Start the studio:

```bash
PYTHONPATH=src python -m agenticapp webapp start --port 19483
```

The chat composer provides:

- **Model: Auto** for dynamic model selection;
- **GPT-5.6 SOL** for an explicit `gpt-5.6-sol` turn;
- **Effort: Auto**, Low, or Medium;
- **Execute** or **Plan only** mode;
- cancellation and live durable-task polling.

Each browser profile receives a stable conversation id. Codex resumes that
conversation's prior thread, so follow-up requests retain context without
mixing users or workspaces.

## Rooms

The `/rooms` surface provides durable room-scoped conversations using the same
workspace-agent runtime and artifact store:

```text
http://127.0.0.1:8787/rooms
```

Owner access is local-only unless `LABCANVAS_ROOMS_TOKEN` is configured.
Owner-created invite links are room-scoped, expire, and force participant turns
into plan mode. Each room has an independent conversation ID, SQLite message
ledger, durable task links, and artifact URLs constrained to the webapp storage
directory.

The allowlisted WeCom `LabAgent` transport uses the shared worker routines for
research, TeX/PDF, editable figure generation, CAD, PCB/KiCad, OpenSCAD, and
Blender work. It must return both review previews and editable/source artifacts
to the originating group. It does not authorize public video publication,
payment, manufacturing submission, or other irreversible external actions.

## CLI

```bash
labcanvas agent capabilities
labcanvas agent chat "Design and render a C-mount sensor holder"
labcanvas agent chat "Rebuild this exact Shapr3D part" --model gpt-5.6-sol --effort medium
labcanvas agent chat "Inspect the KiCad board" --mode plan
labcanvas agent chat "Run a long Blender task" --detach --json
labcanvas agent tasks
labcanvas agent status TASK_ID
labcanvas agent cancel TASK_ID
```

Use `--conversation NAME` to preserve a separate CLI thread. `--dry-run` prints
the selected model policy and full operating contract without launching an
agent.

## Model Policy

Auto routing classifies only the current request:

| Request | Default effort | Default model |
| --- | --- | --- |
| Short answer or status | low | `auto-code-review` |
| Analysis, documentation, or ordinary tool work | medium | `auto-code-review` |
| Complex implementation and broad engineering validation | high | `gpt-5.6-sol` |
| Demanding autonomous research, design, or presentation synthesis | xhigh | `gpt-5.6-sol` |

Explicit low, medium, high, and xhigh values are supported. `max` and Ultra
normalize to xhigh.
Environment variables `LABCANVAS_AGENT_FAST_MODEL` and
`LABCANVAS_AGENT_STANDARD_MODEL` can replace the low/medium auto tiers. High
and xhigh use their explicit shared-policy entries. Backend
quota/unavailable failures may fall back to AgInTi when the
saved setting permits it. New AgInTi versions use the noninteractive
`aginti run --stdin` contract. Older installed versions receive a short command
that points to the task's private durable prompt file. The default workspace `.`
keeps either form inside LabCanvas instead of depending on an AgInTiFlow source
checkout.

## Tasks and Artifacts

Durable state is written under the ignored directory:

```text
output/webapp/agent/tasks/<task-id>/
  task.json
  prompt.md
  agent-result.json
  response.md
  artifacts/
```

The worker runs outside the HTTP request, so browser refreshes do not cancel a
task. It registers declared PNG/PDF/STEP/STL/3MF/Blend/KiCad/TeX and other safe
artifact types in the normal LabCanvas canvas. Source designs remain in their
proper repository folders; the canvas receives review copies.

## Action Boundaries

Normal local design, editing, rendering, compilation, and validation can run in
Execute mode. The agent must stop for explicit current-user authorization before
payment, final manufacturing submission, public publication, credential changes,
destructive deletion, or another irreversible external action. Completion must
be supported by real command, file, render, or external-status evidence.
