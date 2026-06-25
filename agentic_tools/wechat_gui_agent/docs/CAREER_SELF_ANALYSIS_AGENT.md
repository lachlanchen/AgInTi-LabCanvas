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
  --send --attach-report --morning-time 08:30 \
  --model gpt-5.5 --reasoning-effort xhigh
```

Status:

```bash
PYTHONPATH=src python -m agenticapp wechat career-agent status --json
```

Reusable user script:

```bash
~/scripts/create-labcanvas-career-daily-tmux.sh
```

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

## Evidence Sources

The daily agent uses read-only evidence:

- `agentic_tools/wechat_gui_agent/.private/wechat_memory.sqlite`
- recent organized memory for `写作 外语 挣钱` and `lachlanchan`
- shallow local repo surface under `/home/lachlan/ProjectsLFS`
- shallow local repo surface under `/home/lachlan/DiskMech/Projects`
- `LazyInvestment` or adjacent investment repo evidence if present
- `VoidAbyss`/`voidabyss` folders if present
- `lazying.art`, `BLOG`, `Documentations`, and `LazySkills` identity surfaces
- current web/GitHub/company research when the question depends on live facts

Raw private chats are not posted back to WeChat. The worker summarizes patterns
and keeps detailed evidence in private trace artifacts.

Default model policy: use `gpt-5.5` with `xhigh` reasoning for daily self
analysis. This report is meant to be high-quality reflection, not a cheap fast
ack. Only override `WECHAT_CAREER_AGENT_EFFORT` for explicit debugging or
emergency latency reasons.

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
- `project_surface.md`: local repo/project evidence.
- `lazyinvestment_snapshot.md`: investment repo evidence if available.
- `voidabyss_snapshot.md`: narrative/IP evidence if available.
- `identity_surface.md`: lazying.art/blog/skill/profile evidence.
- `agent_result.json`: sanitized agent backend metadata and response.
- `private_report.md`: full private Markdown report.
- `share_report.md`: sanitized report safe to attach to WeChat.

Latest convenience paths:

```text
agentic_tools/wechat_gui_agent/.private/output/career_daily/YYYY-MM-DD-career-strategy-private.md
output/wechat_strategy/YYYY-MM-DD-career-strategy.md
```

`output/wechat_strategy/` is the only report path intended for WeChat
attachment. Private trace paths may include local evidence and should stay
ignored by git.

## Agent Method

The prompt asks for nine sections:

1. Today's thesis
2. What to write
3. Talent/profile evidence
4. Money and career opportunities
5. Investment/watchlist notes, with risks
6. The single primary bet
7. 90-day execution plan
8. Today's 3 actions
9. Today's 3 self-discovery questions

The self-discovery section must contain exactly three questions, formatted as
`Q1`, `Q2`, and `Q3`. They should be specific to the day's evidence, answerable
in 10-15 minutes, gently uncomfortable, and useful enough that an honest answer
could change tomorrow's plan. The sender extracts these questions into the
WeChat text message before attaching the share report, so they remain visible
even if file delivery is delayed.

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
