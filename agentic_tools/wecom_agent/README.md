# LabCanvas WeCom Bridge

This sidecar exposes two official WeCom transports and one isolated desktop
fallback. The AI Bot WebSocket receives bot DMs and internal-group events.
Tencent's `wecom-cli` message interface can poll authorized external groups.
When the tenant does not grant that capability, the allowlisted GUI relay can
bridge an external group through the owner's WeCom Wine client. All three
preserve one isolated agent session per chat and use the LabCanvas routine
orchestrator.

Prefer the official API transports. They do not require a desktop login:

| Chat surface | Transport | Desktop login |
| --- | --- | --- |
| Bot DM or internal group | AI Bot WebSocket | No |
| Authorized external group in an eligible tenant | `wecom-cli msg` | No |
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

If an Android WeCom client is needed only to scan the QR, the optional helper
downloads Tencent's official APK into the ignored private directory and waits
for the owner to unlock the device:

```bash
agentic_tools/wecom_agent/scripts/wecom_android_setup.sh prepare
agentic_tools/wecom_agent/scripts/wecom_android_setup.sh wait-install
```

It never bypasses a secure keyguard and never uses personal WeChat as ingress.
The Android client remains setup-only.

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
for this channel.

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
a LaTeX-compiled Nature-style PDF. Daily research tasks
have no queue deadline: GPT-5.6 SOL may run from low through ultra effort, and
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

The tmux stack has `gateway`, `worker`, `daily`, and `knowledge` windows. The
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

Private state lives under `agentic_tools/wecom_agent/.private/`. Downloaded
source media and task artifacts live under ignored `output/`; WeCom event
telemetry uses `output/wecom/wecom_mirror.sqlite`, never the personal-WeChat
mirror. The local send
API binds only to `127.0.0.1`; it refuses unknown chat IDs and uses a private
bearer token. Bot secrets, user IDs, chat IDs, and message history must never be
committed.

`wecom_worker_loop.sh` is the WeCom-specific worker boundary. It disables
personal-WeChat GUI file recovery, media-sync fallback, Android text sending,
and publication preflights before invoking the shared routine orchestrator. It
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
