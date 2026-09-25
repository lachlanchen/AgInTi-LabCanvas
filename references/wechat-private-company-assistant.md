# Private company assistants through the existing WeChat bridge

## Contract

A company group is an ordinary isolated LabCanvas chat, not a new pipeline.
Use the selected personal-WeChat transport even when some members are WeCom
users or the approved reference documents live in WeDrive. Adding a personal
WeChat group must not enable any paused WeCom group, scheduler or Android poller.

The agent handles meaning, research, useful insights and follow-through. Existing
native intake, source ledger, burst coalescing, persistent sessions, worker queue
and receipt-verified sender handle transport. Do not impose a business keyword
router or a fixed response template. Do not create recurring reports without a
separate request.

## Private configuration

Keep the group title, native identity, company documents, session pointers and
working notes under ignored `.private/`, never in public configuration or logs.
Each direct config has its own `chat_name`, exact `message_table`, `state_path`,
`send_target` and stable `session_scope`.

```json
{
  "chat_name": "<EXACT_COMPANY_GROUP>",
  "session_scope": "<STABLE_PRIVATE_COMPANY_SCOPE>",
  "chat_purpose": "company_collaboration",
  "assistant_context": {
    "brief": "Help this team with evidence-grounded answers and decisions. Read the approved reference brief. Preserve attribution, protect confidentiality and avoid repeated acknowledgements. External actions require authorization.",
    "reference_paths": ["<PRIVATE_COMPANY_BRIEF.md>"]
  }
}
```

`assistant_context` is operator-owned configuration, not an inbound-message
field. Only the string `brief` and a list of string `reference_paths` are accepted.
They travel as `capability_profile.operator_context` through the route prompt,
fast reply prompt, worker policy, bounded Codex packet and AgInTi fallback packet.
This does not override cross-chat isolation, authorization or language policy.
Groups without it retain their existing behavior.

The private reference brief should separate verified facts from plans, company
claims from measured functionality, repository history from published releases,
document inventory from documents actually read, and suggestions from approved
decisions, owners and deadlines.

Approved external repositories and another development session may be read-only
references. Never resume, send input to, edit the rollout of, or stop the other
session. Resolve its session ID with the existing collaboration helper rather
than assuming the account-profile directory. Never copy raw histories into git.

## Enrollment and immediate verification

1. Resolve the exact group from the active native contact export. Do not guess a
   database table from a similar display name. Transfer JSON as UTF-8 bytes:
   Windows PowerShell `Get-Content` without `-Encoding UTF8` can corrupt titles.
2. Back up the private transport configuration. Add only this exact target and
   native message table; preserve existing groups and the current account.
3. Run `wechat_tiny11_bridge.sync_once()` and verify account, client readiness,
   table presence and no missing binding. Cached rows alone do not prove login.
4. Inspect the current inbound request. Seed the new monitor cursor immediately
   before that request. Retain older history as context, not as a backlog of
   instructions to execute. Never replay all old messages on enrollment.
5. Include the private config in `WECHAT_DIRECT_CONFIGS` in the existing private
   supervisor environment. `wechat_supervisor_tmux.sh ensure` adds the missing
   monitor without restarting clients, existing monitors or GUI stacks.
6. Process the actual request immediately through the monitor and worker. Do not
   send an operator-authored substitute answer and claim the system handled it.
7. Require an exact native outbound echo for the final answer and a terminal
   queue state. An enqueued task, pressed Enter or generated answer is not proof
   of delivery. Preserve uncertain sends for receipt reconciliation, not retries
   that duplicate the same message.
8. Check self-echo suppression, other groups' cursors, paused services and startup
   configuration. Record the verified result in the private runtime handoff.

Mixed WeChat/WeCom membership adds a colored badge beside the title. Tesseract
can read it as `C`, `Q` or a Chinese character after the member count. The native
title reader retries with chromatic badge pixels whitened, retaining monochrome
title text and the existing exact match. Never fix this by accepting arbitrary
suffixes, prefix matches or a fuzzy group name. Regression tests preserve dark
and grey text, reject similar names and prove the source image is unchanged.

## Memory and confidentiality

The native mirror and source-message ledger retain messages. A stable session
scope accumulates company context without borrowing another chat's memory.
Agent working notes can record decisions, open questions and agreed next steps
beside the private brief, with source message IDs and timestamps. Do not invent
owners or dates, or claim a complete pre-join history was imported.

Configuration provides guidance and source isolation; it is not an OS-level
sandbox for a full-access backend. Use a separately restricted runtime when the
group needs hostile-user isolation. Never describe prompt-only restrictions as a
security boundary. Do not send secrets, other groups' messages, internal paths or
diagnostic logs to the company group.

## Regression coverage

`test_private_assistant_context_reaches_router_and_reply_without_leaking` checks
config validation, prompt propagation and absence from unrelated profiles.
`test_private_group_context_survives_codex_and_fallback_packets` checks worker
packet retention and isolation for both supported agent paths.

Native chat identity, sender serialization, restart durability and outbound echo
remain covered by existing transport and worker tests. Keep the brief small and
link to evidence; do not dump entire histories into every routing call.
