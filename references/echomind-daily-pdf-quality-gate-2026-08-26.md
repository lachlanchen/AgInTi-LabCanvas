# EchoMind Daily PDF Quality Gate

Date: 2026-08-26

## Problem

The daily chat message could be useful while the PDF was generic, repetitive, or
linguistically weak. The previous implementation gave the writer the exact prior-day
messages plus an oversized lifetime-history packet. In the observed failure, a tiny
prior-day lesson was competing with tens of thousands of historical prompt tokens.
The semantic reviewer later rejected the PDF, but an older retry path could still
deliver an already compiled file without proving that its accepted review matched the
same PDF bytes.

## Current Contract

- The exact previous local calendar day is the authoritative lesson source.
- Pure outbound artifact rows such as a generated PDF filename are not teaching
  evidence.
- Lifetime history contributes only a summary-level learner profile, capped by
  `ECHOMIND_DAILY_PDF_LONGITUDINAL_CHAR_BUDGET` (6,000 characters by default).
  Old high-fidelity excerpts are not included in the daily PDF prompt.
- The editor and auditor must preserve source scenarios while independently correcting
  Chinese, English, Japanese, pinyin, furigana, romaji, pronunciation, grammar, and
  exercises.
- Auditing includes source specificity, coherence, and reader value in addition to
  linguistic correctness and concision.
- A globally shallow, structurally broken, or generic report receives one coherent
  source-grounded rewrite. Narrow defects continue to use bounded whole-section
  patches.
- Machine responses wrapped as `{"response": "..."}` are unwrapped before LaTeX
  validation.
- Placeholder ruby, Latin-letter furigana, and body-level `\\textipa` commands are
  rejected deterministically.
- Compilation and delivery occur only after deterministic checks and the semantic
  audit both pass.
- A pending retry is deliverable only when its quality sidecar is `accepted`, has no
  open issues, and contains the exact current PDF identity. A changed, missing, or
  rejected file fails closed.

## Validation

Use an isolated root and `deliver=False` when checking content changes. Keep the real
chat ledger read-only, but redirect scheduler state, lock, and output paths to a
temporary directory. Inspect all of the following before enabling the production
scheduler:

1. The quality JSON has `status: accepted`, every semantic score is at least 4, and
   `contract_issues` is empty.
2. `pdfinfo` reports a readable PDF and `pdftotext -layout` contains the complete
   lesson rather than logs, paths, or source-process commentary.
3. Render every page with `pdftoppm` and inspect the PNGs for clipping, overlap,
   unreadable ruby, broken line wrapping, or blank output.
4. Confirm the isolated run did not call chat delivery.

The 2026-08-25 no-send validation used one substantive exact-day source row and a
bounded learner profile. The production routing completed two targeted revisions,
passed the independent audit, compiled a five-page PDF, and produced an immutable
accepted sidecar. The artifact stayed under `/tmp` and was not sent to EchoMind.

## Regression Tests

Focused tests live in `tests/test_echomind_language_scheduler.py`. They cover context
bounding, artifact-row exclusion, response-wrapper normalization, deterministic
language-format checks, rewrite selection, semantic audit dimensions, accepted-file
identity, and rejection of stale or failed pending PDFs.
