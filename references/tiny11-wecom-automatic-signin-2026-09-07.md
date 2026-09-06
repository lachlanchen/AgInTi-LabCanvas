# Tiny11 automatic Windows sign-in for WeCom

## Scope and verified state

The owner explicitly authorized automatic sign-in on the existing dedicated
Tiny11 VM. Use `agentic_tools/wecom_agent/windows/Configure-Tiny11Autologon.ps1`;
do not recreate the account, reset its password, or replace the WeCom profile.

On 2026-09-07 the helper was copied through the existing localhost SSH/SFTP
transport to `C:\LabCanvas\WeComBridge\Configure-Tiny11Autologon.ps1`.
Credential validation with `LogonUser` succeeded before configuration changes.
Post-apply checks reported:

- `automatic_login=true`;
- `lsa_secret_present=true`;
- `plaintext_registry_password_present=false`;
- `limited_logon_count_present=false`;
- `reboot_performed=false`.

The existing WeCom bridge still reported `chat_ready=true`,
`client_visible=true`, and `closed_loop_state=ready`. No logout, VM reboot,
phone UI control, message replay, or public publication was performed. A
future actual boot is the remaining end-to-end test of automatic sign-in.

## Credential handling

`Enable` accepts a one-line JSON object containing `password` on standard
input. Pass it over the authenticated SSH connection, not command arguments,
shell history, a temporary credential file, or source code. Obtain a password
interactively with Python `getpass` for future human-operated runs; never put
an actual credential in examples or documentation.

The native helper validates the supplied local-account password, stores it
using `LsaStorePrivateData` under Winlogon's `DefaultPassword` secret, verifies
that the secret exists, and enables `AutoAdminLogon` last. It does not output
the secret. Its temporary unmanaged password buffer is zeroed after use.
Existing automatic-login configuration for another username is rejected.

LSA storage is encrypted, but Windows administrators can recover it.
Automatic sign-in also makes the account accessible to anyone with access to
the VM console. Keep noVNC, SSH, RDP, and the bridge localhost-only, and
protect the Ubuntu host and VM disk. This is an explicitly authorized
convenience for a dedicated machine, not a way to bypass WeCom authentication.

## Inspection and reversal

Run these through the existing Tiny11 SSH transport, replacing the computer
name with the exact intended VM name:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\LabCanvas\WeComBridge\Configure-Tiny11Autologon.ps1 -Mode Status -ExpectedComputer TINY11-KVM
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\LabCanvas\WeComBridge\Configure-Tiny11Autologon.ps1 -Mode Disable -ExpectedComputer TINY11-KVM
```

`Status` is read-only. `Disable` sets `AutoAdminLogon=0` and leaves the
encrypted secret intact; it does not log off the current session or delete
credentials. Inspect the before/after metadata under the host's private
`~/.local/state/labcanvas/storage-guard/tiny11-autologon-*.json`. Those files
contain configuration booleans/account identity, not the password.

## Startup sequence

1. The existing LabCanvas user supervisor starts/reuses the Tiny11 VM.
2. Windows performs automatic console sign-in using the saved local account.
3. `LabCanvas-WeCom-Client` starts the installed WeCom executable at logon.
4. `LabCanvas-WeCom-Bridge` starts the interactive helper at logon.
5. LabCanvas resumes its existing exact-group receiver, sender, and ledger.

WeCom may still request account verification when its own session expires.
Automatic Windows sign-in cannot guarantee that WeCom never requires a QR.
Do not reset or repeatedly relaunch a client to work around that requirement.

## Separate Windows screens

noVNC can display QEMU's Windows console. Two browser windows connected to
one console share the same desktop, focus, mouse, and keyboard; that does not
provide independent application automation. For fully separate WeChat and
WeCom screens, use separate isolated desktops, with a second dedicated
Windows VM as the straightforward option for this setup. No second VM or
Windows WeChat migration was authorized or performed during this change.
Keep working Ubuntu WeChat code/profile intact until any replacement has
passed exact-account, inbound, outbound, file-transfer, and restart checks.

## Sources

- [Microsoft automatic-logon guidance](https://learn.microsoft.com/en-us/troubleshoot/windows-server/user-profiles-and-logon/turn-on-automatic-logon)
- [Microsoft Sysinternals Autologon and its LSA security caveat](https://learn.microsoft.com/en-us/sysinternals/downloads/autologon)
- [Microsoft LsaStorePrivateData reference](https://learn.microsoft.com/en-us/windows/win32/api/ntsecapi/nf-ntsecapi-lsastoreprivatedata)
- [noVNC server requirements and QEMU support](https://github.com/novnc/noVNC#server-requirements)
