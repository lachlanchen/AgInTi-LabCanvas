# Shipinhao Comment Reading Research

Date: 2026-06-29

## Conclusion

Shipinhao/WeChat Channels comments are not hopeless. The reliable path is not
plain HTTP scraping of a shared card. The useful path is a logged-in page or
native UI session that can access the Channels runtime APIs, then a local helper
exports comments for the agent to summarize.

## Best Open Source Lead

`nobiyou/wx_channel` is the strongest reference found. It injects helper code
into the logged-in Channels web/runtime page, exposes local endpoints, and maps
the page method `finderGetCommentList` to a local API key
`key:channels:fetch_feed_comment_list`.

Relevant behavior:

- `GET /api/channels/feed/comment/list`
- fields: `object_id`, `nonce_id`, optional `comment_id` and `next_marker`
- returns comment/reply pages directly over HTTP, avoiding Windows-only saved paths
- `POST /api/channels/feed/comment/export`
- request fields: `object_id`, `nonce_id`, `title`, `author`
- output: JSON under `comment_data/YYYY-MM-DD/`
- captures top-level comments and level-two replies
- saves `.partial.json` checkpoints during long exports
- locks page refresh during export to avoid losing long comment jobs

This is suitable for finding `@元宝`, `腾讯元宝`, `英文全文`, `全文`, `总结`,
`摘要`, `字幕`, `转写`, `transcript`, and `summary` comments that may contain or
request video summaries/transcripts.

## Other Useful Reference

`qiye45/wechatVideoDownload` focuses on downloading 视频号 media and live
replay URLs by listening while the official client/browser opens videos. It is
useful for media retrieval, but it is not a comment-export solution.

## LabCanvas Integration Plan

Use this order for Shipinhao links/cards:

1. Parse the WeChat shared card and save metadata from the message row.
2. Try the exact card media URL or a matching verified native audio capture
   first, then transcribe it with `shipinhao_media_transcribe.py`.
3. If the embedded URL expired, open the exact same-chat card, verify the
   player title/author, and try its literal native `复制链接` action. A validated
   copied share link is fed back to the existing resolver automatically; the
   sender is not asked to paste it.
4. If a logged-in Channels page/runtime is available, use a `wx_channel`-style
   comment export.
5. Run `shipinhao_comment_intel.py` on the exported JSON.
6. Use comments only as auxiliary evidence. Prefer comments containing Yuanbao,
   transcript, summary, quoted lines, timestamps, names, links, or corrections.
7. Do not post a comment or ask Yuanbao from the account unless the current user
   explicitly requests it.
8. If the page, video, comments, and transcript are unavailable, say that
   plainly and avoid a fake deep analysis.

Audio/video evidence and comment evidence stay separate. A transcript JSON or
`verified-capture.json` is never passed to `shipinhao_comment_intel.py` as if it
were a comment export.

## Source-Scoped Audio Fallback

When a Tencent card URL has expired, open the exact native card and run:

```bash
agentic_tools/wechat_gui_agent/scripts/shipinhao_gui_audio_capture.py \
  --object-id '<OBJECT_ID>' \
  --title '<CARD_TITLE>' \
  --author '<AUTHOR>' \
  --identity-term '<DISTINCTIVE_TERM>' \
  --display :97 \
  --json
```

The helper records only while expected identity remains visible and trims the
feed's next item. The worker discovers `verified-capture.json` by object ID and
adds a timestamped transcript to preflight. Full operating details are in
`references/wechat-shipinhao-audio-transcription-workflow.md`.

## Local Utility

The LabCanvas helper can analyze an exported comment JSON:

```bash
agentic_tools/wechat_gui_agent/scripts/shipinhao_comment_intel.py \
  --comments-json /path/to/comment_data/2026-06-29/video.json \
  --markdown-out output/shipinhao-comment-intel.md \
  --json-out output/shipinhao-comment-intel.json
```

If a compatible local `wx_channel` API is running:

```bash
agentic_tools/wechat_gui_agent/scripts/shipinhao_comment_intel.py \
  --api-url http://127.0.0.1:2026 \
  --object-id OBJECT_ID \
  --nonce-id OBJECT_NONCE_ID \
  --title "video title" \
  --author "channel name"
```

The script highlights Yuanbao/transcript/summary comments and high-like
comments, then returns Markdown or JSON for the WeChat worker.

The helper now prefers the paginated `comment/list` API and follows reply pages.
It falls back to `comment/export` for older/alternate runtimes. This lets a
Linux worker consume an API running elsewhere without requiring the returned
Windows `saved_path` to exist locally.

## Worker Preflight

`wechat_task_worker.py` now runs comment intelligence before research-summary
tasks when the task looks like a Shipinhao/Finder/视频号 share.

Preflight sources:

- explicit exported JSON paths in the task text/context;
- `WECHAT_SHIPINHAO_COMMENT_JSON`;
- exact matching JSON automatically discovered under private/download
  `comment_data` roots and `WECHAT_SHIPINHAO_COMMENT_DIRS`;
- a compatible logged-in local API via `WECHAT_WX_CHANNEL_API_URL`,
  `WECHAT_SHIPINHAO_WX_CHANNEL_API_URL`, or `WX_CHANNEL_API_URL`, when
  `object_id` and `nonce_id` are known.
- an auto-discovered compatible API on `http://127.0.0.1:2026` when no URL is
  configured and exact object/nonce IDs are available.

The worker writes:

```text
<artifact_dir>/shipinhao_comment_intel/manifest.json
<artifact_dir>/shipinhao_comment_intel/manifest.md
<artifact_dir>/shipinhao_comment_intel/comments-*.json
<artifact_dir>/shipinhao_comment_intel/comments-*.md
```

Agents must read `task.preflight.shipinhao_comment_intel` before answering. If
the status is `ok`, use the comment hits as auxiliary evidence. If the status is
`not_available`, avoid claiming a deep video analysis unless another reliable
video, transcript, or article source was actually read.

Agents must also read `task.preflight.wechat_source_recovery`. It supplies the
current-card title, author, object ID, nonce ID, and exact reconstruction
queries. If comments/media are unavailable, search those identities and
corroborate public sources instead of asking the user to verify a page.

## Practical UI Path

For a shared Shipinhao card, the automation can still use GUI assist:

- open the card in the native WeChat/Channels UI;
- let the logged-in runtime load the video detail page;
- click or scroll the comments panel when necessary;
- run the local injected comment export if available;
- otherwise capture visible comments with screenshot/OCR as a fallback.

This should be implemented as a read-only action by default. It should never
send comments, likes, follows, or Yuanbao prompts without explicit current
permission.

## Native Visible Capture Fallback

When `wx_channel` comment export is not available but the official WeChat client
already shows the Shipinhao/Finder detail page, use the read-only capture helper:

```bash
agentic_tools/wechat_gui_agent/scripts/shipinhao_native_capture.py \
  --output-dir output/wechat_worker/TASK_ID/shipinhao-native-capture \
  --scrolls 3 \
  --json
```

The helper does not click like/follow/comment buttons. It captures the visible
WeChat window, OCRs the title/comment area, sends read-only `Page_Down` events,
and writes screenshots, OCR text, `shipinhao-visible-comments.md`, and
`manifest.json`. Treat this as evidence for visible title/comments only. It is
not proof that the complete video was watched.

If the user asks to `@元宝` or request a transcript from Yuanbao, that is a
public comment/reply action from the account. The worker should first read
existing comments for Yuanbao/transcript/summary clues. Posting a new Yuanbao
prompt requires explicit current confirmation for that specific video.
