# Tiny11 WeCom Transport Handoff

## Purpose

LabCanvas uses the logged-in native WeCom client in the dedicated Tiny11 KVM as
the production fallback for allowlisted external groups that Tencent's official
server transports cannot read. Personal WeChat and WeCom remain separate.

The current manual recovery console is:

```text
http://127.0.0.1:6143/
```

The retired Wine console on port `6192` must remain stopped while Tiny11 is the
selected backend. The Android MIX 2S mirror may remain available for the owner,
but its WeCom relay configuration is disabled and no Android UI polling is part
of this transport.

### Large Login View

On a wide 2560x1440 desktop, native fixed-size login dialogs become too small
when the full desktop is scaled into a browser. Use the same console page:

- Large live WeCom QR: <http://127.0.0.1:6143/?view=wecom>
- Large WeChat login: <http://127.0.0.1:6143/?view=wechat>
- Normal shared desktop: <http://127.0.0.1:6143/>

The toolbar switches views without another VNC connection or guest display
change. Enlarged login views are read-only, repaint only from the current local
noVNC canvas, and hide stale pixels during disconnect. They do not re-encode,
cache, publish, or transfer the QR code. Return to Desktop to click native
Refresh/Log In controls or after scanning. Crops follow the centered Shared
layout; after manually moving a login window, restore that layout before using
the enlarged view. Do not inflate Windows DPI just to enlarge a QR, because it
also increases minimum app widths and can break the shared layout.

Canonical files are `agentic_tools/wecom_agent/web/tiny11-console.html` and
`tiny11-console.mjs`. Deploy with `install -m 0644` into the existing VM's
`tools/novnc-web/` as `index.html` and `tiny11-console.mjs`, retaining a private
backup of the old index. Reload the existing Firefox tab; no VM, app, or
websockify restart is needed. The VM launcher serves this persistent directory.

### Readable Text Without Restart

Use <http://127.0.0.1:6143/?zoom=100> for native-size text. The toolbar's
Fit/100% selector changes only noVNC local scaling. Fit restores the complete
side-by-side desktop; 100% uses native noVNC panning/scrolling when the desktop
is larger than the viewport. Windows remains 2560x1440 at 100% DPI, so agent
capture and input geometry do not change. QR views temporarily restore the
complete framebuffer before cropping, then restore the selected desktop zoom.

WeCom Settings -> General Setting -> Text Size offers Small, Middle, Large,
and Largest. In the inspected client, switching from Small to Large requested
an application restart. That restart was cancelled to preserve the freshly
verified login. Viewer zoom is the reversible no-restart alternative. It is
not a fix for Tencent's environment/security warning.

After the owner's September 13 phone confirmation, the native notice showed
verification completed for LABCANVAS-PC. The relay's own security quarantine
cleared through passive stabilization and LabAgent became ready again. See
[the warning investigation](tiny11-console-input-and-remote-warning-2026-09-13.md)
for the evidence and limitations. No permanent Android polling or blanket
approval loop was enabled.

## Data Path

Repeated PDFs after reconnect are not normal catch-up. See the
[file retry loop repair](wecom-file-retry-loop-repair-2026-09-13.md) for durable
pre-Send attempts, non-retryable uncertainty, and native history crop checks.

If Windows reports that it cannot open a browser, check the actual HTTP/HTTPS
handler executable. Tiny11's removed Edge left broken `MSEdgeHTM` associations;
see [the verified default-browser repair](tiny11-default-browser-repair-2026-09-13.md).
Restoring Edge does not require restarting the VM or the chat clients.

```text
native WeCom in Tiny11
  <-> interactive localhost-only PowerShell helper
  <-> SSH localhost forward on Ubuntu
  <-> wecom_tiny11_gui_bridge.py
  <-> durable WeCom cursor/delivery SQLite state
  <-> LabCanvas ingress, worker queue, and artifact sender
```

Artifacts take a separate verified path:

```text
repository artifact
  -> task-scoped Ubuntu staging
  -> SCP/SFTP to C:\LabCanvas\WeComBridge\inbox\<delivery-key>
  -> remote byte-size and SHA-256 verification
  -> Windows file-drop clipboard
  -> exact LabAgent composer
  -> newly visible history card
  -> durable delivery ledger
  -> temporary staging cleanup
```

## Runtime Ownership

- VM launcher: `/home/lachlan/UbuntuSDA/VirtualMachines/Windows-Tiny11/tools/windows-tiny11-kvm`
- VM SSH forward: `127.0.0.1:2290`
- VM VNC: `127.0.0.1:5943`
- VM noVNC: `127.0.0.1:6143`
- LabCanvas GUI API: `127.0.0.1:19580`
- Windows helper through SSH: `127.0.0.1:19582`
- tmux transport window: `labcanvas-wecom:tiny11-transport`
- tmux relay window: `labcanvas-wecom:external-gui`
- Windows task: `LabCanvas-WeCom-Bridge`

Secrets, screenshots, chat text, cursors, VM inbox files, and bearer tokens stay
in ignored private/runtime storage. Do not add them to git or documentation.

## Normal Commands

```bash
PYTHONPATH=src python -m agenticapp wecom gui status --json
PYTHONPATH=src python -m agenticapp wecom gui chats --json
PYTHONPATH=src python -m agenticapp wecom gui messages \
  --chat LabAgent --after 0 --limit 100 --json
PYTHONPATH=src python -m agenticapp wecom gui send \
  --chat LabAgent --message 'Result ready.' \
  --file output/report.pdf --task-id exact-task-id --live --json
agentic_tools/wecom_agent/scripts/wecom_autostart.sh status
```

Use the API or CLI instead of ad hoc mouse commands. Stable task IDs make exact
payload retries idempotent. Combined text and files remain under one GUI lock,
and the exact chat title is checked before each operation.

## Recovery

The enabled user service runs `wecom_autostart.sh supervise`. It recreates only
missing project-owned tmux windows. The Tiny11 transport starts or reuses the
VM, installs the helper in the current interactive Windows session, and restores
the localhost SSH tunnel. It does not switch accounts, generate a QR code, or
replay an old backlog.

```bash
agentic_tools/wecom_agent/scripts/wecom_autostart.sh once
agentic_tools/wecom_agent/scripts/wecom_tmux.sh gui-restart
python3 agentic_tools/wechat_gui_agent/scripts/wechat_transport_stall_guard.py \
  --json --strict
```

If `chat_ready` is false:

1. Check that Tiny11 SSH, VNC, noVNC, helper, and GUI API ports are listening.
2. Open the noVNC console only when visual inspection or human login is needed.
3. Keep the native WeCom client open; fullscreen, restored, and resized layouts
   are supported.
4. Confirm `LabAgent` is visible and the relay can OCR its exact title.
5. Restart only `tiny11-transport` and `external-gui`; do not start Wine or the
   Android relay.

A send that fails before the composer is verified may be retried with the same
task ID. A send that becomes uncertain after the Send action must first be
reconciled from before/after history evidence; never blindly resend it.

### Login Cooldown Recovery

On 2026-09-13, successful login did not release the relay because rejected
sends were being mistaken for new authentication challenges. The stored blocker
accumulated repeated `(cooldown Ns)` suffixes, and retries restarted the cooldown
or reset its stabilization timer. This was a bridge bug, not evidence that the
logged-in client needed another login.

`quarantine_from_exception` now distinguishes an existing-pause error from a
fresh GUI-observed challenge. Both polling and sending use that same handler.
Retrying a paused send preserves the original deadline and recovery timer.
Fresh visible QR/security challenges still activate quarantine. The passive
screen check, cooldown duration, stabilization interval, exact-chat checks,
delivery ledger, and message behavior are unchanged.

Deploy by restarting only the Python GUI relay with `wecom gui restart`.
Do not restart the Windows apps, reset the private database, force-clear the
security state, enable Android polling, or mass-replay deferred work. Observe
the original deadline expiring, the clear-screen stabilization completing, and
the exact target chat becoming ready. A healthy helper alone is not proof of
inbound reception or artifact delivery.

Regression coverage in `tests/test_wecom_agent_bridge.py` checks repeated
exception/result retries across expiry, legacy nested cooldown errors, and
fresh observed challenges. Run:

```bash
python -m unittest discover -s tests -p test_wecom_agent_bridge.py
python -m unittest discover -s tests -p test_wecom_tiny11_transport.py
npm test
```

Personal Windows WeChat login remains separate from this WeCom recovery.
The existing personal-chat monitors still use the Ubuntu client/database; do
not report those monitors healthy merely because Windows WeChat is logged in.
Do not switch accounts or replace that transport as an incidental auth fix.

Live verification: the old stored blocker expired and cleared normally after
the relay reload. Both app views rendered at 1280x800 in passive view-only mode.
WeCom subsequently displayed a genuine full-page device-environment verification
challenge, so live message/artifact delivery was not verified. Do not present
the cooldown fix as a fix for Tencent's security warning. The local Tiny11
configuration now disables the old `allow_verified_file_send_during_device_warning`
exception: there is no usable chat composer on that full-page challenge.
Neither Windows app was explicitly restarted and no Android input was sent.

### Shared Desktop, 2026-09-13

The owner requested WeCom on the left and personal WeChat on the right of the
same original console at `http://127.0.0.1:6143/`. Do not replace that endpoint
with an RDP session, secretly redirect it to a different desktop, or enable
Android polling as a layout workaround.

The initial QEMU standard VGA display exposed **only 1280x800** through
Microsoft Basic Display Adapter. `Get-DesktopModes.ps1` reads the actual
interactive-session modes with `EnumDisplaySettings`; changing browser zoom
does not create more guest desktop pixels. A live placement test established
that this WeCom build clamps its main window to **986 pixels minimum width**.
Forcing a 636-pixel half produced overlap, not a usable shared layout. The test
was undone, preserving the existing two-monitor app arrangement and logins.

The reusable `Set-Tiny11AppScreens.ps1 -Layout Shared -Watch` mode requires at least 2000x800,
places WeCom left and WeChat right with an eight-pixel gap, restores a new
main window once, and preserves later manual positioning. `-Layout Dual`
remains an explicit compatibility mode; the installed task now selects Shared.
The existing `LabCanvas-App-Screens` scheduled task owns the single watcher.
Do not create another watcher beside it. A wider boot display may require a
Windows restart; obtain confirmation before risking the current app logins.

The owner authorized a VM-only reboot. The completed shared-console setup is:

1. Back up the VM's `OVMF_VARS.fd` privately, preserving its original file mode.
2. Stop the owned split-view service, guest TightVNC service, and the exact
   auxiliary `Root\MttVDD` device. Keep the signed driver installed for rollback.
   Do not disable unrelated display adapters or remote-access services.
3. Reboot Windows normally. Escape enters OVMF; Device Manager > OVMF Platform
   Configuration > Change Preferred Resolution selects **2560x1440**. Commit
   Changes and Exit, then Reset from the firmware front page. No QEMU device,
   Windows display-driver package, app binary, or login profile was replaced.
4. IMPORTANT: the larger QEMU framebuffer alone is not sufficient. Windows
   retained a logical **1280x800** desktop after that boot. In Windows Display
   Settings select **2560x1440** and Keep changes. Check both the console canvas
   and Windows `Screen.Bounds`; browser scaling cannot fix this mismatch.
5. Update the existing `LabCanvas-App-Screens` task to `-Layout Shared
   -LaunchWeChat -Watch`, with its existing interactive user and triggers. The
   old task referenced a previous computer name and failed SID resolution.
   Repair its principal and logon-trigger `UserId` using the same local account's
   SID, not a stale `COMPUTER\user` string. Do not change the account or password.
6. Keep `labcanvas-tiny11-displays.service` disabled. Ports 6144, 15943, 5944,
   and 5945 are retired in this mode. The original QEMU VNC 5943/noVNC 6143
   remains the only VM view. Guest `tvnserver` is stopped with Manual startup.
7. Resume `labcanvas-wecom-autostart.service`. Authentication blockers and
   delivery records remain intact; never mass-replay old work on reboot.

The helper installer now also resolves the current account SID when registering
its interactive principal and logon trigger, instead of copying an old qualified
account name. Windows may normalize IDs back to names in exported task XML;
after any future hostname change, re-register the owned tasks and verify their
triggers rather than assuming the old XML is portable. `Focus-WeCom` does nothing when WeCom or an
owned dialog already has focus. On a real app switch it checks the result and
refuses to type if Windows denied focus. Read-only screenshot polling never
activates or restores the app. This fixes redundant focus events and avoids
pulling focus away from a native file dialog; it is not a security-check bypass.

Live outcome: Windows reports one 2560x1440 primary monitor and both native
apps are centered in their separate halves. The shared watcher is running and
will fit the main windows after login. WeCom shows QR login and WeChat shows
its existing-account Log In button; **authenticated messaging is not verified**.
The session probe found one active console and zero RDS/shadowing flags, which
does not establish that WeCom's private security checks will accept the client.
Ubuntu WeChat and mobile WeCom remain available as the owner's fallback;
their code/profiles were preserved and Android polling was not enabled.

Two real helper problems were found during this inspection:

- WeCom exposes a larger `PerryShadowWnd` beside `WeWorkWindow`. Selecting the
  largest window could manipulate or capture its shadow. Window selection and
  placement now exclude the shadow and separate title-bar windows.
- Normal account-login notifications contain past-tense text such as
  `扫码登录了以下设备`. That is not a QR login prompt. Chinese QR detection now
  checks instruction line endings; actual QR and device-verification screens
  still pause automation. Existing quarantine expires through the normal
  passive recovery path, never by deleting its state.

The helper captures only the WeCom window rectangle, paints everything else
black, and rejects overlap with a visible WeChat window. It keeps full primary
image dimensions so existing OCR and click coordinates stay valid. The owner's
noVNC console remains unmasked. These changes prepare a shared desktop without
feeding one application's conversations to the other application's worker.

Both native apps were visibly signed in during the layout inspection. This
does **not** establish that personal Windows WeChat has a working LabCanvas
receiver: the personal-chat monitors still use the Ubuntu transport. The
shared layout and that transport migration are separate acceptance checks.

That sign-in observation preceded the later warning and authorized reboot;
use the latest live outcome above, not the earlier observation, for readiness.

Focused Windows regression test (no real GUI input): stage
`tests/windows/test_wecom_focus.ps1` in the private guest inbox, then run it with
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File <test-path>`. It extracts
the deployed focus function and tests already-focused, owned-dialog, other-app,
and focus-denied cases against a fake native API, without starting the listener.

Reference for the read-only display probe:
[Microsoft EnumDisplaySettings](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumdisplaysettingsw)
and [DEVMODEW](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-devmodew).

## Acceptance Evidence

The production route was tested with:

- exact `LabAgent` title verification at fullscreen geometry;
- inbound polling through the existing durable cursor;
- Unicode message compose/readback/send verification;
- SCP/SFTP staging with remote size and SHA-256 equality;
- one native attachment send and visible history verification;
- idempotent delivery-status reconciliation;
- removal and recreation of both transport tmux windows through autostart;
- strict shared transport and schedule health checks.

The authoritative detailed contract remains
`agentic_tools/wecom_agent/docs/GUI_RELAY_INTERFACE.md`.
