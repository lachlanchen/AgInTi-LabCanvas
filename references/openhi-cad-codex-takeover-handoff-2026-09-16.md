# OpenHI CAD: Codex Thread Takeover Handoff

Date: 2026-09-16

## Scope

This note records the state of the OpenHI CAD work stream when the Codex
thread `LabCanvas-CAD` (forked 2026-08-29 from the `LabCanvas` thread) was
taken over by a Claude Code session. It is the curated entry point for any
agent continuing the CAD work. Raw session history stays private and is not
part of this repository.

## Where the work stopped

The last completed Codex turn was 2026-09-01 15:35 UTC. It delivered the run-5
print release for all four same-lens systems and commit `3a0cfcd` (`fix OpenHI
C threads and output grips`). Nothing was mid-edit afterwards; the only later
event in the thread is an idle interruption on 2026-09-16.

Current accepted release for printing:

```text
cad/designs/openhi_4f_<key>_same_lens/runs/run-5-c-thread-straight-camera-grip-print-ready-20260901T143912Z/
/home/lachlan/Nutstore Files/Projects/LabCanvas/openhi_4f_<key>_same_lens/<same run folder>/
```

with `<key>` in `jh042`, `jh036`, `gla11_025_025`, `gla11_025_050`.

## Read these in order

1. `references/openhi-same-lens-4f-design-philosophy-2026-08-29.md`: source
   authority, datums, 4f + 4.6 mm end-path contract, thread map.
2. `references/openhi-same-lens-4f-input-receiver-lens-cavity-correction-2026-09-01.md`:
   optical-vertex versus annular-seat datums, exact A input receiver.
3. `references/openhi-same-lens-4f-c-thread-straight-output-grip-correction-2026-09-01.md`:
   part-name map, final thread map, OCCT off-axis helix failure and the
   Z-frame construction rule, straight B/C output grip.
4. `references/openhi-same-lens-4f-final-mechanical-optical-audit-2026-08-30.md`
   (superseded for print use, still the fullest dimensional table).
5. `references/openhi-six-part-thread-fit-regeneration-2026-08-08.md`,
   `references/openhi-abc-exact-parametric-baseline-2026-08-16.md`,
   `references/openhi-shapr3d-step-import-repair.md`: the original six-part
   regeneration and print-fit history that the 4f families build on.
6. `cad/README.md`, `cad/references/cad-toolchain.md`,
   `cad/references/openhi-print-fit-and-thread-reference.md`.
7. The `parametric-cad-design` skill (`../LazySkills/skills/parametric-cad-design/`),
   especially `references/shapr3d-cad-patterns.md`.

## Design contract in one table

| Item | Value | Source |
| --- | --- | --- |
| Beam-splitter center | `(255, 210, 600) mm` | source STEP |
| B chain axis | `X = 254.633 mm` (`-0.367` from A/C), keep | source STEP, user confirmed |
| Optical datum | inward axis vertex at one catalog EFL from BS center | ST018 convention |
| Outer-end paths A-B and A-C | `4f + 4.6 mm` (A end `f + 0.2`, output ends `f + 4.4`) | measured ST018 assembly |
| Lens pocket | `D + 0.25 mm`, axial travel `0.20 mm` | user: keep prior tolerance |
| Clear aperture | `min(24, D - 1.5) mm` | builder rule |
| Lens-retainer threads | holder female `29.8/30.6`, cap male `29.6/30.4`, pitch `0.8`, `7.75 mm` | six-part measurement, user |
| Central C pair | female `29.6/30.4` vs male `29.8/30.6`, `0.2 mm` interference | accepted printed fit |
| A input receiver | `25.0` pilot, `25.8` groove, `12.474 mm` deep | source `A.step` |
| B/C output thread | `24.4/25.2`, `4.7 mm`, straight `40 mm` grip, flat shoulder | source profile, user 2026-09-01 |

Part names: `A_C_BS`, `Lens_B_holder`, `Lens_C_holder` are the A, B, C lens
holders; `A`, `B`, `C` are the caps.

## Item to confirm with the user

Two user statements about the `A_C_BS` female pivots conflict (2026-08-29: C
end `29.6`, other `29.8`; 2026-08-30: the reverse wording). The built and
printed geometry is A-side `29.8`, C-side `29.6`. Confirm before regenerating
`A_C_BS`.

## Toolchain

```bash
P=cad/.conda/cad-python/bin/python
$P cad/designs/openhi_4f_<key>_same_lens/build_<key>_openhi_4f.py --no-sync
blender --background --python cad/tools/render_openhi_same_lens_4f.py -- --design-dir cad/designs/openhi_4f_<key>_same_lens
$P cad/tools/package_openhi_same_lens_4f_print_release.py --design-dir cad/designs/openhi_4f_<key>_same_lens
PYTHONPATH=src python -m unittest tests.test_openhi_same_lens_4f_manifests
```

Every regeneration keeps the previous outputs as a new `runs/run-N-...` folder,
places one directly usable `USE_THIS_*.step` at the design root, renders
assembly, exploded, section, and print-layout views, and mirrors the print-ready
run to Nutstore byte-for-byte.

## Shapr3D intake reminder

A `.shapr` archive on Linux is a zip whose `workspace` SQLite mostly stores
imported Parasolid bodies. OCCT cannot read Parasolid, so a new Shapr design
must arrive with a STEP export (or already exist under `cad/extracted/`) before
elements can be adjusted, validated, and rendered here. Use
`cad/tools/shapr_workspace_probe.py` or the skill's
`inspect_shapr_step_sources.py` to read names, operation history, and body
counts from the archive itself.

## Cross-agent handoff

Use the `codex-collaboration` skill (`../LazySkills/skills/codex-collaboration/`)
to read a Codex thread, write a handoff packet, or hand work back to Codex once
quota is available. Private packets live under `~/.codex/handoffs/`.
