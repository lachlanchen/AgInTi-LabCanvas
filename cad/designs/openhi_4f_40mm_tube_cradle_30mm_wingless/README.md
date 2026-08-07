# OpenHI 4F 40 mm Compact Wingless Tube Cradle

Run 1 derives a compact 30 mm-long cradle from the accepted 50 mm wingless
geometry and combines it with the stronger four-corner anti-warp ears from run
3. The optical-table wings and M6 mounting holes are intentionally absent. The
clean Shapr3D STEP has no sacrificial tabs.

## Geometry

- Tube axis: along the `30 mm` holder length.
- Complete clean cradle envelope: `30 x 40 x 15 mm`.
- Tube seat: `40.2 mm` diameter, giving `0.2 mm` diametral / `0.1 mm` radial
  clearance around a nominal `40.0 mm` tube.
- Minimum material directly under the tube: `2.0 mm`.
- Maximum side shoulder height: `15.0 mm`.
- Flat top shoulder remaining at each outer edge: about `1.1957 mm`.
- No side wings or flanges.
- No M6 mounting holes.
- Bottom: fully flat. Print with the concave seat facing upward.

The `15 mm` dimension is the total overall height. The `2 mm` floor is included
inside that envelope, so the part is not `17 mm` high.

The slightly oversize seat compensates for printed fit while retaining the same
circular profile as the tube. The tube proxy rests at the bottom tangent point;
the clearance is above and beside it rather than underneath it.

## Print Files

- `PRINT_THIS_openhi_4f_40mm_tube_cradle_30mm_wingless_single.stl/.step/.3mf`: exactly one holder with four
  removable corner ears; print this set.
- `USE_THIS_openhi_4f_40mm_tube_cradle_30mm_wingless.step`: editable single-holder handoff for Shapr3D.
- `USE_THIS_openhi_4f_40mm_tube_cradle_30mm_wingless_top_render.png`: top check of the compact wingless outline.

Each corner ear is `1.0 mm` thick. It contacts both
adjacent edges, includes a diagonal corner pull, and ends in a wider pad. Cut or
peel the ears away after printing. The single print layout measures
`68.0 x 78.0 x 15.0 mm`.

## Validation

- Clean holder STEP: `1` valid
  solid, bounding box `[30.0, 40.0, 15.0] mm`, volume
  `7342.5212 mm3`.
- Direct-print STEP: `1` valid solid,
  bounding box `[68.0, 78.0, 15.0] mm`.
- Direct-print STL: watertight `True`,
  component count `1`.
- Direct-print 3MF ZIP: `True`.

Physically test one holder before relying on the fit. If the tube is too loose
or tight, revise only `seat_diameter_mm`; do not scale the whole model.
