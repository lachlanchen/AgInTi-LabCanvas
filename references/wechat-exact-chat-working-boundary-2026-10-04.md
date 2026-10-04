# Exact-chat working boundary

This is a tightening of the existing bridge and backend runtime, not a new
pipeline. Histories, attribution, resumable session keys, models, source matching,
delivery receipts and configured schedules retain their existing ownership.

## Working roots

`wechat_workspace.chat_workspace()` gives each exact stable session scope a
private folder under `output/chat_workspaces/`. A digest prevents similar names,
non-Latin titles and WeChat/WeCom transport scopes from colliding. Reject symlink
redirects. New worker artifacts live in `tasks/<task-id>/`; already-recorded paths
are preserved rather than moving unfinished work.

The shared `run_agent_session()` scopes every turn that previously used the repo
root. Router and fast-chat turns stay read-only. Workers use the existing writable
workspace sandbox. An explicit dedicated non-root task directory is retained.
The operator boundary is included in both the primary and compact fallback
prompts, without changing requested models or replacing the task instructions.

## Approved reads

Use only operator-configured `assistant_context.reference_paths` and
`workspace_read_paths`, plus exact source copies and explicitly recorded legacy
task artifacts. The worker also grants read-only access to existing exact files
named by its host-generated preflight; it never expands those files to their
parent directories. Shared tool code is readable, not writable, and never grants a
different group's private context. Never allowlist the whole transport `.private`
store, personal Codex session directory, credential folder or workstation home.
Approving a company repository for reading does not authorize editing it or
controlling its development session. Review sensitive subdirectories before
approving an entire repository.

Codex uses the existing native permission-profile machinery: deny the general
filesystem, allow minimal runtime paths and shared tool code for reading, add
the group's approved references as read-only, and allow workspace writes only
for worker roles. Include the installed Codex executable package as a runtime
read so Linux's native sandbox can start. Use `approval_policy=never`; do not
mix custom permission profiles with legacy sandbox flags. See the
[official permissions documentation](https://learn.chatgpt.com/docs/permissions).

AgInTi uses its existing Docker modes and `--read-root`, with the exact workspace
overriding global workspace/host settings. This does not change AgInTi itself.
Other explicitly opted-in backends retain their own tool permission model; do
not claim equivalent OS confinement without validating that backend.

Trusted transport, media preflight, compilation, publishing and senders still
own their existing host runtime state and authorization gates. A shared service
does not make its files part of a group's writable project. This filesystem
boundary is not a sandbox for arbitrary MCP/network/browser services.

## Validation and deployment

Regression tests: `tests/test_wechat_workspace.py`. Cover collision resistance,
symlink rejection, reference propagation, unchanged models, read-only routing,
fallback workspace containment, legacy task recovery and native profile arguments.
Also check that fallback read roots do not make the current task directory
read-only and that malformed operator reference fields cannot become path lists.
Use a token-free native sandbox probe with temporary dummy files to verify own
workspace writes, approved reference reads, no persistent host writes to an
outside path, unchanged reference files, and denied reads of another group's
file. A synthetic parent directory may be writable inside the sandbox's temporary
mount namespace; the relevant check is that it cannot modify the host filesystem.

Reload only idle project-owned monitor/worker/scheduler processes after tests.
Do not restart chat clients, unpause WeCom, drain historical queues, rotate all
sessions, or send test messages to groups. Keep internal smoke evidence private.

On 2026-10-04, the full suite passed (2,292 tests, 16 skipped), both native
filesystem and CLI probes passed, and a live internal Codex turn read the
approved LightMind brief and returned a company-focused answer. No smoke output
was sent to a group. This confirms the scoped filesystem and basic CLI contract,
not every external host service or an equivalent Claude sandbox.
