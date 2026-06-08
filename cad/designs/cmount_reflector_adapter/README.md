# C-Mount Reflector Adapter

This is a first editable draft for a 4f-system adapter: male C-mount-like thread on one side, hollow optical tube through the center, and a 20 x 20 x 20 mm internal reflector cube on the other side.

![C-mount reflector adapter cross-section](artifacts/adapter_cross_section.png)

## Files

- `cmount_reflector_adapter.scad`: parametric OpenSCAD model.
- `adapter_cross_section.svg`: dimension sketch for review.
- `artifacts/adapter_cross_section.png`: PNG preview generated from the SVG sketch.

## Key Parameters

- External thread default: `24.4 mm` major diameter, matching the local STEP reference label `Thread camera 24.4`.
- Nominal C-mount reference: `25.4 mm`, `32 TPI`, `0.79375 mm` pitch.
- Bore diameter: `20 mm`.
- Reflector cavity: `20 x 20 x 20 mm`.
- Cube wall: `3 mm`, giving a `26 x 26 x 26 mm` outside cube.
- Body cylinder diameter: `26 mm`, so the cylinder bottom and cube bottom lie on the same plane.

## Usage

Open the model in OpenSCAD:

```bash
openscad cad/designs/cmount_reflector_adapter/cmount_reflector_adapter.scad
```

Export when OpenSCAD is installed:

```bash
openscad -o output/cad/cmount_reflector_adapter.stl cad/designs/cmount_reflector_adapter/cmount_reflector_adapter.scad
```

Before printing the full device, print only the male thread section and test it against the target female C-mount. Tune `thread_major_d`, `thread_depth`, and `clearance` in small increments.

## Status

This is a mechanical draft, not a metrology-grade thread model. It is suitable for iterative 3D-print fitting. For machined metal, replace the approximate OpenSCAD thread with a proper 1.000"-32 UN-2A thread defined in CAD/CAM.
