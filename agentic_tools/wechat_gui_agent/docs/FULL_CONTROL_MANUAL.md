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

## Control Layers

```text
WeChat official Linux client on Xvfb/noVNC
  -> encrypted local DB/cache under xwechat_files
  -> private decrypt refresh cache
  -> direct per-chat monitors
  -> mirror + memory + media databases
  -> fast router agent
  -> JSONL worker queue
  -> Codex/LabCanvas worker tools
  -> guarded GUI sender with OCR title check
  -> WeChat message/file reply
```

The system intentionally keeps read, reasoning, worker execution, and send
separate. This makes crosstalk, duplicate replies, and wrong-chat sends easier
to detect and block.

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
labcanvas wechat queue --json
labcanvas wechat worker once --send
labcanvas wechat approve <task-id> --note "approved"
labcanvas wechat reject <task-id> --note "stop"
labcanvas wechat media-sync --chat "<CHAT_NAME>" --auto-source
```

The web studio exposes the same backend through `/api/wechat/status` and
`/api/wechat/action`. The UI can start the stack, open noVNC, process one worker
task, approve/reject the newest waiting task, and send a short explicit message.
Do not add browser-only behavior that bypasses the CLI scripts.

## Runtime Sessions

`agentic_tools/wechat_gui_agent/scripts/wechat_stack_tmux.sh start` starts two
tmux sessions:

| Session | Purpose |
| --- | --- |
| `labcanvas-wechat` | WeChat desktop, decrypt refresh, one direct monitor per chat, worker, media sync, and chat materialization sync. |
| `labcanvas-web-wechat` | LabCanvas web control panel for status and manual actions. |

Within `labcanvas-wechat`, `wechat_supervisor_tmux.sh` creates:

| Window | Script | Role |
| --- | --- | --- |
| `desktop` | `wechat_virtual_desktop.sh` | Xvfb/noVNC WeChat desktop and keep-awake. |
| decrypt pane | `wechat_decrypt_refresh_loop.sh` | Incremental private DB refresh. |
| `direct-*` | `wechat_direct_chatops.py --loop --send --no-decrypt` | Fast per-chat monitor. |
| `worker` | `wechat_task_worker.py --loop --send` | Slow backend task executor. |
| `media-sync` | `wechat_media_sync_loop.sh` | Background media/file cache import. |
| `chat-sync` | `wechat_chat_sync_loop.py --loop` | Dry-opens configured chats so inactive Linux WeChat conversations materialize fresh DB rows. Use `WECHAT_CHAT_SYNC_PRIORITY` to visit important groups first. |

Use `hold reload-workers` or `stack restart` after code/config changes. These
keep the WeChat GUI alive and respawn only monitors, worker, media sync, and web
processes. Use `restart-all` only when it is acceptable to close and reopen
WeChat, which may require phone confirmation.

## Script Inventory

| Script | Main use |
| --- | --- |
| `wechat_virtual_desktop.sh` | Launch WeChat on display `:97`, VNC, noVNC, and X11 keep-awake. |
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
| `wechat_memory.py` | Structured local inbox/memory tables for notes, todos, links, and summaries. |
| `wechat_mirror.py` | SQLite evidence log for GUI sends, reads, screenshots, and direct messages. |
| `wechat_codex_sessions.py` | Per-chat fast/worker Codex session registry. |
| `wechat_browser_assist.py` | Open a local browser in the isolated desktop for login/CAPTCHA/download help. |
| `wechat_group_create.py` | Open/execute group creation after visual confirmation. |
| `wechat_group_admin.py` | Best-effort group rename and in-group alias changes. |
| `wechat_restart_loop.sh` | Restart wrapper used by tmux supervisor panes. |
| `wechat_supervisor_tmux.sh` | Main WeChat tmux supervisor. |
| `wechat_stack_tmux.sh` | WeChat supervisor plus LabCanvas web panel. |

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
```

Before a worker task is queued, the fast monitor converts the route decision
into a named routine from `wechat_routines.py`. The task stores `task.routine`.
For hard artifact requests, deterministic guards override a bad `chat_only`
route: if the current coalesced request asks to send/save/download/copy a file,
video, image, audio, PDF, or generated artifact, the task is queued for the
worker even when the route model misclassifies it as chat.
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
in order, verify non-VIP `Seedance 2.0 Fast`, generate/download the MP4, verify
with `ffprobe`, and send the verified MP4 back to the source WeChat chat. A
submitted Xiaoyunque job stays as `generation_waiting` and is checked by short
status-probe cycles; the next poll is based on page state rather than a fixed
long timeout. If the agent times out before returning monitor state, the worker
discovers the active Xiaoyunque `thread_id` through Chrome CDP and resumes from
the browser state instead of closing the task.

For required artifact delivery, file/video send success is not enough to mark a
task done if the follow-up text or confirmation send fails. Keep
`sent_file_paths`, store `post_artifact_send_errors`, and leave the task in
`send_deferred_locked` when the failure is `WECHAT_LOCKED`, entry-required,
busy, or timeout. The next flush should skip already sent files and retry only
the missing user-facing text/confirmation.

LazyEdit import/process and public publish are separate current
request permissions encoded as `stage_permissions` in the route contract. Old
history may provide story or subtitle context, but it cannot authorize LazyEdit
or public posting. For generated-video tasks, MP4 delivery is strict: the file
is sent before the completion text, successful sends are recorded in the task
ledger, and file-send failure keeps the task retryable instead of marking it
done by moving it to `send_deferred_artifact` or `send_deferred_locked`. It returns
plain text or JSON:

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

For exact WeChat video tasks:

```bash
labcanvas wechat autopublish-video --chat "<CHAT_NAME>" --message-local-id 14 --sync --fetch-gui --json
```

`--fetch-gui` opens the official client and clicks the visible video so WeChat
caches the MP4 before the tool copies it to Nutstore AutoPublish.

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
| Direct DB is stale for an inactive group | Keep the `chat-sync` supervisor window running. It dry-opens configured chats with `wechat_gui_send.py` without `--send`, which prompts Linux WeChat to materialize new rows for the direct monitors. |
| Title OCR fails | Prefer native popup title matching; otherwise add stable `expected_title_aliases`, inspect title crop screenshots, and keep the default minimum title wait/retry window. Blank OCR (`OCR=''`) is retryable as `title_guard_blank`; nonblank wrong titles fail closed. Wrong popups are closed before fallback clicks continue. |
| Backend done but reply failed | Fix the sender/title guard, then run `python3 agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py --resend <task-id>` so work is not rerun. |
| WeChat is locked, at entry, or sender is busy | Do not bypass the lock or run parallel clickers. `WECHAT_LOCKED`, `WECHAT_ENTRY_REQUIRED`, `WECHAT_SEND_BUSY`, `WECHAT_SEND_TIMEOUT`, and blank title-guard OCR become `send_deferred_locked` with `send_deferred_reason`, then the watchdog/worker flusher retries after unlock, Enter Weixin, or the active send finishes. GUI subprocess timeouts kill the whole process group so clipboard/helper children cannot hold the lane. |
| Text artifacts trigger file picker issues | Keep `.md`/`.txt`/`.json` as saved paths in the message; use `WECHAT_WORKER_SEND_FILES=0` to disable attachment sends or `WECHAT_WORKER_REQUIRE_FILE_SEND=1` for strict delivery. |
| Task replies to wrong chat | Treat as a bug; check route contract, send target, state path, and title guard logs. |
| File missing | Run same-chat media sync and verify exact local/server ids before retrying. |
| Worker hangs | Check queue status, worker log, and Codex session registry; stale claims are reclaimable. |
| Risky action requested | Mark `waiting_confirmation` or open browser assist; do not bypass protections. |

## Non-Goals

Do not add methods that recover credentials, intercept encrypted traffic, bypass
WeChat login, forge protocol requests, evade CAPTCHA, mass-message people, or
scrape unrelated/private chats. These are outside the LabCanvas control model
and should be refused or redirected to a manual consented path.
