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
   - One request owns one active Xiaoyunque `thread_id` until the MP4 is
     downloaded and delivered, unless the current chat message explicitly asks
     to start a new/continued generation. If the thread already shows
     `final_video.mp4` or `渲染合成最终视频 ... 已完成`, the only valid next stage is
     download and delivery.
   - Continuation: when a Xiaoyunque probe contains `请确认` plus
     `继续帮您生成视频`, use `xyq_continue_thread.py` to send the approval into the
     same `thread_id`. The helper uses the browser send button and, when
     `XYQ_ACCESS_KEY` is available, also submits the same continuation through
     Xiaoyunque OpenAPI so the underlying run advances. This is not a public
     action and should not require manual WeChat approval when the current
     request already asked for video generation.
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
   - Timeout/running state: `generation_poststage_pending` with `next_poststage_at`.

6. `public_publish`
   - Owner: queue orchestrator via LazyEdit.
   - Entrypoint: `run_generated_video_lazyedit_command(..., publish=True)`.
   - Requirement: current request explicitly permits public publish and names or
     implies platforms. Old chat history cannot authorize posting.
   - Existing generated videos quoted later are resolved by exact WeChat video
     MD5/length against same-chat task artifacts, then copied to AutoPublish
     with the original source task summary passed into LazyEdit prompt files.
   - “Queued”, “submitted”, “running”, or “imported” are not “published”.
     Existing-video publish work uses `publish_poststage_pending` until all
     requested platforms have terminal LazyEdit/remote evidence or public URL
     proof.

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
