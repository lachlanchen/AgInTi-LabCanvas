# OpenHI and Nature STEP Notes

Date: 2026-06-09

## Imported Local Files

The reference archives were copied into `cad/sources/` and unpacked into `cad/extracted/`.

- `OpenHI_STEP.zip`: 24 STEP files, including `A.step`, `B.step`, `C.step`, collimator parts, lens holders, LED holder, and sensor arm.
- `Nature_STEP.zip`: 4 STEP files, including `Body 01.step`, `BS lateral.step.step`, stepper/collimator assembly, and microscope assembly.

All inspected STEP headers use AP242-style STEP data and millimetre SI units.

## Thread Clues Found In STEP Brep Names

The files include named solids that expose the designer's intended thread diameters:

- `OpenHI_STEP/C.step`: `Thread camera 24.4`, `Thread lens 29.6`
- `OpenHI_STEP/B.step`: `Thread camera 24.4`, `Thread lens 29.6*`
- `OpenHI_STEP/Collimator tube.step`: `Outer thread`, `Thread left 24.8`
- `OpenHI_STEP/Collimator cap.step`: `Cap thread 24.8`
- `Nature_STEP/BS lateral.step.step`: repeated `Thread camera 24.4`, `Thread lens 29.6`, `Thread top`, `Thread BS`

Inference: the camera-side thread appears to be a C-mount-compatible printed fit that was intentionally reduced from the nominal 25.4 mm C-mount diameter to about 24.4 mm. This matches the note that roughly 1 mm was adjusted to make the 3D print fit the real mating part.

## C-Mount Baseline

Industrial C-mount uses a 1"-32 UN thread with nominal 25.4 mm diameter and 1/32 inch pitch. The pitch is 0.79375 mm. The standard flange focal length is 17.526 mm.

For printed prototypes, use the local reference value first:

- `thread_major_d = 24.4 mm`
- `thread_pitch = 25.4 / 32 = 0.79375 mm`
- `thread_length = 5.5 mm` initial draft

Validate fit with a short threaded test coupon before printing the full adapter.

Sources:

- https://www.baslerweb.com/en-us/lenses/c-mount/
- https://www.thorlabs.com/c-mount-extension-tubes-and-spacer-rings

## Adapter Design Intent

The first adapter draft is saved in `cad/designs/cmount_reflector_adapter/`.

Requirements captured:

- one end mates to the female C-mount of a 4f optical system;
- adapter therefore needs a male external C-mount-like end;
- opposite side connects to a reflector chamber;
- chamber has a 20 x 20 x 20 mm internal cube;
- wall thickness is 3 mm, so the outer cube is 26 x 26 x 26 mm;
- hollow cylinder and cube are centered on the same optical axis;
- cylinder bottom and cube bottom are coplanar for flat printing or fixture alignment.

The OpenSCAD file keeps these as named parameters so print compensation can be tuned after test fitting.

Detailed 1:1 scale parameters and print-check dimensions are consolidated in `cad/references/cmount-reflector-adapter-scale.md`.
