# Social Platform Automation Research

Research date: 2026-07-15

## Recommended Architecture

Use LabCanvas/Codex for repository reading, positioning, platform adaptation,
and review. Use Postiz as the optional broad publishing transport and the
official X MCP only where X-specific tools add value. Keep a local SQLite
source of truth for campaigns, content hashes, approvals, publication IDs, and
analytics snapshots. Do not give an arbitrary community MCP access to social
credentials when an official API or established OAuth provider exists.

## Evaluated Projects and APIs

### Postiz

[Postiz Agent](https://github.com/gitroomhq/postiz-agent) is the primary broad
adapter. It provides JSON commands for integrations, provider settings,
dynamic tools such as Reddit flair discovery, post creation, media upload, and
analytics. [Postiz](https://github.com/gitroomhq/postiz-app) is open source and
supports self-hosting; its hosted flow uses official platform OAuth. LabCanvas
keeps Postiz optional and invokes it only after exact-content approval. The
Postiz Agent CLI stores its OAuth credential in `~/.postiz/credentials.json`,
outside this repository.

### X

[xdevplatform/xmcp](https://github.com/xdevplatform/xmcp) is the official X
FastMCP server. It exposes the current X OpenAPI operations and supports an
allowlist. For this project, start with read operations plus `createPosts` only:

```text
getUsersMe,getUsersPosts,getPostsAnalytics,searchPostsRecent,createPosts
```

Do not enable follows, likes, reposts, DMs, or deletion merely because those
tools exist. X MCP requires a Developer Platform app and OAuth credentials; a
normal x.com browser login alone is not sufficient.

### Reddit

Use official Reddit/Devvit capabilities or Postiz's official OAuth integration.
Reddit's [spam policy](https://support.reddithelp.com/hc/en-us/articles/360043504051-Spam)
rejects repeated or unsolicited mass engagement, and its
[developer rules](https://support.reddithelp.com/hc/en-us/articles/360043512931-Don-t-break-the-site)
require registered, policy-compliant applications. Each subreddit has its own
rules, so the tool marks Reddit copy as needing target-rule review. It never
automates voting, unsolicited outreach, or comments.

### Hacker News

The [official Hacker News API](https://github.com/HackerNews/API) is read-only
and useful for topic/recent-submission research. The
[submission guidelines](https://news.ycombinator.com/newsguidelines.html) ask
for original sources, neutral titles, no vote solicitation, and no generated
or AI-edited text. The [Show HN rules](https://news.ycombinator.com/showhn.html)
also require a usable project and an author who stays to discuss it. Therefore
LabCanvas does not generate or automatically submit HN text. For
PocketPolyglot, the runnable Studio may be a Show HN candidate; a collection of
books alone is not enough.

### Bluesky and Mastodon

Bluesky offers the official [AT Protocol SDK and API](https://docs.bsky.app/docs/get-started),
and Mastodon exposes the official
[`POST /api/v1/statuses`](https://docs.joinmastodon.org/methods/statuses/)
endpoint with idempotency keys. Both can be added as direct adapters later.
Postiz is the initial shared transport because it already handles OAuth,
media, scheduling, and provider discovery.

## Content Model

One campaign produces independent platform drafts rather than one body copied
everywhere. The agent receives only repository evidence, campaign objective,
audience, target, and policy. It must not invent traction, benchmarks,
endorsements, or maturity claims. Recommended media must come from discovered
repository assets.

Publication uses two deliberate gates:

1. `social approve` records an expiring token for the exact content hash.
2. `social publish --live` verifies that token immediately before the provider
   call.

Editing the title, body, target, media, provider settings, thread, alt text, or
other publication metadata invalidates all previous approvals. Provider
responses are stored locally without credentials.

## PocketPolyglot Positioning

The source-backed core is specific and credible:

- Generates pocket-size interlinear books with ruby/furigana, pinyin,
  grammar-color roles, and line alignment.
- Current production focus is Chinese/Japanese, while the data model supports
  other prepared language pairs.
- Includes TeX templates, Python pipelines, JSON schemas, validation, preview
  assets, and a local Studio with durable SQLite/tmux jobs.
- Website: <https://learn.lazying.art>
- Source: <https://github.com/lachlanchen/PocketPolyglot>
- Full books require rights-cleared source material; public promotion should
  show the tool, layout, and rights-cleared examples rather than imply bundled
  rights to copyrighted works.

Strong initial media candidates are the Studio queue screenshot and the Kokoro
four-edition comparison. Platform copy should invite concrete feedback about
readability, language pairs, e-ink output, educator workflows, and contributor
experience.
