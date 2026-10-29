# Channels transcription and retry recovery

## Symptoms and cause

A healthy WeChat message cursor and an empty worker queue do not prove that
every requested artifact was produced. In this incident the client remained
logged in and all seven monitors were caught up, but two Channels tasks had
failed transcription preflights. Their agents subsequently returned the original
videos and summaries without the expected transcript files.

The worker restricted the transcription child to physical GPU 1 with
`CUDA_VISIBLE_DEVICES=1`, while its inherited Whisper setting requested
`cuda:1`. CUDA renumbers a single visible device to `cuda:0`. Model loading
therefore failed with an invalid device ordinal. Trying a smaller model on the
same invalid ordinal could not fix it.

## Runtime contract

- `WECHAT_SHIPINHAO_CUDA_DEVICE` selects the physical GPU exposed to the child.
- When exactly one GPU is exposed, a CUDA Whisper request is normalized to
  `cuda:0` inside that child. Explicit CPU execution is preserved.
- The host environment is not modified. Other projects' GPU processes are not
  stopped, and no driver restart is required for this fix.
- Recover a task through its exact card identity and original source manifest.
  Never use a screen recording or nearby video as a substitute.

## Retrying without duplicate delivery

Use the existing media transcriber and keep its result in the task's canonical
`shipinhao_media_transcript/manifest.json`. Pass a recovered native share link
through `--recovered-share-url`, not by appending it after Finder XML.

Result preparation now reconciles a successful canonical retry when the queued
preflight still records failure. Acceptance requires the same expected object
ID, verified content identity (or a matching normalized embedded-media URL
digest from that exact task), a supported exact-source input kind, readable
delivery media, and a successful transcription or verified-silent result.
Failed, missing-media, unverified, and wrong-card manifests are rejected.

Reconciliation supplies the safe transcript artifact and refreshes source
knowledge. It reuses an already-sent video path only when its bytes match the
recovered original. Existing delivery receipts suppress repeated messages and
files. A stored-result repair does not rerun the agent or public publication:

```bash
PYTHONPATH=src python3 -m agenticapp wechat worker repair-result TASK_ID
PYTHONPATH=src python3 -m agenticapp wechat worker repair-result TASK_ID --send
```

Inspect the prepared result and existing receipts before the live repair. A
successful send must also appear in the native source history. Keep source IDs,
share URLs, raw chat content, media, and delivery evidence in ignored private
storage, not this runbook.

## Verification

The worker, direct-message monitor, completion auditor, transport guard, GUI
sender, and media-transcriber regression suites passed 1,025 tests. New cases
cover physical/logical GPU mapping, CPU preservation, successful retry
reconciliation, already-delivered video reuse, and rejection of unrelated or
failed manifests.

Two live original-video tasks were transcribed and repaired through the normal
sender. Native history recorded exactly two additional transcript attachments,
without repeated videos or summary messages. Both transcripts entered the
source-knowledge store.

## Remaining host limitation

The loaded NVIDIA module and installed NVML library have different versions.
A small CUDA matrix operation succeeded, but loading the full Whisper model
failed inside the native allocator's NVML initialization. A process-local test
with CUDA's asynchronous allocator exposed insufficient free GPU memory instead;
it was not installed as a global workaround. The existing CPU fallback completed
both live transcriptions but was slower than GPU execution. Do not restart the
host, replace driver libraries, kill another project's model, or claim GPU
throughput is restored on the strength of a small CUDA probe.

PyTorch documents process-level allocator selection in its
[CUDA memory-management guide](https://docs.pytorch.org/docs/stable/notes/cuda).

The live client was not restarted. EchoMind schedules remain disabled and
WeCom remains paused. These repairs do not authorize automatic publication of
ordinary inbound videos.
