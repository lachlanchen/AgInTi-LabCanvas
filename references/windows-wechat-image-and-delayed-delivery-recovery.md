# Windows WeChat Images and Delayed Video Delivery

Updated: 2026-09-26

This extends [the Windows Channels runbook](windows-wechat-channels-originals-and-send-reconciliation.md).
It repairs native Windows image intake and late file receipts without starting
another desktop, operating Android, restarting chat clients, or replaying video.

## Image Failure and Repair

The worker still searched the inactive Linux cache after the Windows migration.
In addition, a Windows image message's XML MD5 is not its native cache filename.
The native resource database supplies that mapping. Most observed full images
were encrypted V2 DAT files containing WXGF/HEVC, not JPEG files.

The persistent path is:

1. Validate the configured account and exact chat/table/message binding.
2. Translate the host projection ID through `Tiny11Rows` to the native ID.
3. Join `MessageResourceInfo` by chat, local ID, server ID, creation time and
   image type. Accept one unambiguous resource token in its known protobuf field.
4. Select that token's high/full native cache file, never a thumbnail, nearby
   file selected by modification time, chat bubble crop or viewer screenshot.
5. Decode with the separately installed upstream decoder. Cached intake uses
   a private key without process-memory scanning or GUI input.
6. Transfer through the existing SSH/SFTP connection and validate source
   length/MD5 where supplied, export length/SHA-256, and successful decoding.
7. Retain WXGF as the original. Decode its HEVC image on CPU to native-size
   lossless PNG for vision; no resizing or lossy JPEG conversion is introduced.
8. Feed that source into the existing image-reading agent, source knowledge
   storage and ordinary exact-chat sender. The agent supplies the useful reply.

The guest snapshot operation shares the existing store-sync lock. Waiting for
that lock is bounded. A missing cache, missing key, ambiguous resource mapping,
checksum mismatch and decoder failure remain distinct private failure states.
None authorizes substitution of another image. An uncached original still
requires native retrieval; this repair does not claim remote CDN access.

### Attachment Cache Arrival Race

A live image on September 26 reached the message database before its full
attachment was cached. The native reader correctly returned
`exact_full_image_not_cached`, but the worker immediately converted that into a
generic file-upload/resend message and marked the task done. Its original
subsequently became available and passed the existing resource/transfer checks.
This was a retrieval timing and orchestration failure, not missing vision.

The worker now opens the exact allowlisted source chat using the existing
serialized Windows bridge and retries the same native export up to three times,
with 0.5, 2 and 5 second delays. The snapshot lock is released between attempts;
the GUI lock is released after opening the chat. Record the initial failure,
`gui_cache_probe` and `second_refresh` in the task's media-resolution manifest.
Do not retry identity, checksum, decoder or key-provisioning failures as cache
misses. Respect the existing GUI/media-preflight disable switches.

If no original is recovered, image intake now reaches the per-chat agent with
the actual preflight evidence rather than returning the generic file receipt.
The agent can recheck with the existing `recover --task-id` command. It must not
guess from a thumbnail, switch accounts, ask for a resend before inspecting the
native recovery evidence, or promise background recovery without a durable job.
Opening a chat may let the official client download its attachment; it is not a
guarantee for expired/deleted originals or a substitute for verified retrieval.

For an already-missed image, use the normal worker's exact-task `--reprocess`
with a recovery reason, not a manually composed reply or a broad history replay.
On September 26 the worker recovered a 750x1334 original and delivered its
semantic App Store screenshot analysis to the source group with no send errors.
Keep task IDs, screenshots and receipts in ignored runtime evidence.

Regression coverage in `tests/test_wechat_tiny11_image.py` includes late cache
arrival, bounded failure, failed chat opening, integrity/key failures, exact-task
reuse and the agent handoff. Neither Ubuntu nor Android transport is touched.

### Reusable Installation

The existing native store reader and account keys must already be provisioned.
Do not duplicate profiles or reacquire keys on every incoming message.

Upstream decoder: [ylytdeng/wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt),
pinned revision `656d06a527781bc715955bdade080234a47e122b`.
Only `decode_image.py` and `find_all_keys.py` are deployed beside the existing
guest reader. Keep the upstream checkout under ignored private storage.

The embedded guest Python needs PyCryptodome. The verified wheel is
`pycryptodome-3.23.0-cp37-abi3-win_amd64.whl`, SHA-256
`c75b52aacc6c0c260f204cbdd834f76edc9fb0d8e0da9fbf8352ef58202564e2`.
It can be downloaded once with `pip download --only-binary=:all: --no-deps
--platform win_amd64 --python-version 312 --abi cp312 pycryptodome==3.23.0`.
Verify that digest, transfer through the existing SFTP helper, and extract this
trusted wheel beside the embedded guest reader. Do not extract arbitrary chat
archives into the reader directory.

```bash
python agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_image.py install \
  --decoder-root '<PINNED_PRIVATE_DECODER_CHECKOUT>'

python agentic_tools/wechat_gui_agent/scripts/wechat_tiny11_image.py recover \
  --task-id '<EXACT_IMAGE_TASK_ID>' --provision-key
```

`install` checks the pinned revision and unchanged decoder files, deploys the
adapter, restricts guest directory ACLs and verifies the crypto dependency.
`--provision-key` is an explicit one-time offline derivation using the installed
upstream routine and exact account/cache metadata. It never runs automatically
per message. Later diagnostics use the same command without that flag.

Host outputs live in the ignored task's `native_image/`, with a
`native-image-export.json` provenance manifest. Guest keys remain in
`C:\LabCanvas\WeChatStore\image-key.private.json`; do not copy them into prompts,
logs, docs or git. The installation restricts access to the account, SYSTEM and
Administrators. Keep host media/receipts private as well.

## Long Video Transcript/Summary Delivery

Observed failure: original download, ASR and summary succeeded, but the native
outgoing video's successful row was not available during the sender's initial
wait. The whole result entered `send_uncertain`. Although the video subsequently
arrived, its transcript and summary remained held.

The idle worker now performs one read-only reconciliation at a time:

- Only personal Windows WeChat uncertain file tasks are eligible. Respect
  exact-chat filters, paused tasks, changed execution generations and cooldowns.
- Require the original persisted send intent and its same-chat/self-sender
  binding. A file's existence or a recent outgoing row alone is not proof.
- Reuse exact native file verification. Remuxed videos must have identical
  video/audio stream hashes, not merely similar duration or appearance.
- Record confirmed file delivery and let the normal deferred sender send only
  the remaining transcript and summary. Never press Send again for uncertain
  video, reset its delivery key or rerun ASR to repair a delivery problem.
- Serialize receipt maintenance across workers. Recheck task status and
  generation under the queue lock before releasing the remainder, so a user
  pause during verification wins.
- Missing or mismatched evidence stays held, with a five-minute proof-read
  backoff. No new video upload is attempted.

Text receipts, files and source knowledge remain separate. This is not a
guarantee of arbitrary-length upload support; provider size limits, actual
transcodes and unavailable native cache need their own evidence-based handling.
Worker progress updates replace the private queue atomically after flushing
the complete new contents. Unlocked readers no longer observe a temporarily
empty queue during those updates; a failed replacement preserves the old file.

### Resource-Bound Transcription

A live follow-up exposed a separate delay: Whisper exhausted its assigned
GPU's available memory, fell back to CPU and spent over fifteen minutes in the
first 30-second decoding window. A read-only stack sample confirmed CPU decoding,
not a network wait or sender deadlock. The downloaded original and extracted WAV
were intact.

`wechat_voice_transcribe.py` now caps its own CPU inference pool at four threads
by default (`WECHAT_WHISPER_CPU_THREADS` overrides this). It restores the previous
thread count even on failure. GPU selection, model, timestamps and decoding
options are unchanged; it does not steal another GPU or terminate another
project's model. Regression tests cover both GPU-OOM fallback and CPU failure.
Do not reset a whole chat or rerun a download to repair a stalled ASR child.

## Repeated Microsoft Browser Tabs

The observed Edge tabs were MSN/captive-portal pages opened through Windows
NCSI, not a new LabCanvas research task. This can recur with restricted or
intercepted network probes. See [Microsoft KB 4494446](https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/internet-explorer-edge-open-connect-corporate-public-network).

`agentic_tools/wecom_agent/windows/Set-Tiny11PortalProbes.ps1` provides
`Status`, `Apply` and `Restore`, guarded by the expected guest hostname.
It backs up the two owned registry values before setting `NoActiveProbe=1`
and `DisablePassivePolling=1`. The current backup is
`C:\LabCanvas\BrowserRepair\ncsi-before.json`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\LabCanvas\BrowserRepair\Set-Tiny11PortalProbes.ps1 -Mode Status
# Use -Mode Apply for the dedicated messaging VM, or -Mode Restore to undo.
```

This is a dedicated-VM workaround, not a general Windows recommendation:
Microsoft warns that applications relying on NCSI may incorrectly act offline.
Verify actual HTTPS connectivity and native message delivery, not the taskbar
network icon. It does not bypass or fix an upstream quota/login requirement.
No firewall edits, network-service restart, client restart or logout is needed.
Close only the observed unwanted browser process after checking its tabs;
never kill all workstation browsers or install a periodic browser-killer.

## Validation and Operations

```bash
WECHAT_TINY11_DISABLE=1 WECHAT_WORKER_DISABLE_CODEX_IMAGE_READ=1 \
  PYTHONPATH=src python -m unittest discover -s tests -p 'test_wechat_tiny11*.py'
npm test
```

Regression coverage includes cross-chat/resource mismatches, source/transfer
checksums, native-to-projection IDs, WXGF decoding at native dimensions, no
Linux fallback for Windows images, missing/wrong-chat send intent, paused tasks,
concurrent pause during proof reading, and delivery without composing again.

Live verification on 2026-09-22 recovered the exact 780x1040 image and matched
its original message digest. Two completed approximately four-minute Channels
videos received delayed native receipt verification; their normal worker sent
the missing transcript/summary without uploading the videos again. Keep the
account/message IDs and actual receipts in ignored runtime evidence, not here.

Reload only idle personal-WeChat workers after validation. Their supervisor
reloads the same queue; preserve active tasks, cursors and client sessions.
The shared console remains `http://127.0.0.1:6143/`. LabAgent's user-requested
pause and Android no-control policy are unaffected.
