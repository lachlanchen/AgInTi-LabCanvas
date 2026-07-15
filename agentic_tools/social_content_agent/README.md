# LabCanvas Social Content Agent

This tool turns a local open-source repository into source-grounded,
platform-specific campaign drafts while keeping publication under exact human
control. It uses one persistent Codex conversation per project, defaults to
`gpt-5.6-sol` with Ultra (`xhigh`) reasoning, stores campaign state in SQLite,
and invalidates approvals whenever post text, target, media, settings, or
publication metadata change.

## Quick Start

```bash
PYTHONPATH=src python -m agenticapp social init

PYTHONPATH=src python -m agenticapp social project add \
  --repo ../ZhJpBook \
  --id pocketpolyglot \
  --name PocketPolyglot \
  --homepage https://learn.lazying.art

PYTHONPATH=src python -m agenticapp social campaign create \
  --project pocketpolyglot \
  --name public-introduction \
  --objective "Introduce the usable open-source Studio and ask for concrete learner and developer feedback" \
  --audience "language learners, educators, multilingual publishing developers" \
  --platform x \
  --platform reddit:r/languagelearning \
  --platform bluesky \
  --platform mastodon \
  --platform hackernews

PYTHONPATH=src python -m agenticapp social draft generate CAMPAIGN_ID --dry-run --json
PYTHONPATH=src python -m agenticapp social draft generate CAMPAIGN_ID --json
PYTHONPATH=src python -m agenticapp social export CAMPAIGN_ID --output output/social/review/CAMPAIGN_ID
```

Review one draft, then bind approval to its current SHA-256 content envelope:

```bash
PYTHONPATH=src python -m agenticapp social approve DRAFT_ID --note "Checked claims, community rules, media, and links"
PYTHONPATH=src python -m agenticapp social publish DRAFT_ID \
  --provider postiz \
  --integration POSTIZ_INTEGRATION_ID \
  --approval APPROVAL_TOKEN
```

The last command is still a dry run. Add `--live` only when the exact reviewed
draft should be written to the external provider.

After connected posts have real analytics, run the same persistent project
agent as a content maintainer. It separates observed metrics from inference and
returns a local report; it does not post or reply:

```bash
PYTHONPATH=src python -m agenticapp social maintain CAMPAIGN_ID \
  --integration x=POSTIZ_X_ID \
  --integration reddit=POSTIZ_REDDIT_ID \
  --days 30 \
  --dry-run

# Remove --dry-run after checking the contract.
```

## Provider Setup

Install optional tools outside the repository:

```bash
agentic_tools/social_content_agent/scripts/install_optional_tools.sh postiz
agentic_tools/social_content_agent/scripts/install_optional_tools.sh xmcp
```

Postiz provides the broad transport for X, Reddit, Bluesky, Mastodon,
LinkedIn, DEV, and other connected networks. Its OAuth login is stored in the
provider-managed `~/.postiz/credentials.json`; API keys can remain in the
environment. Both stay outside git. The official X MCP is optional for
X-specific research and analytics; its allowlist should remain narrow.

```bash
postiz auth:login
PYTHONPATH=src python -m agenticapp social postiz-integrations --json
PYTHONPATH=src python -m agenticapp social providers --probe --json
```

Copy `.env.example` to `.private/.env` only when environment credentials are
needed. The repository already ignores every `agentic_tools/**/.private/`
folder.

## Operating Boundaries

- Drafting, research, project discovery, exports, and analytics reads are safe
  local operations.
- Every provider write requires both `--live` and a non-expired approval token
  bound to the exact current draft hash.
- Reddit targets require a fresh review of the named community's rules. The
  tool does not automate comments, votes, DMs, follows, or repetitive posting.
- Hacker News is manual-only. The agent creates a fact worksheet because HN's
  guidelines reject generated or AI-edited submission text. The human writes
  the final title and body, imports them with `draft import-human`, and submits
  in a visible browser.
- A successful Postiz call means the item was accepted/scheduled by Postiz. It
  does not claim the destination platform published until later analytics or
  provider status confirms that state.

See [platform research](docs/PLATFORM_RESEARCH.md) for the evaluated APIs,
MCPs, provider choices, and policy rationale.
