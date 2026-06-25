---
name: lazyedit-publish-workflow
description: Publish videos through LazyEdit, AutoPubMonitor, Nutstore AutoPublish, Shipinhao, YouTube, and Instagram from LabCanvas or WeChat worker tasks.
---

# LazyEdit Publish Workflow

This repo-local skill mirrors the LazyEdit publish skill from
`/home/lachlan/DiskMech/Projects/lazyedit/references/skills/lazyedit-publish-workflow/SKILL.md`
and the active Codex skill. Use it when a WeChat/LabCanvas task asks to publish,
re-publish, import, process, subtitle, or monitor a video.
For LabCanvas-specific agent boundaries, also read
`references/lazyedit-agent-integration-handoff.md`. The full LazyEdit-side
handoff is
`/home/lachlan/DiskMech/Projects/lazyedit/references/AGENT_HANDOFF_LAZYEDIT_PUBLISH_2026_06_25.md`.

## Runtime Map

- LazyEdit repo/backend: `/home/lachlan/DiskMech/Projects/lazyedit`
- Studio app: `http://127.0.0.1:18791/editor`
- LazyEdit API: `http://127.0.0.1:18787`
- Publish CLI: `scripts/lazyedit_publish.py`
- AutoPubMonitor repo: `/home/lachlan/DiskMech/Projects/autopub-monitor`
- Nutstore import folder: `/home/lachlan/Nutstore Files/AutoPublish/AutoPublish`
- Remote AutoPublish host: `ssh lachlan@lazyingart`
- Remote publish API: `http://lazyingart:8081/publish`
- Remote tmux session: `autopub`

## Core Rule

Prefer the LazyEdit CLI over manual browser work. It creates normal LazyEdit
jobs, keeps the web queue in sync, and provides stable monitoring output.
LazyEdit is the mature downstream video tool: do not rebuild subtitle
correction, translation, metadata, logo/subtitle burn, browser-safe packaging,
or platform posting in LabCanvas. LabCanvas agents prepare exact source video
evidence plus context files, call LazyEdit, monitor terminal evidence, and send
artifacts/status back to WeChat.

```bash
cd /home/lachlan/DiskMech/Projects/lazyedit
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lazyedit
```

## Safety Rules

- Use `--no-publish` before a real publish when testing packaging, subtitles, or
  logo output.
- Publish exactly once after the final MP4/ZIP is correct. When the user
  explicitly asks to publish, `--no-publish` is only a temporary quality gate;
  continue to the real publish automatically unless login, CAPTCHA, payment,
  consent, or another manual block prevents it.
- Real publishes should use polished subtitles and the configured LazyEdit logo
  unless the user explicitly says otherwise.
- Verify logo settings before publish:

```bash
curl -fsS http://127.0.0.1:18787/api/ui-settings/logo_settings | jq .
```

- Normal logo outputs end in `_subtitles_logo.mp4`.
- Use `--correction-prompt-file` for full transcript/story context and
  `--metadata-prompt-file` for a short public-facing brief. Do not pass a full
  script as metadata context.
- Generated-video LazyEdit runs must prefer the worker-created
  `lazyedit_correction_context.md` and `lazyedit_metadata_brief.md` from
  `task.preflight.lazyedit_context`; story/prompt files from the browser monitor
  are fallback only.
- The correction context must include the WeChat message sent with the video.
  For AI-generated video publication, append the generated story/script and
  Xiaoyunque/Seedance prompt before calling LazyEdit.
- Use the resumed Codex/AgInTi worker agent to call routines, scripts, and CLI
  commands. Deterministic code may isolate sources, guard duplicates, probe
  status, verify terminal evidence, and enforce artifact delivery, but it must
  not become a separate hardcoded publishing workflow.
- Silent or nearly silent videos may produce empty transcripts and
  `burn=skipped`. This is acceptable when transcribe/translate/caption/keyframes
  are complete; continue metadata generation, cover extraction, publish queue
  submission, and terminal platform verification instead of waiting forever or
  swapping in an older video.
- AutoPublish browser uploads require a web-safe MP4 inside the ZIP. LazyEdit
  must package `_highlighted.mp4` as H.264/AVC (`avc1`), `yuv420p`, AAC audio,
  and `+faststart`. If the selected source/burn output is HEVC/H.265, AV1, or
  another browser-risk codec, transcode it during publish-bundle preparation
  before sending the ZIP.
- Do not commit generated ZIPs, runtime media, temporary prompts, cookies, or
  queue snapshots.

## WeChat Video Import

For a video shared in a monitored WeChat group or DM, first copy the same-chat
source into the Nutstore AutoPublish watcher:

```bash
PYTHONPATH=src python -m agenticapp wechat autopublish-video \
  --chat "<chat>" \
  --message-local-id VIDEO_LOCAL_ID \
  --sync \
  --fetch-gui \
  --since-minutes 720 \
  --json
```

This opens the isolated WeChat desktop when needed, clicks the latest visible
video so WeChat caches the MP4, syncs media, and atomically writes a
`*_COMPLETED` file into the Nutstore watcher. Use `--list --json` to inspect
candidates and `--source /abs/video.mp4` when the exact source file is known.
When a task references a specific WeChat video row, always pass
`--message-local-id`; this prevents a nearby older cached MP4 from being copied
or published by mistake. If the exact row cannot be cached, fail closed and ask
for a resend or a GUI cache retry rather than falling back to another video.

After import, find the LazyEdit `video_id`:

```bash
tmux capture-pane -pt autopub-monitor:0.1 -S -100 | tail -n 100
tmux capture-pane -pt autopub-monitor:0.2 -S -100 | tail -n 100
curl -fsS http://127.0.0.1:18787/api/videos | jq '.videos[:20] | map({id,title,created_at,file_path})'
```

## WeChat Context To Subtitle Correction

When the publish request comes from WeChat, preserve the full source-scoped task
packet generated by the monitor:

- current coalesced request;
- quoted message text;
- recent same-chat history;
- source/reference `local_id` rows;
- visible media metadata such as title, filename, URL, MD5, and video row;
- synced file paths from `.private/downloads/<chat>/...`.

Write that context under the worker artifact directory, for example
`lazyedit_correction_context.md`, and pass it as `--correction-prompt-file`.
Use it to fix names, terminology, and obvious ASR mistakes. Do not invent lines
that are unsupported by the audio/video or chat context.

Create a separate short file, for example `lazyedit_metadata_brief.md`, for
viewer-facing title, description, keywords, and platform notes. Pass that file
as `--metadata-prompt-file`. Never reuse the full chat history or full script as
metadata context.

## Process Then Publish

Use separate subtitle-correction and metadata context files:

```bash
python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --correction-prompt-file /abs/full_context.md \
  --metadata-prompt-file /abs/metadata_brief.md \
  --no-correct-subtitles \
  --steps keyframes,caption,transcribe,polish,translate,burn,metadata_zh,metadata_en,cover \
  --platforms shipinhao,youtube,instagram \
  --guided-monitor \
  --remote-log-command "ssh lachlan@lazyingart 'tmux capture-pane -pt autopub:0 -S -140 | tail -n 140'" \
  --wait \
  --poll-seconds 10 \
  --process-timeout 3600 \
  --publish-timeout 7200
```

For direct upload from a local MP4:

```bash
python scripts/lazyedit_publish.py \
  --video /abs/video.mp4 \
  --title TITLE_COMPLETED \
  --use-current-settings \
  --correction-prompt-file /abs/full_context.md \
  --metadata-prompt-file /abs/metadata_brief.md \
  --correct-subtitles \
  --correction-source polished \
  --platforms shipinhao,youtube,instagram \
  --wait \
  --poll-seconds 10
```

## Publish Existing Output

Use `--no-process` when the user says "same output", "last run", or the final
processed video already exists:

```bash
python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --platforms shipinhao,youtube,instagram \
  --no-process \
  --wait \
  --poll-seconds 10
```

Platform-only variants:

```bash
python scripts/lazyedit_publish.py --video-id VIDEO_ID --use-current-settings --platforms shipinhao --no-process --wait --poll-seconds 10
python scripts/lazyedit_publish.py --video-id VIDEO_ID --use-current-settings --platforms youtube,instagram --no-process --wait --poll-seconds 10
```

## Context Files

Subtitle correction context may include the full story, transcript, prompt, or
user notes. Treat it as evidence, not a verbatim script: fix obvious ASR errors,
names, objects, and broken phrases without inventing unsupported dialogue.

Metadata context should be short and public-facing:

- one hook sentence
- characters and setting
- central conflict, joke, or emotion
- desired title tone
- 8 to 15 keywords or hashtags
- instruction not to reveal every beat or line

## Manual Subtitle Quality Pass

Before real publish, inspect polished subtitles when precise context exists:

```bash
sed -n '1,180p' DATA/VIDEO_FOLDER/*_mixed_polished.md
rg -n "bad term|broken term|ASR artifact" DATA/VIDEO_FOLDER/*_mixed_polished.*
```

Keep `.json`, `.srt`, and `.md` aligned if hand-editing. Prefer LazyEdit save
endpoints when available; use database recovery only for clear duplicate-worker
status corruption.

## Monitoring

Local LazyEdit queue:

```bash
curl -fsS http://127.0.0.1:18787/api/autopublish/queue | jq '.jobs[:8] | map({id,video_id,status,platforms,remote_status,remote_job_id,error})'
```

Remote AutoPublish queue:

```bash
curl -fsS http://lazyingart:8081/publish/queue | jq '.jobs[:8] | map({id,status,platforms,filename,error,updated_at})'
```

Remote browser automation:

```bash
ssh lachlan@lazyingart 'tmux capture-pane -pt autopub:0 -S -120 | tail -n 120'
```

AutoPubMonitor panes:

```bash
tmux capture-pane -pt autopub-monitor:0.0 -S -120 | tail -n 120
tmux capture-pane -pt autopub-monitor:0.1 -S -120 | tail -n 120
tmux capture-pane -pt autopub-monitor:0.2 -S -120 | tail -n 120
tmux capture-pane -pt autopub-monitor:0.3 -S -120 | tail -n 120
```

## Shipinhao Notes

- Shipinhao may require WeChat QR or email login. Keep the long wait running
  after the user scans.
- Expected success log includes `Successfully published on ShiPinHao.`
- Do not bypass CAPTCHA, login, or consent pages. Open the isolated browser for
  human assistance and ask the user to approve continuation.

## Recovery Checks

If processing appears stuck, inspect processes before killing anything:

```bash
ps -eo pid,ppid,cmd | rg 'vad_lang_subtitle|HandBrakeCLI|scripts/lazyedit_publish.py'
```

Only stop a duplicate worker when it is clearly redundant and a valid completed
output exists. Then confirm queue state before publishing.

## Handoff Report

Final status back to WeChat or the terminal should include:

- LazyEdit job id
- remote job id, if any
- platforms
- current status or blocking human step
- whether processing was reused or rerun
- output MP4/ZIP paths only when safe to share
