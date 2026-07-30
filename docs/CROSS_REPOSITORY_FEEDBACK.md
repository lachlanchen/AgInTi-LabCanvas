# Cross-Repository Feedback

LabCanvas can record a verified integration bug, feature request, or handoff in
an allowlisted sibling repository without granting arbitrary filesystem writes
to chat content.

## Command Surface

```bash
PYTHONPATH=src python -m agenticapp feedback targets --json
PYTHONPATH=src python -m agenticapp feedback write lazyedit feature \
  "Expose a job-scoped login QR artifact" \
  --summary "LabCanvas needs the current publish job's QR image." \
  --expected "Return one current job-scoped QR artifact." \
  --observed "Only a login-blocker state is available." \
  --evidence "Verified against the current local publish status response." \
  --acceptance "The caller can retrieve the QR without duplicate sends." \
  --verified --json
PYTHONPATH=src python -m agenticapp feedback list lazyedit --json
```

Allowed targets are `labcanvas`, `lazyedit`, `musia`, `books`, `zhjpbook`,
`lalachan`, `proteinstructure`, and `agintiflow`. Reports are written under:

```text
<target-repository>/handoff/labcanvas/
```

The target registry may be redirected for tests or local installations with
`LABCANVAS_FEEDBACK_<TARGET>_ROOT`; it still cannot accept an arbitrary path
from a chat message.

## Agent Contract

The route agent selects `cross_repo_feedback` only for an explicit bug report,
feature request, or integration handoff tied to a known target. A normal
research report remains a research task.

The worker agent:

1. Reads the exact current request and same-chat context.
2. Reproduces or inspects a bug, or makes an explicit feature requirement and
   testable acceptance criteria concrete.
3. Returns structured `upstream_feedback` in its JSON result.
4. Lets the queue orchestrator validate, redact, and write the report.

Deterministic code does not invent the report. It rejects unverified or
transient proposals and accepts at most three bounded entries from one worker
turn.

## Safety And Delivery

- Login, CAPTCHA, quota, network, timeout, and transport failures are not
  product reports unless independent evidence establishes a persistent defect.
- Passwords, tokens, cookies, raw chat/task/member IDs, signed URLs, absolute
  home paths, and private logs are removed or replaced before writing.
- Stable target, kind, and title produce one stable report ID and filename.
  Identical content is a no-op; changed content increments the revision.
- The Markdown report remains local by default. It is attached to WeChat or
  WeCom only when the current request explicitly asks for the report file.
- A local report does not authorize a public GitHub issue, commit, push,
  release, publication, payment, or credential change.

## Integration Pattern

Sibling tools remain the owners of their domain implementation. LabCanvas
calls their mature CLI/API, verifies real behavior, and records a concrete
handoff when the interface is missing or wrong. This keeps chat automation
agent-led while making cross-repository improvements durable and reviewable.
