# WeChat Automation GitHub Options

Checked on 2026-06-19 with `gh search repos`.

## Strong Existing Projects

| Repo | Stars at check | Fit | Notes |
| --- | ---: | --- | --- |
| `cluic/wxauto` | 7127 | Windows WeChat GUI automation | Mature Python API for Windows desktop WeChat; not a native Linux solution. |
| `cluic/wxauto4` | 217 | Windows WeChat 4.x | Tracks newer WeChat 4.0 client behavior; still Windows-focused. |
| `lich0821/WeChatFerry` | 6705 | Windows client hook / robot | Powerful and robust for supported Windows WeChat versions, but invasive compared with GUI control and not for the native Linux client. |
| `wechatferry/wechatferry` | 2038 | WeChatFerry upstream/package | Same ecosystem as above. |
| `wechaty/wechaty` | 22851 | Bot/RPA framework | Large ecosystem, but usually depends on puppet/protocol providers and is heavier than a visible desktop task. |
| `wechaty/python-wechaty` | 1826 | Python bot framework | Useful if building a bot architecture, not direct control of this installed Linux WeChat. |
| `Saroth/docker_wechat` | 149 | Linux container with WeChatFerry | Interesting for containerized WeChatFerry; not simpler than current native Linux GUI path. |

Search for `linux wechat xdotool` returned no strong purpose-built repository.

## Decision

For this machine's native Linux WeChat 4.1.x install, prefer the local virtual
desktop GUI route:

- It uses the already logged-in desktop client.
- It avoids protocol hooks, DLL injection, or private API coupling.
- It can be watched through noVNC.
- It works with Chinese and emoji target names through clipboard paste.
- It is fragile only at the visible UI layer, which is acceptable for small
  explicit tasks like sending `test` to a few named chats.

Use Windows-only libraries such as `wxauto` or `WeChatFerry` only when operating
a supported Windows WeChat environment and when hook/API-style automation is
worth the maintenance and account-risk tradeoff.
