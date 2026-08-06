# OpenHI 4F Square Tube Connector CAD Handoff

Date: 2026-08-06

This note records the reusable CAD method used for the OpenHI 4F connector and
the earlier Shapr3D/OpenHI reconstruction work. It is intended for another
Codex session or another workstation that must regenerate, inspect, or revise
the design without relying on chat history.

## Current Design

Project:

```text
cad/designs/openhi_4f_40mm_square_tube_connector_m6/
```

The part joins two nominal 40 mm OpenHI 4F tubes. The measured tube diameter is
about 39.8 mm.

| Feature | Value |
| --- | ---: |
| Connector envelope | 42 x 42 x 62 mm |
| Tube bore | 40.2 mm |
| Measured tube | 39.8 mm |
| Diametral fit clearance | 0.4 mm |
| Center stop location | z = 31 mm |
| Center stop radial projection | 2.1 mm (derived; 36 mm throat unchanged) |
| Center stop open aperture | 36 mm |
| Center stop axial base | 4 mm |
| Fasteners | 8 radial M6 x 1.0 positions |
| Fastener stations | z = 15.5 and 46.5 mm |
| Printed bolt crest | 5.8 mm |
| Printed bolt root | 4.8 mm |

The user's phrase "straight fillet" means a **chamfer** or **bevel**. A fillet
is rounded; a chamfer is a straight sloped face.

## Datum And Geometry

- Tube and print axis: Z.
- Square body center: x = 0, y = 0.
- Tube stop plane: z = 31 mm.
- Lower tube enters from z = 0; upper tube enters from z = 62 mm.
- The stop is an annular triangular ridge, not a disk:
  - bore 40.2 mm at z = 29;
  - bore 36 mm at z = 31;
  - bore 40.2 mm at z = 33.
- The two 45-degree chamfers avoid an unsupported internal right-angle shelf
  when the connector prints upright along the tube axis.

The 42 mm square around a 40.2 mm bore gives only 0.9 mm face wall at each face
center. An M6 thread cannot be placed at a face center and retain useful
engagement. The eight radial fasteners are therefore offset tangentially by
14.5 mm toward the corners. The validated design retains:

- 4.6369 mm minimum material over the full M6 crest;
- 7.2250 mm material at the thread centerline;
- 3.5 mm outer ligament from thread crest to the adjacent square edge.

This is a general rule: calculate wall engagement across the complete hole
radius, not only at the hole centerline.

## Bounded Helical Threads

Use a local thread coordinate frame. In this design, each radial thread is
built along local +X and then rotated/translated to a body face.

For both male and female threads:

1. Build the root cylinder or pilot cylinder.
2. Sweep a triangular profile along a right-hand helix.
3. Extend the helix by half a pitch beyond both target endpoints.
4. Intersect the sweep with an exact clipping box for the intended thread
   length.
5. For female threads, union the bounded tooth sweep with the smooth pilot to
   make one cutter, then subtract it.
6. For male threads, union the bounded tooth sweep with the root cylinder.
7. Re-import the exported STEP and validate it. Do not trust only the in-memory
   CadQuery object.

The extra half-pitch construction runout prevents a missing first or last
tooth. The final clipping prevents thread overflow beyond the parent body.

This design uses:

```text
female pilot/root       5.0 mm
female cutter crest     6.0 mm
pitch                   1.0 mm
tooth radial height     0.5 mm
triangle base           0.58 mm
male root               4.8 mm
male crest              5.8 mm
male diametral reduction 0.2 mm
```

Print one bolt first. Horizontal printed female M6 threads can be rough even
when the CAD is correct. The build therefore exports both:

- a real-helical threaded connector;
- a tap-ready connector with smooth 5.0 mm pilot holes for an M6 x 1.0 tap.

## Shapr3D Lessons

The earlier OpenHI and Nature work established these rules:

1. Treat `.shapr` as evidence, not automatically as a replayable feature tree.
   Many archives contain imported Parasolid/B-rep bodies and operation labels
   without enough clean parameters for exact feature replay on Ubuntu.
2. Preserve an exact STEP baseline before making a print-fit variant.
3. Do not broadly fill and recut old threaded B-rep regions. That can leave
   sliver faces, internal shells, transparent regions, missing threads, and a
   long Shapr3D repair pass.
4. Rebuild a fragile receiver from simple analytic cylinders, cones, planes,
   and bounded cutters at a stable datum.
5. OCCT-valid is necessary but not sufficient for Shapr3D. Count solids,
   validate B-rep, check bounds and volume, inspect B-spline faces, import the
   exported STEP, and render it.
6. True helical threads create B-spline faces. Keep them for the printable
   artifact when required, but also provide a smooth/tap-ready or bounded
   ring-groove Shapr target when editability is more important.
7. Keep visual proxies separate from printable geometry. Tube proxies and
   inserted screws belong in the fit-check assembly, not in the connector STL.

## Export And Validation Contract

A serious print-ready run must contain:

- the parametric build script;
- the Blender technical-render script;
- one connector STEP/STL/3MF;
- one single fit-test bolt STEP/STL/3MF;
- the complete bolt-grid STEP/STL/3MF;
- the fit-check assembly STEP;
- a half-section STEP/STL and render;
- README and machine-readable manifest;
- full connector, fit, section, and exact print-layout renders.

Required checks:

- connector STEP imports as one valid B-rep solid;
- connector bbox is exactly 42 x 42 x 62 mm;
- connector STL is watertight and one component;
- bolt STEP is one valid solid;
- 4 x 2 bolt grid is eight solids/components;
- 3MF is a valid ZIP package with `3D/3dmodel.model`;
- point tests prove bore clearance, center-stop material, open aperture,
  threaded mouths, and retained corner material;
- final renders exist. Blender may return exit code 0 even after an embedded
  Python exception, so the build must check the expected PNG paths explicitly.

Blender Workbench with material colors, studio lighting, shadows, and cavity
shading is preferred for cross-version CAD inspection. It shows threads and
section geometry more reliably than a decorative dark Eevee render.

## Run And Nutstore Layout

Regenerate from the repository root:

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/openhi_4f_40mm_square_tube_connector_m6/\
  build_openhi_4f_40mm_square_tube_connector_m6.py
```

The source folder keeps the complete artifact set and a timestamped run. The
clean handoff is also copied to:

```text
/home/lachlan/Nutstore Files/Projects/LabCanvas/
openhi_4f_40mm_square_tube_connector_m6/<run-name>/
```

The Nutstore run must include the `PRINT_THIS_*` connector, eight-bolt grid,
single test bolt, README, manifest, and renders. It also gets an unambiguous
root connector STEP and fit-check assembly STEP for Shapr3D/LabCanvas import.

## Safe Revision Procedure

1. Read the current README and manifest.
2. Change named parameters only.
3. Preserve the 40.2 mm optical/tube bore and 42 x 42 envelope unless the user
   explicitly changes them.
4. Recompute fastener engagement if hole diameter, offset, bore, or envelope
   changes.
5. Rebuild all artifacts from source; do not edit the STL.
6. Inspect the full, assembled, section, and print-layout renders.
7. Re-run all validations.
8. Sync the checked run to Nutstore.
9. Commit only source, documentation, and repository-approved artifacts; leave
   unrelated dirty files untouched.
