# Career Self-Analysis Agent

This runbook documents the WeChat career/writing/money self-analysis workflow.
It is for agents that need to understand Lachlan's recurring interests,
writing direction, product opportunities, and daily next actions without
depending on this conversation.

## Purpose

The workflow answers:

- what to write and what story to tell;
- who Lachlan is, based on evidence from messages and projects;
- visible talents, leverage points, and monetization opportunities;
- watchlist-style investment or company themes, with risk framing;
- the single practical next bet for wealth, freedom, and happiness.

It is strategic coaching, not therapy, prophecy, or financial advice.

## Main Entry Points

One-shot report:

```bash
PYTHONPATH=src python -m agenticapp wechat career-agent once \
  --model gpt-5.5 --reasoning-effort xhigh --json
```

Daily tmux loop:

```bash
PYTHONPATH=src python -m agenticapp wechat career-agent start \
  --send --attach-report --organize-report \
  --organize-chat "写作 外语 挣钱" --morning-time 08:30 \
  --model gpt-5.5 --reasoning-effort xhigh
```

Immediate PDF-only organization of recent items:

```bash
PYTHONPATH=src python -m agenticapp wechat career-agent organize \
  --send --organize-chat "写作 外语 挣钱" --json
```

The organizer reuses a distinct `daily_organizer` Codex session for the exact
chat. It keeps Markdown and evidence local, compiles one Chinese XeLaTeX PDF,
and sends only the PDF. Its delivery ledger makes restart and transport retries
idempotent: a failed send reuses the existing PDF without another agent turn.

The organizer is a synthesis workflow, not a transcript formatter. It reads a
bounded recent ledger together with compacted same-profile lifetime context,
first explains the day's larger threads in substantial prose, then provides a
complete organized reference. Its quality gate scales depth with evidence and
rejects raw chat rows, source-by-source evidence appendices, list-dominant
exports, timestamps, media sizes, model diagnostics, and thin generic advice.
Only an accepted draft is rendered. The PDF uses a mobile-readable XeLaTeX
layout and AcroForm checkboxes only for genuine actions.

Each dated PDF is delivered with the stable component scope
`daily-organizer-YYYY-MM-DD-v3`. The native Android sender verifies the exact
allowlisted chat, recipient confirmation, and completed Send. Its component key
also includes the file hash, making retries of the same report no-ops without
blocking a revised same-day report. If the process restarts after a committed
send, the exact outbound file echo reconciles the organizer state instead of
sending a duplicate.

Full WeChat stack after reboot:

```bash
~/scripts/create-labcanvas-wechat-after-reboot.sh
```

The after-reboot wrapper starts the normal WeChat supervisor, LabCanvas web
panel, and this daily scheduler together. Prefer it when recovering the whole
system after a machine reboot. On this workstation, it is also called from the
enabled user tmux entrypoint `~/scripts/create_tmux_session.sh`, so reboot
startup follows the same path as manual recovery.

Status:

```bash
PYTHONPATH=src python -m agenticapp wechat career-agent status --json
```

Reusable user script:

```bash
~/scripts/create-labcanvas-career-daily-tmux.sh
```

When `--attach-report` is enabled, the sender keeps the sanitized Markdown
locally and sends Chinese and English PDF companions to WeChat, for example
`2026-06-26-career-strategy.zh.pdf` and
`2026-06-26-career-strategy.en.pdf`. Missing language Markdown is generated
through the existing agent backend, then rendered with pandoc/XeLaTeX so the
report is easier to read on mobile WeChat. The two PDFs are sent before the
agent-written `微信摘要` and three questions. If either PDF cannot be generated
or delivered, the sender records a delivery failure and does not claim the
daily report was completed in chat.

The launch wrappers set:

```bash
WECHAT_MARKDOWN_PDF_LANGUAGES=zh,en
WECHAT_MARKDOWN_PDF_PANDOC=$HOME/miniconda3/bin/pandoc
WECHAT_MARKDOWN_PDF_ENGINE=xelatex
```

If `pandoc` is absent from the tmux process PATH, the renderer also probes
`~/miniconda3/bin/pandoc`, `~/.local/bin/pandoc`, and
`/usr/local/bin/pandoc`. Busy GUI sends use a bounded pre-send retry; other
errors fail closed to avoid duplicate attachments. A PDF failure records a
`pdf:` error and marks the run `delivery_failed` instead of silently treating
Markdown-only delivery as complete.

## Code Surfaces

- `src/agenticapp/wechat_ops.py`: exposes `labcanvas wechat career-agent`.
- `scripts/wechat_career_daily_agent.py`: builds the prompt, collects evidence,
  resumes the Codex career session, writes reports, and optionally sends the
  sanitized report to WeChat.
- `scripts/wechat_direct_chatops.py`: routes `写作 外语 挣钱` and `lachlanchan`
  career/writing/money messages to `career_strategy`.
- `scripts/wechat_routines.py`: defines the `career_strategy` routine contract.
- `scripts/wechat_chat_sync_loop.py`: dry-opens inactive chats, now bounded by
  `--max-targets-per-cycle` so it does not block real replies.
- `scripts/wechat_supervisor_tmux.sh`: keeps the WeChat desktop, direct monitors,
  workers, media sync, unlock watchdog, and chat sync alive.
- `scripts/wechat_stack_tmux.sh`: starts the supervisor, web panel, and career
  scheduler as one tmux-managed stack.

## Evidence Sources

The daily agent uses read-only evidence:

- `agentic_tools/wechat_gui_agent/.private/wechat_memory.sqlite`
- recent organized memory for `写作 外语 挣钱` and `lachlanchan`
- deduplicated memo/todo/idea evidence from `写作 外语 挣钱`
- interest evidence from `鏈接` and `🍓我的设备`, used only in the private
  `lachlanchan` analysis
- shallow local repo surface under `/home/lachlan/ProjectsLFS`
- shallow local repo surface under `/home/lachlan/DiskMech/Projects`
- `LazyInvestment` or adjacent investment repo evidence if present
- `VoidAbyss`/`voidabyss` folders if present
- `lazying.art`, `BLOG`, `Documentations`, and `LazySkills` identity surfaces
- `https://github.com/lachlanchen`, `https://lazying.art`, and the exact Google
  Scholar profile `Kdqr_AcAAAAJ`
- current web/GitHub/company research when the question depends on live facts

Raw private chats are not posted back to WeChat. The worker summarizes patterns
and keeps detailed evidence in private trace artifacts.

Default model policy: use `gpt-5.5` with `xhigh` reasoning for daily self
analysis. This report is meant to be a deep Chinese memo with enough evidence
to matter, not a cheap fast ack or a rigid template. It should avoid generic
self-help, generic startup advice, and unsupported investment themes. Only
override `WECHAT_CAREER_AGENT_EFFORT` for explicit debugging or emergency
latency reasons.

## Trace Bundle

Each run writes a private bundle:

```text
agentic_tools/wechat_gui_agent/.private/output/career_daily/runs/YYYY-MM-DD-HHMMSS/
```

Files:

- `manifest.json`: run id, model, effort, thread id, input/output paths, send
  status, privacy flags, and git state.
- `agent_prompt.md`: exact prompt sent to the career agent.
- `memory_snapshot.md`: private memory summary used as evidence.
- `life_memo_snapshot.md`: deduplicated recent memo/todo/idea evidence.
- `project_surface.md`: local repo/project evidence.
- `lazyinvestment_snapshot.md`: investment repo evidence if available.
- `voidabyss_snapshot.md`: narrative/IP evidence if available.
- `identity_surface.md`: lazying.art/blog/skill/profile evidence.
- `public_profile_surface.md`: exact public profile URLs and current GitHub
  profile fields.
- `agent_result.json`: sanitized agent backend metadata and response.
- `private_report.md`: full private Markdown report.
- `share_report.md`: sanitized report safe to attach to WeChat.

Latest convenience paths:

```text
agentic_tools/wechat_gui_agent/.private/output/career_daily/YYYY-MM-DD-career-strategy-private.md
output/wechat_strategy/YYYY-MM-DD-career-strategy.md
output/wechat_strategy/YYYY-MM-DD-career-strategy.zh.pdf
output/wechat_strategy/YYYY-MM-DD-career-strategy.en.pdf
```

`output/wechat_strategy/` is the only report path intended for WeChat
attachment. Private trace paths may include local evidence and should stay
ignored by git.

## Agent Method

The prompt asks for a natural, substantial memo rather than a fixed section
template. It should still answer:

- what Lachlan seems to be trying to write or become;
- what his visible talents are, grounded in concrete evidence;
- which opportunity or money-making lane is most realistic now;
- what to ignore because it dilutes the signal;
- what one primary bet deserves today's energy;
- what to do today.

The self-discovery section must contain exactly three questions, formatted as
`Q1`, `Q2`, and `Q3`, each with a short `为什么重要：...` sentence. They should be
specific to the day's evidence, answerable in 10-15 minutes, gently
uncomfortable, and useful enough that an honest answer could change tomorrow's
plan. The sender extracts these questions into the WeChat text message before
attaching the share report, so they remain visible even if file delivery is
delayed.

The agent should:

- use evidence, not vague motivation;
- separate writing, career, product, money, and investment themes;
- recommend small experiments with validation signals;
- ask questions that discover desire, avoidance, identity, and leverage rather
  than generic journaling prompts;
- treat investment ideas as watchlists/risk frameworks, not orders;
- verify current company/market facts before time- or money-intensive advice;
- avoid exposing private chat logs, credentials, wxids, or DB paths in WeChat.

## Supervisor Method Used

For the initial deep research, four xhigh subagents were used in parallel:

- writing/story/VoidAbyss analysis;
- identity/talent analysis;
- investment/company opportunity analysis;
- single-bet wealth/freedom/happiness synthesis.

Their conclusions were folded into the routine contract and daily-agent prompt:
Lachlan's strongest repeatable lane is a paid LabCanvas/LazyingArt artifact
production system for researchers, creators, and technical founders, supported
by bilingual writing and classical/technical narrative IP.

## Operational Checks

Run focused tests:

```bash
PYTHONPATH=src python -m unittest \
  tests.test_wechat_career_daily_agent \
  tests.test_wechat_chat_sync_loop \
  tests.test_wechat_routines \
  tests.test_wechat_direct_chatops -v
```

Run all tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Reload without closing WeChat:

```bash
PYTHONPATH=src python -m agenticapp wechat hold reload-workers --json
```

Check the daily loop:

```bash
PYTHONPATH=src python -m agenticapp wechat career-agent status --json
tmux attach -t labcanvas-career-daily
```

## Failure Handling

- If a report is generated but not sent, inspect `send.errors` in
  `manifest.json`.
- If WeChat GUI sending is busy, chat-sync should yield to queued sends and use
  bounded dry-open cycles.
- If current market facts are needed and web access fails, say what was not
  verified and avoid strong stock claims.
- If the memory DB is unavailable, still use project surfaces and write the
  failure into the trace bundle.
