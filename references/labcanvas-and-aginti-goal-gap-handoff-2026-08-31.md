# LabCanvas And AgInTi Goal And Gap Handoff

Date: 2026-08-31

Status: active engineering contract and current verification checkpoint

## 2026-09-02 Checkpoint

The two-track goal below remains active. The latest completed slice fixes a
specific boundary between LabCanvas recovery and AgInTi evidence handling:

- A scheduled, message-only WeCom correction must be treated as a
  host-managed response. It must not inherit an older task's artifact root,
  missing-file list, or task-evidence requirement.
- LabCanvas now withholds unsupported publication, date, validation, forecast,
  and quantitative claims from message-only research when no fresh exact-task
  evidence manifest exists. It still permits a clearly labeled, source-free
  hypothesis with an actionable experiment.
- Generic completion-checker uncertainty about a scheduled correction no
  longer causes a mechanical "unfinished part" notice after the corrected
  message has passed the dedicated evidence gate. Substantive missing
  requirements remain unresolved and cannot be waived by this reconciliation.
- A successful replacement explicitly records its message-only evidence state
  as `accepted`; stale rejection state from an earlier generation cannot
  mislead later recovery or health diagnostics.

LabCanvas commits for this slice are `28705ce`, `cd31c7c`, `24aee8b`, and
`c487b8e`. The focused worker and WeCom bridge suite passes 686 tests. Two live
LabAgent inspiration occurrences were repaired without regenerating completed
safe content: both now contain a concise labeled hypothesis, no files, no
invented source or benchmark, no confirmation request, and no mechanical
coverage notice.

The current remaining failure is transport, not task execution:

- the MIX 2S is physically reachable but Android reports the existing computer
  ADB key as unauthorized;
- desktop personal WeChat is at its QR login entry;
- the isolated desktop WeCom client is at its security-verification gate;
- all monitor, worker, and scheduler processes are alive, and neither the
  personal-WeChat nor WeCom queue has an active or stale task;
- exact generated results remain persisted for bounded delivery recovery and
  are not regenerated while transport is unavailable.

Do not delete or regenerate the existing ADB key. The next physical acceptance
gate is to unlock the phone and approve that existing computer key. After a
transport returns, acceptance requires one exact inbound message and one stored
deferred result to complete without duplicate delivery.

AgInTiFlow `main` is currently released as `0.20.327`; its recent scoped
response-only work complements the LabCanvas host guard. The next AgInTi
campaign target is to make response-only research honor an evidence scope
before generation, especially during DeepSeek-to-LocalLLM handoff, while
keeping LabCanvas chat names, schedules, permissions, and transport policy out
of the general AgInTi runtime.

## Name And Intent

The product name is **LabCanvas**, pronounced as two ordinary English words:
`Lab Canvas` (`lab CAN-vuhs`). It is not Canva, commerce, commas, or Canyas;
those variants came from speech recognition.

The user's intended system is simple at the interaction boundary:

```text
WeChat / WeCom / Web / CLI
        -> one persistent exact-chat agent session
        -> mature routines and tools
        -> verified useful response or artifact in the same chat
```

The implementation can be sophisticated, but using it should feel like talking
to a capable colleague. A message must not disappear, stall behind unrelated
work, trigger repetitive logs, or require the user to restate established
context and tool knowledge.

This checkpoint supplements the full governing contract in
`references/labcanvas-conversation-derived-system-contract-2026-08-30.md`.
It records the normalized two-track goal, the latest verified progress, and the
remaining gap after reviewing the conversation and current runtime evidence.

## 2026-09-01 Goal And Runtime Update

The current operating goal is:

> Make LabCanvas feel like a smooth direct conversation with a capable agent.
> Every genuine WeChat, WeCom, web, or CLI message must be retained, understood
> with its exact-chat context, and given one appropriate disposition: a natural
> reply, durable tool task, verified artifact, deliberate contextual silence, or
> concrete blocker. Consecutive messages may be answered together, but none may
> disappear. The MIX 2S is an owned transport lane for WeChat and WeCom, not an
> operator-only workaround. Automatic turns use AgInTi with DeepSeek first,
> then LocalLLM only as a same-session fallback. Codex remains an explicit or
> specialist route. Every reusable failure becomes a regression test and a fix at
> the LabCanvas, AgInTi, provider, transport, or owning-routine layer.

This wording corrects dictation variants such as `Lab Canyas`, `Lab commerce`,
or `Canva`: the product and repository are **LabCanvas**.

Current authoritative state:

- `configs/model-policy.json` selects AgInTi automatically.
- AgInTi's configured provider order is DeepSeek, then LocalLLM.
- LabCanvas no longer injects AgInTi's OpenAI provider merely because the outer
  Codex attempt carried a GPT model name. Commit `aae8ccc` fixes and tests that
  boundary.
- AgInTiFlow `0.20.307` is published and installed. Its explicit-source
  evidence contract, manifest-free LabCanvas artifact recovery, and
  response-only provider-resume completion contract are accepted.
- The complete LabCanvas suite passes 1,785 tests at this checkpoint.
- All six personal-WeChat monitors and the WeChat/WeCom schedulers are alive,
  with no active or stale WeChat queue item.
- Delivery is currently unavailable because desktop WeChat is at login entry
  and the MIX 2S reports `adb unauthorized`. Generated career, memo, and
  periodic-language outputs remain persisted for bounded same-artifact retry.
- The pre-existing MIX 2S ADB key was recovered from the still-running ADB
  server, validated, and restored after an operator probe accidentally replaced
  its on-disk copy. No key regeneration should be used as a diagnostic again.
- A 14:00 LabAgent inspiration turn exposed a distinct failover gap: Codex lost
  its network connection after read-only tool activity, but the generic
  duplicate-side-effect guard prevented the configured AgInTi fallback. The
  worker now marks only `system_safe_read_only` tasks as replay-safe across that
  boundary. Ordinary, public, paid, destructive, and otherwise side-effecting
  tasks retain the no-replay guard. Backend attempt evidence now records whether
  execution and tool activity began so future attribution does not depend on
  inference from truncated logs.
- EchoMind quiet hours previously slept from 20:00 toward the next 06:00 daily
  PDF wake in one long interval. Delivery stayed quiet as intended, but the
  scheduler heartbeat crossed its 12-minute health limit. Quiet-hour sleeps are
  now bounded by the existing five-minute poll interval: no conversational
  lesson is sent overnight, the 06:00 PDF remains independent, and liveness is
  continuously observable.
- Live AgInTi acceptance through `labcanvas agent chat` passed on 2026-09-01:
  task `b699995fc1974712baa95f3c10516420` returned the exact requested chat
  response through DeepSeek, and task `da610379b1c74da4a95ed04cd54c662c`
  resumed the same provider session for a follow-up in six seconds. Task
  `2c7efa9c37bb45e6a663d769b34d68e3` then completed a bounded live web search
  against an official allowlisted source with command and browser evidence.
  These prove the current installed AgInTi `0.20.306` path for direct chat,
  durable continuation, and source-grounded research.
- The same LabCanvas surface also has current LocalLLM fallback evidence. Task
  `3bf3fd607fa8408fb3c88dbf3325b8d0` selected the `localllm` provider and
  completed a bounded read-only repository/readiness inspection in 17 seconds.
  Task `020612f0c26844febc280bd47dde340f` selected `localllm`, completed a
  read/write artifact task in 30 seconds, and registered the verified
  `provider-fallback-readiness.md` artifact. Both ran only after the LocalLLM
  maintenance `COMPLETE.json` appeared. This proves the final fallback path;
  it does not change AgInTi's operating order of DeepSeek followed by LocalLLM.
- Repair-agent prose is no longer presented as authoritative live health. Every
  repair-agent attempt is followed by a deterministic transport snapshot that
  records `recovered` or `unresolved`, the current issue codes, and its own
  timestamp. The agent narrative remains diagnostic evidence only. This fixes
  a misleading state where an older sentence said Android polling was healthy
  while the same health response correctly reported the phone as unauthorized.
  The focused health, worker, backend, and WeCom regression suite passes 808
  tests after this change, and the reloaded live guard now reports only the two
  real degraded conditions without the contradictory narrative.
- A broad no-churn audit of AgInTiFlow `main` at `890094d` / `0.20.306` passed,
  but a later exact LabCanvas reproduction exposed a narrower truthful-
  completion defect. LocalLLM executed and returned the requested finish value,
  yet `deriveScsTaskContract` treated the forbidden clause `Do not create or
  modify any file` as a positive file-evidence requirement and rejected the
  completion because the external-evidence ledger was empty. Commit `6f0f9b0`
  now derives the generic evidence requirement from the positive,
  forbidden-language-stripped goal while preserving the original prohibition
  in `forbiddenActions`. The regression covers one saved session across a
  LocalLLM artifact turn, a DeepSeek continuation, and an explicit LocalLLM
  response-only continuation. The full AgInTi test suite, provider/runtime
  smokes, package dry-run, and package-surface audit passed; release commit
  `3f958a3` published `@lazyingart/agintiflow@0.20.307` and the exact release was
  installed globally.
- Production acceptance then reused the same LabCanvas conversation and saved
  AgInTi session that had failed before the fix. Pre-fix task
  `c6971bc25e52422c88878058bf6524c8` ended with
  `model_did_not_execute`. Post-install task
  `7747e244624249fcaa55dc5b6b565bf9` completed in eight seconds with the exact
  response `LOCALLLM_FORCED_RESUME_OK`, no file or tool actions, the same
  AgInTi session ID, provider `localllm`, and turn count 3. This is installed-
  package evidence, not a source-checkout-only smoke. Follow-up task
  `dc602234575a41f481e22e4df5101720` then switched that same installed session
  back to provider-default DeepSeek, returned the exact response
  `DEEPSEEK_AFTER_020307_OK` in four seconds, and advanced the same session to
  turn count 4.

The next external gate is one physical acceptance of the restored computer key
on the unlocked MIX 2S: enable `Always allow from this computer`, then choose
`Allow`. After that, the waiting supervisors must recover automatically. The
acceptance is not complete until one inbound message reaches its exact-chat
agent session and each pending schedule artifact is delivered once without
regeneration or duplication.

## Normalized Two-Track Goal

### Track A: LabCanvas

LabCanvas owns the application and operational system:

- exact WeChat, WeCom, web, and CLI message transport;
- one isolated resumable session per chat or DM;
- complete same-chat context, consecutive-message coverage, and interruptions;
- durable task, artifact, delivery, retry, and schedule state;
- profile-specific emphasis without cross-chat leakage;
- deterministic identity, permission, idempotency, and safety gates;
- mature routine entry points for LazyEdit, LALACHAN/Xiaoyunque, Musia, CAD,
  PCB, TeX/PDF, presentations, research, protein structure, images, audio,
  video, documents, books, and other integrated tools;
- concise natural delivery to the exact source chat;
- truthful health and automatic bounded recovery after failure or reboot.

LabCanvas must remain operational when a supported backend changes. A weaker
model may reduce reasoning quality, but it must not change message coverage,
source identity, permission boundaries, queue semantics, schedule timing, or
artifact delivery guarantees.

### Track B: AgInTi

AgInTi is a general agent runtime, not a collection of LabCanvas group rules.
It owns:

- persistent sessions, provider handoff, compaction, and memory continuity;
- planning, tool selection, web research, and recovery from partial state;
- understanding an authoritative task packet and later interruptions;
- using an existing routine rather than needlessly recreating it;
- validating evidence before claiming completion;
- retaining as much DeepSeek or LocalLLM capability as the provider genuinely
  offers.

Reusable runtime defects belong in AgInTi. Chat names, schedule policy,
personal preferences, publishing authorization, and workstation-specific tool
contracts belong in LabCanvas or the owning project skill.

### Boundary Rule

The backend agent decides **what the request means and what to do next**.
LabCanvas and its routines make **the mechanics reliable and auditable**.

Do not hardcode conversational answers in LabCanvas. Do not ask AgInTi to
reimplement stable media acquisition, LazyEdit publication, CAD export, PDF
compilation, browser control, or delivery mechanics on every task.

## Conversation-Derived Requirements

The repeated requirements reduce to the following system behavior:

1. Treat every genuine inbound message as an immutable source event.
2. Coalesce consecutive messages when that improves the answer, while retaining
   a completion disposition for every source event.
3. Feed later same-chat messages into the active task as interruptions. A newer
   direction invalidates stale worker output before it can be delivered.
4. Reply promptly for ordinary chat. Let substantial work continue durably and
   return the useful result when finished.
5. Do not bombard chats with logs, raw paths, model traces, repeated
   acknowledgements, or duplicate files.
6. Preserve sender and quoted-message attribution in group discussion.
7. Keep each chat's context, memory, files, and artifacts isolated.
8. Use exact original images, audio, videos, files, cards, and links. Never
   substitute by proximity or modification time.
9. A bare ordinary video is save-only. Public publication requires explicit
   current-message intent and one exact video identity.
10. Video publication uses LazyEdit with chat context for subtitle correction
    and a separate concise metadata brief, then verifies requested platforms.
11. A Shipinhao card in a source-reading chat should recover the exact video,
    transcribe verified audio, summarize it naturally, and return the useful
    video/transcript once. A Gongzhonghao card should recover and read the full
    article when possible.
12. Images, voice, PDFs, Word files, and archives should be read and used, not
    merely acknowledged by checksum.
13. Schedules run once immediately when created or changed, then at the
    configured time. Daily jobs are independent of conversational quiet hours.
14. Schedule retries reuse the stored output and exact occurrence identity;
    they do not regenerate or replay after reboot.
15. Explicit reversible local work should proceed without needless permission
    prompts. Login, CAPTCHA, payment, publication, deletion, and other
    irreversible external actions keep their real human gates.
16. Desktop and Android transports are additive. A mobile fallback must not
    delete or silently replace the desktop implementation.

## Verified Current Reality

### Exact Shipinhao Acceptance

A real Shipinhao card from the Shares profile was processed end to end through
the Android-native fallback:

- the exact source chat and card identity were bound before capture;
- native playback video and system audio were captured with the phone speaker
  muted;
- repeated playback was bounded using audio and visual evidence;
- a full-duration source-scoped MP4 was retained privately;
- the audio was transcribed into a timestamped transcript;
- a natural summary, transcript artifact, and playable mobile-sized MP4 were
  delivered to the exact source chat;
- the queue row reached `done` with verified file-send evidence and no public
  action.

This is now a reusable worker path, not an operator-only procedure.

### Message And Worker Correctness

The current scoped validation passed:

- 62 Android source, sender, ingress, and control-lease tests;
- 498 worker/orchestration tests;
- the complete guarded WeChat self-test, including exact message ledgers,
  interruption preservation, passive-video safety, document/audio intake,
  source recovery, LazyEdit poststage repair, and duplicate prevention;
- 47 EchoMind scheduler tests after adding monotonic repair and busy-run
  suppression.

The final guarded startup suite passed all 97 checks after adding the two
Android-native source checks. The complete LabCanvas repository suite passed
all 1,741 tests after the phone-only transport and AgInTi boundary checkpoints.

AgInTiFlow `0.20.295` also passed its syntax, safe-chat, deep-research,
truthful-completion, and persistent-session smoke suites. After the recorded
LocalLLM maintenance completion marker appeared, one isolated live LabCanvas
turn selected AgInTi, completed in about eight seconds, returned the exact
requested response, created no tool action, and modified no project source.

Worker execution generations now fence stale in-memory workers. A manual
reprocess or successor claim can leave diagnostic artifacts, but its older
message/files cannot overwrite the queue row or reach chat delivery.

### Queue And Schedule State

At this checkpoint:

- WeChat and WeCom queues have no active, stale, recently failed, or
  delivery-blocked tasks requiring immediate attention;
- the career analysis and memo organizer for 2026-08-31 are delivered;
- the LabAgent idle scheduler is alive;
- EchoMind's six-hour schedule is alive;
- EchoMind's first previous-day PDF attempt was rejected because one repair
  removed required romaji and, more fundamentally, there were zero readable
  August 30 source messages.

EchoMind repair is now monotonic: a candidate that introduces a deterministic
defect absent from the current body is discarded. A manual immediate invocation
also returns `in_progress` when the authoritative scheduled transaction already
holds the lock, instead of waiting and generating a duplicate report.
When the exact previous day has no readable language material, the occurrence
now terminates as `skipped_no_source`: it sends nothing, clears retry state, and
does not ask a model to invent a tutorial. Current health shows no EchoMind PDF
error or pending retry.

### Transport State

The Android device is authorized and the Android intake/sender paths are active.
The desktop personal-WeChat client is currently at `login_required`; health now
reports that truth instead of treating a live polling loop as a logged-in
client. Compact operator health reports `operational=true`, `degraded=true`:
both six-route phone-ingress lanes are fresh and reach the agent, while the
desktop issue remains visible. The desktop path is preserved for later login
and review.

The first phone-only exact text round trip is now accepted while desktop WeChat
remains at `login_required`:

- one long self-authored marker was copied from the exact native green bubble;
- `Select all` plus native `Copy` recovered the complete marker instead of the
  short visible fragment;
- the exact per-chat monitor generated the requested reply;
- a first native send failure was preserved as one durable deferred result;
- the retry reused the stored result, did not rerun the backend, cleared the
  stale composer draft, and produced one verified `text-sent` proof;
- the final reply appeared once in `My devices`;
- compact health reports both phone-ingress lanes fresh and agent-reachable,
  with all six monitor heartbeats healthy and desktop degradation still visible.

The send failure was not an LLM or routing defect. The direct monitor runs in a
decrypt-only Python environment without Pillow, so the Android sender could not
detect the visible green Send button. Android sender subprocesses now use a
GUI-capable Python interpreter selected by an import probe.

### AgInTi Boundary Acceptance

A bounded read-only LabCanvas task against AgInTi `0.20.295` and DeepSeek
exposed a provider-protocol defect. DeepSeek returned a textual DSML tool
envelope for `read_file`, but AgInTi treated that envelope as a successful final
answer instead of executing the tool. The exact before/after task evidence is
kept locally under:

- `output/webapp/agent/tasks/b6c98c3e77f547d78c60e55ae2b43e02/` - false
  completion before the boundary guard;
- `output/webapp/agent/tasks/a86c75e239eb42a4b6b09c7dadc2438f/` - truthful
  `unresolved_tool_protocol` failure after the guard.

LabCanvas and the WeChat backend now reject unresolved tool envelopes instead
of forwarding them to users or marking the task complete. This is a boundary
guard, not a replacement tool loop. The general AgInTi runtime owns the proper
fix: normalize the DeepSeek DSML envelope and its safe `file` to `path` alias
into a native validated tool call, execute it, and continue the same session.

### 2026-09-01: Full-Context Memo Campaign And AgInTiFlow 0.20.308

The historical `memo-current-local-062` row was not treated as success merely
because it produced a PDF. Independent review found a crowded first page, an
almost-empty second page, an invented book-archive completion claim, lost
context, and an accidentally tracked SyncTeX file. The authoritative campaign
ledger now records that run as failed with page renders and source evidence.

A fresh ordinary-prompt campaign, `memo-current-092`, then reproduced a more
general AgInTi defect on `0.20.307`. DeepSeek correctly read the full chat,
wrote a good Chinese XeLaTeX memo, compiled and visually inspected the PDF,
sent it to the canvas, and staged the exact TeX/PDF pair. The pre-commit
document gate nevertheless received `artifacts=[]` because generated root
documents discovered through current-goal mutation evidence were not included
in the assessment candidates. The agent consequently repeated compilation
instead of committing.

AgInTiFlow commit `6edf9d95e9af64bc3b57a639295a356094f08626`
fixes the runtime at the owning layer. Pre-commit and final document validation
now include sanitized `.pdf` and `.docx` paths from the current goal's mutation
history. Arbitrary pre-existing root documents remain excluded. Regression
coverage proves generated root-PDF discovery, unrelated-root-PDF rejection,
and preservation of semantic/source-status blockers. The fix passed focused
smokes, `npm run check`, the full npm suite, package-surface inspection, and a
global install check, then shipped as `@lazyingart/agintiflow@0.20.308` from
release commit `4e50ca05de2b3caa10ed8080274c413099b71812`.

The same persistent DeepSeek session resumed on `0.20.308`, passed the real
document-quality gate, and committed only `daily_memo.tex` and
`daily_memo.pdf` as target commit `239d8f5`. Independent acceptance verified:

- a clean two-page A4 PDF with no overlap or broken layout;
- `qpdf`, `pdfinfo`, and `pdftotext` integrity;
- all interrupted-chat commitments, cancellations, waiting states, and
  evidence boundaries;
- no raw chat rows, private media identifiers, diagnostics, or placeholders;
- editable CJK-capable TeX source, intentional git history, and a clean
  worktree.

The authoritative evidence is under
`/home/lachlan/ProjectsLFS/Aginti-Test/supervision/evidence/memo-current-092/`,
and the campaign ledger records `memo-current-092` as `passed_after_fix`.

The follow-up campaign `same-task-retained-document-093` closed the remaining
resume inefficiency. AgInTiFlow commits
`5ee94fe78392554d290afc3b652940f3f5b839ec` and
`1a11370e496cd9db6c893f5b6358cf25dd51ff95` now permit retained PDF/DOCX
discovery across goal revisions only when all of the following hold:

- the artifact path is safe, project-relative, non-private, and not a scoped
  verification artifact;
- the file exists as a nonempty regular file and is not a symlink;
- the artifact mutation carries a nonempty task hash equal to the current task
  hash;
- every intervening continuation is explicitly same-task and carries that same
  nonempty task hash;
- no later same-task mutation changed the artifact or a likely same-stem source
  such as `.tex`, `.md`, `.qmd`, or `.typ` without a newer artifact mutation.

This allows the harmless `TASK.md` touch/revert seen in the real memo run while
rejecting different goals, missing hashes, unrelated stale root documents, and
stale compiled output after source edits. Focused dynamic-step, document,
truthful-completion, syntax, and full npm gates passed. Independent review
caught and corrected permissive missing-hash handling before release. The
campaign ledger records the scenario as `passed_after_fix`.

The fix shipped as `@lazyingart/agintiflow@0.20.309` from release commit
`b887c1e1ab48d711d4aaee10a00425b73a60445a`. Registry metadata, the global
installation, and both `aginti` CLI binaries report `0.20.309`; local `main`
and `origin/main` match and the source worktree is clean. A live continuation
of the exact accepted `aginti-memo-current-092` DeepSeek session then completed
as `completed-continuation-noop` in zero steps. It made no model request, tool
call, producer invocation, file mutation, or external side effect. Independent
before/after checks confirmed unchanged hashes and mtimes for `TASK.md`,
`daily_memo.tex`, and `daily_memo.pdf`, unchanged target commit `239d8f5`, and
a clean target worktree. This is the release-level proof that completed
same-task artifacts are reused instead of regenerated.

### 2026-09-02: AgInTi Primary Routing And Schedule Carry-Over

The repository, CLI, Studio, personal-WeChat, and WeCom automatic routes now
inherit one policy: AgInTi is primary, DeepSeek is its first provider, and
LocalLLM is its same-session fallback. Codex remains available through an
explicit backend choice and through specialist policy such as nontrivial
AlphaFold work. The ignored personal-WeChat and WeCom environment pins that
still requested Codex were cleared and only worker-side processes were
reloaded; GUI identities were not restarted.

Focused runtime, CLI, web, and backend tests passed 134 cases. Dry-run evidence
selects `aginti / provider-default / medium` for CAD and
`codex / gpt-5.6-sol / medium` for AlphaFold. A live CLI turn completed in five
seconds through AgInTi and the durable registry records provider `deepseek`,
model `deepseek-v4-flash`, and one retained conversation turn. Transport health
then reported both WeChat and WeCom as policy-aligned with effective backend
AgInTi.

The midnight audit also found that the career/memo scheduler reset to the new
date before retrying the prior day's persisted delivery failures. The scheduler
now performs one bounded previous-day carry-over check using only the existing
quality-accepted report/PDF and existing idempotent send routines. Its
regression forbids an agent call and verifies the organizer PDF bytes are
unchanged. Live acceptance retried the 2026-09-01 career and organizer files
after midnight, advanced their persisted backoff to 04:16 HKT, and preserved
the exact three PDF hashes and mtimes. Delivery remains blocked only by the
existing WeChat login and MIX 2S ADB authorization state; no report was
regenerated.

## 2026-09-02 AgInTi Response-Only Evidence Release

AgInTiFlow `0.20.328` closes the general response-only evidence bypass found
while repairing scheduled LabCanvas messages. Before this release, an explicit
host-managed/response-only turn could bypass the normal completion-evidence
gate and persist the first non-empty DeepSeek or LocalLLM answer, including
unsupported publication, validation, metric, and forecast claims.

The fix is deliberately implemented in AgInTiFlow rather than as LabCanvas
chat policy. Under an explicit response-only evidence contract, AgInTi now:

- evaluates source-bearing claims segment by segment in Chinese, English, and
  Japanese;
- does not allow a generic uncertainty sentence to launder a separate factual
  claim;
- permits clearly labeled source-free hypotheses and ordinary conversation;
- permits claims backed by current scoped evidence or tool results;
- attempts one same-session provider repair when the first response is unsafe;
- fails closed with `source_free_evidence_required` when the repair remains
  unsupported, without persisting or returning the fabricated answer as a
  completed session.

Source commit `58914c1744d72193162644cbfcb4244a0fec9434` and release commit
`b605063b9ed53834b38b9a35d5d6e8f2580e11de` are pushed on AgInTiFlow `main`.
The package is published as `@lazyingart/agintiflow@0.20.328`, npm `latest`
resolves to that version, and both installed entry points (`aginti` and
`aginti-cli`) report `0.20.328`. The full test suite, source checks, focused
truthful-completion and provider-handoff smokes, package dry-run, package
surface inspection, and production-dependency audit passed. The AgInTiFlow
worktree was clean after release.

LabCanvas also repaired the exact 2026-09-02 08:00 and 11:00 LabAgent
message-only schedule records without rerunning their model work. Their stored
results now contain no invented paper, date, metric, or validation claims and
record an accepted message-only evidence decision. Delivery remains deferred
where the WeCom transport is unavailable; the clean result identity is retained
for exact-once delivery recovery.

AgInTiFlow `0.20.329` then closed a second provider-handoff gap. A resumed
response-only session could hand off from DeepSeek quota to LocalLLM yet fail
before inference when retained same-session context exceeded the local context
window. Normal agent steps already had bounded context recovery, but the direct
response branch did not. Source commit
`7080a5ea33c5e2e2019a4239616b4e95dbc896d0` now compacts retained authoritative
goal/evidence once, records the context-budget and compaction events, and retries
the same response-only request without bypassing the source-free evidence
guard. Release commit `69e027dcbc6aacf52b5c84a7fe414dc1d4f550d9` is pushed;
npm `latest`, `aginti`, and `aginti-cli` all verify `0.20.329`. The focused
handoff/context/truthfulness smokes, full npm suite, syntax checks, package
inspection, audit, and clean-tree checks passed. If the compacted request still
cannot fit, AgInTi fails closed.

## 2026-09-02 EchoMind Daily PDF Recovery

The due EchoMind report exposed a deterministic false rejection rather than a
model-quality or transport defect. Source normalization removed whitespace
before lexical tokenization, so an English sentence became one giant token and
a faithful paraphrase could never overlap it. Commit `c2d6b94` preserves token
boundaries while still normalizing punctuation and LaTeX/ruby notation. A
mixed English/Japanese paraphrase regression covers the exact failure class,
and the full LabCanvas suite passed with 1,815 tests.

The required immediate invocation then generated and compiled one accepted
three-page previous-day PDF. It passed deterministic source coverage and the
independent trilingual audit after two bounded repair passes. The scheduler was
reloaded onto the tested code and proved it reused the same accepted PDF rather
than regenerating it. The artifact remains in exact-once pending-delivery state
because the existing MIX 2S ADB identity is unauthorized. After reload, schedule
health is green, WeChat and WeCom queues are empty, and the only health issues
are the external WeChat login and Android authorization gates.

## 2026-09-02 AgInTi Tool-Call Annotation Recovery

AgInTiFlow `0.20.330` closes a provider-shaped tool-loop failure found in a
normal project-inspection task. DeepSeek could attach a harmless bounded string
`reason` to an otherwise valid `inspect_project` call, but the strict schema
rejected that annotation before dispatch and repeated calls could terminate as
`tool_contract_violation`. Source commit
`ac6068b178b902ef0fffaf7839b90dbfafc6e1eb` now treats `reason` like the existing
non-executable `description` annotation: it is removed only when the offered
schema forbids additional properties and does not define that field. Structured,
non-string, oversized, and executable unknown fields still fail closed.

The direct contract regression and persisted runtime regression both pass, as do
provider handoff, LocalLLM recovery, syntax, the full npm suite, audit, dry-run
packaging, and real package-surface inspection. Release commit
`270a12de375a8f0d7f0298107e2ebcd05b75c017` is pushed; npm `latest`, `aginti`, and
`aginti-cli` independently verify `0.20.330`. The durable campaign scenario
`inspect-project-annotation-093` is recorded as `passed_after_fix`.

AgInTiFlow `0.20.331` then closes a related but distinct native-tool routing
failure. Retained evidence and a controlled persisted reproduction showed a
provider placing `tmux_list_sessions` or exact `tmux list-sessions` text inside
generic `run_command`, causing shell failure or a broad permission pause even
though the safer native tmux tool was offered. Source commit
`15242420769f313e8336976527ac34cc62d3841e` now auto-corrects only those exact
read-only aliases to `tmux_list_sessions` before shell guardrails run. It records
the correction and original requested tool, dispatches no generic shell command,
and continues to block tmux startup, send, and mutation commands.

The persisted positive and negative regressions, tmux guardrail suite,
progressive-tool selection, provider handoff, syntax, full npm suite, audit, and
package gates pass. Release commit
`09b3b31314f4edf3aab21c8973ddfc7acfaa2609` is pushed; npm `latest`, `aginti`, and
`aginti-cli` independently verify `0.20.331`. The durable scenario
`tmux-run-command-native-recovery-094` is `passed_after_fix`.

## Remaining Gaps

### Completed: Unified Personal-WeChat Availability

Compact health now separates operational phone ingress from the degraded
desktop path, while the detailed desktop-centered view still returns a false
top-level `ok`. The next correction is to make every health surface express the
same lane-aware semantics:

- desktop unavailable must stay truthful;
- Android readiness must be measured from exact ingress and send evidence, not
  merely ADB authorization;
- a chat is operational when at least one permitted source and delivery lane is
  proven usable;
- desktop recovery must not interrupt healthy Android work, and vice versa.

Acceptance passed on 2026-08-31. The compact authoritative health surface now
reports the usable Android lanes and the degraded desktop lane separately. The
detailed desktop diagnostic intentionally remains available for troubleshooting
and may still show zero desktop-ready groups while the compact operational view
is healthy.

### Completed: Read-Only Gongzhonghao Recovery

An exact prior Shares article URL was recovered as a full `#js_content` article
through the mobile-compatible request and private-cache route. It required no
external browser, no verification request, and no chat delivery. The accepted
body is retained locally at
`output/acceptance/wechat-gongzhonghao-20260831/article-1/article.md`.

A later exact native-card test remains useful for the Android card-to-URL
acquisition step, but full-text source recovery itself is accepted.

### P1: Burst And Interrupt Live Acceptance

Unit coverage proves source ledgers and stale-worker fencing. A harmless live
test should still send several consecutive fragments plus one correction while
work is active, then verify one coherent corrected answer and a disposition for
every source row.

### P1: Schedule Delivery Under Transport Failure

Generation and delivery state are separated, but live acceptance should hold a
due artifact while one transport is unavailable and deliver the same artifact
once when an exact lane recovers. It must not rerun research or create a second
file identity.

### P2: AgInTi Capability Attribution

AgInTi is the configured automatic agent runtime. It uses DeepSeek first and
LocalLLM only as a same-session fallback; Codex remains an explicit or
specialist route. Continue
representative tests for ordinary chat, research, files, schedules, CAD,
publication supervision, and recovery. Compare raw provider output, AgInTi
output, and routine evidence before deciding where to fix a failure.

The response-only evidence bypass is fixed and installed in AgInTiFlow
`0.20.328`. Continue testing provider output, tool-call normalization, and
completion evidence independently: LabCanvas must still fail closed or hand
off through a permitted provider whenever an unrecognized raw envelope reaches
the transport boundary.

Do not start LocalLLM inference during an active maintenance fence. The current
maintenance workflow now records completion, so normal provider handoff is
permitted again; any future fence must be honored in the same way.

## Next Acceptance Order

1. Restore one MIX 2S or desktop-WeChat transport lane using the existing
   identity, then verify automatic supervisor recovery.
2. Prove deferred schedule delivery across that transport outage reuses each
   stored artifact exactly once.
3. Prove a live consecutive-message interruption turn with one disposition per
   source event and one coherent response.
4. Prove the next source-bearing EchoMind day compiles and delivers one accepted
   PDF, while a source-empty day remains a quiet terminal skip.
5. Continue bounded AgInTi task-family acceptance and attribute every failure to
   LabCanvas transport, AgInTi runtime, provider quality, or an owning routine.
6. Commit and push only scoped source, tests, and documentation; keep private
   captures, raw chat state, credentials, and runtime artifacts ignored.

## Definition Of Done

The campaign is not complete because one video worked or one test suite passed.
The system is considered operational when ordinary users can send text, media,
links, files, interruptions, and tool requests through an exact chat and obtain
one useful verified result without operator rescue; schedules remain unique and
recoverable; irreversible actions remain gated; and changing between AgInTi and
another supported backend does not break the transport contract.

The long-running improvement goal therefore remains active after this
checkpoint.
