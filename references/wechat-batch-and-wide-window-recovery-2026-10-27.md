# Native WeChat Batch And Channels Recovery

## Distinguish Intake, Work, And Delivery

A running monitor and an advanced source cursor do not prove that a reply was
delivered. Inspect the exact task's result, send errors, native receipts, and
source-message coverage independently. Preserve successful research when a
recipient-title check fails; use `wechat_task_worker.py --resend TASK_ID` after
repairing the sender, rather than rerunning the model.

The October 27 incident had three separate defects:

- Header OCR included window controls and message-body text. The first OCR line
  failed the exact-recipient guard even though the intended chat was open.
- A maximized Channels scan calculated the chat-list boundary as 36% of the
  window width. At 1920 px this excluded nearly all of an incoming card.
- A resumed batch answer covered later shares but treated the original unsent
  draft as though it had already reached the chat.

## Geometry And Identity

`wechat_gui_send.title_crop_regions` now bounds the primary header crop between
y=24 and y=72 relative to the window, with a maximum width of 800 px and room
reserved for caption controls. The first-line exact-title check is unchanged;
message-body matches never authorize a send.

`shipinhao_gui_audio_capture.message_pane_region` bounds the chat-list boundary
between 300 and 370 px instead of scaling it indefinitely with window width.
Tests cover widths of 1000, 1440, 1920, and 2560 px. Exact-cover matching and
player title/author verification still gate link recovery.

A saved wide-window screenshot that previously excluded the source card now
matches its exact cached cover at greater than 0.94 confidence. Keep screenshots,
signed links, card IDs, and chat contents in ignored private storage, not git.

## Channels Original-Video Path

1. Resolve the exact same-chat card and its object identity.
2. Use the native helper with `--share-link-only --recover-share-link-first`.
   This opens the identity-checked card and copies its link; it does not record
   the screen/audio, forward to another recipient, or publish externally.
3. Pass the copied URL explicitly as `--recovered-share-url` to
   `shipinhao_media_transcribe.py`. Reuse its identity checks and original-media
   cache. Do not substitute a similar video.
4. Probe the original file, transcribe, and return it through the normal worker
   and guarded sender. Keep the transcript and source knowledge exact-chat
   scoped. Reconcile native receipts before retrying any send.

On the shared workstation, the ignored supervisor environment sets
`WECHAT_SHIPINHAO_WHISPER_DEVICE=cuda:1`; preserve this GPU selection when workers
restart. Do not reset it to unqualified `cuda` and consume another project's GPU.

The live verification recovered a 102.958-second H.264/AAC original, 6,463,340
bytes, with one audio stream. The normal worker delivered the original MP4,
timestamped TXT transcript, and source-grounded summary. Both files have native
send receipts. Source transcript and summary were retained in the private
knowledge index.

There was also an intermittent native player-open failure on an automatic retry.
The successful recovery does not prove every player-open attempt is reliable.
Keep `card_scan`, `player_open`, `share_link`, download, and transcription failures
distinct. A failed attempt is not evidence that the source is silent, deleted,
or requires the user to resend it.

## Consecutive Messages

Keep every source ID in the message ledger while combining related replies.
The interruption prompt now explicitly distinguishes an unsent assistant draft
from a delivered answer. A suppressed draft requires a complete replacement
covering the original request and still-valid updates. Reuse prior research and
never repeat an external action merely to rebuild a reply.

The completion auditor must find substantive coverage of the original item as
well as subsequent items. Phrases such as "the remaining items" are not proof
of an earlier delivery. When an actual delivered-result record exists, return
only the missing supplement. The incident's omitted first article was delivered
as one supplement, without repeating the later batch.

## Validation And Operations

- 780 worker, completion-audit, sender, native-card, and media-transcriber unit
  tests passed; three optional-dependency tests were skipped in the system
  Python. All 22 native-card tests passed in the installed OpenCV environment.
- The saved batch reply and the Channels files were verified in native history.
- Idle worker processes were reloaded through their existing restart wrappers;
  the logged-in WeChat client, monitors, and browser profile were not restarted.
- EchoMind schedules remain disabled. WeCom and Android controls remain paused.

Do not promise unlimited throughput. Durable intake preserves source IDs while
bounded workers process batches; unavailable source media and delivery failures
must remain explicit. A queue row marked `done` with a missing-source answer is
not proof that the source was downloaded or understood.
