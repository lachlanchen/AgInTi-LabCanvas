# Tiny11 Default Browser Repair

## Cause

The Windows client displayed a reminder that it could not open a browser and
asked for a default browser. The VM had no Edge, Firefox, or Chrome executable.
HTTP and HTTPS still selected `MSEdgeHTM`, but Windows Shell could not resolve
either protocol to an installed executable. This was a missing browser, not a
KVM/noVNC connection failure or a WeCom authentication problem.

## Reusable Repair

Canonical script:
`agentic_tools/wecom_agent/windows/Repair-Tiny11Browser.ps1`

Deployed guest copy:
`C:\LabCanvas\Displays\Repair-Tiny11Browser.ps1`

Run in the Windows user's PowerShell session (or that same user's SSH session):

```powershell
# Read-only association/executable check; does not launch a browser.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LabCanvas\Displays\Repair-Tiny11Browser.ps1

# Explicit repair when the selected Edge handler is missing.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LabCanvas\Displays\Repair-Tiny11Browser.ps1 -InstallMissingEdge
```

The execution-policy option applies only to this PowerShell invocation. It
does not change machine execution policy or WeCom security controls.

The script uses Windows `AssocQueryString` to resolve HTTP/HTTPS, then verifies
the returned executable exists. Installation is opt-in, targets exactly
`Microsoft.Edge` from the `winget` source, retains installer hash validation,
and requests silent installation without a reboot. Existing working handlers
are a no-op. A different explicitly selected browser is not replaced; inspect
that browser instead. UserChoice hashes, credentials, and chat profiles are
never modified. Installation errors remain errors, not success receipts.

## Verified Result

- Installed Microsoft Edge `153.0.4234.32`, installer exit code 0.
- WinGet verified the Microsoft-hosted installer hash:
  `4388dc0c46b5ec98aebdf9b78a07f2c70076164f322e20228dc7de366d60a385`.
- Installed executable: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.
- Executable Authenticode status: `Valid`, signer Microsoft Corporation.
- Both HTTP and HTTPS resolved to that executable after installation.
- Repeating the repair returned `ok=true`, `installed=false`.
- A normal `Start-Process 'https://example.com'` in the existing interactive
  console session opened Edge and displayed the Example Domain page.
- First-run setup completed without Microsoft/Google sign-in, browser-data
  import, optional browsing-data personalization, or automatic Windows-start
  launch. No VM, WeCom, or WeChat restart was required.
- The test browser was closed and the temporary launch task removed. No chat
  response or artifact delivery was requested for this internal diagnostic.
- Five identical old browser reminders were stacked behind WeCom. Each was
  brought forward, visually checked for the exact missing-browser message,
  and dismissed individually. The final screenshot shows the reminders gone
  and the logged-in LabAgent chat still open. Do not blindly dismiss security
  or authentication dialogs using the same coordinates.
- Final read-only verification found both protocol handlers working, the
  original WeCom process still alive, no remaining Edge test processes, and
  no temporary `LabCanvas-Browser-*` scheduled tasks.

Do not run a visible browser smoke test from SSH session 0. Use the existing
interactive console session and serialize it with the WeCom GUI lock, so the
relay cannot mistake a covering browser window for chat history. Release that
lock as soon as the test window is closed. Keep one existing noVNC console at
`http://127.0.0.1:6143/`; no second desktop is needed.

Installation logs stay on the guest under `C:\LabCanvas\BrowserRepair`.
Screenshots stay private under `output/tiny11-browser-repair/20260913/`.
Do not commit installers, profiles, credentials, or screenshots of chat history.

## Primary References

- [Microsoft WinGet install command](https://learn.microsoft.com/en-us/windows/package-manager/winget/install)
- [Windows Shell association query](https://learn.microsoft.com/en-us/windows/win32/api/shlwapi/nf-shlwapi-assocquerystringw)
