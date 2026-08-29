# WeChat Shipinhao Audio Transcription Workflow

## Exact Share-Link Fast Path

When the current source is `https://weixin.qq.com/sph/<token>`, use
`agentic_tools/wechat_gui_agent/scripts/shipinhao_share_link_resolver.py` before
native GUI capture. It reuses the logged-in localhost Yuanbao CDP cookie and a
short-lived `ltaoo/wx_channels_download` parse-only subprocess. It must run as
the normal user with `proxy.enabled=false`, `proxy.system=false`, `tun=false`,
`skipInstallRootCert=true`, and MCP disabled. The process is always terminated
after one result. Do not install a root certificate, change policy routes, or
leave `wx_video_download` resident.

The exact share token is the stable source identity when Finder does not expose
an object ID. Prefer the returned H.264 URL, validate its Tencent host, download
with byte/time limits, and require `ffprobe` to confirm readable video/audio
streams. Keep cookies and signed URLs private. Run Whisper in the dedicated
`~/miniconda3/envs/whisper` environment (GPU 1 by workstation default), then
pass the safe transcript context to the resumed exact-chat agent.

For a bare exact card/link, deliver the verified MP4 and one concise natural
summary/transcript to the source chat. Do not call LazyEdit or any public
platform unless the current message explicitly asks to process or publish.

## Purpose

This workflow lets a LabCanvas worker read a WeChat Channels/Shipinhao share as source material, transcribe its actual audio, summarize it with the chat's resumed agent session, and return the answer to the originating chat. It is read-only: opening the shared card and recording local playback does not like, follow, comment, repost, or send a Yuanbao chat prompt. The exact-share fast path may reuse Yuanbao's authenticated parser endpoint without producing a public action.

## Evidence Pipeline

1. Resolve the exact current WeChat row and parse its `<finderFeed>` block.
2. Bind the task to `objectId`, title, author, nonce ID, duration, and media URL hash.
3. Try the allowlisted Tencent media URL with bounded download and SSRF guards.
4. If the signed URL expired, OCR the exact card cover, translate short Chinese evidence when useful, and search a bounded set of public mirrors. Require transcript-to-cover agreement plus either duration agreement or a time-localized excerpt from a bounded longer source.
5. If no public mirror passes, automatically open that exact card in the guarded source chat.
6. Normalize to the latest message and scan bounded recent history. Match the exact cached card cover on the received side first; otherwise associate a play control only with nearby title/author OCR from the same card.
7. Run an identity-gated local capture. Wait for or start the `WeChatAppEx` PipeWire stream once, then record while visual source identity remains valid.
8. Stop after consecutive identity loss or the card duration upper bound, trim the source-only audio, and write `verified-capture.json` below the private object-ID cache.
9. Transcribe with Whisper, write timestamped Markdown, and pass only the source-scoped transcript to the resumed per-chat worker agent.
10. Send the natural summary through the guarded same-chat sender and verify `sent`, `done-sent`, and `synced` mirror states.

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
- locates the exact same-object cached cover with bounded multi-scale matching;
- rejects cover/play candidates on the right-aligned reply side;
- binds a play control only to OCR evidence in its local card neighborhood;
- preserves cover/play candidate identity so real media targets receive the full player-open timeout;
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

The packaged LabCanvas entrypoint is equivalent:

```bash
PYTHONPATH=src python -m agenticapp wechat shipinhao-transcribe \
  --source-text-file '<TASK_DIR>/shipinhao_media_transcript/exact-source-card.txt' \
  --output-dir '<TASK_DIR>/shipinhao_media_transcript' \
  --json
```

`--captured-audio` remains an operator diagnostic input. Autonomous workers use `--capture-manifest` because it validates object ID, title, author, private path, identity terms, and SHA-256 before trusting audio. Every captured-audio cache name includes the audio hash, preventing one capture from overwriting or silently reusing another.

## Expired-URL Recovery

Public-mirror recovery is automatic and intentionally strict:

- use the exact card title, author, duration, and still-valid cover image;
- OCR the cover locally with Tesseract and optional EasyOCR fallback;
- translate only short Chinese title/cover evidence through a bounded helper;
- search a small public candidate set through the locally installed `yt-dlp` module;
- prefilter with available public captions before downloading candidate media;
- prefer candidates inside the duration tolerance;
- allow a longer public source only when card/caption evidence identifies a bounded excerpt window;
- transcribe that excerpt with Whisper and require independent audio corroboration;
- reject related videos from the same speaker when paraphrase/topic evidence does not match;
- keep media, OCR, and transcripts in the ignored private cache;
- expose only `content_verified_public_mirror`, a public candidate ID, and bounded match metrics to the worker.

If the automatic query set remains unresolved, the manifest exposes private
`cover_path` and `source_text_file` paths to the resumed worker. The agent may
inspect the cover and rerun the same command with at most three repeatable
`--search-hint` values. The deterministic evidence gate remains authoritative.

Disable this fallback for diagnostics with `--no-public-mirror-recovery` or `WECHAT_SHIPINHAO_PUBLIC_MIRROR_RECOVERY=0`. A public mirror is equivalent content evidence, not proof that the original WeChat binary was recovered.

## Failure Contract

These outcomes are intentionally different:

- `no_audio` with `verified_silent_media=true`: readable media was probed and contains zero audio streams.
- `failure_stage=download`: the signed Tencent URL failed or expired.
- `input_kind=content_verified_public_mirror`: the signed binary expired, but transcript content matched the exact card evidence and either duration matched or a longer source was clipped to an independently corroborated excerpt.
- `error_code=finder_card_not_found`: the exact source card was outside bounded history or could not be identified.
- `error_code=finder_player_unavailable`: the exact card was found, but the Linux client did not open its player.
- `error_code=finder_audio_stream_unavailable`: the verified player produced no capturable PipeWire stream.
- `error_code=wechat_gui_busy`: another guarded GUI operation owns the serialized lane; retry later.
- `audio_evidence_status=media_unavailable_not_silent`: no source transcript was recovered, and silence was not verified.

Every preflight outcome writes a private `agent_context_path`. The resumed agent must read it even when the pipeline failed. Only `no_audio` plus `verified_silent_media=true` means the video is silent. Failure aliases forcibly clear the silent flag. A content-verified public mirror is usable transcript evidence; the remaining failure outcomes preserve card, comment, and public reconstruction as weaker evidence and require an evidence-limited answer. They must not be rewritten as “the video has no audio.”

## Worker Reprocessing

After a verified capture becomes available, rerun the original source-scoped task rather than creating a detached summary:

```bash
labcanvas wechat worker reprocess '<TASK_ID>' \
  'Verified Shipinhao capture is ready; transcribe and summarize the exact source' \
  --send
```

The worker writes `task.preflight.shipinhao_media_transcript`, resumes the exact chat's agent session, and sends the selected response to the task's original chat. Comments are a separate auxiliary source. Transcript and capture manifests are not comment exports.

The resumed backend receives a bounded task packet rather than the full queue
row. It includes the current request, source IDs, recent same-chat context,
interruptions, route/routine state, and readable context paths. Raw Finder XML,
signed URLs, cookies, keys, hashes, and unused media paths stay out of the model
prompt.

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

The 2026-07-16 regression test bound the exact TED card after its signed URL expired. Its 38-second card duration matched a 39.265-second public mirror; cover OCR and the Whisper transcript shared a 22-word contiguous run with 0.697 token coverage. The tool returned `content_verified_public_mirror` instead of falsely reporting no audio or requiring the unsupported Linux Finder player.

The later 2026-07-16 live excerpt test recovered a 43-second Steve Jobs card
from a 133.3-second public talk. It rejected a related “Secrets of Life” clip,
selected the consulting talk, localized `19.925-62.925`, and corroborated the
caption match with a Whisper transcript about owning recommendations and
learning from implementation. A warm-cache rerun completed in about one second.

The 2026-07-17 regression used a real expired-URL card whose Linux client could
not open a Finder player. Exact-cover matching located the source card at high
confidence, while the worker emitted `media_unavailable_not_silent` and a
mandatory agent evidence context. Tests prove that neither the Finder packet nor
its general audio-intake alias can convert this acquisition failure into
`verified_silent_media=true`.

## Open-Source References

- `nobiyou/wx_channel`: Channels identity/comment API patterns.
- `qiye45/wechatVideoDownload`: official-client media interception reference.
- `lecepin/WeChatVideoDownloader`: Channels media download architecture reference.
- `yt-dlp/yt-dlp`: bounded public-video search and private mirror download fallback.

These projects are references only. LabCanvas keeps its source binding, private cache, transcription, worker routing, and delivery gates local.
