# WeChat Combined Images and Included-Quota Routing

## Outcome

Windows WeChat merged-display image messages now retain every original in the
native album and pass the complete ordered set to vision. A failed three-image
message was recovered through the ordinary queue and sender. The final reply
used the sender's subsequent product comment; one matching native outbound row
and one successful outbound mirror event verified delivery.

LabCanvas's shared model policy now sets `codex.allow_paid_credits=false`.
Routing uses freshly verified included account quota or an explicitly observed
Luna reserve. A purchased wallet balance does not make an exhausted account
eligible. This applies to the workspace runtime, chat sessions, image reading,
and the legacy GUI chat bridge.

## Native Image Format

The inspected Windows client stored the merged message as three separate type-3
rows, each containing an ordinary image resource and common membership metadata:

```xml
<msg>
  <img />
  <extcommoninfo>
    <groupinfo>
      <type>1</type>
      <id>NATIVE_GROUP_ID</id>
      <count>3</count>
    </groupinfo>
  </extcommoninfo>
</msg>
```

The display collage is not the source image. Never group files by modification
time, a nearby thumbnail, or visual similarity. Membership must match the
account, exact chat table, group ID, declared count, and native sender. Retain
each member's native message identity and order.

`wechat_combined_images.py` parses the bounded metadata and rejects DTD/entity
declarations. `wechat_tiny11_image.recover_images` resolves membership against
the existing read-only host mirror, then calls the established guest original
image exporter for each member. The existing SSH transfer, native length/hash
checks, full-resolution validation, and lossless wxgf decoding remain in use.
The first image export is reused rather than fetched twice.

An incomplete mirror snapshot gets a short bounded wait for the exact members.
An identity mismatch fails immediately. A mixed image/video group requires the
separate video intake contract; this feature does not authorize video processing
or public publication.

## Worker and Context

The worker preserves all verified originals in `source_media/` and `intake/`,
removing the former one-image intake limit for complete native albums. The
private `native-combined-image-export.json` records the ordered original paths
and identities. Native manifests have mode `0600` and stay under ignored output.

One joint vision call reads all images with their text and relationships. File
intake reuses the successful joint result instead of reading every image again.
Group vision runs from the same chat workspace under its read-only permissions.

Media resolution remains bound to the exact source row, while vision receives
the same chat's answer context. A correction or interruption returns control to
the resumed chat agent rather than returning an old caption directly. No other
group's files, memories, or publication authority become available.

Separate monitor polls for sibling rows deduplicate pure album intake against
the same native album. Their numbered message ledger entries are retained. A
later text instruction is not classified as duplicate album intake.

When the main message is text, current numbered `coalesced_source` image entries
can select the native image anchor. Every candidate is checked against the same
native chat/database; multiple candidates must belong to one verified album.
The worker then expands that album, including members from an earlier poll.
This fixes the image-then-comment case without selecting arbitrary old images
from conversation history. Ambiguous separate albums remain explicit.

## Quota Contract

`src/agenticapp/codex_accounts.py` owns account selection. The token-free
`codex_quota_status.py` monitor reads the official local app-server quota state.

- Normal attempts require fresh positive included quota when paid usage is
  disabled. Unknown, stale, future-dated, and exhausted observations are rejected.
- An explicit pinned account still passes the quota gate.
- Reserve attempts require a fresh, positive, separately observed reserve bucket
  matching the configured model. They are not inferred from regular exhaustion.
- The verified local reserve model for this deployment is `gpt-5.6-luna`.
- There is no implicit default-account execution when the eligible pool is empty.
- Purchased-credit retries are disabled even if a per-chat configuration enables
  them. Existing safe backend fallback behavior remains available.
- Account failover preserves the thread and stops once tools have run, avoiding
  duplicate external actions.

The live probe found two accounts with regular included allowance and another
with usable reserve. Account identities, wallet balances, tokens, and raw quota
payloads remain private.

This is a local admission/routing rule, not a server-side spending cap. Other
sessions share the accounts, and quota can change after a cached observation or
during a long turn. A before/after shared-wallet comparison cannot establish the
cost of one LabCanvas call while other sessions are running. Do not claim that
such a comparison proves zero paid usage. Never deliberately retry against an
exhausted paid account under this policy.

## Operations and Recovery

Use the existing task ID when recovering a missed album:

```bash
PYTHONPATH=src python -m agenticapp wechat worker reprocess TASK_ID \
  'Read the complete original album and answer the same-chat follow-up.' --send
```

This invalidates the old execution generation and rebuilds preflight. Inspect
the final queue state, original count, semantic reply, and native delivery
receipt. A `done` label alone is weaker evidence than the native outbound row.
Normalize the outgoing rich mention with the sender's `mention_header` helper
when comparing: WeChat stores editor padding differently from the task's draft.
Do not resend a successful reply to obtain another receipt.

Refresh quota observations without an inference call:

```bash
python agentic_tools/wechat_gui_agent/scripts/codex_quota_status.py \
  probe --agentshell-all
```

Inspect quota output privately; it can contain account and billing metadata.
Reload only idle project-owned workers and monitors after changing their code.
Keep queue state, cursors, session registries, and send receipts. An existing
paused WeCom queue remains paused. Image recovery needs no phone input, client
restart, new browser profile, VM restart, or login reset.

## Verification

The live three-image album exported three distinct original-resolution files in
native order. A joint Luna vision smoke test read all three. The normal worker
then recovered the failed task, retained all three originals through intake,
and delivered a context-aware reply once. Private evidence is under
`output/wechat_combined_images_validation/20261004/`.

Regression coverage includes exact membership and ordering, wrong sender/count,
missing members, mixed video groups, original manifests, joint vision, full
intake retention, sibling deduplication, later instructions, read-only group
workspace selection, stale/unknown/pinned account gates, reserve routing,
disabled credit retries, and empty-pool behavior without a default invocation.

```bash
WECHAT_TINY11_DISABLE=1 PYTHONPATH=src python -m unittest discover -s tests
```

The transport override isolates unit tests from the workstation's live Windows
configuration. It is not a production setting. Live original recovery and
native delivery were verified separately against the existing client.
