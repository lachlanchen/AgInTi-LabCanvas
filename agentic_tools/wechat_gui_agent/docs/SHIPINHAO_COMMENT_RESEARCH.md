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
2. Try cached local media or downloaded video first.
3. If a logged-in Channels page/runtime is available, use a `wx_channel`-style
   comment export.
4. Run `shipinhao_comment_intel.py` on the exported JSON.
5. Use comments only as auxiliary evidence. Prefer comments containing Yuanbao,
   transcript, summary, quoted lines, timestamps, names, links, or corrections.
6. Do not post a comment or ask Yuanbao from the account unless the current user
   explicitly requests it.
7. If the page, video, comments, and transcript are unavailable, say that
   plainly and avoid a fake deep analysis.

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

## Worker Preflight

`wechat_task_worker.py` now runs comment intelligence before research-summary
tasks when the task looks like a Shipinhao/Finder/视频号 share.

Preflight sources:

- explicit exported JSON paths in the task text/context;
- `WECHAT_SHIPINHAO_COMMENT_JSON`;
- a compatible logged-in local API via `WECHAT_WX_CHANNEL_API_URL`,
  `WECHAT_SHIPINHAO_WX_CHANNEL_API_URL`, or `WX_CHANNEL_API_URL`, when
  `object_id` and `nonce_id` are known.

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
