# WeCom API Bridge

LabCanvas supports an official, bidirectional WeCom route through an AI Bot
WebSocket connection. This is preferable to GUI automation when the target
conversation is a WeCom bot DM or an internal WeCom group: it needs no public
callback URL, maintains its own heartbeat/reconnect loop, and supports text,
image, mixed, voice transcript, file, and video input.

## What It Can Reach

| Conversation | Official bridge |
| --- | --- |
| WeCom AI bot direct message | Yes |
| Internal WeCom group containing the bot | Yes; group delivery normally follows WeCom's bot mention rules |
| Existing personal WeChat group | No; keep using `labcanvas wechat` |
| External customer/WeChat group | Different WeCom customer-contact or archive product; not enabled here |

## One-Time Setup

```bash
PYTHONPATH=src python -m agenticapp wecom init-config
PYTHONPATH=src python -m agenticapp wecom install
PYTHONPATH=src python -m agenticapp wecom admin
```

The last command opens the WeCom admin console in the established shared
browser on the isolated `:98` desktop. View it at:

```text
http://127.0.0.1:6099/vnc_lite.html?host=127.0.0.1&port=6099&autoconnect=1&scale=1
```

Scan the admin QR code, create an intelligent bot in long-connection mode, and
place its Bot ID and Secret in:

```text
agentic_tools/wecom_agent/.private/wecom.local.env
```

Do not paste those values into tracked JSON, documentation, shell history, or
chat. Start the gateway after the credentials are present:

```bash
PYTHONPATH=src python -m agenticapp wecom gateway start
PYTHONPATH=src python -m agenticapp wecom doctor --json
```

Send the bot a direct message first. With the default access policy, that user
becomes the paired owner. Add the bot to an internal group and mention it to
test group routing. Each DM/group gets a hashed LabCanvas chat name and an
independent route/worker Codex session.

## Reliability Contract

- The Node process uses the official `@wecom/aibot-node-sdk` and maintains one
  authenticated WebSocket connection with heartbeat and reconnect.
- Incoming message IDs are deduplicated across restarts.
- Encrypted media URLs and AES keys are used only in memory; only decrypted,
  source-scoped files are retained under ignored `output/wecom/inbound/`.
- Simple chat can return through the callback stream. Tool work is queued and
  returns later through proactive text/media send.
- Worker retries are idempotent: delivered text chunks and files are recorded
  privately by task ID before a retry.
- The proactive-send API listens only on localhost, requires a random bearer
  token, and refuses chats the gateway has not previously observed.
- Payments, purchases, public publishing, deletion, credential changes, and
  other irreversible actions keep the existing current-message authorization
  gates.

## GitHub Options Reviewed

The direct dependency is the [official WeCom AI Bot Node SDK](https://github.com/WecomTeam/aibot-node-sdk).
The [official WeCom OpenClaw plugin](https://github.com/WecomTeam/wecom-openclaw-plugin)
is the strongest full-feature reference for chat isolation, message parsing,
stream expiry, and media delivery. The [Qwen Code WeCom channel](https://github.com/QwenLM/qwen-code/tree/main/packages/channels/wecom)
is a useful agent-runtime adapter reference. `loonghao/wecom-bot-mcp-server`
is useful for outbound webhook sends, but a webhook MCP alone cannot receive
group messages, so it is not the transport used here.

The legacy self-built-app callback route remains possible, but requires a
public HTTPS endpoint plus CorpID, app secret, AgentID, Token, and
EncodingAESKey. Use it only if the account cannot create a long-connection AI
bot or needs self-built-app events unavailable to bot mode.
