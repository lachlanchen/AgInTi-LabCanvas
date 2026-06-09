# C-Mount Reflector Adapter Scale Reference

Date: 2026-06-09

## Source Files

- Design source: `cad/designs/cmount_reflector_adapter/cmount_reflector_adapter.scad`
- Design notes: `cad/designs/cmount_reflector_adapter/README.md`
- Local STEP research: `cad/research/openhi_nature_step_notes.md`
- Visual previews: `cad/designs/cmount_reflector_adapter/artifacts/`

## Coordinate System

All dimensions are millimetres. The optical axis runs along `X`.

- `X = 0`: front face of the male C-mount-like thread.
- `Y = 0`: horizontal centerline.
- `Z = 0`: flat bottom plane shared by cylinder and cube.
- Optical axis: `Y = 0`, `Z = 13`.

## 1:1 Scale Table

| Feature | Value | Notes |
| --- | ---: | --- |
| Total model length | `49.5 mm` | `5.5 + 18 + 26` |
| Thread section length | `5.5 mm` | First printable draft |
| Body cylinder length | `18 mm` | Between thread and cube |
| Cube outside | `26 x 26 x 26 mm` | 20 mm cavity plus 3 mm walls |
| Cube inside | `20 x 20 x 20 mm` | Reflector pocket |
| Wall thickness | `3 mm` | Cube walls |
| Body cylinder outside diameter | `26 mm` | Makes bottom coplanar with cube |
| Optical bore diameter | `20 mm` | Continuous through cylinder into cube |
| Printed thread major diameter | `24.4 mm` | Inferred from local STEP `Thread camera 24.4` |
| Nominal C-mount major diameter | `25.4 mm` | 1 inch nominal |
| C-mount pitch | `0.79375 mm` | 32 TPI |
| Axis height above bottom | `13 mm` | Half of 26 mm outside diameter |
| Thread root overlap | `0.12 mm` | Fuses printable thread into core |
| Join overlap | `0.2 mm` | Fuses thread/body/cube at face joins |

## Generated Artifacts

| Artifact | Purpose |
| --- | --- |
| `artifacts/cmount_reflector_adapter.stl` | OpenSCAD-exported printable mesh |
| `artifacts/cmount_reflector_adapter.blend` | Blender render scene |
| `artifacts/adapter_render_blender.png` | Full 3D render preview |
| `artifacts/adapter_render_3d.png` | Lightweight annotated 3D preview |
| `artifacts/adapter_render_full_scale.png` | Zoomed-out scale preview |
| `artifacts/adapter_cross_section.png` | Dimension sketch |

Mesh validation with Trimesh:

```text
watertight: true
connected components: 1
bounds: 49.5 x 26.0 x 26.0 mm
```

## Print Check

Before printing the whole adapter, print a short male-thread coupon using:

- `thread_major_d = 24.4 mm`
- `thread_pitch = 0.79375 mm`
- `thread_depth = 0.42 mm`

Tune `thread_major_d` in `0.1 mm` steps if the fit is too tight or too loose. Do not scale the whole model to fix thread fit, because that would also change the 20 mm optical bore and reflector pocket.

## Reference Evidence

Local STEP names show these thread clues:

- `OpenHI_STEP/C.step`: `Thread camera 24.4`, `Thread lens 29.6`
- `OpenHI_STEP/B.step`: `Thread camera 24.4`, `Thread lens 29.6*`
- `OpenHI_STEP/Collimator tube.step`: `Thread left 24.8`
- `OpenHI_STEP/Collimator cap.step`: `Cap thread 24.8`

External C-mount references:

- Basler documents C-mount as a 1"-32 thread with a 17.526 mm flange focal length: https://www.baslerweb.com/en-us/lenses/c-mount/
- Thorlabs C-mount adapter pages use the same `1.000"-32` thread family for C-mount accessories: https://www.thorlabs.com/c-mount-extension-tubes-and-spacer-rings
