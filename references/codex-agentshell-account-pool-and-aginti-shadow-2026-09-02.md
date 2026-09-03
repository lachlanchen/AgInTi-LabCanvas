# Codex AgentShell Account Pool And AgInTi Shadow Review

Date: 2026-09-02

## Runtime Contract

LabCanvas uses Codex as the automatic execution authority. The web app, CLI,
WeChat, and WeCom continue to use their existing persistent conversation
sessions and established task routines. AgInTi remains available as the
DeepSeek-first, LocalLLM-second fallback.

AgentShell provides isolated saved Codex accounts with shared Codex history.
LabCanvas discovers only existing profile directories containing
`profile.conf`; discovery never invokes profile-management commands and cannot
create a profile. A read-only monitor calls the official Codex app-server
`account/rateLimits/read` method for each profile and writes a private mode-0600
cache under `agentic_tools/wechat_gui_agent/.private/`.

Selection order is:

1. A valid explicitly pinned account, when configured.
2. Accounts with remaining weekly allocation, highest remaining allocation
   first.
3. Accounts with purchased credits.
4. Existing profiles without a fresh snapshot, after positively available
   profiles.

LabCanvas model order is separate from account selection:

1. Use `gpt-5.6-sol` through the best available AgentShell account while the
   normal Codex allocation is at least 5 percent.
2. Below 5 percent, use `gpt-5.3-codex-spark` for the next Codex turn. The
   cached quota probe makes this decision without delaying message intake.
3. If that quota-aware Spark attempt is unavailable, exhausted, empty, or
   times out before tool activity, continue through the configured AgInTi
   fallback. AgInTi uses DeepSeek first and LocalLLM second.

An explicit model/backend selection remains authoritative. Once a tool has
started, the worker keeps the exact task resumable instead of replaying an
unknown side effect on another model or backend.

Profiles proved exhausted by a real inference response are temporarily removed
from selection even if the read-only quota snapshot is optimistic. The quota
monitor preserves that temporary runtime rejection marker.

## Side-Effect Safety

Codex can rotate to another AgentShell account after an explicit quota,
transport, or startup rejection only when no tool item has run. Codex may emit
`turn.started` before a quota rejection; that event alone does not represent a
side effect. Once tool activity appears, LabCanvas preserves the exact task for
recovery instead of replaying it through another account or backend.

A nonzero Codex exit with no answer and no tool activity is also a safe
pre-execution failure. LabCanvas rotates to another AgentShell account for that
case, then uses the configured backend fallback if every eligible Codex account
fails the same way. A nonzero exit after tool activity is never replayed this
way because its side effects may be unknown.

Because AgentShell profiles use shared Codex history, the replacement account
can resume the same conversation thread. The private session registry records
the last selected profile for diagnosis without exposing it in chat output.

## AgInTi Learning

Successful nontrivial Codex task turns may enqueue one private AgInTi shadow
review. Fast chat and routing turns are excluded. The review receives bounded
task/result text and runs with shell, file, web, MCP, parallel-scout, auxiliary,
and external-action capabilities disabled. It cannot deliver to a chat or
repeat the task. Results stay under the ignored private shadow directory and
capture structured observations about task understanding, missed requirements,
safer/faster approaches, and reusable agent improvements.

This is evaluation evidence, not a second execution path. Codex output remains
authoritative until AgInTi is explicitly selected or reached through the normal
fallback contract.

## Research And Batch Completion Guards

For concise scheduled research messages, AgInTi may provide its structured deep
research manifest. A successful Codex web-search answer can instead cite a DOI
or modern arXiv identifier. LabCanvas resolves only those strict scholarly IDs
through their canonical endpoints, without following an arbitrary model-supplied
URL, and stores the result in a private mode-0600 task manifest. Identifier
resolution proves that the cited record exists; it does not prove every claim
about the paper. The chat answer must still state an uncertainty, limitation,
or hypothesis boundary. Unresolved identifiers and unsupported general URLs
remain blocked from delivery.

When consecutive messages are handled as one batch, every source row retains a
numbered completion identity. If one item needs a supplement, the next audit
checks the already delivered answer together with the supplement, while the
sender transmits only the new supplement. This prevents a recovery turn from
forgetting earlier coverage or duplicating the entire batch.

## Commands

Refresh all saved-account quota snapshots without inference:

```bash
PYTHONPATH=src python \
  agentic_tools/wechat_gui_agent/scripts/codex_quota_status.py \
  probe --agentshell-all --json
```

Run the continuous monitor:

```bash
PYTHONPATH=src python -u \
  agentic_tools/wechat_gui_agent/scripts/codex_quota_status.py \
  loop --agentshell-all --interval-seconds 60 --json
```

Optional local controls:

```text
LABCANVAS_CODEX_ACCOUNT=<profile>
LABCANVAS_CODEX_ACCOUNTS=lab,personal
LABCANVAS_CODEX_ACCOUNT_POOL_ENABLED=0
LABCANVAS_AGINTI_SHADOW_ENABLED=0
LABCANVAS_AGINTI_SHADOW_PROVIDER=deepseek
```

Never commit AgentShell profiles, quota caches, shadow packets, session
registries, credentials, or raw chat/task context.
