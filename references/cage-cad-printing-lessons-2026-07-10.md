# Cage CAD and 3D Printing Lessons

Date: 2026-07-10

This note records the practical design rules learned from the recent cage sample
holder, 100 mm rod dock, and 50 mm rod runs. Use it when creating new optical
cage fixtures, sample holders, broad flat bases, or Shapr3D handoff STEP files.

## Designs Covered

- `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35`
- `cad/designs/cage_rod_dock_100mm_base_10mm_holes`
- `cad/designs/cage_rods_50mm_m6`

Key print-ready Nutstore handoff folder:

```text
/home/lachlan/Nutstore Files/Projects/LabCanvas/
```

For the sample holder, the organized print folders are:

```text
.../cage_sample_holder_two_piece_lock_slide_petri35/run-4-thin-0p5mm-direct-corner-ears-print-ready/
.../cage_sample_holder_two_piece_lock_slide_petri35/run-5-full-corner-diagonal-ears-print-ready/
```

## Cage Geometry

- Standard cage rod centers are `x/y = +/-15 mm` from the optical or sample
  center, giving a `30 mm` cage square.
- Nominal rods are `6 mm` diameter.
- Printed rod sockets should usually use `6.4 mm` diameter as the first fit
  attempt.
- Do not move cage rod holes toward the outer corners of a wide holder. Keep
  the cage datum independent from the holder outline.

## Rods

The `cage_rods_50mm_m6` design treats "M6 rod" as a smooth `6 mm` cage rod, not
as a modeled helical thread. The direct-use rod is:

```text
cad/designs/cage_rods_50mm_m6/USE_THIS_cage_rods_50mm_m6_smooth_rod.step
```

If a screw connection is needed, use the separate M3 pilot variant or a real
metal M6 threaded rod. Avoid modeled helical threads in Shapr-target files unless
the thread itself is the experiment.

For batch printing, output a clean 5x5 grid of 25 rods in the current print
orientation. The grid should have no dock, no visual rod proxies, and no extra
reference bodies. Provide STEP, STL, and 3MF forms with `PRINT_THIS_` prefixes.

## Anti-Warp Ears

Broad, flat printed parts should get removable ears by default. Run-4 and run-5
showed the difference:

- Run-4: thin `0.5 mm` Z-thick ears with side pulls. Good, but the pull mostly
  acts along the two adjacent edges.
- Run-5: side pulls plus a direct diagonal bridge from the true corner to the
  outer tail pad. This also pulls the actual corner outward along the diagonal.

Preferred ear pattern after the first dock/sample-holder print feedback:

- Use stronger sacrificial Z thickness by default, usually `0.8-1.0 mm`.
  Use `0.5 mm` only when the user explicitly prioritizes easy removal.
- Use a small breakaway overlap into the part edge, around `0.35 mm`.
- Add two side contacts for edge hold-down.
- Add one diagonal neck/tail from the real corner for diagonal corner hold-down.
- Make the outer tail pad wider and larger than the neck so it grips the print
  bed more strongly.
- Keep ears in a print-specific export; the assembled/reference files can keep
  the same geometry for checking, but the print layout should be the file to
  slice.

The 2026-07 dock print showed that the ear concept works, but the earlier thin
ears should be made stronger, thicker, and larger in future broad flat prints.

## Run and Sync Convention

Keep one design folder per project. For each major change, archive a complete
run under:

```text
runs/run-N-human-readable-info-YYYYMMDDTHHMMSSZ/
```

The root `artifacts/` directory remains the latest checked output. If a user is
ready to print, also create a clean Nutstore folder, for example:

```text
.../LabCanvas/<design-name>/run-N-short-name-print-ready/
```

Include at minimum:

- `PRINT_THIS_*.stl`
- `PRINT_THIS_*.step`
- `PRINT_THIS_*.3mf`
- separate `bottom_part.step` and `top_part_180deg_print.step` when applicable
- a render PNG for quick visual confirmation

The 3MF can be generated from the validated STL when the CAD kernel cannot write
3MF directly. Keep millimeter units and verify that the 3MF zip contains
`3D/3dmodel.model`.

## Shapr3D Safety

For Shapr-friendly STEP files:

- Prefer analytic boxes, cylinders, chamfers, and simple polygon extrusions.
- Avoid helixes, thread sweeps, fragile fill-and-recut booleans, and unnecessary
  B-spline faces.
- Validate every important output by re-importing STEP, checking solid count,
  bounding box, BRep validity, STL watertightness, and B-spline face count.
- A good Shapr-target fixture should normally have `bspline_faces=0`.

Recent validation targets:

- rods: `6 x 6 x 50 mm`, valid one-solid smooth rod
- dock with ears: valid one-solid dock, `164 x 164 x 30 mm` including ears
- sample holder run-5 print layout: valid two-solid print layout,
  `161 x 213 x 31.2 mm`

## Completion Checklist

Before reporting a CAD print design as ready:

1. Generate STEP, STL, manifest, README, and render PNG.
2. Generate 3MF for the direct print file when a slicer-ready handoff is useful.
3. Validate STEP import, BRep validity, solid count, bbox, STL watertightness,
   3MF zip structure, and B-spline face count.
4. View at least one render or top-view image.
5. Sync direct-use STEP files and print-ready folders to Nutstore.
6. Commit only the relevant design files; do not stage unrelated CAD archives.
7. Push and confirm GitHub Actions status when the repo workflow runs.
