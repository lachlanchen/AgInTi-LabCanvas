# WeChat Agent Routine Cheat Sheet

This is the execution contract for autonomous WeChat work. WeChat is only the
message box. The system agent is the direct monitor, queue, routine registry,
Codex resume session, deterministic probes, guarded sender, and poststage
worker.

This file is also an implementation input. `wechat_routines.py` turns the same
rules into `task.routine.autonomy_contract`, writes
`agent_routine_cheat_sheet.md` beside every task's `routine_contract.*`, and
includes the compact autonomy contract in the resumed worker prompt. Do not
treat this as manual-only documentation.

## Core Loop

1. Direct monitor reads new rows, coalesces context, routes with the agent, and
   writes one queue task with source chat, local IDs, route decision, and
   routine.
2. Worker claims a task, writes `routine_contract.*`, and uses mature routine
   entrypoints before asking the same chat's resumed Codex worker session to
   reason.
3. If a browser job is submitted, immediately persist `generated_video_monitor`
   and return the task to `generation_waiting`.
4. Long waits stay in queue timestamps. Workers run short deterministic probes,
   then release the worker for later messages.
5. Safe artifacts are sent back to the exact source chat by default. MP4/PDF/
   image delivery is a required gate before follow-up text can close the task.
6. LazyEdit and public publishing run only when the current request explicitly
   asks for them, and only after the MP4 has been sent back to WeChat.

The human operator should not be part of the normal execution loop. The system
may ask for approval only for login, CAPTCHA, payment/credits, public posting,
deletion, purchases, or another unsafe/irreversible decision.

## Generated Video Routine

- Route: `route_kind=generate_video`, routine `generated_video`.
- Submit/resume: use existing Xiaoyunque CDP/browser helpers and avoid
  duplicate submit if a thread is already queued/running.
- Continue: if the current thread asks to confirm generated storyboard/reference
  assets before making the final video, run `xyq_continue_thread.py` through the
  worker. Keep the same `thread_id`; do not open an old history item. When the
  local Xiaoyunque key is available, the helper also submits the continuation
  through OpenAPI so the actual run advances.
- Monitor: `deterministic_generated_video_monitor_result()` calls
  `watch_thread_dom_download.py` in short probe cycles.
- Recovery: if an agent/browser turn times out, adopt active `watch_*.json` or
  Chrome CDP `thread_id` into `generated_video_monitor`.
- Verification: use `ffprobe`; duration within 5 seconds of the requested
  length is acceptable unless the request says exact duration.
- Delivery: send the verified MP4 to the source chat and record
  `sent_file_paths`.
- Poststage: after delivery, run LazyEdit/import and public publish only when
  `stage_permissions` allow them.

## Scheduling Rules

- New `pending` messages are claimed before old due video polls.
- Video polls must be short probes; do not let a worker sleep for minutes inside
  a watcher process.
- One old generation must not block routing, downloads, CAD/PCB, writing, or
  later WeChat requests.
- Old generated-video tasks with many failed polls and hours without an MP4 are
  paused as `generation_stale_paused`; do not keep reopening stale Xiaoyunque
  sessions forever.
- Hardcoded logic is only for source isolation, safety gates, deterministic
  probes, and delivery gates. Capability decisions remain agent/routine based.

## Failure Handling

- Never mark generated-video work done until the MP4 is delivered or explicitly
  deferred.
- Do not use old AutoPublish/WeChat MP4s as output for a new generation task.
- If GUI send fails, leave `send_deferred_artifact` or `send_deferred_locked`
  with retry state.
- If a probe sees login/CAPTCHA/payment/credit blockers, keep the task
  resumable and request the specific confirmation.
- Treat `积分不足`/`余额不足` as a real blocker, not a polling state. Move the task
  to `waiting_confirmation` until the user recharges or approves a shorter or
  lower-budget alternative.
