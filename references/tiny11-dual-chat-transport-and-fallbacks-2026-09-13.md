# Tiny11 Chat Transports and Preserved Fallbacks

## Requested Topology

Use the existing Tiny11 console for personal WeChat and WeCom, side by side.
Keep the Ubuntu personal WeChat implementation and the physical Android phone's
WeCom implementation, configurations, profiles, and cursors for fallback.
They are fallbacks, not simultaneous duplicate receivers or senders.

The current shared console is <http://127.0.0.1:6143/>. It belongs to the existing
Windows VM stack; do not launch another desktop, restart either chat client, or
log out an account to inspect it. The phone mirror may remain available without
Android input/polling. Do not revive retired per-app noVNC stacks.

## Verified State and Limitations

Verified during the 2026-09-13 evening cutover:

- Both native Windows clients were visibly logged in on interactive session 1.
- The existing WeCom Tiny11 helper, relay, worker, and schedules remained active.
  This is not proof that every historical task was delivered.
- Personal WeChat is enabled in the existing six direct monitors, worker
  senders, and daily senders. The read-only Windows shadow is
  `message_999998.db`. Five configured native contact bindings are present;
  `My devices` is not found under its configured identity. Four native message
  tables are currently materialized. Empty shadow tables let known contacts
  with no local history be monitored; they do not prove that a missing group
  exists. Health reports the missing binding separately.
- Live exact-title navigation passed for EchoMind, LazyResearch, Shares, MEMO,
  and the career DM. Both Shares-to-DM and DM-to-Shares switching passed. A
  missing native result never falls through to an internet search or guessed
  recipient.
- A new actual Shares card/request reached the direct agent and worker. The
  agent's acknowledgement has a native outgoing receipt. This proves text
  intake/routing/reply, not successful video download.
- Today's MEMO PDF, career summary, and Chinese/English career PDFs were
  delivered through the normal routines. Exact new native rows verified sender,
  conversation, server ID, text or filename/byte count, and send status. Retry
  reconciliation recognized completed sends without uploading the PDFs again.
- EchoMind's six-hour quiet-time policy remains intact. The previous-day daily
  PDF was `skipped_no_source`, not delivered; do not call it delivered merely
  because the scheduler process is alive.
- No synthetic test messages, Android UI polling, account logout, or bulk
  historical replay was used. Only the current authorized scheduled outputs
  were recovered. Original Ubuntu/Android code, profiles and cursors remain.

**Media follow-up:** automatic Windows Channels Copy Link recovery, original
download, transcription, and native video receipt verification were subsequently
verified for one exact source. Two other cards exposed further history/menu/player
recovery gaps under repair. See
[Channels originals and retry reconciliation](windows-wechat-channels-originals-and-send-reconciliation.md)
for the shared implementation and evidence requirements. General native
attachment-cache export is a separate capability, not implied by this result.
The inactive Ubuntu QR screen is never evidence about the Windows login.

**2026-09-14 00:02 update:** the selected Windows WeChat client itself displayed
"For account security, log in again." Native recovery was stopped. WeCom stayed
logged in. The two unfinished Channels tasks remain unresolved; the successful
video must not be resent. The exact cause of this account-security transition
has not been established. Do not keep reopening cards or reset profiles to
work around it. Revalidate the native adapter after authorized login before
claiming all three source deliveries succeeded.

Do not interpret a visible login, `helper.ok`, or a successful database copy as
end-to-end delivery. Do not flip the private `enabled` flag based on this note.

## Shared Windows Helper

`agentic_tools/wecom_agent/windows/WeComBridge.ps1` accepts an authenticated
`X-LabCanvas-App` header: `wecom` or `wechat`. Missing headers retain the existing
WeCom behavior. The corresponding host setting is `tiny11.app` in the private
transport configuration.

Every request selects one app. Window discovery uses process ownership and
native window geometry. Screenshots mask the other app and reject overlapping
main windows; shadow/title helper windows are not mistaken for the other chat.
Pointer input must remain inside the selected app's main window. This closes
the gap where focusing WeCom could still click adjacent WeChat coordinates.
Both adapters share the existing serialized GUI-input lock.

Only the interactive helper scheduled task was refreshed. Neither client was
restarted. SSH PowerShell output is explicitly UTF-8 so Chinese JSON/text does
not fail host decoding. Keep the helper bound to loopback and reuse its
authenticated SSH tunnel; never expose the token or decrypted store.

## Read-Only Personal WeChat Store

The production adapter is:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py status
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py sync
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py probe-chat --chat '<EXACT_CONFIGURED_CHAT>'
```

`sync` imports allowlisted native rows into an ignored shadow database only.
It does not itself enqueue or send; the existing direct monitors consume its
rows. `probe-chat` changes the selected native chat but does not send. A failed
one-shot sync exits nonzero. The supervisor owns one `tiny11-store` loop, which
polls without GUI interaction and backs off on failures. Unchanged successful
polls are quiet.

Guest scripts under `agentic_tools/wecom_agent/windows/`:

- `Inspect-WeChatAccessibility.ps1`: bounded, short-lived accessibility probe.
  The current Qt client exposed only its root/container, not message controls.
  No accessibility provider is retained in the persistent helper.
- `Inspect-WeChatStore.py`: account-scoped key/session and SQLite integrity
  diagnostics, with private logs and no key material on stdout.
- `Export-WeChatStore.py`: explicit account match, allowlisted message tables,
  source-local IDs, sender identities, native content bytes, and high-water marks.
- `wechat_store_snapshot.py`: stable private base/WAL snapshot validation.

The reviewed reader is **only** `wechatauto/db.py` from
[wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica), pinned to
commit `61a88bb38a63b8b9a7e3557398195fd4991e9407`. Its SHA-256 is
`28292ae9bfd3dceb2c2ec890b8f3ea0c93766af66a074b535bc45d1cd2415e02`.
The checkout stays private and outside tracked source. Re-review and verify the
hash before updating it. Do not import the upstream GUI driver or its memory
patching mechanisms. Our use reads the authorized account's store/key state;
it does not write app process memory, inject code, or modify the live database.

The earlier [wechat-decrypt reader](https://github.com/ylytdeng/wechat-decrypt)
did not recover the current Windows build's keys. Preserve it for the existing
Ubuntu workflow; this finding does not justify replacing unrelated readers.

### Snapshot Defect and Fix

The encrypted base database decrypted correctly, but the upstream WAL merge
produced an invalid SQLite copy. It filtered pages by the first byte of the
decrypted page, which incorrectly rejects valid overflow pages, and did not
limit replay to the last valid committed transaction.

The replacement follows the [SQLite WAL format](https://www.sqlite.org/fileformat2.html):

1. Copy base and WAL to private temporary files without changing the originals.
2. Require source size/mtime stability across the copy, with bounded retry.
3. Validate the WAL header, page size, salts, checksum chain, and commit frames.
4. Apply every valid committed page, including overflow pages. Ignore stale,
   incomplete, or uncommitted tails; truncate to the committed database size.
5. Require SQLite `quick_check` to return `ok` before atomically replacing the
   private snapshot. Cache only the validated source stamp.

On Windows, `with sqlite3.connect(...)` commits/rolls back but does **not** close
the connection. Use `contextlib.closing` before replacing a database file, or
Windows can reject replacement because the file is still open.

For this verified Windows schema, `real_sender_id` references **the message
shard's `Name2Id`**. Do not switch to `message_resource.SenderName2Id` after it
becomes populated: that independent index first appeared after a PDF upload and
caused a receipt read to fail. Never hardcode self ID 2. The configured account
must match the actual reader account, and every sender comes from its own shard.
System notices remain separate.

The host shadow retains binary content losslessly, distinguishes local IDs by
source shard, and commits row identities and cursors in one transaction. Local
system rows may share server ID zero; server ID alone is not a unique key.
Repeated native exports must not duplicate messages. Only one export runs at a
time, so probes cannot overwrite the poller's request/result packet.
Exports reread a short tail to update native send status/server IDs in place;
the shadow row's identity does not change and the monitor does not see another
incoming message.

### Private Provisioning

Reuse the verified embedded Python at `C:/LabCanvas/Python312/python.exe`:
Python 3.12.10, cryptography 50.0.1, cffi 2.1.1, pycparser 3.0. These are shared
within this VM, not another Python/Windows installation per chat.

The current guest reader workspace is `C:/LabCanvas/WeChatStore`. It contains the
reviewed standalone `db.py`, the three Python scripts above, private
`config.json` with the exact account's `db_storage` path, private key cache,
snapshot cache, request/export JSON, and logs. Restrict its ACL to the owning
Windows user, SYSTEM, and Administrators. Do not print or commit those files.
Set the protected ACL on the workspace root and let children inherit it.
Removing inheritance recursively without granting replacement permissions can
leave existing child files unreadable. Verify file access as the owning user.

Host private state lives under
`agentic_tools/wechat_gui_agent/.private/tiny11/`, configured by sibling
`wechat_tiny11.local.json`. Keep files mode 0600/directories 0700. The separate
WeCom configuration, queue, event ledger, and helper credential remain owned by
the WeCom transport. Use verified SFTP with the existing transport for file
staging; use forward-slash guest paths and PowerShell `-LiteralPath`.

## Delivery and Recovery

`wechat_transport_selection.py` is the lightweight selector shared by the
minimal monitor venv, full workers, CLI health, and supervisors. The ignored
`wechat_tiny11.local.json` enables the Windows route. WeCom uses its separate
config, queue, identity and state; only GUI input serialization and the
app-scoped Windows helper are shared.

- Use existing `send_gui_message`, worker `send_message`/`send_file`, or the daily
  delivery routines. They select Windows automatically. The bridge also accepts
  a private `send --request-file` JSON with `chat`, `task_id`, `message`, `files`.
- Keep task IDs stable across retries. Intent is persisted before Enter. If a
  process loses its reply after submission, reconcile the native receipt; do
  not switch transports or submit again because of a timeout.
- Text delivery needs exact normalized content, current native row, self sender,
  exact chat, successful status and nonzero server ID. File delivery additionally
  needs exact filename and byte count. A truncated composer filename is only a
  pre-send check, never proof of delivery.
- Before a file submission, write `file_send_intent` with status `sending` and
  content identity to the mirror. Using `file_send` at that stage fails the
  established echo contract and can route our own PDF as a user request. Native
  `<appattach><totallen>` must be parsed even when the message has no MD5.
- Compare Chinese chat IDs as UTF-8 bytes with `hmac.compare_digest`; its string
  mode rejects non-ASCII. Normalize Windows clipboard paths with
  `PureWindowsPath`, not raw slash-sensitive strings.
- Clipboard access can retry briefly when another app owns it. Do not retry
  clicks or Enter. Preserve existing drafts on every failed composer check.
- Prefer raw-pixel Chinese OCR for small native titles; aggressive sharpening
  changed a short DM title into another character. Verify the full title after
  navigation, not just the sidebar or search row.
- Personal WeChat uses Enter, not WeCom's Alt+S. Escape can hide its main window
  in the tray. Restore through the running client's configured normal hotkey
  (verified default Ctrl+Alt+W here), gated to one exact existing app window.
  Do not force-show a Qt tray-hidden window (it can become white), launch a
  second login process, restart the client, or log out to restore it. The live
  restore retained the same main process and authenticated conversation.
- The shared desktop placement watcher must not move personal WeChat's search
  results, menus or Channels popups. They are top-level Qt windows too. The old
  broad size-based rule misclassified the search popup as a login dialog,
  centered it mid-navigation, and invalidated the sender's coordinates.
  `Select-AppPlacementWindows` now selects only named WeChat main/login
  windows with the native main-window class. Keep the existing WeCom filter.
  Pale native search-category labels need contrast-preserving OCR, and the
  title crop must exclude toolbar icons even after the main window narrows.

## Startup and Schedules

`wechat_supervisor_tmux.sh` owns `labcanvas-wechat:tiny11-store`, the existing
six `direct-*` windows, and two workers. With Tiny11 selected, it does not launch
the legacy decrypt/media-sync/chat-sync/unlock or Android ingress loops. Old
cursors were backed up and Windows cursors seeded at the cutover boundary;
only subsequent current messages were handled. Do not reset those cursors on
reboot.

The existing enabled `create-tmux-session.service` invokes
`~/scripts/create-labcanvas-wechat-after-reboot.sh`; the WeCom autostart service
retains the VM/helper connection. This cutover did not reboot the live logged-in
VM to test persistence. Only idle monitor/worker/scheduler processes were
reloaded. No current message task may be killed for a deployment.

Recover a completed daily output without rerunning its agent or duplicating a
send:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_career_daily_agent.py retry-organize --send --json
python3 agentic_tools/wechat_gui_agent/scripts/wechat_career_daily_agent.py retry --send --attach-report --json
PYTHONPATH=src python3 -m agenticapp wechat health --json --compact
```

Career retry preserves `pdf_required` and both language PDF requirements.
A previously sent summary is not a completed report delivery. EchoMind daily
06:00 HKT and six-hour lessons remain distinct; 20:00-08:00 quiet hours apply to
periodic conversation only, not daily output.

The previous WeCom retry-loop repair remains authoritative:
[uncertain file send recovery](wecom-file-retry-loop-repair-2026-09-13.md).
The 11 held uncertain legacy tasks must not be requeued merely because both
Windows clients are now logged in.

## Regression Checks

The initial pre-cutover baseline passed 2,053 tests (13 skipped). The final
cutover suite, including the layout-watcher fix, passed **2,070 tests**. All
25 personal-WeChat transport tests passed. Live navigation then passed the
career DM, MEMO, EchoMind, LazyResearch, Shares, and back to MEMO with the
fixed watcher running. Run tests
with private transport selection disabled so a developer's logged-in account
cannot change mock database resolution or cause a real send. Worker startup
selftests set this automatically.

```bash
WECHAT_TINY11_DISABLE=1 python3 -m unittest discover -s tests -p 'test_wechat_tiny11_bridge.py'
WECHAT_TINY11_DISABLE=1 python3 -m unittest discover -s tests -p 'test_wecom_tiny11_transport.py'
WECHAT_TINY11_DISABLE=1 PYTHONPATH=src python3 -m unittest discover -s tests
```

Coverage includes real SQLite WAL overflow/commit handling, corrupt headers,
private mirror identity/deduplication, zero server IDs, invalid tables,
disabled-send gating, native receipt updates, in-flight file echo suppression,
no Enter on missing native search results, app-scoped helper headers, pointer
boundaries, and unchanged WeCom defaults. Mocked tests do not substitute for
the remaining exact media retrieval and missing-chat binding checks.
