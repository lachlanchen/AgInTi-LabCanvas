# Image Posts, Mixed Sources, and Cropped Channels Cards

## Scope

LabCanvas must recover evidence according to the actual source format, rather
than treating every Official Account share as a long text article. The source
reader supplies exact assets, coverage, and a reading plan; the resumed chat
agent interprets the material and decides which existing tools to use next.
These changes do not authorize publication or change group schedules.

## Failures and Fixes

- **Short text:** a 240-character threshold rejected genuine short posts.
  An ungated content container with readable body text is now sufficient.
- **Image posts:** native `mmreadershare` type 8 and image-detail URLs can
  identify an album even when the web endpoint returns a verification page.
  Recover its exact first-image URL from the same native card. Parse ordered
  `picture_page_info_list` images and `content_noencode` text when available.
  Image-only HTML content is also recognized without native type metadata.
- **Script-only gates:** `secitptpage/verify` is a verification response, not
  an article with an empty body. It must not override usable native assets.
- **Mixed media:** scoped audio/video/source/iframe URLs become media evidence
  and a reading plan. A player URL is not a transcript; the agent must use the
  established download/audio tools before claiming it heard the material.
- **Several cards:** preserve native source order and bind metadata separately
  by article identity. The bounded preflight handles three sources; remaining
  sources are explicitly pending for the agent, not silently omitted.
- **Retained text shortcut:** image/mixed sources must enter normal asset
  recovery instead of replaying an old metadata-only article result.

JavaScript data is read as quoted string literals with `ast.literal_eval`,
never executed. The parser approach was checked against the upstream
[NewsCrawler WeChat reader](https://github.com/NanmiCoder/NewsCrawler/blob/main/news_crawler/wechat_news/wechat_news.py).
No upstream cookies or credentials are used.

## Original Image Contract

`wechat_post_assets.py` downloads only explicitly supplied qpic/qlogo CDN
images. Redirects outside those CDNs are rejected. Downloads are bounded to
12 images, 16 MiB per image, and 48 MiB total; unsupported/corrupt or oversized
images remain explicit failures. Images are verified and retained as original
bytes with private permissions. They are not resized into bubble previews.

The worker reads the available images as an ordered source set through the
existing vision/model policy, then adds semantic reading notes to the source
context. A vision failure preserves downloaded assets and other sources so
the agent can use another available vision tool. Successful reading notes enter
the existing same-chat source-knowledge store with complete/partial provenance.

Coverage is mandatory. A native card advertising nine images but supplying
only one original is **one of nine pages**, not a fully recovered album. Never
invent the missing pages or substitute another post's images. Inspect exact
source alternatives, then state any remaining limitation naturally.

## Channels Link Recovery

Native clients sometimes crop portrait covers to fit their card. A full-image
template can then fail even though the correct card is visible. Keep the old
template threshold; fall back to geometric matching of local features from
the exact cached cover. Require consistent affine inliers, restrict matching
to the received-message side, and still verify player title/author before
using Copy Link. A cover match alone never authorizes media processing.

Short players are paused during identity/menu checks to prevent feed
auto-advance. Copy Link uses exact menu-label recognition with alternate OCR
layout when necessary. Clipboard transfer is asynchronous: wait for a fresh
share URL, and only retry another read-only menu after rechecking the same
player identity. Never click a forwarding action or accept a stale clipboard.

The verified share URL enters the existing original downloader and GPU 1
transcription path. No screen recording or audio capture substitutes for the
original file. Public-mirror candidates additionally require content agreement;
matching metadata and duration alone cannot establish media identity.

## Live Verification

On 2026-11-14, private retained tasks demonstrated:

1. An image post behind a script-only gate yielded its original 2151 x 3114
   JPEG. The integrated worker vision stage read its argument and recorded
   incomplete coverage: one available page out of nine.
2. A cropped portrait Channels card matched through 187 geometric inliers.
   Native title verification and Copy Link succeeded. The existing downloader
   recovered an identity-verified 20.54-second MP4 with an AAC audio stream,
   and GPU 1 transcription produced four segments. No source resend was needed.

Private receipts are under ignored
`output/wechat-source-recovery-20261114/`. These checks requested no group
delivery, so no diagnostic messages, old videos, or duplicate replies were sent.
They prove these source paths, not universal access to every post or every
missing album page. Preserve this distinction in future reports.

## Regression and Operation

Run `npm test`, then run `test_shipinhao_gui_audio_capture.py` with the production
Python environment containing OpenCV. A system-Python OpenCV skip is not proof
that geometric matching works. Targeted tests also cover original image bytes,
CDN/redirect rejection, per-card metadata, deferred sources, partial coverage,
vision-failure isolation, retained replay, and knowledge provenance.

Reload only idle worker processes after tests. Preserve the current official
clients, login profiles, send ledgers, group isolation, and disabled schedules.
Do not replay historical failed tasks indiscriminately as a deployment test.
