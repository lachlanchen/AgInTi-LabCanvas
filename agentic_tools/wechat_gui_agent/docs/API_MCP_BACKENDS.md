# WeChat API And MCP Backend Notes

Checked on 2026-06-19.

## Available Backend Families

| Backend | Platform | Useful For | LabCanvas Decision |
| --- | --- | --- | --- |
| `BiboyQG/WeChat-MCP` | macOS | MCP tools over Accessibility API and screen capture; reads recent chats and sends replies. | Good reference for MCP shape, not usable on this Ubuntu Linux WeChat desktop. |
| `lw396/wechat-mcp` | Windows | WeChatFerry-backed MCP with login, send, contacts, groups, attachments, and chatroom tools. | Strong option if we run a supported Windows WeChat VM; not the current Linux client. |
| `paean-ai/claude-code-wechat` | WeChat iOS + ClawBot | Official ClawBot ilink API bridge into Claude Code channels. | Interesting official/API-like route, but tied to Claude Code Channels and iOS ClawBot. |
| `loonghao/wecom-bot-mcp-server` | WeCom | Enterprise WeChat/WeCom bot MCP. | Useful only if the workflow can move to WeCom. |
| `wechaty/wechaty` | Cross-platform bot SDK | Bot architecture with WeChat puppet/provider backends. | Mature ecosystem, but heavier and provider-dependent for personal WeChat. |
| `ylytdeng/wechat-decrypt` | Windows/macOS/Linux desktop | WeChat 4.x key extraction, SQLCipher DB decrypt, real-time Web UI/SSE, and MCP tools. | Implemented as optional private receive backend; GUI sending remains the production output path. |

## Current Production Choice

For this machine, keep the native Linux WeChat stack:

1. Direct decrypted local DB polling for low-latency reads.
2. Purpose-specific fast agent per group.
3. `gpt-5.5` low reasoning for immediate chat replies.
4. Worker queue for slow CAD, PDF, GitHub, JLC/Wenext, and file tasks.
5. Guarded official GUI sending with title OCR and a global send lock.

This avoids Windows hooks, unsupported protocol clients, or account migration.
Future MCP/API backends should implement the same internal contract:

```text
read_recent(chat, after_id) -> messages
send_text(chat, text) -> evidence
send_file(chat, path) -> evidence
health() -> backend status
```

The monitor should then choose the first healthy backend in this order:
official API or WeCom, trusted MCP bridge on the same account, local DB read,
visible GUI/OCR fallback.

## Implemented External Decrypt Backend

Use the optional external decrypt backend when the direct decrypted cache needs
to be refreshed or inspected independently of the production monitor:

```bash
labcanvas wechat backend install --skip-deps
labcanvas wechat backend status --json
labcanvas wechat backend probe --json
labcanvas wechat backend decrypt --incremental
labcanvas wechat backend monitor-web --port 5679
labcanvas wechat backend api-history --port 5679 --json
labcanvas wechat backend mcp-config
```

`find-keys` is deliberately explicit because it reads process memory and needs
root or `CAP_SYS_PTRACE` on Linux. The `monitor-web` action uses a LabCanvas
localhost-only launcher around the upstream `monitor_web.py`, avoiding the
upstream default all-interface bind. Keep all generated configs, keys, decrypted
DBs, MCP client configs, and API snapshots under `.private/`.
