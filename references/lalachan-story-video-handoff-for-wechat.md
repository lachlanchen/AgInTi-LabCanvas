# LALACHAN Story, Video, Download, and Publish Handoff

Use this handoff when an agent, WeChat automation worker, or external tool needs to create a daily LALACHAN story, generate a Xiaoyunque video through the browser UI, download it, copy it to the repository or Nutstore, and optionally submit or publish through LazyEdit.

This workflow is intentionally browser-first. Do not use the Xiaoyunque API unless the human explicitly asks for API usage.

## Quick Operator Message

Send a worker a compact request like this:

```text
请完成今天的 LALACHAN 视频任务：
1. 写一个自然、好懂、有趣的中文故事，不要奇怪语言。
2. 保存故事到 references/stories/，保存小云雀提示词到 references/prompts/。
3. 用已登录 Chrome/CDP 的小云雀网页，不要用 API。
4. 上传实际图片文件，不要把路径粘进提示词。
5. 按需求选择模式、模型、时长、4:3，确认附件和提示词后只提交一次。
6. 监控到视频完成，下载 MP4，ffprobe 验证，复制到 Videos/。
7. 如果要求发布，用 LazyEdit 发布到指定平台；如果未要求发布，不要公开发布。
每一步都报告证据：故事路径、提示词路径、上传数量、模型/时长/比例、视频路径、发布 job id。
```

## Environment Contract

Prefer environment variables in reusable scripts and handoff docs:

```bash
export LALACHAN_ROOT="${LALACHAN_ROOT:-/home/lachlan/ProjectsLFS/LALACHAN}"
export LAZYEDIT_ROOT="${LAZYEDIT_ROOT:-/home/lachlan/DiskMech/Projects/lazyedit}"
export NUTSTORE_AUTOPUBLISH="${NUTSTORE_AUTOPUBLISH:-/home/lachlan/Nutstore Files/AutoPublish/AutoPublish}"
export XYQ_CDP_URL="${XYQ_CDP_URL:-http://127.0.0.1:9222}"
export LAZYEDIT_API="${LAZYEDIT_API:-http://127.0.0.1:18787}"
export AUTOPUBLISH_SSH="${AUTOPUBLISH_SSH:-lachlan@lazyingart}"
```

Never store tokens, cookies, or private chat logs in this document. Local machine paths are acceptable inside this private handoff, but public skills should replace them with variables.

## Repositories and Outputs

- LALACHAN repo: `$LALACHAN_ROOT`
- Story drafts: `$LALACHAN_ROOT/references/stories/`
- Xiaoyunque prompts: `$LALACHAN_ROOT/references/prompts/`
- Run logs/screenshots: `$LALACHAN_ROOT/outputs/xyq-YYYY-MM-DD-slug/`
- Final downloaded videos: `$LALACHAN_ROOT/Videos/`
- LazyEdit repo: `$LAZYEDIT_ROOT`
- Nutstore AutoPublish import folder: `$NUTSTORE_AUTOPUBLISH`
- LazyEdit CLI: `$LAZYEDIT_ROOT/scripts/lazyedit_publish.py`

Use stable filenames:

```text
references/stories/YYYY-MM-DD-short-slug.md
references/prompts/YYYY-MM-DD-short-slug-15s-seedance-fast.md
references/prompts/YYYY-MM-DD-short-slug-30s-mini.md
Videos/short_slug_15s_YYYY-MM-DD.mp4
Videos/short_slug_30s_YYYY-MM-DD.mp4
outputs/xyq-YYYY-MM-DD-short-slug/
```

## Default Characters and Reference Images

Always upload actual image files. Do not paste local paths into the Xiaoyunque prompt.

Default upload order:

1. `$LALACHAN_ROOT/words-card.jpg` - 小白屏学习卡 style reference. Create a fresh word for each episode.
2. `$LALACHAN_ROOT/LazyingArtRobot.png` - robot `庄子`; preserve the LazyingArt chest logo.
3. `$LALACHAN_ROOT/display.png` - LightMind AI glasses.
4. `$LALACHAN_ROOT/patchwork-leather-notebook-luxury-clean-v2.png` - handmade patchwork notebook/tool prop.
5. `$LALACHAN_ROOT/raraxia.jpeg` - 啦啦侠 individual reference.
6. `$LALACHAN_ROOT/ayachan.png` - 阿芽酱 individual reference.
7. `$LALACHAN_ROOT/sasakun.jpeg` - 飒飒君 individual reference.
8. `$LALACHAN_ROOT/Trio.png` - group relationship and identity reference.

Prompt labels must match upload order:

```text
图1: words card / 小白屏学习卡
图2: LazyingArtRobot / 庄子机器人
图3: LightMind AI 眼镜
图4: 拼皮笔记本
图5: 啦啦侠
图6: 阿芽酱
图7: 飒飒君
图8: 三人合照关系参考
```

If the user requests fewer or extra images, keep numbering accurate and state what changed.

## Story Generation Standard

Write the story first, then turn it into a compact video prompt.

Quality bar:

- Use normal, readable Chinese.
- Keep one clear chain: setup, problem, action, twist, payoff.
- Dialogue should sound like friends talking.
- Avoid pseudo-code, abstract slogans, stiff translation, over-explained lore, and strange AI-sounding phrases.
- Keep scene actions concrete and visible.
- For 15s, use 2-4 short beats and very few lines.
- For 30s, use 4 beats or one compact mini-story.
- If the scene is educational, show the concept through action and one plain sentence.
- If using `AgInTi`, capitalize it exactly as `AgInTi`.

Story file should include:

```markdown
# YYYY-MM-DD Title

## Short Story
...

## Dialogue
...

## Video Notes
- Duration:
- Ratio:
- Model target:
- Images:
- No subtitles:
```

## Words Card Rule

Every new episode should use a fresh word matching the story. The card is a physical scene prop, not subtitles.

Prompt pattern:

```text
图1 是小白屏学习卡风格参考，可作为场景边缘、桌面、道具架或角色背包上的小道具。
卡片内容是 English: WORD；Japanese: 日本語；Furigana: ふりがな；中文：中文含义。
它只是场景里的真实道具，不是字幕，也不是说明文字。
```

Two valid methods:

- Generate a new card image first with an image tool, then upload it as 图1.
- Upload `words-card.jpg` as a style reference and give Xiaoyunque the exact word content.

Use either method. Prefer a pre-generated card when text accuracy matters.

## Prompt Rules

The Xiaoyunque prompt should be compact and direct. Overpatched prompts often perform worse.

Must include:

- Duration and ratio.
- Model preference if specified.
- Image labels as 图1, 图2, etc.
- Character stability request.
- One clear story.
- No subtitles:

```text
不要字幕，不要生成任何字幕、说明文字、下三分之一文字、文件名或路径。
```

Never include:

- Local filesystem paths.
- Raw filenames as visible scene text.
- Full debug notes.
- Repeated model/cost warnings.
- A giant storyboard unless the user explicitly asks for a long-video plan.

## Xiaoyunque Browser Setup

Use the logged-in browser UI, not API.

Attach to the existing Chrome/CDP session:

```bash
cd "$LALACHAN_ROOT"
scripts/xyq_cdp_browser.py --cdp-url "$XYQ_CDP_URL" list-pages
scripts/xyq_cdp_browser.py --cdp-url "$XYQ_CDP_URL" bring-to-front PAGE_ID
scripts/xyq_cdp_browser.py --cdp-url "$XYQ_CDP_URL" visible PAGE_ID
```

If the browser is closed, launch the known Chrome profile/session with the local launcher:

```bash
scripts/xyq_chrome/launch_chrome.sh
scripts/xyq_cdp_browser.py --cdp-url "$XYQ_CDP_URL" list-pages
```

If Xiaoyunque opens but loads forever, refresh the same tab with `Ctrl+L` then `Enter`, or navigate the current page to the same URL. Do not open new tabs or new sessions unless the current thread is unusable.

## Mode, Model, Duration, Ratio

Default choices:

- Ratio: `4:3` unless the user asks otherwise.
- Duration: `15s` by default. Use `30s` only when requested.
- Mode: `沉浸式短片` for normal 15s videos.
- Longer video: use `创作 Agent` / integrated-agent when 30s cannot be set in short-film mode.
- Model: choose the cheapest suitable Seedance option allowed by the user.

Common model rules:

- If the user says `no VIP`, do not choose a paid VIP-only model.
- If the user asks for `Mini 体验版`, use `Seedance 2.0 Mini 体验版`.
- If `沉浸式短片` caps duration at 15s and the user needs 30s, switch to Agent/integrated workflow and set duration to 30s.
- If credits drop or a task is queued/running, do not resubmit.

Before paid submit, verify:

- Correct Xiaoyunque tab/thread.
- Correct mode/workflow.
- Correct selected model row.
- Correct duration.
- Correct ratio, especially `4:3`.
- Actual image attachment count and names are visible/successful.
- Prompt contains no local paths.
- Prompt includes no-subtitle instruction.
- Submit/send button is enabled.

## Upload Reference Images

Use the plus/upload controls or direct CDP file input. The important requirement is that the site receives real files.

```bash
scripts/xyq_cdp_browser.py --cdp-url "$XYQ_CDP_URL" upload-images-verify PAGE_ID \
  "$LALACHAN_ROOT/words-card.jpg" \
  "$LALACHAN_ROOT/LazyingArtRobot.png" \
  "$LALACHAN_ROOT/display.png" \
  "$LALACHAN_ROOT/patchwork-leather-notebook-luxury-clean-v2.png" \
  "$LALACHAN_ROOT/raraxia.jpeg" \
  "$LALACHAN_ROOT/ayachan.png" \
  "$LALACHAN_ROOT/sasakun.jpeg" \
  "$LALACHAN_ROOT/Trio.png" \
  --timeout 180 \
  --interval 2 \
  --screenshot "$LALACHAN_ROOT/outputs/xyq-run/after-upload.png"
```

Do not treat typed paths, pasted filenames, or prompt-only descriptions as uploads. If upload verification fails, stop before submitting.

## Fill Prompt and Submit

Fill the prompt:

```bash
scripts/xyq_cdp_browser.py --cdp-url "$XYQ_CDP_URL" type-prompt PAGE_ID "$LALACHAN_ROOT/references/prompts/PROMPT.md" --wait 2
```

Submit only once after the pre-submit contract is satisfied. If the user clicks or refreshes during the run, re-inspect the page state and continue from what the page actually shows. Do not assume the old state.

For Agent/integrated workflows, Xiaoyunque often pauses after storyboard/reference generation and asks for confirmation. Continue in the same thread:

```text
继续生成最终视频。保持30秒、4:3、当前模型，使用已上传参考图，不要字幕，不要说明文字，不要文件名或路径。
```

Do not start a new session just because it paused.

## Monitor Generation

Use the watcher first:

```bash
scripts/xyq_chrome/watch_thread_dom_download.py \
  --cdp-url "$XYQ_CDP_URL" \
  --page-id PAGE_ID \
  --thread-url "THREAD_URL" \
  --output-dir "$LALACHAN_ROOT/outputs/xyq-YYYY-MM-DD-slug" \
  --filename slug_30s_YYYY-MM-DD.mp4 \
  --copy-to "$LALACHAN_ROOT/Videos" \
  --interval 15 \
  --max-polls 240
```

Watch for:

- `生成中，大约还需...`
- `已完成`
- `积分不足` or `余额不足`
- login/CAPTCHA
- `内部错误`
- confirmation prompts

Stop only on a real blocker. If points drop and the job says running, monitor only.

## Download Final Video

Preferred watcher path:

- The watcher finds a downloadable URL or browser download.
- It writes the final MP4 under `outputs/xyq-.../`.
- It copies to `$LALACHAN_ROOT/Videos/`.

If watcher sees `完成` but no `<video>` tag:

1. Open the resource/artifact panel.
2. Click `视频` then `生成结果`.
3. Select `final_video.mp4`, not `S1.mp4`, `S2.mp4`, etc.
4. Open the preview.
5. Use the preview `下载` button or extract the preview `<video src=...>` URL from the logged-in page context.
6. Download that URL immediately; signed URLs can expire.

Example direct extraction after preview is open:

```bash
scripts/xyq_cdp_browser.py --cdp-url "$XYQ_CDP_URL" eval PAGE_ID \
  "(()=>[...document.querySelectorAll('video')].map(v=>v.currentSrc||v.src).filter(Boolean)[0]||'')()"
```

Then:

```bash
curl -L --fail --retry 2 --retry-delay 2 -A 'Mozilla/5.0' "$VIDEO_URL" \
  -o "$LALACHAN_ROOT/outputs/xyq-run/result.mp4"
cp -f "$LALACHAN_ROOT/outputs/xyq-run/result.mp4" "$LALACHAN_ROOT/Videos/result.mp4"
```

Verify every downloaded MP4:

```bash
ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=width,height,codec_name \
  -of json "$LALACHAN_ROOT/Videos/result.mp4"
```

For requested 15s/30s durations, accept within about 5 seconds unless the user asked for exact length.

## Copy to Nutstore

Use a stable `_COMPLETED` filename when triggering Nutstore AutoPublish:

```bash
cp -f "$LALACHAN_ROOT/Videos/result.mp4" \
  "$NUTSTORE_AUTOPUBLISH/result_COMPLETED.mp4"
```

Avoid repeatedly copying new filenames for the same video; that can create duplicate imports.

Monitor AutoPubMonitor if using Nutstore import:

```bash
tmux capture-pane -pt autopub-monitor:0.1 -S -100 | tail -n 100
tmux capture-pane -pt autopub-monitor:0.2 -S -100 | tail -n 100
curl -fsS "$LAZYEDIT_API/api/videos" | jq '.videos[:20] | map({id,title,created_at,file_path})'
```

## Submit to LazyEdit Without Public Publish

If the user asks for LazyEdit processing/import but not public publishing, use `--no-publish`:

```bash
cd "$LAZYEDIT_ROOT"
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lazyedit

python scripts/lazyedit_publish.py \
  --video "$LALACHAN_ROOT/Videos/result.mp4" \
  --title result_COMPLETED \
  --source lalachan-xyq \
  --expect-duration 30 \
  --duration-tolerance 5 \
  --expect-min-size-mb 1 \
  --use-current-settings \
  --correction-prompt-file "$LALACHAN_ROOT/references/prompts/PROMPT.md" \
  --metadata-prompt-file "$LALACHAN_ROOT/temp/metadata_brief.md" \
  --correct-subtitles \
  --correction-source polished \
  --no-publish \
  --wait \
  --poll-seconds 10
```

## Publish Through LazyEdit

Use LazyEdit CLI for real publishing so webapp state stays synchronized.

For a fresh generated video:

```bash
cd "$LAZYEDIT_ROOT"
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lazyedit

python scripts/lazyedit_publish.py \
  --video "$LALACHAN_ROOT/Videos/result.mp4" \
  --title result_COMPLETED \
  --source lalachan-xyq \
  --expect-duration 30 \
  --duration-tolerance 5 \
  --expect-min-size-mb 1 \
  --use-current-settings \
  --correction-prompt-file "$LALACHAN_ROOT/references/prompts/PROMPT.md" \
  --metadata-prompt-file "$LALACHAN_ROOT/temp/metadata_brief.md" \
  --correct-subtitles \
  --correction-source polished \
  --platforms youtube,instagram \
  --guided-monitor \
  --remote-log-command "ssh $AUTOPUBLISH_SSH 'tmux capture-pane -pt autopub:0 -S -120 | tail -n 120'" \
  --wait \
  --poll-seconds 10 \
  --process-timeout 3600 \
  --publish-timeout 7200
```

For all platforms:

```bash
--platforms shipinhao,youtube,instagram
```

For only YouTube and Instagram:

```bash
--platforms youtube,instagram
```

For only Shipinhao after the same video was already processed:

```bash
python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --platforms shipinhao \
  --no-process \
  --guided-monitor \
  --remote-log-command "ssh $AUTOPUBLISH_SSH 'tmux capture-pane -pt autopub:0 -S -120 | tail -n 120'" \
  --wait \
  --poll-seconds 10 \
  --publish-timeout 7200
```

Do not republish YouTube/Instagram when the user asks only for Shipinhao later.

## Metadata Brief

Do not pass the full script as metadata context. It creates long, storyboard-like post descriptions.

Create a short temporary metadata brief:

```markdown
# Metadata Brief

Hook: one sentence.
Characters and setting: short phrase.
Tone: warm, cute, funny, adventurous.
Central conflict/joke/emotion: one sentence.
Title style: short and viewer-facing.
Keywords/hashtags: 8-15 terms.
Instruction: do not reveal every beat or line of dialogue.
```

Use:

```bash
--correction-prompt-file "$LALACHAN_ROOT/references/prompts/PROMPT.md"
--metadata-prompt-file "$LALACHAN_ROOT/temp/metadata_brief.md"
```

The full prompt is for subtitle correction only. The metadata brief is for public title/caption/description.

## Subtitle Correction

For generated videos, treat the story/prompt as context, not a transcript.

Correct:

- clear ASR errors;
- wrong character names;
- broken phrases;
- obvious object/name mistakes.

Do not invent dialogue that is unsupported by the audio/video. If the video has little or no dialogue, empty or minimal subtitles are acceptable.

If publishing real platforms, inspect polished subtitles when context is precise:

```bash
sed -n '1,180p' "$LAZYEDIT_ROOT"/DATA/VIDEO_FOLDER/*_mixed_polished.md
```

## Monitor LazyEdit and Remote Publish

CLI with `--guided-monitor` is preferred. Additional checks:

```bash
curl -fsS "$LAZYEDIT_API/api/videos" | jq '.videos[:10] | map({id,title,created_at,file_path})'
curl -fsS "$LAZYEDIT_API/api/publish/jobs/JOB_ID" | jq .
ssh "$AUTOPUBLISH_SSH" 'tmux capture-pane -pt autopub:0 -S -140 | tail -n 140'
```

Final success requires:

- local LazyEdit publish job status `done`;
- remote AutoPublish status `done`;
- platform list matches the user request.

## Platform Caveats

YouTube:

- Wait for upload complete and checks complete.
- Select playlist/default audience as configured by AutoPublish.
- Metadata must be concise; no script dump.

Instagram:

- Use original crop when possible.
- Wait for publish confirmation.

Shipinhao:

- May show a login iframe and require manual login.
- If login is required, wait while the remote worker polls; it may send email.
- After login, verify upload preview ready, description set, collection selected, publish button enabled.
- Shipinhao short title field may not exist; skip it if absent.

## Recovery Rules

- If Xiaoyunque asks to continue after storyboard/reference generation, send a short continue message in the same thread.
- If Xiaoyunque output is complete but only S1/S2/S3/S4 clips are visible, switch artifact category to `生成结果` and download `final_video.mp4`.
- If direct signed media URL returns 404 outside the page, open preview and download from the logged-in browser context.
- If a browser session is broken, refresh same tab before opening a new session.
- If upload verification fails, do not submit.
- If credits were consumed or points dropped, do not resubmit automatically.
- If LazyEdit already processed the video and the user adds another platform later, use `--video-id VIDEO_ID --no-process`.
- If remote publish waits on login, report the blocker and keep monitoring if the user says they logged in.

## AgenticApp / WeChat Automation Contract

For WeChat automation, maintain a task record with these fields:

```json
{
  "task": "lalachan_daily_video",
  "story_path": "",
  "prompt_path": "",
  "xyq_thread_url": "",
  "xyq_page_id": "",
  "mode": "",
  "model": "",
  "duration": "",
  "ratio": "4:3",
  "uploaded_images": [],
  "output_video": "",
  "ffprobe": {},
  "nutstore_copy": "",
  "lazyedit_video_id": null,
  "publish_job_id": null,
  "remote_job_id": null,
  "platforms": [],
  "status": "draft|submitted|generating|downloaded|copied|processing|published|blocked|failed",
  "blocker": ""
}
```

The automation should post short status updates:

- `故事已保存: PATH`
- `提示词已保存: PATH`
- `已上传 8 张参考图，截图: PATH`
- `已提交小云雀: mode/model/duration/ratio`
- `视频已下载并验证: PATH, duration, size, resolution`
- `已复制到 Nutstore: PATH`
- `LazyEdit video_id=...`
- `Publish job=..., remote job=..., platforms=..., status=done`

## Final Report Template

```text
完成。

Story: PATH
Prompt: PATH
Video: PATH
ffprobe: DURATION, SIZE, WIDTHxHEIGHT, CODECS
Xiaoyunque: MODE, MODEL, DURATION, RATIO
LazyEdit: video_id=...
Publish: job=..., remote=..., platforms=..., status=done
Notes/blockers: none
```

## Hard Safety Rules

- Do not use Xiaoyunque API unless explicitly requested.
- Do not submit paid generation twice without proof the first attempt failed without charging.
- Do not paste local paths into Xiaoyunque prompts.
- Do not skip image upload.
- Do not publish to platforms not requested.
- Do not use the full script as public metadata.
- Do not end the task while required watcher or publish processes are still running.
