# WeChat Shipinhao Audio Transcription Workflow

## Purpose

This workflow lets a LabCanvas worker read a WeChat Channels/Shipinhao share as source material, transcribe its actual audio, summarize it with the chat's resumed agent session, and return the answer to the originating chat. It is read-only: opening the shared card and recording local playback does not like, follow, comment, repost, or invoke Yuanbao.

## Evidence Pipeline

1. Resolve the exact current WeChat row and parse its `<finderFeed>` block.
2. Bind the task to `objectId`, title, author, nonce ID, duration, and media URL hash.
3. Try the allowlisted Tencent media URL with bounded download and SSRF guards.
4. If the signed URL expired, automatically open that exact card in the guarded source chat.
5. Normalize to the latest message and scan bounded recent history. Associate a play control only with nearby title/author OCR from the same card.
6. Run an identity-gated local capture. Wait for or start the `WeChatAppEx` PipeWire stream once, then record while visual source identity remains valid.
7. Stop after consecutive identity loss or the card duration upper bound, trim the source-only audio, and write `verified-capture.json` below the private object-ID cache.
8. Transcribe with Whisper, write timestamped Markdown, and pass only the source-scoped transcript to the resumed per-chat worker agent.
9. Send the natural summary through the guarded same-chat sender and verify `sent`, `done-sent`, and `synced` mirror states.

## Native Capture

Automatic same-chat capture:

```bash
python agentic_tools/wechat_gui_agent/scripts/shipinhao_gui_audio_capture.py \
  --object-id '<OBJECT_ID>' \
  --title '<EXACT_CARD_TITLE>' \
  --author '<EXACT_AUTHOR>' \
  --chat '鏈接' \
  --expected-duration-seconds 42 \
  --display :97 \
  --json
```

For an exact player already visible, omit `--chat` and supply distinctive `--identity-term` values. The helper:

- takes the serialized WeChat GUI lock;
- opens only the configured source chat and rejects a failed title guard;
- parses Tesseract TSV literally so quote characters cannot merge unrelated rows;
- binds a play control only to OCR evidence in its local card neighborhood;
- selects a PipeWire output whose process binary is `WeChatAppEx` on the same display;
- OCRs player title and footer regions without navigating or posting;
- records with `pw-record` while source identity remains visible;
- detects feed auto-advance or uses duration as a bounded stop while identity checks continue;
- stores hashes plus source identity evidence in a private manifest.

Monitoring is local and does not poll Codex or consume model tokens.

## Transcription

Automatic workers discover the matching private manifest by object ID. Manual verification is available with:

```bash
python agentic_tools/wechat_gui_agent/scripts/shipinhao_media_transcribe.py \
  --source-text-file '<TASK_DIR>/shipinhao_media_transcript/exact-source-card.txt' \
  --capture-manifest '<PRIVATE_CACHE>/<OBJECT_ID>/verified-capture.json' \
  --output-dir '<TASK_DIR>/shipinhao_media_transcript' \
  --model turbo \
  --json
```

`--captured-audio` remains an operator diagnostic input. Autonomous workers use `--capture-manifest` because it validates object ID, title, author, private path, identity terms, and SHA-256 before trusting audio. Every captured-audio cache name includes the audio hash, preventing one capture from overwriting or silently reusing another.

## Failure Contract

These outcomes are intentionally different:

- `no_audio` with `verified_silent_media=true`: readable media was probed and contains zero audio streams.
- `failure_stage=download`: the signed Tencent URL failed or expired.
- `error_code=finder_card_not_found`: the exact source card was outside bounded history or could not be identified.
- `error_code=finder_player_unavailable`: the exact card was found, but the Linux client did not open its player.
- `error_code=finder_audio_stream_unavailable`: the verified player produced no capturable PipeWire stream.
- `error_code=wechat_gui_busy`: another guarded GUI operation owns the serialized lane; retry later.

Only the first outcome means the video is silent. All other outcomes preserve card, comment, and public reconstruction as weaker evidence and require an evidence-limited answer. They must not be rewritten as “the video has no audio.”

## Worker Reprocessing

After a verified capture becomes available, rerun the original source-scoped task rather than creating a detached summary:

```bash
labcanvas wechat worker reprocess '<TASK_ID>' \
  'Verified Shipinhao capture is ready; transcribe and summarize the exact source' \
  --send
```

The worker writes `task.preflight.shipinhao_media_transcript`, resumes the exact chat's agent session, and sends the selected response to the task's original chat. Comments are a separate auxiliary source. Transcript and capture manifests are not comment exports.

## Failure Rules

- Reject a capture if card or player visual identity does not match.
- Never authorize a card click from title text in a later bot reply.
- Never reload the player after selecting a PipeWire stream; reload may replace the audio node and pair the visible card with a different stream.
- Treat nominal duration only as an upper bound while visual identity checks continue; do not use it as source identity proof.
- Never reuse a capture from a different object ID or chat.
- Do not expose signed URLs, private chat rows, screenshots, audio, or full transcripts in git.
- If no exact media, verified capture, transcript, or reliable reconstruction exists, give an evidence-limited answer instead of claiming the video was watched.
- Posting a comment or Yuanbao prompt remains a separate explicit write action.

## Validation Record

The 2026-07-15 live validation recovered a roughly three-minute art lecture, detected the following feed item, produced a source-only Whisper transcript, ran the normal resumed worker agent, and verified the reply in the native chat plus SQLite mirror. A deliberately mixed capture was rejected before delivery.

The 2026-07-16 regression test bound the exact TED card by local title terms after its signed URL returned HTTP 400. Linux WeChat did not open that unsupported Finder player, and the tool correctly returned `finder_player_unavailable` rather than `no_audio`.

## Open-Source References

- `nobiyou/wx_channel`: Channels identity/comment API patterns.
- `qiye45/wechatVideoDownload`: official-client media interception reference.
- `lecepin/WeChatVideoDownloader`: Channels media download architecture reference.

These projects are references only. LabCanvas keeps its source binding, private cache, transcription, worker routing, and delivery gates local.
