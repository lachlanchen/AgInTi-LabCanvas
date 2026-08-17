# LabCanvas AgInTi Fallback Runtime

Date: 2026-08-17

This note defines the boundary between LabCanvas, AgInTiFlow, and LocalLLM when Codex is unavailable or out of quota. The fallback is deliberately small: AgInTi supervises one already-selected LabCanvas routine. It does not replace the transport, scheduler, media readers, CAD/PCB tools, document pipeline, LazyEdit, or artifact delivery code.

## Ownership

LabCanvas owns:

- WeChat and WeCom intake, exact-chat identity, durable cursors, coalescing, and sender attribution;
- per-chat context, interruptions, task coverage, schedules, queue state, retry state, and idempotency;
- deterministic preflight such as exact media resolution, document extraction, transcription, source recovery, and routine selection;
- established CAD, PCB, Blender, TeX, presentation, book, Musia, LazyEdit, and cross-repository routines;
- artifact validation and delivery to the originating chat.

AgInTiFlow owns:

- understanding the bounded current request and recent same-chat context;
- reading the selected routine contract and choosing the next safe routine action;
- using existing project commands and tools instead of redesigning mature workflows;
- producing one natural response plus verified task-scoped artifact paths;
- reporting an exact blocker without claiming completion.

LocalLLM is a provider behind AgInTiFlow. It is not a separate scheduler or transport. DeepSeek is tried first; LocalLLM is the fallback when DeepSeek fails before task execution.

## Runtime Path

```text
WeChat/WeCom message
  -> LabCanvas exact-chat monitor
  -> bounded task + selected routine
  -> Codex when available
  -> AgInTi fallback
       -> DeepSeek
       -> LocalLLM only after a verified pre-inference provider failure
  -> LabCanvas artifact validation
  -> exact originating-chat delivery
```

Codex receives the existing rich worker prompt. AgInTi receives a compact task packet containing only the current request, exact source identity, recent same-chat context, interruptions, selected routine contract paths, current stage, safe preflight evidence, output directory, and irreversible-action gates. This prevents the former 40k-token global handbook from overflowing a 32k LocalLLM context window.

The normal defaults are:

```bash
WECHAT_AGINTI_WORKSPACE=
WECHAT_AGINTI_PROVIDER_CHAIN=deepseek,localllm
WECOM_AGINTI_WORKSPACE=
WECOM_AGINTI_PROVIDER_CHAIN=deepseek,localllm
```

An empty workspace means the current AgenticApp repository. AgInTiFlow is the runtime executable, not the task workspace.

## Safety and Retry Rules

- Provider fallback is allowed only for recognized failures before inference or tool execution: unavailable credentials/provider, quota/rate limit, connection failure, model unavailable, or context-window rejection.
- A timeout, unknown failure, valid model response, or possible post-execution failure is not replayed on another provider. This prevents duplicate publication, generation, sending, payment, or destructive actions.
- Public publication, payment, manufacturing submission, credential changes, deletion, and other irreversible operations still require the existing LabCanvas gate and current-message authorization.
- Fast chat and routing roles have no shell or file tools. Worker roles receive only the selected routine's established tools.
- `AGINTI_EVIDENCE_SCOPE_JSON` tells AgInTi's truthful-completion layer whether the turn is conversational or an exact task. Control-prompt words no longer create false file-evidence requirements.

## Context Recovery

AgInTiFlow now preserves both the first request and the latest interruptions when compacting context. LocalLLM planning receives a bounded head-and-tail goal. If a local request still exceeds the configured context window, AgInTi compacts authoritative history and retries once, recording the event privately.

This recovery is for context-size failures only. It does not retry an executed task.

## Validation

Run the focused LabCanvas tests:

```bash
PYTHONPATH=src python -m unittest \
  tests.test_wechat_agent_backend \
  tests.test_wechat_task_worker
```

Run AgInTi validation:

```bash
cd /home/lachlan/ProjectsLFS/Agent/AgInTiFlow
npm run check
npm run smoke:context-budget-recovery
npm run smoke:truthful-completion
```

A live, non-writing smoke should prove both a conversational `CHAT:` response and a strict worker JSON response. Inspect private `provider_attempts` to confirm DeepSeek was used or that LocalLLM was entered only after a safe pre-inference failure.

## Failure Contract

The system must never send stack traces, provider logs, model names, quota diagnostics, or AgInTi planning text to a group. A failed task either moves to a durable resumable state with concise feedback or records a private terminal failure. Restart recovery must not drain an old backlog or rerun model work.

