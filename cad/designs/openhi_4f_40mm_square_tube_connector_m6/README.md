# OpenHI 4F 40 mm Square Tube Connector With Eight M6 Set Screws

This clean parametric connector joins two measured `39.8 mm` OpenHI 4F tubes.
The connector is `42 x 42 x 62 mm`, with a `40.0 mm` bore and eight radial
M6-class printed set screws.

## Geometry

- Tube axis / print axis: `Z`.
- Connector envelope: `42 x 42 x 62 mm`.
- Bore: `40.0 mm`; measured tube: `39.8 mm`.
- Fit: `0.2 mm` diametral / `0.1 mm` radial clearance.
- Center stop: a `2.0 mm` inward annular ridge at `z=31 mm`.
- The stop is a triangular cross-section with straight `45 degree` chamfers:
  bore `40 -> 36 -> 40 mm` over `z=29 -> 31 -> 33 mm`.
- Optical opening remains `36 mm`; the stop is not a blocking disk.
- Eight radial threaded holes: four at `z=15.5 mm`, four at `z=46.5 mm`.
- The holes are offset `14.5 mm` toward the corners. This preserves
  `4.6369 mm` minimum
  material across the full M6 crest and
  `7.225 mm` at each hole
  centerline. A centered face hole would have only `1 mm` wall.

## Threads

- Female: M6-class right-hand, `1.0 mm` pitch, `5.0 mm` pilot/root,
  `6.0 mm` cutter crest.
- Male screw: `5.8 mm` crest (`0.2 mm` diametral reduction), `4.8 mm` root,
  `12 mm` threaded length.
- Triangle profile: `0.58 mm` base, `0.5 mm` radial tooth height.
- Both cutters and male threads are swept an extra half pitch beyond each end,
  then clipped to the exact parent length. Threads reach both end planes but
  create no overflow bodies.
- Head: printed hex, `10 mm` across flats, `4 mm` high.

Horizontal printed M6 holes can be rough depending on layer height and cooling.
The main print file contains real helical threads. A separate tap-ready STEP/STL
uses only `5.0 mm` pilot holes so an M6 x 1.0 metal tap can clean or replace the
printed female thread without changing the connector envelope.

## Direct Print Files

- `PRINT_THIS_openhi_4f_40mm_square_tube_connector_m6_threaded_connector.step/.stl/.3mf`: one connector,
  printed upright on a `42 x 42 mm` end face.
- `PRINT_THIS_openhi_4f_40mm_square_tube_connector_m6_8x_set_screws.step/.stl/.3mf`: eight screws in a `4 x 2`
  grid, heads on the build plate.
- `PRINT_THIS_openhi_4f_40mm_square_tube_connector_m6_single_set_screw.step/.stl/.3mf`: one fit-test screw.
- `USE_THIS_openhi_4f_40mm_square_tube_connector_m6_threaded_connector.step`: editable threaded connector.
- `USE_THIS_openhi_4f_40mm_square_tube_connector_m6_tap_ready_connector.step`: smooth `5.0 mm` pilot version.
- `USE_THIS_openhi_4f_40mm_square_tube_connector_m6_fit_check_assembly.step`: connector, two tube proxies, and
  eight screws as separate assembly solids.

## Validation

- Threaded connector STEP: `1`
  valid solid; bbox `[42.0, 42.0, 62.0] mm`.
- Printable helical STEP topology: `218`
  faces, including `120`
  B-spline faces from real helices.
- Tap-ready Shapr STEP topology: `18`
  faces and `0` B-spline
  faces; use this file when fast, clean downstream editing matters.
- Threaded connector STL: watertight
  `True`; components
  `1`.
- Eight-screw print grid STEP: `8`
  solids; STL components `8`.
- Connector 3MF valid: `True`.
- Screw-grid 3MF valid: `True`.

Print one screw first and test it in one hole. If the screw is too tight, clean
the female hole with an M6 x 1.0 tap; do not scale either part.
