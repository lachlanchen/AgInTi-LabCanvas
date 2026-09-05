# LabCanvas Source Knowledge And Card Intake

## Scope And Boundaries

This is a chronological investigation. The later **Card-Only Live Verification**
section supersedes the earlier unresolved player/download status; it preserves
those earlier observations without treating them as current blockers.

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
context, not instructions to echo files or revive old tasks.

The direct-chat route prompt and both normal and EchoMind fast-reply prompts
also retrieve relevant source evidence. They use the exact configured chat and
transport, the current question (the coalesced request for routing), and a
read-only SQLite connection. `source_knowledge_char_budget` defaults to 3000,
supports zero to disable, and is capped at 8000. The lookup has a 250 ms
lock/query budget so it cannot hold up fresh chat indefinitely. A failed lookup
leaves current-message handling available and tells the agent not to invent
recalled source content; database diagnostics stay private. No extra model
invocation or automatic chat send is introduced.

This still does not add derived-source retrieval to every scheduler-specific
context builder; those retain their existing history/memory integrations.

For exact-task recovery without a model call or chat send:

```bash
python agentic_tools/wechat_gui_agent/scripts/wechat_source_knowledge.py \
  --queue agentic_tools/wechat_gui_agent/.private/wechat_task_queue.jsonl \
  --task-id TASK_ID
```

Database failures are recorded in the durable task's `source_knowledge` as
`retry_pending`. Idle worker maintenance now retries one due index after
pending work and due deliveries have had priority. It uses a 250 ms SQLite
lock wait, a nonblocking maintenance lock, and exponential backoff from 30
seconds up to 30 minutes. Legacy retry markers without a deadline are due
immediately. The source-knowledge field is reconciled against the current task
generation and state; newer transport results and newly arrived queue rows
are preserved. No queue lock is held while indexing. SQLite schema, write,
and read connections are explicitly closed.

This maintenance performs no source retrieval, model invocation, task rerun,
or chat send. It does not reset delivery status or revive an expired response.
The same exact-task command above remains available for operator indexing.
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

## Native Window Cleanup

`wechat_window_control.request_close` sends the application's advertised
`WM_DELETE_WINDOW` protocol instead of `xdotool windowclose`. The latter uses
`XDestroyWindow`, which bypasses normal application close handling. Destroying
an auxiliary Qt window is not evidence that its modal/application state has
been cleaned up.

The helper verifies same-user WeChat process ownership, excludes the protected
main window, and refuses unsupported close protocols. Install `python-xlib`
through the optional `wechat` extra in the actual sender interpreter. There is
no process-kill or force-destroy fallback when a close request is rejected.
Channels cleanup is bounded and reports `finder_player_close_pending` if an
already-requested window remains, rather than looping indefinitely.

Live checks removed an auxiliary window normally without restarting WeChat or
altering its login. This did **not** resolve the native player-opening failure.
X input probes showed raw button events, but the card still did not open; that
does not identify a definitive application or X-server root cause. Do not
claim this cleanup fix completed download or delivery. Android control remains
disabled, and no recording was substituted for the original video.

The no-URL card regression uses WeChat's packed type `219043332145` with a
`finderFeed` object ID. It must request source download/transcription/return,
never ordinary-video passive intake or publication.

The Shares inbox prompt previously contradicted that contract: a later generic
source-summary instruction prohibited artifact return without an explicit file
request. Shipinhao cards now reuse `automatic_wechat_source_instruction` in
the inbox too. The route-agent prompt explicitly preserves this exception and
ordinary-video save-only intake. No-URL cards request native link recovery and
the existing GPU 1 transcription routine, not a recording substitute. Source
IDs stay in the structured ledger; the agent uses exact local/server references
rather than receiving raw signed metadata in its human-facing task text.

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
- Fast-chat tests use temporary databases and prove source retrieval in routing,
  ordinary chat, and EchoMind prompts; exact-chat/transport isolation; disabled
  retrieval; and continued routing on a private database error. A locked SQLite
  database test checks the lookup deadline.
- Idle-maintenance regressions cover database retry/backoff, queue contention,
  concurrent delivery updates, newer knowledge state, active-task exclusion,
  and one-task-per-pass behavior. Schema/write connection closure is tested.
  Validation on September 5: 594 worker tests, 183 direct-chat tests, 12 source
  knowledge tests, and the full WeChat self-test suite passed. A live internal
  maintenance invocation found no pending knowledge retry and sent nothing.

## Continued Live Audit

An ephemeral Xlib test window on the existing WeChat display received real
XTEST motion, button press, and release events. Its window was destroyed after
the test and the original pointer position restored. This narrows the failure:
the virtual input path works in that isolated test, while WeChat's native
player/file-picker actions still fail. It does not prove the client is healthy.
Normal single-instance activation exited without replacing the logged-in
primary client. No client restart, profile deletion, phone control, or new GUI
stack was performed.

A later, different source link was picked up by the system, downloaded, and
transcribed. Its source knowledge was stored automatically, including after
file delivery failed. Its queue record remains deferred for required artifact
delivery. Do not substitute that source for the earlier no-link card or report
queued files as sent. The WeCom Tiny11 transport remained ready during checks.

## Card-Only Live Verification

The owner authorized a fresh test of the original card. With the existing
logged-in Linux client able to open its native player, LabCanvas recovered the
share link itself, downloaded the original 374.863-second H.264/AAC video
(15,633,847 bytes), transcribed 116 timestamped segments using GPU 1, and stored
the transcript and synthesis in the exact chat's source knowledge. The MP4,
transcript TXT, and agent-written summary were delivered to the source chat.
This verifies this client/card, not every possible Channels share or account.

The fixes are reusable worker behavior, not a separate operator downloader:

1. `should_prepare_media_resolution` leaves Finder sources to their existing
   exact-card resolver. Generic attachment scans had spent several minutes on
   irrelevant thumbnails and vision before reaching the native card.
2. Try the exact embedded media first, then the native share link, before costly
   public-mirror research. Keep content-verified mirror recovery as a fallback.
3. `shipinhao_gui_audio_capture.py --share-link-only` opens the exact same-chat
   card under the shared GUI lock and verifies title/author. In this Linux
   player the copy-link item is in the bottom share-arrow menu, not the browser
   three-dot menu or ordinary context menu. The menu crop is enlarged 3x for
   OCR. Coordinates only open the menu; clicking requires an exact copy-link
   label. Forward-to-contact items are never selected. A fresh clipboard marker
   prevents accidentally accepting a previous card's URL.
4. Pass the copied URL explicitly as `--recovered-share-url` to
   `shipinhao_media_transcribe.py`. Appending it after Finder XML was insufficient:
   the parser correctly prioritized the card and ignored the appended URL.
   The explicit handoff still checks the resolved title/author and share token,
   and preserves the original object ID for the private cache and provenance.
5. Release the GUI lock and close only the owned auxiliary player before the
   network download and ASR. Automatic source recovery never records the screen
   or audio as a substitute original. The legacy capture tool is retained only
   for explicitly requested diagnostics, not this default path.

Delivery verification exposed two additional bugs. The sender renamed the files
but the completion gate still required their old paths. Required paths now map
to an existing alias only after same-file or byte-count/SHA-256 verification.
Missing or changed aliases cannot satisfy delivery. The receipt-repair helper
also used to create a new supplemental filename for every already-sent file;
that produced a duplicate attachment pair during this test. It now preserves
unchanged files for normal receipt/response repairs. Explicit rebuilt-artifact
recovery retains its supplemental delivery behavior. Do not resend this test
again to demonstrate the fix; test duplicate suppression with mocked senders.
Future source aliases use the card title from preflight, not the generic
forwarded-message instruction wrapper. Private evidence retains the original
names and identity; already-delivered files are not renamed and sent again.

The direct monitor now recognizes a pending native text-send receipt before
the sender has finished recording success. It requires the exact configured
self account, chat table, message text, database shard, post-send local ID, and
send-time window. This closes the race where the system could answer its own
message while still permitting genuine messages from the owner using the same
account. The live summary was recorded as `self_outbound_echo`, with zero new
route candidates. Do not implement this as a blanket self-account exclusion.

### Use And Recovery

Normal use: share a Channels card in a monitored chat. No pasted URL or second
command is required. The agent receives the verified transcript and current
same-chat request, and supplies one concise source-grounded summary alongside
the video and transcript. Plain inbound videos remain passive save-only unless
a current instruction requests more; no public publication is authorized here.

For an operator's exact-task delivery-only repair, use:

```bash
PYTHONPATH=src python -m agenticapp wechat worker repair-result TASK_ID --send
```

Inspect native send receipts and the queue first. This command must reuse the
stored result and delivered-file ledger, not rerun the source download, model,
ASR, or publication. Source-unavailable, copy-link failure, download failure,
and ASR failure are distinct from genuinely silent media.

Regression coverage includes exact copy-link menu selection, no-capture mode,
explicit URL handoff and conflicting identities, thumbnail-scan avoidance,
pre-receipt self-echo suppression without losing owner commands, alias content
validation, and unchanged-file repair deduplication. Private live evidence stays
under the ignored task directory; never commit card URLs, raw chats, or media.
