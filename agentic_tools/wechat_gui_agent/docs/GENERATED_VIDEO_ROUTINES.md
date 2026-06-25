# Generated Video Routines

This workflow is a fixed orchestration routine for WeChat-triggered LALACHAN,
Xiaoyunque, LazyEdit, and public publishing tasks. Agents should supervise the
routine and resolve blockers; they should not invent a new path when a stage
already has an entrypoint.

The general routine registry is `agentic_tools/wechat_gui_agent/scripts/wechat_routines.py`
and the operator guide is `docs/ROUTINE_ORCHESTRATOR.md`. This document is the
specialized stage contract for the `generated_video` routine. The short
operational checklist for autonomous agents is
`docs/AGENT_ROUTINE_CHEAT_SHEET.md`.
The end-to-end LALACHAN operator handoff is documented in
`references/lalachan-story-video-handoff-for-wechat.md`. It is the canonical
guide for story quality, Xiaoyunque browser operation, reference-image upload
order, monitoring, MP4 download, repo/Nutstore copy, and when to enter
LazyEdit.
The LazyEdit boundary and agent handoff are documented in
`references/lazyedit-agent-integration-handoff.md`. LazyEdit is the mature tool
for subtitle correction, metadata, logo/subtitle burn, browser-safe packaging,
and AutoPublish submission; LabCanvas agents should provide exact inputs and
supervise the routine, not rebuild those functions.
For generation and publication, use the resumed Codex worker agent to call the
routine scripts/commands. Deterministic code is limited to source isolation,
duplicate guards, queue timestamps, short probes, terminal verification, and
artifact delivery gates.

Core boundary: generation is not publication. Generation means story/prompt
creation, Xiaoyunque submission, monitoring, MP4 download, verification, and
WeChat send-back. Publication means posting to public platforms such as
Shipinhao/视频号, YouTube, Instagram, or public AutoPublish queues, and it is
allowed only when the current request explicitly asks for public publish/post.
Uploading reference images/assets into Xiaoyunque is part of generation, not
publication.

## Routine Stages

1. `route_contract`
   - Owner: fast chat agent.
   - Entrypoint: `prepare_worker_preflight()` and `write_generated_video_contract()`.
   - Output: `generated_video_route_contract.json` and `.md` with current-request
     permissions only.

2. `story_and_prompt`
   - Owner: worker agent.
   - Entrypoint: `run_worker_codex_once()` with the LALACHAN/Xiaoyunque tool
     context.
   - Output: story markdown, prompt markdown, upload evidence, and either
     submitted monitor state or a verified MP4.
   - Interruption rule: newer same-chat story/video messages are appended to
     `task.interruptions` and requeue the same task. The resumed worker agent
     must read the full interruption packet, revise the story/prompt, send the
     updated story to the group, and confirm before video generation unless the
     latest messages clearly authorize generation.
   - Approval transition: when the updated story is sent as
     `waiting_confirmation`, `labcanvas wechat approve TASK_ID --note "story ok
     generate video now"` promotes the same queue row from
     `story_script_generation` to `generated_video`. The approved story message,
     story file paths, and confirmation text are preserved on
     `story_confirmation_result` / `approved_story_*` and must be used as the
     Xiaoyunque prompt source.
   - Recency rule: an interruption can only attach to a recent active
     story/video task. The default maximum target age is 12 hours
     (`WECHAT_WORKER_INTERRUPT_TARGET_MAX_AGE_SECONDS` and
     `WECHAT_DIRECT_INTERRUPT_TARGET_MAX_AGE_SECONDS`). Older generation jobs
     stay paused/stale and new story requests become their own tasks.
   - Model policy: model selection must not block the task. Choose a relatively
     cheaper suitable Seedance option from the page and proceed. Prefer
     `Seedance 2.0 Mini 体验版` / `vipnew` with a visible cheap rate such as
     `单秒限时低至4积分`; otherwise use the relatively cheaper suitable `Fast`,
     `Fast VIP`, or available Seedance row. Pause only for real non-model
     blockers such as no credits, recharge/payment approval, disabled submit,
     login, CAPTCHA, or an explicit user budget limit.

3. `xyq_deterministic_monitor`
   - Owner: queue orchestrator.
   - Entrypoint: `deterministic_generated_video_continue_result()` when the
     thread asks for storyboard/reference confirmation, then
     `deterministic_generated_video_monitor_result()`.
   - Output: downloaded MP4, or `generation_waiting` with `next_poll_at`.
   - Long renders wait through queue state and CDP probes, not a multi-hour model
     call.
   - Paid action idempotence: one logical WeChat request owns at most one paid
     Xiaoyunque/Seedance thread. If the task already has
     `generated_video_monitor.thread_url`, `generated_video_submit_probe`,
     `credit_guard`, `route_decision.no_new_xyq_submit`, or
     `monitor_only_no_resubmit`, the worker must not submit, continue, retry, or
     create another paid generation. It may only monitor, download, verify, and
     send back the existing thread result. A new paid rerun requires a fresh
     current-message instruction that explicitly says to start a new paid rerun.
   - Existing-MP4 shortcut: before any continuation, browser monitor, submit
     helper, or resumed Codex worker runs, the queue checks
     `generated_video_monitor.output_dir` plus the configured `filename`. If the
     MP4 already exists, `deterministic_existing_generated_video_file_result()`
     returns that file through the artifact delivery gate and records
     `existing_generated_video_artifact`; no model or paid action is invoked.
   - One request owns one active Xiaoyunque `thread_id` until the MP4 is
     downloaded and delivered, unless the current chat message explicitly asks
     to start a new/continued generation. If the thread already shows
     `final_video.mp4` or `渲染合成最终视频 ... 已完成`, the only valid next stage is
     download and delivery.
   - If a newer same-chat interruption says the story is wrong, asks for a
     revision, or says the website generation was stopped/cancelled, do not
     treat the stale submitted run as success. Re-enter `story_and_prompt` and
     continue from the latest confirmed stage.
   - If a newer same-chat/operator note says the owner already downloaded one
     or more XYQ outputs, for example two videos in the same Xiaoyunque session,
     to `Downloads` and handed them to LazyEdit/publication, record a
     `manual_generated_video_handoff` and stop automation for that session. Do
     not reopen XYQ, redownload, resubmit, continue, import, or publish unless a
     later explicit request asks the automation to take over again.
   - Continuation: when a Xiaoyunque probe contains `请确认` plus
     `继续帮您生成视频`, use `xyq_continue_thread.py` to send the approval into the
     same `thread_id`. The helper uses the browser send button and, when
     `XYQ_ACCESS_KEY` is available, also submits the same continuation through
     Xiaoyunque OpenAPI so the underlying run advances. This is not a public
     action and should not require manual WeChat approval when the current
     request already asked for video generation.
   - Continuation prompt source: if the active task has same-chat interruptions,
     the continuation prompt must include the latest group instructions. Do not
     send a generic “current storyboard is OK” message when the user has revised
     the story. If the story was shown in the group and the latest user message
     confirms it, the continuation/prompt must use that approved story plus any
     later constraints.
     the story, stopped a run, or corrected the desired direction.
   - Duration check: if the current request asks for a duration such as 30s,
     accept the verified MP4 when `ffprobe` shows it is within 5 seconds of the
     request, unless the request explicitly says the duration must be exact.
   - Credit block: if the watcher or API-visible run reports `积分不足` or
     `余额不足`, stop polling and move the task to `waiting_confirmation` with a
     clear recharge/shorter-budget request only when no completed MP4 is visible
     in the same thread. A completed `final_video.mp4` wins over later stale
     credit text from accidental retries.

4. `wechat_artifact_delivery_gate`
   - Owner: queue orchestrator and GUI sender.
   - Entrypoint: `send_result_with_retries()` and `apply_send_outcome()`.
   - Requirement: the MP4 must be sent to the source WeChat chat and recorded in
     `sent_file_paths`.
   - Failure state: `send_deferred_artifact` or `send_deferred_locked`.
   - No LazyEdit or public publishing poststage may start before this gate passes.
   - The same required-media gate applies when an MP4/audio file is returned by
     a file-save/download route; use `labcanvas wechat worker repair-artifacts`
     to requeue older rows that lack `sent_file_paths`.
   - Follow-up file-save/download requests for an already generated video first
     resolve the newest bounded-age same-chat MP4 from worker artifacts and
     attach that file back to the chat. This avoids repeating Xiaoyunque
     generation or sending a stale AutoPublish cache video.

5. `lazyedit_poststage`
   - Owner: queue orchestrator.
   - Entrypoint: `deterministic_generated_video_poststage_result()`.
   - Requirement: current request explicitly permits LazyEdit import/process.
   - Handoff: follow `references/lalachan-story-video-handoff-for-wechat.md`
     for generated-video artifact provenance and
     `references/lazyedit-agent-integration-handoff.md` for LazyEdit command
     details.
   - Timeout/running state: `generation_poststage_pending` with `next_poststage_at`.
   - Context files: write `lazyedit_correction_context.md` from same-chat
     source rows, the WeChat message sent with the video, the current request,
     exact media metadata, and safe source-task summaries. For AI-generated
     video publication, append the generated story/script and Xiaoyunque/Seedance
     prompt before calling LazyEdit. Write
     `lazyedit_metadata_brief.md` separately with only hook, characters,
     tone, keywords, and platform notes. The correction context can be rich;
     the metadata brief must stay concise.
   - Generated-video LazyEdit commands must always pass context files when
     `--correct-subtitles` is used. If preflight did not create
     `lazyedit_context`, `run_generated_video_lazyedit_command()` creates
     fallback `lazyedit_correction_context.md` and `lazyedit_metadata_brief.md`
     in the task artifact directory from the current request, approved story,
     and same-chat interruption packet.

6. `public_publish`
   - Owner: queue orchestrator via LazyEdit.
   - Entrypoint: `run_generated_video_lazyedit_command(..., publish=True)`.
   - Requirement: current request explicitly permits public publish and names or
     implies platforms. Old chat history cannot authorize posting.
   - Third-party consent: if the source user asks another participant whether the
     video may be posted, such as `@A 可以发到视频号吗？` or `@A can I publish this?`,
     the monitor creates a `waiting_confirmation` publish task with
     `public_publish_allowed=false`. A later clear affirmative reply from a
     different same-chat participant reactivates that exact task as `pending`
     with `public_publish_allowed=true`; a denial cancels it. The system must not
     publish from the permission question alone.
   - Existing generated videos quoted later are resolved by exact WeChat video
     MD5/length against same-chat task artifacts, then copied to AutoPublish
     with the original source task summary passed into LazyEdit prompt files.
   - LazyEdit owns subtitle correction, translation, logo/subtitle burn,
     metadata, cover extraction, ZIP/MP4 packaging, and local publish queue
     submission. The worker must call LazyEdit and monitor it instead of
     hand-editing subtitles, manually building publish ZIPs, or driving platform
     browsers directly.
   - Browser-platform packages must be codec-verified before a publish is called
     done. The MP4 inside the LazyEdit ZIP must be H.264/AVC `avc1`, `yuv420p`,
     AAC audio when audio exists, and faststart. HEVC/H.265 `hvc1`, AV1, or
     unknown codecs are repairable packaging failures; rebuild through LazyEdit
     before posting. See
     `docs/LAZYEDIT_INSTAGRAM_CODEC_INCIDENT_2026_06_25.md`.
   - Queue `done` is not enough when the user reports a platform popup. For
     Instagram, inspect live browser evidence: `Your reel has been shared.` is
     success; visible error text overrides LazyEdit or AutoPublish queue state.
   - The resumed Codex worker owns context selection and command invocation. The
     queue orchestrator may probe, requeue, de-duplicate, and verify terminal
     evidence, but it should not replace the agent with a new hardcoded publish
     workflow.
   - LazyEdit execution must use `source ... && conda activate lazyedit &&
     python scripts/lazyedit_publish.py ... --json`; an empty JSON payload after
     zero exit means the publish command did not actually submit a job.
   - Probe for an already verified LazyEdit/remote job before issuing a new
     existing-video public publish. If the same `video_id` and requested
     platforms are already terminal-verified, report that evidence and skip the
     duplicate publish command.
   - “Queued”, “submitted”, “running”, or “imported” are not “published”.
     Existing-video publish work uses `publish_poststage_pending` until all
     requested platforms have terminal LazyEdit/remote evidence or public URL
     proof.
   - After terminal evidence exists, the outbox still owns WeChat completion
     delivery. If desktop GUI send is blocked by a blank title guard or timeout,
     a verified text-only completion may use the Android ADB fallback, but only
     after screenshot OCR matches the exact source chat title.

## State Rules

- `generation_waiting`: browser job submitted or still rendering; monitor again
  later. This is silent by default; do not send repeated progress messages.
- `send_deferred_artifact`: backend work is complete but the MP4 has not reached
  WeChat; resend before continuing.
- `send_deferred_locked`: WeChat GUI is locked, or the serialized send lane was
  busy/timed out while another file/video send was active; retry after normal
  unlock or after the active send finishes.
- `generation_poststage_pending`: MP4 was delivered and LazyEdit/public publish
  is queued or still running. This is silent by default unless a human decision
  is required.
- `publish_poststage_pending`: an existing quoted/generated video is in
  LazyEdit/public publish verification; deterministic probes and the resumed
  chat worker session continue until terminal proof or repairable failure. This
  is silent by default; do not post each poll result into WeChat.
- `done`: only after the requested current-message stages have completed.

The WeChat group is a command mirror. The durable system is the monitor, queue,
session registry, deterministic routines, and worker supervisor.
