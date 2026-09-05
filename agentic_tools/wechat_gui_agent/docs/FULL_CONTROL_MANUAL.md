# WeChat Full Control Manual

This manual is the operator map for LabCanvas WeChat automation. In this repo,
"full control" means reliable, auditable control of the logged-in local WeChat
client through owned and consented surfaces: isolated GUI actions, local message
mirrors, private media sync, worker queues, and explicit human approval gates.
It does not mean packet interception, TLS bypass, credential extraction, private
protocol replay, CAPTCHA bypass, or unsafe account automation.

Use [`ROBUST_EFFICIENT_OPERATIONS.md`](ROBUST_EFFICIENT_OPERATIONS.md) as the
reliability contract for invariants, token policy, state recovery, and change
checklists. Use [`GENERATED_VIDEO_ROUTINES.md`](GENERATED_VIDEO_ROUTINES.md) for
the fixed generated-video/LazyEdit/public-publish routine.

Before restarting after disk/I/O errors, follow
[storage failure recovery](../../../references/labcanvas-storage-failure-recovery-2026-09-06.md).
The host-side guard must remain readable independently of the project drive.
Never initialize new private queues to hide unavailable or corrupt state.

## Control Layers

```text
WeChat official Linux client on Xvfb/noVNC
  -> encrypted local DB/cache under xwechat_files
  -> private decrypt refresh cache
  -> direct per-chat monitors
  -> mirror + memory + media databases
  -> reused per-chat route agent
  -> JSONL worker queue
  -> reused per-chat Codex/LabCanvas worker session
  -> routine probes, safety gates, and artifact delivery
  -> guarded GUI sender with OCR title check
  -> WeChat message/file reply
```

The system intentionally keeps read, reasoning, worker execution, and send
separate. This makes crosstalk, duplicate replies, and wrong-chat sends easier
to detect and block.

Bridge-mode chats should behave like WeChat is only the message transport for a
backend Codex conversation. The monitor does not try to become the agent. It
coalesces current messages, preserves same-chat source rows/media, asks the
route session whether to answer directly or enqueue a worker, and appends later
same-chat messages as interruptions for the reused worker session. Deterministic
logic is limited to privacy/source isolation, current-message permission gates,
known routine probes, wait-state polling, retry/unlock, and verified file send
back.

## Primary Entry Points

Use the installed/source CLI first:

```bash
labcanvas wechat status
labcanvas wechat health --json
labcanvas wechat control-map --json
labcanvas wechat desktop start
labcanvas wechat hold start
labcanvas wechat hold reload-workers
labcanvas wechat stack start --web-port 19474
~/scripts/create-labcanvas-wechat-after-reboot.sh
labcanvas wechat queue --json
labcanvas wechat worker once --send
labcanvas wechat approve <task-id> --note "approved"
labcanvas wechat reject <task-id> --note "stop"
labcanvas wechat media-sync --chat "<CHAT_NAME>" --auto-source
```

The web studio exposes the same backend through `/api/wechat/status` and
`/api/wechat/action`. The UI can start the stack, open noVNC, process one worker
task, approve/reject the newest waiting task, and send a short explicit message.
Use `labcanvas wechat queue --json` as the first task debugger. Its `attention`
section separates active work from delivery blockers, human confirmations,
stale waits, and failed tasks, then suggests the next safe CLI command.
Do not add browser-only behavior that bypasses the CLI scripts.

## Runtime Sessions

`agentic_tools/wechat_gui_agent/scripts/wechat_stack_tmux.sh start` starts the
full reboot-safe tmux stack:

| Session | Purpose |
| --- | --- |
| `labcanvas-wechat` | WeChat desktop, decrypt refresh, one direct monitor per chat, worker, media sync, and chat materialization sync. |
| `labcanvas-web` | LabCanvas web control panel for status and manual actions. |
| `labcanvas-career-daily` | Daily writing/career/money/self-analysis agent, defaulting to `gpt-5.5` with `xhigh` reasoning and sending to `lachlanchan`. |

After reboot, run:

```bash
~/scripts/create-labcanvas-wechat-after-reboot.sh
```

This wrapper recreates or reuses the same three sessions, then prints JSON
status for the WeChat stack and daily scheduler.

Within `labcanvas-wechat`, `wechat_supervisor_tmux.sh` creates:

| Window | Script | Role |
| --- | --- | --- |
| `desktop` | `wechat_virtual_desktop.sh` | Xvfb/noVNC WeChat desktop and keep-awake. |
| decrypt pane | `wechat_decrypt_refresh_loop.sh` | Incremental private DB refresh. |
| `direct-*` | `wechat_direct_chatops.py --loop --send --no-decrypt` | Fast per-chat monitor. |
| `worker` | `wechat_task_worker.py --loop --send` | Slow backend task executor. |
| `media-sync` | `wechat_media_sync_loop.sh` | Background media/file cache import. |
| `chat-sync` | `wechat_chat_sync_loop.py --loop` | Dry-opens configured chats so inactive Linux WeChat conversations materialize fresh DB rows. Its GUI alarm derives from `WECHAT_CHAT_SYNC_TIMEOUT`; failed dry-opens back off per chat through `WECHAT_CHAT_SYNC_FAILURE_BACKOFF_SECONDS`, and `WECHAT_CHAT_SYNC_PRIORITY` visits important groups first. |

Use `hold reload-workers` or `stack restart` after code/config changes. These
keep the WeChat GUI alive and respawn only monitors, worker, media sync, and web
processes. `stack restart` also restarts the daily scheduler so it picks up new
agent settings. Use `restart-all` only when it is acceptable to close and reopen
WeChat, which may require phone confirmation.

`chat-sync` is intentionally lower priority than outbound replies. By default
it checks `.private/wechat_task_queue.jsonl` and returns `send_lane_reserved`
instead of dry-opening chats when the queue has pending work, retryable
deferred sends, artifact delivery, or long-running poststage work that may need
the serialized GUI sender. It checks at the start of a cycle and before every
target, so a worker send that appears mid-cycle stops further dry-open actions.

## Script Inventory

| Script | Main use |
| --- | --- |
| `wechat_virtual_desktop.sh` | Launch WeChat on display `:97`, VNC, noVNC, and X11 keep-awake; preserve visible QR/entry windows, bound X11 probes, and recover only the exact stale display/client processes when no real window remains. |
| `wechat_gui_send.py` | Search/open target chat, verify native popup title or OCR title, paste/send text, record screenshots. |
| `wechat_chatops_bridge.py` | Legacy visible-chat OCR monitor and direct visible message/file send path. |
| `wechat_direct_backend.py` | Install/probe/decrypt wrapper for optional `ylytdeng/wechat-decrypt`. |
| `wechat_decrypt_refresh_loop.sh` | Locked incremental refresh loop for decrypted DB cache. |
| `wechat_direct_chatops.py` | Direct DB polling, mirror sync, fast route decision, ACK/reply, worker enqueue. |
| `wechat_routines.py` | Named routine registry and stage contracts for queued worker tasks. |
| `wechat_task_worker.py` | Queue claim, model effort selection, LabCanvas worker prompt, artifact/file return. |
| `wechat_chat_sync_loop.py` | No-send GUI opener that cycles direct configs and keeps multi-chat DB ingestion fresh. |
| `wechat_media_sync.py` | Copy same-chat files/images/videos from WeChat folders into private storage. |
| `wechat_media_sync_loop.sh` | Repeat `media-sync` for configured chats. |
| `wechat_autopublish_video.py` | Resolve exact WeChat video rows and copy MP4 to Nutstore AutoPublish. |
| `shipinhao_comment_intel.py` | Read-only analyzer for exported Shipinhao/Finder comment JSON or compatible `wx_channel` API exports. |
| `shipinhao_media_transcribe.py` | Download or consume a verified exact-card capture, run Whisper, and write source-scoped transcript evidence. |
| `shipinhao_gui_audio_capture.py` | Record the visible native Channels player's `WeChatAppEx` stream while OCR identity remains matched; trim auto-advance and register a private hash manifest. |
| `wechat_memory.py` | Structured local inbox/memory tables for notes, todos, links, and summaries. |
| `wechat_mirror.py` | SQLite evidence log for GUI sends, reads, screenshots, and direct messages. |
| `wechat_codex_sessions.py` | Per-chat fast/worker Codex session registry. |
| `wechat_browser_assist.py` | Open a local browser in the isolated desktop for login/CAPTCHA/download help. |
| `wechat_group_create.py` | Open/execute group creation after visual confirmation. |
| `wechat_group_admin.py` | Best-effort group rename and in-group alias changes. |
| `wechat_restart_loop.sh` | Restart wrapper used by tmux supervisor panes. |
| `wechat_supervisor_tmux.sh` | Main WeChat tmux supervisor. |
| `wechat_stack_tmux.sh` | WeChat supervisor plus LabCanvas web panel and daily scheduler. |

## Artifact Delivery Defaults

Workers should not turn every saved note into a WeChat attachment. Ordinary
link/read-later tasks save Markdown/evidence locally and send only a concise
useful chat answer unless the user asked for a file/report or the worker
explicitly marks a substantively read source as worth attaching. The daily
career/self-analysis agent is the special case that attaches Chinese and English
PDF companions, for example `YYYY-MM-DD-career-strategy.zh.pdf` and
`YYYY-MM-DD-career-strategy.en.pdf`. General worker Markdown-to-PDF companions
are opt-in with `WECHAT_MARKDOWN_PDF_COMPANIONS=1`.

The Memo organizer is another explicit scheduled-PDF path. It sends one
interactive Chinese PDF, but only after its agent response has been unwrapped,
grounded against the recent exact-chat evidence ledger, checked for substantive
coverage, and compiled successfully. Its lifetime context is compacted to fit
the smallest active AgInTi provider so a DeepSeek-to-LocalLLM handoff does not
drop the evidence. Raw JSON envelopes, generic tool refusals, and shallow
ungrounded drafts stay private and are retried rather than delivered.

Long-response preservation is separate from those content defaults. The worker
never clips an answer: it sends a moderate answer as at most three coherent,
numbered, retry-safe chat parts. If more parts would be required, it keeps the
complete Markdown in the ignored exact-task artifact directory and sends one
compiled `complete-response.pdf` with a concise chat preview. A failed PDF
compile falls back to all numbered parts, not a truncated prefix. Configure the
boundary with `WECHAT_WORKER_CHAT_PART_CHARS` and
`WECHAT_WORKER_CHAT_MAX_PARTS`.

For source-reading chats, the preferred WeChat output is a short, grounded
message. `鏈接` should try to read links/channel videos/articles and state the
real accessible evidence. `写作 外语 挣钱` should turn shared material into
high-quality writing/career/money ideas. `🍓我的设备`, `懒人科研`, and
`lachlanchan` may run the full LabCanvas/LazyEdit/video/CAD/PCB tool surface
when explicitly requested. `EchoMind` remains language teaching first.
Its periodic lesson runs every six hours and stays within one concise message.
Each example aligns Chinese, English, and Japanese, with tone-marked pinyin,
Japanese inline ruby/furigana such as `予約（よやく）`, and romaji. The separate
previous-day XeLaTeX review remains scheduled at 06:00 HKT. Oversized or
incomplete periodic drafts go through a bounded agent editing pass; never clip
a lesson mid-example merely to satisfy the chat length limit.

Personal-WeChat file attachments default to the allowlisted Android native share
transport. It stages a meaningful filename, resolves the exact MediaStore row,
selects the exact chat, verifies the native recipient confirmation, and records
the component by task/checksum. Long mixed Chinese/English titles get a second,
contrast-enhanced OCR pass only when normal OCR has no exact alias match; tap
coordinates are mapped back to device pixels and remain title-guarded. A file
that passed recipient confirmation and native Send remains delivered even when
restoring the chat surface afterward would fail. Any following text component
performs its own exact-chat guard.

Personal-WeChat Android intake has two complementary lanes. Native notification
events carry messages authored by other people. WeChat does not notify the
account about text authored by that same account on another client, so
`wechat_android_screen_ingress.py` watches only allowlisted chat rows and copies
new outgoing green bubbles through WeChat's native `Copy` action. OCR locates
the row and action, but the copied native text is the payload. The first pass
seeds each visible route without replaying history. Both lanes write the same
synthetic `message_999999.db`, which the ordinary per-chat monitors already
consume.

Screen-intake failures are isolated per route. An exact-title mismatch defers
only that chat with bounded persistent backoff; a changed row signature bypasses
the old backoff, and the other routes continue in the same poll. When OCR sees
both a chat-title line and a message preview containing the same alias, the
exact title line wins. This prevents one renamed or temporarily hidden chat from
poisoning all personal-WeChat intake.

Long self-authored bubbles must be copied in full. After long-pressing the exact
bubble, the screen ingress selects WeChat's native `Select all` action before
`Copy` when that action is present. The native clipboard text, rather than a
visible OCR fragment, is the source event. Health requires a recent successful
route scan, not merely a recent polling heartbeat, so a loop that is alive but
cannot obtain the phone GUI lane is reported as stale.

The MIX 2S exposes WeChat on physical display 0 and WeCom on a virtual display,
but Android 9 UIAutomator is not display-addressable. Consequently all phone
GUI reads and writes share one serialized control lease and one clipboard lock.
Passive WeCom subprocesses are interruptible when a personal-WeChat send needs
the lane; the operation then restores the dual layout. Physical screenshots use
the display token parsed from SurfaceFlinger, and every touch/key command names
display 0 explicitly. Direct personal-WeChat text first tries the guarded Linux
desktop and falls back to the exact-title Android sender only when desktop
preflight proves that WeChat is logged out, locked, or absent. The fallback is
idempotent per exact inbound message and requires a post-send screenshot before
reporting success. Passive readers use a separate cooperative waiter marker so
one reader eventually receives a bounded turn without outranking explicit
outbound work.

The direct monitor may run inside the small decrypt-only virtual environment,
but native Android visual send detection requires Pillow. The monitor therefore
resolves a GUI-capable Python interpreter for `wechat_android_send.py` instead
of blindly inheriting `sys.executable`. A failed native send preserves the exact
reply as a durable `send_deferred_locked` item. Its retry clears any matching
stale composer draft before pasting, verifies that the connected green Send
control disappeared, and records one `text-sent` proof before completion.

WeCom follows the same Android limitation. Before an automated read, text send,
or file send, the bridge temporarily moves WeCom to physical display 0 and uses
explicit `input touchscreen -d 0` and `input keyboard -d 0` commands. The
right-side virtual WeCom pane is a review surface, not the UIAutomator input
surface. After the exact-chat operation, the bridge restores WeChat on the left
and WeCom on the right. In the WeCom hierarchy, `:id/gor` is the quoted-reply
banner, not an attachment tray; preserve it. File delivery opens the real plus
button, accepts the titleless owned attachment modal only after exact chat-title
verification, and uses the known lower-right plus-button fallback when the icon
sits just below the composer's measured bounds.

An ordinary inbound video attachment is save-only. Its source-local-id task may
copy the exact MP4 into the ignored task `source_media/` directory, but it must
remain silent and cannot enter LazyEdit, AutoPublish, transcription, return-file
delivery, or public posting without a separate current same-chat text request.
The Android sender stores the submitted file name, size, MD5, and SHA-256 in its
private component ledger. If WeChat transcodes a returned video, the monitor
matches XML `originsourcemd5` against that ledger and suppresses the row before
routing. This prevents a returned MP4 from recursively creating new work.

When the source exists only in Android WeChat, use `labcanvas wechat
native-save-video`. The command verifies the exact chat, opens the agent-selected
exact bubble, requests `查看原视频` when offered, invokes native album save, pulls
the new `DCIM/WeiXin/mmexport...` MediaStore object, probes and checksums the
host copy, and then deletes the temporary phone file plus MediaStore row. It
writes `native-video-export.json`; Android media cannot enter AutoPublish unless
that manifest binds the exact host path/checksum and records
`device_copy_removed=true`. Screen/player/scrcpy/GUI recordings are forbidden
as recovery substitutes. If native retrieval fails, stop.

The serialized desktop Linux file chooser remains a preflight fallback only
when Android proves its exact-title guard failed before sharing began. It uses
clipboard path paste (`Ctrl+L`, paste absolute path, `Enter`). Uncertain Android
submission states never fall through to desktop because that could duplicate an
already committed file.

## Private State Files

All real account data stays ignored under `agentic_tools/wechat_gui_agent/.private/`.
Never commit these files or paste their secrets into public logs.

| File or folder | Purpose |
| --- | --- |
| `wechat_supervisor.local.env` | `WECHAT_DIRECT_CONFIGS`, media chat list, and supervisor settings. |
| `*-direct-chatops.local.json` | One direct monitor config per group or DM. |
| `*-direct-chatops.state.json` | Per-chat cursor and responded IDs. Must be unique per chat. |
| `wechat_send_targets.local.json` | Optional send target registry. |
| `wechat_task_queue.jsonl` | Private worker queue and task status. |
| `wechat_gui_send.lock` | Global send lock for all GUI sends. |
| `wechat_mirror.sqlite` | Evidence and message mirror. |
| `wechat_memory.sqlite` | Structured notes, links, todos, and tags. |
| `wechat_android_ingress/message_999999.db` | Synthetic exact-chat intake for Android notifications and native screen-copy self messages. |
| `wechat_android_send.sqlite` | Idempotent native Android outbound component ledger. |
| `wechat_decrypt/` | External checkout, keys, decrypted DB cache, and logs. |
| `wechat_image_keys.local.json` | Optional private image decode keys. |
| `codex_sessions/sessions.local.json` | Per-chat fast/worker Codex session ids. |
| `downloads/` | Private synced WeChat media/files by chat/profile/category. |

## Direct Chat Config Contract

Each monitored chat must have a private config with an isolated state file and
a guarded send target:

```json
{
  "chat_name": "<CHAT_NAME>",
  "message_table": "<Msg_TABLE>",
  "self_wxid": "<SELF_WXID>",
  "state_path": "agentic_tools/wechat_gui_agent/.private/<chat>.state.json",
  "respond_to_all": false,
  "ignore_self_messages": true,
  "chat_purpose": "research",
  "send_target": {
    "name": "<CHAT_NAME>",
    "query": "<SEARCH_TEXT>",
    "expected_title": "<CHAT_NAME>",
    "expected_title_aliases": ["<OCR_ALIAS>"],
    "result_click": [165, 125],
    "fallback_clicks": [[165, 100], [165, 170], [240, 335]]
  }
}
```

Rules:

- `chat_name`, `message_table`, and `state_path` must be distinct per group.
- Keep `ignore_self_messages: true` in production.
- Use `chat_purpose` to separate research, language learning, web clips,
  personal organizer, and direct-message behavior.
- Prefer `expected_title_aliases` for emoji/OCR issues.
- Prefer configured visible-list row coordinates over search. The sender tries
  single-click open first, then double-click fallback, and only sends after the
  exact title guard passes.
- Blank-pane OCR noise such as `OCR='3 - oO\n|'` is retryable as
  `title_guard_blank`; real wrong-chat title text remains a hard failure.
- `allow_title_guard_fallback` is for dry-run review only. Live sends still fail
  closed unless `allow_live_title_guard_fallback` is deliberately set for a
  known single-chat workflow.

## No-Crosstalk Guarantees

Wrong-group replies are prevented at several layers:

1. One direct config and state file per chat prevents local ID collisions.
2. Fast monitor tasks include a `route` contract with source chat, config id,
   message table, send target name, and expected title.
3. Worker sends validate `task.chat`, `source.chat`, `route.chat`,
   `send_target.name`, and `expected_title` before any message/file is sent.
4. `wechat_gui_send.py` uses one global lock, opens the target, OCR-checks the
   right-pane title, and fails closed if the title does not match.
5. Media sync and worker prompts are source-limited to the same chat and exact
   source/reference local IDs.

If a monitor is handling `🍓我的设备` while a new message arrives in `鏈接`, the
device task must continue replying only to `🍓我的设备`; the `鏈接` monitor handles
its own message independently.

## Receive Path

The normal receive path is direct local data, not screen OCR:

1. `wechat_decrypt_refresh_loop.sh` refreshes decrypted cache files under
   `.private/wechat_decrypt/decrypted/`.
2. Each `wechat_direct_chatops.py` monitor reads only its configured
   `message_table`.
3. Rows are mirrored with `chat_name`, local/server ids, sender display, type,
   timestamp, and decoded visible text.
4. Structured memory capture can tag notes, links, todos, media, and requests.
5. `should_respond` checks self-message guard, danger policy, local type, quote
   rows, attachment triggers, and chat purpose.
6. The fast agent returns one of `CHAT`, `ACK+TASK`, or `NO_REPLY`.

Direct monitor state is written atomically. If a monitor is killed during a
write, the next restart should see either the old valid JSON state or the new
valid JSON state, not a concatenated partial file.

Polling is local DB/file work. It spends model tokens only when a new message
needs a route decision, a language/research answer, or a worker task.

## Worker Path

Slow work goes through `.private/wechat_task_queue.jsonl`.

```bash
labcanvas wechat worker enqueue --chat "<CHAT_NAME>" "summarize this PDF"
labcanvas wechat worker once --send
labcanvas wechat queue --json
labcanvas wechat routines --json
labcanvas wechat voice-transcribe --config "<DIRECT_CONFIG>" --local-id 121 --json
```

Before a worker task is queued, the fast monitor converts the route decision
into a named routine from `wechat_routines.py`. The task stores `task.routine`.
When `agent_bridge_mode=true`, this route decision is agent-first: a safe
`chat_only` decision stays in the direct chat path, and backend decisions become
source-scoped tasks with a routine contract. Non-bridge legacy configs may still
use deterministic hard-artifact guards as a safety fallback, but monitored
bridge chats should prefer the route agent plus the routine menu over keyword
dispatch.
Voice rows are handled before this routing step: `wechat_voice_transcribe.py`
uses decrypted `message/media_0.db`/`VoiceInfo`, the private decrypt venv's
`pilk` SILK decoder, and a separate ASR Python that can import OpenAI
`whisper` or `faster_whisper`. The default selector prefers a dedicated
multilingual conda environment such as `~/miniconda3/envs/whisper/bin/python`,
then falls back to `whisperx`, main conda, and system Python. Override with
`voice_transcription_python` / `WECHAT_VOICE_TRANSCRIBE_PYTHON`; force a backend
with `voice_transcription_backend` / `WECHAT_VOICE_WHISPER_BACKEND=whisper`.
Transcripts are cached under `.private/voice_transcriptions.json`; raw voice XML
secrets are not passed to prompts. If the message row arrives before
`VoiceInfo` is ready, the monitor stores the row in a pending-voice backlog and
retries it on a short backoff. The normal cursor may continue advancing, but the
voice row is routed when the audio later appears.
When the worker claims the task, it writes `routine_contract.json` and
`routine_contract.md` in the task artifact directory and includes that contract
in the worker prompt. The worker supervises routine stages and resolves blockers
instead of designing a fresh workflow for every message. See
`docs/ROUTINE_ORCHESTRATOR.md`.

The worker chooses effort based on task difficulty:

| Effort | Typical tasks |
| --- | --- |
| `medium` | PDF, paper search, summaries, figures, links, dataset notes. |
| `high` | CAD, PCB, Blender/OpenSCAD, video, downloads, scripts, database work. |
| `xhigh` | Full autonomous tasks, install, publish, GitHub/MCP, ordering, robust end-to-end work. |

The worker prompt includes LabCanvas commands for figure grids, AgInTi image
generation, CAD/PCB tasks, Blender scene renders, LazyEdit/AutoPublish, and
browser assist. It also recognizes LALACHAN/RaraXia/AyaChan/SasaKun requests
from WeChat and routes them as a story-video workflow: write/save the Chinese
story, save the Xiaoyunque prompt, upload the eight LALACHAN reference images
in order, choose a relatively cheap suitable Seedance model, generate/download the MP4, verify
with `ffprobe`, and send the verified MP4 back to the source WeChat chat. `Seedance 2.0 Mini 体验版` / `vipnew`
at a visible cheap rate such as `单秒限时低至4积分` is preferred; if unavailable, the worker should choose the
relatively cheaper suitable `Fast`, `Fast VIP`, or available Seedance row and continue. Model selection is not a blocker. A
generated MP4 within 5 seconds of the requested duration is acceptable unless the current request explicitly requires exact duration. A
submitted Xiaoyunque job stays as `generation_waiting` and is checked by short
status-probe cycles; the next poll is based on page state rather than a fixed
long timeout. If the thread asks to confirm storyboard/reference assets before
making the final video, the worker uses `xyq_continue_thread.py` to send the
approval into the same `thread_id`; when `XYQ_ACCESS_KEY` is available the
helper also submits the same continuation through Xiaoyunque OpenAPI. It must
not reopen an old history item. If Xiaoyunque reports `积分不足` or `余额不足`,
the task stops as `waiting_confirmation` instead of looping; the user must
recharge or approve a shorter/lower-budget fallback before the worker resumes. If
the agent times out before returning monitor state, the worker
discovers the active Xiaoyunque `thread_id` through Chrome CDP and resumes from
the browser state instead of closing the task.

For required artifact delivery, file/video send success is not enough to mark a
task done if the follow-up text or confirmation send fails. Keep
`sent_file_paths`, store `post_artifact_send_errors`, and leave the task in
`send_deferred_locked` when the failure is `WECHAT_LOCKED`, entry-required,
busy, or timeout. The next flush should skip already sent files and retry only
the missing user-facing text/confirmation.

Do not treat a file-picker click as artifact delivery. The visible-chat bridge
must preflight and post-check the WeChat surface and emit `WECHAT_LOCKED` or a
send failure if the client did not accept the attachment. If delivery falls
back to an owner-authorized Android phone, verify the target chat list or
mirror row shows a new `[视频]`, `[图片]`, or `[文件]` entry before closing the
task.

LazyEdit import/process and public publish are separate current
request permissions encoded as `stage_permissions` in the route contract. Old
history may provide story or subtitle context, but it cannot authorize LazyEdit
or public posting. For generated-video tasks, MP4 delivery is strict: the file
is sent before the completion text, successful sends are recorded in the task
ledger, and file-send failure keeps the task retryable instead of marking it
done by moving it to `send_deferred_artifact` or `send_deferred_locked`. It returns
plain text or JSON:

For an incoming video with no accompanying text instruction, the transport
only caches the exact same-chat source privately. It does not transcribe,
process, return, or publish the video. A later explicit same-chat text command
promotes that exact source row into the requested routine; old history never
supplies the authorization.

```json
{
  "message": "Finished the render.",
  "files": ["/absolute/path/to/render.png", "/absolute/path/to/model.step"],
  "confirmation": ""
}
```

The sender refuses private paths, decrypted DBs, cookies, browser profiles, chat
logs, unsupported suffixes, missing files, and oversized outputs.

## Media And File Handling

Use media sync before interpreting "this image", "this PDF", or "this video":

```bash
labcanvas wechat media-sync --chat "<CHAT_NAME>" --auto-source --since-minutes 60
```

The sync logic scans WeChat file, video, attach, cache, and temp image folders,
then records candidates in the private mirror. Old XOR `.dat` images can decode
directly; newer V1/V2 image containers need a private image key. If exact source
media is unavailable, the worker asks the user to resend or open the source in
WeChat. It must not borrow files from another group or an older task.

For explicit image/file/video routes, `wechat_task_worker.py` performs a
media-resolution preflight before calling the worker agent. It refreshes
same-chat sync, resolves candidates by current source row, quoted row, MD5/token,
and `create_time` window, then copies usable files into:

```text
output/wechat_worker/<task-id>/source_media/
```

The same preflight writes `media_resolution_manifest.json` and
`media_resolution_manifest.md`. Use the manifest `task_copy_path` files as the
agent's first-choice inputs. Decoded images/videos/PDFs rank above raw WeChat
`.dat` cache files; raw `.dat` is retained only as last-resort evidence.

If the first mirror lookup is empty, the preflight can dry-open the exact source
chat and click likely visible image bubbles once. This forces the official
WeChat client to preview/cache the image before the second media sync. The probe
does not send text and is serialized behind the normal GUI send lock. If the
client still exposes only a tiny/broken cached file, the probe saves screenshot
crops around likely image bubbles and registers them as
`visible_wechat_image_fallback` media candidates.

For raster images, the copied file is also probed with Pillow and OCRed with
local Tesseract when available. OCR output goes to:

```text
output/wechat_worker/<task-id>/image_text/
```

The manifest and worker prompt include the OCR transcript path and preview as
private evidence. The user-facing answer comes from semantic vision: Codex is
called first, and a timeout, failure, or empty result falls back to the
loopback-only OpenAI-compatible API from the sibling LocalLLM project using the
`localllm-vision` alias. The answer should read like a normal explanation of
the image, without OCR labels, reader/model diagnostics, or a fixed caption
template. For an explicit exact transcription request, use the transcript as
supporting evidence, then inspect
the copied image itself or visible fallback crop if OCR is empty. If the
manifest remains empty after sync plus GUI cache probe, stop with a
source-limited missing-media response instead of choosing a nearby old download.

The LocalLLM fallback reads `WECHAT_LOCALLLM_API_KEY`,
`LOCALLLM_API_KEY`, an explicitly configured key file, or the sibling
`../LocalLLM/.env` without putting credentials in argv, logs, manifests, or
chat. `WECHAT_LOCALLLM_API_BASE` defaults to
`http://127.0.0.1:8008/v1`; non-loopback endpoints are rejected.

For exact WeChat video tasks:

```bash
labcanvas wechat autopublish-video --chat "<CHAT_NAME>" --message-local-id 14 --sync --fetch-gui --json
```

`--fetch-gui` opens the official client and clicks the visible video so WeChat
caches the MP4 before the tool copies it to Nutstore AutoPublish.

When that desktop cache path is unavailable and the exact video is visible on
the allowlisted Android chat:

```bash
labcanvas wechat native-save-video \
  --target "<TARGET_KEY>" \
  --task-id "<TASK_ID>" \
  --output-dir "output/wechat_android_intake/<TASK>/native_original" \
  --filename "<MEANINGFUL_NAME>.mp4" \
  --video-tap x,y \
  --json
```

The command always removes its exact phone-side export after successful host
verification. It does not offer a recording fallback.

For read-only Shipinhao summaries where the shared media URL expired, keep the
exact card visible and run `shipinhao_gui_audio_capture.py` with object ID,
title, author, and distinctive identity terms. The helper uses the same GUI
serialization lane, records only the matching native player stream, and stops
when the feed advances. Its private `verified-capture.json` is automatically
consumed by the next worker preflight. Keep raw audio, signed URLs, hashes, and
identity screenshots private and uncommitted; the worker may return the
source-scoped reader-facing transcript when the current intake contract asks
for it.

These source defaults are profile-independent. An exact Gongzhonghao article
in any monitored WeChat or WeCom chat enters read-only full-text recovery and
concise analysis. An exact Shipinhao card or share URL enters verified MP4
download, audio transcription, concise summary, and return delivery. Per-chat
focus still shapes the answer, but cannot turn either source into title-only
chat or infer public publication. Ordinary bare MP4 uploads remain passive
save-only unless the current same-chat text explicitly asks for more.
When current messages arrive consecutively, the resolver treats that bounded
coalesced burst as one source batch: a later instruction retains the exact
Shipinhao card/link from the row immediately before it, without searching old
chat history for a substitute source.

If desktop WeChat is unavailable and the source row came from the allowlisted
Android intake, the worker invokes `wechat_android_source_recovery.py` instead
of asking for a pasted link. It returns to the exact chat after audio-helper
prewarm, opens the exact native article/Finder card, and emits only a
source-scoped manifest. Article cards copy and verify their canonical link.
Finder cards capture muted system audio plus screen video, reject identity
changes, and trim repeated playback only with matching audio and visual proof.
The worker may send a bounded playable H.264/AAC copy while retaining the full
verified capture privately. This mobile lane supplements rather than deletes
the desktop lane.

For bot-sent/generated videos, `wechat_task_worker.py` runs the exact
message-local-id cache path first. If that fails, it checks the same-chat
artifact ledger using only the current/source video row `md5`/`length` tokens,
not every old video token in recent history. A verified match is copied into
Nutstore AutoPublish with a `_COMPLETED` name, and the source task
request/result summary is included only as LazyEdit correction and metadata
context. No current/source-row MD5 or length match and no exact WeChat cache
means no publish.

Silent or nearly silent videos are allowed. If LazyEdit records an empty
transcript and `burn=skipped`, continue to metadata, cover extraction, publish
queue submission, and terminal platform verification. Do not block forever on
subtitle burn, and do not replace the exact current video with an older one.

If a code or routine fix makes a stored worker result stale, requeue the same
source-scoped task through the reusable reprocess path:

```bash
labcanvas wechat worker reprocess "<TASK_ID>" "source resolver fixed" --send
```

This preserves the original request, source, route decision, and context, while
clearing stale preflight/result/send state so the normal worker owns the retry.

## GUI Send Path

Dry-run target opening:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  --display :97 \
  --targets-file agentic_tools/wechat_gui_agent/.private/test-targets.local.json
```

Live send:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  --display :97 \
  --targets-file agentic_tools/wechat_gui_agent/.private/test-targets.local.json \
  --send
```

The sender writes before/opened/composed/sent screenshots plus a
`send_manifest.json`. It should be the only code path that presses Enter in the
WeChat composer.

## Browser Assist And Human Approval

If a task hits login, CAPTCHA, consent, download confirmation, payment,
purchase, deletion, public posting, or other irreversible actions, open a
human-assist browser or ask for approval:

```bash
labcanvas wechat browser-assist --url "https://example.com/download" --json
labcanvas wechat approve <task-id> --note "continue"
labcanvas wechat reject <task-id> --note "do not continue"
```

Do not try to bypass account protections. The worker should return
`waiting_confirmation` for risky actions.

For WeChat official-account articles, direct HTTP may return `环境异常` or
`完成验证后继续访问`. The research worker must run
`scripts/wechat_source_recovery.py`, which uses a mobile WeChat user agent,
extracts `#js_content`, and writes ignored article evidence plus a private cache.
On a remaining gate, the worker uses exact-title/account/identity reconstruction
queries and authoritative public sources. It does not open/focus a browser or
request human verification for this read-only path. Login/CAPTCHA approval rules
still apply to authenticated or write actions.

## Group And Alias Operations

These are real WeChat actions and can notify people. Use dry-runs and visual
confirmation first.

```bash
labcanvas wechat create-group --member-query "<CONTACT>" --name "<GROUP>" --dry-run
labcanvas wechat rename --chat "<CHAT_NAME>" --name "<NEW_NAME>" --dry-run
labcanvas wechat alias --chat "<CHAT_NAME>" --name "LazyingArt" --dry-run
```

Only remove `--dry-run` after the target and member list are visually correct in
the noVNC desktop.

## Skills And Future Agent Behavior

The Codex skill is:

```text
/home/lachlan/.codex/skills/wechat-labcanvas-chatops/SKILL.md
```

The shareable LazySkills copy is:

```text
../LazySkills/skills/wechat-labcanvas-chatops/SKILL.md
```

When changing WeChat automation behavior, update the repo docs and sync the
skill. The skill should always remind future agents to:

- use the LabCanvas CLI and existing scripts instead of ad hoc GUI commands;
- keep secrets and decrypted DBs private;
- use one config/state file per chat;
- preserve route contracts, routine contracts, and title guards;
- source-limit media/files to the same chat and exact source rows;
- use browser assist or approval for protected or irreversible steps.

## Test And Verification Commands

Run focused checks after changing WeChat code:

```bash
PYTHONPATH=src python -m unittest \
  tests.test_wechat_gui_send \
  tests.test_wechat_direct_chatops \
  tests.test_wechat_task_worker \
  tests.test_wechat_media_sync \
  tests.test_wechat_memory

python -m py_compile \
  agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops.py \
  agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py

labcanvas wechat health --json
tmux list-windows -t labcanvas-wechat
```

After a code change, reload live monitors:

```bash
labcanvas wechat hold reload-workers
```

Then inspect fresh logs under `output/wechat_gui_agent/YYYY-MM-DD/`.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| noVNC is blank | Run `labcanvas wechat desktop keep-awake`; check `labcanvas wechat status`. |
| Login expired | Stop sends and ask the user to approve login in noVNC or on phone. |
| Wrong search row opens | Add `fallback_clicks` or use a verified `open_click`; keep OCR title guard enabled. |
| Direct DB is stale for an inactive group | Keep the `chat-sync` supervisor window running. It dry-opens configured chats with `wechat_gui_send.py` without `--send`, which prompts Linux WeChat to materialize new rows for the direct monitors. If dry-open logs show `WECHAT_SEND_TIMEOUT`, raise `WECHAT_CHAT_SYNC_TIMEOUT` or `WECHAT_CHAT_SYNC_GUI_SEND_MAX_SECONDS`. |
| Title OCR fails | Prefer native popup title matching; otherwise add stable `expected_title_aliases`, inspect title crop screenshots, and keep the default minimum title wait/retry window. For opted-in targets with `allow_title_guard_fallback`, a visible chat-list row match may proceed when emoji-heavy header OCR is noisy and no search/AI surface is detected. Blank OCR (`OCR=''`) is retryable as `title_guard_blank`; nonblank wrong titles fail closed. Wrong popups are closed before fallback clicks continue. |
| Backend done but reply failed | Fix the sender/title guard, then run `python3 agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py --resend <task-id>` so work is not rerun. |
| WeChat is locked, at entry, or sender is busy | Do not bypass the lock or run parallel clickers. `WECHAT_LOCKED`, `WECHAT_ENTRY_REQUIRED`, `WECHAT_SEND_BUSY`, `WECHAT_SEND_TIMEOUT`, and blank title-guard OCR become `send_deferred_locked` with `send_deferred_reason`, then the watchdog/worker flusher retries after unlock, Enter Weixin, or the active send finishes. GUI subprocess timeouts kill the whole process group so clipboard/helper children cannot hold the lane. |
| Composer stays empty | Check for stale clipboard owners and sender screenshots. The GUI sender uses a bounded `xclip -selection clipboard -loops 1` owner plus `xdotool --clearmodifiers ctrl+v`; if paste fails, inspect `*-composed.png` before increasing retries. |
| Multi-file artifact send times out | Keep the worker and GUI sender alarms aligned. The worker sets `WECHAT_GUI_SEND_MAX_SECONDS` from `WECHAT_WORKER_SEND_TIMEOUT_SECONDS`; raise `WECHAT_WORKER_GUI_SEND_MAX_SECONDS` only for slow remote desktops or large attachments. |
| Android cannot find a long mixed-language chat title | Inspect normal and `*-ocr-enhanced` evidence. The native sender retries with grayscale contrast-enhanced OCR and rescales its row coordinates; add an authoritative `expected_title_aliases` entry only when the enhanced exact title is still genuinely ambiguous. Never use a substring-only live match. |
| Text/source artifact send fails | Required CAD/PCB/media/download artifacts still use the deferred sender. Ordinary `.md`/report notes from link summaries should stay local unless explicitly requested or marked high-value by the worker. Use `WECHAT_WORKER_SEND_FILES=0` only for a diagnostic path-only run. |
| Task replies to wrong chat | Treat as a bug; check route contract, send target, state path, and title guard logs. |
| File missing | Run same-chat media sync and verify exact local/server ids before retrying. |
| Worker hangs | Check queue status, worker log, and Codex session registry; stale claims are reclaimable. |
| WeCom missing-window repair always times out on `wecom_tmux.lock` | Confirm the lease outlives both the 45-second action wait and 180-second autostart repair bound. The supervisor must acquire mutations through its parent `flock --close` wrapper so a new tmux server cannot inherit the lock. Preserve the old locked inode before replacing it; then let `wecom_autostart.sh` recreate only missing windows. |
| Scheduled report exists locally but did not arrive | Inspect trigger, artifact, transport, and delivery-ledger state separately. Recover the exact stored artifact without rerunning research. For WeChat, let the watchdog complete normal phone confirmation; for WeCom, ensure the Android relay is foregrounded and outbound delivery is not waiting behind passive polling. |
| Risky action requested | Mark `waiting_confirmation` or open browser assist; do not bypass protections. |

## Non-Goals

Do not add methods that recover credentials, intercept encrypted traffic, bypass
WeChat login, forge protocol requests, evade CAPTCHA, mass-message people, or
scrape unrelated/private chats. These are outside the LabCanvas control model
and should be refused or redirected to a manual consented path.
