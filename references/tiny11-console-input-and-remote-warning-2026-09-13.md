# Windows App Views and the WeCom Remote-Control Notice

## Current Status

The later authorized VM reboot replaced the split views with one shared
2560x1440 desktop at <http://127.0.0.1:6143/>. WeCom is left, WeChat right.
Guest TightVNC is stopped/Manual, the auxiliary MttVDD display is disabled,
and the split-view service/reflectors are stopped and disabled. No device
identity or app security logic was patched. See the completed procedure and
login limitations in [the transport handoff](tiny11-wecom-labcanvas-transport.md#shared-desktop-2026-09-13).

The sections below record the earlier two-monitor investigation. Its 6144
URLs and active TightVNC description are historical, not the current route.
Removing unnecessary control layers and redundant focus events does not prove
the WeCom warning is resolved. After reboot, WeCom requires login; authenticated
message and file delivery must be checked separately. The owner accepts Ubuntu
WeChat plus mobile WeCom as the fallback if the Windows warning keeps recurring.

## Evidence and Limits

The user observed a WeCom remote-control notice after adding separate browser
views. A passive phone screenshot on September 13 also showed a WeCom Team
notification preview referring to remote operation. The complete notification
and its timestamp were not inspected; causation is not established.

This is separate from the confirmed Windows memory-exhaustion/DWM crash in
[the recovery report](labcanvas-windows-memory-recovery-2026-09-13.md). Fixing
that crash does not prove WeCom's security notice is fixed.

The live desktop probe found one active local console session, not an RDP
session. Both apps run in that same session. All three installed display
adapters currently report OK. Windows remained at the same boot time and the
same WeCom/WeChat process IDs throughout the input-route change.

`SM_REMOTESESSION=0` and `SM_REMOTECONTROL=0` were observed in the interactive
session. These are Windows RDS/shadowing metrics, NOT evidence that WeCom will
accept automation or suppress a security notice. Microsoft's
[GetSystemMetrics documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getsystemmetrics)
describes their scope. Do not run this check in SSH session zero and use that
result to describe the interactive desktop.

## Small, Reversible Change

Originally, port 6143 used QEMU's native framebuffer and input. The September 7
split views added a guest TightVNC server, an indirect display, an SSH tunnel,
and two clipped VNC reflectors. Although still one Windows console session,
this changed the input/capture path.

WeCom's browser view now connects directly to the original QEMU VNC endpoint
on 5943. It no longer sends browser mouse/keyboard events through guest
TightVNC or a WeCom reflector. This restores the original console route while
keeping the familiar separate URL and shared automation input lock.

WeChat's secondary monitor still needs guest TightVNC and its single clipped
reflector on 5945. The guest server remains installed and active; this is NOT
a claim that Windows is free of remote-access software. The existing WeCom
automation helper also remains unchanged, including its normal Windows GUI
input methods. No device identities, app binaries, security policies, cookies,
credentials, or login profiles were modified.

QEMU's [VNC documentation](https://www.qemu.org/docs/master/system/qemu-manpage.html)
describes its own display/input route. A hypervisor console is still remote
operation; do not promise that it is invisible to application checks.

## Current Interfaces

- WeCom: <http://127.0.0.1:6144/wecom>, backed by QEMU 5943.
- WeChat: <http://127.0.0.1:6144/wechat>, backed by reflector 5945.
- Full primary console: <http://127.0.0.1:6143/>.
- Shared input lock: `agentic_tools/wecom_agent/.private/wecom_gui_bridge.lock`.
- One service: `labcanvas-tiny11-displays.service`.
- One tmux session: `labcanvas-tiny11-displays`, panes `views`, `tunnel`, `wechat`.

The extra `wecom` reflector and its port 5944 are obsolete, not milestones to
keep running. The launcher removes only the verified owned legacy process,
and preserves unexpected processes. The web service starts before checking
SSH/secondary VNC so WeCom's native console remains available during guest
transport recovery. No second VM, X desktop, or Android controller is started.

Both views retain scale-to-viewport, fixed 1280x800 Windows geometry, exclusive
Take control, automatic reconnect, and the Unicode clipboard helper. Viewing
does not acquire control. These are two app-oriented monitor views, not
separate Windows sessions or a privacy/security boundary between users.

## Reusable Diagnostics

`agentic_tools/wecom_agent/windows/Test-DesktopSession.ps1` records session IDs,
RDS flags, display bounds, driver status, cursor coordinates, memory, and process
IDs. It does not click, type, focus apps, restart them, collect chat text, or
read credentials. It refuses SSH session zero and an unexpected computer name.

Copy it with the existing `Tiny11Transport.scp_to_guest` to
`C:\LabCanvas\Displays\Test-DesktopSession.ps1`. Run it via a temporary
interactive scheduled task using the existing bridge task principal. Read
`desktop-session.json` over SSH and remove the temporary task afterward. The
probe is an on-demand diagnostic, not another permanent polling loop.

Useful host commands:

```bash
bash agentic_tools/wecom_agent/scripts/tiny11_displays.sh status
systemctl --user status labcanvas-tiny11-displays.service
tmux list-windows -t labcanvas-tiny11-displays
```

For deployment, acquire the shared input lock first, then restart ONLY this
app-view service. Windows and the applications do not need a reboot/restart.
Never restart WeCom or force a new login as an automatic response to a VNC
disconnect. Never change the phone state to diagnose Windows display problems.

## Verification and Next Evidence

Private before/after evidence is under
`output/tiny11-dual-monitor/20260913-console-route/`. Keep screenshots containing
QR codes and chat previews ignored. Source/behavior tests cover the direct
console route, startup recovery, guarded legacy-process cleanup, exclusive
control, upstream-failure lock release, and the read-only probe contract.

Live verification after deployment:

- Both views rendered nonblank at 1440x1000 and 390x844 browser sizes, with
  their complete 1280x800 canvases visible and no JavaScript errors.
- Pointer movement reached the primary and secondary monitors at the intended
  coordinates (within two pixels on the QEMU route). No app button or message
  composer was clicked; no keyboard message was sent.
- Reload/reconnect passed. A concurrent control request returned HTTP 409;
  the second view acquired control normally after the first released it.
- QEMU, WeCom, WeChat, and the phone mirror kept their existing process IDs.
  Port 5944 closed, leaving one secondary-display reflector instead of two.
- `npm test`: 2,016 tests passed, 13 optional skips. All 13 focused display
  tests passed in the display venv, including its optional HTTP tests.

Wait for actual rendered canvas pixels when taking verification screenshots:
an RFB connect event precedes the first decoded frame. A screenshot taken at
that event can be blank even though the display renders immediately afterward.

At the start of this change, both desktop clients were already at QR login.
Desktop rendering/input verification is not chat login or delivery verification.
A claim that the WeCom notice no longer occurs requires a later authenticated
session and inspection of any new notice with its timestamp. If it recurs,
compare the actual input route and foreground app at that time; do not infer
the cause merely from the window title, VM hostname, or use of two monitors.
