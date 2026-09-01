# OpenHI Same-Lens 4f C-Thread And Straight Output-Grip Correction

Date: 2026-09-01

## Scope

This note records the coordinated run-5 correction for these four parametric
OpenHI systems:

- `cad/designs/openhi_4f_jh042_same_lens/`
- `cad/designs/openhi_4f_jh036_same_lens/`
- `cad/designs/openhi_4f_gla11_025_025_same_lens/`
- `cad/designs/openhi_4f_gla11_025_050_same_lens/`

The correction does two things only:

1. restores the missing lens-facing female thread in `Lens_C_holder.step` and
   the matching male thread in `C.step`;
2. replaces the outer B/C output-end `40 -> 24.4 mm` conical taper with a
   straight `40 mm` cylindrical grip ending at a flat annular shoulder around
   the protruding C-mount-style thread.

The `30 mm` lens-facing transitions, lens seats, focal datums, beam-splitter
geometry, A input receiver, and central C mating interface are unchanged.

## Part Names

The source filenames can be misleading. Use this map:

| File | Mechanical role |
| --- | --- |
| `A_C_BS.step` | A lens holder and beam-splitter body |
| `Lens_B_holder.step` | B lens holder |
| `Lens_C_holder.step` | C lens holder |
| `A.step` | A lens-retaining cap and input receiver |
| `B.step` | B lens-retaining/output cap |
| `C.step` | C lens-retaining/output cap |

## Thread Map

The three lens-retainer pairs intentionally use the same clearance fit:

| Interface | Female holder | Male cap |
| --- | --- | --- |
| A lens | `29.8 mm` pilot, `30.6 mm` groove | `29.6 mm` root, `30.4 mm` crest |
| B lens | `29.8 mm` pilot, `30.6 mm` groove | `29.6 mm` root, `30.4 mm` crest |
| C lens | `29.8 mm` pilot, `30.6 mm` groove | `29.6 mm` root, `30.4 mm` crest |

All use `0.8 mm` pitch and `0.4 mm` radial tooth height. This gives `0.1 mm`
radial clearance at both the root/pilot and crest/groove.

The separate central C connection is deliberately different:

- `A_C_BS` side/C female: `29.6 mm` pilot, `30.4 mm` groove;
- `Lens_C_holder` beam-splitter-side male: `29.8 mm` root, `30.6 mm` crest.

That central pair preserves the accepted tight source fit. Do not replace the
three lens-side `29.8 mm` female pilots with `29.6 mm`; those are different
interfaces.

The B/C output thread remains the local OpenHI C-mount-style profile:

- root: `24.4 mm`;
- crest: `25.2 mm`;
- pitch: `0.8 mm`.

It is not relabeled as exact `1 in-32 UN` C-mount.

## Defect Found In Run 4

The run-4 generator created valid standalone helical sweeps for the C-axis
parts, but direct X-axis boolean operations caused OCCT to classify those
helical regions away in the final solids. The exported C holder and C cap
therefore retained only smooth pilot/root cylinders at the lens interface.

The defect was easy to miss because:

- the standalone cutters were valid;
- the final STEP files were still valid single solids;
- the smooth cylinders looked plausible in an exterior render;
- A and B used the same parameters and exported correctly.

Final-solid face inspection proved the problem: run 4 had no helical B-spline
faces in the C lens-thread interval, while its central and output threads were
still present.

## Stable Construction Fix

The corrected method is:

1. construct the complete C holder lens arm in the proven Z-axis frame;
2. perform every female-thread subtraction and bore boolean in that frame;
3. rotate the finished solid rigidly onto the +X C axis;
4. fuse it to the preserved central C body;
5. construct the complete C cap, including both male threads and bore cuts, in
   the same Z-axis frame;
6. rotate the finished cap onto +X;
7. inspect the final exported solids, not only the thread tools.

The generator now requires at least two helical B-spline faces in each final
thread interval for:

- all A/B/C holder female threads;
- all A/B/C cap male threads;
- both B/C output threads;
- both sides of the central C connection.

Packaging stops if any final thread is absent.

## Straight B/C Output Grip

`B.step` and `C.step` retain their original lens-facing chamfers and internal
optical bores. Only the exterior output transition changed:

- old: a conical exterior transition from the `40 mm` body to the output
  thread;
- new: a straight `40 mm` cylinder up to the output-thread start, followed by
  a flat annular shoulder and the protruding output thread.

This removes the thin sloping grip edge. The flat shoulder requires slicer
support when printed in the packaged orientation, as requested.

## Validation

Every one of the four systems passed:

- valid one-solid STEP for all six mechanical parts;
- watertight one-component STL and 3MF outputs;
- one 3MF build item and verified first-layer contact;
- final-solid helical-face presence for every declared thread;
- zero lens-to-mechanical and holder-to-cap interference;
- at least `5 mm` lens-thread engagement;
- centered A/B/C axes and preserved B-axis shift;
- catalog-EFL optical-vertex spacing and complete `4f + seat` paths;
- clear A/B/C optical cores and clear C receiver;
- exact source A input receiver preservation;
- byte-identical local and Nutstore run folders.

Focused evidence renders are included in each run:

- `renders/openhi_4f_c_lens_thread_section.png`
- `renders/openhi_4f_b_c_straight_camera_grips.png`

## Print-Ready Run

All four systems use:

`run-5-c-thread-straight-camera-grip-print-ready-20260901T143912Z`

Each run contains one-part `PRINT_THIS_*.step`, `PRINT_THIS_*.stl`, and
`PRINT_THIS_*.3mf` files, the reference assembly, lens model, manifests,
builder snapshot, and renders. The exact same run folders are mirrored under:

`/home/lachlan/Nutstore Files/Projects/LabCanvas/<design>/`

## Reprint Decision

For any system printed from run 4:

- reprint `Lens_C_holder` and `C`; the run-4 C lens pair was smooth rather than
  threaded;
- reprint `B` only when the new straight output grip is wanted;
- `A_C_BS`, `Lens_B_holder`, and `A` do not need reprinting for this specific
  correction;
- use the matching run-5 parts from one lens system only; do not mix focal
  variants.

The C cap already needs reprinting for its restored lens thread, so its new
straight output grip comes with that required replacement.

## Reusable Commands

Regenerate one system with the repository CAD kernel:

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/openhi_4f_jh042_same_lens/build_jh042_openhi_4f.py \
  --no-sync
```

Render the assembly, print layout, A sections, C thread section, and B/C grip
evidence:

```bash
blender --background \
  --python cad/tools/render_openhi_same_lens_4f.py \
  -- \
  --design-dir cad/designs/openhi_4f_jh042_same_lens
```

Package and sync one or more checked systems:

```bash
cad/.conda/cad-python/bin/python \
  cad/tools/package_openhi_same_lens_4f_print_release.py \
  --design-dir cad/designs/openhi_4f_jh042_same_lens
```

The packager refuses any manifest with a failed check, revalidates each
print-oriented STEP/STL/3MF, and copies the complete run folder to Nutstore.
