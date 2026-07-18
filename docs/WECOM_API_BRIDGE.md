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

The last command opens the WeCom admin console in a dedicated browser profile
on the isolated `:93` desktop. It intentionally does not share the
Xiaoyunque/WeChat browser profile. View it at:

```text
http://127.0.0.1:6133/vnc.html?host=127.0.0.1&port=6133&autoconnect=1&resize=scale
```

The default VNC and CDP ports are `5933` and `9353`. Override them with
`WECOM_ADMIN_VNC_PORT`, `WECOM_ADMIN_NOVNC_PORT`, and
`WECOM_ADMIN_CDP_PORT` when needed; `labcanvas wecom admin --json` reports the
actual noVNC URL.

After login, open `App Management -> Intelligent Bot` (route
`#/aiHelper/list`). Choose `Create Bot -> Manual creation -> API mode
creation`, select `Use long connection`, set the visibility range, and save.
This is separate from the self-built `Message Push` webhook app. Place the
resulting Bot ID and Secret in:

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

The owner can instead pair from the first group message. That action enrolls
only that exact group when `WECOM_GROUP_MEMBER_ACCESS=trusted` (the default).
Subsequent members of the enrolled group may request safe research and artifact
work, while unrelated groups and DMs remain closed. LabAgent uses the same
research/drawing/design worker permissions as the private LazyResearch group,
but video publication and other public posting are disabled for this bridge.
Dangerous requests are soft-filtered by the agent, with exact-chat isolation and
the existing sensitive-action approval gates retained as hard boundaries.

## Daily Research

An enrolled research group can persist one topic per member:

```text
#daily computational microscopy and event sensors
#daily status
#daily off
```

A bare `#daily` enables the group and asks for a topic. At
`WECOM_DAILY_RESEARCH_TIME` (default `09:00` in `Asia/Hong_Kong`), the `daily`
tmux worker queues at most one report per group/date. It uses the same persistent
per-group agent and research routine as ordinary requests, combines active
preferences with bounded recent group context, verifies current papers and
project sources, and returns a Chinese digest plus Markdown/PDF evidence. When
no topic is configured, it asks once at `WECOM_DAILY_TOPIC_PROMPT_TIME` rather
than consuming model quota.

```bash
PYTHONPATH=src python -m agenticapp wecom daily status --json
PYTHONPATH=src python -m agenticapp wecom daily run --force --json
tmux list-windows -t labcanvas-wecom
```

Normal LabAgent messages may ask for literature reviews, research proposals,
lawful open-access paper downloads, TeX/PDF reports, editable paper figures,
CAD/PCB, Blender, and scientific design artifacts.
They are queued through `wechat_task_worker.run_task_orchestrator`; deterministic
transport code does not replace the agent's research judgment.

## Reliability Contract

- The Node process uses the official `@wecom/aibot-node-sdk` and maintains one
  authenticated WebSocket connection with heartbeat and reconnect.
- Incoming message IDs are deduplicated across restarts.
- Daily report and topic-prompt IDs are deduplicated per group/date across restarts.
- Encrypted media URLs and AES keys are used only in memory; only decrypted,
  source-scoped files are retained under ignored `output/wecom/inbound/`.
- Simple chat can return through the callback stream. Tool work is queued and
  returns later through proactive text/media send.
- Worker retries are idempotent: delivered text chunks and files are recorded
  privately by task ID before a retry.
- The proactive-send API listens only on localhost, requires a random bearer
  token, and refuses chats the gateway has not previously observed.
- Video publication and other public posting are disabled for LabAgent. Other
  sensitive actions retain the existing current-message authorization gates.
- The bridge can consume only new bot-visible events. It cannot retrieve prior
  messages from an arbitrary personal-WeChat or WeCom group history.

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
