# LabCanvas WeCom Bridge

This optional sidecar connects LabCanvas to the official WeCom AI Bot
WebSocket channel. It receives bot DMs and WeCom group messages, decrypts
official media downloads, preserves a separate Codex session per chat, queues
nontrivial work through the existing LabCanvas routine orchestrator, and sends
text and artifacts back through the same official connection.

It does not replace the personal-WeChat GUI/database bridge. Existing ordinary
WeChat groups are not exposed by the WeCom API.

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
```

The default `owner` access mode pairs the first sender and rejects other users
unless their user IDs are listed in `WECOM_ALLOWED_USERIDS`. Use `all` only
when the bot is intentionally available to every member who can see it.

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
```

Private state lives under `agentic_tools/wecom_agent/.private/`. Downloaded
source media and task artifacts live under ignored `output/`. The local send
API binds only to `127.0.0.1`; it refuses unknown chat IDs and uses a private
bearer token. Bot secrets, user IDs, chat IDs, and message history must never be
committed.

## Upstream

- Official SDK: <https://github.com/WecomTeam/aibot-node-sdk>
- Official full plugin reference: <https://github.com/WecomTeam/wecom-openclaw-plugin>
- Agent-channel reference: <https://github.com/QwenLM/qwen-code/tree/main/packages/channels/wecom>

The SDK is pinned in this sidecar's `package-lock.json`. The project does not
copy the upstream implementations.
