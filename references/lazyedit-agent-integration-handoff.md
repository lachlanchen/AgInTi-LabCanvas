# LazyEdit Agent Integration Handoff

Date: 2026-06-25

This note tells LabCanvas, WeChat chatops, Codex, and AgInTiFlow agents how to
use LazyEdit as the mature video correction, processing, and publishing tool.
Do not reimplement LazyEdit inside LabCanvas. LabCanvas agents should identify
the exact source video, prepare source-scoped context, call the LazyEdit CLI/API,
monitor the queues, and return artifacts or verified status.

## Source Of Truth

- LazyEdit repo: `/home/lachlan/DiskMech/Projects/lazyedit`
- Full LazyEdit handoff:
  `/home/lachlan/DiskMech/Projects/lazyedit/references/AGENT_HANDOFF_LAZYEDIT_PUBLISH_2026_06_25.md`
- LazyEdit workflow skill:
  `/home/lachlan/.codex/skills/lazyedit-publish-workflow/SKILL.md`
- LabCanvas repo-local skill:
  `agentic_tools/wechat_gui_agent/skills/lazyedit-publish-workflow/SKILL.md`
- LabCanvas generated-video routine:
  `agentic_tools/wechat_gui_agent/docs/GENERATED_VIDEO_ROUTINES.md`

## Responsibility Boundary

LazyEdit owns:

- upload/import into the local video library;
- transcription and subtitle polishing;
- context-aware subtitle correction;
- translation and subtitle burn;
- LazyEdit logo burn and Studio settings;
- metadata generation;
- cover extraction;
- browser-safe MP4/ZIP packaging;
- local publish queue submission.

Remote AutoPublish owns:

- Shipinhao/视频号 posting;
- YouTube posting;
- Instagram posting;
- remote platform login sessions and publish evidence.

LabCanvas and WeChat agents own:

- current-message permission checks;
- exact source video resolution from the same chat/source row;
- context collection for subtitle correction and metadata;
- calling LazyEdit through its mature CLI/API;
- polling local LazyEdit and remote AutoPublish queues;
- sending MP4/PDF/image/status artifacts back to the source chat.

## Normal Agent Flow

1. Confirm the current request asks for LazyEdit processing or public publish.
2. Resolve the exact video. Prefer current/quoted WeChat `local_id`, MD5, byte
   length, task artifact ledger, or an explicit absolute path. Never borrow a
   nearby old video or another chat's artifact.
3. Write `lazyedit_correction_context.md` in the worker artifact directory.
4. Write `lazyedit_metadata_brief.md` separately. Do not reuse full chat history
   or a full script as metadata.
5. Run `scripts/lazyedit_publish.py` from the LazyEdit repo under the
   `lazyedit` conda env.
6. Monitor local LazyEdit queue and remote AutoPublish queue until terminal
   evidence exists or a real blocker appears.
7. Return the final MP4/package/status to the source chat through the guarded
   WeChat artifact delivery gate.

## Subtitle Correction With Context

Subtitle correction is the main place where agents add value. The correction
context should be rich enough for LazyEdit to fix ASR mistakes without making up
unsupported dialogue.

Include useful source-scoped context:

- the current user request;
- the WeChat message sent with the video, including nearby text in the same
  coalesced request and quoted/source `local_id` rows;
- same-chat task summary for the exact generated/source video;
- for AI-generated videos, the generated story/script and the Xiaoyunque/Seedance
  prompt used to create the video;
- names, places, products, song titles, technical terms, and expected languages;
- visible filenames, URLs, captions, OCR, or transcript snippets;
- notes about what must not be changed.

Correction rules:

- Use the script or story as reference, not a verbatim transcript.
- Fix clear ASR errors, broken phrases, wrong names, wrong objects, wrong song
  lyrics, and context-inconsistent fragments.
- Read neighboring lines before changing text.
- Preserve timing and natural speech style where possible.
- Do not invent dialogue that the audio/video does not support.
- Do not overpatch one video with custom code. If subtitle rendering loses
  grammar colors, ruby, pinyin, romaji, or language separation, fix the shared
  LazyEdit subtitle pipeline.

Minimal correction prompt:

```markdown
# Subtitle Correction Context

Correct ASR subtitles for this video. Preserve timestamps and line structure as
much as possible.

Use the context below as background, not as a verbatim transcript. Fix clear
recognition errors, broken phrases, wrong names, wrong objects, song lyrics,
technical terms, and context-inconsistent fragments. Keep natural speech. Do not
invent unsupported content.

Important terms:
- ...

User/video context:
- ...

Reference story or prompt:
- ...
```

## Metadata Brief

Metadata should be short, public-facing, and platform-oriented. Do not pass the
full video script as metadata context.

Minimal metadata brief:

```markdown
# Metadata Brief

Create concise platform metadata. Use Traditional Chinese for Chinese metadata
unless the user requests otherwise.

Hook:
- ...

Characters / setting:
- ...

Core idea:
- ...

Tone:
- ...

Keywords / hashtags:
- ...

Do not reveal every scene beat. Do not copy the full script.
```

## CLI Pattern

Run from the LazyEdit repo:

```bash
cd /home/lachlan/DiskMech/Projects/lazyedit
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lazyedit
```

Correct/process without publishing when checking quality:

```bash
python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --correction-prompt-file /abs/lazyedit_correction_context.md \
  --metadata-prompt-file /abs/lazyedit_metadata_brief.md \
  --correct-subtitles \
  --correction-source polished \
  --no-publish \
  --guided-monitor \
  --wait \
  --poll-seconds 10 \
  --process-timeout 7200
```

Process and publish when the current request explicitly asks for public posting:

```bash
python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --correction-prompt-file /abs/lazyedit_correction_context.md \
  --metadata-prompt-file /abs/lazyedit_metadata_brief.md \
  --correct-subtitles \
  --correction-source polished \
  --platforms shipinhao,youtube,instagram \
  --guided-monitor \
  --remote-log-command "ssh lachlan@lazyingart 'tmux capture-pane -pt autopub:0 -S -160 | tail -n 160'" \
  --wait \
  --poll-seconds 10 \
  --process-timeout 7200 \
  --publish-timeout 7200
```

Reuse an already completed LazyEdit output only when the user asks for the same
version or no rerun:

```bash
python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --platforms shipinhao,youtube,instagram \
  --no-process \
  --guided-monitor \
  --wait \
  --poll-seconds 10 \
  --publish-timeout 7200
```

## Agent-Supervised Execution

Use Codex/AgInTi worker-agent supervision for generation and publication stages.
The agent should call mature routines, commands, and scripts; it should not
replace itself with pure deterministic branches.

Deterministic code is allowed for:

- exact-source isolation from WeChat rows, MD5, length, and artifact ledgers;
- duplicate-publish guards;
- queue timestamps and short status probes;
- terminal LazyEdit/AutoPublish verification;
- artifact delivery gates and retry state.

The resumed worker agent owns:

- deciding what source context is relevant and safe;
- ensuring the WeChat message sent with the video is included;
- adding generated story/script/prompt context for AI videos;
- invoking LazyEdit CLI/API with the right prompt files and platforms;
- repairing failed LazyEdit/browser states through existing scripts;
- producing the final user-facing explanation.

## Verification Contract

Before saying "published", verify:

- correct source video path, MD5/size/duration when available;
- corrected subtitle files exist or correction was intentionally skipped;
- metadata is concise and not a script dump;
- configured LazyEdit logo is used unless disabled by the user;
- final MP4 or package is browser-safe H.264/AVC, `yuv420p`, AAC, and faststart;
- for Instagram and other browser-upload platforms, the MP4 inside the ZIP is
  not HEVC/H.265 `hvc1`, AV1, or an unknown codec;
- local LazyEdit publish job is terminal;
- remote AutoPublish job is terminal for every requested platform;
- live browser evidence is inspected when the user reports a popup or queue
  state conflicts with the visible platform state;
- platform set matches the current request.

Queued, submitted, imported, processing, or running is not published.

## Failure Handling

- If LazyEdit exits 0 with no JSON payload, treat it as a failed submission and
  keep the queue stage pending for repair.
- If login, QR, CAPTCHA, payment, or credits block posting, move the task to
  `waiting_confirmation` with the same poststage preserved.
- If a silent video produces empty transcription and `burn=skipped`, continue
  metadata, cover, packaging, and publish verification when that matches the
  video content.
- If the selected MP4 is HEVC/H.265, AV1, or otherwise browser-risky, let
  LazyEdit transcode the publish bundle before AutoPublish receives it.
- If AutoPublish already extracted a stale HEVC/H.265 ZIP, rebuild the LazyEdit
  ZIP, verify the local and remote extracted MP4 are H.264/AVC `avc1`, then
  rerun only the failed platform. Do not republish unrelated successful
  platforms.
- If terminal evidence already exists for the same LazyEdit `video_id` and
  requested platforms, report verified status and do not publish again.

## Known Incident: Instagram HEVC False Success

On 2026-06-25, the video
`c05ffae4cac15cfb5f8abe6a8922c486_COMPLETED` first showed a remote queue
`done` state while Instagram displayed a publish error. The failed remote ZIP
contained an HEVC/H.265 `hvc1` `_highlighted.mp4`. Rebuilding through LazyEdit
produced a H.264/AVC `avc1` browser-safe MP4, and an Instagram-only retry
completed with live browser evidence: `Your reel has been shared.`

The detailed WeChat automation runbook is:

```text
agentic_tools/wechat_gui_agent/docs/LAZYEDIT_INSTAGRAM_CODEC_INCIDENT_2026_06_25.md
```

## Copy-Paste Agent Prompt

```text
Use LazyEdit as the mature video pipeline. Do not rebuild subtitle correction,
metadata generation, packaging, or public publishing in this repo.

Resolve the exact source video from the current request and same-chat/source
rows. Write a full correction context file and a separate short metadata brief.
Run /home/lachlan/DiskMech/Projects/lazyedit/scripts/lazyedit_publish.py from
the lazyedit conda env with --use-current-settings, correction prompt, metadata
brief, guided monitoring, and the requested platform set. Verify local LazyEdit
and remote AutoPublish terminal evidence before saying published. Send artifacts
or verified status back to the source chat.
```
