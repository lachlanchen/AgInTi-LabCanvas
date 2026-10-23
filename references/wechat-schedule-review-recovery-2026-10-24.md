# WeChat Schedule Review Recovery

## Failure Boundary

A ready client, a fresh message cursor, and a running scheduler do not prove that
a requested document was generated or delivered. Inspect these stages separately:

1. Native client login and source-database freshness.
2. Per-chat cursor, current queue, and exact outbound receipts.
3. Account quota and actual model execution. Remaining quota does not establish
   model entitlement. Probe the shared backend with a small read-only request.
4. Document generation, review, compilation, and verified delivery.

In the observed EchoMind failure, an independent reviewer first identified real
language and exercise problems. A later reviewer invocation returned no valid
audit. The scheduler treated missing audit scores as lesson defects and tried
editing the document again. A subsequent run also restarted from the original
draft, losing reviewed improvements.

## Recovery Contract

- Document and periodic-editor model defaults follow the shared model policy.
  Explicit environment and document-quality configuration overrides still win.
  Remove an obsolete private override rather than repeatedly changing the shared
  policy to accommodate it.
- Career/MEMO CLI and generated boot helpers use the same shared policy when no
  explicit model was requested. Update installed boot helpers as well as source
  templates; otherwise a supervisor can restore the obsolete pin after repair.
- An unsuccessful reviewer invocation, incomplete JSON, or invalid score schema
  raises `DailyPdfAuditUnavailable`. It cannot approve a PDF or trigger content
  rewrites. Genuine complete negative audits still drive bounded content repair.
- Before each audit, atomically save a private review checkpoint with the exact
  source-message identity and body hash. Resume that reviewed body only when the
  source identity and hash match. A changed source or corrupt checkpoint requires
  regeneration. Recovered content must pass a fresh audit before delivery.
- Keep deterministic content checks, independent linguistic review, PDF identity,
  native send verification, and same-date duplicate suppression intact.
- Restart only an idle scheduler, holding its daily-PDF lock during replacement.
  Preserve the existing tmux command, WeChat profile, client, and chat monitors.
  The resumed scheduler immediately checks due work; a completed daily artifact
  must not be resent simply to test restart.

## Native Header Recovery

A failed title guard is not necessarily a logout. Inspect the attempt sequence:
the correct group may have opened, but OCR can join its title and member count
with far-right toolbar icons. Restrict header matching to the first nonempty
line's left column, separated by the wide whitespace gap. Do not search message
body lines or another column for the expected title. Keep the remaining title
and rejected-surface guards, then retry only the retained undelivered result.
Never disable the title guard or repeat the backend task to repair delivery.

## Verification

`tests/test_echomind_language_scheduler.py` covers unavailable versus negative
audits, source-bound checkpoint reuse, tamper rejection, and a two-attempt recovery
that sends once without reauthoring or editing after an unavailable audit.
The repository regression suite passed 2,370 tests with 16 skips, including the
native-header regression tests. A live read-only
reply through the shared Codex route succeeded; no test message was posted to a
group and paid-credit usage remained disabled.

The resumed EchoMind routine generated and reviewed the previous-day report,
compiled its four-page PDF, and obtained a native `sent_verified` receipt.
Two retained reply tasks also reached verified delivery; their answers explicitly
limited themselves to card evidence where original Channels media was unavailable.
The career routine also delivered both language PDFs and its concise summary
through its ordinary artifact sender. The stack launcher passes an empty model
override by default, with a shell-level regression covering explicit overrides.

Runtime evidence and per-chat state remain under ignored private/output paths.
Do not include raw source messages, account identities, tokens, or private reports
in a public recovery record.
