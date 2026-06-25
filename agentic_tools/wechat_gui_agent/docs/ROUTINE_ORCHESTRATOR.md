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
- `story_script_generation`: story, script, plot, dialogue, and prompt writing
  or revision. This route is shared by 懒人科研 and 🍓我的设备, and it must draft
  the requested text before any explicitly requested image/video stage.
- `labcanvas_cad_pcb`: CAD, PCB, OpenSCAD, KiCad, Blender, renders, Gerbers,
  STEP/STL, and device design.
- `file_intake`: bare WeChat file upload with no explicit instruction. It
  syncs/saves the exact file, copies it into the task artifact directory,
  records metadata/checksum, and sends a short receipt without deep reading.
- `file_download_save`: exact-source file, media, link, and download handling.
- `video_publish_existing`: source-scoped existing video processing and
  LazyEdit/public publishing only when explicitly requested; `public_publish_verified`
  is a required gate before any response may say “published”.
- `generated_video`: LALACHAN/Xiaoyunque generation, long monitoring, MP4
  send-back, optional LazyEdit, and optional public publish. The full
  operator handoff is `references/lalachan-story-video-handoff-for-wechat.md`;
  LazyEdit internals stay in `references/lazyedit-agent-integration-handoff.md`.
- `general_worker`: safe fallback for other backend work.

Routing scope:

- All monitored chats use the same backend routine skill surface for explicit
  tool or artifact requests: EchoMind, 懒人科研, 鏈接, 写作 外语 挣钱, 🍓我的设备,
  and `lachlanchan` can route CAD/PCB, LabCanvas, figure/image, file/media,
  story/script, video, publish, writing, LaTeX, PDF, and research tasks to these
  routines when the current message asks for them.
- EchoMind is intentionally language-learning by default. Ordinary
  Japanese/Chinese/English practice stays in the language reply path; explicit
  backend instructions use the shared route/worker agents.

## Contract Rules

Every worker task should contain `task.routine`. When claimed, the worker writes
`routine_contract.json`, `routine_contract.md`, and
`agent_routine_cheat_sheet.md` into the task artifact directory. The worker
prompt includes the compact routine contract and autonomy contract before the
tool playbook, so the resumed agent receives the same execution rules as data.

`wechat_task_worker.py` uses `run_task_orchestrator()` as the central execution
boundary. The orchestrator always writes the routine contract, records
`task.orchestrator`, runs cheap deterministic routine stages first, and resumes
the same per-chat Codex worker session for reasoning, repair, browser work, or
tool-heavy execution. Deterministic code should not grow into a second agent; it
should provide mature stage probes and gates that the resumed worker can trust.

Required behavior:

- select routines from the current `route_decision` and current request;
- treat route and routine contracts as source-of-truth intent boundaries;
- treat the human operator as approval-only for real blockers; normal safe
  work must continue through queue state, deterministic stages, and the resumed
  per-chat worker session;
- route all nontrivial execution through the resumed worker session with
  `role=worker`, `reuse=True`, and the orchestrator handoff in the prompt;
- preserve per-chat source isolation;
- keep long waits in queue state, not one long model call;
- send or defer required artifacts through the artifact delivery gate;
- keep LazyEdit/public publish work in `publish_poststage_pending` until
  requested platforms have terminal LazyEdit/remote evidence;
- treat LazyEdit as the mature video-processing/publishing boundary. Workers
  prepare exact source video evidence plus `lazyedit_correction_context.md` and
  `lazyedit_metadata_brief.md`, then call LazyEdit CLI/API and monitor queues
  instead of rebuilding subtitle correction, metadata, packaging, or platform
  browser automation;
- for LALACHAN/Xiaoyunque generated videos, follow
  `references/lalachan-story-video-handoff-for-wechat.md` for story/prompt
  files, image order, model/duration/ratio checks, download verification,
  repo/Nutstore copies, and current-message publish permission gates;
- treat bare file uploads as cheap `file_intake` unless the current message
  explicitly asks to summarize, read, translate, convert, publish, or otherwise
  process the content;
- when an existing-video publish poststage has a LazyEdit `video_id` but no
  local publish job, reissue the real LazyEdit publish command from the stored
  prompt files once before handing repair to a Codex worker session;
- accept `burn=skipped` for silent videos and continue metadata, cover, publish
  queue submission, and terminal platform verification;
- monitor existing local/remote publish jobs instead of starting duplicates;
- if a configured remote AutoPublish log scan detects platform login or QR
  requirements, return `waiting_confirmation` with the poststage preserved so
  approval resumes the same job;
- require current-message permission for public publish, purchases, deletion,
  payment, and other irreversible actions.

The artifact delivery gate is a routine stage, not a best-effort send. A
file-picker click is not proof. Required media/files must be either verified as
sent by the guarded bridge or mirror/phone evidence, left in a deferred send
state such as `send_deferred_locked`, or blocked with evidence the worker can
resume from.

## Adding A Routine

1. Add a `RoutineDefinition` in `wechat_routines.py`.
2. Map route kinds or fallback keywords to the routine.
3. Add a focused test in `tests/test_wechat_routines.py`.
4. If it changes worker behavior, add a queue or prompt test.
5. Update this document and `ROBUST_EFFICIENT_OPERATIONS.md`.
