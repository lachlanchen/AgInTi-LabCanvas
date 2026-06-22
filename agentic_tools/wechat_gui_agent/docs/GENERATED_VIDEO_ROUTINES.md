# Generated Video Routines

This workflow is a fixed orchestration routine for WeChat-triggered LALACHAN,
Xiaoyunque, LazyEdit, and public publishing tasks. Agents should supervise the
routine and resolve blockers; they should not invent a new path when a stage
already has an entrypoint.

The general routine registry is `agentic_tools/wechat_gui_agent/scripts/wechat_routines.py`
and the operator guide is `docs/ROUTINE_ORCHESTRATOR.md`. This document is the
specialized stage contract for the `generated_video` routine.

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
   - Entrypoint: `deterministic_generated_video_monitor_result()`.
   - Output: downloaded MP4, or `generation_waiting` with `next_poll_at`.
   - Long renders wait through queue state and CDP probes, not a multi-hour model
     call.

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
  later.
- `send_deferred_artifact`: backend work is complete but the MP4 has not reached
  WeChat; resend before continuing.
- `send_deferred_locked`: WeChat GUI is locked, or the serialized send lane was
  busy/timed out while another file/video send was active; retry after normal
  unlock or after the active send finishes.
- `generation_poststage_pending`: MP4 was delivered and LazyEdit/public publish
  is queued or still running.
- `publish_poststage_pending`: an existing quoted/generated video is in
  LazyEdit/public publish verification; deterministic probes and the resumed
  chat worker session continue until terminal proof or repairable failure.
- `done`: only after the requested current-message stages have completed.

The WeChat group is a command mirror. The durable system is the monitor, queue,
session registry, deterministic routines, and worker supervisor.
