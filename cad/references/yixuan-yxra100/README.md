# Yixuan YXRA100 Supplier References

Supplier: Beijing Yixuan Motion Control Technology Co., Ltd.

Public customer library: <https://a590136ec28bee41f.bj6.agentos-app.net>.
The library exposes read-only `/api/list` and `/api/file/ID/download` routes.
No administrator password, upload, account change, or login is needed to read
the product documents. `download_references.py` retrieves the exact catalog
entries, verifies their byte counts, and records SHA-256 values in
`downloads.json`. Original binary references remain local and ignored.

## Selected Purchased Variant

The selected device is the **40 mm / 100 W servo YXRA100**, not the 42 mm stepper
or the separate 57 mm motor model. Its authoritative references are:

- `YXRA100_100W_servo.step`: supplier assembly, including servo casing surfaces;
- `YXRA100_40_servo_specification.pdf`: dimension drawing, revision V2.3,
  updated 2023-11-10.

The additional standard/42PUL/57 mm files are retained for identification only.
Do not substitute their motor envelope when making the servo fixture.

## Verified Interface Geometry

- Rotating table: diameter 100 mm.
- Stationary mounting base: 100 x 110 mm.
- Overall stage height: 45 mm.
- Optical through-aperture: diameter 30 mm.
- Three stationary-base holes: diameter 6.5 mm, counterbore diameter 10.5 mm,
  counterbore depth 25 mm. They form an asymmetric pattern, not a 25 mm grid.
- Rotating face: twelve M6 taps on the documented 12.5/25 mm layout.
- Bottom 63 x 63 mm M4 pattern is shown in the drawing but is not used by the
  fixture; the three through holes are directly measured in the supplied STEP.

The servo STEP contains five closed solids and open surface shells for parts
of the motor. Preserve them for visualization/reference; do not claim that the
entire purchased device is a single watertight printable solid. The separate
57 mm motor file contains no closed solids and is not the design baseline.

The catalog's file names and selected dimensions identify the model; some
internal legacy STEP names refer to a different historical export name.
Never infer dimensions or product identity from the internal name alone.

## Breadboard Interface

The fixture assumes a metric M6 breadboard on 25 mm centers. This convention
is documented by [Thorlabs](https://www.thorlabs.com/newgrouppage9.cfm?objectgroup_ID=1861),
but the particular laboratory table still needs physical confirmation. The
fixture uses M6 clearance slots; the actual threads are in the breadboard.

The supplied ITF RTH-ITF link concerns research-talent funding, not stage
geometry. It was reviewed separately and is not used as engineering evidence:
<https://www.itf.gov.hk/en/funding-programmes/nurturing-talent/research-talent-hub/research-talent-hub-for-itf-projects-rth-itf-/index.html>.
