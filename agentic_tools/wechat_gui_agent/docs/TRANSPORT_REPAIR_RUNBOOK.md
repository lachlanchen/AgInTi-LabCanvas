# Transport Repair Runbook (WeChat / WeCom)

Durable repair procedure for the health-guard issue codes below. This runbook
is the operational contract for the **transport repair agent**: it reuses the
repository's existing supervisors, health probes, queue recovery commands, and
tests. It never reads or quotes chat content, never bypasses login/QR/CAPTCHA,
never changes credentials or accounts, never sends chat messages, and never
restarts a healthy logged-in GUI.

## Issue codes covered

| Code | Meaning | Typical classification |
| --- | --- | --- |
| `wechat_login_required` | Official WeChat client state is `entry_required`; reason `login_required`; `human_action_required=true` | Human-action blocker (owner must scan QR) |
| `wecom_login_required` | WeCom profile/session requires owner re-authorization | Human-action blocker (owner must authorize) |
| `android_poll_stalled` | WeCom Android relay poll unhealthy; e.g. `surface=other_app`, `BridgeError: WECOM_ANDROID_BUSY: serialized GUI control exceeded 5.0s` | Degraded-but-reachable surface conflict; restart-eligible only when stale/unreachable |

Related but non-blocking signals: queue `historical_coverage_unresolved_ids`
(`delivered_unverified`, `delivery_expired`, `worker_failed`) are **residue
recovery** items, not active faults. Active faults are: missing tmux windows,
stale monitor heartbeats, stale/in-progress queue tasks, or an unreachable
endpoint.

## Step 0 -- Read the health guard JSON

The guard provides the authoritative starting state. Key fields:

- `issues[]` -- codes + detail (do not act on codes not listed above).
- `tmux.{wechat,wecom}` -- `running`, `missing_windows`, `window_count`.
- `direct_monitors` -- per-config `heartbeat_ok`, `state` (`client_unavailable`
  is expected while the client itself is `entry_required`).
- `android` -- `endpoint_reachable`, `poll_healthy`, `surface_state`,
  `consecutive_poll_failures`, `last_poll_error`.
- `queues.{wechat,wecom}` -- `stale_ids`, `coverage_unresolved_ids`,
  `in_progress`, `oldest_active_seconds`.

## Step 1 -- Verify with the existing supervisors and probes

Run only the bounded commands needed for the issue codes. Never grep chat
content; restrict log inspection to issue-code keywords
(`entry_required`, `login_required`, `WECOM_ANDROID_BUSY`, `heartbeat`,
`stale`, `restart-eligible`).

```bash
# tmux stack integrity (read-only)
tmux list-windows -t labcanvas-wecom
tmux list-windows -t labcanvas-wechat

# autostart supervisor status (read-only)
agentic_tools/wecom_agent/scripts/wecom_autostart.sh status
agentic_tools/wecom_agent/scripts/install_wecom_autostart.sh status

# health probes (read-only)
PYTHONPATH=src python -m agenticapp wecom doctor --json
PYTHONPATH=src python -m agenticapp wecom daily status --json
PYTHONPATH=src python -m agenticapp wecom android status --json
labcanvas wechat health --json
labcanvas wechat control-map --json
```

## Step 2 -- Classify before acting

1. **`wechat_login_required` / `wecom_login_required`**
   - The health guard reports `human_action_required=true` and the client
     state is `entry_required` with a short validity window
     (`state_valid_for_seconds` ~90). This is a **human-action blocker**.
   - Monitors are expected to report `client_unavailable` while heartbeats
     stay fresh. Heartbeats fresh + client unavailable => **no automated
     restart**. Restarting the GUI would only reopen the same login screen and
     is explicitly out of scope (never restart a healthy logged-in GUI, never
     bypass login).
   - The only safe, allowed action is to keep supervisors alive and wait for
     the owner to scan the QR code. Report the exact window/URL for the owner
     (e.g. the WeChat noVNC URL or WeCom external authorize guard), then stop.
   - If the owner authorizes later, verify with `labcanvas wechat health
     --json` or `wecom external status --json` before declaring recovery.

2. **`android_poll_stalled` (reachable endpoint)**
   - Per the WeCom README: a reachable relay that reports only that WeCom
     could not reach the foreground **stays degraded without being
     process-restarted**. Surface recovery is rate-limited
     (`surface_recovery_cooldown_seconds`, default 5 minutes); a locked
     keyguard also waits for a human unlock. Stale or unreachable relays are
     the only restart-eligible cases.
   - If `endpoint_reachable=true` and `surface_state` is `other_app`:
     do **not** force-stop or restart. Confirm the Android window exists in
     `tmux list-windows -t labcanvas-wecom` and that no `stale_ids` exist.
   - If the relay is **unreachable or stale** (deadline exceeded, e.g.
     3-minute/20-cycle idle deadline or 15-minute in-progress deadline), the
     allowed repair is an Android-relay-only restart. Prefer the existing
     supervisor command over raw kills:
     `PYTHONPATH=src python -m agenticapp wecom android restart --json`
     (or the stack's documented relay restart) -- this preserves WeCom app
     data and the logged-in account.

3. **Queue residue (`historical_coverage_unresolved_ids`)**
   - These are past delivery failures, not active queue faults. Active queue
     faults look like `stale_ids` or `in_progress` older than the processing
     deadline (`processing_stale_after_seconds` ~900).
   - To resume one durable task safely, use the repository's recovery
     commands (they reapply the safety/delivery contract without rerunning the
     model or task tools):
     ```bash
     PYTHONPATH=src python -m agenticapp wechat worker reprocess TASK_ID \
       "recover completed report" --artifact-recovery-only --send \
       --queue agentic_tools/wecom_agent/.private/wecom_task_queue.jsonl
     PYTHONPATH=src python -m agenticapp wechat worker repair-result TASK_ID --send
     ```
   - These commands are the only allowed way to touch queued deliveries; never
     hand-edit the queue JSONL and never send through a non-supervisor path.

## Step 3 -- Restarting an exact dead/stalled tmux window

Restart **only** the exact window named by the guard, never the whole session,
and never a healthy window:

```bash
# Confirm the window exists and is the right one
tmux list-windows -t labcanvas-wecom
tmux capture-pane -pt labcanvas-wecom:<exact-window> | tail -40

# Exact-window restart via the stack's own command where available
PYTHONPATH=src python -m agenticapp wecom gui restart --json        # GUI relay window only
PYTHONPATH=src python -m agenticapp wecom external restart --json   # external window only
labcanvas wechat hold restart                                       # supervisor/workers, NOT the desktop
labcanvas wechat hold reload-workers                                # code-change reload, keeps desktop
```

- `labcanvas wechat hold restart` / `reload-workers` never restart the WeChat
  desktop. Use `restart-all` only if the owner explicitly wants the official
  client closed and reopened (may require mobile confirmation).
- After any restart, capture a fresh run marker / heartbeat / PID before
  treating capture text as current evidence (tmux scrollback persists).

## Step 4 -- Clearing an orphaned process (only after proof)

Allowed only when all of the following are proven:

1. The PID's command line matches the dead/stalled window's role
   (`ps -o pid,ppid,lstart,cmd -p PID` and full `ps` scan).
2. Its parent (PPID) is gone (init/reparented) and no live supervisor or tmux
   pane claims it.
3. No newer replacement process is running the same role.

Only then, kill the exact PID (`kill <PID>`, verify with `ps -p <PID>`), and
let the supervisor restart the window. Never kill a process whose parent
supervisor is alive.

## Step 5 -- Focused tests (read-only / dry-run)

```bash
PYTHONPATH=src python -m agenticapp wechat selftest --suite all --json
PYTHONPATH=src python -m agenticapp wechat selftest --suite publish-poststage --json
PYTHONPATH=src python -m agenticapp wecom doctor --json
```

Selftests exercise transport, routine contracts, resume, and poststage repair
without sending live messages. A focused failing test narrows the fault to
one window; report the failing suite name, not chat content.

## Step 6 -- Verify and report

Re-run the Step 1 probes. Expected end state per code:

- `wechat_login_required` -> resolved only by owner QR scan; guards/supervisors
  healthy, no restart performed, owner-facing URL reported.
- `android_poll_stalled` -> `poll_healthy=true` or, if reachable-but-degraded,
  no automated restart performed and cooldown respected.
- Queue residue -> `coverage_unresolved_ids` shrinks only through
  `reprocess`/`repair-result`; never claimed resolved without evidence.

## Boundaries (hard no-go)

- No chat message sends, publishes, orders, credential/account changes.
- No QR/CAPTCHA/login bypass of any kind; no WeChat/WeCom client injection.
- No reading or quoting chat content -- bounded log inspection only.
- No restart of a healthy logged-in GUI; no whole-session teardown.
- No editing queue files by hand; no deleting user data.

## Escalation

If the fault remains unresolved after all bounded steps above, include the
exact marker `ESCALATE_HIGH` once in the final report. It must not appear in
any normal (resolved or human-blocked) report.
