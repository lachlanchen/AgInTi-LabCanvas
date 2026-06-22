# Robust And Efficient Operations

This guide is the system contract for keeping LabCanvas WeChat automation
durable, low-cost, and predictable. Use it when changing monitors, workers,
media sync, generated-video workflows, LazyEdit publishing, or GUI sending.

## Operating Model

Treat WeChat as a command mirror, not as the executor. The durable system is:

```text
official WeChat client
  -> local decrypted mirror
  -> per-chat fast monitor
  -> route decision and source context
  -> routine contract
  -> JSONL worker queue
  -> deterministic routines and Codex worker sessions
  -> artifact delivery gate
  -> guarded GUI sender
```

The fast monitor should be responsive and cheap. It reads local DB/files,
coalesces bursts, classifies intent, saves memory items, and enqueues slow work.
The worker owns tool execution, artifact creation, long browser jobs, and final
deliverables. Deterministic routines own polling, resend, and poststage work so
long waits do not hold a model call open.

The routine registry is implemented in
`agentic_tools/wechat_gui_agent/scripts/wechat_routines.py` and documented in
`agentic_tools/wechat_gui_agent/docs/ROUTINE_ORCHESTRATOR.md`. Every queued
worker task must carry `task.routine`; when claimed, the worker writes
`routine_contract.json` and `routine_contract.md` into the task artifact
directory. The Codex worker supervises that contract rather than designing a new
workflow from scratch.

## Non-Negotiable Invariants

- One chat or DM equals one private config, one state file, and one exact send
  target.
- Never mix context, media, files, Codex sessions, or generated artifacts across
  chats.
- Every live send must pass the send target and title guard.
- For the common phone-to-desktop workflow, enable
  `allow_human_self_messages=true` with `self_message_policy=human_commands`.
  Keep `ignore_self_messages=true`, `respond_to_self=false`,
  `self_messages_text_only=true`, and `ignore_probable_bot_self_replies=true`.
  This lets same-account mobile text commands control the system while blocking
  the bot's own acknowledgements and returned files from looping.
- Old history can explain context, but cannot authorize LazyEdit, public
  posting, purchases, deletion, or other irreversible actions.
- Source media must match the same chat and exact source or quoted message. If
  it is missing, stop source-limited and ask for resend/opening the media.
- GUI file delivery is a first-class state, not a best-effort afterthought.
- Fast chat replies and organizer acknowledgements must also be durable. If the
  GUI is locked, the serialized sender is busy, or the sender times out while a
  file/video is being delivered, enqueue them as `send_deferred_locked`
  worker-outbox tasks instead of dropping them. Preserve
  `send_deferred_reason` as `wechat_locked`, `gui_send_busy`,
  `gui_send_timeout`, `wechat_entry_required`, or `title_guard_blank`.
- Direct monitor state writes must be atomic. A restart or concurrent stop
  cannot leave a half-written JSON state file.
- Login, CAPTCHA, QR, payment, lock screen, and irreversible decisions wait for
  normal human approval.
- Do not use packet interception, private-protocol replay, credential/session
  extraction, lock bypass, or traffic decryption for control.

## Routine Ownership

| Routine | Owner | Entry point | Efficient behavior |
| --- | --- | --- | --- |
| Direct receive | Fast monitor | `wechat_direct_chatops.py --loop` | Poll local decrypted DB; no Codex call unless new rows need routing/reply. |
| Memory/inbox | Fast monitor | organizer config + `wechat_memory.py` | Deterministic save/ACK for ordinary notes. |
| Media sync | Media loop | `wechat_media_sync_loop.sh` | Copy only same-chat files/media into ignored private storage. |
| Routine selection | Fast monitor | `wechat_routines.py` | Convert route decisions into named routines and stage contracts. |
| Slow task enqueue | Fast monitor | `enqueue_worker_task()` | Put full source context and `task.routine` into queue once; avoid duplicate work. |
| Worker execution | Worker | `wechat_task_worker.py --loop --send` | Write routine contract, supervise stages, dynamic model effort, retry only weak/failing outputs. |
| Generated video | Queue orchestrator | `GENERATED_VIDEO_ROUTINES.md` | Store route contract, wait via queue/CDP, deliver MP4 before poststage. |
| Exact video publish | Worker | `wechat_autopublish_video.py` + LazyEdit CLI | Use exact message IDs; fail closed if media is missing. |
| GUI send | Sender | `wechat_gui_send.py` | Serialize with lock, OCR/title guard, screenshots, deferred outbox. |
| Browser assist | Human + worker | `wechat_browser_assist.py` | Use only for login/CAPTCHA/download confirmation or blocked web UI. |

## Token And Latency Policy

- Idle polling is local-only and should not spend model tokens.
- Use fast-router Codex only for new actionable messages, ambiguous routing, or
  immediate lightweight replies.
- Keep route classification agent-first for triggerable non-language chats:
  `agent_route_enabled=true` with `agent_route_prefilter=agent_first` lets the
  per-chat `route` Codex session choose `route_kind`, project, source policy,
  and worker need before keyword lists. Keyword and attachment checks remain as
  fallback and safety gates, not the primary capability map.
- The route model cannot suppress hard artifact work. If the current coalesced
  request clearly asks to send/save/download/copy a file, video, image, audio,
  PDF, or generated artifact, route it to the worker even if the route model
  mistakenly returns `chat_only`.
- Do not use the WeChat search box for normal sending. GUI delivery should use
  the currently verified chat, a configured `open_click`, or configured
  `fallback_clicks`; otherwise defer/fail closed. Configured visible-list rows
  are opened with a normal single click before double-click fallback, because
  double-clicking can leave some Linux WeChat builds on a blank right pane. If
  the task needs web/source search, use the controlled browser or
  browser-assist workflow instead of WeChat search.
- Reuse per-chat `fast` and `worker` sessions. Session keys must be scoped by
  exact chat title and role.
- Coalesce short message bursts into one task, but preserve every focused row in
  the request so the worker sees the complete instruction.
- Generated-video rendering waits through `generation_waiting` and
  `next_poll_at`; do not keep a multi-hour Codex turn open.
- LazyEdit/public publish poststages wait through
  `generation_poststage_pending`; timeouts requeue instead of completing.
- Use `gpt-5.5` medium for normal research, PDF, figure, and generated-video
  browser work. Use high for CAD/PCB/Blender/install/tool execution. Use xhigh
  only for full autonomous end-to-end tasks.

## State Machine

| State | Meaning | Next action |
| --- | --- | --- |
| `pending` | Task is queued. | Worker claims under file lock. |
| `in_progress` | Worker owns the task. | Complete, requeue, or fail with evidence. |
| `generation_waiting` | Xiaoyunque/browser job is running or queued. | Deterministic CDP/status probe after `next_poll_at`. |
| `send_deferred_artifact` | Result exists but required file was not sent. | Fix GUI/file send and flush deferred outbox. |
| `send_deferred_locked` | WeChat is locked, at the Enter Weixin gate, or the serialized GUI send lane was busy/timed out. | Unlock, enter the client, or wait for the active send, then flush deferred outbox. `gui_send_busy`, `gui_send_timeout`, and `wechat_entry_required` use short retries once the lane is free. |
| `generation_poststage_pending` | MP4 was delivered; LazyEdit/public publish is queued or still running. | Worker claims poststage after `next_poststage_at`. |
| `waiting_confirmation` | Human approval required. | Approve/reject through CLI or web panel. |
| `send_failed` | Non-deferred send failure. | Inspect evidence, fix target/title guard, resend stored result. |
| `worker_failed` | Backend failed before a useful result. | Fix source/tool issue; rerun only if safe. |
| `done` | Requested stages completed. | No action. |

Returned video/audio files are required delivery artifacts for every route, not
only `generate_video`. The worker must send media before completion text,
record success in `sent_file_paths`, and keep the queue item deferred if the GUI
cannot attach the media. A guarded `dry-run-opened` chat event only proves the
target chat was opened; the attachment bridge must also exit successfully before
`sent_file_paths` is updated. If old rows were closed without the media ledger,
run:

```bash
labcanvas wechat worker repair-artifacts
```

File-send success must mean WeChat accepted the attachment, not merely that the
automation clicked the file-picker button. The visible-chat bridge captures a
preflight screenshot and a post-send screenshot, runs the same locked/entry
surface detector used by `wechat_gui_send.py`, and exits with `WECHAT_LOCKED`
instead of recording success if the client surface is not usable. If desktop
delivery is unreliable but an owner-authorized Android device is attached, use
the Android share-sheet fallback, then verify the phone chat list or mirror DB
shows the target chat with `[视频]`, `[图片]`, or `[文件]` at the new timestamp
before treating the artifact as delivered.

## Generated Video Contract

For `route_kind=generate_video`, the task artifact directory must contain a
generated-video route contract with `stage_permissions` and
`orchestration_routine`. Follow this order:

1. write route contract;
2. create story/prompt and submit or resume Xiaoyunque;
3. monitor/download through deterministic CDP routines;
4. send the verified MP4 to the source chat and record `sent_file_paths`;
5. only then queue LazyEdit import/process;
6. publish only if the current request explicitly allows it.

If the MP4 cannot be sent, do not import to LazyEdit or publish. Leave the task
in `send_deferred_artifact` or `send_deferred_locked`.

## Health Checks

Run these after code changes, config changes, desktop restarts, or reports of no
response:

```bash
labcanvas wechat status
labcanvas wechat health --json
labcanvas wechat control-map --json
labcanvas wechat queue --json
tmux list-windows -t labcanvas-wechat
```

Expected signs:

- all monitored configs have distinct `state_path`;
- `ignore_self_messages` is true in production;
- `allow_human_self_messages` is true when the account owner sends commands from
  the same logged-in mobile account;
- `self_messages_text_only` and `ignore_probable_bot_self_replies` are true to
  prevent self-file and bot-reply loops;
- send targets have title guards;
- direct monitors are caught up or intentionally stale because no new DB rows
  exist;
- `chat-sync` is running when multiple groups must respond even if the Linux
  client has not recently opened those conversations;
- `chat-sync` yields with `send_lane_reserved` when the worker queue has
  pending, active, retryable deferred, or artifact-send tasks, so dry-open
  polling cannot hold the serialized GUI sender ahead of actual replies. It
  re-checks the queue before every configured target, not only once per cycle,
  so a newly claimed worker send can interrupt an in-progress sync pass;
- worker loop is alive;
- no unexpected `pending`, stale `in_progress`, or wrong-chat send errors.

## Recovery Playbooks

No reply:

```bash
labcanvas wechat health --json
labcanvas wechat queue --json
tail -n 80 output/wechat_gui_agent/$(date +%F)/supervisor-worker.log
```

If the monitor is caught up and no task exists, the message was not actionable
or was filtered. If a task exists, follow its state instead of sending a manual
duplicate.
If the source group has no fresh DB rows even though the user sent a message,
run or check `wechat_chat_sync_loop.py`: it dry-opens the configured chat with
the normal title guard and no send action, then the direct monitor can process
newly materialized rows.
If old send failures contain title-guard OCR noise such as `OCR='3 - oO\n|'`,
the worker treats it as a retryable `title_guard_blank` blank-pane failure,
while real wrong-chat titles remain non-retryable.
For live smoke tests, simple messages such as `ping`, `test`, `best`, `在吗`, or
`测试` are actionable in organizer/link-inbox chats and should return a short
health acknowledgement or become a deferred outbox task if WeChat is locked.

Wrong or mixed chat:

- stop live sends;
- verify each config has a unique `state_path`;
- verify `chat`, `source.chat`, `send_target`, and expected title;
- clear only the bad private state after backing it up;
- rerun health and send a dry-run message before live sending.

Missing image/video/file:

- run media sync for the exact chat;
- ensure the user opened/downloaded the source in WeChat if the client has not
  cached it;
- fail source-limited instead of borrowing nearby files.

WeChat locked:

- do not bypass the lock, decrypt traffic, or forge protocol requests;
- backend work may continue and results become `send_deferred_locked`;
- if a required MP4/PDF/image was already sent but the final text fails, keep
  `sent_file_paths`, record `post_artifact_send_errors`, and leave the task
  `send_deferred_locked` so the next flush sends the missing text instead of
  falsely closing the task;
- keep `wechat_desktop_unlock_watchdog.py --loop --flush-deferred` running when
  an owner-authorized Android phone is attached;
- the watchdog only uses the normal mobile WeChat `桌面微信已锁定` / `已登录设备`
  controls and refuses to handle phone credential prompts;
- if the Linux client restarts to the small `Enter Weixin` gate, the watchdog
  clicks that normal desktop entry button and then flushes one deferred outbox
  item;
- after unlock, run `wechat_task_worker.py --flush-deferred` or let the
  watchdog/worker loop flush automatically.

Blank title guard:

- `Opened chat title guard failed ... OCR=''` is treated as a transient
  rendering/OCR miss, not as a wrong-chat proof.
- The sender waits at least 0.8 seconds before title OCR and retries title
  checks for at least 8 seconds so a selected chat can finish loading.
- Blank title-guard failures enter `send_deferred_locked` with
  `send_deferred_reason=title_guard_blank` and are retried with a short backoff.
- Nonblank wrong titles remain fail-closed because they may indicate cross-chat
  risk.
- If a stale click point opens a wrong popup, `wechat_gui_send.py` closes that
  non-target WeChat window before trying the next configured fallback click.
- Transient GUI send retries are bounded by
  `WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES` so one broken outbox item cannot
  monopolize the worker.

Stuck GUI sender:

- Worker and direct sender subprocesses run in their own process group.
- On `WECHAT_SEND_TIMEOUT`, the whole process group is killed, including
  clipboard/GUI helper children, and the task is deferred instead of leaving a
  live process holding the send lane.

Long Xiaoyunque/LazyEdit work:

- check `generation_waiting` or `generation_poststage_pending`;
- verify `next_poll_at` or `next_poststage_at`;
- avoid manual reruns unless the source contract is wrong or the browser state
  is unrecoverable.

## Change Checklist

Before committing changes that affect WeChat automation:

```bash
PYTHONPATH=src python -m unittest tests.test_wechat_task_worker
PYTHONPATH=src python -m unittest discover -s tests
npm test
```

Then:

- update `README.md`, `RUNBOOK.md`, and this guide if behavior changes;
- update the Codex skill and LazySkills copy for durable agent memory;
- restart only worker-side panes with `labcanvas wechat hold reload-workers` or
  kill the worker child under `wechat_restart_loop.sh`;
- verify `gh run list --repo lachlanchen/AgInTi-LabCanvas --limit 3`.

## Documentation Map

- `FULL_CONTROL_MANUAL.md`: complete architecture, scripts, private state, and
  safety boundaries.
- `RUNBOOK.md`: launch, verify, send, and operator procedures.
- `GENERATED_VIDEO_ROUTINES.md`: fixed generated-video/LazyEdit/public publish
  routine.
- `CHATOPS_ARCHITECTURE.md`: routing, monitor, worker, memory, and media design.
- `MIRROR_SCHEMA.md`: local evidence database schema.
- this file: invariants, efficiency rules, states, and recovery.
