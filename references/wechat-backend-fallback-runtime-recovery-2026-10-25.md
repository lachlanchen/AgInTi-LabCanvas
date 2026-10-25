# WeChat Backend and Fallback Recovery

## Distinguish Transport from Execution

A logged-in client and a fresh message cursor do not prove that the backend can
complete tasks. Check client readiness, source ingestion, agent execution, and
verified delivery separately. A failed backend is not a reason to restart WeChat
or invalidate its profile.

The October 25 investigation found two independent execution failures:

- Some AgentShell profiles reported unused quota but rejected the requested
  Codex model with `model_not_found`. Quota is not model entitlement. These
  errors had been classified as empty responses, allowing unnecessary retries.
- A boot-service worker had a minimal PATH containing system Node 18. It found
  AgInTi inside an existing Node 22 npm installation, but the CLI's
  `#!/usr/bin/env node` selected Node 18. Its Playwright dependency exited before
  inference because it required Node 20 or newer. Changing providers or reasoning
  effort could not repair that startup failure.

## Runtime Contract

`wechat_agent_backend.aginti_subprocess_env` pairs a Node CLI with its own
installation's `bin/node`, including when the npm executable is a resolved
symlink into `lib/node_modules`. It prepends that directory only for the child
process. It does not source interactive shell startup files, change system Node,
upgrade packages, or alter custom non-Node wrapper environments.

An incompatible Node runtime is an infrastructure failure. Do not retry the same
CLI with LocalLLM or escalate reasoning. Retain diagnostics privately; do not
send Node, Playwright, provider logs, or internal paths to a group.

`wechat_codex_sessions` recognizes model-access rejection separately from quota.
It moves to another eligible account only before any tool activity. A short-lived
cache rejects only the specific account/model pair, not other models on that
account. Quota refresh retains unexpired model rejections. Rejections do not
trigger fresh-thread recovery or network retries, even when stderr also contains
an earlier transient network warning.

Model and provider selection remains in `configs/model-policy.json`. Paid Codex
credits remain disabled. Subscription/reserve availability must be verified;
unavailable Codex work may fall back to AgInTi with DeepSeek. Sandbox boundaries,
exact-chat context, source identity, current-message authorization, and delivery
deduplication apply equally to either backend. Never replay an uncertain tool
side effect on another backend.

## Verification and Recovery

1. Run `labcanvas wechat health --json` and the token-free
   `codex_quota_status.py probe --agentshell-all --json`. Keep their output private.
2. Inspect a failed task's `agent_session`, `worker_policy_attempts`, and native
   backend error evidence. Do not infer quota exhaustion from an empty answer.
3. Run a small read-only Codex turn. Separately simulate only Codex unavailability
   and invoke the real AgInTi backend under the service PATH. The fallback test
   must produce a clean answer, not merely an exit code or a CLI help screen.
4. Test a worker against an existing, explicit file inside an isolated test
   workspace. Verify the tool read and unchanged source. Do not expand read roots
   to compensate for a missing test fixture.
5. Run backend, account-pool, quota, and worker regression tests plus
   `labcanvas wechat selftest --suite all --json` before reloading idle workers.
6. Retry only identified recent failed tasks with `labcanvas wechat worker
   reprocess TASK_ID REASON`. Preserve their source identity and normal delivery
   guards. Do not reset intake cursors or replay the historical failure backlog.

Live checks on October 25 verified a Codex reply, a real DeepSeek reply after a
simulated Codex quota failure, and a real AgInTi file-tool read. These establish
backend execution, not successful retrieval of every external video or article.
Source availability and final chat delivery require their own evidence.

## Daily Review Source Filtering

The daily PDF had a separate source-selection failure. A native outbound file
message for the previous report remained as an XML attachment envelope in the
mirror. The filename-only filter missed it, so the coverage validator required
the next tutorial to cover transport metadata. Rewriting the lesson could not
satisfy that requirement meaningfully.

The source filter now excludes parsed outbound `msg/appmsg` file messages
(`type=6`) as well as bare artifact filenames. It preserves inbound attachments,
normal lesson text mentioning files, and quotation messages. Filtering happens
before source identity, context construction, and coverage checks. Keep the
independent language audit and delivery deduplication unchanged; never approve a
PDF by suppressing a failed quality result.

The completion auditor also distinguishes unavailable source bytes from absent
analysis capability. A precise missing-source blocker must not be "repaired" by
inventing content, demanding a resend, or creating a confirmation gate. This
does not count retrieval as successful or excuse unrelated unfinished requests.
