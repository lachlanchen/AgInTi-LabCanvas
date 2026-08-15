# OpenHI Lens C Holder: Right Female 29.8 mm Pivot

This is a narrow print-fit variant of
`cad/extracted/OpenHI_STEP/Lens C holder.step`. It changes only the
positive-X female receiver from a `30.2 mm` pivot and `31.0 mm` groove to a
`29.8 mm` pivot and `30.6 mm` groove.

The STEP export is the authoritative B-rep. `cad/extracted/OpenHI.shapr`
confirms the Lens C body context, but stores this geometry as imported bodies
rather than a recoverable native feature history.

## Preserved Geometry

- The complete negative-X `Thread BS` male tooth solid is reused unchanged.
- The negative-X male root remains `29.8 mm`; its crest remains `30.6 mm`.
- The `25.5 mm` lens seat remains unchanged at `x=324.5..325.0 mm`.
- The `24.0 mm` center bore, `40.0 mm` outside envelope, and every source
  feature through `x=325.0 mm` remain unchanged.
- Thread pitch remains `0.8 mm`, radial tooth height remains `0.4 mm`, and
  threaded length remains `7.75 mm`.

## Revised Right Receiver

| Feature | Source | This variant |
| --- | ---: | ---: |
| Female pivot / land | `30.2 mm` | `29.8 mm` |
| Female groove maximum | `31.0 mm` | `30.6 mm` |
| Lens-side 45-degree transition | `x=325.00..327.35` | `x=325.00..327.15` |
| Threaded interval | `x=327.35..335.10` | `x=327.15..334.90` |
| Mouth 45-degree transition | `x=335.10..340.00` | `x=334.90..340.00` |

The receiver is rebuilt cleanly from the lens-seat datum instead of broadly
filling and recutting the old helical B-rep. The female cutter is constructed
beyond both ends and clipped to the exact thread interval, preventing thread
overflow and fragile internal shell remnants.

## Use These Files

- `USE_THIS_openhi_lens_c_holder_right_female_29p8_pivot.step`: checked
  threaded two-solid source structure for Shapr3D and assembly use.
- `USE_THIS_openhi_lens_c_holder_right_female_29p8_pivot.3mf`: direct slicer
  handoff containing the two closed source shells.
- `USE_THIS_openhi_lens_c_holder_right_female_29p8_pivot_smooth_editable.step`:
  right receiver without its helical groove, while retaining the source left
  male geometry.
- `artifacts/openhi_lens_c_holder_right_female_29p8_pivot_preserved_left_male.step`:
  exact preserved male reference body.
- `artifacts/openhi_lens_c_holder_right_female_29p8_pivot_receiver_cutters.step`:
  transition, pilot, bounded helical groove, and mouth cutters.

## Validation

The builder rejects the output unless all of these checks pass after STEP,
STL, and 3MF round trips:

- two source solids and the `50 x 40 x 40 mm` envelope are preserved;
- all material deltas are confined to the positive-X receiver;
- the right receiver probes as `29.8/30.6 mm` with no remaining `30.2 mm`
  land;
- the receiver helix has the same hand and pitch as the source STEP;
- both 45-degree transitions meet the revised thread interval;
- the left male bbox, radial probe, and source topology are unchanged;
- both printable mesh shells are closed and winding-consistent;
- the STEP is OCCT-valid and the 3MF bounds match the STL.

The requested `29.8/30.6 mm` female profile has zero nominal diameter
clearance against a `29.8/30.6 mm` male. Confirm the physical printer and
material fit before committing to a complete optical assembly.

## Rebuild

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/openhi_lens_c_holder_right_female_29p8_pivot/build_openhi_lens_c_holder_right_female_29p8_pivot.py

blender --background --python \
  cad/designs/openhi_lens_c_holder_right_female_29p8_pivot/render_openhi_lens_c_holder_right_female_29p8_pivot.py

cad/.conda/cad-python/bin/python \
  cad/designs/openhi_lens_c_holder_right_female_29p8_pivot/build_openhi_lens_c_holder_right_female_29p8_pivot.py \
  --package-only
```
