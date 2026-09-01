# LabCanvas And AgInTi Goal And Gap Handoff

Date: 2026-08-31

Status: active engineering contract and current verification checkpoint

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
> operator-only workaround. Codex is attempted first; an unavailable turn falls
> back to AgInTi with DeepSeek, then to AgInTi with LocalLLM only as the final
> capability path. Every reusable failure becomes a regression test and a fix at
> the LabCanvas, AgInTi, provider, transport, or owning-routine layer.

This wording corrects dictation variants such as `Lab Canyas`, `Lab commerce`,
or `Canva`: the product and repository are **LabCanvas**.

Current authoritative state:

- `configs/model-policy.json` selects Codex first.
- AgInTi's configured provider order is DeepSeek, then LocalLLM.
- LabCanvas no longer injects AgInTi's OpenAI provider merely because the outer
  Codex attempt carried a GPT model name. Commit `aae8ccc` fixes and tests that
  boundary.
- AgInTiFlow `0.20.306` is published and installed. Its explicit-source
  evidence contract and manifest-free LabCanvas artifact recovery are accepted.
- The complete LabCanvas suite passes 1,780 tests at this checkpoint.
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

AgInTi remains the configured fallback agent runtime. LabCanvas attempts Codex
first, then AgInTi with DeepSeek, then AgInTi with LocalLLM. Continue
representative tests for ordinary chat, research, files, schedules, CAD,
publication supervision, and recovery. Compare raw provider output, AgInTi
output, and routine evidence before deciding where to fix a failure.

The current highest-priority core defect is DeepSeek DSML tool-call
normalization. Until the AgInTi fix is validated and installed, LabCanvas must
fail closed or hand off through a permitted provider; it must never deliver the
raw envelope as an answer.

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
