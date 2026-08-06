# OpenHI C-Branch Slide/Petri Holder Handoff

Date: 2026-08-06

This note records the reusable method used for
`cad/designs/openhi_c_branch_slide_petri35_holder/`.

## Design Goal

Adapt the accepted two-piece slide and 33 mm Petri-dish holder to the upward C
branch of the OpenHI 4F system. Preserve the complete sample-facing geometry
and replace only the former lower cage-rod interface.

## Sources

- Accepted holder builder:
  `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/build_cage_sample_holder_two_piece_lock_slide_petri35.py`
- Measured reference:
  `cad/extracted/OpenHI_STEP/C.step`

The accepted builder remains the source of truth for the tray, slide recess,
Petri recess, optical opening, finger access, lock feet, top frame, chamber
gap, and anti-warp ears. The new build imports and calls those functions rather
than retyping their dimensions.

## Measured C-Branch Interface

The free C end in `C.step` has these useful axial regions:

- approximately 40 mm outer tube/shoulder;
- a 7.8 mm conical transition;
- a 24.4 mm plain nose/body;
- a separate thread envelope reaching approximately 25.2 mm;
- approximately 3.9 mm plain-nose length.

The user selected a non-threaded 25.0 mm ID receiver. The new adapter therefore
uses:

- 40.0 mm OD;
- 25.0 mm smooth ID for 5.0 mm;
- 7.8 mm taper;
- 39.0 mm taper mouth, leaving a 0.5 mm radial print lip;
- 18 mm optical through-opening;
- no generated thread.

The 25.0 mm ID is intentionally tighter than the measured 25.2 mm thread crest.
The design includes a small 25 mm fit coupon so the physical printer/part fit
can be checked before printing the full holder.

## Decoupled Architecture

The adapter and tray are separate solids:

- tray underside pocket: 38.2 mm ID by 2.2 mm depth;
- adapter registration spigot: 38.0 mm OD by 2.0 mm height;
- 0.2 mm diametral and 0.2 mm axial allowance;
- adhesive or another later user-selected retention method after fit checking.

This avoids coupling an uncertain measured receiver to the proven sample tray.
If a physical test changes the socket diameter, only the small adapter needs to
be regenerated.

## Print Orientation

The adapter is flipped for printing: the registration-spigot/18 mm optical face
rests on the build plate and the 39 mm tapered mouth points upward. Printing
from the wide mouth would leave only a 0.5 mm first-layer annulus and is less
reliable.

The top frame uses the accepted 180-degree print orientation. The tray keeps the
accepted normal orientation and anti-warp ears.

## Validation Contract

The completed run checks:

- adapter is one valid B-rep solid;
- adapter bbox is exactly 40 x 40 x 14.8 mm;
- adapter has zero B-spline faces and no helical topology;
- tray, adapter, and coupon STLs are watertight;
- all 3MF ZIP packages are valid;
- the accepted top-frame STEP and regenerated top frame have identical bbox,
  solid count, and volume;
- the old four lower cage socket locations are now solid;
- slide, Petri, registration, socket, optical, wall, and mouth point probes pass;
- assembly, exploded, fit, section, and print-layout renders are inspected.

For fit visualization, transform the real C STEP to the optical axis, then
intersect it with a bounded 40.1 mm cylindrical region. This keeps the real
mating branch but excludes unrelated distant assembly bodies that would obscure
the render.

## Reuse Rule

When adapting a proven holder to a new mount:

1. Reuse the accepted feature functions for all geometry that must not change.
2. Remove only the obsolete interface operation.
3. Add a shallow, named registration feature.
4. Build the new measured interface as an independent body.
5. Provide a fit coupon for any uncertain physical diameter.
6. Keep reference hardware visualization-only.
7. Compare accepted and regenerated invariants before export.
