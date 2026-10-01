# WeChat / WeCom Security and Stability Root-Cause Audit

## Conclusion

The incidents are not one failure. Do not attribute every frozen window,
security notice, login page, and paused queue to an abnormal Windows install.

| Finding | Confidence | Evidence / boundary |
| --- | --- | --- |
| The old GUI helpers exhausted Windows memory and destabilized the desktop. | Confirmed | System event 2004 identifies two PowerShell processes consuming about 20 GB; DWM crash events overlap. The earlier UIAutomation/native snapshot reproduction isolated the leak. |
| WeCom detected remote operation and imposed a phone-confirmation deadline. | Confirmed notice and policy | The saved native notice names this computer, gives 2026-09-13 14:36 HKT, and says missing confirmation within five minutes causes logout. This particular notice was subsequently verified. |
| Our synthetic GUI input is a plausible detector input. | Hypothesis, not the exact proven trigger | The native helper uses `mouse_event` and `SendKeys`. Windows exposes injected-input flags. Tencent's actual detector decision was not recovered. |
| WeChat's embedded browser component crashed separately. | Confirmed crash, unresolved triggering operation | Four Application 1000 records at 2026-09-27 08:16:11 identify `WeChatAppEx.exe` 2.5.6.25558; WER reports classify them as APPCRASH. This is not proof of a security logout. |
| A content worker previously restarted the client outside its task boundary. | Previously recorded operational defect | The September 27 delivery investigation records this intervention. It caused account-entry recovery work; the content/lifecycle prompt boundary was then tightened. It does not explain every later vendor notice. |
| Paused WeCom status advertised an old security state as its current state. | Reproduced and fixed in this audit | The private ledger retained a September 18 blocker while the native helper was currently input-ready. `closed_loop_state` was `security_verification_required` despite `enabled=false`. |

The most defensible explanation for the WeCom remote-operation notice is the
legitimate remote-control/automation path being recognized as remote operation,
not a demonstrated damaged installation. The precise detector input remains
unknown. Personal WeChat's separate account-security re-login message must not
be assigned the same cause without its own evidence.

## Evidence Timeline

All times below are Asia/Hong_Kong.

### September 12: resource exhaustion

The new read-only query recovered System event 2004 at 12:38:30:

- `powershell.exe`: 14,728,630,272 committed bytes.
- A second `powershell.exe`: 5,401,886,720 committed bytes.
- `Weixin.exe`: 1,135,165,440 committed bytes.

Application 1000 records show DWM faults in the same period, including
12:24 and 12:38-12:39. The earlier controlled reproduction compared retained
UIAutomation provider objects with native Win32 snapshots. The native path
replaced the leaking implementation; do not reintroduce UIAutomation polling.
See [the memory recovery record](labcanvas-windows-memory-recovery-2026-09-13.md).

The current audit found no resource-exhaustion event newer than September 12 in
the queried 30-day interval. The two interactive helper samples were about
83 MB and 151 MB of private memory, rather than gigabytes. A sample is not a
guarantee against all future leaks.

### September 13: native remote-operation notice

The private screenshot `output/android_device_agent/wecom-security-notice-open.png`
shows a 14:34 Windows WeCom login, a remote-operation event at 14:36, and a
completed verification. Its warning explicitly states that an unconfirmed
event causes device logout after five minutes.

This proves the warning category and logout mechanism. It does **not** prove
that confirmation was missed in this captured incident; the client was later
observed logged in. Other reported logouts require their own notice/timeline.
See [the console-route record](tiny11-console-input-and-remote-warning-2026-09-13.md).

Stopping TightVNC and the old indirect-display/split-view route did not make
remote access cease: QEMU console control and the native GUI helper remain
remote/automated input. No RDP session is not the same as no remote operation.
Renaming the computer, increasing QR/font size, or making the desktop look
ordinary is not a verified security remedy.

### September 18: durable state retained during the operator pause

The WeCom SQLite runtime retained `device_environment_abnormal`, an expired
quarantine deadline, and `last_ready_at=2026-09-18T06:11:54`. The ledger had no
original observation timestamp. Do not invent one from the deadline.

At the October 1 audit, configuration still deliberately disabled WeCom
automation. The native helper reported `client_state=ready`, `input_ready=true`,
and no system input blocker. That does not establish that Tencent can never
issue another notice, but it contradicts presenting the old cached marker as
a freshly observed active alert.

### September 27: separate embedded-browser failure

Four distinct crash events identify the WeChat browser runtime with these
exceptions: `c0000005`, `c00000fd`, and two `e0000008` records. WER queue/archive
rows duplicate the same reports; they are not eight separate crashes.

Do not infer corruption of Windows from a faulting system DLL alone, nor infer
account risk from an APPCRASH. The repository also records a runaway renderer
episode and a later unresponsive main window. Exact linkage between every
renderer fault, operator cleanup, and main-window hang was not established.
See [the native Channels record](windows-wechat-channels-originals-and-send-reconciliation.md)
and [the delivery/hang investigation](windows-wechat-docked-pane-delivery.md).

## What Was Not Proven

- The clock was already close to host time before the Windows Time repair.
  Enabling ongoing synchronization was maintenance, not an established fix for
  Tencent's September security notices.
- Activated Windows, valid Tencent executable signatures, enabled UAC, and
  enabled Defender do not make GUI automation invisible or rule out all malware.
- No Defender 1116/1117 detection events appeared in the queried interval. This
  is scoped log evidence, not a full malware-clearance certificate.
- Native WeCom main logs use an encoded/encrypted container. Personal WeChat
  Xlogs start with `0x07`; Tencent's public decoder identifies that as a format
  requiring the cryptographic decoder, not the no-crypt path. No vendor private
  key was available, and no runtime key extraction or security patch was attempted.
- The sampled CEF/HTTPDNS plaintext logs did not yield a security/logout reason.
  They cannot establish the absence of a vendor-side risk decision.
- No safe A/B experiment was performed against the live account. Triggering
  another security warning just to identify a detector would risk its login.

Microsoft documents the input observability in
[MSLLHOOKSTRUCT](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-msllhookstruct).
Tencent's log-format boundary is visible in its
[Mars decoder](https://github.com/Tencent/mars/blob/master/mars/xlog/crypt/decode_mars_nocrypt_log_file.py).
Neither source establishes which signal WeCom actually evaluated here.

## Persistent Changes Made

1. A disabled WeCom relay now reports `closed_loop_state=paused`, never claims
   chat delivery readiness, and preserves its old blocker for later guarded
   recovery. No quarantine was cleared and no automatic send was enabled.
2. Status marks a retained blocker as `cached_observation`. New observations
   record `auth_blocker_observed_at`; a rejected retry carrying a cooldown does
   not refresh that timestamp. Legacy timestamps remain unknown.
3. Native helper state is exposed separately from the durable relay state.
4. The existing environment audit has an opt-in bounded incident collector:

```bash
python agentic_tools/wecom_agent/scripts/wecom_tiny11_transport.py \
  environment --incident-days 30 --json
```

It queries up to 200 events per log, reports unavailable logs and truncation
explicitly, reads structured crash/resource fields, samples helper memory and
native browser counts, and lists project-owned scheduled task state. It never
serializes raw chat logs, event messages, process command lines or credentials.
It stages a checksum-verified script via the existing SSH/SFTP transport; it
does not install a helper, focus a window, click, restart clients, or reboot.
Zero incident days remains the inexpensive ordinary environment check.

The private audit is
`agentic_tools/wecom_agent/.private/environment-health/2026-10-01-root-cause-audit.json`,
mode `0600`. Its client identity check remained unchanged across collection.
No Android actions or group test messages were performed.

## Operational Decision

Keep the current login/profile, single native console, cached-key database
intake, serialized exact-chat sender, security quarantine, and explicit WeCom
pause. Stop unnecessary GUI inputs; do not turn a content retrieval failure
into a restart/login attempt. Never auto-approve an account-security prompt.

For a recurrence, first preserve the exact native notice category and event
time, then run this audit and compare the last authorized GUI/task operation.
Classify vendor verification, client hang, browser crash, OS dialog, transport
failure, and historical cache independently. A support-approved API route can
remove desktop input for supported groups, but external-group eligibility must
be verified; it is not a drop-in promise for LabAgent.

Do not promise that a normal-looking VM or a helper optimization eliminates
Tencent's remote-operation policy. The exact vendor trigger remains a support
question if it cannot be established from preserved native evidence.
