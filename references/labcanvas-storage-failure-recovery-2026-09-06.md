# Storage failures must not become lost messages or duplicate sends

## Incident

On 2026-09-06 at 00:25 HKT the project NVMe began returning read/write
timeouts. Linux attempted controller resets, then logged:

```text
00:27:15 Device not ready; aborting reset, CSTS=0x1
00:27:35 Device not ready; aborting reset, CSTS=0x1
00:27:35 Disabling device after reset failure: -19
00:27:35 Aborting journal on device dm-3-8
```

The controller state was `dead`. The affected ProjectsLFS filesystem held
LabCanvas code, configuration, queues, and recovery logs. WeCom's Ubuntu API
became unreachable while the native Windows WeCom client remained running.
WeChat's native client also remained running. Earlier successful Channels
downloads do not contradict this later storage outage.

These observations establish a controller/storage failure, not its underlying
hardware cause. Do not invent a thermal, firmware, power-management, Windows
Update, or model-quality diagnosis from these logs alone.

## Installed safeguards

`scripts/labcanvas_storage_guard.py` is standalone standard-library code. Its
installed copy, configuration, and state must live on a filesystem independent
of the project:

```text
~/.local/lib/labcanvas/storage_guard.py
~/.local/lib/labcanvas/storage_gate.sh
~/.config/labcanvas/storage-guard.json
~/.local/state/labcanvas/storage-guard/status.json
```

It checks the required mount, follows device-mapper slaves to the backing NVMe,
and rejects a controller that is not live, read-only mounts, and ext4 errors
recorded during the current boot before touching project files. When those
checks pass it reads the configured required files and verifies a tiny durable
write in the existing output directory. It never creates an output tree in an
unmounted fallback directory or creates replacement queues.

Disk probes run in a bounded subprocess. A timed-out probe's process identity
is retained so repeated checks cannot spawn unbounded stuck probes. Configuration
or state errors fail closed, not as an empty/new queue.

Controller failure, I/O error, probe timeout, or filesystem corruption latches
`recovery_review_required`. A later successful probe or host reboot does not
clear that hold. A briefly missing mount without evidence of corruption can
recover normally. This deliberate difference prevents silent replay after
durability becomes uncertain.

The shared gate runs before private config/log/queue access in WeChat/WeCom
supervisor startup and before restart-loop attempts. WeCom's autostart status
directory now defaults to `~/.local/state/labcanvas/wecom-autostart`. A systemd
drop-in waits using the host-side guard before loading the project supervisor;
the existing unit's process-only kill behavior is preserved. No runtime model
or agent quota is used for the once-per-minute wait. Logs describe state
transitions, not repeated raw errors or chat contents.

This is a startup/recovery gate, not hardware redundancy and not a guarantee
that every already-running task stops before its first failed disk operation.
Stop only verified project data-processing loops during an active outage.
Preserve native GUI clients and their login state. Never stop a complete tmux
server or systemd control group containing unrelated projects.

## Install and inspect

Prepare a clean source checkout on healthy storage first if the original
repository cannot be read. Do not overwrite its uncommitted work.

```bash
python scripts/install_labcanvas_storage_guard.py \
  --root /home/lachlan/ProjectsLFS/AgenticApp \
  --mountpoint /home/lachlan/ProjectsLFS
```

This is a dry run. Repeat with `--apply` to install the standalone code,
configuration, and WeCom service drop-in. Installation does not restart any
service. Immediately exercise the gate:

```bash
/usr/bin/python3 ~/.local/lib/labcanvas/storage_guard.py check
```

Exit zero means startup is allowed. Exit 75 means held/unavailable, not healthy.
`status.json` records the reason. The installed service can be active while its
guard is waiting: service liveness is not chat-processing readiness.

For this workstation, the existing three `~/scripts/create-labcanvas-*`
WeChat/WeCom entrypoints were backed up and given this gate before their `cd`
or Python launch, preserving the user's main `create_tmux_session.sh`:

```bash
ROOT=/home/lachlan/ProjectsLFS/AgenticApp
source "$HOME/.local/lib/labcanvas/storage_gate.sh"
labcanvas_storage_ready || exit 75
```

Fresh installations must add this same bounded check to external boot wrappers;
the repository supervisor scripts already include it. A guard configured for
another workspace does not gate unrelated development checkouts.

## Recovery order

1. Preserve kernel evidence, readable source changes, and private queue/delivery
   state on a healthy volume. Never turn an I/O error into empty state.
2. Identify ownership before stopping data-processing loops. Keep WeChat,
   Windows WeCom, their profiles, and remote displays intact when possible.
3. Obtain approval before rebooting or shutting down the shared workstation.
   A dead controller that already failed resets may need a cold power cycle.
   Do not repeatedly reset/rebind a mounted shared device or force remount it
   read-write. Do not run filesystem repair on a mounted filesystem.
4. Once the device is accessible, prioritize backups. Inspect SMART/error logs,
   temperatures, PCIe errors, and the manufacturer's firmware guidance. Arrange
   offline filesystem checking and repair as appropriate. Replace an unreliable
   drive; a software retry policy cannot promise to cure it.
5. Recover the original repository without discarding local work, and merge
   these guard changes. Validate private JSON/JSONL queues and SQLite integrity
   from consistent backups. Do not assume a cloned code repository contains
   chat history, credentials, pending tasks, or successful-send receipts.
6. Reconcile source message IDs with exact-chat task and delivery records.
   Retain successful sends; inspect uncertain sends against native history.
   Do not replay successful schedules, paid jobs, or publishing operations.
7. Only after that review, explicitly clear the hold:

```bash
/usr/bin/python3 ~/.local/lib/labcanvas/storage_guard.py \
  --ledgers-verified acknowledge
```

The command refuses if storage is still unhealthy. `--ledgers-verified` is an
operator attestation, not an automatic database repair/check. Then allow the
existing supervisors to restore missing windows and retry only unfinished,
authorized tasks. Confirm a real inbound-to-outbound result in its source chat.

Do not copy corrupt live SQLite files or omit WAL state as a backup strategy.
After recovery, consistent SQLite backups and lock-consistent queue snapshots
should be maintained off the project drive. This change does not claim those
history backups already exist or implement automatic cross-disk task failover.

## Verification

- 11 focused regression tests cover mount boundaries, escaped paths, LVM/NVMe
  traversal, fail-closed state, timeout child deduplication, and recovery holds.
- Full `npm test`: 1,994 tests passed, 8 optional skips.
- An isolated live fixture on healthy filesystems verified durable probing,
  persistence across CLI invocations, rejection of unreviewed acknowledgement,
  reviewed recovery, and command execution only after a healthy check.
- The actual failed controller was detected without project-volume probing.
  Both local boot entrypoints returned 75 without starting tasks.
- The WeCom unit is now waiting in the host-side guard. Its former failing
  autostart process exited. Remaining media-sync and official gateway loops
  were stopped via their exact tmux windows; native clients were not stopped.
- No storage recovery, live group delivery, or skipped-card retry is claimed
  complete while the controller remains dead.

The working recovery checkout and launcher backups are on the healthy home
filesystem under `~/.local/state/labcanvas-storage-recovery-20260906/`. They
must not be confused with a recovered production private-data directory.

## Post-repair restart, 2026-09-06 evening

After the owner repaired the disk and rebooted, the project filesystem was
read-write and its backing NVMe reported `live`. Startup remained held by the
deliberate recovery-review latch; an active guard service did not mean that
the chat workers had resumed.

Recovery performed:

- Fast-forwarded the original checkout from `309314b` to `34a31a3`, preserving
  all existing uncommitted work. The healthy-volume recovery clone was not
  substituted for the production private directory.
- Validated both JSONL queues (733 WeChat and 490 WeCom records), private JSON
  configuration/cursors, and ten nonempty SQLite databases. Used SQLite's
  backup API and ran `PRAGMA quick_check` on the copies, including the 2 GB
  WeChat mirror. Preserved terminal task states and successful-send receipts.
- Saved the consistent database copies and lock-protected queue snapshots
  under `~/.local/state/labcanvas/storage-recovery-20260906-1938/`, on the
  separate home volume. `validation.json` records the checks privately.
- Acknowledged the storage hold only after that review. The WeCom user service
  resumed its existing supervisor. Invoked
  `~/scripts/create-labcanvas-wechat-after-reboot.sh start` once to restore
  WeChat, the Studio, the career/memo scheduler, and EchoMind's scheduler.
- Started the existing Tiny11 disk through its original launcher after
  confirming no VM was running. Its qcow2 consistency check passed. Did not
  create a new VM, account, profile, or Android relay.
- Today's three LabAgent daily jobs were queued by the scheduler once. The
  first entered processing; the remaining two waited in sequence. EchoMind's
  daily PDF and the career/memo work also resumed. This is generation/queue
  evidence, not proof of delivery.

Current review endpoints, opened in the existing desktop Firefox:

- Studio: `http://127.0.0.1:19474/`
- Ubuntu WeChat:
  `http://127.0.0.1:6107/vnc.html?host=127.0.0.1&port=6107&autoconnect=1&resize=scale&reconnect=1&reconnect_delay=1000`
- Windows WeCom: `http://127.0.0.1:6143/`

All three returned HTTP 200. The restored long-running sessions are
`labcanvas-wechat`, `labcanvas-wecom`, `labcanvas-web`,
`labcanvas-career-daily`, `labcanvas-echomind-language`, and
`windows-tiny11-novnc`. WeChat uses display `:97`; WeCom uses the dedicated
Tiny11 console, not Wine or the phone. Android ingress remains disabled and
the desktop unlock watchdog remains in observation-only mode.

At this checkpoint, WeChat rejected its saved-account entry with an account
exception, and Windows was waiting at the existing user's sign-in screen.
Do not describe the system as able to receive/send live messages until both
native clients are actually logged in. WeCom's status has distinct fields:
`ok` can describe the bridge endpoint while `chat_ready=false`,
`client_visible=false`, or `closed_loop_state=login_required` describes the
unavailable chat transport.

An interactive scheduled task named `LabCanvas-WeCom-Client` now launches the
installed `C:\Program Files (x86)\WXWork\WXWork.exe` at the existing Windows
user's logon. It uses `LogonType=Interactive`, `RunLevel=Limited`, and
`MultipleInstances=IgnoreNew`. It does not store a password, enable automatic
Windows sign-in, or change WeCom credentials. The separate
`LabCanvas-WeCom-Bridge` task still owns the helper. After sign-in, verify both
the native app and the authenticated helper, followed by a source-chat
delivery check; do not reset cursors or force replay old reports.

Post-repair validation: all 11 storage-guard tests and
`labcanvas wechat selftest --suite all --json` passed. These checks do not
replace a live authenticated inbound-to-outbound test.

## Technical basis

[Linux ext4 documentation](https://www.kernel.org/doc/html/latest/admin-guide/ext4.html)
describes error handling and journal behavior. Even a read-only ext4 mount may
replay the journal, so read-only inspection is not automatically zero-write.
[e2fsck manual](https://man7.org/linux/man-pages/man8/e2fsck.8.html) explains why
repair must not be run against a mounted filesystem.
