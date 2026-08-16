# OpenHI A/B/C Exact Parametric Baseline

Date: 2026-08-16

This note records the exact regeneration of the three current OpenHI bodies:

- `cad/extracted/OpenHI_STEP/A.step`
- `cad/extracted/OpenHI_STEP/B.step`
- `cad/extracted/OpenHI_STEP/C.step`

The output project is:

```text
cad/designs/openhi_abc_exact_parametric_baseline/
```

No dimensions, pivots, threads, chamfers, lens seats, placements, or body
topology were changed in this baseline. It is the stable starting point for
future local fit variants.

## Source Authority

`cad/extracted/OpenHI.shapr` was inspected for identity and design-history
evidence. Its archive contains imported bodies rather than a replayable native
feature tree:

- revision ID: `9`
- `Shapes`: `0`
- `SketchControllers`: `3`
- `HistoryImportedBodies`: `77`
- `HistoryTreeNodes`: `102`

Therefore, the flattened STEP bodies are the exact geometry authority on
Ubuntu. Reconstructing the complete parts from visual measurements would be
less exact than preserving and round-tripping their existing B-reps.

The previously accepted regeneration work for `A+ C + BS.step`,
`Lens B holder.step`, and `Lens C holder.step` was used as the implementation
reference. This baseline follows the same rules: preserve the accepted B-rep,
name the physical fit parameters, isolate future thread edits, and validate the
exported file after STEP re-import.

## Original Thread Parameters

The exact source family uses:

- pitch: `0.8 mm`
- radial tooth height: `0.4 mm`
- crest/pivot diameter difference: `0.8 mm`
- thread hand: right-hand

Current source pivots and crests:

| Interface | Pivot | Crest |
| --- | ---: | ---: |
| A top male | 29.8 mm | 30.6 mm |
| B lens male | 29.6 mm | 30.4 mm |
| B camera male | 24.4 mm | 25.2 mm |
| C lens male | 29.6 mm | 30.4 mm |
| C camera male | 24.4 mm | 25.2 mm |

The builder exposes each pivot as a named argument. With the defaults used in
this run, it preserves every source solid. A future changed argument rebuilds
only the corresponding helical tooth and root sleeve region; it does not
redraw or globally scale the surrounding part.

## Exact Geometry Evidence

| Part | Solids | Faces | Bounding box | Source volume | Round-trip volume delta |
| --- | ---: | ---: | --- | ---: | ---: |
| A | 3 | 24 | 40.0000002 x 40.0000002 x 50.0000001 mm | 31633.375958322 mm3 | 0.000012859 mm3 |
| B | 4 | 41 | 40.0 x 40.0 x 54.400000085 mm | 34853.533699355 mm3 | 0.011412917 mm3 |
| C | 4 | 38 | 54.0000001 x 40.0 x 40.0 mm | 34854.531947972 mm3 | 0.000020741 mm3 |

For all three outputs:

- source and output B-reps pass `BRepCheck_Analyzer`;
- minimum, maximum, and bounding-box size are unchanged;
- solid, shell, face, edge, and surface-type counts are unchanged;
- every separately tessellated source solid is watertight;
- each 3MF is a valid ZIP package with one object per B-rep solid;
- the rendered full views show the expected threads, shoulders, chamfers, and
  asymmetric C-body layout.

The small volume/area deltas are STEP serialization tolerance on helical
B-spline surfaces, not deliberate geometry edits. The acceptance threshold is
strict enough to reject a real dimensional change while allowing the numeric
round trip.

## Why Meshes Are Exported Per Solid

The source STEP compounds intentionally keep helical tooth bodies and their
root/main bodies as separate touching solids. If the whole compound is
tessellated and treated as one fused mesh, shared interfaces can look
non-manifold even though each source solid is valid and watertight.

The reusable exporter therefore:

1. imports and validates the exact STEP compound;
2. tessellates each B-rep solid independently;
3. verifies every component is watertight;
4. concatenates the components into the requested STL without changing their
   placement;
5. writes a multi-object 3MF that preserves one object per source solid.

This avoids destructive boolean fusion and preserves the original split-thread
semantics used by Shapr3D.

That source-coordinate package is evidence/editing data, not the default Qidi
Studio handoff. The first export retained the original OpenHI assembly
coordinates (`Z` around 480-724 mm) and exposed each source solid as a separate
3MF object. Qidi Studio correctly warned about multiple parts and then found an
empty initial layer.

The corrected print contract is separate:

- rigidly move A and B to `Z=0` without changing their thread axes;
- rotate C from its source assembly X axis onto print Z, then move it to `Z=0`;
- boolean-union the overlapping tooth/root solids into one valid watertight
  print B-rep without changing the exterior envelope;
- package that one physical solid as one 3MF model object and one build item;
- verify `min_z_mm == 0`;
- verify triangles intersect the first `0.2 mm` layer;
- verify the serialized STL is one watertight component;
- compare the print STEP to the fused source envelope under a rigid-transform
  invariant.

The run-2 print validation found `1227`, `553`, and `553` first-layer triangles
for A, B, and C respectively. Every print 3MF has exactly one object and one
build item.

One source runout contains a zero-area half-pitch extremum. A triangle mesh can
miss that mathematical point by up to `0.4 mm` on one axis while the STEP B-rep
retains it exactly. The STEP is therefore the geometry authority; STL and 3MF
are printable tessellations.

## Reusable Commands

Build and validate the unchanged baseline:

```bash
cad/.conda/cad-python/bin/python3.11 \
  cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py
```

Render all three bodies and the overview:

```bash
blender --background --python \
  cad/designs/openhi_abc_exact_parametric_baseline/render_openhi_abc_exact_parametric_baseline.py
```

Refresh the run handoff and Nutstore copy after rendering:

```bash
cad/.conda/cad-python/bin/python3.11 \
  cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py \
  --sync-only \
  --run-name run-2-qidi-single-object-build-plate-20260816T135323Z
```

Example future fit variant, not used in this baseline:

```bash
cad/.conda/cad-python/bin/python3.11 \
  cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py \
  --b-lens-pivot 29.8 \
  --run-name run-3-b-lens-pivot-29p8-YYYYMMDDTHHMMSSZ
```

Always use a new run name for a geometry change. Never overwrite the extracted
STEP sources or call a pivot variant an exact baseline.

## Direct Outputs

The unambiguous editable files at the design root are:

```text
USE_THIS_OpenHI_A_exact_current_geometry.step
USE_THIS_OpenHI_B_exact_current_geometry.step
USE_THIS_OpenHI_C_exact_current_geometry.step
```

The files intended for Qidi Studio are:

```text
PRINT_THIS_OpenHI_A_exact_current_geometry.step
PRINT_THIS_OpenHI_A_exact_current_geometry.stl
PRINT_THIS_OpenHI_A_exact_current_geometry.3mf
PRINT_THIS_OpenHI_B_exact_current_geometry.step
PRINT_THIS_OpenHI_B_exact_current_geometry.stl
PRINT_THIS_OpenHI_B_exact_current_geometry.3mf
PRINT_THIS_OpenHI_C_exact_current_geometry.step
PRINT_THIS_OpenHI_C_exact_current_geometry.stl
PRINT_THIS_OpenHI_C_exact_current_geometry.3mf
```

The complete checked run is:

```text
cad/designs/openhi_abc_exact_parametric_baseline/runs/
run-2-qidi-single-object-build-plate-20260816T135323Z/
```

The same handoff is synchronized to:

```text
/home/lachlan/Nutstore Files/Projects/LabCanvas/
openhi_abc_exact_parametric_baseline/
```

Use `USE_THIS_*.step` for Shapr3D editing and geometric authority. Use
`PRINT_THIS_*.3mf` in Qidi Studio; the print 3MF is preferred because its
single-object build contract is explicit. The previous multi-object files are
retained in run 1 as provenance, not as the latest slicer inputs.
