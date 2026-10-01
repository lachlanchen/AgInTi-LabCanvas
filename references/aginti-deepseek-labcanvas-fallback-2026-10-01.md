# DeepSeek Fallback Acceptance for LabCanvas

## Scope

Codex remains the primary backend. AgInTi with DeepSeek is the normal fallback;
LocalLLM is a separate final capability fallback, not a dependency of this test.
No model-policy change, group message, public publication, payment, Android
control, or WeCom restart was performed. WeCom/LabAgent remains paused.

The standalone CLI tutorial is at
`~/Documents/SystemTutorial/agents/aginti-deepseek-fallback-20261001.md`.
Passing standalone CLI tests is not sufficient: both LabCanvas adapters must
preserve their own output, session, routine, and safety contracts.

## Defects Fixed

1. Machine-mode Studio and WeChat invocations now enforce `--no-wrappers`, on
   both new and resumed sessions. A fallback must not call back into an
   unavailable Codex or Claude wrapper. Established local routines remain usable.
2. A failed/timed-out WeChat turn retains its resumable ID only when the pointer
   and saved state prove the exact workspace and session. A missing state or
   foreign workspace cannot create a false recovery entry. Partial artifacts
   remain available to the next turn.
3. Studio merges registry updates under a short shared file lock after each
   model turn. Separate conversations may execute concurrently without erasing
   each other's session entries.
4. AgInTi's completion gate no longer forces an unrelated input/source edit
   when creating a separate deliverable. A verified current-turn mutation inside
   a bounded artifact root satisfies artifact freshness even though private
   outputs do not increment the project-source revision. Old artifacts and real
   source-repair tasks retain their freshness checks.
   A repeated installed-package test exposed a second state issue: an obsolete
   missing-file repair continued forcing edits after the scoped mutation had
   satisfied it. The runtime now retires that forced phase, but does not waive
   genuine source/artifact quality repairs.
5. AgInTi recognizes postfix read-only input declarations. Its source-free
   claim gate also distinguishes “do not invent revenue forecasts” from actually
   making a forecast; a real claim later in the same sentence remains gated.

The first three fixes belong to LabCanvas. The latter two are general AgInTi
behavior, not WeChat-specific task branches. Docker/host permissions were not
widened to make a test pass.

## Reusable Acceptance

```bash
python scripts/evaluate_aginti_fallback.py --live
```

The default invocation without `--live` refuses inference. To inspect a candidate:

```bash
python scripts/evaluate_aginti_fallback.py --live --command /path/to/bin/aginti-cli.js
```

This uses the real WeChat and Studio adapters, isolated synthetic workspaces,
the Studio task packet, an explicit DeepSeek-only provider chain, and local
XeLaTeX compilation. It does not send to live groups or authorize LocalLLM
inference. The existing worker JSON parser handles fenced JSON consistently
with production; no task-specific answer substitution is used.

The four cases check:

- Consecutive same-chat messages plus a quote: one reply, exact video identity,
  all four requested subtitle languages, and no publication authorization.
- Daily memo: earlier/current engineering and business context, host-compiled
  Chinese PDF, CJK line wrapping, and rejection of overflowing text.
- Existing routine: invoke `scene-template experiment-setup`, preserve its
  geometry, validate via `render-scene --dry-run`, then resume to change only
  resolution. Do not rewrite the CLI or run Blender.
- Studio: summarize named inputs, resume after a resolved login blocker, retain
  language/publication/payment constraints, and preserve source files.

Evidence checks use saved provider/tool history, real artifact parsing, original
input hashes, and attempted file writes, not just the agent's success sentence.
The registry concurrency and timeout recovery tests use deterministic mocks so
normal regression runs spend no model quota.

## Observed Results and Limits

Initial live runs exposed false completion gates, unwanted temporary input edits,
and stalled no-op repair loops. Their reports are retained under ignored
`output/aginti-fallback-acceptance/`; failed evidence was not deleted.

After correction, all four candidate cases passed in
`20261001T051917Z-26bac660/report.json`: about 2.4 s for grouped chat, 3.8 s for
memo generation/compilation, 31.4 s for both routine turns, and 34.3 s for both
Studio turns. The PDF preview was also visually inspected.

These tests establish a useful simple-task fallback, not equivalence to Codex or
proof of every CAD, research, media, publication, or live delivery workflow.
Provider transport, model quality, missing tools, login, and permission failures
remain distinct limitations. Never publish, retry external writes, or report
delivery merely because the fallback returned a successful text answer.
