# WeChat Login Recovery and Astra/Luna Account Routing

## Incident and Verified Recovery

On 2026-10-01 the personal WeChat native client displayed an explicit
"For account security, log in again" dialog. Seven monitor heartbeats were
alive, but their source database could not advance. This was an authentication
blocker, not proof that an agent had ignored newly received messages.

The owner logged in. The existing transport recovered without a client restart,
profile reset, Android interaction, or queue replay. Health then reported seven
ready and caught-up conversations. A queued response completed at 07:39 HKT;
the sender verified it against a native outbound database row. At the following
check, current active, failed, stale, and delivery-blocked counts were zero.
Historical terminal records were retained, not replayed or relabeled successful.

WeCom/LabAgent remains explicitly paused. Personal WeChat recovery never implies
permission to resume WeCom, manipulate the phone, or publish an inbound video.
The current VM console remains http://127.0.0.1:6143/.

## Shared Backend Policy

`configs/model-policy.json` is the default policy for CLI, web, and worker turns:

1. Use GPT-6 Astra with the requested reasoning effort.
2. Use existing authorized AgentShell profiles with current regular quota or
   usable purchased credits. Read quota through the official local app-server
   `account/rateLimits/read`; the read-only monitor spends no inference tokens.
3. If regular attempts are unavailable, consider GPT-5.6 Luna only when the
   account's fresh response actually contains a usable reserve allowance.
4. Preserve the established AgInTi fallback if Codex cannot start safely.

The regular bucket is `rateLimitsByLimitId.codex`. The observed reserve bucket
is `rateLimitsByLimitId.base_model_inference`, with
`normalModelSlug=gpt-5.6-luna`. Normalize these separately. An incomplete optional
reserve bucket must not discard a valid regular quota response. A low regular
percentage alone never proves reserve entitlement or exhaustion.

AgentShell discovery uses existing saved profiles only. It does not create
accounts, edit credentials, or log out another session. Invalid profiles remain
unmodified. Do not log account emails, credit balances, auth files, or raw quota
responses to group chats.

Reserve eligibility requires a fresh, explicitly observed allowance and depleted
regular quota or a verified runtime quota rejection. Reserve-specific rejection
cooldowns do not disable the normal pool. Check reserves lazily after regular
attempts so just-observed quota rejection can be respected without another probe.

Both `wechat_codex_sessions.py` and `workspace_agent.py` use
`agenticapp.codex_accounts.codex_account_attempts`. Keep the same per-conversation
thread and record the model/account/pool actually used. Stop failover once an
answer succeeds or tool activity has occurred; do not replay a publishing,
uploading, generation, or other side-effecting turn on another account.

GPT-5.6 SOL remains a model-unavailable compatibility fallback. Explicit model
overrides remain available. Direct-chat configs can opt into
`use_shared_model_policy: true` to replace stale per-chat model names while
preserving their own timeouts, permissions, prompts, and conversation identity.
New unspecified direct-chat defaults also follow the shared policy.

## Safe Deployment and Checks

```bash
npm test
PYTHONPATH=src python -m agenticapp wechat selftest --suite all --json
PYTHONPATH=src python -m agenticapp wechat health --json
```

Inspect private queue state and native receipts, not just process liveness or a
model's "done" response. Once existing turns and sends are idle, reload only
the owned backend workers/monitors and read-only quota monitor. Keep the native
client, its profile, saved message cursor, and outbound ledger untouched. Never
use a whole-stack restart as a quota-routing deployment mechanism.

The live Astra smoke test used the actual AgentShell invocation and returned
`READY` with no tools or chat delivery. Reserve ordering, actual-model recording,
same-thread preservation, rejection cooldowns, missing entitlement, stale quota,
and the no-replay-after-tools boundary are covered by mocked regression tests.
No live reserve inference was claimed: normal accounts still had quota.

Validation for this change: the full suite passed 2,236 tests with 16 skips;
the worker's guarded `selftest --suite all` also passed before it restarted.
After rollout all seven personal-chat monitors were ready and caught up,
with no current active, failed, stale, or delivery-blocked queue entries.

## Authentication Boundaries

Do not repeatedly click login, dismiss security prompts as ordinary overlays,
restart a healthy client, reset a profile, or probe the mobile GUI. Keep pending
work durable and report a genuine login blocker once. Resume normal intake only
after native state is ready; verify outbound rows before retrying uncertain sends.
No implementation can guarantee that Tencent will never request authentication,
or that every model account will always have quota or network access.

## Official References

- [Luna Reserve in Codex and ChatGPT Work](https://help.openai.com/en/articles/20001499-luna-reserve-in-codex-and-chatgpt-work)
- [Managing usage with GPT-6 Astra in Work and Codex](https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex)

Reserve is a separate, limited allowance available to eligible accounts, not an
unlimited backup. The account's observed response is authoritative for routing.
