# WeChat Source Recovery

## Goal

Read Gongzhonghao (`mp.weixin.qq.com`) articles and gather useful Shipinhao
evidence without asking the owner to complete a verification page. This is a
read-only research path: it does not focus the GUI, open a browser, post a
comment, like, follow, or send a Yuanbao chat prompt. Exact `weixin.qq.com/sph`
links may use an already logged-in local Yuanbao session only as a private
read-only URL parser.

## Article Pipeline

`wechat_task_worker.py` runs `wechat_source_recovery.py` before the worker
agent for matching `research_summary` tasks.

1. Isolate URLs and card metadata from the current coalesced request and exact
   source row. Old chat history is excluded.
2. Normalize captcha wrapper URLs back to the original article URL.
3. Request the article with a mobile WeChat `MicroMessenger` user agent and a
   normal `mp.weixin.qq.com` referer. A desktop request is only a fallback.
4. Reject pages containing `环境异常`, `完成验证后继续访问`, or captcha markers.
5. Parse `#js_content`, title, account, author, publish time, and image URLs.
6. Save successful HTML and Markdown under the ignored task artifact directory
   and a hashed private cache under `.private/source_recovery_cache/`.
7. If no canonical URL is present but the exact Android source row contains a
   native article card, `wechat_android_source_recovery.py` re-enters the exact
   allowlisted chat, opens the matching title, copies the canonical link through
   WeChat's native share menu, and reruns the same extractor. The recovered page
   is accepted only when its title equals the card title or has a strong
   publisher-suffix match.
8. If extraction remains blocked, give the worker exact-title/account,
   `__biz`/`mid`/`sn`, DOI, arXiv, and GitHub reconstruction queries. The agent
   searches canonical papers, repositories, author pages, and trustworthy
   same-title copies, then labels the result as reconstructed.

Manual use:

```bash
python agentic_tools/wechat_gui_agent/scripts/wechat_source_recovery.py \
  --url 'https://mp.weixin.qq.com/s/ARTICLE' \
  --output-dir output/wechat-source-check \
  --json
```

## Shipinhao Pipeline

The source-recovery packet isolates title, author, object ID, and nonce ID from
the current Finder card. Media evidence runs before comment intelligence:

1. A native Finder card already contains its exact object identity and a signed
   Tencent media URL. LabCanvas consumes that card directly; it must not ask the
   sender to copy a separate `sph` link while the card URL is usable.
2. For an exact `https://weixin.qq.com/sph/...` source,
   `shipinhao_share_link_resolver.py` reads the existing local Yuanbao cookie
   through localhost CDP and starts `ltaoo/wx_channels_download` as a bounded,
   non-root, parse-only provider. The generated private config explicitly
   disables TUN, system proxy, proxy serving, MCP, certificate installation,
   and unrelated download interception. The provider is stopped in `finally`.
3. The resolver verifies the exact share token, author/title returned for that
   link, and an allowlisted Tencent video URL. Signed URLs and cookies remain
   private; only the verified MP4 and safe evidence enter the worker task.
4. `shipinhao_media_transcribe.py` tries the exact card's allowlisted Tencent
   media URL with bounded download and SSRF checks.
5. If the signed URL expired, the agent opens the exact card in native WeChat
   and runs `shipinhao_gui_audio_capture.py` with distinctive title/author terms.
   The history navigator recognizes the visible latest-message control by its
   green-on-white visual structure rather than depending on English OCR.
6. The capture helper binds to the active `WeChatAppEx` PipeWire stream, verifies
   visible identity, stops on feed auto-advance, and writes a private
   object-ID/hash manifest.
7. The worker discovers that manifest, validates it, transcribes the source-only
   audio, and writes `task.preflight.shipinhao_media_transcript`.

When desktop WeChat is unavailable but the allowlisted MIX 2S transport is
active, the same fallback is owned by `wechat_android_source_recovery.py`:

1. Prewarm the source-audited `sndcpy` helper, then explicitly return to and
   verify the exact source chat before scanning any card.
2. Open only a card whose visible title/author terms match the exact task packet.
3. Mute the physical phone speaker while capturing Android system audio and the
   native player screen. Host or phone volume settings do not define whether
   the stored stream contains audio.
4. Keep the full raw capture private. Detect a repeated player loop only when
   both audio correlation and visual-frame evidence agree, then produce one
   source-duration recovered MP4 and WAV plus a source-ID/hash manifest.
5. Validate that manifest in `shipinhao_media_transcribe.py`, transcribe it, and
   create a bounded H.264/AAC delivery copy when the verified source exceeds the
   normal mobile share size. The complete private source remains unchanged.
6. Deliver the playable MP4, useful transcript, and one natural summary through
   the exact-chat sender ledger. A committed native share is not downgraded just
   because restoring the review surface later fails.

The Android fallback is additive. Do not remove the desktop recovery code or
pretend a desktop QR/login state is healthy. Whichever transport is selected
must preserve the same source message ID, chat identity, object identity, and
outbound idempotency contract.

Never run `wx_channels_download` as a permanent root/TUN interceptor. A
long-lived TUN provider can replace normal routes, break WeChat networking, and
intercept unrelated desktop traffic. The supported LabCanvas path is one exact
share link, one short-lived parse-only process, no GUI focus, and verified
cleanup (`wx_video_download` absent and `tun0` absent) after every request.

An exact Shipinhao card or `sph` link defaults to source intake: download the
verified MP4, transcribe readable audio, return the MP4 plus one concise natural
summary/transcript, and stop. A platform name or source URL is not publication
authorization; public posting still requires an explicit current-message
publish/post/upload action.

Comment intelligence then checks:

1. explicit exact comment JSON paths;
2. exact matching exports discovered under private/configured `comment_data`
   roots;
3. a configured local `wx_channel` API;
4. an auto-discovered local API at `http://127.0.0.1:2026`;
5. a read-only native capture only when the matching page is already visible;
6. exact title/author/object-ID public reconstruction.

Set additional export roots with:

```bash
export WECHAT_SHIPINHAO_COMMENT_DIRS='/path/one:/path/two'
```

The worker may use comments as auxiliary evidence, especially Yuanbao,
transcript, summary, quoted-line, timestamp, and correction comments. Comments
alone are not proof that the complete video was watched. Posting a new comment
or Yuanbao prompt remains an explicit per-video write action.

The native audio capture is also read-only. It must not reload the page after
selecting a PipeWire stream, and it must not accept nominal duration as proof of
source boundaries. Visual title/author identity loss is the auto-advance stop
gate. See `references/wechat-shipinhao-audio-transcription-workflow.md`.

The API adapter reads `/api/channels/feed/comment/list` directly, paginates
top-level comments and replies, and saves a local raw snapshot before analysis.
It falls back to `/api/channels/feed/comment/export` when the list endpoint is
not available.

## Evidence Contract

- `full_article`: the extracted article body was read.
- `reconstructed`: claims were rebuilt from identified public sources.
- `comment_hits` or `comments_available`: comments are auxiliary evidence.
- `transcribed` with `visual_identity_verified=true`: actual source-scoped
  audio was transcribed.
- `blocked` or evidence-limited: answer only from verified metadata and say so.

Read gates never become `waiting_confirmation`. Authentication, CAPTCHA,
payment, publication, deletion, and other write/risky actions keep their normal
human approval boundaries.

## Open-Source References

- `gxcsoccer/wechat-article-crawler`: mobile WeChat user agent, `#js_content`,
  and lazy-image extraction pattern (MIT).
- `xiguawang/wechat-reader`: structured CLI/MCP status and browser-session
  adapter (MIT); useful when an already-readable logged-in page exists.
- `nobiyou/wx_channel`: local Channels profile/comment APIs and persistent
  comment exports (MIT; Windows runtime).
- `qiye45/wechatVideoDownload`: Channels media URL capture reference; it does
  not provide comment intelligence.
- `ltaoo/wx_channels_download`: exact `sph` share-link parsing through Yuanbao
  and Finder Preview APIs. LabCanvas reuses only its bounded parse endpoint;
  its TUN/system-proxy modes are explicitly disabled.

Do not copy private article bodies, comment exports, cookies, chat rows, or
source URLs into git.
