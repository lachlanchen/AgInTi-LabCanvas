# OpenHI 4F 40 mm Tube Cradle, 50 mm Long

This is a new, clean parametric cradle for the `40 mm` OD OpenHI/4F tube. It is
not derived by editing any earlier holder.

## Geometry

- Tube axis: along the `50 mm` holder length.
- Holder envelope: `50 x 40 x 15 mm`.
- Tube seat: `40.2 mm` diameter, giving `0.2 mm` diametral / `0.1 mm` radial
  clearance around a nominal `40.0 mm` tube.
- Minimum material directly under the tube: `2.0 mm`.
- Maximum side shoulder height: `15.0 mm`.
- Flat top shoulder remaining at each outer edge: about `1.1957 mm`.
- Bottom: fully flat. Print with the concave seat facing upward.

The slightly oversize seat compensates for printed fit while retaining the same
circular profile as the tube. The tube proxy rests at the bottom tangent point;
the clearance is above and beside it rather than underneath it.

## Print Files

- `PRINT_THIS_openhi_4f_40mm_tube_cradle_50mm_single.stl/.step/.3mf`: one holder.
- `PRINT_THIS_openhi_4f_40mm_tube_cradle_50mm_2x2_print_grid.stl/.step/.3mf`: four separate holders with
  `5 mm` gaps; no connecting sprues.
- `USE_THIS_openhi_4f_40mm_tube_cradle_50mm.step`: editable single-holder handoff for Shapr3D.

The 2x2 layout measures `105 x 85 x 15 mm`. Anti-warp ears were intentionally
omitted because this compact part has a thick `15 mm` body and the requested
outline is simple. Add ears in a later run only if the physical print curls.

## Validation

- Single STEP: `1` valid solid,
  bounding box `[50.0, 40.0, 15.0] mm`.
- Single STL: watertight `True`, component
  count `1`.
- 2x2 STEP: `4` valid solids, bounding
  box `[105.0, 85.0, 15.0] mm`.
- 2x2 STL: watertight `True`, component count
  `4`.
- 3MF archives: single `True`, grid
  `True`.

Physically test one holder before relying on the fit. If the tube is too loose
or tight, revise only `seat_diameter_mm`; do not scale the whole model.
