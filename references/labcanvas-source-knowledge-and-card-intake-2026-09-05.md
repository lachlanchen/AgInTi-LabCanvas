# LabCanvas Source Knowledge And Card Intake

## Scope And Boundaries

See `labcanvas-current-goal.md`. This session maintains LabCanvas transports,
task execution, history, and agent context. AgInTi development stays separate.
No authenticated client was restarted for these changes. Android polling and
control remain disabled; WeCom stays on its existing Tiny11 transport.

## Retained Knowledge

`agentic_tools/wechat_gui_agent/scripts/wechat_source_knowledge.py` stores source
material in the ignored private SQLite database
`agentic_tools/wechat_gui_agent/.private/source_knowledge.sqlite` (mode 0600).
This complements, rather than replaces, the immutable message ledger and
existing lifetime-history compaction.

- Verified Shipinhao and exact-source audio/video transcripts.
- Recovered full Gongzhonghao article text.
- Readable PDF/document text, with partial/truncated extraction explicitly
  labelled rather than called complete.
- Agent summaries linked to those sources, separately labelled as synthesis,
  never as the sharing member's personal belief or an authoritative quotation.
- Exact transport/chat/task/source IDs, source paths, content checksums,
  evidence quality, and creation time.

The entire available extracted text is stored, not just a preview. The reader's
existing extraction bounds still apply. An 8 MiB per-text import guard reports a
private error and preserves the original file rather than silently truncating.
The FTS5 trigram index supports Chinese and Latin text. Retrieval is bounded to
the model packet, exact-chat scoped, and includes paths for deeper reading.

The worker calls `retain_source_knowledge` after source preflight and after
producing the final result, before attempting chat delivery. A failed send does
not discard acquired knowledge. A failed/unverified card cannot become a stored
transcript. Rerunning the same import is idempotent. Backend diagnostics and
arbitrary model-returned file paths are not imported as source knowledge.

Both Codex and AgInTi worker packets receive `same_chat_source_knowledge` when
relevant evidence matches the current question. The source paths are private
context, not instructions to echo files or revive old tasks. This change does
not yet add derived-source retrieval to every fast-router or scheduler-specific
context builder; those still have their existing history/memory integrations.

For exact-task recovery without a model call or chat send:

```bash
python agentic_tools/wechat_gui_agent/scripts/wechat_source_knowledge.py \
  --queue agentic_tools/wechat_gui_agent/.private/wechat_task_queue.jsonl \
  --task-id TASK_ID
```

Database failures are recorded in the durable task's `source_knowledge` as
`retry_pending`; the same command retries indexing without rerunning the task.
Partial read/import failures are reported separately. Never claim an import
completed based only on a generated summary or artifact filename.

## Shipinhao Card-Only Recovery

The native route is already part of the worker preflight: use embedded exact
media when valid; otherwise open the same-chat card, verify its identity, copy
the native share link, and pass that URL to the existing authenticated resolver
and downloader. The user should not have to supply a URL manually.

The observed card had Simplified Chinese metadata while Tesseract returned its
author in Traditional Chinese. `shipinhao_gui_audio_capture.normalize_identity`
now applies OpenCC t2s normalization before comparison, as the chat-title
selector already does. This does not weaken source identity to a fuzzy title
guess or allow another card's media.

Install the optional `wechat` package extra, or install
`opencc-python-reimplemented>=0.1.7` in the interpreter used by
`WECHAT_SHIPINHAO_CAPTURE_PYTHON`. The active system worker interpreter and
interactive interpreter were both checked; the system interpreter was missing
OpenCC and received the same 0.1.7 user-site dependency. No browser profile or
login state was changed.

Live recheck found the exact card after normalization, but Linux WeChat did not
open the player after clicking. The result is now correctly classified as
`finder_player_unavailable`, not `finder_card_not_found` or a silent video.
Card-only download is therefore **not yet verified end to end for this client
state**. Preserve this blocker instead of claiming that an original MP4 was
downloaded or delivered.

## Responsiveness

The read-later route previously suppressed every source-task acknowledgement,
even when the agent had written a useful one for an explicit request. It now
accepts a short agent-authored acknowledgement when that chat enables them,
while preserving an empty acknowledgement for a bare share. No generic receipt
is substituted for an empty agent response. Shares enabled this setting.
The final source-grounded response remains owned by the worker. This is not a
periodic heartbeat sender and does not authorize repetitive progress messages.

## Verification

- Regression tests cover retained text/provenance, idempotency, private file
  mode, Chinese retrieval, cross-chat/transport isolation, path/symlink bounds,
  partial PDFs, failed-source rejection, and failed-backend summary rejection.
- Worker tests prove both backend packets carry retrieved source knowledge and
  database errors do not incorrectly fail an otherwise valid delivery.
- Native-card tests cover Traditional/Simplified identity equivalence while
  rejecting an unrelated author/video.
- Two existing verified transcript tasks were indexed locally, each with its
  summary; retrieval was verified. The failed card imported zero records.
- Chat acknowledgements and knowledge retention do not prove GUI sending works.
  Keep the unresolved client/player and delivery failures visible in health.
