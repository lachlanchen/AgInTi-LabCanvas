# One Tiny11 VM, Two App Monitors

## Current Result

Implemented on 2026-09-07 without rebooting Windows, logging out WeCom, starting
another VM, or controlling Android. Windows WeChat is installed and waiting for
its own QR login. Its LabCanvas transport has NOT replaced Ubuntu WeChat.

- WeCom: <http://127.0.0.1:6144/wecom>
- Windows WeChat: <http://127.0.0.1:6144/wechat>
- Existing recovery console: <http://127.0.0.1:6143/>
- Original Ubuntu WeChat noVNC remains on port 6107, unchanged.

These are two monitors in ONE Windows login session, not two isolated Windows
sessions or ordinary Task View desktops. They share keyboard, mouse, clipboard,
and account permissions. They are not a security boundary between users.

## Geometry and Transport

| Role | Windows rectangle | Host VNC reflector |
| --- | --- | --- |
| WeCom, original primary | 1280x800 at 0,0 | 127.0.0.1:5944 |
| WeChat, additional monitor | 1280x800 at 1280,0 | 127.0.0.1:5945 |

The QEMU standard VGA display is preserved. One signed Virtual Display Driver
monitor extends it to the right. Guest TightVNC captures the combined desktop;
QEMU's original VNC console does not need to support the indirect display.

```text
Windows TightVNC, loopback 5900
  -> SSH 2290 tunnel, host loopback 15943
  -> x11vnc -reflect with per-monitor -clip
  -> one localhost web service 6144
  -> noVNC core, scaled to the browser viewport
```

There is no extra Xvfb desktop and no second VM. The existing noVNC JS library
and installed x11vnc perform RFB rendering, compression, clipping, and pointer
coordinate translation. Do not implement another screenshot polling viewer.

## Reusable Files

- `agentic_tools/wecom_agent/windows/Install-Tiny11Displays.ps1`: guarded signed
  driver installation and loopback-only TightVNC setup.
- `agentic_tools/wecom_agent/windows/Set-Tiny11AppScreens.ps1`: interactive
  startup placement and lightweight window replacement guard.
- `agentic_tools/wecom_agent/scripts/tiny11_displays.sh`: start, stop, status,
  and supervision of this exact stack.
- `agentic_tools/wecom_agent/scripts/tiny11_display_views.py`: local web/RFB
  transport, shared input lease, and native Unicode clipboard access.
- `agentic_tools/wecom_agent/web/displays/index.html`: two scaled noVNC views.
- `agentic_tools/wecom_agent/systemd/labcanvas-tiny11-displays.service`:
  storage-gated user-service startup/recovery.
- `agentic_tools/wecom_agent/requirements-displays.txt`: optional service
  dependency; the rest of LabCanvas does not depend on this web service.

Runtime venv: `~/.local/share/labcanvas/tiny11-displays-venv`.
Guest scripts and status: `C:\LabCanvas\Displays`.
Evidence and installers: ignored `output/tiny11-dual-monitor/`.
Never commit installer binaries, screenshots of chats/QRs, profiles, or tokens.

## Installation Evidence and Sources

Used the [signed Virtual Display Driver release 25.7.23](https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.7.23),
specifically the x86 driver-only archive containing the x64 Windows driver.
Installed driver reports `11.30.4.434`. The catalog's Authenticode signature
validated as SignPath Foundation; NefCon 1.14.0 validated as Nefarius Software
Solutions. Only the verified catalog signer was added to TrustedPublisher.
No test signing or Secure Boot relaxation was used.

The [upstream installation instructions](https://virtualdrivers-virtual-display-driver.mintlify.app/installation)
use NefCon to create a root device. On this VM, explicitly running
`pnputil /add-driver ...\MttVDD.inf /install` was also needed to bind the
package to that node. A root device alone was NOT proof of a working monitor.
The driver XML has one additional 1280x800 monitor at 30 Hz, logging disabled.

Used [TightVNC 2.8.88](https://www.tightvnc.com/download.php), server component
only. The signed MSI verified as GlavSoft. Installation explicitly disables
firewall exceptions, web/Java serving, and lock/logoff on disconnect. The
listener was verified at **127.0.0.1:5900**, not on the guest LAN.
Authentication is provided by the existing SSH tunnel and local machine access;
these views are not a public or multi-user service.

Used Tencent's official Windows WeChat 4.1.13 installer; Authenticode validated
as Tencent Technology (Shenzhen) Company Limited. Installers run over SSH must
use `Start-Process ... -Wait -PassThru`: exiting the SSH process immediately
after a background launch can leave installation incomplete. Check the actual
installed executable and interactive process, not only an installer launch PID.

## Input and Clipboard

Views initially open read-only in noVNC. **Take control** obtains the same
`agentic_tools/wecom_agent/.private/wecom_gui_bridge.lock` used by the WeCom
automation. Another control view receives a busy response. Viewing without
control does not pause automation. Release, disconnect, changing away from
the tab, or 90 seconds without input returns control to automation; the server
also caps an individual control connection at ten minutes.

The UI's read-only flag is an interaction guard, not a permission sandbox.
Direct localhost RFB ports and the recovery console remain operator tools;
do not drive them concurrently with the automated sender. Agents for any future
Windows WeChat transport MUST use the same shared GUI lock, not a second lock.

Classic VNC clipboard text lost Chinese/Japanese characters in the live test.
The Clipboard dialog therefore calls the existing authenticated Windows helper
using UTF-8 JSON and the native Unicode clipboard, bound to the active input
lease. It does NOT type or send a message. After setting clipboard text, paste
it into the intended application normally. Empty text clears the clipboard.

The web service is localhost-only, rejects foreign Host/Origin values, exposes
no private config directory, and does not log HTTP access or clipboard content.

## App Placement and Context Privacy

`LabCanvas-App-Screens` is an interactive Windows scheduled task at login,
delayed 20 seconds. It launches WeChat only if absent, centers a fixed-size QR
window on monitor two, and fits a new main window there after login. It checks
window replacements every three seconds without stealing foreground focus.
Status is rewritten only on initial observation or window placement.

WeCom's original window and layout are not resized or moved. The native
`WeComBridge.ps1` screenshot endpoint now captures only the primary monitor,
rejecting a WeCom window moved outside it. This preserves existing OCR/click
coordinates and prevents the adjacent WeChat screen from entering a WeCom
task's agent context. Do not restore VirtualScreen capture for research tasks.

## Daily Operation and Recovery

```bash
bash agentic_tools/wecom_agent/scripts/tiny11_displays.sh status
bash agentic_tools/wecom_agent/scripts/tiny11_displays.sh start
systemctl --user status labcanvas-tiny11-displays.service
```

Owned tmux session: `labcanvas-tiny11-displays`, with `tunnel`, `wecom`,
`wechat`, and `views` windows. Startup reuses them instead of duplicating
processes. The user service recovers missing panes every 30 seconds. It waits
for the existing VM's SSH/VNC readiness; it does not start or reboot a VM.
It uses the workstation storage guard before touching ProjectsLFS after boot.

For an intentional full stop, stop the user service; otherwise its supervisor
will recover the stack:

```bash
systemctl --user stop labcanvas-tiny11-displays.service
```

This stops only the new browser views, reflectors, and their SSH tunnel. It
does not stop QEMU, WeCom, Ubuntu WeChat, or the original 6143 recovery console.
The Windows signed display driver persists across restarts. A driver rollback
must target only the `Root\MttVDD` device; never uninstall the original QEMU
adapter or disable all monitors.

## Verification and Remaining Boundary

- Two native monitors verified at the exact coordinates above.
- Both browser canvases are 1280x800 and render the correct separate monitor.
- A click in the WeChat view opened its proxy settings; returned to QR without
  changing any network settings. WeCom remained in LabAgent throughout.
- Exclusive input test rejected a concurrent control request with HTTP 409.
- Native clipboard round-trip passed for Chinese and Japanese in both
  directions; previous clipboard text was restored.
- WeCom task screenshot verified at 1280x800, excluding WeChat.
- WeCom bridge stayed `chat_ready=true`, `closed_loop_state=ready`, session 1.
- Eight display-view tests and nine existing/extended Tiny11 transport tests
  passed. Screenshots remain private under the runtime output folder.
- Full repository unittest discovery passed: 2,004 tests, 12 skips. The five
  optional HTTP tests skipped by the base environment passed separately in
  the display-service venv.

Windows WeChat login and its future message transport cutover still require
verification after the QR is scanned. Installing it did not authorize logging
out Ubuntu WeChat or migrating history. Reboot persistence is configured;
the live VM was not rebooted to test it because WeCom was already working.
