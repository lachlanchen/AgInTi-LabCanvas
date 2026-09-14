# Quoted Message Identity And Context

## Observed Failure

Two consecutive requests in the same chat quoted two different Channels
videos. The routing agent requested the quoted originals correctly, but the
worker returned a newer cached video. The routing stage had rendered both
quotes as the same unsupported-version notice. The original quote payloads
were still present in the private message history; intake had not lost them.

The failure was in LabCanvas, before meaningful worker-agent execution:

1. Native reply envelopes contain an entity-escaped `refermsg/content` with
   their own sender, server ID, message type, and source payload.
2. The quote renderer retained only an outer card title. Finder cards often
   use a generic compatibility notice there, not the actual video title.
3. The generic video-download shortcut selected the newest same-chat artifact
   by modification time. Same-chat recency is not quoted-source identity.
4. The shortcut returned an apparent success before the agent handled the
   real request. Nearby media also entered the reference candidate set.

## Correct Contract

- Preserve the current sender separately from the quoted sender. The current
  sender issues the request; quoting someone does not transfer authorship or
  create new authorization from old text.
- Decode the native envelope structurally. Preserve the quoted server ID and
  embedded payload, even when the original message lies outside recent history.
- Match a task source by chat, message shard, and server ID; use local ID only
  when the source lacks a server ID.
- For Finder quotes, use the actual object ID, account, and description from
  the embedded payload, never the compatibility title or a newer card.
- Consecutive quoted requests remain distinct message-ledger items. One
  combined response is allowed, but each referenced source must be covered.
- Explicit references outrank recency. A failed quote decode must not authorize
  selecting another cached file. Preserve the unresolved state for the agent.
- Card download/transcription is not LazyEdit processing or publication.
- Keep raw native payloads and signed media URLs private. Agent packets retain
  readable quote meaning and attribution, not secrets or raw XML.

## Implementation

- `wechat_quote_reference.py`: shared envelope parser and exact task-source lookup.
- `wechat_direct_chatops.py`: meaningful quote rendering and explicit reference
  candidate selection before route/worker execution.
- `wechat_source_recovery.py`: read the quoted source rather than adjacent cards.
- `wechat_task_worker.py`: quoted Finder resolution, backend-neutral quote
  context, and guards against recent-artifact shortcuts, including stored results.
- `tests/test_wechat_quote_reference.py`: escaped envelopes, two consecutive
  quotes, missing original history rows, sender preservation, cross-shard/chat
  rejection, article-versus-video isolation, truncated-context regression, and
  no unrelated cached-video fallback.

## Verification And Recovery

Run `npm test`. Unit tests must not read the workstation's live quota cache or
contend with real scheduler locks. Reproduce source selection from private
stored tasks without making external writes, then reload idle monitor/worker
processes only. Do not restart or log out the official clients.

Use the existing worker `reprocess` operation for specifically affected tasks.
Do not replay the whole queue or resend previously correct unrelated videos.
Verify the recovered source object and outgoing file receipt separately;
correct source selection alone does not prove download or delivery success.
