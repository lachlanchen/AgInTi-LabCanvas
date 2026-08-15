# OpenHI Lens B Holder: 29.8 mm Upper Female Pivot

## Use This File

`USE_THIS_openhi_lens_b_holder_upper_female_29p8_pivot.step`

For a mesh handoff, use `USE_THIS_openhi_lens_b_holder_upper_female_29p8_pivot.3mf`. The smooth no-groove inspection/editing fallback is `USE_THIS_openhi_lens_b_holder_upper_female_29p8_pivot_smooth_editable.step`.

## Requested Change

This variant starts from the authoritative source B-rep:

`cad/extracted/OpenHI_STEP/Lens B holder.step`

Only the positive-Z, lens-side female receiver changes:

- female pivot/pilot diameter: `30.2 -> 29.8 mm`;
- female groove diameter: `31.0 -> 30.6 mm`;
- pitch: unchanged at `0.8 mm`;
- radial tooth height: unchanged at `0.4 mm`;
- tooth base: unchanged at `0.8 mm`;
- handedness: unchanged, right-hand;
- threaded axial length: unchanged at `7.75 mm`.

The source STEP remains untouched. `cad/extracted/OpenHI.shapr` was checked for assembly and body context; this Lens B body is imported geometry there, so the STEP B-rep is the exact geometric authority.

## Chamfer Logic

The original `25.5 mm` lens seat and both straight `45 degree` transitions are preserved logically:

- lens seat ends at `z = 650.0 mm`;
- lower transition is `25.5 -> 29.8 mm`, from `z = 650.0` to `652.15 mm`;
- female thread is from `z = 652.15` to `659.90 mm`;
- upper mouth is `29.8 -> 40.734 mm`, from `z = 659.90` to `665.367 mm`.

Changing the pivot by `-0.4 mm` while preserving the lens seat, top mouth, 45-degree slopes, and `7.75 mm` thread length moves both thread boundaries down by `0.2 mm`. This is intentional and avoids a discontinuity or thin shell at either end.

The helix is constructed for an extra `1.2 mm` at both ends and clipped back to the true thread interval. The thread therefore reaches both ends smoothly without overflowing into the chamfers or adjacent body.

## Preserved Geometry

The builder imports the original single-solid STEP, fills only the old receiver interior, and re-cuts only that bounded region. It preserves:

- the complete outer body and bounding box;
- the `25.5 mm` lens seat;
- the central bore;
- the two side pin holes;
- the oblique end sink/counterbore;
- all lower B-holder geometry;
- every feature outside the upper receiver envelope.

The manifest proves that all added and removed material is confined to the upper receiver, the exported STEP reopens as one valid OCCT solid, and the STL/3MF are one watertight consistently wound component.

## Fit Warning

A matching `29.8/30.6 mm` male root/crest has zero nominal profile clearance against this `29.8/30.6 mm` female pilot/groove. This is the requested tight-fit geometry. Test the printer/material fit before committing to the complete optical assembly.

## Outputs

- `artifacts/openhi_lens_b_holder_upper_female_29p8_pivot.step`: true helical B-rep.
- `artifacts/openhi_lens_b_holder_upper_female_29p8_pivot.stl`: checked watertight mesh.
- `artifacts/openhi_lens_b_holder_upper_female_29p8_pivot.3mf`: checked one-object 3MF.
- `artifacts/openhi_lens_b_holder_upper_female_29p8_pivot_smooth_editable.step`: same body and pivot without helical groove.
- `artifacts/openhi_lens_b_holder_upper_female_29p8_pivot_receiver_cutters.step`: decomposed receiver operation for inspection.
- `artifacts/manifest.json`: dimensions, hashes, measured geometry, and all validation gates.
- `artifacts/*_render.png`: full, thread-detail, and cutaway renders.
- `runs/run-1-upper-female-29p8-pivot-20260815T041551Z/`: reproducible accepted run package.

## Rebuild

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/openhi_lens_b_holder_upper_female_29p8_pivot/build_openhi_lens_b_holder_upper_female_29p8_pivot.py

blender --background --python \
  cad/designs/openhi_lens_b_holder_upper_female_29p8_pivot/render_openhi_lens_b_holder_upper_female_29p8_pivot.py

cad/.conda/cad-python/bin/python \
  cad/designs/openhi_lens_b_holder_upper_female_29p8_pivot/build_openhi_lens_b_holder_upper_female_29p8_pivot.py \
  --package-only
```

The package step also syncs the accepted run and direct `USE_THIS_*` STEP/3MF files to `/home/lachlan/Nutstore Files/Projects/LabCanvas`.
