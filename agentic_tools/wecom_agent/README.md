# LabCanvas WeCom Bridge

This sidecar exposes two separate official WeCom transports. The AI Bot
WebSocket receives bot DMs and internal-group events. Tencent's `wecom-cli`
message interface can poll explicitly authorized external WeCom groups. Both
preserve one isolated agent session per chat and use the LabCanvas routine
orchestrator.

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
PYTHONPATH=src python -m agenticapp wecom external bind --json

# Equivalent low-level command:
WECOM_CLI_CONFIG_DIR="$PWD/agentic_tools/wecom_agent/.private/wecom-cli-message-config" \
  agentic_tools/wecom_agent/.private/wecom-cli-runtime/node_modules/.bin/wecom-cli \
  init --noninteractive
PYTHONPATH=src python -m agenticapp wecom external probe --json
PYTHONPATH=src python -m agenticapp wecom external restart --json
```

The CLI bridge admits one exact configured group-name match, stores raw IDs and
message fingerprints privately, processes only the latest recent message on
first binding, and prevents restart backlog floods. Its official message API
currently supports text replies; do not claim generic outbound file delivery
for this channel.

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

Use `#daily` for persistent research preferences:

```text
#daily event-camera reconstruction and hybrid imaging
#daily status
#daily off
```

`#daily` without a topic asks the group what to follow. At the configured time,
the scheduler combines active topics with recent same-group context and queues
one source-grounded briefing per group/day. It returns a concise Chinese digest,
Markdown evidence, and a compiled PDF. Configure the local schedule with
`WECOM_DAILY_RESEARCH_TIME`, `WECOM_DAILY_TOPIC_PROMPT_TIME`, and
`WECOM_DAILY_TIMEZONE`. New owner-enrolled groups are prompted automatically;
set `WECOM_DAILY_AUTO_ENROLL=0` to require a bare `#daily` first.

## Runtime

```text
WeCom AI Bot WebSocket
  -> src/bridge.mjs
  -> scripts/wecom_ingest.py
  -> private durable task queue
  -> wechat_task_worker.run_task_orchestrator
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
```

The tmux stack has `gateway`, `worker`, and `daily` windows. An `external`
window is added when the CLI bridge is enabled and its QR-bound profile exists.
The scheduler only reads local private SQLite state while idle; model quota is
spent only when a due report is enqueued and executed by the worker.

Private state lives under `agentic_tools/wecom_agent/.private/`. Downloaded
source media and task artifacts live under ignored `output/`. The local send
API binds only to `127.0.0.1`; it refuses unknown chat IDs and uses a private
bearer token. Bot secrets, user IDs, chat IDs, and message history must never be
committed.

## Upstream

- Official SDK: <https://github.com/WecomTeam/aibot-node-sdk>
- Official full plugin reference: <https://github.com/WecomTeam/wecom-openclaw-plugin>
- Official external message CLI: <https://github.com/WecomTeam/wecom-cli>
- Agent-channel reference: <https://github.com/QwenLM/qwen-code/tree/main/packages/channels/wecom>

The SDK is pinned in this sidecar's `package-lock.json`. The project does not
copy the upstream implementations.
