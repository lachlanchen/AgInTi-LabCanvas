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
- Image edit/generation routes that refer to a just-sent, quoted, or attached
  image must keep `needs_recent_media=true` even if the route agent names the
  task `generate_image`; the worker must receive the source row IDs and media
  tokens for exact sync.
- The worker runs a source-scoped media-resolution preflight for explicit
  image/file/video routes. It refreshes same-chat media sync, resolves mirror
  candidates by exact token and source time window, copies matches into
  `output/wechat_worker/<task-id>/source_media/`, and writes
  `media_resolution_manifest.json` plus `.md`. Worker agents must use
  `task_copy_path` inputs from that manifest before saying an image/file is
  unavailable. Decoded JPG/PNG/MP4/PDF files outrank raw WeChat `.dat`
  containers; `.dat` is kept only as low-priority evidence. If the first mirror
  lookup has no candidates, the preflight may dry-open the exact source chat
  through `wechat_chat_sync_loop.py` so the official WeChat client materializes
  the media cache, click likely visible image bubbles to force preview/download
  caching when the source is an image, then run media sync a second time before
  declaring the source missing. Raster images copied to `source_media/` are
  probed with Pillow and OCRed with local Tesseract (`eng+chi_sim+chi_tra+jpn`
  when available). The OCR transcript is written under
  `output/wechat_worker/<task-id>/image_text/`, added to the manifest, and
  injected into the worker prompt as evidence for image-reading tasks. If WeChat
  exposes only a broken or tiny cached image, the GUI probe also saves visible
  screenshot crops as `visible_wechat_image_fallback` candidates.
- Bare file or image uploads with no explicit instruction are still work: route
  them to `file_intake`, sync/copy the exact source into
  `output/wechat_worker/<task-id>/intake/`, record metadata and checksum, and
  send a short receipt. Do not deep-read or summarize unless the current
  message asks for it.
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
| Exact video publish | Worker | `wechat_autopublish_video.py`, same-chat artifact ledger, LazyEdit CLI | Resolve exact WeChat message IDs/cache first; use the same-chat artifact ledger only when it matches the current/source video row MD5 or byte length. |
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
- Voice-message ingestion is a text normalization step before routing. When
  `message/media_0.db` is decrypted, the direct monitor reads `VoiceInfo`,
  decodes SILK to WAV, transcribes with OpenAI `whisper` or `faster_whisper`,
  caches by chatroom/local_id, and passes the transcript to the same text
  router. Prefer a dedicated multilingual conda ASR environment such as
  `~/miniconda3/envs/whisper/bin/python`; override with
  `WECHAT_VOICE_TRANSCRIBE_PYTHON`, and force OpenAI Whisper with
  `WECHAT_VOICE_WHISPER_BACKEND=whisper` when language auto-detection matters.
  In EchoMind language mode, trust an agent-first `chat_only` decision for
  ordinary transcribed voice; only explicit tool/artifact instructions should
  become worker tasks. If `VoiceInfo` is not ready yet, store the row in the
  pending-voice backlog and retry on backoff. Do not lose the row just because
  the normal message cursor advances. The monitor can run inside the decrypt
  venv, but the voice transcription subprocess must use an ASR Python outside
  that venv.
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
- For story/video tasks, same-chat follow-ups may interrupt an active routine,
  but only when the target task is recent enough. The default 12-hour window
  prevents today’s LALACHAN story request from being merged into an old stale
  Xiaoyunque task. When an interruption is accepted, stale worker output is
  suppressed and the task is requeued for the same per-chat worker session.
- Do not spam progress. Nonterminal `generation_waiting`,
  `generation_poststage_pending`, and `publish_poststage_pending` states are
  internal queue state by default. WeChat should see one contextual ack, then a
  required confirmation/blocker, delivered artifacts, or final verified result.
- Generated-video rendering waits through `generation_waiting` and
  `next_poll_at`; do not keep a multi-hour Codex turn open.
- Paid Xiaoyunque/Seedance work is idempotent per logical WeChat request. After
  a task has a thread URL, submit probe, `credit_guard`,
  `no_new_xyq_submit`, or `monitor_only_no_resubmit`, the automation must not
  submit/continue/retry another paid run for that request. It may only
  monitor/download/send the existing result unless a later current message
  explicitly asks for a new paid rerun.
- If that monitored task already has its configured MP4 on disk, preflight
  returns the MP4 immediately through the required artifact delivery gate before
  any continuation helper, watcher, submitter, or Codex worker agent is called.
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
2. create story/prompt, read same-chat interruptions, and send the revised story
   for confirmation when the latest messages ask for story changes;
3. when the story is approved, promote the same `waiting_confirmation` row into
   `generated_video` and preserve `story_confirmation_result` plus
   `approved_story_*` so the worker uses the exact story already shown to the
   group;
4. submit or resume Xiaoyunque only after the current request/interruptions
   authorize generation;
5. answer Xiaoyunque storyboard/reference continuation prompts in the same
   `thread_id` with `xyq_continue_thread.py` when the current request already
   authorizes generation, using the approved story and the latest same-chat
   constraints rather than a generic continue message;
6. monitor/download through deterministic CDP routines;
7. send the verified MP4 to the source chat and record `sent_file_paths`;
8. only then queue LazyEdit import/process;
9. publish only if the current request explicitly allows it.

If the user changes direction while a story/video worker is running, the
monitor does not solve the task itself. It appends an interruption packet to
the active queue row. When the worker turn returns, the queue suppresses stale
output, requeues the task, and the resumed worker agent reads the full
interruption history before choosing the next routine stage.

If the user or operator says the XYQ output was already manually downloaded to
`Downloads` and handed to LazyEdit/publication, including a session with two
video outputs, record `manual_generated_video_handoff`, close the automation
task, and take no further XYQ/LazyEdit action. That note is state, not a new
download, generation, import, or publish request.

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

1. extract the current/source quoted video `md5`/`length` metadata from the
   exact local-id rows selected by routing;
2. run `wechat_autopublish_video.py` with exact `message_local_ids` and
   optionally `--fetch-gui` so the official client/cache path has priority;
3. if the cache path fails, search only same-chat queued task history for prior
   `sent_file_paths`, result files, generated-video outputs, and task artifact
   MP4s;
4. accept a ledger file only when it matches the current/source video row MD5,
   or when no MD5 exists and byte length matches that row;
5. copy the exact match into Nutstore AutoPublish with a `_COMPLETED` name;
6. pass the original generation/source task summary, supporting prompt/story
   snippets, and safe source material into the LazyEdit correction and metadata
   prompt files;
7. mark old cache-miss refusals or old unverified “submitted publish” bot
   messages as obsolete context, not evidence;
8. run LazyEdit and verify local plus remote publish queues.

LazyEdit is a mature downstream tool, not a block of logic to reimplement in
the worker. The worker should prepare exact source evidence and two prompt
files, then call LazyEdit:

- `lazyedit_correction_context.md`: rich same-chat/source context for subtitle
  correction, including the WeChat message sent with the video, quoted/source
  rows, media metadata, known names, terms, and visible context. For
  AI-generated videos, append the generated story/script and Xiaoyunque/Seedance
  prompt before the LazyEdit command. Use this as reference, not a verbatim
  transcript.
- `lazyedit_metadata_brief.md`: short public-facing title/description/keyword
  guidance. Do not pass full scripts or chat history as metadata.

LazyEdit owns subtitle correction, translation, subtitle/logo burn, metadata,
cover extraction, browser-safe MP4/ZIP packaging, and local publish job
creation. AutoPublish owns platform browser/API posting. LabCanvas owns source
isolation, current-message permissions, queue state, terminal verification, and
WeChat artifact delivery.
The resumed Codex worker agent owns LazyEdit context selection and command
invocation. Deterministic code is allowed for source isolation, duplicate
guards, short probes, queue state, and terminal verification, but it must not
become a parallel hardcoded publish workflow.

If both the WeChat cache and artifact ledger fail, stop source-limited. Do not
reuse a nearby video, another group’s artifact, or an older unrelated task.
Old history and source-task summaries may improve subtitle correction and
metadata, but they must not broaden source-video selection beyond the current
quoted/source local-id rows.
When a bug fix invalidates an already stored worker result, re-run the original
task with `labcanvas wechat worker reprocess <task_id> <reason>` instead of
editing the private queue or manually doing the chat task. Reprocess preserves
the source rows and clears stale result/preflight/send state.
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
Silent or nearly silent videos may produce empty transcripts and a skipped
subtitle-burn step. Treat `burn=skipped` as a valid terminal media state when
transcribe/translate/caption/keyframes are complete; the routine must still
generate metadata, extract a cover, queue the real publish job, and verify the
remote platforms. Do not wait for subtitle burn forever and do not use an old
video to satisfy the request.
Publish-bundle verification includes the ZIP payload codec, not only the source
file. The bundled `_highlighted.mp4` must be browser-safe H.264/AVC (`avc1`),
`yuv420p`, AAC audio, and `+faststart`; if the selected source or skipped-burn
fallback is HEVC/H.265, LazyEdit must transcode it before AutoPublish receives
the ZIP.
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
- direct monitors report `ready=true`; `caught_up=true` only means state reached
  the latest decrypted row, while `source_stale=true` means the Linux WeChat
  source has not materialized recent phone-side messages and can miss audio;
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
- `labcanvas wechat queue --json` includes `attention.counts`,
  `attention.summary`, `attention.by_chat`, and
  `attention.recommended_commands`;
- no unexpected `pending`, stale `in_progress`, stale `send_retrying`, or
  wrong-chat send errors.

## Recovery Playbooks

No reply:

```bash
labcanvas wechat health --json
labcanvas wechat queue --json
tail -n 80 output/wechat_gui_agent/$(date +%F)/supervisor-worker.log
```

If the monitor is `ready=true`, caught up, and no task exists, the message was
not actionable or was filtered. If `source_stale=true`, first restore desktop
message materialization; Whisper and route logic cannot process rows that never
entered the decrypted DB. If a task exists, follow its state instead of sending
a manual duplicate.
Use the queue attention section first: `delivery_blocked` means the artifact or
completion exists but WeChat delivery is blocked, `human_blocked` means an
approval step is required, `failed` means repair/reprocess is needed, and
`stale` means a queue clock such as `next_poll_at`, `next_poststage_at`, or
`send_retry_claimed_at` is overdue. Follow `recommended_commands` before
running ad hoc scripts.
If the source group has no fresh DB rows even though the user sent a message,
run or check `wechat_chat_sync_loop.py`: it dry-opens the configured chat with
the normal title guard and no send action, then the direct monitor can process
newly materialized rows. On slow remote desktops, raise
`WECHAT_CHAT_SYNC_TIMEOUT` or `WECHAT_CHAT_SYNC_GUI_SEND_MAX_SECONDS` instead of
letting dry-open attempts fail at the short standalone GUI sender timeout.
If one configured chat repeatedly times out or returns noisy blank title OCR,
leave `WECHAT_CHAT_SYNC_FAILURE_BACKOFF_SECONDS` enabled so the loop retries it
periodically without blocking refresh of the other groups.
Chat-sync dry-open is only a materialization helper; it must yield whenever the
queue has `send_retrying`, `send_deferred_locked`, or required artifact delivery
work so actual replies and files get the GUI lane first.
If old send failures contain title-guard OCR noise such as `OCR='3 - oO\n|'`,
the worker treats it as a retryable `title_guard_blank` blank-pane failure,
while real wrong-chat titles remain non-retryable.
`send_retrying` rows must not be reclaimed before the active GUI sender timeout
plus grace. If a row is stuck, inspect `send_retry_claimed_at` and
`send_deferred_reason`; do not start a second manual sender while one may still
own the serialized GUI send lane.
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
- inspect `media_resolution_manifest.md` in the task artifact directory and use
  any listed `task_copy_path` before reporting missing media;
- if the media row exists but no file is cached, let the preflight dry-open the
  exact chat and, for images, click the visible bubble once so WeChat caches the
  preview/original before rerunning sync;
- for image transcription, use the manifest `OCR text` path and preview first;
  if OCR is empty, inspect the copied image itself before saying no readable
  text was found; visible GUI crops are valid fallback source media when the
  original WeChat cache file is broken;
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
