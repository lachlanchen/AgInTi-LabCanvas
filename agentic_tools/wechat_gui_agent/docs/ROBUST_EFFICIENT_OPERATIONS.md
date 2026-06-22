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
  GUI is locked, enqueue them as `send_deferred_locked` worker-outbox tasks
  instead of dropping them.
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
| `send_deferred_locked` | WeChat is locked. | Unlock normally, then flush deferred outbox. |
| `generation_poststage_pending` | MP4 was delivered; LazyEdit/public publish is queued or still running. | Worker claims poststage after `next_poststage_at`. |
| `waiting_confirmation` | Human approval required. | Approve/reject through CLI or web panel. |
| `send_failed` | Non-deferred send failure. | Inspect evidence, fix target/title guard, resend stored result. |
| `worker_failed` | Backend failed before a useful result. | Fix source/tool issue; rerun only if safe. |
| `done` | Requested stages completed. | No action. |

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
- keep `wechat_desktop_unlock_watchdog.py --loop --flush-deferred` running when
  an owner-authorized Android phone is attached;
- the watchdog only uses the normal mobile WeChat `桌面微信已锁定` / `已登录设备`
  controls and refuses to handle phone credential prompts;
- after unlock, run `wechat_task_worker.py --flush-deferred` or let the
  watchdog/worker loop flush automatically.

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
