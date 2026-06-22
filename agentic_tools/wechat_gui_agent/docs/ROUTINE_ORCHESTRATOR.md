# WeChat Routine Orchestrator

This is the fixed execution layer for WeChat-triggered LabCanvas work. The
agent should supervise these routines and resolve blockers; it should not
invent a new workflow when a routine already covers the request.

## Flow

```text
direct DB monitor
  -> route decision
  -> routine contract
  -> JSONL task queue
  -> worker writes routine_contract.json/.md
  -> deterministic stages and Codex worker supervision
  -> artifact delivery gate
```

## Routine Registry

The registry lives in:

```text
agentic_tools/wechat_gui_agent/scripts/wechat_routines.py
```

Inspect it with:

```bash
PYTHONPATH=src python -m agenticapp wechat routines
PYTHONPATH=src python -m agenticapp wechat routines --json
```

Current routines:

- `research_summary`: papers, PDFs, links, summaries, and source-grounded
  answers.
- `editable_figure_image`: AgInTi/image/BioRender-style figure work with
  editable parts, manifests, SVG/TeX, and previews.
- `labcanvas_cad_pcb`: CAD, PCB, OpenSCAD, KiCad, Blender, renders, Gerbers,
  STEP/STL, and device design.
- `file_download_save`: exact-source file, media, link, and download handling.
- `video_publish_existing`: source-scoped existing video processing and
  LazyEdit/public publishing only when explicitly requested.
- `generated_video`: LALACHAN/Xiaoyunque generation, long monitoring, MP4
  send-back, optional LazyEdit, and optional public publish.
- `general_worker`: safe fallback for other backend work.

## Contract Rules

Every worker task should contain `task.routine`. When claimed, the worker writes
`routine_contract.json` and `routine_contract.md` into the task artifact
directory. The worker prompt includes the routine contract before the tool
playbook.

Required behavior:

- select routines from the current `route_decision` and current request;
- treat route and routine contracts as source-of-truth intent boundaries;
- preserve per-chat source isolation;
- keep long waits in queue state, not one long model call;
- send or defer required artifacts through the artifact delivery gate;
- require current-message permission for public publish, purchases, deletion,
  payment, and other irreversible actions.

## Adding A Routine

1. Add a `RoutineDefinition` in `wechat_routines.py`.
2. Map route kinds or fallback keywords to the routine.
3. Add a focused test in `tests/test_wechat_routines.py`.
4. If it changes worker behavior, add a queue or prompt test.
5. Update this document and `ROBUST_EFFICIENT_OPERATIONS.md`.
