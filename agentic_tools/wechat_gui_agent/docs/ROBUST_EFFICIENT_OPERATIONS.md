# Robust And Efficient Operations

This guide is the system contract for keeping LabCanvas WeChat automation
durable, low-cost, and predictable. Use it when changing monitors, workers,
media sync, generated-video workflows, LazyEdit publishing, or GUI sending.

## Operating Model

Treat WeChat as a communication bridge, not as the executor. A WeChat message
should feel like a message sent into the same interactive Codex thread for that
chat. The durable system is:

```text
official WeChat client
  -> local decrypted mirror
  -> per-chat fast monitor
  -> reused per-chat route Codex session
  -> source context and routine contract
  -> JSONL worker queue
  -> reused per-chat Codex worker session
  -> deterministic routine probes and gates
  -> artifact delivery gate
  -> guarded GUI sender
```

The fast monitor should be responsive and cheap. It reads local DB/files,
coalesces bursts, saves memory items, and asks the route agent whether this is
normal chat or backend work. Keyword checks remain safety fallbacks, not the
capability map. The worker owns tool execution, artifact creation, long browser
jobs, and final deliverables. Deterministic code should stay narrow: transport,
source isolation, safety gates, known routine probes, wait-state polling, retry,
and verified send-back.

In `agent_bridge_mode`, the route agent is trusted for safe `chat_only`
decisions even when a keyword heuristic would have enqueued work. Backend tasks
carry `agent_bridge_mode=true`, and later same-chat messages append as
interruptions to the active task so the reused worker session can adjust plan,
story, prompt, media references, or publish scope like an interactive Codex
conversation.

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
Routines are callable contracts and cheat sheets for mature work such as
LazyEdit, Xiaoyunque, CAD/PCB, media sync, PDFs, and artifact sending. They
should speed the agent up, not replace agent reasoning.

The worker must not dump the whole queue row into the backend prompt. Build a
bounded task packet containing the current request, exact source IDs, at most 12
recent same-chat rows, interruptions, route/routine state, and readable context
paths. Strip raw Finder XML, signed media URLs, cookies, keys, hashes, and unused
media paths. This keeps the resumed agent focused while deterministic routines
retain the full private evidence on disk.

## Official WeCom Transport

WeCom AI bot DMs and internal WeCom groups may enter the same routine
orchestrator through `agentic_tools/wecom_agent/`. This is an alternate
transport, not a second agent runtime:

```text
official WeCom WebSocket -> wecom_ingest.py -> private queue
  -> run_task_orchestrator -> same per-chat backend/session rules
  -> authenticated localhost send API -> official WeCom text/media send
```

Use the official `@wecom/aibot-node-sdk` long connection by default. It needs
only BotID and Secret and does not expose a public callback endpoint. Keep each
WeCom DM/group in its own hashed chat key. Incoming encrypted URLs/AES keys are
ephemeral; exact decrypted files go to ignored source-scoped output folders and
enter the bounded worker packet as `preflight.wecom_media`. Never run personal
WeChat DB/GUI media recovery for those files.

The local proactive-send endpoint must remain on `127.0.0.1`, require its
private bearer token, refuse unseen chat IDs, and keep an idempotent per-task
delivery ledger. Bot credentials, raw chat/user IDs, owner pairing, known-chat
state, and message history stay under `agentic_tools/wecom_agent/.private/`.
Default access is first-owner pairing; organization-wide access must be an
explicit operator choice. Existing personal-WeChat groups are outside this API
and continue using the GUI/database bridge.

WeCom boot recovery is independent from the personal-WeChat stack. Install
`agentic_tools/wecom_agent/scripts/install_wecom_autostart.sh` as the lingering
user service `labcanvas-wecom-autostart.service`. Its only job is to call the
idempotent WeCom tmux repair contract on startup and at a low-frequency health
interval. It must:

- preserve the same private queue, SQLite state, Wine prefix, noVNC display,
  delivery ledgers, and per-chat agent sessions across reboot;
- independently restore `gateway`, `worker`, `daily`, `knowledge`, optional
  official external transport, `wecom-client`, and `external-gui` windows;
- use the tmux mutation lock so the general `create_tmux_session.sh` fallback
  and the dedicated service may start concurrently without duplicate windows;
- leave healthy windows and the authenticated GUI process untouched;
- never enter account-switch/QR login, send a message, replay an old queue, or
  bypass Tencent authentication as part of boot repair.

The Wine client supervisor owns Xvfb, x11vnc, websockify, noVNC, native window
fitting, and bounded persisted-profile relaunch. If authentication is no longer
valid, boot recovery may expose the existing localhost noVNC desktop for normal
owner action, but it must not manufacture or automate a login.

For the restricted LabAgent research group:

- The paired owner enrolls the exact group; trusted members then share the
  private LazyResearch worker's research, drawing, and design routines.
- A scientifically valuable idea uses a two-track response. The route agent
  promptly sends a concise, useful preliminary answer, explicitly provisional
  when evidence has not yet been checked. In parallel it queues one durable
  source-grounded task. Mechanism questions, hypotheses, experimental-design
  problems, literature comparisons, roadmaps, and quoted scientific follow-ups
  normally require a polished LaTeX PDF even when the sender did not type
  `PDF`; routine factual questions and small talk do not.
- A deep report is evidence work, not a longer knowledge point. It must cite
  traceable primary or authoritative sources, distinguish direct evidence,
  indirect evidence, hypotheses, and unknowns, state limitations, and provide
  actionable experiments or decisions. The fast answer and deep task retain
  the exact sender, chat, current text, quote preview, and bounded same-chat
  context.
- The delivery gate requires at least two traceable sources in a recovered deep
  report and targets three or more primary/authoritative sources when the
  literature permits. A PDF without source evidence is not completion.
- Video publication and other public posting are disabled. Other dangerous
  requests are assessed by the route agent and retain the existing approval
  gates.
- `<interest> #daily` stores one private subscription row per member and
  accumulates distinct interests in that row. `status #daily` inspects it and
  `off #daily` disables only that member. At 06:00 `Asia/Hong_Kong` by default,
  the local scheduler enqueues one `research_summary` job per active member
  subscription. Interests belonging to that member are combined, but jobs from
  different members remain separate and carry deterministic sequence metadata;
  the single worker executes them one by one. Idle checks spend no model quota.
  A newly added interest also queues one idempotent initial report immediately
  without consuming the scheduled report. Repeated interests do not create
  another initial run. The prefix syntax remains a compatibility alias.
- Daily reports return a concise digest and requested Markdown/PDF or editable
  figure artifacts through the source-scoped WeCom send gate. Author a polished
  LaTeX source, compile with XeLaTeX and the restrained Nature-style header, and
  inspect rendered pages for missing glyphs, blank pages, clipping, overflow,
  and unreadably dense text before delivery. Daily tasks have no
  pending or deferred-send queue expiry, including legacy rows restored through
  artifact-only reprocessing; a per-turn watchdog is only a hung-process guard.
- If a daily/research agent writes a substantive exact-task Markdown report and
  source PDFs but loses its final response, recover from that task directory,
  compile the report PDF, and require one source-chat delivery. Exclude routine
  contracts, manifests, and notes; never salvage another task's artifacts.
- If the report already has an exact-name sibling PDF rendered from its TeX
  source, recovery sends that designed PDF. Generic Markdown-to-PDF compilation
  is fallback only and must not replace a polished report or drop its figures.
- Send only that polished PDF to the group by default. Keep Markdown, TeX,
  evidence papers, and rendered-page audits in the private task directory;
  deliver source files only when the current request explicitly asks for them.
- `route_decision.require_file_delivery` and
  `execution_contract.required_artifacts` are authoritative delivery gates.
  Reprocessing preserves the execution contract. A report task cannot become
  `done` merely because its chat summary was sent; the PDF needs a verified
  transport ledger entry. Use artifact-only reprocessing for supplemental or
  backfill delivery so completed research is not rerun and the summary is not
  repeated.
- Maintain the private per-member knowledge store with
  `wecom_member_knowledge.py`. Inbound attachments are archived at ingest;
  completed task artifacts and structured ideas/insights are indexed by the
  `knowledge` tmux window. Ownership is the stable hashed member key plus exact
  chat, with message/task provenance and file checksums. Never merge records
  because display names look similar.
- Only a bounded exact-member/exact-chat memory view may enter route or worker
  prompts. Keep the SQLite database under `agentic_tools/wecom_agent/.private/`
  and file copies under ignored `output/wecom/member_knowledge/`. Do not commit,
  send, or expose database internals, raw user IDs, archive hashes, or another
  member's memory. Explicit `#idea`, `#insight`, `#intuition`, `#interest`,
  `#hypothesis`, and `#note` markers are deterministic; agent-derived memory
  must still be durable, source-grounded, and free of credentials or speculative
  profiling.
- The knowledge indexer must be cheap while idle. Use the message-table
  high-water row and queue file signature; do not rescan full history or spend a
  route/worker turn merely to maintain the index. `labcanvas wecom knowledge
  status|sync|search|export` is the operator interface.

### External WeCom GUI Relay

When Tencent does not grant the tenant's official external-group `msg`
permission, `wecom_gui` may bridge one explicitly allowlisted group through the
isolated WeCom Wine client. It is still a WeCom transport and must never reuse
personal-WeChat database, media, search, sender, or fallback paths.

- Read through the durable cursor interface, not ad hoc screenshots from a
  worker: `GET /v1/messages?chat_id=gui:<name>&after=<cursor>&limit=<n>`.
- Send through the authenticated `/v1/send` interface with a stable `task_id`.
  Combined text and files remain in one serialized GUI transaction.
- Seed the first visible viewport and do not replay it after restart. Refuse an
  ambiguous viewport rather than converting old OCR into new tasks. Move the
  message pane to its live tail before each active poll. The normal loop first
  takes a passive, quantized screenshot signature that excludes the composer.
  It touches the client only when the conversation list/chat tail changes or a
  bounded three-minute safety rescan is due. Passive checks spend no model
  quota and inject no keyboard or pointer events.
- Read each visible inbound text bubble with WeCom's native Copy command and
  Wine `CF_UNICODETEXT`. Use OCR only to locate the bubble or as a bounded
  fallback; never replace a successful native copy with OCR output.
- Treat native context-menu cleanup as part of the read transaction. Dismiss
  the popup after every copy attempt and again before outbound compose so a
  stale overlay cannot consume later paste or Send clicks.
- Preserve exact text in `request` and `original_request`. A route-agent plan is
  advisory and must not rewrite names, capitalization, or digits. For an
  uncertain scientific identifier, the worker checks capitalization and
  letter/digit variants against authoritative databases and primary literature
  before deciding whether one concise clarification is actually necessary.
- Match one exact configured chat title. Search is disabled by default.
- Multiple allowlisted WeCom groups share one serialized desktop only; each
  keeps its own cursor, source ID, hashed chat key, agent session, task state,
  and delivery ledger. Never reuse a result or cursor across group names.
- When enabled explicitly, GUI search is an exact-title navigation fallback,
  not content search. Verify the opened title before reading or sending.
- The official CLI guard must probe `msg_permission` before reporting
  `bridge_running`. Use the GUI relay when status is
  `message_permission_unavailable`; do not keep polling an unusable API.
- The Wine client supervisor may restart only the normal persisted-profile
  client. It must never enter account-switch mode after a crash or hidden
  layered window. Opening a fresh QR login is a separate explicit operator
  action, because it can invalidate a reusable authenticated session.
  Limit automatic client starts to three attempts per hour, followed by a
  30-minute quiet period. A continuously healthy hour replenishes the budget;
  a short crash/relaunch cycle does not.
- Verify Unicode composer readback before a text send. For files, require the
  exact filename in WeCom's native picker. Because WeCom visually truncates long
  attachment labels, verify the composer/history attachment using the proven
  isolated-picker identity plus its visible filename prefix and a newly added
  card before updating delivery state. Native picker selection only stages an
  artifact; the separate composer Send is mandatory. Keep select/paste or
  select/copy in one key transaction; split key processes are not reliable
  under Wine.
- A device-security or QR challenge can appear after the native file picker,
  even when the chat was ready at transaction start. Re-check authentication
  while waiting for the sent file card. QR-login and explicit security-
  verification screens always fail closed. A persistent
  `device_environment_abnormal` composer warning is narrower: when
  `allow_verified_file_send_during_device_warning` is enabled, the relay may
  attempt files only, through the exact native picker and new-card history
  verification. Text, polling, and unverified attachment sends remain blocked.
  If the verified file route does not complete, classify it as
  `WECOM_GUI_AUTH_REQUIRED` and preserve
  `send_deferred_reason=wecom_auth_required` for idempotent recovery.
- The first detected security challenge places the GUI transport in a durable
  five-minute input quarantine. During quarantine, polling and text sends are
  screenshot-only/fail-closed. The sole exception is the verified file-only
  route above; successful delivery still requires exact filename identity and
  a newly visible chat card. After the warning disappears, require an
  uninterrupted one-minute passive stabilization window before exact-chat
  polling and text delivery resume.
- Pace ordinary text attempts at least 12 seconds apart and file attempts at
  least 30 seconds apart. Wait inside the serialized transaction instead of
  returning an error that encourages retries against the desktop. After a
  reconnect, all allowlisted chats must remain ready for two minutes before
  recovering at most one prior outbox delivery.
- Treat the external WeCom relay as an observable closed loop: authenticated
  client, exact-chat readiness, durable ingest, worker result, verified
  compose/send, and delivery ledger. `login_required` and
  `chat_verification_pending` are not send-ready states.
- Use X11/VNC input for ordinary WeCom navigation, composer select/copy/paste,
  and text entry. Win32 `SendInput` for the composer is disabled by default and
  requires explicit private configuration. The one retained Wine exception is
  the file-picker `More` toolbar click, which uses a controlled Win32 helper
  because the X11 click is ignored. Do not post arbitrary
  native window messages or send blind `Escape` cleanup. The helper may close
  only exact stale WeCom picker/document/error modal classes after an interrupted
  file send. Detect QR/login/abnormal-device screens before input, fail closed,
  and let the persistent client retain ownership of its authenticated profile.
- Before each WeCom exact-chat poll, close only stale same-process native file
  pickers, document hosts, file-error reminders, and `SearchResultWindow2`.
  These overlays can visually leave the target chat selected while blocking
  title verification; cleanup must resume ingestion without restarting or
  logging out the authenticated client. Never approximate the search-layer
  close button with the adjacent main-toolbar `+`; that opens `Start Group
  Chat`, which is also an exact allowlisted stale-window cleanup target. Wine
  may keep its wrapper HWND marked disabled after a modal closes, so use exact
  post-cleanup chat-title verification instead of that flag as the readiness
  gate.
- WeCom transport should feel conversational: coalesce adjacent messages from
  one sender and let the low-effort route agent return one natural response to
  ordinary comments as well as requests. Do not use silence merely because a
  human message has no explicit command, and do not reply to proven self-output.
  Suppress exact same-chat WeCom GUI text repeated within 90 seconds before the
  route turn; sender OCR instability must not create duplicate tasks or replies.
- Keep GUI config, cursors, events, screenshots, and delivery ledgers under
  ignored `agentic_tools/wecom_agent/.private/` paths.

The stable interface and recovery commands are documented in
`agentic_tools/wecom_agent/docs/GUI_RELAY_INTERFACE.md`.

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
- Self-message ownership is evidence-first. Before applying prose heuristics,
  compare a same-account DB row with recent successful outbound mirror records
  (`sent`, `done-sent`, or `waiting-confirmation-sent`) for the same chat and a
  bounded time window. An exact match is `self_outbound_echo` and must never be
  routed. Do not accept the monitor's own `synced` record as send evidence,
  because doing so would suppress legitimate same-account mobile commands.
- `NO_REPLY` is an internal control signal, never chat content. Treat case,
  whitespace, underscore/hyphen, Markdown fences, `CHAT:`/`ACK:` wrappers, and
  appended explanations such as `NO_REPLY: this is an echo` equivalently.
  Suppress it at fast-response parsing, worker-result parsing, the send API, and
  the final GUI sender. A worker that returns this signal without explicit
  artifacts finishes silently as `done-no-reply`; it must not create a deferred
  outbox item or another task. Explicit files still follow the normal artifact
  delivery gate, but the control text itself is never sent.
- Completion/status messages from the bot, including `Published OK: ...`, must
  never become new backend tasks. If the route agent says a message is bot
  completion/status with no new backend work, do not let keyword fallback
  override it into a publish route.
- Self-generated failure diagnostics are also bot output. Messages such as
  `Worker failed via codex: ...`, `codex wrapper error: ...`, missing-Codex
  launcher errors, or route-agent failure notices must be ignored as self
  replies, not treated as new research or repair tasks. Infrastructure failures
  are terminal diagnostics for that attempt and must not trigger higher-effort
  model escalation.
- Worker and route sessions must resolve a real Codex binary inside tmux,
  conda/venv, and restart-wrapper environments. Prefer explicit
  `WECHAT_CODEX_BIN`/`CODEX_BIN`, then concrete nvm installs such as
  `~/.nvm/versions/node/*/bin/codex`, before generic `PATH` wrappers like
  `~/bin/codex`. A wrapper that cannot find the real Codex binary should fail
  visibly without crashing the monitor loop.
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
  when available). OCR is private supporting evidence, not a reply template. The transcript is written under
  `output/wechat_worker/<task-id>/image_text/`, added to the manifest, and
  injected into the worker prompt as evidence for image-reading tasks. If WeChat
  exposes only a broken or tiny cached image, the GUI probe also saves visible
  screenshot crops as `visible_wechat_image_fallback` candidates.
- For chat-level image backfill, use
  `agentic_tools/wechat_gui_agent/scripts/wechat_image_backfill.py --config <direct-config> --limit N`.
  It reads recent direct monitor image rows, source-scopes each row by
  `local_id`/media tokens/time window, selects one best non-thumbnail candidate,
  and runs the same Codex image reader (`WECHAT_IMAGE_READ_MODEL=gpt-5.5`,
  `WECHAT_IMAGE_READ_EFFORT=low`) plus OCR before optionally sending one
  natural content-aware reply back to the originating chat with `--send`. A
  one-image backfill sends the semantic answer directly; a multi-image backfill
  uses only simple image numbering and never exposes local IDs, dimensions,
  model names, checksums, or `Visible text / Image caption / Notes` labels.
  Prefer decoded
  `msg/attach/.../Img/<md5>.jpg` originals over `cache/.../Bubble/*_b` previews;
  Bubble previews can be gray placeholders and must not win when a readable
  source attachment or thumbnail exists. GUI screenshot crop fallback is opt-in
  only (`--allow-visible-crop-fallback`) because the visible chat can move and
  capture later bot replies instead of the source image.
- Bare uploads with no explicit instruction are still work: route them to
  `file_intake`, sync/copy the exact source into
  `output/wechat_worker/<task-id>/intake/`, and record metadata plus checksum.
  Raster images are automatically read with Codex vision
  (`WECHAT_IMAGE_READ_MODEL=gpt-5.5`, `WECHAT_IMAGE_READ_EFFORT=low`) and OCR.
  The vision turn must respond like a normal multimodal Codex conversation:
  explain what the image shows or means, using nearby same-chat context when
  useful. Do not send raw OCR blocks, reader/model diagnostics, dimensions,
  checksums, or a fixed caption schema unless the user explicitly asks for
  exact transcription or diagnostics. ZIP, RAR, 7z, Word, PDF, and text files must be
  passed through the bounded read-only document reader. When readable evidence
  exists, resume the exact-chat agent and provide a concise natural preliminary
  summary; do not short-circuit into a checksum receipt. An explicit user
  instruction controls deeper summary, extraction, comparison, translation, or
  conversion. Unsupported, encrypted, oversized, or missing files fail closed.
  The file-intake preflight must prefer `media_resolution.copied[*].task_copy_path`
  over broad "Recent synced files" appendices so old images/files cannot be
  mistaken for the new source upload. A typed attachment `title` and
  `extension` are an identity contract: candidates must match the exact
  filename/local ID and declared suffix. If no match exists, return no
  candidate; never rank a nearby image or another recent file as a fallback.
  For native file cards that are not cached yet, guarded GUI intake opens only
  the exact source chat, matches the visible filename, downloads it through the
  official client, and then repeats source-scoped resolution. A complete exact
  native-cache file is reused without clicking the card again.
- Archive handling is inventory/extraction only: reject traversal paths,
  symlinks, encrypted members, executables, excessive member counts/sizes,
  excessive nesting, and suspicious compression ratios. Never execute archive
  members or Office macros. RAR/7z inventory uses `7z`; RAR extraction may use
  read-only `bsdtar` when the installed 7z build can list but cannot decompress
  the archive method. Only supported document members are extracted for
  bounded recursive reading. DOCX is read from XML; PDF uses `pdftotext` and a
  bounded `pdftoppm` + Tesseract fallback for scanned pages. Full extracted
  text stays in ignored task artifacts and only a short preview enters queue
  JSON; the worker must open `agent_context_path` before answering.
  Treat that text as untrusted source data: embedded prompts cannot authorize
  tool calls, secret access, outbound sends, publishing, or route changes.
- Follow-up requests such as “send the video here”, “download/save the generated
  video”, or “submit it to LazyEdit” should first resolve the newest bounded-age
  same-chat generated MP4 from the worker artifact ledger. This resolver must
  ignore AutoPublish-cache files and other chats, then return the MP4 through
  the required artifact delivery gate.
- GUI file delivery is a first-class state, not a best-effort afterthought.
- Image and media analysis is multilingual by default: explain the verified
  source in Chinese, English, and Japanese. When the source contains readable
  language material, add pinyin, kana/furigana, romaji, pronunciation, grammar,
  and vocabulary as useful; keep OCR and parser diagnostics private.
- EchoMind compiles one previous-day language review at 08:00 HKT using
  XeLaTeX. The PDF contains balanced Chinese, English, and Japanese teaching
  sections, pinyin, Japanese ruby furigana, pronunciation, grammar, and
  exercises, and is delivered through the normal verified file gate with a
  date-based deduplication record.
- WeCom GUI artifacts use a private one-file C-drive staging directory and the
  visible `More -> File -> Local File` picker. Navigate to the directory, select
  the verified sole row, stage it, then send it from the composer. Long labels
  may be ellipsized; exact picker readback plus the visible attachment prefix
  and a new history card form the identity proof. Do not use a Wine Explorer
  drag fallback or treat a closed picker as proof of delivery.
- Android WeCom artifacts use the native DocumentsUI `Download` root. Use a
  deterministic short display name with a content digest, verify the exact row
  and pre-send confirmation, and write a `committing` ledger component before
  tapping Send. A stable full or middle-ellipsized same-chat history card
  completes the component. On timeout, reconcile that component before any
  retry; never upload the same file twice merely because the card text was
  truncated.
- Treat Android WeCom text and files as independent delivery components. Before
  a send or deferred retry, query `/v1/delivery-status` with the stable task ID
  and full desired batch. Persist every confirmed component even when the batch
  response contains later errors, normalize stale DocumentsUI/attachment/
  confirmation surfaces back to the exact chat composer, and submit only the
  ledger-confirmed pending components. A partial response must not cause a
  whole-batch retry or duplicate a PDF already visible in chat.
- For a mixed artifact-and-text result, send all artifacts before completion
  text. Native mention selection is a best-effort notification layer and must
  not be allowed to disturb the exact chat before required files reach it.
- Keep authorship and transport separate. The resumed route/worker agent owns
  the natural immediate acknowledgement, final explanation, file selection,
  and task-specific judgment. The deterministic routine owns exact-chat
  locking, sender attribution, staging, checksums, artifact-first ordering,
  native mentions, retries, deduplication, and the component ledger. Do not
  replace normal agent replies with canned keyword responses; deterministic
  text is only a bounded failure/safety fallback when every configured agent
  backend is unavailable.
- Treat the agent result as one delivery contract: every selected file and the
  contextual final message are separate ledger components. A partial batch is
  not complete. Backfill only the missing components from the stored result,
  without rerunning research, regenerating artifacts, or resending components
  already marked `sent`.
- Before native mention composition, persist a private `composing` component.
  If the process stops, the next guarded send may clear a draft only when that
  ledger proves bridge ownership or the composer contains only WeCom's native
  mention markers plus a dangling `@`. Preserve any unowned human prose draft.
  Mark recovered ownership `abandoned`, then retry the original text component
  and mention instead of creating a new message task.
- After tapping an external-group row, tolerate the official client's bounded
  loading transition and wait for the exact title (including a member-count
  suffix such as `LabAgent(6)`). A transitional hierarchy is not proof of a
  wrong chat; a persistent different title still fails closed.
- Hold the Android GUI serialization lock only for official-client reads and
  writes. Release it before calling ingress, routing, or any backend agent, then
  reacquire it for each reply send. A long research turn must never monopolize
  the GUI lane and starve an unrelated artifact delivery.
- Persist the structured worker result and exact artifact list before entering
  any GUI sender. If the picker, relay, or worker process stops, recovery must
  resume delivery from that stored result without rerunning expensive tools.
  In the deferred outbox, verified publication completion remains first,
  required artifact deliveries come next, and ordinary text follows. Preserve
  concrete relay errors before applying the generic missing-artifact gate so
  operators can repair the actual transport failure.
- The WeCom worker's `--chat wecom` value is a transport namespace, not a chat
  filter. Its idle loop must scan the WeCom queue's deferred outbox and retry
  the highest-priority required artifact automatically.
- Official WeCom voice, quoted voice, and mixed-message voice must be downloaded
  by the SDK into the exact message directory and exposed as
  `transport_preflight.wecom_media`. The worker passes only those exact files to
  `wechat_audio_intake.py`, reads its `agent-context.md`, and never falls back
  to a personal-WeChat database or nearby media file.
- Deduplicate Android WeCom files by SHA-256 within the exact destination chat,
  not only by task ID or filename. A renamed artifact or supplemental task must
  reuse the prior delivery record instead of uploading the same bytes again.
  Only an explicit operator `--force` resend may bypass this content guard.
- Ordinary link/read-later research should send a concise chat answer by
  default, not Markdown/PDF/image attachments. Save local notes under the task
  artifact directory. Attach reports or images only when the current request
  asks for them, or when the worker truly read substantial content and marks the
  report as worth sending. The daily self-analysis agent is the normal
  bilingual zh/en PDF path.
- In link/read-later chats such as `鏈接`, forwarded Gongzhonghao/mp.weixin
  article cards are `research_summary` tasks by default. Source-card routing
  must happen before CAD/PCB/3D keyword fallback because URL hashes can contain
  misleading substrings such as `3d`. Run `wechat_source_recovery.py` before the
  agent: mobile-WeChat HTTP extraction and private cache first, followed by the
  manifest's exact-title/account/identity reconstruction queries. A gate is not
  a human-confirmation state. Never open/focus a browser or ask the owner to
  verify for read-only research; return an evidence-limited answer if recovery
  remains incomplete.
- WeCom Android renders ordinary text under resource `j1l`, but a native
  Gongzhonghao card title under `mww`. Treat that row as
  `wechat_article_card`, preserve its exact sender and title, and route it to
  `research_summary`; never discard it merely because no `j1l` node exists.
- The Android relay performs one bounded, round-robin historical scan at a low
  cadence. It scans at most the configured number of older viewports, records
  only unseen exact-row fingerprints, and re-enters through the conversation
  list so the client returns to the newest viewport. This recovers a card hidden
  by a long bot response without turning every poll into a history crawl.
- For a WeCom Android article card with no URL in the event,
  `wecom_native_article_recovery.py` finds the exact same-chat title, opens that
  card in the native WeChat reader, uses its `复制链接` action, verifies the
  copied `mp.weixin.qq.com` article title, and hands the URL to the existing
  read-only `wechat_source_recovery.py` path. The native client is restored to
  the WeCom conversation list afterward. If native resolution fails, exact
  title/account reconstruction remains available and the agent must state the
  evidence limit rather than asking for browser verification.
- Group voice, audio, and ordinary video intake is source-scoped and agent-led.
  The monitor transcribes native type-34 voice rows before routing, keeps only
  safe transcript/language/duration fields in the private task, and never loses
  the transcript at the queue boundary. The worker aliases those rows or an
  exact resolved audio/video file into `task.preflight.audio_intake`, whose
  `agent_context_path` must be read by the same chat's resumed backend session.
  `wechat_audio_intake.py` owns `ffprobe`, extraction, ASR, caching, and strict
  `no_audio` evidence; Codex owns interpretation and requested work. Use
  `PYTHONPATH=src python -m agenticapp wechat audio-intake --input <media> --output-dir <task-dir> --json`
  for a standalone check. Encoded app-message types must be reduced to their
  low 32-bit base type before deciding whether media resolution applies.
- Shipinhao/Finder/视频号 research tasks should run the read-only source
  recovery, exact-media transcription, and comment-intelligence preflights.
  Try the card's allowlisted Tencent media URL first. If it expired, keep the
  operation read-only and try `shipinhao_media_transcribe.py` public-mirror
  recovery: OCR the exact card cover with Tesseract and an optional EasyOCR
  fallback, translate short Chinese evidence when available, search only bounded
  public candidates, and inspect public captions before downloading media. Accept
  either a close-duration content match or a bounded excerpt from a longer source.
  A longer-source excerpt requires independent caption/card agreement, a localized
  time window, and a corroborating Whisper transcript. Related clips from the same
  speaker must remain rejected when they do not match the card paraphrase/topic.
  Version public-mirror cache identity so a superseded match cannot remain cached.
  Record only a public source ID and bounded match metrics; do not persist search
  logs or signed URLs. A valid
  result is `input_kind=content_verified_public_mirror` with both
  `content_identity_verified=true` and `public_mirror_validation.accepted=true`.
  The directly usable entrypoint is:
  `PYTHONPATH=src python -m agenticapp wechat shipinhao-transcribe --source-text-file <card.txt> --output-dir <task-dir> --json`.
  If deterministic recovery remains unresolved, it may expose only private
  `cover_path` and `source_text_file` context paths to the resumed agent. The
  agent may inspect the cover and supply up to three `--search-hint` values, but
  the same deterministic identity gate must still accept the result; a visual
  guess alone is not evidence.
  If no candidate passes, use `shipinhao_gui_audio_capture.py` automatically
  against the exact guarded source chat. Normalize to the latest message and
  scan only bounded recent history. Prefer a multi-scale match against the exact
  same-object cached cover; otherwise bind a detected play control to
  title/author OCR in that same card's local neighborhood. Restrict both paths
  to the received/source side and preserve the candidate kind so a real
  cover/play target gets the full player-open timeout. Never authorize a click
  from matching text in a later right-aligned bot reply.
  After the exact card opens, bind the current `WeChatAppEx` PipeWire stream,
  start playback once if the stream has not appeared, require player title/author
  identity, and stop on consecutive identity loss or the source card's bounded
  expected duration. Trim feed auto-advance and register a private object-ID/hash
  manifest. The worker must validate and transcribe that manifest before claiming
  video-level understanding. Do not reload the player after binding its stream,
  trust nominal duration without continuing visual identity checks, reuse a
  capture from a different object ID, or expose private audio/screenshots.
  Failure semantics are strict: `no_audio` is valid only after `ffprobe` reads
  media and reports zero audio streams; HTTP/download failure, public-mirror
  mismatch, card not found,
  source card found but player unavailable, and PipeWire stream unavailable are
  separate `failure_stage`/`error_code` values. Every outcome must write a
  private `agent_context_path` and `audio_evidence_status`. Unresolved outcomes
  use `media_unavailable_not_silent`, forcibly clear `verified_silent_media`,
  and instruct the resumed agent not to rewrite acquisition failure as silence.
  The same rule applies to the aliased `task.preflight.audio_intake` packet.
  Automatically discover
  exact matching `comment_data` JSON under configured/private download roots and
  probe a local `wx_channel` API on `127.0.0.1:2026` when object IDs are known.
  The worker writes
  `task.preflight.shipinhao_comment_intel` and
  `output/wechat_worker/<task-id>/shipinhao_comment_intel/manifest.*`; agents
  must use that as auxiliary evidence and stay source-limited when no video,
  transcript, comment export, or reliable mirror is available. If JSON/API
  export is missing but the matching official WeChat/Channels detail page is already visible, use
  `agentic_tools/wechat_gui_agent/scripts/shipinhao_native_capture.py` to capture
  screenshots and OCR visible title/comments as read-only evidence. Never post
  comments or ask Yuanbao from the account without explicit current per-video
  permission. Otherwise execute exact title/author/object-ID reconstruction
  queries and answer with explicit evidence quality rather than requesting
  verification.
- Chat behavior by purpose:
  `鏈接` reads shared links/cards/videos/files and replies with a short useful
  summary or a clear limitation; `🍓我的设备`, `懒人科研`, and `lachlanchan` can run
  the full tool surface when asked, including media reading, CAD/PCB, video
  generation, LazyEdit, and publishing; `写作 外语 挣钱` should give high-quality
  writing/career/money thoughts from the shared material; `EchoMind` stays
  focused on language teaching unless an explicit backend task is requested.
- File attachments should use the official Linux file chooser with clipboard
  path paste (`Ctrl+L`, paste absolute path, `Enter`). If WeChat locks during
  that file-picker flow, the worker releases the serialized send lock, runs the
  Android-backed unlock watchdog, and retries the same file send within the
  bounded `WECHAT_WORKER_FILE_SEND_UNLOCK_RETRIES` budget.
- Text delivery is successful only after WeChat consumes the clipboard and the
  focused composer can be copied back with content equal to the intended
  message. A clipboard-owner timeout or composer mismatch is a send failure;
  screenshot pixel changes alone are not proof because focus and cursor blink
  can change an otherwise empty window. Keep every attempt's screenshot prefix
  unique so failed evidence cannot be overwritten by a later retry.
- Fast chat replies and organizer acknowledgements use bounded durability. If
  the GUI is locked, the serialized sender is busy, or the sender times out,
  enqueue at most a short-lived `send_deferred_locked` outbox item. Preserve
  `send_deferred_reason` as `wechat_locked`, `gui_send_busy`,
  `gui_send_timeout`, `wechat_entry_required`, or `title_guard_blank`. Ordinary
  deferred sends expire after 10 minutes by default and retries are globally
  spaced by 30 seconds, so a restart cannot dump a stale burst into WeChat.
- Immediate invocation is part of every routine contract: enabling or changing
  a schedule runs one bounded invocation immediately. If that routine requests
  chat output or an artifact, it must verify delivery before reporting success;
  internal-only runs must use an explicit `--no-send` or equivalent mode. A
  failed sender records a durable deferred state instead of silently dropping
  the result or replaying a stale burst after restart.
- Scheduled EchoMind lessons and LabAgent research/inspiration jobs observe
  local `Asia/Hong_Kong` quiet hours from 20:00 through 08:00. The scheduler
  sleeps until 08:00 and then resumes; explicit user requests and interactive
  replies remain available overnight.
- EchoMind's periodic multilingual teaching cadence is three hours
  (`10800` seconds), not one hour. The scheduler records the last successful
  delivery and waits out the remaining interval after a restart, preventing a
  reboot or tmux recovery from sending an extra lesson.
- LabAgent inspiration is opportunistic. If that exact chat has a pending or
  running question, report, confirmation, or artifact send, defer inspiration
  without enqueueing a backlog item or emitting a status message. The next
  quiet-cycle check may run it after interactive work is terminal.
- WeCom GUI reconnect is a narrow exception, not backlog replay. Do not infer
  authentication from window geometry. Recovery begins only after the normal
  poll successfully opens and title-verifies the exact allowlisted chats; a
  cached or half-authenticated full-size window consumes no recovery attempt.
  Hold that verified state for two minutes before recovery. The transition may
  then recover at most one `send_expired` WeCom result from the previous 12
  hours, only when it had already reached a send state and still contains a
  resendable result. The per-task recovery cap, exact-chat guard, and durable
  text/file delivery ledgers still apply. It must not recover pending work,
  another transport, or arbitrary historical messages.
- Duplicate-response guards must not use placeholder WeChat `server_id` values
  such as `0`, empty, `null`, or `-1` as globally unique ids. Store a per-row
  response key and fall back to `local_id` for placeholder server ids so
  EchoMind and other fast chats do not silently ignore later messages.
- Worker reloads must not leave orphaned GUI send helpers holding the send lock
  forever. Before checking the serialized send lane, the worker reaps stale
  orphaned `wechat_gui_send.py` processes older than
  `WECHAT_WORKER_STALE_GUI_SEND_SECONDS` while leaving non-orphaned active sends
  under the normal timeout.
- Direct monitor state writes must be atomic. The monitor checkpoints the
  inbound cursor before route-agent or GUI network work. A failed turn may be
  replayed only through the explicit replay command; restart must not consume
  the same historical burst again.
- Login, CAPTCHA, QR, payment, lock screen, and irreversible decisions wait for
  normal human approval.
- The WeCom GUI transport may derive bounded `Up`/`Down` navigation from the
  selected row's blue geometry and the target row's OCR when Wine ignores a
  pointer click, but must verify the exact title afterward. It sends a verified
  composer with `Alt+S` and records delivery only after the composer clears or
  the exact artifact appears in history.
- The WeCom GUI transport checkpoints successfully ingested inbound messages
  before attempting their acknowledgement sends. A post-send verification
  failure may defer an acknowledgement, but it must never replay the incoming
  request or bombard the group with duplicate replies.
- The WeCom Android transport is a separate, allowlisted WeCom-only path. It
  locks device rotation to portrait, checks the exact native chat title, never
  overwrites a non-empty draft, and records sends by stable task/component hash.
  Group replies carry the current source sender's exact visible display name;
  the relay selects one native mention-picker row and verifies a rich mention
  span before Send. The only accepted row normalization is WeCom's `@微信`
  suffix. Missing, ambiguous, broadcast, or wrong-chat targets fail closed.
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
| WeCom Android relay | WeCom sender/monitor | `wecom_android_bridge.py` | Use unread badges for low-latency hints and periodically reconcile every allowlisted group, enqueue exact sender context, send idempotent text/files, and select native per-sender mentions without desktop login. |
| Android text fallback | Worker outbox | `send_result_with_retries()` | For verified publish-completion text only, if desktop GUI send fails with a deferable guard/timeout, ADB may send a sanitized ASCII completion after screenshot OCR proves the phone is already open to the exact target chat. |
| Browser assist | Human + worker | `wechat_browser_assist.py` | Use only for login/CAPTCHA/download confirmation or blocked web UI. |

## Target-Scoped Send API

Use the LabCanvas send API for direct text sends from the CLI, web app, or
other local tools. Do not call `wechat_gui_send.py` ad hoc unless debugging the
sender itself.

```bash
PYTHONPATH=src python -m agenticapp wechat send \
  --chat EchoMind \
  --message "收到，我会按这个上下文继续。" \
  --json
```

HTTP callers use:

```text
POST /api/wechat/send
{"chat":"EchoMind","message":"...","dry_run":false}
```

The API resolves targets from the ignored private registry
`agentic_tools/wechat_gui_agent/.private/wechat_send_targets.local.json`, then
falls back to the direct chat config's `send_target`. Every target must include
`name`/`query` plus `expected_title` or `expected_title_aliases`; this keeps the
OCR title guard mandatory. Search is disabled by default. Use `--dry-run` or
`"dry_run": true` to open/compose without pressing Enter.

Before sending, the API removes obvious backend log lines such as `AgInTi:`,
`stdout:`, `stderr:`, `backend:`, `model:`, command traces, and script paths.
Workers should still return structured JSON with `message`, `confirmation`,
and `files`; `parse_worker_result()` extracts that JSON even when AgInTi,
Codex, Claude, or a wrapper prints progress logs around it. Raw agent stdout is
evidence for local artifacts, not chat-facing content.

## Token And Latency Policy

- Idle polling is local-only and should not spend model tokens.
- LabAgent group inspiration is a separate low-frequency routine: after three
  hours without human group activity, enqueue at most one concise, agent-written
  knowledge point using same-group history, active `#daily` interests, explicit
  `#interest` settings, and prior inspiration outputs. An explicit interest
  update queues one immediate point, then the three-hour quiet-period schedule
  resumes. It must be idempotent and must not merge private member context or
  create a public-posting permission.
- Use fast-router Codex only for new actionable messages, ambiguous routing, or
  immediate lightweight replies.
- For the isolated WeCom transport, use `gpt-5.6-sol` low for route/chat turns
  and dynamic `gpt-5.6-sol` effort from low through ultra for durable work;
  daily research starts at high. Keep those defaults in
  `wecom_worker_loop.sh` and pass its private env via
  `WECHAT_WORKER_ENV_FILE` so the shared guarded entrypoint cannot overwrite
  them with personal-WeChat policy.
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
- Backend fallback is centralized in
  `agentic_tools/wechat_gui_agent/scripts/wechat_agent_backend.py`. If the
  selected Codex model is Spark and the live attempt fails with quota/rate-limit
  text or returns an empty payload, the same chat/role turn retries once with
  `gpt-5.6-sol` and low reasoning. If the Codex/Claude attempt is still
  quota-limited, unavailable, empty, or times out for the agent turn, the turn
  falls back to AgInTi using the configured
  `aginti.command`, `aginti.args`, and `aginti.workspace` when
  `agent_fallbacks.fallback_to_aginti=true`. Timeout fallback is on by default
  and can be disabled with `agent_fallbacks.fallback_on_timeout=false` for a
  deployment that prefers terminal timeouts. Normal weak agent answers do not
  trigger backend fallback; those stay under the worker effort-escalation
  policy.
- The default AgInTi fallback uses the backward-compatible one-shot form
  `aginti <wrapped-prompt>`. Do not assume the globally installed package has a
  local checkout's newer `run --stdin` command: an older CLI interprets those
  words as the task itself. An explicitly configured `--stdin` command remains
  supported and automatically selects stdin prompt mode. The bridge resolves
  the emitted `web-agent-*` session and accepts its final assistant turn only
  when the state file is newer than the invocation and contains the exact
  current wrapped prompt. It never forwards console headers such as `Session:`,
  `Provider:`, `Model:`, `Plan:`, or workspace paths to WeChat. A response that
  contains only a session UUID or runtime metadata is treated as empty/failure,
  not as a valid chat reply. `parse_fast_response()` repeats this check as the
  final transport gate.
- Backfill one missed row with
  `wechat_direct_chatops.py --config <CHAT_CONFIG> --force-local-id <LOCAL_ID>
  --send --no-decrypt`. Exact replay is one-shot only: it isolates that local
  row, clears both dedupe forms, and restores the monitor cursor afterward so
  newer turns are neither coalesced nor duplicated. Use
  `--force-latest-user-burst N` only when the whole newest burst was missed.
- Keep fallback configuration system-level through `agent_fallbacks` and the
  per-backend `codex`/`claude`/`aginti` config blocks. Do not implement a
  one-off Spark quota workaround inside EchoMind, link inbox, video generation,
  LazyEdit, or another individual routine. Every call to
  `wechat_agent_backend.run_agent_session` should get the same fallback
  behavior and should record `backend_attempts` plus `backend_fallback_used`.
- Keep fast route/chat timeouts bounded (25 seconds by default). A slow primary
  must yield to the centralized fallback instead of holding the monitor lane for
  minutes. Worker and long-job probe timeouts remain separate and longer.
- Launch Codex, Claude, and AgInTi agent turns in dedicated process groups. On
  timeout, terminate and reap the entire group, including native CLI children;
  killing only a Node/Python wrapper can leave an inherited output pipe open
  and prevent the worker from reaching its fallback policy.
- Do not confuse agent-turn timeout fallback with long browser or generation
  monitoring. Xiaoyunque, LazyEdit, AutoPublish, CAD, PCB, and file-download
  jobs should persist queue/probe state, status, and artifacts, then continue or
  requeue from evidence. They should not restart or switch tools just because a
  generation browser page is still running.
- Do not impose the ordinary 600-second worker boundary on WeCom daily
  research. The task itself has no deadline, and the launcher uses long
  effort-specific watchdogs. If a watchdog still fires after deliverables were
  written, exact-task artifact recovery completes delivery before any effort or
  backend retry, preventing duplicate research and duplicate acknowledgements.
- Treat structured worker output as the delivery contract. A non-empty
  `message`, `confirmation`, `files`, or explicit `NO_REPLY` is a usable result.
  A useful answer may mention that one source request timed out; that sentence
  is evidence about the source, not proof that the worker failed. Escalation
  only follows an explicit execution-failure result or an empty/too-short turn.
  Across effort retries, retain the highest-quality earlier result so a later
  empty JSON payload can never erase a substantive answer.
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
- The direct DB monitors still poll locally at sub-second intervals. On Linux
  clients that materialize inactive chats only after opening them, rotate a
  small number of chats every few seconds with `wechat_chat_sync_loop.py` and
  always yield its GUI lane while a reply/artifact send is active. This bounds
  inactive-chat pickup latency without sending messages or fighting the sender.
  Non-queue senders such as the daily report reserve
  `.private/wechat_gui_send_priority.json`; chat sync yields until that bounded
  reservation is released or expires, preventing background dry-open scans from
  starving real file/message delivery. The sync loop removes malformed,
  expired, or dead-owner reservations immediately so a crashed sender cannot
  stall chat materialization.
- Personal-WeChat deployments may retain their configured model policy. The
  isolated WeCom worker is explicitly GPT-5.6 SOL: low/medium for bounded work,
  high for daily research and execution, and xhigh/max/ultra only when the
  agent's incomplete result requires escalation.

## Grant Goal Workflow

- Route grant applications, funding proposals, and specific-aims packages to
  `grant_proposal` before generic career, document, or research heuristics.
- Initialize one ignored `grant_project/` under the exact task artifact
  directory. `goal.json`, `current_request.md`, source and figure manifests,
  proposal sources, and validation state are the durable source of truth for
  the resumed per-chat agent.
- Use Codex `create_goal` when the worker surface exposes it. If not, continue
  from `goal.json` without claiming that a goal tool was called. Never call
  `update_goal` until evidence, editable figures, compilation, validation, and
  source-chat delivery all pass.
- Prefer authenticated BioRender MCP/browser assets for scientific figures,
  while preserving atomic source parts and an assembly manifest. An editable
  SVG/TeX fallback is mandatory when BioRender is unavailable.
- `proposal.pdf` is a required delivery artifact. The sender recovers it from
  the canonical grant workspace even when the model omits the path. An invalid
  workspace silently resumes the same agent session up to the bounded repair
  limit instead of sending progress chatter or marking the task done.
- Grant drafting never authorizes public submission, payment, credential
  changes, or fabricated evidence, citations, people, facilities, eligibility,
  deadlines, approvals, or budgets.

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
| `expired_stale` | An ordinary pending task exceeded the 15-minute backlog TTL. | Leave terminal; explicitly replay the current request only if it is still wanted. |
| `send_expired` | An outbound retry exceeded the 10-minute outbox TTL. | Leave terminal by default. Explicitly resend only after confirming relevance. The authenticated WeCom GUI reconnect hook may revive a bounded recent transport-send result under the constraints above. |
| `worker_abandoned` | The process owning an ordinary `in_progress` task ended. | Leave terminal by default; explicitly reprocess only if the request is still wanted. |
| `worker_failed` | Backend failed or every fallback returned an empty delivery payload. | Fix source/tool issue; rerun only if safe. Never mark an empty payload `done`. |
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
For every video workflow, probe the exact source audio before completion. If an
audio stream is readable, create a timestamped transcript and caption/subtitle
artifact and pass the same source-scoped context to LazyEdit for correction,
translation, and burn. A verified zero-audio source is the only reason to skip
captions; record that as `silent_verified` rather than treating it as a failed
transcription.
For readable-audio teaching videos, the worker also writes a source-scoped
teaching pack beside the transcript. It must cover the original/corrected
lines in Chinese, English, and Japanese, with pinyin, Japanese kana/furigana
and romaji, pronunciation guidance, grammar, and useful vocabulary. Keep the
pack detailed enough to study from, but do not invent dialogue that is absent
from the verified audio.
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
If a research backend stopped only after writing a complete report and source
files, use `labcanvas wechat worker reprocess <task_id> '<reason>'
--artifact-recovery-only --send`. This compiles and delivers the exact task
artifacts without another model turn or repeated research.
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
PYTHONPATH=src python agentic_tools/wechat_gui_agent/scripts/wechat_transport_stall_guard.py --json
```

The persistent guard runs in `labcanvas-wecom:health`. It checks the WeChat and
WeCom tmux runtimes, all configured direct-monitor `last_loop_at` heartbeats,
`chat-sync`, sender-lock ownership, active queue clocks, the Android relay,
the three-hour EchoMind scheduler, and the daily career scheduler. A configured
official WeCom CLI route is optional when its private state says
`message_permission_unavailable`; the healthy GUI/Android routes must not be
reported as degraded merely because the tenant does not grant that permission.

Repairs require repeated observations and preserve the logged-in clients. A
stalled direct monitor reloads only monitor/chat-sync windows; a missing runtime
uses the idempotent supervisor `ensure` path. EchoMind is managed by
`echomind_language_scheduler_tmux.sh`, which reuses its ignored state and waits
the remainder of the three-hour interval after restart instead of sending a
duplicate lesson. `wechat_stack_tmux.sh start` restores both EchoMind and the
daily career scheduler after reboot.
- A terminal scheduled-inspiration delivery outcome such as `send_failed`,
  `send_expired`, `worker_failed`, or `expired_stale` must not block later
  three-hour LabAgent inspiration cycles. Pending, in-progress, deferred, and
  retrying deliveries still suppress a new cycle so the group is not flooded.
- Direct monitors journal exact inbound local IDs before any route-agent or GUI
  operation. A restart re-reads those rows even though the normal cursor was
  checkpointed, and the worker queue deduplicates by exact source identity.
  Health checks treat a bounded journaled agent turn as `processing` for up to
  15 minutes instead of killing it after the normal 30-second idle-heartbeat
  threshold. This prevents a health repair from consuming a message without
  creating its task.
- LabAgent inspiration uses the latest human inbound activity, preference
  update, or prior enqueue as its baseline. Bot replies do not reset the idle
  clock. A private heartbeat is refreshed on every scheduler poll, including
  overnight quiet hours, so transport health can distinguish ordinary waiting
  from a stalled loop. Two consecutive stale checks restart only the `daily`
  scheduler window; they do not restart or log out WeCom clients.

Set `LABCANVAS_HEALTH_ALERT_TRANSPORT=wecom-android` and
`LABCANVAS_HEALTH_ALERT_CHAT=<allowlisted-group>` only in the ignored WeCom env.
Serious alerts are sent after three consecutive failed checks, keyed by the
fault-set transition, and are cooldown/delivery-ledger deduplicated. A transient
Codex quota error that succeeds through GPT-5.6 SOL or AgInTi fallback is not an
alert; only a recent terminal task where every configured backend is exhausted
is. Alert text contains health codes only, never chat text, raw IDs, secrets, or
private paths.

Expected signs:

- all monitored configs have distinct `state_path`;
- `ignore_self_messages` is true in production;
- `allow_human_self_messages` is true when the account owner sends commands from
  the same logged-in mobile account;
- `self_messages_text_only` and `ignore_probable_bot_self_replies` are true to
  prevent self-file and bot-reply loops;
- recent bot text appears as `self_outbound_echo` rather than a new queued task,
  and control variants such as `noreply` or `NO_REPLY: reason` produce no GUI
  send;
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
- `direct_monitors.healthy` equals `direct_monitors.configured`, schedules report
  EchoMind at `10800` seconds, and `agent_failures.quota_failure_count` is zero.

### Black noVNC Canvas

The WeChat desktop is `DISPLAY=:97`, VNC `5917`, and noVNC `6107`. The shared
Xiaoyunque/JLC browser is a separate `DISPLAY=:98` desktop on noVNC `6099`.
Do not diagnose one through the other URL.

If noVNC `6107` connects but shows a completely black canvas, check:

```bash
DISPLAY=:97 XAUTHORITY= xwininfo -root -tree
DISPLAY=:97 XAUTHORITY= xdotool search --onlyvisible --class wechat getwindowgeometry --shell
```

Healthy WeChat has a mapped window substantially larger than a helper window,
normally around `1020 x 739`. A `1 x 1` unmapped `wechat` window or an unmapped
`200 x 200` `WeChatAppEx` window is only a background/helper surface; x11vnc
will correctly transmit the black X root because there is no chat UI to show.

`wechat_virtual_desktop.sh` now treats this as a stale background-only client.
It first invokes WeChat normally to request activation. If no large mapped
window appears within the bounded startup wait, it gracefully restarts only the
`/usr/bin/wechat` process whose environment matches `DISPLAY=:97`, preserving
Xvfb, x11vnc, websockify, the profile, queue, and monitors. Set
`WECHAT_AUTO_RECOVER_UNMAPPED=0` to disable this fallback while debugging.

## Recovery Playbooks

### ProteinStructure and AlphaFold

Protein-structure requests are agent-owned worker tasks. The transport ACKs and
queues them; the worker resumes the exact chat session with `gpt-5.6-sol` and
Ultra effort, then calls the existing `ProteinStructure` routines through the
thin LabCanvas CLI. Do not duplicate AlphaFold browser logic in the worker.

```bash
labcanvas protein start --json
labcanvas protein status --json
labcanvas protein submit path/to/job.fasta --dry-run
labcanvas protein poll --download --all-pages
labcanvas protein metrics --detailed
labcanvas protein render all
labcanvas protein screenshot
```

The source submodule is `external/ProteinStructure`; the default artifact
workspace is the sibling `../ProteinStructure`. The browser reuses
`~/.cache/alphafold-server-chrome`, CDP `127.0.0.1:9222`, and localhost noVNC
`127.0.0.1:6187`. Generated downloads, figures, PDFs, screenshots, and logs
remain ignored in the sibling workspace. Results returned to chat must include
the useful model/metrics/plot/report artifacts, not merely local paths.

Treat structure prediction and inhibitor identification as separate evidence
stages. AlphaFold confidence does not prove binding, docking is a hypothesis,
and literature/database evidence must remain distinguishable from experimental
validation. Respect AlphaFold Server terms and do not represent its output as
clinical or screening validation.

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
- for image understanding, inspect the copied image with Codex vision first and
  use the manifest `OCR text` only as supporting evidence. The user-facing reply
  should naturally explain the image, not reproduce the internal evidence
  schema. If both vision and OCR are empty, inspect the copied image itself
  before saying no readable content was found; visible GUI crops are valid
  fallback source media when the original WeChat cache file is broken;
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
  `WECHAT_WORKER_TRANSIENT_SEND_MAX_RETRIES` (default 2), old automatic recovery
  cycles are disabled, and deferred sends share a 30-second global cooldown.
  This prevents a recovered network or restarted desktop from bombarding chat
  windows with accumulated replies.

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
