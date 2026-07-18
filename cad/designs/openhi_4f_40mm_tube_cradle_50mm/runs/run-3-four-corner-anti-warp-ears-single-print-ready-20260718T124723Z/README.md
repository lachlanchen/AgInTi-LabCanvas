# OpenHI 4F 40 mm Tube Cradle With Optical-Table Wings

Run 3 preserves the accepted run-2 cradle geometry and adds removable anti-warp
ears only to the direct-print body. The clean Shapr3D STEP has no sacrificial
tabs.

## Geometry

- Tube axis: along the `50 mm` holder length.
- Main cradle envelope: `50 x 40 x 15 mm`.
- Overall table-mount envelope: `50 x 70 x 15 mm`.
- Tube seat: `40.2 mm` diameter, giving `0.2 mm` diametral / `0.1 mm` radial
  clearance around a nominal `40.0 mm` tube.
- Minimum material directly under the tube: `2.0 mm`.
- Maximum side shoulder height: `15.0 mm`.
- Flat top shoulder remaining at each outer edge: about `1.1957 mm`.
- Two integral mounting wings: `50 x 15 x 5 mm` each.
- Two M6 clearance bores: `6.4 mm` diameter, vertical through the wings.
- Hole centers: `(x, y) = (0, +/-25 mm)`, giving `50 mm` center spacing for a
  standard `25 mm` optical-table grid.
- Outer hole-edge ligament: `6.8 mm`; inner wing ligament: `1.8 mm`, backed by
  the full-height cradle sidewall.
- Bottom: fully flat. Print with the concave seat facing upward.

The slightly oversize seat compensates for printed fit while retaining the same
circular profile as the tube. The tube proxy rests at the bottom tangent point;
the clearance is above and beside it rather than underneath it.

## Print Files

- `PRINT_THIS_openhi_4f_40mm_tube_cradle_50mm_single.stl/.step/.3mf`: exactly one holder with four
  removable corner ears; print this set.
- `USE_THIS_openhi_4f_40mm_tube_cradle_50mm.step`: editable single-holder handoff for Shapr3D.
- `USE_THIS_openhi_4f_40mm_tube_cradle_50mm_mounting_pattern_top_render.png`: top check of both wings
  and the `50 mm` two-hole pattern.

Each corner ear is `1.0 mm` thick. It contacts both
adjacent edges, includes a diagonal corner pull, and ends in a wider pad. Cut or
peel the ears away after printing. The single print layout measures
`88.0 x 108.0 x 15.0 mm`.

## Validation

- Clean holder STEP: `1` valid
  solid, bounding box `[50.0, 70.0, 15.0] mm`, volume
  `19415.8362 mm3`.
- Direct-print STEP: `1` valid solid,
  bounding box `[88.0, 108.0, 15.0] mm`.
- Direct-print STL: watertight `True`,
  component count `1`.
- Direct-print 3MF ZIP: `True`.

Physically test one holder before relying on the fit. If the tube is too loose
or tight, revise only `seat_diameter_mm`; do not scale the whole model.
