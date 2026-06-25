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
- `career_strategy`: writing direction, career positioning, monetization,
  talent/strength synthesis, market/opportunity research, and daily strategy
  notes for `写作 外语 挣钱` and `lachlanchan`.
- `editable_figure_image`: AgInTi/image/BioRender-style figure work with
  editable parts, manifests, SVG/TeX, and previews.
- `story_script_generation`: story, script, plot, dialogue, and prompt writing
  or revision. This route is shared by 懒人科研 and 🍓我的设备, and it must draft
  the requested text before any explicitly requested image/video stage.
- `labcanvas_cad_pcb`: CAD, PCB, OpenSCAD, KiCad, Blender, renders, Gerbers,
  STEP/STL, and device design.
- `file_intake`: bare WeChat file or image upload with no explicit instruction.
  It syncs/saves the exact source, copies it into the task artifact directory,
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
- In `写作 外语 挣钱` and `lachlanchan`, questions about what to write, career
  direction, making money, talents/strengths, opportunities, GitHub/lazying.art
  positioning, or "what should I do" route to `career_strategy`. The worker
  should use chat memory, local project evidence, GitHub/lazying.art context,
  and current research when useful, then return practical next actions without
  exposing private logs.
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
- for career strategy work, keep private evidence reports under `.private/` and
  only send sanitized Markdown from `output/wechat_strategy/` when attaching a
  report to WeChat;
- treat LazyEdit as the mature video-processing/publishing boundary. Workers
  prepare exact source video evidence plus `lazyedit_correction_context.md` and
  `lazyedit_metadata_brief.md`, then call LazyEdit CLI/API and monitor queues
  instead of rebuilding subtitle correction, metadata, packaging, or platform
  browser automation;
- for LALACHAN/Xiaoyunque generated videos, follow
  `references/lalachan-story-video-handoff-for-wechat.md` for story/prompt
  files, image order, model/duration/ratio checks, download verification,
  repo/Nutstore copies, and current-message publish permission gates;
- paid Xiaoyunque/Seedance submit/continue actions are idempotent per logical
  WeChat request. Once a task has a thread URL, submit probe, credit guard, or
  monitor-only flag, agents may only monitor/download/send that existing result
  unless the current user message explicitly authorizes a new paid rerun;
- if the monitored generated-video MP4 already exists in the task output
  directory, the deterministic preflight returns that exact file through the
  artifact delivery gate before calling any continuation helper, watcher,
  submitter, or resumed worker agent. This is an artifact-completion gate, not a
  replacement for the worker agent;
- same-chat follow-up messages for an active story/video task are interruptions,
  not competing tasks. The monitor appends them to `task.interruptions`; the
  resumed worker agent reads the packet, adjusts the routine, and may re-enter
  story/prompt revision before any further Xiaoyunque submit or polling. The
  interruption target must also be recent, currently within 12 hours by
  default, so a new story request cannot attach to a days-old generated-video
  task only because it is in the same chat;
- story/video interruptions are confirmation-gated: after a user asks to revise
  or show a story, the worker must send the updated story to the group and wait
  for clear same-chat generation approval before submitting or continuing
  Xiaoyunque. A later explicit approval can continue the same routine, and its
  Xiaoyunque prompt or continuation message must carry the approved story plus
  the latest same-chat story requirements forward;
- manual Xiaoyunque/LazyEdit handoff notes are terminal state updates. If the
  owner says one or more XYQ videos were already downloaded to `Downloads` and
  handed to LazyEdit/publication, record the handoff, prevent new XYQ submit or
  LazyEdit publish actions, and close the automation task unless a later
  explicit request asks the system to take over again;
- story approval is a state transition, not a new one-off command. Approving a
  `waiting_confirmation` LALACHAN story task with generation intent changes the
  same queue row from `story_script_generation` to `generated_video`, preserves
  the approved story text/file paths under `story_confirmation_result` and
  `approved_story_*`, and lets the worker create the Xiaoyunque prompt from
  that exact approved story;
- treat bare file/image uploads as cheap `file_intake` unless the current
  message explicitly asks to summarize, read, translate, convert, publish, or
  otherwise process the content;
- preserve source media for image edit/generation tasks. If the current request
  refers to a just-sent, quoted, or attached image, the route must carry
  `needs_recent_media=true`, source row IDs, and media tokens even when the
  agent-facing route kind remains `generate_image`;
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
