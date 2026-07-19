# WeCom API Bridge

LabCanvas has two official WeCom transports and one isolated desktop fallback.
The AI Bot WebSocket handles bot DMs and internal groups. Tencent's
`wecom-cli msg` interface can poll an authorized external group when the tenant grants its
message permission. When that permission is unavailable, an allowlisted GUI
relay can bridge an external group through the owner's WeCom desktop client.
None of these routes reads personal WeChat state.

## What It Can Reach

| Conversation | Transport |
| --- | --- |
| WeCom AI bot direct message | Official AI Bot WebSocket |
| Internal WeCom group containing the bot | Official AI Bot WebSocket; normal mention rules apply |
| External WeCom group | Official `wecom-cli msg` when granted; otherwise exact-name GUI relay |
| Existing personal WeChat group | Not available here; keep using `labcanvas wechat` |

The transports never fall back into each other. In particular, failure to read
an external WeCom group must not trigger personal-WeChat database or GUI access.

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

## External Group Transport

Install and initialize the separate official CLI runtime:

```bash
PYTHONPATH=src python -m agenticapp wecom external install --json
PYTHONPATH=src python -m agenticapp wecom external init --chat AgentTest --json
```

Authorize its message profile with the WeCom mobile app. Credentials stay in
ignored `agentic_tools/wecom_agent/.private/wecom-cli-message-config/`. This is
a tenant capability: `wecom external probe` fails clearly when WeCom does not
grant the `msg` category.

```bash
PYTHONPATH=src python -m agenticapp wecom external authorize --json
PYTHONPATH=src python -m agenticapp wecom external status --json

# Equivalent low-level command:
WECOM_CLI_CONFIG_DIR="$PWD/agentic_tools/wecom_agent/.private/wecom-cli-message-config" \
  agentic_tools/wecom_agent/.private/wecom-cli-runtime/node_modules/.bin/wecom-cli \
  init --noninteractive

PYTHONPATH=src python -m agenticapp wecom external probe --json
PYTHONPATH=src python -m agenticapp wecom external once --json
PYTHONPATH=src python -m agenticapp wecom external restart --json
```

The `authorize` command runs a persistent QR/bridge guard in the `external`
tmux window. It refreshes expired official QR pages in one dedicated browser
tab, records only a fingerprint in private state, and probes the actual `msg`
scope before switching to `bridge_running`. A complete encrypted profile alone
is not readiness. When the tenant denies the scope, status becomes
`message_permission_unavailable` with `gui_fallback_recommended=true`. It restarts
only that external window and does not disconnect the internal LabAgent bot.
Use `bind` only for a bounded one-shot authorization attempt.

Tencent's current AI Bot documentation says long-connection bots do not support
external/customer groups. The external path is therefore a separate,
conditional `wecom-cli msg` capability rather than a fallback from the internal
bot. If the tenant does not grant that capability, official access fails closed
and the separately allowlisted GUI relay may be used instead.

An optional setup-only Android helper can install Tencent's official WeCom APK
after the owner unlocks a connected device:

```bash
agentic_tools/wecom_agent/scripts/wecom_android_setup.sh prepare
agentic_tools/wecom_agent/scripts/wecom_android_setup.sh wait-install
```

It neither bypasses a keyguard nor becomes a runtime transport.

For a Linux workstation, an optional isolated Wine client provides the official
desktop enrollment path when Android installation is unavailable:

```bash
PYTHONPATH=src python -m agenticapp wecom client install --json
PYTHONPATH=src python -m agenticapp wecom client start --json
```

The helper downloads only from Tencent's current official Windows-client URL,
stores the installer and Wine prefix under ignored `.private/`, and binds its
VNC/noVNC ports to localhost. The default viewer is:

```text
http://127.0.0.1:6192/vnc.html?host=127.0.0.1&port=6192&autoconnect=1&resize=scale
```

The client supports official login/enrollment and, when explicitly configured,
the external-group GUI relay described below. It never reads personal-WeChat
state.
The full noVNC client scales the entire remote canvas. A persistent guard keeps
the login QR centered before authentication. After login, WeCom under Wine uses
several synchronized top-level layers, so the guard preserves its native main
window geometry; force-resizing one layer separates the content from its frame.
Reapply the safe fit check with `labcanvas wecom client fit --json` if needed.

## External GUI Relay

Use this owner-account fallback only when the official CLI probe confirms that
the tenant does not grant external-group `msg` permission:

```bash
PYTHONPATH=src python -m agenticapp wecom gui init --chat LabAgent
PYTHONPATH=src python -m agenticapp wecom gui init --chat AgentTest --allow-search-fallback
PYTHONPATH=src python -m agenticapp wecom gui restart --json
PYTHONPATH=src python -m agenticapp wecom gui status --json
PYTHONPATH=src python -m agenticapp wecom gui chats --json
PYTHONPATH=src python -m agenticapp wecom gui messages --chat LabAgent --after 0 --limit 100 --json
PYTHONPATH=src python -m agenticapp wecom gui guide --chat LabAgent --live --json
PYTHONPATH=src python -m agenticapp wecom gui guide --chat AgentTest --live --json
```

The relay watches only exact names in its ignored allowlist. It seeds the
visible history on first run, records later inbound messages in a cursor-based
private SQLite ledger, and sends them into `wecom_ingest.py` with transport
channel `wecom_gui`. The same per-chat agent and worker routines then answer the
question or deliver a daily report to that exact group.
`LabAgent` and `AgentTest` therefore have distinct hashed chat keys, durable
cursors, delivery ledgers, and resumed agent sessions even though one desktop
serializes their GUI operations.

Text and artifacts use one authenticated localhost interface. `task_id` plus
the exact payload provides retry-safe duplicate suppression:

```bash
PYTHONPATH=src python -m agenticapp wecom gui send \
  --chat LabAgent --message 'The report is ready.' \
  --file output/report.pdf --task-id report-20260719 --live --json
```

Unicode text is read back from the composer before Send. Files are staged one
at a time and recorded only after the exact filename is visible in both the
composer and sent history. The detailed CLI, HTTP schemas, cursor rules, and
recovery playbook are in
[`GUI_RELAY_INTERFACE.md`](../agentic_tools/wecom_agent/docs/GUI_RELAY_INTERFACE.md).

The official CLI bridge resolves `AgentTest` by one exact `chat_name` match.
Zero or multiple matches fail closed. On first binding it seeds old history and processes only
the latest recent message, preventing a restart flood. Later polls use private
fingerprints, a short debounce, bounded batching, and stale-message expiry.
Incoming attachments are downloaded by exact `media_id` into an ignored,
source-scoped directory. The external path currently returns text through the
official CLI; generic outbound file messages are not claimed because its `msg`
interface exposes text send only.

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
- The AI Bot WebSocket consumes only new bot-visible events. Neither channel
  can retrieve arbitrary personal-WeChat group history.
- The external CLI path can retrieve only authorized recent WeCom
  conversations (currently a seven-day API window); only exact configured
  group names are admitted.
- Both channels carry `wecom_transport_channel` through ingress, tasks, daily
  scheduling, and delivery. A CLI-origin task cannot fall back to the AI Bot
  WebSocket or the personal-WeChat sender.
- The GUI relay uses the same transport field with value `wecom_gui`. It binds
  only to localhost, authenticates versioned read/send APIs, serializes GUI
  access, and refuses non-allowlisted group names and repository-external files.
- GUI cursor reads are monotonic. Text is composer-readback verified; file
  delivery is composer- and history-verified before the idempotency ledger is
  updated.
- The shared LabCanvas routine orchestrator is execution code only. It does not
  read a personal-WeChat database or GUI for a WeCom task; WeCom source media
  and delivery remain bound to the originating WeCom transport and chat.
- `scripts/wecom_worker_loop.sh` disables personal-WeChat GUI/media/Android
  fallbacks and public-publish preflights before entering that shared runtime.
- WeCom event telemetry is stored in ignored
  `output/wecom/wecom_mirror.sqlite`; it does not use the personal-WeChat
  mirror database.

## GitHub Options Reviewed

The direct dependency is the [official WeCom AI Bot Node SDK](https://github.com/WecomTeam/aibot-node-sdk).
Tencent's [AI Bot help page](https://open.work.weixin.qq.com/help?doc_id=21657)
defines the current internal/external-group scope.
External-group polling uses Tencent's [official WeCom CLI](https://github.com/WecomTeam/wecom-cli).
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
