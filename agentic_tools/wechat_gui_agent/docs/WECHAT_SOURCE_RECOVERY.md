# WeChat Source Recovery

## Goal

Read Gongzhonghao (`mp.weixin.qq.com`) articles and gather useful Shipinhao
evidence without asking the owner to complete a verification page. This is a
read-only research path: it does not focus the GUI, open a browser, post a
comment, like, follow, or invoke Yuanbao.

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
7. If extraction remains blocked, give the worker exact-title/account,
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
the current Finder card. Comment intelligence then checks:

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

The API adapter reads `/api/channels/feed/comment/list` directly, paginates
top-level comments and replies, and saves a local raw snapshot before analysis.
It falls back to `/api/channels/feed/comment/export` when the list endpoint is
not available.

## Evidence Contract

- `full_article`: the extracted article body was read.
- `reconstructed`: claims were rebuilt from identified public sources.
- `comment_hits` or `comments_available`: comments are auxiliary evidence.
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

Do not copy private article bodies, comment exports, cookies, chat rows, or
source URLs into git.
