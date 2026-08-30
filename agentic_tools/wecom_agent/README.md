# LabCanvas WeCom Bridge

This sidecar exposes two official WeCom transports plus isolated desktop and
owner-authorized Android fallbacks. The AI Bot WebSocket receives bot DMs and internal-group events.
Tencent's `wecom-cli` message interface can poll authorized external groups.
When the tenant does not grant that capability, the allowlisted GUI relay can
bridge an external group through the owner's WeCom Wine client, while the
allowlisted Android relay can use an authenticated physical WeCom client. All
preserve one isolated agent session per chat and use the LabCanvas routine
orchestrator.

Prefer the official API transports. They do not require a desktop login:

| Chat surface | Transport | Desktop login |
| --- | --- | --- |
| Bot DM or internal group | AI Bot WebSocket | No |
| Authorized external group in an eligible tenant | `wecom-cli msg` | No |
| Allowlisted external group on an owner-authorized phone | Android relay | No |
| External group without server-side message permission | allowlisted GUI relay | Yes |

Tencent currently limits `wecom-cli msg` to eligible small teams; a server-side
`message_permission_unavailable` result cannot be fixed by patching the desktop
binary. Do not reverse engineer, inject into, or modify the proprietary client.
Use an internal bot-visible group, an eligible official CLI profile, or a
dedicated native Windows/Android client for external-group fallback.

It does not replace the personal-WeChat GUI/database bridge. Existing ordinary
WeChat groups are not exposed by the WeCom API.

There is no cross-transport fallback: WeCom never enters through personal
WeChat, and personal WeChat never enters through this sidecar.

## Setup

```bash
PYTHONPATH=src python -m agenticapp wecom init-config
PYTHONPATH=src python -m agenticapp wecom install
PYTHONPATH=src python -m agenticapp wecom admin
```

The admin browser uses a dedicated persistent profile on display `:93` and is
available through localhost noVNC port `6133` by default. The command's JSON
output reports the actual URL when ports are overridden. It uses the full
noVNC client with `resize=scale` and fits Chrome to the virtual display.

In the WeCom admin console:

1. Open `App Management -> Intelligent Bot`, or navigate to
   `#/aiHelper/list` in the authenticated admin console.
2. Choose `Create Bot -> Manual creation -> API mode creation`.
3. Select `Use long connection`, set the visibility range, and save the bot.
4. Copy its `Bot ID` and `Secret` into the ignored file printed by
   `wecom init-config`.
5. Add the bot to an internal WeCom group or open its direct chat.

Do not confuse `Intelligent Bot` with the self-built `Message Push` app. The
latter is an outbound webhook and cannot provide this bidirectional transport.

Then start and verify the bridge:

```bash
PYTHONPATH=src python -m agenticapp wecom gateway start
PYTHONPATH=src python -m agenticapp wecom doctor --json
PYTHONPATH=src python -m agenticapp wecom daily status --json
```

### Reboot and Crash Recovery

Install the dedicated user service once:

```bash
agentic_tools/wecom_agent/scripts/install_wecom_autostart.sh install
agentic_tools/wecom_agent/scripts/install_wecom_autostart.sh status
loginctl show-user "$USER" -p Linger
```

The service starts at boot through the user's `default.target`, even before an
interactive desktop login when linger is enabled. Every minute it idempotently
verifies the `labcanvas-wecom` tmux stack and recreates missing `gateway`,
`worker`, `daily`, `knowledge`, official external transport, `android-relay`,
`wecom-client`, or `external-gui` windows according to private configuration. The existing
`~/scripts/create_tmux_session.sh` launcher remains a compatible second boot
entry; a private mutation lock makes concurrent starts safe.

Recovery reuses the same ignored Wine prefix and noVNC desktop. It does not
switch accounts, open a new QR flow, send messages, replay old tasks, or restart
a healthy GUI relay. The desktop client supervisor separately restores Xvfb,
x11vnc, websockify, window fitting, and the normal persisted-profile client with
its bounded restart budget. If Tencent invalidates authentication, the service
keeps the profile intact and waits for the owner rather than bypassing login.

Useful checks:

```bash
agentic_tools/wecom_agent/scripts/wecom_autostart.sh status
tmux list-windows -t labcanvas-wecom
curl -fsS http://127.0.0.1:6192/vnc.html >/dev/null
```

The GUI remains available at
`http://127.0.0.1:6192/vnc.html?host=127.0.0.1&port=6192&autoconnect=1&resize=scale`.

For an external WeCom group, install and bind the separate CLI profile:

```bash
PYTHONPATH=src python -m agenticapp wecom external install --json
PYTHONPATH=src python -m agenticapp wecom external init --chat AgentTest --json
PYTHONPATH=src python -m agenticapp wecom external authorize --json
PYTHONPATH=src python -m agenticapp wecom external status --json

# Equivalent low-level command:
WECOM_CLI_CONFIG_DIR="$PWD/agentic_tools/wecom_agent/.private/wecom-cli-message-config" \
  agentic_tools/wecom_agent/.private/wecom-cli-runtime/node_modules/.bin/wecom-cli \
  init --noninteractive
PYTHONPATH=src python -m agenticapp wecom external probe --json
PYTHONPATH=src python -m agenticapp wecom external restart --json
```

`authorize` starts a persistent guard in the dedicated WeCom tmux stack. Until
authorization succeeds it keeps one current official QR page open in the
separate WeCom-admin browser; expired QR pages are replaced rather than
accumulated. After the ignored profile is complete, that same guard starts and
supervises the external bridge. Authorization/restart touches only the
`external` tmux window, so the internal LabAgent WebSocket stays connected.
`bind` remains a bounded one-shot diagnostic.

The Android helper installs Tencent's official APK into the ignored private
directory and waits for the owner to unlock and authorize the device. The
installer never runs under a root shell; it requires an interactive owner
session so the keyguard and authorization prompts stay visible:

```bash
agentic_tools/wecom_agent/scripts/wecom_android_setup.sh prepare
agentic_tools/wecom_agent/scripts/wecom_android_setup.sh wait-install
```

It never bypasses a secure keyguard and never uses personal WeChat as ingress.
After normal WeCom login, configure the guarded external-group relay:

```bash
PYTHONPATH=src python -m agenticapp wecom android init \
  --serial <ADB_SERIAL> --chat LabAgent --chat AgentTest --force --json
PYTHONPATH=src python -m agenticapp wecom android start --json
PYTHONPATH=src python -m agenticapp wecom android status --json
PYTHONPATH=src python -m agenticapp wecom android send \
  --chat AgentTest --mention '<SENDER_DISPLAY_NAME>' \
  --message '处理完成。' --task-id <STABLE_TASK_ID> --live --json
```

The bridge reads only exact allowlisted chats, seeds old visible history instead
of replaying it, and forwards new events into the same isolated worker queue.
Outbound replies verify the exact native title and can select the original
sender through WeCom's real member picker. Plain `@name` text is not treated as
a mention. External member rows may carry WeCom's native `@微信` suffix; the
bridge accepts that one exact suffix while preserving case and rejecting
ambiguous or broadcast matches. Inbound image bubbles are opened in WeCom's
native full-image viewer, `查看原图` is requested when available, and the exact
saved image is pulled from Android MediaStore into ignored private staging
before the vision-capable worker runs. The bridge verifies the exported byte
size, image signature, dimensions, and exact source identity. Chat-bubble crops,
viewer screenshots, and other compressed previews are disabled by default;
ambiguous or unverifiable media remains pending instead of reaching vision. See
[`docs/ANDROID_RELAY_INTERFACE.md`](docs/ANDROID_RELAY_INTERFACE.md).

Android relay health uses the normal three-minute/20-cycle deadline while the
poller is idle. A poll actively performing bounded reconciliation or history
scanning gets a 15-minute deadline so a healthy native scan is not repeatedly
restarted; set `poll_in_progress_stale_seconds` in the ignored Android config
only when that bounded deadline needs tuning. An active poll beyond the
deadline remains unhealthy and eligible for an Android-relay-only restart.
Native-surface recovery is independently rate-limited to one attempt every five
minutes by default (`surface_recovery_cooldown_seconds`). A reachable relay that
reports only that WeCom could not reach the foreground stays degraded without
being process-restarted. A reachable relay reporting a locked Android keyguard
is handled the same way: health stays degraded for a normal human unlock, with
no automated unlock or relay restart loop. Stale or unreachable relays remain
restart-eligible.

On a dedicated transport phone, an Android freeform/floating app can remain
above WeCom even after `am start` succeeds. This machine opts into a narrow
recovery in the ignored Android config:

```json
{
  "dismiss_foreground_conflicts": true,
  "foreground_conflict_packages": ["com.tencent.mm"]
}
```

The bridge force-stops only the currently focused package when it exactly
matches that private allowlist, then starts WeCom again. It never clears app
data, changes an account, or closes an unrelated foreground package. Leave the
option disabled on a phone where the listed app must remain interactively
active.

The minute-level autostart supervisor fingerprints both the health-guard source
and the Android bridge source. An on-disk guard update reloads only the
non-GUI health window; an Android bridge update reloads only `android-relay`,
preserving WeCom app data and the logged-in account. This activates bounded
recovery fixes without restarting either desktop client.

### Login-required recovery

When the health guard reports `wechat_login_required`, the desktop WeCom
client has lost its authenticated session. This is a degraded state, not a
crash: the supervisor does not force-restart the client, because a restart
would not restore the login and could discard the owner's session state.
Recovery is bounded to the following reversible steps, in order:

1. Confirm the client window is alive and not stalled (health probe).
2. If the window is dead or stalled, restart only that exact tmux window.
3. If the window is healthy but logged out, surface the login prompt to the
   owner for a normal human QR/CAPTCHA unlock. The agent never bypasses
   QR/CAPTCHA or changes credentials.
4. Resume any durable queued task that was paused by the login loss, using the
   repository's queue recovery command, after the session is restored.

The supervisor keeps the transport degraded (not restart-looping) while the
owner completes the human unlock, matching the Android keyguard handling above.

### Health-guard issue codes

The deterministic health guard reports the following bounded issue codes. Each
maps to a single reversible recovery action; the agent inspects only the
operational logs needed for the code and never reads or quotes chat content.

| Code | Meaning | Bounded recovery |
| --- | --- | --- |
| `wechat_login_required` | Desktop WeCom lost its authenticated session | Surface login prompt to owner; never bypass QR/CAPTCHA; keep transport degraded until human unlock. The Wine client must be restarted only when its tmux window is confirmed dead or stalled; a healthy logged-in client is never force-restarted. |
| `wecom_queue_stalled` | Durable queue task paused by transport loss | Resume with the repository's queue recovery command |
| `wecom_window_dead` | Exact tmux window is dead or stalled | Restart only that exact tmux window |
| `wecom_orphan_process` | Orphaned process left after a crash | Clear only after proving it is orphaned |

These codes are degraded states, not crashes. The supervisor does not
force-restart a healthy logged-in client, does not change credentials or
accounts, and does not delete user data. Recovery stays local and reversible.

On Linux, the official download page does not provide a native desktop build.
The optional enrollment helper installs Tencent's official Windows client in a
dedicated ignored Wine prefix and exposes only that client on localhost noVNC:

```bash
PYTHONPATH=src python -m agenticapp wecom client install --json
PYTHONPATH=src python -m agenticapp wecom client start --json
PYTHONPATH=src python -m agenticapp wecom client status --json
```

Its default desktop is `:92`, with VNC `5992` and noVNC `6192`. Override these
with `WECOM_CLIENT_DISPLAY`, `WECOM_CLIENT_VNC_PORT`, and
`WECOM_CLIENT_NOVNC_PORT`. Outside GUI-relay mode, the Wine client is only for
official login and the admin console's `Forward to chat` action. It is never a
personal-WeChat ingress, database, media source, or delivery fallback. It can
host the separate allowlisted WeCom GUI relay when the tenant blocks
external-group API access.

Configure that relay only for an exact external group:

```bash
PYTHONPATH=src python -m agenticapp wecom gui init --chat LabAgent
PYTHONPATH=src python -m agenticapp wecom gui init --chat AgentTest --allow-search-fallback
PYTHONPATH=src python -m agenticapp wecom gui restart --json
PYTHONPATH=src python -m agenticapp wecom gui status --json
PYTHONPATH=src python -m agenticapp wecom gui chats --json
PYTHONPATH=src python -m agenticapp wecom gui messages --chat LabAgent --after 0 --limit 100 --json
PYTHONPATH=src python -m agenticapp wecom gui guide --chat LabAgent --live --json
```

Text/file sends are dry runs unless `--live` is present. Always supply a stable
`--task-id` so retrying the exact payload cannot duplicate it. The full local
API and delivery contract is in
[`docs/GUI_RELAY_INTERFACE.md`](docs/GUI_RELAY_INTERFACE.md).

The CLI bridge admits one exact configured group-name match, stores raw IDs and
message fingerprints privately, processes only the latest recent message on
first binding, and prevents restart backlog floods. Its official message API
currently supports text replies; do not claim generic outbound file delivery
for this channel. When the tenant lacks `msg` permission, the bridge reports
`wechat_login_required` as a degraded health state rather than a hard failure,
so the supervisor can keep the transport warm and retry binding on the next
poll cycle without restarting a healthy logged-in GUI. The health guard treats
`wechat_login_required` as a recoverable degraded state: it inspects only the
bounded operational status/logs for that issue code, restarts an exact dead or
stalled tmux window when proven, resumes a durable task, and clears an orphaned
process only after proving it is orphaned. It never sends chat messages,
publishes, changes credentials/accounts, bypasses QR/CAPTCHA, deletes user
data, or restarts a healthy logged-in GUI.

Tencent currently documents that long-connection AI bots do not participate in
external/customer groups. The official CLI guard therefore verifies `msg`
permission before claiming readiness. When it reports
`message_permission_unavailable`, the owner may bind `LabAgent` and `AgentTest`
to the isolated GUI relay; this is still WeCom-only and never permission to
fall back to personal-WeChat state.

The default `owner` access mode pairs the first sender. When that owner first
uses the bot in a group, the exact group is enrolled and its members may request
safe research/tool work. Unrelated groups and non-owner DMs remain rejected.
LabAgent does not perform video publication or other public posting. Dangerous
or out-of-scope requests receive an agent-written refusal or safer alternative;
the existing confirmation gates still protect sensitive in-scope actions. Use
`all` only when the bot is intentionally available to every visible user.

## LabAgent Research Group

After adding the bot to the internal `LabAgent` group, send a new bot-visible
message from the intended owner. WeCom normally requires mentioning the bot in
a group. The official API does not expose earlier group history, so enrollment
starts with the first delivered event.

Normal messages are forwarded to a persistent, isolated LabCanvas agent session.
The group can request literature research, research proposals, lawful paper
downloads, Markdown/TeX/PDF reports, editable paper figures, and the other
LabCanvas CAD/PCB/Blender design routines with the same worker permissions as
the private LazyResearch group. Results and requested artifacts return to the
same group. Video/publication work is deliberately outside this bot's scope.

The route agent answers at conversation level, not once per transport row.
Every inbound message keeps its sender and source identity in history, while
the agent may combine related fragments, use a contribution as context, stay
silent during peer discussion, or bind a correction to one exact active task.
A different member can interrupt an active task only when the route agent marks
the message related and binds it to that task ID; attribution is never merged.
If the route backend is temporarily unavailable, ordinary discussion is stored
without creating a worker backlog. Explicit research, files, and tool/artifact
requests still use the bounded deterministic fallback. Backend stderr, DNS,
WebSocket, and MCP diagnostics remain private and are never sent into the
group.

The token-free health guard distinguishes live coverage failures from old audit
evidence. Active or recently terminal messages that remain unverified still
degrade health and trigger bounded repair. Older terminal rows remain listed as
`historical_coverage_unresolved_ids`, but they do not keep the transport
permanently degraded and are never replayed after a restart.
Scheduled personal-WeChat career and MEMO deliveries likewise remain healthy
while their scheduler has a persisted future retry; they become overdue only
after that retry is actually missed.
`historical_coverage_categories` separates delivered-but-unverified results,
expired delivery, and worker failures without spending model tokens. Backend
stderr and diagnostic payloads remain private. A legacy task whose chat scope
starts with `wecom:` is always routed through WeCom and can never fall back to
the personal-WeChat sender, even when older source metadata is incomplete.

Each member gets one daily-research subscription. End a message with `#daily`
to add a distinct interest; later interests accumulate in that same member
record instead of creating additional daily jobs:

```text
event-camera reconstruction and hybrid imaging #daily
organoid spatial quality control #daily
status #daily
off #daily
```

The older prefix form remains accepted for compatibility. A bare `#daily` asks
the group what to follow. The GUI relay derives a private stable member identity
from the visible sender label and refuses to save a preference when identity is
unresolved. Each newly added interest also queues one idempotent first briefing
immediately; repeating the same interest does not queue it again. This initial
run does not consume the normal scheduled report. At 06:00 `Asia/Hong_Kong` by
default, the scheduler creates one source-grounded briefing per active member
subscription. Multiple interests from the same member remain one job, while
different members are kept separate and run sequentially through the single
worker queue. Each job returns a concise Chinese digest, Markdown evidence, and
a LaTeX-compiled Nature-style PDF. Daily research tasks have no queue deadline:
scheduled daily research uses GPT-5.6 SOL at `xhigh`
effort, while other durable work may run from low through ultra effort, and
completed exact-task reports are recovered and delivered if the final agent
response is interrupted. Configure the local schedule with
`WECOM_DAILY_RESEARCH_TIME`, `WECOM_DAILY_TOPIC_PROMPT_TIME`, and
`WECOM_DAILY_TIMEZONE`. New owner-enrolled groups are prompted automatically;
set `WECOM_DAILY_AUTO_ENROLL=0` to require a bare `#daily` first. `off #daily`
disables only that member's subscription; other members' interests remain.

## Private Member Knowledge

Every stable WeCom member has a private knowledge partition. Incoming papers
and other attachments are indexed immediately; completed worker and daily tasks
add their returned artifacts plus durable ideas, insights, intuitions,
hypotheses, interests, decisions, preferences, and useful agent conclusions.
Each row retains its exact member, chat, source message/task, checksum, and
timestamp. The agent only receives a bounded view for the same member in the
same chat, so another member's records cannot enter its prompt.

State remains local and ignored by git:

- database: `agentic_tools/wecom_agent/.private/wecom_member_knowledge.sqlite`
- archive: `output/wecom/member_knowledge/<member-key>/<category>/<year>/<month>/`

Use explicit markers such as `#idea`, `#insight`, `#intuition`, `#interest`,
`#hypothesis`, or `#note` when a message must be retained deterministically.
The route/worker agents may also return structured memory items, but are told
not to store greetings, credentials, quoted paper text as a personal belief, or
speculative profiling.

```bash
PYTHONPATH=src python -m agenticapp wecom knowledge status --json
PYTHONPATH=src python -m agenticapp wecom knowledge sync --json
PYTHONPATH=src python -m agenticapp wecom knowledge search \
  --member-key MEMBER_KEY --kind paper --query microscopy --json
PYTHONPATH=src python -m agenticapp wecom knowledge export \
  --member-key MEMBER_KEY --output-dir output/private-export --json
```

Search and export use hashed member keys and never emit raw transport user IDs.
Exports are private operator artifacts and should remain under ignored paths.

## Runtime

```text
WeCom AI Bot WebSocket
  -> src/bridge.mjs
  -> scripts/wecom_ingest.py
  -> private durable task queue
  -> scripts/wecom_worker_loop.sh
  -> shared run_task_orchestrator execution routines
  -> persistent per-chat Codex/AgInTi session
  -> localhost authenticated delivery API
  -> WeCom text/media send

Authorized external WeCom group
  -> official wecom-cli msg polling
  -> scripts/wecom_cli_bridge.py
  -> scripts/wecom_ingest.py
  -> the same private queue and isolated agent session
  -> separate localhost CLI delivery API
  -> official wecom-cli text send

Allowlisted external WeCom group without CLI permission
  -> isolated WeCom Wine client on :92
  -> scripts/wecom_gui_bridge.py native per-bubble Copy + cursor ledger
  -> scripts/wecom_ingest.py
  -> the same private queue and isolated agent session
  -> authenticated localhost GUI delivery API
  -> verified Unicode text/file send to the exact group
```

The GUI relay reads visible text with WeCom's native Copy command and the Wine
Unicode clipboard. OCR is only a bubble locator and bounded fallback. It never
rewrites the copied request; the route agent's plan is advisory, while the
worker receives the exact original text and may normalize identifiers only
after checking authoritative evidence. Native-copy context menus are closed
before the GUI lock is released and outbound compose clears stale transient UI
before pasting, so reads cannot block later verified delivery.

The tmux stack has `gateway`, `worker`, `daily`, `knowledge`, `health`, and
`quota` windows. The
knowledge window incrementally indexes new message rows and changed completed
tasks without model calls or full-history polling. An `external`
window is added whenever the external bridge is enabled. Before authorization
it maintains the official QR; afterward it probes message permission before it
can report `bridge_running`. `wecom-client` and `external-gui` windows are added
when `wecom_gui_bridge.local.json` is enabled. The client supervisor preserves
the same Wine prefix, never enters account-switch mode implicitly, and limits
restart attempts to protect device trust. The GUI relay uses passive
screen-change detection while idle; active navigation runs only after a visible
change or bounded rescan. Security/QR challenges start a durable input
quarantine and clean recovery window. Reconnect recovery waits for every
allowlisted chat to remain ready, composer operations use X11 input by default,
and sends are paced to prevent retry bursts.
The scheduler only reads local private SQLite state while idle; model quota is
spent only when a due report is enqueued and executed by the worker.
The quota window reads `account/rateLimits/read` from the official local Codex
app server once per minute and caches only the percentage/reset metadata under
ignored private storage. Below 5% remaining, the next actionable request gets a
concise warning in its ordinary reply or acknowledgement without blocking the
task or repeating in the final result.

Inspect the current snapshot without spending model quota:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/codex_quota_status.py probe --json
```

`labcanvas-wecom-autostart.service` is the outer recovery boundary. It survives
ordinary shell and desktop logouts through the user manager, starts the stack
after reboot, and periodically calls the same idempotent tmux repair path used
by the CLI. It never owns chat state itself; durable queues, cursors, delivery
ledgers, daily subscriptions, and member knowledge remain in ignored storage
and are resumed by their normal windows.

Private state lives under `agentic_tools/wecom_agent/.private/`. Downloaded
source media and task artifacts live under ignored `output/`; WeCom event
telemetry uses `output/wecom/wecom_mirror.sqlite`, never the personal-WeChat
mirror. The local send
API binds only to `127.0.0.1`; it refuses unknown chat IDs and uses a private
bearer token. Bot secrets, user IDs, chat IDs, and message history must never be
committed.

`wecom_worker_loop.sh` is the WeCom-specific worker boundary. It disables
personal-WeChat GUI file recovery, media-sync fallback, personal-WeChat Android
text fallback, and publication preflights before invoking the shared routine
orchestrator. The separate allowlisted WeCom Android transport remains
available through its authenticated localhost API. It
keeps route/chat turns fast, while durable work uses GPT-5.6 SOL with dynamic
effort and long per-turn hang watchdogs instead of a ten-minute research limit.

## Upstream

- Official SDK: <https://github.com/WecomTeam/aibot-node-sdk>
- Official AI Bot scope/help: <https://open.work.weixin.qq.com/help?doc_id=21657>
- Official full plugin reference: <https://github.com/WecomTeam/wecom-openclaw-plugin>
- Official external message CLI: <https://github.com/WecomTeam/wecom-cli>
- Agent-channel reference: <https://github.com/QwenLM/qwen-code/tree/main/packages/channels/wecom>

The SDK is pinned in this sidecar's `package-lock.json`. The project does not
copy the upstream implementations.
