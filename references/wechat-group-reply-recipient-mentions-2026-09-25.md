# Group Reply Recipient Mentions

## Behavior

The agent chooses whom its answer addresses from the current same-chat message
ledger and interruptions. For a reply to a question or request, use each actual
recipient's exact display name once in a separate leading line:

```text
@Member One @Member Two
The shared answer.
```

Consecutive requests can still receive one combined answer. Do not mention
everyone in history, quoted authors who did not ask, another group's members,
or the assistant itself. Never use a broadcast mention. General scheduled
briefings, DMs, silent intake, and ignored emoji need no recipient header.
Continuation messages and file attachments do not each need another mention.

This is agent guidance, not a new keyword-based task router or a rule forcing
one answer per inbound message. The shared `wechat_chat_profiles.py` contract
reaches both fast replies and worker tasks.

## Windows WeChat Sender

`wechat_reply_mentions.py` parses only an explicit leading recipient line;
names may contain spaces. `wechat_tiny11_bridge.py` upgrades those names using
the native group member picker in the already verified conversation:

1. Keep the shared GUI lock and refuse to overwrite an existing composer draft.
2. Paste `@`, then the exact name, without refocusing away from the picker.
3. Isolate the newly visible picker beside the editor, excluding unrelated
   history scrollbar repaints. Remove gray row decoration before OCR.
4. Match the entire member label, not a token or a similar name. Ambiguous or
   unreadable labels are not selected.
5. Select each recipient, append the answer, and verify the full unsent draft.
6. Persist the existing native send intent before Enter and verify the native
   outgoing row. A retry reconciles that intent instead of submitting again.

If member selection is unavailable, clear only this invocation's unsent draft
and retain the ordinary named reply. Record this privately as
`plain_name_fallback`; do not claim that plain text notified the member.
Transport failures still propagate and do not become successful mention
fallbacks. No additional group acknowledgement or diagnostic message is sent.

WeChat inserts U+2005 spaces around rich mentions. Normalize these only in the
explicit recipient header for draft and outgoing-receipt comparison. Preserve
the answer content. The same normalization applies to the pending outbound
echo guard so the monitor cannot process its own delivery as inbound input.

Native picker support here belongs to personal Windows WeChat. Existing
WeCom transports retain their own sender behavior; this change does not
unpause WeCom or manipulate Android.

## Verification And Reuse

Live verification used a two-member unsent draft with Latin and Chinese names
in the existing group. Both exact native rows were selected and full draft
readback passed. The draft was removed without sending a test message.
Screenshots and fallback diagnostics stay in the ignored private runtime.
This proves native composition, not receipt of a notification on a member's
phone. Production delivery still requires the native outgoing-row receipt.

Regression coverage lives in `tests/test_wechat_reply_mentions.py`: merged
recipients, names with spaces, duplicate suppression, broadcast/body reference
exclusion, split reply headers, changed scrollbars, exact picker matching,
safe fallback, transport error propagation, rich-draft readback, and outbound
echo suppression. Reuse the shared profile policy and sender routine rather
than adding per-group recipient branches.
