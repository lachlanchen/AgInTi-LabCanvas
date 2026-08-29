# WeChat Video Save-Only And Self-Echo Guard

Date: 2026-08-29

## Default Contract

An ordinary video attachment authorizes one operation: save the exact source
video privately. It does not authorize transcription, LazyEdit processing,
return delivery, AutoPublish intake, or public publication.

A later current-message instruction may authorize one or more additional
stages. Old chat history and internal prompt text can provide context but cannot
authorize those stages.

## Failure Reproduced

A video returned through the Android sender was transcoded by WeChat and then
appeared in the decrypted database as a self-authored video row. Before the
Android file component had a content identity in its ledger, the monitor could
mistake that row for a fresh attachment. Repeated workers then returned the same
video and internal task evidence, creating a delivery loop. One fallback also
copied the file into the AutoPublish intake despite the passive route.

## System Fix

- Android file components persist name, byte size, MD5, and SHA-256 privately.
- WeChat XML parsing collects every MD5 field, including
  `originsourcemd5`, because the visible/transcoded hashes may differ.
- Direct chatops checks both the shared outbound mirror and the Android sender
  ledger before routing a self-authored attachment.
- Passive video preflight always uses the task's ignored `source_media/`
  directory, regardless of publication words in stale context.
- The AutoPublish copy helper rejects passive tasks.
- Worker result enforcement and file preparation both canonicalize passive
  tasks to a silent result with no outbound files.
- Internal routine contracts, interruption manifests, and private Finder
  request/capture files are blocked from chat delivery.

## Verification

Regression coverage proves:

1. a transcoded WeChat video is matched through `originsourcemd5`;
2. a mismatched or stale video is not suppressed;
3. passive tasks cannot write to AutoPublish;
4. misleading agent claims and artifact paths are discarded;
5. a legitimate new video without outbound identity remains eligible for
   normal save-only intake.
