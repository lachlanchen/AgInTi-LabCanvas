# Android WeChat Native Video Save

Date: 2026-08-31

## Purpose

Use this route when the exact inbound WeChat video is visible on the MIX 2S but
is not available in the desktop WeChat cache. The output must be the file saved
by WeChat itself, never a recording of the player or desktop.

## Command

```bash
PYTHONPATH=src python -m agenticapp wechat native-save-video \
  --target <ALLOWLISTED_TARGET> \
  --task-id <TASK_ID> \
  --output-dir output/wechat_android_intake/<TASK>/native_original \
  --filename <MEANINGFUL_NAME>.mp4 \
  --video-tap x,y \
  --expected-duration-seconds <SECONDS_IF_KNOWN> \
  --expected-original-size-mb <ADVERTISED_MB_IF_KNOWN> \
  --json
```

The agent determines the exact visible bubble and supplies `x,y`; the reusable
routine owns the fragile transport steps and verification.

## Verified Sequence

1. Acquire the shared Android control lease and open the allowlisted exact chat.
2. Silence Android media streams 1, 2, and 3.
3. Verify the chat title immediately before opening the selected video bubble.
4. If the native player offers `查看原视频`, request it and wait for completion.
   The advertised MB value is used as a minimum-size guard when OCR recovers it.
5. Tap WeChat's native album-save control.
6. Identify only a newly created `mmexport...` video in Android MediaStore under
   `DCIM/WeiXin`, then wait for its byte size to stabilize.
7. Pull that exact file to the task's ignored `native_original/` directory.
8. Require readable video streams with `ffprobe`, check duration and expected
   original size when known, and calculate SHA-256.
9. Delete the temporary phone file and its MediaStore row, then verify both are
   gone.
10. Write `native-video-export.json` with exact host path/checksum, native source
    kind, probe evidence, `automation_screen_capture=false`, and
    `device_copy_removed=true`.

Host validation happens before phone cleanup. If host validation fails, the
routine does not claim success. If phone cleanup fails, the manifest remains
non-publishable and reports cleanup pending.

## Publication Boundary

`wechat_video_source_policy.py` is called by both the WeChat AutoPublish copier
and the worker's direct AutoPublish copy boundary. Android intake media is
rejected unless its exact path/checksum matches the verified manifest and phone
cleanup is complete. Known automation capture provenance and names such as
`screen_raw` are rejected.

A video intentionally recorded from a screen by the user is not forbidden. It
is valid when WeChat's native export proves it is the exact attachment. What is
forbidden is creating a new player/scrcpy/desktop recording as a recovery
substitute.

## Failure Rule

If the exact native file cannot be recovered, stop. Do not process it through
LazyEdit, copy it to AutoPublish/Nutstore, publish it, or silently fall back to
a GUI recording. A later same-chat source resend or a successfully cached exact
desktop attachment may resume the task.
