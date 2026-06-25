# LazyEdit Instagram Codec Incident

Date: 2026-06-25

This note records a real failure in the WeChat automation -> LazyEdit ->
AutoPublish -> Instagram path and the guardrails that prevent the same failure.

## Incident

A WeChat request asked to publish the LazyEdit video
`c05ffae4cac15cfb5f8abe6a8922c486_COMPLETED` to Instagram. The local and remote
queues first reported `done`, but Instagram showed a publish error popup.

The failed remote package contained:

```text
.../c05ffae4cac15cfb5f8abe6a8922c486_COMPLETED_highlighted.mp4
codec_name=hevc
codec_tag_string=hvc1
pix_fmt=yuv420p
duration=7.533333
size=841449
```

Instagram browser upload can accept this file initially, then fail during
processing or posting. The old AutoPublish queue result was therefore a false
success.

## Corrected Run

LazyEdit regenerated the publish bundle with a browser-safe MP4:

```text
codec_name=h264
codec_tag_string=avc1
pix_fmt=yuv420p
duration=7.534000
size=2072411
```

The corrected Instagram-only run used:

```text
LazyEdit video_id: 409
LazyEdit job: 219
Remote AutoPublish job: job-1782391804462-4
Platform: instagram
Result: done
Live browser evidence: "Your reel has been shared."
```

## Required Guardrails

Before any WeChat automation says a video is published:

1. Resolve the exact source video from the current chat/request.
2. Call LazyEdit, not ad hoc browser scripts, for processing and publish bundle
   creation.
3. Verify the generated ZIP contains a browser-safe MP4 for browser platforms:
   H.264/AVC `avc1`, `yuv420p`, AAC audio when audio exists, and faststart.
4. Treat HEVC/H.265, `hvc1`, AV1, or unknown codecs as repairable packaging
   failures. Rebuild through LazyEdit before posting.
5. Verify local LazyEdit job status and remote AutoPublish job status.
6. For Instagram, also inspect browser evidence when a user reports a popup:
   success text must be `Your reel has been shared.`; visible error text wins
   over a queue `done`.
7. Send the result evidence back to the source WeChat chat.

Useful codec probe:

```bash
ffprobe -v error \
  -select_streams v:0 \
  -show_entries stream=codec_name,codec_tag_string,pix_fmt,width,height \
  -show_entries format=duration,size \
  -of json /path/to/publish_video.mp4
```

Useful ZIP check:

```bash
unzip -l /path/to/publish.zip
```

If a stale remote extraction directory still has the old HEVC MP4, resubmit the
same LazyEdit video to only the failed platform after verifying the local ZIP is
browser-safe:

```bash
cd /home/lachlan/DiskMech/Projects/lazyedit
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lazyedit

python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --platforms instagram \
  --no-process \
  --guided-monitor \
  --remote-log-command "ssh lachlan@lazyingart 'tmux capture-pane -pt autopub:0 -S -160 | tail -n 160'" \
  --wait \
  --poll-seconds 10 \
  --publish-timeout 1800
```

Do not republish other platforms unless the current request explicitly asks for
them.
