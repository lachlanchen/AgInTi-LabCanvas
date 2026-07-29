# JLC Dedicated Browser Stack

JLCPCB/JiaLiChuang ordering has a browser identity separate from the existing
AgInTi Browser/Xiaoyunque session.

## Fixed Identity

| Resource | JLC value |
| --- | --- |
| X display | `:104` |
| VNC | `127.0.0.1:5924` |
| noVNC | `127.0.0.1:6124` |
| CDP | `127.0.0.1:49237` |
| Chrome profile | `~/.cache/jlcpcb-order-shared` |
| State/log root | `~/.local/state/jlcpcb-order/browser/` |

The profile name is historical. It is dedicated to JLC and is not shared with
the AgInTi Browser/Xiaoyunque profile.

## Commands

Inspect the contract without opening a browser:

```bash
agentic_tools/jlcpcb_order_agent/scripts/jlc_browser_stack.sh config --json
agentic_tools/jlcpcb_order_agent/scripts/jlc_browser_stack.sh status --json
agentic_tools/jlcpcb_order_agent/scripts/jlc_browser_stack.sh url
```

Start or reuse:

```bash
agentic_tools/jlcpcb_order_agent/scripts/jlc_browser_stack.sh start
```

Visible URL:

```text
http://127.0.0.1:6124/vnc.html?host=127.0.0.1&port=6124&autoconnect=1&resize=scale
```

Repeated starts reuse the existing process and JLC tab. A new tab is created
only when the dedicated browser contains no JLC page.

Stop only this stack:

```bash
agentic_tools/jlcpcb_order_agent/scripts/jlc_browser_stack.sh stop
```

## Profile and Login Rules

- Never point JLC and Xiaoyunque at the same `--user-data-dir`.
- Never run two Chrome processes against one profile directory.
- A one-time profile copy can carry cookies on the same Linux account, but only
  while the source browser is fully stopped. Copying live Chromium SQLite files
  can corrupt the clone.
- Cookie transfer is not guaranteed. A site may expire sessions, bind them to a
  device, or require login again.
- A copied profile immediately becomes independent; later cookies and tabs do
  not synchronize.
- Do not copy password stores or passkeys between services. Log in once in the
  dedicated profile when a copied web session is rejected.

The existing JLC profile already contains its prior local session state, so no
copy from the live Xiaoyunque profile is required. Leaving Xiaoyunque running
also means it is not safe to clone that profile now.

## Isolation Contract

The old `launch_shared_chrome.sh` filename remains for scripts written against
the previous interface. It delegates to the dedicated JLC stack and fails when
`JLCPCB_TAB_CDP_PORT` is set. This prevents accidental injection into AgInTi
Browser CDP `9344`.

The Books/LibGen browser remains owned by the Books project and is not changed
by this stack.
