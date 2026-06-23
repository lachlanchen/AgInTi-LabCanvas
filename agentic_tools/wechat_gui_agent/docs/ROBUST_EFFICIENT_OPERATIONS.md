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
`routine_contract.json`, `routine_contract.md`, and
`agent_routine_cheat_sheet.md` into the task artifact directory. The compact
autonomy contract is also embedded in the resumed worker prompt, making the
system itself responsible for ordinary safe execution. `run_task_orchestrator()`
is the central worker boundary: it records `task.orchestrator`, runs
deterministic routine stages only for mature probes and gates, then resumes the
same per-chat Codex worker session for reasoning, repair, browser work, and
tool-heavy execution. The Codex worker supervises that contract rather than
designing a new workflow from scratch or waiting for manual operator rescue.

## Non-Negotiable Invariants

- One chat or DM equals one private config, one state file, and one exact send
  target.
- Never mix context, media, files, Codex sessions, or generated artifacts across
  chats.
- All monitored chats share the same backend routine skill surface when the
  current message explicitly asks for tool or artifact work: CAD/PCB/LabCanvas,
  editable figures, story/script, file/media, video, publish, writing, LaTeX,
  PDF, and research requests should reach the shared worker routines.
- EchoMind remains language-learning by default for ordinary Japanese, Chinese,
  and English practice, but explicit backend/tool/artifact instructions route
  through the same worker routines.
- Every live send must pass the send target and title guard.
- For the common phone-to-desktop workflow, enable
  `allow_human_self_messages=true` with `self_message_policy=human_commands`.
  Keep `ignore_self_messages=true`, `respond_to_self=false`,
  `self_messages_text_only=true`, and `ignore_probable_bot_self_replies=true`.
  This lets same-account mobile text commands control the system while blocking
  the bot's own acknowledgements and returned files from looping.
- Completion/status messages from the bot, including `Published OK: ...`, must
  never become new backend tasks. If the route agent says a message is bot
  completion/status with no new backend work, do not let keyword fallback
  override it into a publish route.
- Old history can explain context, but cannot authorize LazyEdit, public
  posting, purchases, deletion, or other irreversible actions.
- Source media must match the same chat and exact source or quoted message. If
  it is missing, stop source-limited and ask for resend/opening the media.
- Follow-up requests such as “send the video here”, “download/save the generated
  video”, or “submit it to LazyEdit” should first resolve the newest bounded-age
  same-chat generated MP4 from the worker artifact ledger. This resolver must
  ignore AutoPublish-cache files and other chats, then return the MP4 through
  the required artifact delivery gate.
- GUI file delivery is a first-class state, not a best-effort afterthought.
- Fast chat replies and organizer acknowledgements must also be durable. If the
  GUI is locked, the serialized sender is busy, or the sender times out while a
  file/video is being delivered, enqueue them as `send_deferred_locked`
  worker-outbox tasks instead of dropping them. Preserve
  `send_deferred_reason` as `wechat_locked`, `gui_send_busy`,
  `gui_send_timeout`, `wechat_entry_required`, or `title_guard_blank`.
- Worker reloads must not leave orphaned GUI send helpers holding the send lock
  forever. Before checking the serialized send lane, the worker reaps stale
  orphaned `wechat_gui_send.py` processes older than
  `WECHAT_WORKER_STALE_GUI_SEND_SECONDS` while leaving non-orphaned active sends
  under the normal timeout.
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
| Exact video publish | Worker | same-chat artifact ledger, `wechat_autopublish_video.py`, LazyEdit CLI | Match quoted video MD5/size against same-chat generated/sent artifacts first; if not found, use exact WeChat message IDs/cache before failing closed. |
| GUI send | Sender | `wechat_gui_send.py` | Serialize with lock, OCR/title guard, screenshots, deferred outbox. |
| Android text fallback | Worker outbox | `send_result_with_retries()` | For verified publish-completion text only, if desktop GUI send fails with a deferable guard/timeout, ADB may send a sanitized ASCII completion after screenshot OCR proves the phone is already open to the exact target chat. |
| Browser assist | Human + worker | `wechat_browser_assist.py` | Use only for login/CAPTCHA/download confirmation or blocked web UI. |

## Token And Latency Policy

- Idle polling is local-only and should not spend model tokens.
- Use fast-router Codex only for new actionable messages, ambiguous routing, or
  immediate lightweight replies.
- Keep route classification agent-first for triggerable monitored chats:
  `agent_route_enabled=true` with `agent_route_prefilter=agent_first` lets the
  per-chat `route` Codex session choose `route_kind`, project, source policy,
  and worker need before keyword lists. `agent_router.reuse_session=true` is
  the default, so repeated requests in one chat resume the same route thread.
  Keyword and attachment checks remain auxiliary fallback and safety gates, not
  the primary capability map.
- Codex is the default backend. `agent_backend=claude` or
  `WECHAT_AGENT_BACKEND=claude` may switch a WSL/Windows deployment to Claude
  Code, but it must still use the same route, worker, queue, media, and
  artifact-delivery contracts. Do not bypass source isolation or delivery gates
  because the backend changed.
- Keep `immediate_route_enabled=true` for monitored chats that should enqueue
  backend work. `immediate_ack_enabled=false` only suppresses the visible ack;
  it must not be used as the routing kill switch.
- Keep chat-facing wording agent-led when a route agent is already invoked:
  `dynamic_ack_enabled=true` lets the route JSON carry a short contextual
  `ack`, while deterministic ACK strings remain fallback only. Safety gates,
  source isolation, and queue state may be hardcoded; visible responses should
  not become repetitive mechanical templates.
- The current coalesced request is authoritative. Route and worker prompts must
  preserve every safe explicit instruction, including multi-stage requests, and
  must not shrink a request to a smaller hardcoded action because one keyword
  matched first.
- Every queued worker task should persist `instruction_contract` with
  `current_request_authoritative`, `preserve_safe_explicit_instructions`, and
  `no_keyword_shrink` so the resumed worker can inspect the rule as data.
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
  the request so the worker sees the complete instruction. If a burst arrives
  one row at a time, include the recent same-sender instruction fragments until
  the bot's previous answer; do not revive older work past a bot reply.
- Do not spam progress. Nonterminal `generation_waiting`,
  `generation_poststage_pending`, and `publish_poststage_pending` states are
  internal queue state by default. WeChat should see one contextual ack, then a
  required confirmation/blocker, delivered artifacts, or final verified result.
- Generated-video rendering waits through `generation_waiting` and
  `next_poll_at`; do not keep a multi-hour Codex turn open.
- Generated-video workers must treat `final_video.mp4`, a video player, or
  `渲染合成最终视频 ... 已完成` in the same Xiaoyunque thread as `download_ready`.
  Do not send another continuation/generation prompt for that request, and do
  not convert later `积分不足` text from accidental retries into a final blocker.
- Fresh `pending` messages must be claimed before old due video polls, and video
  polls must be short probes so one old generation cannot starve new requests.
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
| `publish_poststage_pending` | Existing-video LazyEdit/public publish has no terminal platform proof yet. | Worker claims poststage after `next_publish_poststage_at`; deterministic probes run first, then the same chat’s Codex worker session repairs if needed. |
| `waiting_confirmation` | Human approval required. | Approve/reject through CLI or web panel. |
| `send_failed` | Non-deferred send failure. | Inspect evidence, fix target/title guard, then explicitly resend or set `WECHAT_WORKER_FAILED_SEND_MAX_RETRIES` for a repair run. Default workers do not auto-flush terminal failed rows. |
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
3. answer Xiaoyunque storyboard/reference continuation prompts in the same
   `thread_id` with `xyq_continue_thread.py` when the current request already
   authorizes generation;
4. monitor/download through deterministic CDP routines;
5. send the verified MP4 to the source chat and record `sent_file_paths`;
6. only then queue LazyEdit import/process;
7. publish only if the current request explicitly allows it.

Generation is not publication. A generation request creates/downloads/verifies
the video and sends artifacts back to the source chat; it does not authorize
LazyEdit import, AutoPublish, Shipinhao, YouTube, Instagram, or any public
posting. Uploading reference images/assets into Xiaoyunque is generation-stage
input handling, not publication.

If the MP4 cannot be sent, do not import to LazyEdit or publish. Leave the task
in `send_deferred_artifact` or `send_deferred_locked`.

## Exact Video Publish Contract

For `route_kind=publish_video` or an explicit current-message publish request,
the worker resolves the source in this order:

1. extract quoted video `md5`/`length` metadata from the task context;
2. search only same-chat queued task history for prior `sent_file_paths`,
   result files, generated-video outputs, and task artifact MP4s;
3. accept a file only when MD5 matches, or when no MD5 exists and byte length
   matches a same-chat sent/generated artifact;
4. copy the exact match into Nutstore AutoPublish with a `_COMPLETED` name;
5. pass the original generation/source task summary, supporting prompt/story
   snippets, and safe source material into the LazyEdit correction and metadata
   prompt files;
6. mark old cache-miss refusals or old unverified “submitted publish” bot
   messages as obsolete context, not evidence;
7. run LazyEdit and verify local plus remote publish queues;
8. if no ledger match exists, run `wechat_autopublish_video.py` with exact
   `message_local_ids` and optionally `--fetch-gui`.

If both the WeChat cache and artifact ledger fail, stop source-limited. Do not
reuse a nearby video, another group’s artifact, or an older unrelated task.
If LazyEdit reports only queued, submitted, running, missing, or unverified
status, do not say published. Return the current stage to WeChat and keep the
task in `publish_poststage_pending` until all requested platforms have terminal
LazyEdit/remote evidence, a public URL, or an explicit failure that the worker
can repair or report.
If the poststage finds an imported LazyEdit `video_id` but no local publish job,
the deterministic routine must start the actual LazyEdit publish command from
the stored correction and metadata prompts, record the reissue count, and then
continue polling. Existing running or queued jobs are monitored, not duplicated.
The LazyEdit command must execute as separate shell stages:
`source ~/miniconda3/etc/profile.d/conda.sh && conda activate lazyedit &&
python scripts/lazyedit_publish.py ... --json`. A zero-exit command with no
JSON payload is not a successful publish submission; treat it as repairable
`no_json_output` evidence and keep the poststage pending.
Before issuing any new existing-video public publish, probe LazyEdit/remote
queues for the same `video_id` and requested platforms. If terminal evidence is
already present, return `published_verified`; do not enqueue a duplicate job.
Set `WECHAT_WORKER_LAZYEDIT_REMOTE_LOG_COMMAND` in the ignored supervisor env to
let the verifier inspect bounded AutoPublish logs. Login or QR markers should
become `waiting_confirmation` with the same poststage stored, so the user can
log in normally and approve the task to resume.
The tmux supervisor must start the worker through
`wechat_worker_guarded_loop.sh`, which runs
`PYTHONPATH=src python -m agenticapp wechat selftest --suite all --json`
before the worker loop. Keep this guard enabled so broken message transport,
routine contract, Codex resume, or publish repair logic fails closed at
startup/reload; `WECHAT_WORKER_SKIP_SELFTEST=1` is only for a temporary
emergency bypass.

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
- `chat-sync` dry-open uses a GUI sender alarm derived from
  `WECHAT_CHAT_SYNC_TIMEOUT` so inactive groups are not starved by the short
  standalone sender default;
- `chat-sync` yields with `send_lane_reserved` when the worker queue has
  pending, active, retryable deferred, or artifact-send tasks, so dry-open
  polling cannot hold the serialized GUI sender ahead of actual replies. It
  re-checks the queue before every configured target, not only once per cycle,
  so a newly claimed worker send can interrupt an in-progress sync pass;
- the GUI sender fast-rejects a specific wrong native window title, such as
  `EchoMind` while targeting `我的设备`, before running slow OCR. If a group
  moves in the visible chat list, update its private `send_target` click points
  so the first click lands on the intended row and fallback clicks remain only
  backups;
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
newly materialized rows. On slow remote desktops, raise
`WECHAT_CHAT_SYNC_TIMEOUT` or `WECHAT_CHAT_SYNC_GUI_SEND_MAX_SECONDS` instead of
letting dry-open attempts fail at the short standalone GUI sender timeout.
If one configured chat repeatedly times out or returns noisy blank title OCR,
leave `WECHAT_CHAT_SYNC_FAILURE_BACKOFF_SECONDS` enabled so the loop retries it
periodically without blocking refresh of the other groups.
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
