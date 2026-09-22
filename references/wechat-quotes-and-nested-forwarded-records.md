# WeChat Quotes and Nested Forwarded Records

## Scope and Findings

Checked on 2026-09-22 against the active Windows personal-WeChat projection.
Ordinary native quoted replies retained their reference payload, server ID,
author, and request. The mirror contained three quoted cards in the inspected
recent-card sample, but no merged chat-record cards. Do not describe the new
merged-record support as a live end-to-end delivery test.

The existing formatter reduced type-19 merged forwards to a card title and
description. A quote of a quote could also lose the inner reference. The native
transport was retaining the data; formatting into agent context was the gap.

## Repair

- `wechat_forwarded_messages.py` recursively decodes merged records,
  records inside records, and records reached through quoted replies.
- XML children, CDATA, escaped payloads, and native group-sender prefixes are
  accepted. Text keeps its original author, timestamp, order, and nested path.
- `wechat_direct_chatops.py` exposes attributed text to the router and keeps
  decoded records in the authoritative message ledger. Coalesced inputs are
  not reduced to the final message or the eight-row recent-context preview.
- Ordinary nested quotes retain their original text and quoted authors.
- Worker preflight writes `forwarded-message-context.json` atomically with mode
  0600 in the ignored, exact-task artifact directory. Every relevant coalesced
  record and interruption remains available beyond inline prompt limits.
- Codex and AgInTi receive the same preflight context path and evidence rule.
  The backend reads this file, decides what the current requester means, and
  may answer several related messages together.

Neither archived participants' commands nor card descriptions authorize
publication. Exact current-message authorization and source resolution remain
required. Embedded attachment labels describe metadata, not successfully read
images, videos, or documents. Native media retrieval is a separate step, and
must not substitute another chat's file or a nearby image.

## Bounds and Remaining Limits

The XML envelope is capped at two million characters. DTDs/entities are rejected.
Nested decoding is capped at eight levels and 1,000 structural/message items.
Missing record bodies, count mismatches, unsupported nested payloads, and budget
limits produce explicit partial status. A short preview is never evidence that
the whole record was read.

This does not claim support for every undocumented WeChat card variant or
automatic download of every encrypted attachment inside a forwarded record.
Unknown payloads require an exact-source fixture and a specific recovery path.
WeCom remains separately transported. Its LabAgent intake and schedules were
intentionally paused and were not resumed for this repair.

## Verification and Rollout

Focused regression coverage lives in `tests/test_wechat_forwarded_messages.py`
and `tests/test_wechat_quote_reference.py`. The tests include a Windows export
to SQLite projection to decoded agent-context round trip, nested references,
long-record tail retention, sender attribution, privacy, bounds, and denial of
publication based solely on a forwarded command.

Run the full suite with `npm test`, which isolates tests from live transports.
This repair passed 2,154 tests (14 skipped), including 12 new forwarded-record
tests. Read-only inspection of three recent native quoted rows found no
attribution/decoding failures. No synthetic messages were sent to real groups.
For focused tests, set `WECHAT_TINY11_DISABLE=1` and
`WECHAT_WORKER_DISABLE_CODEX_IMAGE_READ=1`. Never send a synthetic fixture into
a real chat merely to test a parser.

After validation, reload only idle personal-WeChat monitor/worker Python
children under the existing restart supervisor. Keep clients, login sessions,
native sync, delivery receipts, cursors, and all other projects unchanged.
Do not reset a cursor or replay already-handled history to activate this fix.

## Format Reference

The upstream [Wechaty merged-history discussion](https://github.com/wechaty/wechaty/issues/1679)
documents the `recordinfo/datalist/dataitem` structure and distinguishes inline
text from separately retrieved media. Fixtures here are synthetic; private
group histories, CDN keys, signed URLs, and profiles must never be committed.
