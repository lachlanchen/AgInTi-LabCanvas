# Musia, LabCanvas, And WeChat Integration

Date: 2026-07-29

LabCanvas now treats WeChat/WeCom as the transport, the exact-chat Codex
session as the orchestration agent, and Musia Studio as the mature music-domain
runtime. LabCanvas does not implement another music generator.

## Runtime

```text
Musia repo: /home/lachlan/ProjectsLFS/Musia
Studio URL: discovered from Musia data/runs/musia-studio-server.port
Default URL: http://127.0.0.1:8767
Studio tmux: musia-studio
LabCanvas adapter: src/agenticapp/musia_ops.py
Private registry: output/musia/session_registry.json
```

The registry key is a SHA-256-derived source-scope key. Raw chat names and
transport identifiers are not persisted there.

## Commands

```bash
PYTHONPATH=src python -m agenticapp music doctor --json
PYTHONPATH=src python -m agenticapp music start --json
PYTHONPATH=src python -m agenticapp music status --json

PYTHONPATH=src python -m agenticapp music submit \
  "Generate and review the requested song" \
  --source-scope "TRANSPORT:EXACT_CHAT_SESSION" \
  --task-id TASK_ID \
  --mode worker \
  --json

PYTHONPATH=src python -m agenticapp music wait JOB_ID \
  --timeout 10800 \
  --json

PYTHONPATH=src python -m agenticapp music artifacts \
  --source-scope "TRANSPORT:EXACT_CHAT_SESSION" \
  --json

PYTHONPATH=src python -m agenticapp music artifact ARTIFACT_ID \
  --source-scope "TRANSPORT:EXACT_CHAT_SESSION" \
  --output-dir output/wechat_worker/TASK_ID/musia \
  --json
```

The worker may use `music submit --wait` for one bounded turn. A durable job can
always be resumed later with `music wait`; polling the job endpoint does not
spend model tokens.

Task IDs are adapter-idempotent. Repeating the same task and prompt reuses its
existing Musia job. A changed prompt under the same task returns
`revision_required=true` rather than spending another heavy generation. The
agent may pass `--new-revision` only when the current exact-chat request clearly
authorizes a new render. Registered artifacts are copied into the task folder by
exact artifact ID before chat delivery.

## Music Route

`route_kind=music_generation` selects `musia_music_generation`.

The agent:

1. Reads the full same-chat request, recent context, and exact source-scoped
   lyrics/audio/reference files.
2. Reuses the source chat's Musia Studio session.
3. Lets Musia choose and supervise its existing model/production routines.
4. Waits for a real terminal job.
5. Collects registered audio, lyrics, review, cover, and project artifacts.
6. Returns the reviewed song and the smallest useful supporting artifact set.

A queued job is not a generated song. The result must refer to an existing
audio artifact.

## Song-First MV Route

`route_kind=music_to_mv` selects `musia_music_to_mv`.

The stages are:

1. Create or select reviewed Musia master audio.
2. Prepare the handoff:

   ```bash
   PYTHONPATH=src python -m agenticapp music mv-pack \
     --audio /absolute/path/to/reviewed-master.wav \
     --title "Title" \
     --duration 15 \
     --copy-references \
     --json
   ```

3. Use the existing LALACHAN/Xiaoyunque browser routine for visuals.
4. Monitor one idempotent paid generation to a verified MP4.
5. Remux the reviewed Musia master when Xiaoyunque changes/degrades the audio.
6. Verify duration and streams.
7. Return both the reviewed song and MP4 to the exact source chat.

The reviewed Musia master is the timing and soundtrack authority.

## Permission Boundaries

These are independent permissions:

```text
music generation
music-video generation
public publication
```

A song-only request stops after music delivery. An MV request does not
authorize Shipinhao, YouTube, Instagram, or another public post. LazyEdit and
public platforms run only when the current request explicitly asks for that
stage.

## Interruptions

The source chat's persistent LabCanvas agent retains the full conversation and
may steer the active music/MV task. Musia Studio retains bounded music-domain
history and durable jobs. New messages should be applied before the next
generation/review stage; they must not erase still-valid earlier constraints.

If resources were already consumed, the system should revise the current
artifact when possible. It must not silently create another paid/heavy
generation.

## Musia API Handoff

The Musia-side contract and proposed future `/api/agent/*` endpoints are in:

```text
/home/lachlan/ProjectsLFS/Musia/handoff/LABCANVAS_AGENT_API_HANDOFF_2026_07_29.md
```

The current adapter works with the existing Studio API now. The future API adds
idempotent task creation, ordered interruptions, cancellation, durable states,
and stable artifact identities without blocking this integration.
