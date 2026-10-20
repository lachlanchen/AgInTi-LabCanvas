# Native Ubuntu WeChat Recovery

## Scope

This run restored personal WeChat intake, worker replies, and report delivery
through the existing native Ubuntu client. Windows personal WeChat had returned
to its entry screen. WeCom remained paused; Android input and polling remained
disabled. Neither browser profiles nor message/task histories were reset.

This is a transport recovery procedure, not evidence that one operating system
can prevent future account-security checks. A login requirement still needs the
normal official-client login flow.

## Reconcile Intake Before Switching

Windows and Ubuntu assign different local row IDs to the same server message.
Copying a cursor between them can skip new messages or replay old requests.

`agentic_tools/wechat_gui_agent/scripts/wechat_ubuntu_cutover.py` compares exact
server IDs within each configured chat table. It advances only a contiguous
prefix already consumed by the source receiver. New rows remain pending; an
interleaving of consumed and unconsumed rows stops the operation for review.
Zero server IDs are not identities. FTS databases are not message shards.

1. Stop only the selected personal-WeChat receivers, workers and store poller.
   Wait for in-flight source batches and sends to finish.
2. Retain private backups of transport configuration, supervisor environment
   and per-chat state. Verify the Ubuntu decrypted store is fresh.
3. Inspect the plan, repeating `--config` for every configured chat:

   ```bash
   python3 agentic_tools/wechat_gui_agent/scripts/wechat_ubuntu_cutover.py \
     --config '<DIRECT_CONFIG>' \
     --source '<WINDOWS_MESSAGE_DB>' \
     --destination '<UBUNTU_DECRYPTED_MESSAGE_DIR>'
   ```

4. Apply the reviewed plan with `--apply --backup-dir '<NEW_PRIVATE_BACKUP_DIR>'`.
   Backups and updated states are private. The tool does not launch a client,
   change the selected transport, extract keys, send messages or edit task
   delivery records.
5. Select Ubuntu in the existing private transport configuration. Use the
   supervisor's `ensure` action to restore only missing services.
6. Check source freshness, ready groups, queue state and actual delivery.
   A caught-up cursor alone is not proof of a working bridge.

The live cutover retained new source messages for two worker tasks and skipped
already consumed Shares rows. Existing per-chat sessions and delivery ledgers
were preserved.

## Preserve The Client Session

A clipboard failure caused the former health policy to restart the Ubuntu
client unnecessarily. Clipboard, title and receipt failures do not prove that
the application is frozen.

- Automatic health-guard client restart now requires
  `WECHAT_ALLOW_AUTOMATIC_CLIENT_RESTART=1`; leave it unset normally.
- `WECHAT_AUTO_RECOVER_UNMAPPED` defaults to `0`. An unmapped or hidden window
  alone is not permission to replace the client.
- The repair-agent instructions require explicit operator approval before
  restarting an official chat client.
- Keep completed replies for delivery-only recovery. Do not rerun a model or
  side-effecting task merely because sending failed.

The existing desktop had no EWMH window manager. The desktop launcher now starts
Openbox only when installed and no existing window manager is detected. Reuse
the same X display and noVNC stack. In this run both normal client re-entry and
the window manager were restored before clipboard verification passed; the
evidence does not isolate either as the sole cause.

## Verify Text And File Delivery

Text sends retain a pre-Enter receipt. The sender waits up to 30 seconds for the
exact native outgoing row, allowing the incremental store refresh to complete.
The row must match the source chat, self identity, message text, timestamp,
local-row floor, nonzero server ID and accepted native status.

One live reply initially timed out after 10 seconds despite being sent. Its
stored result was reconciled against the native row without pressing Enter
again. Retry with the original task ID:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py \
  --resend '<TASK_ID>'
```

The maximized client also exposed a file-picker bug: a percentage-of-window
click missed the left-anchored folder button. `wechat_gui_send.py` now finds the
folder glyph within the composer strip and refuses absent or ambiguous matches.
It still requires a distinct verified native picker before pasting a path, and
checks the exact chat again after file selection. Theme changes that prevent
recognition fail closed rather than guessing.

Contact-list OCR also confused a gray mention in a chat preview with a contact's
name. The sender now enlarges the list crop for OCR, maps coordinates back to
screen pixels and excludes subdued preview text from title candidates. The
final native/header title guard remains mandatory. Keep private aliases exact;
broad first-name aliases can match another contact.

Saved daily outputs use their existing retry paths, not fresh report generation:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_career_daily_agent.py \
  retry-organize --send --json
python3 agentic_tools/wechat_gui_agent/scripts/echomind_language_scheduler.py \
  --daily-pdf-now
python3 agentic_tools/wechat_gui_agent/scripts/wechat_career_daily_agent.py \
  retry --date YYYY-MM-DD --send --attach-report --json
```

Inspect saved state and concurrent scheduler work before invoking these commands.
Retry only the current missing output; never drain a historical backlog on
startup. Missing translations are preparation failures, not file-send failures.

The Markdown-to-PDF translation helper now uses the shared low-effort model
policy and its configured fallback, while retaining explicit model overrides.
It previously requested a stale hardcoded model. The live corrected call
returned a complete English translation; its four-page PDF was rendered and
visually checked. Account selection still enforces subscription/reserve quota,
not paid credits.

## Verification And Startup

Live evidence confirmed seven ready/caught-up personal-WeChat groups, normal
worker delivery of the retained requests, and delivery of the saved MEMO PDF,
EchoMind previous-day PDF and delayed lesson, plus both career-report PDFs and
their summary. The file-button regression covers normal, maximized, translated
and scaled windows, plus absent/ambiguous icons. A separate regression rejects
a gray preview mention even when its text exactly matches a contact's name.

The existing enabled user startup service calls the existing WeChat stack
wrapper. It retains the selected transport, supervisor configuration and durable
schedule state. No reboot or second desktop was needed for recovery.

Keep current process IDs, the active noVNC URL, screenshots and configuration
backups in the ignored private runtime handoff. Never commit chat screenshots,
decrypted databases, message text, credentials or account identifiers.
