# Channels cards: recover the link before asking the sender

## Default contract

A genuine inbound Shipinhao/Finder card is sufficient input. Unless the current
sender requests otherwise, resolve that exact card, recover its native share
URL when necessary, download the original, transcribe through the configured
GPU 1 routine, and return the video and transcript with one concise agent
summary. Public publishing is a separate permission and is never implied.

Ordinary uploaded video attachments retain their passive save-only default.
Explicit save-only, no-transcription, and other current instructions override
the card default. Keep per-message sender identity, exact quotes, and chat
isolation. Do not substitute a similarly titled cached clip or a screen capture.

An expired embedded URL is an input to native link recovery, not a request for
the user to paste a URL. Reuse the active transport, the exact source card, and
the existing downloader. If recovery genuinely fails, report its actual stage
once, without claiming the video is silent or automatically requesting login.
Do not repeatedly post a failure followed by another link request.

## Observed failure and repair

The recent reproducible failure was on Windows personal WeChat. Routing already
requested automatic original download, but native recovery reported
`exact_card_not_visible` despite the card being visible. The cover matcher
tested scales in 2% increments. A 720-pixel cover rendered at 247 pixels fell
between those samples; the best coarse match was below the unchanged 0.80
threshold. Searching integer widths around the best coarse scale found the
same card above that threshold. This is scale refinement, not a relaxed or
fuzzy content-identity rule.

The native helper still restricts candidates to the received-message region,
uses the verified Copy Link action, and checks the resolved full title and
author. Download and transcription start after releasing the GUI lock. The
helper closes only its own player, preserving the logged-in client.

A separate intake bug let third-party mentions or publication language in a
card caption create a publication-consent wait. That check now reads human
text from the current coalesced batch, or the request portion of a reply,
not source captions or the quoted author's text. Real same-chat permission
questions still wait for confirmation.

## Implementation map

- `agentic_tools/wechat_gui_agent/scripts/shipinhao_gui_audio_capture.py`:
  `exact_cover_candidates`, coarse-to-fine size matching.
- `agentic_tools/wechat_gui_agent/scripts/shipinhao_tiny11_share_link.py`:
  exact card, silent native opening, Copy Link, resolved identity checks.
- `agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py`:
  native-link preflight, explicit `--recovered-share-url` handoff, original
  download, transcript, source-grounded synthesis, and normal delivery.
- `agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops.py`:
  distinguish human publication instructions from shared source captions.
- `agentic_tools/wecom_agent/scripts/wecom_ingest.py`:
  WeCom card and attachment-preflight prompts use the same download-first
  default instead of only discussing the preview and possible papers.

The WeCom prompt update is not proof that a Windows WeCom card can be opened
with the personal-WeChat helper. They have separate clients and source IDs.
Use the active WeCom adapter for that source; never silently navigate the
same-named personal-WeChat group. A live WeCom card needs its own verification.

## Verification and recovery

Use `npm test` for the repository suite; its runner isolates live transport
configuration. Direct invocation on this workstation otherwise reads the
private Windows-enabled setting and can invalidate Linux-transport fixtures.
Use the existing OpenCV environment to run `test_shipinhao_gui_audio_capture.py`
as well, so the image-matching tests actually execute rather than skip.

Regression coverage includes between-scale thumbnail matching, rejection of an
outbound-only cover, native resolved title/author mismatch, preservation of an
already-open player, card-caption consent isolation, and WeCom default prompt
requirements. Never test by reposting an already delivered card.

For an exact failed task, use `wechat_task_worker.reprocess_task` once after
fixing the cause, then monitor the existing supervised worker. Preserve the
task ID and private source evidence. Confirm original-media probing,
transcription, and native delivery receipts before calling delivery complete.
Do not reset or replay unrelated queues.
