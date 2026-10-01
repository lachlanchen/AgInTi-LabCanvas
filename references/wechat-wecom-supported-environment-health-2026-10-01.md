# WeChat / WeCom supported environment health

## Scope and confirmed findings

This is an environment and transport-stability repair, not a bypass of Tencent's
account/security checks. No evidence currently establishes the exact trigger of
the earlier remote-operation warning. A healthy Windows installation does not
guarantee that a remotely operated client will never show such a warning.

Live checks on 2026-10-01, approximately 08:00-08:14 Asia/Hong_Kong:

- The existing Windows 11 Pro guest is `LABCANVAS-PC`, build 26200. Windows
  reports `LicenseStatus=1` (licensed). No installation or identity was replaced.
- WeChat 4.1.15.9 and WeCom 5.0.11.6029 have valid Tencent Authenticode signatures
  on their running executable paths. Each has one root instance in the same
  active console session, session 1. Child processes are not duplicate clients.
- Defender antivirus and real-time protection are enabled; signatures are not
  outdated. UAC remains enabled. These checks are not proof of absence of malware.
- No separate RDP session or running TightVNC, AnyDesk, TeamViewer, Sunlogin,
  ToDesk, or UU remote-control process was found by the scoped audit. The
  existing QEMU console/noVNC still provides legitimate remote access.
- `DISM /Online /Cleanup-Image /CheckHealth` returned exit code 0 and reported
  no component-store corruption. This is the fast CheckHealth operation, not a
  full file-integrity scan or a newly performed Windows repair.
- Windows Time was stopped with Manual startup. The clock was already close to
  the host, so this was not established as the cause of Tencent's warnings.

## Applied repair

The environment routine saved the original Windows Time service state to
`C:\LabCanvas\EnvironmentHealth\time-before.json`, set only `W32Time` to
Automatic, started it, and ran `w32tm /resync`. It preserved the existing NTP
server/domain configuration and timezone. The resync succeeded; a subsequent
`w32tm /query /status` reported synchronization with `time.windows.com,0x9` and
approximately 0.2 seconds of host/guest clock difference.

The before/after root process IDs and creation times were unchanged. Both native
clients still reported `ready`; WeCom automation stayed disabled/paused. No
client/profile restart, logout, reboot, phone input, or group delivery was done.

Microsoft documents the supported Windows Time inspection and resynchronization
commands in [Windows Time tools and settings](https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings).
The component check follows [Repair a Windows image](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/repair-a-windows-image?view=windows-11).

## Reusable operator interface

From the LabCanvas repository, using the existing private Tiny11 connection:

```bash
python agentic_tools/wecom_agent/scripts/wecom_tiny11_transport.py environment --json
python agentic_tools/wecom_agent/scripts/wecom_tiny11_transport.py environment --environment-mode RepairTime --json
```

`Status` is the default. It stages a checksum/size-verified probe script in the
transport inbox, then only inspects client signatures, process/session ownership,
Defender, UAC, and the time service. It does not install/restart the helper, start
a VM, focus a client, send input, enable a chat, or modify security settings.
The script is transferred by SFTP rather than placed inside a long Windows SSH
command line; the initial inline attempt exceeded Windows' command-line limit.
Do not use this relatively expensive diagnostic on every message poll.

`RepairTime` is explicitly opt-in, requires an existing administrative SSH
session, preserves the first backup, and returns a failed result if resync fails.
No UAC popup is opened. An explicitly requested rollback is available as:

```bash
python agentic_tools/wecom_agent/scripts/wecom_tiny11_transport.py environment --environment-mode RestoreTime --json
```

Restore validates the backup's computer and service values before applying it.
An environment result is not a claim that the chat is logged in; use the native
transport health and message ledger separately. A paused WeCom configuration
remains paused even if the window itself is ready.

## Avoid unnecessary control activity

Personal WeChat intake continues through the existing cached-key, read-only
store export. It does not repeatedly focus or scroll the clients to receive
messages. Send/card operations continue to use the existing serialized GUI lane
and exact-chat/source guards.

The history-tail routine now captures an initial viewport before scrolling and
checks after batches of eight wheel events. A viewport already at the tail stops
after eight events rather than the former 48. The total older-history budget
remains 192 events; moving history is not assumed to be at the tail after one
small batch. Invalid history surfaces fail before input. This reduces redundant
control activity, but is not proven to prevent Tencent's warning.

Senders load this routine in their per-delivery subprocess, so no client restart
or backend reload is needed to apply it.

## Security-prompt handling

- Keep the existing signed clients, data, profile, guest identity, network route,
  and console session stable. Do not rotate devices or reinstall for each alert.
- A login/security prompt pauses sending; it must not trigger a client restart
  loop, repeated focus/key input, cross-account fallback, or duplicate delivery.
- Preserve pending tasks/cursors and reconcile native outbound receipts after
  legitimate verification. Do not turn a security blocker into a resend request.
- Do not patch Tencent binaries, disguise virtualization/remote access, change
  security detection code, disable Defender/UAC, or auto-accept verification.
- If a genuine warning recurs, retain its exact text privately and distinguish
  client/account verification from transport unavailability. Supported tenant or
  client verification is separate from an environment audit.

No chat delivery was requested for this maintenance operation. Private evidence
is retained under `agentic_tools/wecom_agent/.private/environment-health/`.

## Verification

Use `npm test` for the full suite. Its existing runner disables the workstation's
private live Windows transport and live image-model calls inside the test process;
it does not change live configuration. Running bare unittest discovery on this
workstation instead selected production private transport state in legacy tests,
causing unrelated fixture failures. The isolated official runner passed.

Focused tests cover explicit repair modes, verified staging, malformed results,
stable/moving chat viewports, the older-history scroll budget, invalid/out-of-frame
surfaces, and preservation of the security-prompt guards. Live Windows verification
used the actual environment routine and native read-only client health, not a
mocked time-service repair. No synthetic group message was sent.
