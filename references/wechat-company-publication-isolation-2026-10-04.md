# Company-chat publication and memory isolation

## Verified failure

A company group discussed content-production products. It had no source video
or current publication instruction. Nevertheless, the monitor sent a
publication-consent acknowledgement, later announced authorization, and sent
missing-video diagnostics twice.

The private queue and exact native outbound echoes showed this sequence:

1. A pre-routing shortcut interpreted an unrelated member mention plus
   publishing-related words as a permission request, before the agent could
   classify the business conversation.
2. A subsequent planning question quoted the assistant's earlier product
   description. The requester-override check included that quoted text and
   mistook its publishing words for fresh authorization.
3. Exact-source resolution failed. The task had neither a verified video nor
   an imported video ID or publish poststage. Its recorded result states that
   no video was inspected, imported or submitted. This is not evidence that a
   video was published.
4. Separately, the shared strategy-context helper included private memo/DM
   memories and a global repository inventory in company tasks. That was a
   genuine cross-chat context violation, even though the bogus publish task
   itself originated inside the company chat.

Raw messages, native IDs, queue records and registry backups stay private.

## Persistent correction

- Set operator-owned `public_publish_enabled=false` for a chat with no public
  publication privilege. Do not hardcode the company's name into routing.
- Keep ordinary company discussion and research enabled. A request may
  override a profile's focus, not the operator's permissions.
- A member mention plus a publication word is insufficient to create a consent
  task. Require an actual permission question and a same-chat video reference;
  in agent-first mode, require the agent's publication-consent decision too.
- Do not force an agent's business/research route into publication merely
  because a heuristic sees permission-related words.
- Remove native/rendered quote evidence for authorization checks only. Keep
  quotes intact as evidence in the reasoning packet. Preserve later authored
  instructions in coalesced batches, including nested quote brackets.
- Propagate the permission denial through direct, Codex and AgInTi task packets.
  Recheck current source-chat configuration for old queued publication tasks
  before deterministic preflight or agent invocation. Guard deterministic and
  generated-video publication entrypoints as well.
- Strategy context uses the exact source chat only, with no implicit personal
  alias expansion or workstation-wide repository inventory.
- Detach contaminated per-chat session pointers after private backup. Do not
  delete conversation history, threads, source artifacts or other groups'
  sessions. New turns rebuild from the originating chat's own evidence.

The worker and prompt controls are not an OS sandbox for an unrestricted agent.
They enforce the normal LabCanvas route and deterministic publication paths;
use a separate restricted runtime when hostile-user isolation is required.

## Verification

`tests/test_wechat_publication_authorization.py` covers business mentions,
missing videos, agent-owned intent, quoted authorization, later coalesced
instructions, disabled consent, incorrect router output, stale queued
permissions and exact-chat strategy memory. Existing publication-consent and
worker suites must continue to pass for authorized personal groups.

Reload idle monitor/worker processes only after confirming there is no active
turn; preserve durable cursors and queues. Do not restart WeChat/WeCom, operate
the phone, send a test message or replay historical tasks to validate this fix.
Use local regression tests and a read-only replay of the offending source
against the new authorization/permission functions.
