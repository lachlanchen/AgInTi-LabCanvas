# LabCanvas Windows Desktop Recovery

## Outcome

The existing Windows installation was repaired in place and renamed from
`TINY11-KVM` to `LABCANVAS-PC`. There was no reinstall, new VM, account change,
password change, or hardware-identity spoofing. The existing disk, user profile,
application data, SSH keys, encrypted automatic-login secret, and display
topology were preserved. One controlled Windows restart applied the rename;
automatic Windows login and both app-view services recovered.

Current operator endpoints:

- WeCom: <http://127.0.0.1:6144/wecom>
- Windows WeChat: <http://127.0.0.1:6144/wechat>
- Recovery console: <http://127.0.0.1:6143/>
- SSH: `ssh -p 2290 lachlan@127.0.0.1`

These browser views capture the existing Windows console through TightVNC.
They do not open an RDP login or create another Windows user session. Input
ownership is shared with the automation through the existing GUI lock.
NoVNC remains a localhost operator interface, not a public access service.

Windows recovery is not proof of a WeCom account login. Both Windows clients
showed QR login screens after recovery. Do not mark chat transport ready until
the native client is authenticated and the exact group can be verified.
Ubuntu WeChat and passive Android mirroring were not migrated or controlled.

## Failure Evidence

The `/wecom` page itself returned HTTP 200 and rendered a valid 1280x800 canvas.
The displayed error came from Windows: Desktop Window Manager had crashed and
logged off the interactive session. Application events 1000/1001 recorded
repeated `dwm.exe` faults around 12:24-12:39 HKT on September 12.

System event 2004 recorded memory exhaustion before the final crash. At
12:38:30, two `powershell.exe` processes accounted for 14,728,630,272 and
5,401,886,720 committed bytes. The guest has 8 GiB physical RAM. This evidence
does not establish that WeCom detected or rejected remote operation.

Both long-lived LabCanvas Windows helpers repeatedly enumerated the desktop
through UI Automation. A controlled interactive test reproduced continuing
memory growth even with explicit garbage collection. Native enumeration
removed this growth in the same test:

| Test | Calls | Private-memory change |
| --- | ---: | ---: |
| Previous UI Automation enumeration | 2,000 | +34,164,736 bytes |
| Native Win32 value snapshots | 10,000 | -241,664 bytes |
| Deployed native WeCom helper, HTTP health requests | 500 | -8,192 bytes |

The deployed helper used about 72 MiB before and after the HTTP test; its
handle count did not grow. The placement guard also remained around 70 MiB.
These are bounded regression measurements, not a claim of indefinite leak-free
operation. Historical process IDs alone cannot establish ownership after PID
reuse; keep the event evidence and controlled reproduction separate.

## Reusable Fixes

`agentic_tools/wecom_agent/windows/NativeWindows.ps1` provides a shared Win32
`EnumWindows` snapshot. It filters process IDs before reading titles and returns
plain values rather than retaining UI Automation provider objects. Hidden or
minimized windows are excluded. Enumeration does not move windows or take focus.

`WeComBridge.ps1` uses that snapshot for native window discovery. Its existing
token authentication, same-monitor screenshot guard, Unicode/file clipboard,
and size-preserving focus behavior remain unchanged. Its installer now stages
the shared dependency alongside the bridge.

`Set-Tiny11AppScreens.ps1` uses the same snapshot and bounds its remembered
window handles to live windows. Placement still happens only when a new WeChat
window appears, not on every poll. The WeCom window is not moved. Both display
scripts accept `-ExpectedComputer`; the default is now `LABCANVAS-PC` and an
unexpected name fails closed. Legacy deployments must explicitly pass their
actual computer name until migrated.

`tiny11_display_views.py` returns HTTP 503 when its upstream VNC endpoint is
temporarily unavailable and releases the input lease. It no longer tries to
close an unprepared WebSocket, which previously generated an additional 500
error during reconnection. The browser retries and uses proportional viewport
scaling without changing the native desktop resolution.

`tiny11_displays.sh` checks live panes, not just retained tmux window names.
It can respawn an exited project-owned pane when `remain-on-exit` is enabled.
It does not kill a live sibling pane, restart Windows, or open another VM.

## Deployment and Rollback

1. Back up the two guest helper scripts and their scheduled-task XML before
   changing them. Keep those backups private.
2. Stage `NativeWindows.ps1` in both `C:\LabCanvas\WeComBridge` and
   `C:\LabCanvas\Displays` before starting either updated helper.
3. Deploy the WeCom helper through `Tiny11Transport.install()`. It restarts
   only its own scheduled helper task, not the WeCom application.
4. Stage and restart the placement guard with the correct `-ExpectedComputer`.
5. Restart `labcanvas-tiny11-displays.service` for web/supervisor code changes.
   This reconnects viewers but does not log off Windows or either application.
6. Verify native process memory, screenshots, canvas dimensions, HTTP/WebSocket
   behavior, and the actual account state. Do not use HTTP 200 as proof of login.

The September 13 guest backups are under
`C:\LabCanvas\Recovery\20260913-memory-repair` and a timestamped rename folder.
If rolling back a helper, restore only that helper and its task. Do not restore
the old hostname guard without adapting it to the current computer name.
Do not reintroduce the leaking enumeration as a long-term workaround.

## Safe Computer Rename

`windows/Rename-LabCanvasComputer.ps1` checks the expected current computer and
refuses domain-joined machines. Without `-Apply`, it reports the plan only.
With `-Apply`, it backs up LabCanvas task XML, translates local task user and
logon-trigger identities to SIDs, changes the computer name, and updates the
local automatic-login domain without reading or changing the LSA password.
It never reboots implicitly.

Example for an operator inside the verified Windows machine:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LabCanvas\Displays\Rename-LabCanvasComputer.ps1 -ExpectedComputer TINY11-KVM
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LabCanvas\Displays\Rename-LabCanvasComputer.ps1 -ExpectedComputer TINY11-KVM -Apply
```

Before restarting, set the placement task's expected name to the new name.
After restarting, verify `hostname`, SSH access, the automatic-login status,
the scheduled helpers, and the two exact 1280x800 monitor rectangles. Internal
QEMU/runtime paths remain `Windows-Tiny11`; those are storage identifiers, not
the Windows computer name. Do not rename or copy a running VM disk.

## Verification Tools

`windows/Test-WindowEnumeration.ps1` runs a read-only interactive stress test
with a configurable iteration count. Invoke it through a temporary interactive
scheduled task, not an SSH session's noninteractive desktop. It writes only
counts, memory measurements, and handle counts, never window titles or chats.
It stops if private memory exceeds 512 MiB and returns failure when bounds or
target-window discovery fail. Remove the temporary task after testing.

Private evidence: `output/tiny11-dual-monitor/20260913-repair/`, including
before/after screenshots, baseline/native memory measurements, and the live
helper HTTP memory test. Never publish QR screenshots, logs, profiles, or tokens.

Regression tests cover same-origin access, exclusive input leases, upstream
refusal/timeout cleanup, dead-pane recovery, shared native dependency deployment,
bounded handle tracking, and unchanged screenshot/geometry isolation. Final
`npm test` passed: 2,009 tests, 13 optional-dependency skips. All 10 display tests
and 11 Tiny11 transport tests also passed in environments with their optional
dependencies available. An earlier full Python run passed 2,008 tests without
skips before the final additional supervisor test was added.

## Operator Boundaries

- No Android polling, touch injection, or logout for this repair.
- No killing DWM, Explorer, or another project's service to hide symptoms.
- No RDP session switching to operate the messaging apps.
- No app patching, virtual-hardware spoofing, or promises to suppress WeCom's
  own authentication checks. A friendly hostname is not a security bypass.
- No reinstallation or copying another disk's Windows image when the existing
  installation is reachable and the failing component can be repaired.
- Keep only the existing VM and its single app-view stack running for review.

See also [the dual-monitor runbook](tiny11-two-monitor-wechat-wecom-2026-09-07.md)
and [automatic Windows login](tiny11-wecom-automatic-signin-2026-09-07.md).
