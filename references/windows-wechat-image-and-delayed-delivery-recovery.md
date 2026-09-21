# Windows WeChat Images and Delayed Video Delivery

Updated: 2026-09-22

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
5. Decode with the separately installed upstream decoder. Normal intake uses
   a cached private key; it does not scan process memory or manipulate the GUI.
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
