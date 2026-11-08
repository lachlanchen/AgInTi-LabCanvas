# WeCom Interactive Recovery And Native Document Intake

## Operating Mode

LabAgent handles incoming member messages, tasks and requested artifacts through
the existing per-chat agent. Daily research and idle inspiration remain disabled.
Enabling the transport does not authorize replaying old paused tasks or enabling
schedules. Consecutive messages may share a contextual answer; receiving every
message does not require a separate reply to each one.

Use the existing Tiny11 client and profile. Its console is
`http://127.0.0.1:6143/`, SSH is localhost port `2290`, the native helper is
`19582`, and the normalized GUI relay is `19580`. Personal WeChat and Android
control are independent and must not be restarted to repair this relay.

Private configuration and ledgers remain under
`agentic_tools/wecom_agent/.private/`. The lingering user service
`labcanvas-wecom-autostart.service` restores the tmux bridge. Verify both the
transport and persisted schedule flags after a reboot; do not infer schedule
permission from a healthy receiver.

## Missed Document Cause

The native receiver recognized gray text bubbles but not white document cards.
A member's request therefore reached the agent without its adjacent Word file.
Selected file cards use a blue background and must also remain recognizable
after a save attempt. Text and file records are now interleaved by screen position,
retaining the sender identity and chronological order.

The receiver materializes attachments before checkpointing the new viewport.
Failure leaves the inbound request eligible for retry rather than recording an
empty attachment list as successfully handled.

Passive change detection uses the native history bounds too. A percentage crop
inherited from Wine omitted the newest rows in a tall Windows console and could
delay processing until the periodic rescan. The native crop includes those rows
while excluding the composer, so typing does not repeatedly trigger intake.

## Original-File Route

1. Open **Save as...** on the exact inbound card, within the serialized GUI lock.
2. Read the native filename from the guarded standard Save As dialog. If Windows
   hides the extension, require one supported extension in that same card.
   Compare the complete name with the card before saving.
3. Save to a new file under `C:\LabCanvas\WeComBridge\intake\<identity>\`.
   The helper accepts only an owned Save As dialog and supported document types;
   security and unrelated modal dialogs remain blocked.
4. Wait for the guest file, calculate its SHA-256, copy through SFTP, and verify
   both byte count and checksum on Ubuntu. Keep the original and its receipt in
   the ignored, same-chat source-media directory with private permissions.
5. Pass the attachment to the existing WeCom ingest and document-reader routines.
   The resumed agent receives readable document context and owns the substantive
   answer. No manual replacement answer or new research pipeline is needed.

Do not retrieve a file through `Clipboard.GetFileDropList`. Delayed clipboard
rendering can open Save As on the helper's STA thread. Even reading clipboard
text after copying a file can trigger that rendering. Use the native Save As
route directly.

Do not fill an IFileDialog filename with `WM_SETTEXT` alone: the field can display
the new value while the dialog still saves to its old destination. Use normal
edit input and wait for the exact field value before submitting. Verify the
actual file afterward; a successful click is not evidence of a saved file.
Use explicit Unicode Win32 marshalling for reading the filename. Avoid retaining
UI Automation providers in the persistent helper.

For text delivery, native WeCom may copy an old selected history bubble even
when the editor is empty. The Tiny11 sender independently checks the empty
editor body, excluding borders and footer controls and allowing only the caret.
Draft text or an attachment must still fail the emptiness check. Reconcile a
previously uncertain delivery from exact native message evidence rather than
blindly repeating it.

## Recovery And Checks

The existing VM launcher also needed a restart correction: an owned, still-live
noVNC listener can outlive the stopped VM. Reuse it only when its recorded PID
and complete websockify endpoint match the same stack. A foreign listener still
blocks startup. Do not launch another noVNC instance or replace the VM disk.

Useful checks:

```bash
PYTHONPATH=src python -m agenticapp wecom gui status --json
PYTHONPATH=src python -m agenticapp wecom daily status --json
agentic_tools/wecom_agent/scripts/install_wecom_autostart.sh status
python -m unittest discover -s tests -p 'test_wecom_native_file_intake.py'
python -m unittest discover -s tests -p 'test_wecom_tiny11_transport.py'
python -m unittest discover -s tests -p 'test_wecom_agent_bridge.py'
```

Restart only `gui-restart` or `worker-restart` through `wecom_tmux.sh` when their
code changes. Preserve the logged-in clients. Worker model defaults come from
the shared policy; an explicit environment override remains authoritative.
Keep account configuration, chat content, document names, screenshots, tokens
and runtime receipts out of commits.

## Live Validation

On November 8, the original incoming Word document was saved natively, transferred
with matching checksums, and parsed through the existing DOCX reader. The normal
worker reviewed the complete readable content and returned its assessment to the
same group. Copying the native sent bubble back matched the stored agent answer
exactly. The uncertain receipt was reconciled through the delivery ledger, without
resending the answer, and the task reached `done`.

The relay reported `ready` with no input or login blocker. Both daily group
enrollments and the idle-inspiration setting remained disabled. The nine older
paused tasks were preserved rather than replayed. This verifies the document
path and a real response; it is not a claim that every other media route has been
retested in this recovery.
