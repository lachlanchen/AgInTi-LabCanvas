# Fallback Worker Deadlines And Coverage Recovery

## Failure

WeChat remained logged in, all seven direct monitors were caught up, and the
current Shares batch reached the worker. The delay occurred after backend
selection. Codex attempts were unavailable under the current account/model
policy, so the task used AgInTi with DeepSeek.

The worker selected 300-, 600- and 1,200-second budgets as its attempts
escalated. The fallback adapter replaced every budget with its generic
120-second chat timeout. A batch of consecutive article shares therefore
repeatedly lost its final response even though the agent had already saved
article bodies and draft summaries in the exact task directory.

The numbered-message coverage checker then reopened the exhausted task as a
supplement. This started another retry ladder after terminal failure feedback
had already said retrying had stopped. A subsequent response wrapped an
internal execution-guard report in valid JSON, which passed envelope validation
and reached chat. None of these failures required a client restart or login.

## Persistent Behavior

`wechat_agent_backend.configured_timeout` preserves the worker policy budget.
A generic backend timeout can extend it but cannot shorten it. An explicit
`worker_timeout_seconds` remains authoritative. Fast chat and routing roles keep
their existing configured timeout behavior. Both backend fallback planning and
the actual invocation use this function.

`reconcile_numbered_message_coverage` still repairs omitted messages after a
useful completed answer, but does not restart a `worker_failed` or exhausted
backend. It retains unresolved coverage as `blocked_backend_failure` so an
operator can recover the task deliberately. Repeated polling cannot restart
the same failed work.

An explicit `worker reprocess` starts a new execution generation and clears
the old single-message supplement, coverage retry count and terminal-feedback
receipt. Current source rows, same-chat interruptions and local artifacts
remain available. This prevents an obsolete repair instruction from narrowing
a new recovery to only one item in a larger batch.

AgInTi result validation checks `message` and `confirmation` inside worker JSON
for existing runtime-report markers and execution-guard refusals. A valid JSON
envelope alone does not make internal diagnostics suitable for chat delivery.

## Recovery

1. Check the client, source freshness and exact task before restarting anything.
2. Compare the worker budget with the effective backend timeout. Preserve
   the current paid-credit restriction and account selection policy.
3. Fix and test the adapter, then reload idle worker children under their
   existing supervisor. Preserve the logged-in client and profile.
4. Reprocess the exact failed task once through the normal worker. Tell the
   agent to reuse its retained sources and drafts, verify every current
   numbered item, and return a combined source-grounded answer.
5. Verify native outbound message history and completion coverage. A queued
   task, saved draft, model exit or generic progress message is not delivery.

Keep private sources, account details, credentials and message history out of
Git. Leave paused WeCom and disabled EchoMind schedules unchanged.

## Regression Checks

- Worker budgets of 300, 600 and 1,200 seconds survive a generic 120-second
  fallback setting; explicit worker overrides still apply.
- The coverage checker does not reopen an exhausted parent or its merged child.
- Explicit reprocessing clears stale repair state while retaining source context.
- Internal guard reports are rejected inside both JSON response fields;
  ordinary source summaries remain valid.
