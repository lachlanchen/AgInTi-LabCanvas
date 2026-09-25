# Windows WeChat Channels Originals and Send Reconciliation

## Scope

Use the selected Windows WeChat account in the existing Tiny11 console. The
shared console is `http://127.0.0.1:6143/`; WeCom remains a separate app and chat
transport on that desktop. Reuse the authenticated helper and shared GUI lock.
Do not inspect the inactive Ubuntu client's QR screen, restart clients, or
operate Android when Windows is the selected transport.

This workflow downloads the exact original Channels video, transcribes its
audio on the configured GPU 1, and returns the video, readable timestamped
transcript and one natural summary to its source chat. It does not authorize
public publication. Ordinary uploaded videos without a current instruction
remain passive save-only input.

## Source Selection

`wechat_task_worker.py` recovers Finder XML from the current task's exact source
row or an explicitly selected reference in its same-chat context. The database
identity must also match. A follow-up such as "download this" needs the routing
agent's uniquely matching title and author, a named work plus author, or an
explicit object ID from the recovery instruction. Never choose an arbitrary
latest card or substitute another chat's media.

Route normalization must preserve the agent's source-selection reason. Replacing
that reason with generic policy prose can erase the only link between a text
instruction and its preceding card. Current coalesced source messages still take
precedence over older context. Ambiguous selections remain unresolved.

Each task keeps its own object ID, original media, transcript, source-knowledge
record, result and delivery ledger. Three cards are three sources even when they
arrive consecutively in one conversation.

## Native Copy Link Adapter

The worker automatically calls
`agentic_tools/wechat_gui_agent/scripts/shipinhao_tiny11_share_link.py` when its
existing exact-media recovery needs a fresh link. For a read-only diagnostic:

```bash
<VISION_PYTHON> agentic_tools/wechat_gui_agent/scripts/shipinhao_tiny11_share_link.py \
  --chat '<EXACT_CHAT>' \
  --source-text-file '<PRIVATE_TASK_DIR>/exact-source-card.txt' \
  --output-dir '<PRIVATE_TASK_DIR>/windows-native-link'
```

The service Python can lack OpenCV even when the existing workstation vision
environment has it. `shipinhao_native_link_python()` respects an explicit
`WECHAT_SHIPINHAO_CAPTURE_PYTHON`, otherwise probes existing interpreters for
`cv2` and Pillow. `pip install '.[wechat]'` declares the vision dependency for
new installations. Do not create environments or install dependencies per card.

The adapter:

1. Validates the exact chat and card identity before GUI input.
2. Uses the card's original cover, with centered thumbnail variants for the
   native Windows card layout, to locate the received card in bounded history.
3. Chooses the exact native Silent Play item and reads the player footer.
4. Copies the link from the native menu without forwarding to a recipient.
5. Uses a fresh clipboard marker and waits for the asynchronous link update.
6. Rechecks the pane and preserves the candidate link privately.
7. Closes only the native tab this invocation opened and releases the GUI.

An already-open user player is preserved. GUI failure is not a login failure
and not evidence of silence. Do not replace original media with a screen or
audio recording. After releasing the GUI, the existing resolver independently
requires the complete title and author to match the original card before the
helper returns a recovered source. Collapsed titles and OCR errors do not
weaken this gate: a read-only candidate link is not yet a verified source.

Pass the copied URL explicitly as `--recovered-share-url` to the existing
`shipinhao_media_transcribe.py`; appending it after XML is not a reliable API.
Download and ASR happen after releasing the GUI lock. Keep signed URLs,
screenshots, native rows and transcripts in ignored private/task storage.

### Full Identity, Not Preview Text

On 2026-09-25 a card-only run copied the correct native link but rejected it
as `native_link_resolved_title_mismatch`. The card parser and link resolver
both truncated captions to 300 characters, using different ellipsis rules.
Their identity strings therefore disagreed even for the same video. A later
user-pasted link worked, incorrectly suggesting that a pasted URL was needed.

`extract_shipinhao_media_profile()` and `normalize_provider_result()` now
preserve the complete whitespace-normalized caption and author. Display and
prompt previews may remain bounded, but those previews must never become
identity fields. Keep the existing normalized title AND author equality gate;
do not accept matching prefixes, approximate OCR, or an unrelated recent card.
Regression tests cover long fields and reject different identities whose first
300 caption characters or 160 author characters happen to be identical.

A live read-only retest supplied only the original card XML to the native
adapter, with no share URL. It recovered and verified the link, downloaded a
135.208-second H.264/AAC original (7,240,468 bytes), and produced 52 transcript
segments on GPU 1. Its SHA-256 matched the independently downloaded original
from the successful URL-based run. No messages or files were resent. Preserve
the private native-link receipt and transcript manifest as evidence; do not
commit chat content, share links or media.

This is the shared worker path for all monitored personal-WeChat groups, not
a per-group workaround. An expired embedded media URL should trigger native
Copy Link recovery before an evidence-limited failure response. A card alone
is sufficient input when that exact card remains accessible in the selected
logged-in client. Deleted/restricted content and real login failures are still
possible; report the actual blocked stage rather than claiming every failed
recovery means an invalid link or asking for a pasted URL as the first step.

## Native Player Focus and Renderer Recovery

The native web player uses `WeChatAppEx.exe`, a child process with its own
top-level window. Focusing `Weixin.exe` again before clicking Copy Link closes
the menu without copying anything. `WeComBridge.ps1` now preserves focus only
after checking the executable's app-specific path, interactive session, live
process ancestry and parent creation times. A generic browser or the other
chat app does not pass. Existing point bounds and app capture isolation remain.
The helper health endpoint exposes process/window identifiers for private
diagnosis without publishing window contents or credentials.

A separate observed failure was over 1,300 personal-WeChat renderer processes,
blank player pages and helper timeouts. Do not diagnose that as an expired
login. `windows/Repair-WeChatWebRuntime.ps1` is a dry-run-first operator routine:
stage it through the existing SSH transport, inspect its result, and use
`-Apply` only for a verified runaway native web runtime. It requires at least
64 renderers, a verified personal-WeChat parent and executable path, then stops
only that renderer tree. It checks that the client process identities remain
unchanged. It does not reboot, log out, clear profiles or restart chat clients.
Native WeChat recreates its own browser component when needed. Serialize this
repair with the shared GUI lock and preserve any active user work first.

The Windows delivery inbox and shared helper installation can have different
roots. Read the scheduled task's actual helper path before deploying; do not
assume the personal transport's `remote_root` is the helper installation path.

## Why a Video Was Sent Twice

The Windows composer held an attachment whose clipboard text was empty. After
a failed filename preview check, a retry treated that non-text draft as empty
and pasted the same file again. Enter then sent both attachments.

The sender now records a draft before pasting and detects non-text attachment
chips as well as clipboard text. A retry verifies its existing draft instead
of pasting again. An unrelated user draft is not overwritten. OCR checks the
isolated filename label as well as the full composer block; truncation must
retain exact filename prefix and suffix, not a fuzzy match.

Native send intent is persisted before Enter. An uncertain submission is
reconciled, not clicked again. Task/content delivery keys remain stable across
recovery and filename changes. Text and file receipts are independent, so a
missing transcript can be delivered without resending its video.

## Native Video Receipt

Windows WeChat can change an MP4 container while retaining its original audio
and video packets. Its outgoing row is type 43, not the type-49 document row
used for PDFs. Filename/total-byte matching alone cannot verify that video.

`wechat_tiny11_media_receipt.py`:

1. Reads the exact outgoing row in the expected chat, after the saved cursor,
   with the self sender, successful status and nonzero server ID.
2. Uses that row's `rawmd5` and `rawlength` to find the exact raw video in the
   active Windows account's month-specific native cache. Size only narrows
   discovery; the digest selects the file.
3. Copies it through the existing SSH/SCP connection and verifies size/digest.
4. Compares every video/audio stream's SHA-256 using FFmpeg stream copy. No
   decoding, re-encoding or visual-similarity substitution is used.
5. Records the proof and native digest alias in the outbound file ledger, so
   the native echo cannot become a new user task.

An absent or nonmatching proof remains uncertain. Do not label it successful
or resubmit blindly. A future codec-changing upload needs a separately reviewed
verification route; this verifier deliberately accepts unchanged streams only.

## Recovery and Tests

Use the existing worker, not a second hand-written delivery pipeline:

```bash
PYTHONPATH=src python -m agenticapp wechat worker repair-result '<TASK_ID>' --send
```

This repairs a stored completed result without rerunning the agent or task
tools. Reprocess a source task only when source work is actually missing; do
not reset completed delivery records to force another upload. Inspect the exact
native receipt before retrying any old `send_uncertain` task.

Run isolated tests without adopting the workstation's live private transport:

```bash
WECHAT_TINY11_DISABLE=1 PYTHONPATH=src python -m unittest \
  tests.test_shipinhao_tiny11_share_link \
  tests.test_wechat_tiny11_media_receipt \
  tests.test_wechat_tiny11_bridge tests.test_wechat_task_worker
```

Reload only idle worker processes after tests. Preserve running chat tasks,
client logins, read cursors and the shared desktop. Record live source and
delivery evidence privately; passing unit tests alone is not proof that a
recipient received the requested files.
