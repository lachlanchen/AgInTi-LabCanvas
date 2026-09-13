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

On 2026-09-13:

- Both native Windows clients were visibly logged in on interactive session 1.
- The existing WeCom Tiny11 helper, relay, worker, and schedules remained active.
  This is not proof that every historical task was delivered.
- Personal WeChat's read-only store probe found 19 usable database keys and a
  valid session store. Only three of the six configured message tables were
  present in the locally available message store. This must not be reported as
  a healthy six-chat receiver.
- Exact title probes passed for EchoMind, LazyResearch, and Shares. Initial
  probes for the other configured targets failed. A missing native search
  result must not fall through to an internet search or a guessed recipient.
- Personal WeChat's new adapter remains disabled, is not connected to the
  production direct monitors/workers, and has not passed outbound text/file
  delivery verification. Ubuntu transport code and state were left intact.
- No test messages or files were sent, no historical tasks were replayed, and
  no Android UI polling was enabled during these checks.

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

The diagnostic adapter is:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py status
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py sync
python3 agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_bridge.py probe-chat --chat '<EXACT_CONFIGURED_CHAT>'
```

`sync` imports allowlisted native rows into an ignored shadow database only.
It does not enqueue a task or send a message. `probe-chat` can change the selected
native chat but does not send. A failed one-shot sync exits nonzero. The optional
loop is diagnostic, not installed as a production receiver by this change.

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

Sender mapping is schema-dependent: use `message_resource.SenderName2Id` when
populated, otherwise the current build's shard `Name2Id`. Do not mix populated
indexes. Reserved self ID 2 resolves to the configured, verified account;
unresolved sender identities fail closed. The current sample's ordinary
message prefixes agreed with the shard mapping. System notices are separate.

The host shadow retains binary content losslessly, distinguishes local IDs by
source shard, and commits row identities and cursors in one transaction. Local
system rows may share server ID zero; server ID alone is not a unique key.
Repeated native exports must not duplicate messages. Only one export runs at a
time, so probes cannot overwrite the poller's request/result packet.

### Private Provisioning

Reuse the verified embedded Python at `C:/LabCanvas/Python312/python.exe`:
Python 3.12.10, cryptography 50.0.1, cffi 2.1.1, pycparser 3.0. These are shared
within this VM, not another Python/Windows installation per chat.

The current guest reader workspace is `C:/LabCanvas/WeChatStore`. It contains the
reviewed standalone `db.py`, the three Python scripts above, private
`config.json` with the exact account's `db_storage` path, private key cache,
snapshot cache, request/export JSON, and logs. Restrict its ACL to the owning
Windows user, SYSTEM, and Administrators. Do not print or commit those files.

Host private state lives under
`agentic_tools/wechat_gui_agent/.private/tiny11/`, configured by sibling
`wechat_tiny11.local.json`. Keep files mode 0600/directories 0700. The separate
WeCom configuration, queue, event ledger, and helper credential remain owned by
the WeCom transport. Use verified SFTP with the existing transport for file
staging; use forward-slash guest paths and PowerShell `-LiteralPath`.

## Remaining Cutover Gates

These are required work, not completed claims:

1. Resolve all six exact native chats and their current account/table bindings.
   Do not copy another group's table, rename a target by guess, or use fuzzy
   sidebar text as send authorization.
2. Prove incoming text, source IDs, sender identities, group isolation, and
   consecutive-message handling using the existing direct-agent runtime.
3. Connect the Windows shadow source to the existing monitor/worker message DB
   resolver without changing agent sessions, prompts, schedules, or backends.
   Keep Linux and Android resolvers for deliberate fallback.
4. Verify text delivery by a new exact native outbound receipt, not merely an
   empty composer. Persist send intent before Enter and account for own-message
   echoes before intake can route them.
5. Verify personal WeChat's actual file-composer/modal behavior and exact new
   file receipt. The existing WeCom file UI must not be assumed identical.
   Retain uncertain-send holds; never blind-retry an attempted submission.
6. Preserve old cursors and seed new Windows cursors at an explicit cutover
   boundary. Reconcile pending authorized work separately; no automatic replay
   of an old backlog after changing transports or rebooting.
7. Make receiver/sender selection exclusive, persist the selected transport for
   reboot, and perform one end-to-end verification without group spam.

The previous WeCom retry-loop repair remains authoritative:
[uncertain file send recovery](wecom-file-retry-loop-repair-2026-09-13.md).
The 11 held uncertain legacy tasks must not be requeued merely because both
Windows clients are now logged in.

## Regression Checks

Local validation on 2026-09-13 passed: 2,053 tests, 13 skipped. Live WeCom health
reported `chat_ready=true` and `closed_loop_state=ready`; the shared noVNC URL
returned HTTP 200. The second personal WeChat shadow import inserted zero
duplicate rows and explicitly reported `all_tables_available=false` (3/6).

```bash
python3 -m unittest discover -s tests -p 'test_wechat_tiny11_bridge.py'
python3 -m unittest discover -s tests -p 'test_wecom_tiny11_transport.py'
PYTHONPATH=src python3 -m unittest discover -s tests
```

Coverage includes real SQLite WAL overflow/commit handling, corrupt headers,
private mirror identity/deduplication, zero server IDs, invalid tables,
disabled-send gating, no Enter on missing native search results, app-scoped
helper headers, pointer boundaries, and unchanged WeCom defaults. Mocked tests
do not substitute for the pending live Windows personal-WeChat cutover gates.
