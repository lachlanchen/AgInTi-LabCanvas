# Exact WeChat Video Publication and LabAgent Schedule Recovery

Date: 2026-08-16

This note records a system-level recovery of one existing-video publication and
one missed LabAgent idle-inspiration run. The important result is the reusable
contract, not the individual publication.

## Verified Outcome

- The exact same-chat MP4 was resolved from its WeChat message shard and local
  ID, not from recency or a Downloads-folder guess.
- LazyEdit processed the source with portrait background fill and bottom-aligned
  French, Traditional Chinese, Japanese, and English subtitles.
- The correction and metadata context identified the visible subject as robotic
  arms built by the creator.
- One replacement local publish job reached terminal success on Shipinhao,
  YouTube, and Instagram. The associated remote AutoPublish job also reached
  `done`.
- The result was returned to the originating WeChat chat only after terminal
  platform verification.
- The missed LabAgent three-hour inspiration was invoked once immediately and
  its resulting message was verified in the WeCom delivery ledger.

The robotic-arm final used the accepted `bottom_anchored` subtitle-band style
with `liftRatio=0.0`. Its comparison with the Paris `lifted` style is recorded
in `references/lazyedit-subtitle-band-lift-variants-2026-08-16.md`.

## Failure Chain

The publication exposed four independent weaknesses:

1. Exact WeChat video recovery needed to bind both the rotated message database
   shard and local message ID. A local ID alone is not globally unique.
2. The resumed worker agent submitted a real LazyEdit job, but its returned
   `video_id` and job ID were not persisted before preflight was rebuilt.
3. Retry metadata was sometimes nested under `data`, while the guarded worker
   loop reads a top-level `publish_poststage_retry` contract.
4. LazyEdit's video-list request synchronously ran `ffprobe` over library items.
   Repeated browser calls blocked the single Tornado request loop and prevented
   the first job from reaching remote AutoPublish.

The LabAgent schedule had a separate cause: a task in
`waiting_confirmation` was treated as active work forever. Confirmation can
remain open for days while consuming no worker, so it must not suppress a later
idle inspiration run.

## Reusable Publication Contract

### Exact source resolution

Use this identity order:

1. exact chat;
2. exact `message_N.db:local_id` reference;
3. exact video MD5/length/native token from that row;
4. a source-scoped artifact-ledger match;
5. fail closed.

Modification time is discovery evidence only. Never replace an unresolved
source with a nearby MP4, thumbnail, old generated video, or another chat's
artifact.

`wechat_autopublish_video.py` owns native cache/GUI recovery and copies the
verified source into the AutoPublish handoff folder. It shares the WeChat GUI
lock, verifies the target header around GUI actions, and treats thumbnail-only
matches as incomplete.

### Agent and deterministic ownership

The resumed per-chat agent owns interpretation and one initial LazyEdit CLI
submission. It must:

- use the exact source and exact current-message platform allowlist;
- pass correction and metadata prompt files;
- apply one-shot layout/language flags;
- use `--no-wait` and return the real `video_id` and local job ID.

The deterministic poststage owns:

- immediate persistence of those IDs;
- long polling without holding a model turn;
- same-source retry identity preservation;
- duplicate prevention;
- login/QR blocker state;
- terminal local and remote platform verification;
- final source-chat delivery.

Never scan the whole video library or submit a second job when an exact
`video_id` or publish job ID is already known. Preserve known IDs only when the
source target/message reference is unchanged.

### Editorial context boundary

LazyEdit prompt files now contain only:

- the focused human request and same-request interruptions;
- bounded requester-authored text context;
- exact source identity and selected-video tokens for local verification;
- source-linked story/prompt excerpts when the video was generated.

They exclude forwarding wrappers, route/routine JSON, raw WeChat XML, signed
URLs, unrelated media tokens, file listings, and old worker status messages.
The metadata brief never includes the full orchestration request or raw chat
history. This keeps public metadata concise while preserving useful subtitle
evidence.

## LazyEdit Request-Thread Fix

Preview probing belongs off the Tornado request thread. The fixed design is:

1. `_preview_info_for_video()` returns current preview state immediately.
2. Missing preview information queues `_enqueue_preview_probe()`.
3. A bounded executor runs `ffprobe` and then queues proxy/poster creation.
4. `PROBING_PREVIEW_VIDEO_IDS` and `QUEUED_PREVIEW_VIDEO_IDS` suppress duplicate
   work.
5. `ffprobe` has a bounded timeout as a final guard.

The regression test proves that `_preview_info_for_video(...,
auto_enqueue=True)` never calls `_should_create_preview_proxy()` on the request
thread. After the change, `/api/videos` returned in tens of milliseconds during
the publication instead of timing out.

## LabAgent Idle-Schedule Rule

Periodic inspiration is opportunistic and must defer for genuinely active work:
claimed, in-progress, retrying, or active artifact delivery. It must not defer
for `waiting_confirmation`, because that state consumes no worker and may remain
open indefinitely.

After changing a schedule or its blocking policy:

1. restart only the owned scheduler pane;
2. invoke the schedule once immediately;
3. verify a single queue row;
4. wait for terminal worker state;
5. require `wecom_delivery.status=sent` before reporting success.

Do not drain old backlogs or replay terminal inspiration after a restart.

## Validation Commands

```bash
PYTHONPATH=src python -m unittest \
  tests.test_wechat_autopublish_video \
  tests.test_wechat_direct_chatops \
  tests.test_wechat_task_worker \
  tests.test_wecom_agent_bridge

PYTHONPATH=src python -m agenticapp wechat selftest \
  --suite publish-poststage --json

PYTHONPATH=src python -m agenticapp wecom daily run --force --json
```

LazyEdit:

```bash
cd /home/lachlan/DiskMech/Projects/lazyedit
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lazyedit
python -m unittest tests.test_preview_probe_async
curl -fsS -o /dev/null -w '%{time_total}\n' \
  http://127.0.0.1:18787/api/videos
```

## Completion Evidence Fields

A successful existing-video publication should retain:

- source chat and exact message reference;
- selected source checksum/size;
- `video_id`;
- local publish job ID;
- remote AutoPublish job ID;
- exact platform allowlist;
- local and remote terminal status;
- correction and metadata prompt paths;
- source-chat delivery status.

Queued, submitted, processing, missing, or login-blocked is not published.
