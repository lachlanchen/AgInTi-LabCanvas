# LabCanvas Conversation-Derived System Contract And Gap Analysis

Date: 2026-08-30

Status: governing product contract and active remediation backlog

## Purpose

This document distills the requirements repeatedly established across the
LabCanvas, AgInTi, WeChat, WeCom, media, publishing, research, scheduling, CAD,
PCB, and artifact-delivery conversations. It is intentionally not a transcript.
Raw private chat messages, credentials, QR codes, account IDs, media URLs, and
device secrets must remain in ignored runtime storage.

The implementation manuals explain how individual mechanisms work. This note
defines what the complete system must accomplish, how it should feel to use,
and what evidence is required before claiming it works.

Related implementation references:

- `agentic_tools/wechat_gui_agent/docs/FULL_CONTROL_MANUAL.md`
- `agentic_tools/wechat_gui_agent/docs/ROBUST_EFFICIENT_OPERATIONS.md`
- `agentic_tools/wechat_gui_agent/docs/ROUTINE_ORCHESTRATOR.md`
- `agentic_tools/wechat_gui_agent/docs/GENERATED_VIDEO_ROUTINES.md`
- `references/aginti-primary-labcanvas-agent-handoff-2026-08-18.md`
- `references/lazyedit-agent-integration-handoff.md`
- `references/lalachan-story-video-handoff-for-wechat.md`

## North Star

WeChat, WeCom, the LabCanvas web app, and the LabCanvas CLI are communication
surfaces for one capable agent system. Sending a message in a group should feel
like continuing a persistent interactive agent session:

1. The exact message enters a durable source ledger.
2. Same-chat context and follow-up interruptions remain available.
3. An agent understands the request and decides what should happen next.
4. Mature routines perform deterministic or tool-specific work.
5. The agent monitors, diagnoses, and adapts when a routine encounters a real
   problem.
6. The result and only the useful artifacts return to the exact source chat.
7. Every source message has a durable disposition, even when several messages
   are answered together.

The system must not be a collection of keyword-triggered chat macros. It must
also not make the agent reimplement stable capabilities such as LazyEdit,
Xiaoyunque control, CAD export, KiCad validation, LaTeX compilation, media
transcription, source recovery, or file delivery on every turn.

The intended relationship is:

```text
human message -> persistent agent -> established routine/tool -> verified result
```

The agent owns interpretation, planning, contextual judgment, interruption
handling, recovery decisions, and the natural answer. Routines own repeatable
mechanics, identity checks, state transitions, retries, and evidence.

## Non-Negotiable Interaction Requirements

### Responsive

- New ordinary messages should be noticed promptly under normal conditions.
- Lightweight chat should not wait behind a long research, CAD, video, or PDF
  task.
- Long work should receive one short natural acknowledgement when useful, then
  one meaningful final response or artifact delivery.
- Progress messages are exceptional. They should report a real stage or blocker,
  not logs, model traces, private paths, or repetitive status prose.
- A task should start once immediately when it is created or its routine is
  enabled. The periodic schedule is for later runs, not the first run.

### No Miss

- Every genuine inbound source row must receive a durable disposition:
  `answered`, `merged_into_response`, `queued`, `waiting_human`, `completed`,
  `intentionally_no_reply`, or `failed_with_reason`.
- Consecutive messages may be coalesced into one coherent turn, but each source
  row must remain represented in the message ledger and completion audit.
- Follow-up messages during active work are interruptions to the same exact-chat
  task when context indicates continuity. They may revise, cancel, narrow,
  expand, or redirect the plan.
- A newer interruption must not be overwritten by an older worker snapshot.
- Quoted, forwarded, combined, file-caption, and reply messages must preserve
  sender attribution and quoted content separately.
- The system must not silently advance a cursor past media or voice metadata
  that has not materialized yet.

### No Duplicate Or Recursive Reply

- One source event must not create multiple equivalent replies, repeated files,
  repeated reports, repeated schedules, repeated generation charges, or repeated
  public publishes.
- Outbound messages and files must be recorded and suppressed if they reappear
  as inbound mirror rows.
- The agent must never answer its own acknowledgement, progress update, final
  message, file echo, or system log.
- Restart recovery must reconcile recent exact records. It must not drain an old
  backlog or replay previously delivered results.

### Natural And Contextual

- Replies should sound like a thoughtful person in the current conversation,
  not a diagnostic template or fixed report form.
- The agent may answer several related people together, but mentions and claims
  must refer to the correct senders.
- Peer discussion should change tone and timing, not create a hard no-reply rule.
  The agent may wait, answer, clarify, or synthesize based on the discussion.
- It should not mechanically answer every fragment separately, yet it must not
  lose any fragment's meaning or requested action.
- Useful content has priority over process narration. If there is little useful
  information, send little or nothing rather than low-quality filler.

## Architectural Boundaries

### LabCanvas

LabCanvas owns:

- transport adapters and exact-chat isolation;
- durable message, task, interruption, artifact, and delivery state;
- routine registry and tool entry points;
- profile-specific defaults and schedules;
- health, recovery, idempotency, and evidence gates;
- a common CLI/web/WeChat/WeCom agent runtime.

LabCanvas must work with any supported backend that satisfies the agent
contract. Transport correctness, source coverage, permissions, and artifact
delivery must not depend on which model is selected.

### AgInTiFlow

AgInTiFlow is a general persistent agent, not LabCanvas-specific business logic.
It owns:

- session continuity and provider handoff;
- tool reasoning and recovery;
- goal, interruption, compaction, and memory behavior;
- skill discovery and routine use;
- high-quality responses from DeepSeek or LocalLLM within provider capability.

Reusable AgInTi defects belong in AgInTiFlow. Group names, personal schedules,
LazyEdit policy, or private workstation conventions belong in LabCanvas or a
project-local skill.

### Mature Sibling Tools

The agent must reuse, not rewrite, mature systems:

| Task family | Existing owner |
| --- | --- |
| Video transcription, correction, metadata, burn, and publication | LazyEdit and AutoPublish |
| LALACHAN story/video generation | LALACHAN and Xiaoyunque routines |
| Music generation and MV handoff | Musia routines |
| Protein prediction and analysis | `external/ProteinStructure` and sibling runtime |
| CAD and printable artifacts | LabCanvas CAD routines and parametric CAD skill |
| PCB design and manufacturing outputs | KiCad/JLCEDA routines |
| Research reports | research, evidence, TeX, and PDF routines |
| Presentations | manifest-driven editable presentation pipeline |
| Book and PocketPolyglot work | Books and ZhJpBook interfaces |

The backend agent supervises these routines and resolves exceptions. It does not
replace them with ad hoc shell sequences unless a missing general capability is
being repaired.

## Backend Contract

### Backend Independence

- AgInTi is the primary LabCanvas backend.
- Its normal provider chain is DeepSeek followed by same-session LocalLLM
  handoff when the first provider is unavailable or categorized as unsuitable.
- Codex and Claude remain explicit compatibility or diagnostic backends.
- Model/provider choice may change latency and answer quality. It must not change
  source-message coverage, task identity, permissions, queue transitions,
  schedule semantics, or delivery guarantees.
- A backend failure must remain private. Users should receive a concise useful
  fallback answer, a real blocker, or a durable deferred status, never raw agent
  logs or provider stack traces.

### Agent Quality

The backend must:

- read the bounded current request before reusable policy;
- use exact same-chat context and long-term memory;
- identify all requested outcomes in a burst;
- select a routine instead of inventing one when it exists;
- use web/source research for unstable or evidence-dependent claims;
- continue from partial tool state after interruption or transient failure;
- validate claimed artifacts and external actions;
- distinguish unavailable evidence from completed work;
- avoid permission requests for already allowlisted reversible local work;
- stop for login, CAPTCHA, payment, public publication permission, deletion, or
  another genuine human gate.

### Provider Attribution

When AgInTi produces a poor result, compare:

1. the raw provider response under the same bounded task packet;
2. the response produced through AgInTi;
3. the routine/tool evidence available to both.

If the raw provider is capable and AgInTi loses the capability, fix AgInTi. If
both fail, improve the prompt, evidence packet, model route, or provider. If the
routine fails, repair the owning routine rather than hiding it with prose.

## Context And Memory

- Each chat or DM has an independent persistent agent session.
- No messages, memories, files, preferences, sources, or task results may leak
  across chats.
- Exact immutable source rows remain the authority.
- Long-term memory is built from the full available chat history with bounded
  compaction, provenance, recurrence preservation, and coverage metrics.
- Recent context is not a replacement for lifetime memory; lifetime memory is
  not authorization for a new irreversible action.
- Current messages and active interruptions are always retained verbatim within
  safe prompt bounds.
- Compaction must preserve unresolved tasks, preferences, decisions, names,
  source identities, and prior artifact outcomes.
- A memory build is valid only when its represented-message count equals its
  scanned-message count or an explicit bounded exclusion is recorded.

## Transport Contract

### Personal WeChat

- The official Linux WeChat client, direct decrypted databases, exact media
  stores, GUI sender, and noVNC desktop form one transport.
- A fresh monitor heartbeat means only that a loop is running. It does not prove
  WeChat is logged in or that the decrypted database is advancing.
- Authoritative GUI states such as QR login, entry required, account locked, or
  client unavailable must make transport health not ready.
- Quiet chats with old last-message timestamps remain healthy when login and
  ingestion are genuinely ready.
- Browser automation must not steal focus from or lock WeChat for read-only
  article work.
- Login QR, CAPTCHA, and account unlock remain human gates. The system should
  make the current QR/noVNC view available once and wait without repeated spam.

### WeCom

- WeCom has independent transport, state, sessions, profiles, and failure
  handling. It must not be coupled to personal-WeChat process health.
- Official API, GUI relay, and Android transport may coexist behind one exact
  delivery contract.
- LabAgent may perform broad research, design, figures, CAD, PCB, and reports,
  but it retains its no-public-video-publication boundary.
- External-group limitations must be surfaced as transport capability states,
  not hidden by sending to a different group.

### Reboot And Recovery

- One owned runtime stack per project is restored after reboot.
- Recovery reuses profiles, sessions, queues, and pending artifact deliveries.
- It does not launch duplicate browsers, duplicate noVNC stacks, duplicate
  workers, or duplicate schedules.
- Only recent exact safe work is reconciled automatically.
- Paid generation, public publishing, purchasing, deletion, and uncertain file
  sends are never blindly replayed.

## Profile Behavior

All profiles share the full safe agent and routine framework. A profile changes
ordinary emphasis and proactive schedules, not what an explicit safe request
may ask the agent to do.

| Surface/profile | Ordinary emphasis | Proactive behavior |
| --- | --- | --- |
| `LazyResearch` | General research, lab work, papers, figures, CAD/PCB, generation | Only configured research routines |
| `🍓My devices` | Omnipotent personal/device intake, files, media, commands, publishing | Private system-health alerts and configured personal work |
| `Shares鏈接` | Read links, Gongzhonghao, Shipinhao, papers, repositories, images | No unsolicited report bundles; concise source-grounded summary |
| `MEMO写作—外语—挣钱` | Memos, writing, language, career, money, and planning | One daily organized interactive PDF; local Markdown retained |
| `EchoMind` | Chinese/English/Japanese language teaching from text, images, audio, and video | One six-hour concise lesson and one 06:00 previous-day PDF |
| `lachlanchan` DM | Personal analysis, career direction, talent, opportunity, and commands | Configured daily bilingual career/self-analysis report |
| WeCom `LabAgent` | Broad collaborative research and design | Daily research tasks plus idle inspiration when configured |

Profile names may change. Stable internal profile IDs and session scopes must
survive title changes without replaying old messages.

## Scheduled Work

### Universal Rules

- Enabling or changing a schedule invokes it once immediately.
- Daily jobs run at their configured wall-clock time even during conversational
  quiet hours.
- Quiet hours suppress only idle or periodic conversational output.
- A busy chat/task may defer idle inspiration; it must not cancel daily work.
- Every schedule has an independent heartbeat, due date, current phase, output
  identity, delivery state, and retry timestamp.
- Restart reuses the existing report or lesson and retries delivery; it does not
  regenerate or duplicate it.
- One exact schedule occurrence produces at most one delivered artifact/message.
- Schedule content must use relevant exact-group context and long-term memory,
  but should not perform arbitrary history archaeology disconnected from current
  interests.

### EchoMind

- Every six hours: one concise but complete Chinese/English/Japanese teaching
  message, outside 20:00-08:00 HKT quiet hours.
- At 06:00 HKT: one high-quality previous-day XeLaTeX PDF, independent of quiet
  hours.
- Examples include tone-marked pinyin, Japanese kana/furigana, romaji,
  pronunciation, grammar, and useful vocabulary.
- Text, full-quality images, exact audio transcripts, and up to seven useful
  video keyframes can become teaching material.
- The lesson should cover broad daily language domains over time rather than
  repeatedly recycling one recent group topic.

### LabAgent

- Daily member topics run at the configured daily time and once immediately on
  enrollment/update.
- A member can maintain a durable interest profile and one active `#daily`
  request under the configured policy.
- If a narrow topic has no meaningful new paper, broaden intelligently into
  adjacent biomedicine, health, imaging, optics, AI/LLM agents, robotics,
  sensors, chips, BCI, and interdisciplinary areas.
- Idle inspiration uses recent and summarized group context, known interests,
  and credible sources. It runs only after a genuine idle interval and does not
  compete with active chat or research work.

### MEMO And Career

- MEMO produces one polished Chinese PDF with real checkboxes and organized,
  contextual actions. Raw classifier output or Markdown must never be sent as
  the report.
- Career/self-analysis uses accumulated personal evidence, repositories,
  writing, interests, and prior reflections. It should be deep and specific,
  not a shallow daily template.
- Reports are persisted locally with evidence and revision history, while the
  chat receives the intended PDF and concise contextual message only.

## Source And Attachment Intake

### Images

- Resolve the exact same-message original image, not a bubble crop, thumbnail,
  nearby cached image, or modification-time guess.
- On Android, request original quality and verify the MediaStore export.
- Use vision to explain naturally what the image contains and means. Do not send
  mechanical OCR headers, model names, hashes, or dimensions unless requested.
- EchoMind adds multilingual teaching detail. Other groups answer according to
  their own context; language output must not leak into LabAgent or Shares.

### Audio And Voice

- Resolve exact audio and transcribe it with the established multilingual ASR
  routine.
- Computer volume or mute state must not determine whether a stored audio stream
  can be read.
- Only `ffprobe` evidence of zero audio streams permits a `silent` result.
- Treat the transcript as user text, preserving attribution and current-chat
  context.
- Return one natural answer and, when useful, a lightly annotated transcript.
  Do not expose ASR internals.

### Ordinary Video Attachments

- A bare video with no current accompanying instruction is passive save-only.
- Save the exact source privately and send no receipt, echo, transcription,
  LazyEdit job, Nutstore copy, or public publish.
- A separate current same-chat instruction may authorize transcription,
  teaching analysis, return delivery, processing, generation continuation, or
  publication.
- Old messages and system-authored text never authorize publication.

### Documents And Archives

- Download and retain exact PDF, Word, text, ZIP, RAR, and 7z files in ignored
  task/source storage.
- Match title, extension, size, source row, and checksum identity.
- Parse readable content and answer from it rather than returning only a receipt.
- Archive extraction is bounded against traversal, links, encryption bombs,
  excessive members, excessive bytes, executables, and high compression ratios.
- A file that cannot yet be parsed still receives a truthful disposition and
  durable retry state.

### Gongzhonghao / `mp.weixin`

- Try WeChat-compatible direct recovery and private cache first.
- Extract the real article body, title, author/account, images when useful, and
  canonical source references.
- Never open an external browser by default for read-only recovery because it
  can disturb the WeChat GUI.
- If full text remains unavailable, summarize only verified evidence and state
  the limitation. Do not pretend the article was read and do not ask for browser
  verification as the default response.

### Shipinhao / Finder

- Isolate exact object ID, card identity, author, title, duration, and source
  chat before media recovery.
- For a shared Shipinhao card/link in a source-reading profile, default to:
  recover/download the exact video when verifiable, transcribe its audio on an
  available GPU that does not interrupt an active generation job, summarize it,
  and return the useful video/transcript result to the exact source chat.
- Try exact Tencent/card URL, verified cache/public mirror, comments, and source
  reconstruction before native GUI capture.
- Native capture must bind the exact card/player and stop if identity changes or
  feed auto-advances.
- Failure to download is not `no_audio`. `no_audio` requires a readable verified
  media file with zero audio streams.
- Comments may supplement understanding but must never be presented as the
  video's transcript.

## Research And Artifact Contract

- Research claims use primary or authoritative sources where possible and
  preserve citations/evidence locally.
- Quick questions receive a direct answer promptly. Valuable research questions
  may continue in parallel into a deeper evidence-backed report.
- A polished PDF is the default mobile artifact for substantial reports,
  proposals, daily reviews, and research syntheses.
- Do not send Markdown or TeX source to chats unless explicitly requested.
- Do not create PDFs merely to appear productive. For link sharing, one concise
  useful message is normally enough.
- PDFs should be compiled from structured Markdown/LaTeX, readable on mobile,
  visually polished, and checked before delivery.
- Presentations remain editable PPTX with manifest-driven native text. Image
  generation may create bounded assets, never a complete flattened slide.
- Filenames are meaningful and source-scoped, not opaque task hashes or raw
  private filesystem paths.
- Artifact delivery is complete only after exact-chat submission is verified.

## Story, Video Generation, Music, And Publication

### Story And Video Generation

- The agent gathers the full same-chat request and subsequent interruptions.
- It drafts a natural story first and sends it to the group for confirmation
  when story approval is part of the conversation.
- It does not submit paid video generation before the required confirmation.
- New messages can revise the story or steer the same Xiaoyunque thread.
- Once submitted, do not resubmit merely because polling, the agent, or the
  browser restarts. Preserve job/thread identity and let charged work finish.
- Download and verify the final full MP4, then send it back when requested.
- Music-first MV work uses Musia for the song and the established MV handoff for
  video generation.

### Publication

- Public publication requires explicit current-message intent and exact video
  identity.
- Asking another group member whether a video should be published creates a
  suspended decision, not permission. A matching later confirmation can resume
  it when sender/context semantics support that interpretation.
- Use LazyEdit as the mature processing/publication boundary. The agent calls
  its CLI/API and monitors the existing local and remote jobs.
- Subtitle correction uses the accompanying chat context and, for generated
  videos, the approved story/prompt as reference rather than a forced script.
- Metadata uses a concise viewer-facing brief derived from the same context. It
  must not dump the script or ignore names, companies, places, products, or
  people supplied in chat.
- Audio-bearing videos receive transcription, corrected timestamps/subtitles,
  translations, configured logo/subtitle burn, metadata, cover, and requested
  platform jobs.
- Existing jobs are resumed or repaired; they are not duplicated.
- Shipinhao login/QR artifacts are surfaced once through a clean handoff. The
  job remains pending until the requested platforms are verified terminal.
- Never claim publication from process success alone. Verify exact requested
  platform status and preserve job/video IDs.

## CAD, PCB, Figures, And Other Tool Work

- Explicit safe requests in any capable profile may use CAD, PCB, Blender,
  figures, TeX, presentations, protein tools, music, and other allowlisted
  routines.
- Tool-specific skills and previous design experience should guide work, but
  user-specific geometry must remain project-local rather than hardcoded into
  the general agent.
- CAD output keeps clean decoupled geometry, alignment, print fit, thread bounds,
  STEP/STL/3MF, render evidence, versioned runs, and Nutstore sync conventions.
- PCB output uses verified footprints, clean routing, DRC/manufacturing exports,
  and existing JLC ordering isolation.
- Irreversible manufacturing submission or payment remains an explicit human
  action gate.

## Health And Recovery Contract

Health is evidence, not process presence.

### Required Health Layers

1. Desktop/client availability: logged in, QR required, locked, crashed, or
   unavailable.
2. Source ingestion: decrypted DB generation/epoch and newest row advancing.
3. Monitor liveness: fresh heartbeat and cursor behavior.
4. Message coverage: every newly observed source row has a ledger disposition.
5. Worker execution: queue claims, heartbeats, interruptions, terminal state.
6. Delivery: exact-chat text/file send and mirror verification.
7. Schedule: heartbeat, due state, output state, delivery state, and catch-up.
8. Backend: provider availability and successful fallback, without exposing
   private logs to users.

### Health Semantics

- `ready` requires authoritative client availability plus a functioning source
  and monitor path. A fresh polling loop alone is insufficient.
- `caught_up` means the monitor reached the current decrypted source epoch. It
  does not prove that the source epoch itself is current.
- An old latest-message timestamp is healthy for a quiet logged-in chat, but
  suspicious when the GUI is logged out, database generation is stale, or the
  phone has newer messages.
- Health alerts go only to the private My Devices profile, once per degradation
  or recovery transition.
- Automated repair may restart an owned dead loop or scheduler. It must not
  silently log out/restart a healthy client, change accounts, send chat content,
  duplicate external actions, or disturb another project's runtime.

### Runtime Evidence Retention

- A heartbeat belongs in a compact state record, not in a full JSON transcript
  written every subsecond poll.
- Routine successful monitor and chat-materialization passes remain quiet.
  Failures retain enough structured context to diagnose the owning layer.
- Background dry-open checks may use screenshots transiently for title and lock
  guards, but must discard them after the check. At most one overwriteable
  latest-failure screenshot per chat is retained.
- Supervisor logs are capped and retain their recent complete tail. Old logs and
  transient screenshots expire automatically; verified sent-message evidence
  receives a longer bounded retention period.
- Reports, PDFs, source documents, task artifacts, durable ledgers, databases,
  and explicitly named evidence are not deleted by generic runtime cleanup.

## Current Gap Analysis (2026-08-30)

The following table separates implemented mechanisms from verified behavior.

| Priority | Gap | Current evidence | Required correction | Acceptance evidence |
| --- | --- | --- | --- | --- |
| P0 | Personal WeChat reports false-ready while logged out | GUI displays QR login; monitor heartbeats are fresh; decrypted rows stopped advancing; `wechat status` still says ready | Make fresh authoritative login/entry state part of desktop, direct-monitor, persistent-transport, and schedule health | Logged-out QR state yields `ready=false`, actionable `login_required`, no send attempts, and no source rows marked handled |
| P0 | Source freshness is conflated with monitor freshness | `caught_up` only means cursor reached stale cache | Track source generation/epoch independently and expose source-stalled versus quiet-chat states | A quiet logged-in fixture stays healthy; a logged-out or frozen-source fixture fails health |
| P0 | End-to-end current-message behavior is unverified | Loops are alive but recent user messages never reached the decrypted DB | Restore login, reconcile only recent exact rows, and run one real inbound-to-delivery smoke test | Exact new message ID appears in source ledger, task/disposition, outbound ledger, and chat exactly once |
| P0 | Schedules can appear alive while transport cannot deliver | Scheduler heartbeat can remain fresh during client logout | Separate generation health from delivery health and persist one deferred exact output | Due report is generated once, deferred while logged out, and delivered once after login without regeneration |
| P0 | WeCom scheduled research can fail before useful work or artifact promotion | Today's exact tasks include safe research ending as `permission_required`, inspiration ending as `model_did_not_execute`, and completed exact-task PDFs left undelivered. Attribution found that LabCanvas defaulted genuine AgInTi workers to conservative host mode; AgInTi correctly refused broad host shell work. | Default genuine workers to `normal` + `docker-workspace` with package setup allowed; keep host mode explicit; retain safe failure attribution; recover only artifacts that pass the existing content gate | A bounded DeepSeek/AgInTi worker now creates and verifies an exact file in Docker without a permission pause. One bounded daily and one inspiration task must still promote/deliver exactly once before closing this row. |
| P1 | Consecutive-message coverage has historically been inconsistent | Repeated reports of only the last message being handled | Enforce immutable per-row ledger and post-response coverage audit across all backends | Burst tests show 100% row representation with one coherent response where appropriate |
| P1 | Duplicate/repeated replies and files have occurred | Repeated acknowledgements, reports, and schedule artifacts were observed | Use one idempotency identity across route, worker, sender, mirror, and restart recovery | Duplicate rate is zero under retry, crash, restart, and outbound-mirror tests |
| P1 | Login-required sends can become generic failures | GUI sender can return entry-required while upstream marks work failed | Persist deferred delivery with exact artifact/message identity and human-gate state | Login recovery sends the existing result once; model/tool task is not rerun |
| P1 | Shipinhao recovery works as a tool but is not consistently selected by LabCanvas | A pasted-link recovery succeeded, while agent turns still requested links or claimed no audio | Route exact Finder cards to the established recovery/transcription routine and pass verified context to the agent | Native card and pasted-link tests both produce exact identity, media/transcript or evidence-limited result without false claims |
| P1 | Video publication quality depends on rescue intervention | Successful runs exist, but context, source identity, platforms, or poststage were sometimes mishandled | Preserve exact-video/current-intent contract and let the agent supervise LazyEdit's existing routine | A live test uses chat context for subtitles/metadata, creates one publish job, and verifies requested platforms |
| P1 | Artifact delivery can stop after local generation | Reports/files have existed locally without arriving in the requested group | Make verified delivery or durable deferred state part of task completion | Completed artifact task cannot become `done` until exact-chat send evidence exists |
| P1 | Runtime evidence grew without bounds | Idle monitors emitted JSON every 0.8 seconds and dry-open checks retained multiple screenshots per chat, producing 1.5 million PNGs and about 174 GiB of output | Keep heartbeats in state, make successful polls quiet, use transient dry-open evidence, and enforce retention/caps | Live idle logs stop growing, only bounded failure/send evidence remains, and automated retention preserves reports and ledgers |
| P2 | Backend fallback quality is uneven | AgInTi fallback improved but still fails some normal tasks | Run raw-provider-versus-AgInTi attribution suites and fix the correct layer | Representative chat, research, file, CAD, publish, and schedule tasks pass with DeepSeek and LocalLLM within declared limits |
| P2 | Long-term context can become mechanical or irrelevant | Some scheduled outputs overfit recent fragments or excavate unrelated history | Use provenance-aware full-memory compaction plus current-interest selection | Schedule review shows source relevance, no cross-chat leakage, and no unexplained history topic |
| P2 | Natural response quality is not consistently enforced | Some replies contain logs, fixed labels, raw paths, or shallow filler | Add response-quality and private-data gates after agent output, not hardcoded prose generation | Adversarial outputs are repaired or rejected; final messages remain natural and useful |
| P2 | Full-quality image and document intake is not uniformly proven | Wrong thumbnails/images and archive-type confusion occurred historically | Keep exact source identity and original-media validation mandatory | Image/file fixture matrix resolves exact originals and parses content without `mtime` substitution |
| P2 | Schedule content quality varies | Duplicate or shallow PDFs and repetitive language lessons occurred | Add content completeness, uniqueness, source relevance, and rendered-artifact review gates | One exact occurrence, polished output, expected schedule timing, no repetition |
| P3 | System truth is spread over several manuals | Mechanisms exist but no single acceptance contract represented the conversation | Maintain this document as the requirements layer and link implementation evidence | Every major change maps to a requirement and an acceptance test below |

## Acceptance Scenarios

These scenarios define “the whole system works”. Unit tests are necessary but
not sufficient; live smoke tests use harmless exact messages and no irreversible
actions.

### A. One Text Message

1. Send one harmless text to a monitored chat.
2. Observe its exact source ID once.
3. Route it to the chat's persistent session.
4. Receive one appropriate response.
5. Verify source disposition and outbound ledger.

### B. Consecutive Messages And Interruption

1. Send three fragments rapidly.
2. Begin a bounded worker task.
3. Send one correction while work is active.
4. Verify all four rows are represented in order.
5. Verify one coherent result follows the corrected intent.

### C. Full-Quality Image

1. Send a high-text image.
2. Resolve the exact original file, not a preview.
3. Return a natural content explanation.
4. In EchoMind only, include complete multilingual teaching material.

### D. Bare Video

1. Send a video without text.
2. Verify exact private save.
3. Verify no acknowledgement, transcription, LazyEdit job, echo, or publish.

### E. Explicit Video Publication

1. Send or identify one exact video and an explicit current publish request.
2. Carry same-chat context into subtitle correction and metadata brief.
3. Reuse LazyEdit, create one publish job, and monitor requested platforms.
4. Verify final platform state and one concise response.

### F. Shipinhao Card

1. Send an exact Finder card to Shares or another research-capable chat.
2. Recover exact identity and media through deterministic routes.
3. Transcribe verified audio and summarize useful content.
4. Return the exact requested artifacts once, without browser verification or
   false `no_audio` claims.

### G. Gongzhonghao Article

1. Send an `mp.weixin` article.
2. Recover `#js_content` or canonical evidence without disturbing WeChat.
3. Return one concise source-grounded summary.
4. If full text is unavailable, state the exact evidence limit.

### H. Client Logout

1. Place WeChat at QR login.
2. Verify every personal-WeChat health view reports not ready/login required.
3. Verify monitors do not consume nonexistent source progress.
4. Verify sends become durable deferred work rather than failed/replayed tasks.

### I. Schedule During Logout

1. Make one harmless schedule occurrence due.
2. Generate and persist it once.
3. Keep delivery deferred while logged out.
4. Log in and verify one delivery without regeneration.

### J. Backend Handoff

1. Run the same bounded task with DeepSeek and LocalLLM through AgInTi.
2. Force categorized provider unavailability.
3. Verify same-session handoff, same source ledger, no duplicate action, and a
   useful result.

### K. Reboot Recovery

1. Persist safe pending message and artifact states.
2. Restart the owned stack.
3. Verify one runtime stack, restored sessions, no old backlog drain, and one
   bounded recent reconciliation.

### L. Exact File Delivery

1. Generate a named PDF or CAD artifact.
2. Verify content/render locally.
3. Send to the exact source chat.
4. Verify native picker target, chat header, and mirror/outbound ledger.

### M. Group Discussion

1. Let two people exchange consecutive and quoted messages.
2. Add a direct request to the agent.
3. Verify correct attribution, no duplicate mentions, no unrelated language
   material, and a response that uses the discussion context naturally.

## Measurable Service Objectives

These are local operational targets, not external availability guarantees:

- Source-row representation: 100% for observed genuine inbound rows.
- Duplicate equivalent responses/files: 0.
- False-ready health under authoritative logout/lock: 0.
- Bare-video accidental processing/publication: 0.
- Public actions without current-message authorization: 0.
- Cross-chat context or artifact leakage: 0.
- Scheduled occurrence duplication: 0.
- Exact-task artifact delivery traceability: 100%.
- Normal lightweight route latency: seconds, not worker-task duration.
- Crash/reboot recovery: bounded recent reconciliation, never unbounded backlog
  replay.

## Active Remediation Order

1. Fix truthful personal-WeChat login/source health.
2. Keep runtime monitoring evidence bounded without weakening state or failure
   diagnostics.
3. Validate the repaired WeCom worker sandbox on one bounded daily and one idle
   inspiration occurrence. Recover existing artifacts only when they pass the
   current quality gate; never deliver or rerun rejected output merely to clear
   a queue row.
4. Restore login through the visible human QR gate and prove one exact live
   round trip.
5. Audit recent source rows only and recover missing safe work without draining
   old history.
6. Prove per-row completion and interruption coverage under bursts.
7. Prove durable deferred delivery across logout and restart.
8. Run schedule catch-up and duplicate-prevention tests.
9. Exercise Shipinhao, Gongzhonghao, image, audio, video, document, and publish
   paths through LabCanvas rather than direct operator intervention.
10. Run AgInTi provider-attribution tests and fix reusable AgInTi gaps.
11. Keep manuals, tests, runtime evidence, commits, and releases synchronized.

## Verification Snapshot (2026-08-30)

The first P0 correction is implemented and locally verified:

- The official WeChat client is visibly at `entry_required` / QR login.
- All six configured direct monitor heartbeats are alive.
- Health now reports `ready_groups=0`, `stale_source_groups=6`, and
  `client.reason=login_required`; it no longer calls the stale decrypted source
  ready merely because polling loops are caught up.
- The persistent transport guard reports one `wechat_login_required` issue,
  preserves the distinction between six healthy heartbeats and zero usable
  client paths, and marks GUI delivery unavailable without restarting WeChat.
- A watchdog retry delay of 300 seconds keeps its authoritative state valid for
  330 seconds, preventing the previous 90-second false-ready gap.
- The focused health/transport suite passed 73 tests.
- The full repository suite passed 1,611 tests after the health and retention
  changes.
- `labcanvas wechat selftest --suite all --json` passed its full routine,
  message-ledger, recovery, media, document, Shipinhao, and publishing contract.
- The output-retention audit found 1,508,695 PNGs and 15.5 GB of logs. The first
  bounded cleanup removed 1,508,180 transient files and 182,491,370,072 bytes,
  reducing `output/wechat_gui_agent` from about 174 GiB to 492 MiB while keeping
  reports and verified sent-message screenshots.
- Direct monitor heartbeats remain fresh in their state files, while all six
  idle transcript logs remained byte-for-byte stable during a live poll window.
  Chat-sync now uses temporary screenshots and retains only one overwriteable
  failure image per chat.
- The focused monitor, chat-sync, and retention suite passed 189 tests.
- The WeCom permission failure was reproduced from exact AgInTi session
  evidence: LabCanvas launched a genuine worker as `permissionMode=normal`,
  `sandboxMode=host`, and AgInTi stopped at `permission_required` rather than
  silently granting broad host access. This was a LabCanvas integration
  regression, not an AgInTi reasoning defect.
- Genuine AgInTi workers now default to the contained writable Docker workspace
  with package setup allowed. Host workspace access remains an explicit
  operator opt-in, and response-only roles remain read-only.
- Failed worker rows now retain compact backend/provider/failure attribution
  without prompts, raw diagnostics, full session IDs, or chat content.
- A live bounded DeepSeek/AgInTi smoke created, read back, and verified
  `output/aginti-permission-smoke-v3/proof.txt`, returned the exact requested
  contract string, and exited with code zero. The worker pane was then reloaded
  through its guarded self-test without restarting the WeCom gateway, GUI,
  account session, scheduler, or Android relay.
- An isolated queue/orchestrator research task then ran through AgInTi with
  DeepSeek, created an exact-task evidence note containing official Python
  documentation URLs, and reached terminal `done` with complete source-message
  coverage. It performed no chat delivery or external write.
- That smoke exposed a completion-audit false negative: outbound Markdown was
  represented only by filename while generated PDFs had bounded reader-facing
  content. The auditor now receives bounded exact-task Markdown/text content,
  treats it as untrusted evidence, and marks a repair successful only when the
  follow-up audit actually has no missing items.
- Structured worker parsing now accepts singular/plural file fields but no
  longer treats ordinary message prose ending in a filename as a file path.
- The focused backend/worker suite passed 536 tests, the completion-audit
  regression suite passed, and the full repository suite passed 1,615 tests.
  The previous storage and health commit also passed GitHub Actions run
  `33293139708`.

This does not yet prove live end-to-end operation. The remaining human gate is
one QR login, followed by bounded reconciliation of recent exact rows and one
new harmless inbound-to-response smoke test. Old failed publication rows must
not be replayed as part of that check.

## Goal Alignment

The active long-running goal is to harden AgInTiFlow into a fast, robust,
generally capable primary agent through evidence-based testing and repair. This
contract adds the operational definition of success for the LabCanvas surfaces
that depend on it:

- LabCanvas must remain correct independently of backend choice.
- AgInTi must preserve and exploit provider capability rather than reduce it.
- WeChat/WeCom must provide exact, isolated, durable message transport.
- Existing routines must make common tasks easier, not constrain the agent.
- Success is established by end-to-end evidence, not process presence, prose,
  or one-off operator rescue.

The immediate campaign checkpoint is complete only when the P0 health/source
gaps are repaired and a post-login live exact-message round trip is verified.
The broader goal remains active after that checkpoint for the P1/P2 capability
and quality work.

## Change Discipline

- Every reliability fix should identify its owning layer: transport, LabCanvas
  orchestration, routine, AgInTi, provider, or one-off external blocker.
- Add a regression test for every reproducible bug.
- Verify behavior before committing.
- Commit only scoped source/docs/tests; keep private runtime evidence ignored.
- Push validated changes and record release/install evidence when AgInTi itself
  changes.
- Never claim the system is healthy until the relevant live acceptance scenario
  passes.
