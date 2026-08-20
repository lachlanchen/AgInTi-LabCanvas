# AgInTi Primary Agent Handoff For LabCanvas

Date: 2026-08-18

LabCanvas now treats AgInTiFlow as its default persistent workspace and chat
agent. AgInTiFlow provides the reasoning/session layer; LabCanvas and sibling
projects continue to own their mature domain routines.

## Runtime Boundary

LabCanvas invokes the machine protocol, never an interactive terminal parser:

```bash
printf '%s' "$REQUEST" | aginti run --stdin --json ...
printf '%s' "$FOLLOW_UP" | aginti resume "$SESSION_ID" --stdin --json
```

One LabCanvas conversation, WeChat chat role, or WeCom chat role owns one
AgInTi session ID. Registry writes and turns are locked per conversation so two
groups cannot share context or race one session.

The machine response is successful only when `ok=true`, `stopped=false`, and
`failed=false`. A useful explanation attached to a stopped run is still a
failure and enters the fallback/retry policy.

Long-running WeChat and WeCom workers use the queue file's device, inode, size,
and nanosecond modification time as an idle wake signature. A queue append is
noticed on the normal short poll, processed work drains immediately, and an
unchanged queue receives a bounded 60-second maintenance scan for timed retry
and generation-monitor work. This avoids repeatedly parsing the full 20-40 MB
private ledger while idle without weakening delivery or restart semantics.

## Provider Policy

The primary backend is `aginti`, configured in `configs/model-policy.json`.
Within AgInTi, the default provider chain is:

1. DeepSeek.
2. LocalLLM, resuming the same AgInTi session after a categorized provider
   failure.

The handoff prompt tells the next provider what failed and preserves the saved
goal/evidence. It does not rerun completed external actions. Codex and Claude
Code remain explicit opt-in compatibility backends; they are not implicit
defaults.

Use AgInTiFlow's provider attribution evaluator when a result is poor. Compare
the raw provider against the provider through AgInTi before deciding whether
to change the orchestration or the model.

## Durable Goal And Interruption Contract

Every resumed request advances the saved goal revision. Accepted completion,
safe pause, and provider/runtime failure are distinguishable in the goal
lifecycle. Follow-up chat messages resume the same session and can correct,
narrow, expand, or interrupt work at a safe model/tool boundary.

The worker task packet remains authoritative for:

- exact source chat and sender;
- current request plus bounded same-chat context;
- same-chat files and media;
- newer interruptions;
- routine state and verified artifacts;
- irreversible-action authorization.

No cross-chat context or artifact fallback is permitted.

## Routine Ownership

AgInTi should select and supervise these existing routines instead of
reimplementing them:

| Capability | Owner / entrypoint |
| --- | --- |
| General CAD, PCB, Blender, TeX/PDF, figures, grants, presentations | LabCanvas CLI and workspace routines |
| Video correction and publication | LazyEdit `scripts/lazyedit_publish.py` and AutoPublish monitoring |
| LALACHAN story/video generation | LALACHAN Xiaoyunque/CDP workflow |
| Music and song-first MV | Musia routines and handoff contracts |
| Protein structure | `external/ProteinStructure` plus sibling runtime workspace |
| Books and PocketPolyglot | Existing Books/ZhJpBook control planes |
| WeChat/WeCom | Exact-chat intake, worker queue, and artifact delivery transports |

Deterministic code owns transport, exact-source identity, parsing, idempotency,
safety gates, and verification. AgInTi owns interpretation, routine selection,
contextual response, supervision, and recovery decisions.

## Artifact Contract

The agent must return real artifact paths produced by the selected routine.
LabCanvas registers allowlisted workspace or sibling-project outputs and sends
the requested primary artifact back to the originating chat. A path mentioned
only in prose is not delivery evidence.

Public publication, payment, manufacturing submission, credential changes,
destructive deletion, or another irreversible external action still requires
current-message authorization. Read-only planning and inspection must not be
blocked by irrelevant command, visual, or publication evidence requirements.

## Acceptance Evidence

The migration was gated by:

- DeepSeek raw-versus-agent attribution: pass;
- LocalLLM raw-versus-agent attribution: pass;
- live established LazyEdit routine discovery, read-only and no publication:
  pass;
- live DeepSeek exact artifact creation and byte verification: pass;
- live LocalLLM direct-response task: pass;
- AgInTi deterministic runtime, goal, inbox, tool, skill, and completion
  smokes: pass;
- LabCanvas full suite: 1,291 tests passed;
- WeChat complete self-test: 81 runtime results and 72 contract checks passed.

The ignored acceptance workspace is under
`output/aginti-primary-acceptance/`. It is evidence, not source and must not be
committed.

## Operator Checks

```bash
cd /home/lachlan/ProjectsLFS/AgenticApp
PYTHONPATH=src python -m agenticapp agent capabilities
PYTHONPATH=src python -m agenticapp wechat selftest --suite all --json
PYTHONPATH=src python -m unittest discover -s tests

cd /home/lachlan/ProjectsLFS/Agent/AgInTiFlow
npm test
npm run eval:provider-attribution
npm pack --dry-run
```

After publishing a new AgInTi package, update the existing installation and
restart only the already-owned `agintiflow` tmux runtime. Do not create a
second web/noVNC stack. Reload the guarded WeChat worker only after package,
machine protocol, and host acceptance checks pass.

## 2026-08-20 Primary-Backend Hardening

The remaining implicit Codex pins were removed from WeChat defaults, WeCom
ingest and schedules, EchoMind schedules, completion audits, transport repair,
grant work, and social-content work. The centralized policy now chooses AgInTi
by default. `WECHAT_AGENT_BACKEND`, `WECOM_AGENT_BACKEND`, and explicit task
configuration remain authoritative opt-ins for Codex or Claude Code.

LabCanvas distinguishes two AgInTi execution classes:

- Response-only roles use the `chatops` profile with shell and file tools off.
  They include routing, chat, completion audit, scheduled lesson editing,
  translation, career report bodies, and other content that the host will
  persist or compile.
- Tool-capable workers use the general `auto` profile and retain the routines
  required for research, CAD, PCB, Blender, media, publication, and artifact
  delivery.

Response-only host-managed prompts carry
`AGINTI_EVIDENCE_SCOPE_JSON.mode=host-managed-response`; AgInTi must return the
requested content without falsely requiring it to duplicate the host's file,
compile, or delivery stages.

AgInTi now tolerates a provider that ignores `parallel_tool_calls=false` and
returns a small valid mixed batch. Only the first tool is dispatched; the rest
are deferred and must be reconsidered after the result. Invalid schemas,
duplicate IDs, hidden fields, unavailable tools, and oversized batches remain
hard failures. A categorized runtime stop can hand off DeepSeek to LocalLLM by
resuming the same session, never by replaying the original task.

Release validation for this hardening requires:

```bash
cd /home/lachlan/ProjectsLFS/Agent/AgInTiFlow
npm test

cd /home/lachlan/ProjectsLFS/AgenticApp
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp wechat selftest --suite all --json
```
