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

## Data Path

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
