# Shapr3D, OpenHI, And Nature CAD Design Analysis

Date: 2026-07-08

## Scope

This note records what was found in the synced Shapr3D and STEP sources, how to
read them, and what design rules should be reused for future OpenHI/Nature
optical, PCB, sensor, and cage parts.

The native Shapr3D source found in this workspace is:

- `cad/extracted/Nature.shapr`
- duplicate user download: `/home/lachlan/Downloads/Nature.shapr`

The actionable geometry is in the STEP exports:

- `cad/extracted/Nature_STEP/`
- `cad/extracted/OpenHI_STEP/`

The Shapr file and the flattened OpenHI STEP folder describe the same design
family. The STEP folder is more useful on Ubuntu because it exposes named
solids, B-rep labels, and stable importable geometry.

## Inspection Method

Reusable inspector:

```bash
../LazySkills/skills/parametric-cad-design/scripts/inspect_shapr_step_sources.py \
  --shapr cad/extracted/Nature.shapr \
  --step cad/extracted/OpenHI_STEP \
  --step cad/extracted/Nature_STEP \
  --markdown
```

Measured bounding boxes were produced with the repo CAD Python environment:

```bash
cad/.conda/cad-python/bin/python - <<'PY'
from pathlib import Path
import cadquery as cq
for folder in [Path("cad/extracted/OpenHI_STEP"), Path("cad/extracted/Nature_STEP")]:
    print(f"## {folder}")
    for path in sorted(folder.glob("*.step*")):
        shape = cq.importers.importStep(str(path))
        solids = shape.solids().vals()
        bb = shape.val().BoundingBox()
        print(path.name, len(solids), round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3))
PY
```

STEP body names were extracted from `MANIFOLD_SOLID_BREP(...)` and product
names from `PRODUCT(...)`. These labels are useful because the `.shapr` archive
does not expose a clean editable feature tree.

## Shapr Package Findings

`Nature.shapr` is a zip package containing a SQLite `workspace` database:

- metadata: `remoteID=d7d0c915-727f-474e-89cb-dba0eee15c17`, `revisionID=24`
- `Shapes`: `0`
- `SketchControllers`: `2`
- `HistoryImportedBodies`: `77`
- `HistoryTreeNodes`: `82`
- `HistoryNames`: `42454`
- `Images`: `0`
- `Drawings`: `0`

Sketch controllers:

- `Sketch 01`, hidden, origin `(0, 0, 0)`, normal `(0, 0, 1)`
- `Sketch 02`, hidden, origin `(0, 0, 0.013)`, normal `(0, 0, 1)`

Interpretation: this is not a parametric Shapr feature-history file in a form
that can be safely edited on Ubuntu. It is mostly imported Parasolid/B-rep
history. Exact regeneration should therefore preserve the exported STEP B-rep
first, then make clean sibling parametric variants for physical-fit changes.

## Nature STEP Assemblies

| File | Solids | Bounding box mm | Role and details |
| --- | ---: | ---: | --- |
| `Nature_STEP/42 stepper FH PLP.step.step` | 32 | `75.000 x 369.770 x 137.000` | Full illumination/motion assembly. It combines collimator holder, motor cushion/cap/holder/lid, light switch holder, grating/dichroic holder, sensor arm, chamber slide, EVK holder, Lumileds PCB, and 42 stepper motor. Use it to understand how the LED, collimator, motion rail, sensor arm, and grating parts relate. |
| `Nature_STEP/BS lateral.step.step` | 20 | `228.408 x 50.000 x 287.200` | Full lateral optical branch assembly. It includes `Body 01`, left/right locks, A/B/C branch pieces, Lens B/C holders, Lens A + BS holder, camera proxy, and EVK proxy. Use it as the global 4f-system layout reference. |
| `Nature_STEP/Body 01.step` | 1 | `400.000 x 300.000 x 13.000` | Large base plate. It anchors the optical branch and helps infer overall footprint/clearance, but it is not a small holder source. |
| `Nature_STEP/Microscope yx umot large.step.step` | 2 | `50.000 x 50.000 x 302.000` | Microscope upper/lower proxy. Use as an envelope/reference body, not as a part to regenerate unless the user asks. |

## OpenHI STEP File Analysis

| File | Solids | Bounding box mm | Named bodies | Design reading |
| --- | ---: | ---: | --- | --- |
| `42 stepper FH PLP.step.step` | 7 | `75.000 x 364.770 x 134.000` | `Lid`, `Mainslide`, `EVK 5 holder (3)`, imports, `42 stepper*` | Flattened motion/stepper subassembly. It preserves the stepper, EVK holder, slide, and auxiliary imported solids. Use it for coarse envelope and mounting references around the motorized side, not for optical thread reconstruction. |
| `A+ C + BS.step` | 1 | `40.000 x 40.000 x 84.900` | `Lens A + BS holder (1)` | 40 mm square optical branch body joining lens A, C, and beamsplitter geometry. Use it for the 40 mm module cross section and branch spacing. |
| `A.step` | 3 | `40.000 x 40.000 x 50.000` | `Thread top`, two `Scope fittings` bodies | Scope/top interface. The body labels show a separate top thread plus two square fitting bodies. Keep the thread and square block concepts separated when rebuilding. |
| `B.step` | 4 | `40.000 x 40.000 x 54.400` | `Thread lens 29.6*`, `Thread camera 24.4`, `Lens B camera` halves | B branch adapter. It contains both the larger OpenHI lens thread family and the smaller camera/C-mount-like thread family. This file proves these are separate standards and should not be merged. |
| `BS cap.step` | 1 | `24.500 x 24.500 x 2.700` | `BS cap` | Thin cap/cover. It is a small simple planar part; use it as a reference for flat retaining caps, not for thread specs. |
| `C.step` | 4 | `54.000 x 40.000 x 40.000` | `Thread camera 24.4`, `Thread lens 29.6`, `Lens C camera` halves | C branch adapter. Same thread-family split as B, rotated through the lateral axis. Good evidence for axis conventions and inserted square body sizes. |
| `Collimator arm FHPLP.step` | 1 | `10.000 x 152.410 x 10.000` | `Collimator holder (1)` | Long 10 mm square arm. Use as a rod/arm reference for optical placement, not a detailed holder. |
| `Collimator cap.step` | 2 | `33.800 x 20.000 x 33.800` | `Cap thread 24.8`, `Collimator cap` | Cap plus internal/receiving 24.8-thread family. Together with collimator tube, it gives female-side print-fit values for the camera-thread family. |
| `Collimator holder FHPLP.step` | 1 | `50.000 x 10.000 x 71.000` | `Collimator holder FHPLP` | Upright collimator support. It is mostly rectangular with cylindrical holes; useful for rod/arm datum placement. |
| `Collimator tube.step` | 3 | `30.600 x 30.800 x 30.600` | `Outer thread`, `Thread left 24.8`, `Collimating tube (1)` | Best local reference for nested thread roles: larger outer thread, smaller left thread, and the smooth collimating body. Use it when designing adapters that must mate to the old collimator/camera path. |
| `Grating & dichroic.step` | 2 | `62.000 x 117.500 x 50.000` | `Grating dichroic holder`, `Dichroic base` | Flat-optic holder and base. Many planar faces; useful for deciding how to keep grating/dichroic components accessible and mechanically simple. |
| `GratingFixer.step` | 1 | `25.000 x 2.500 x 25.000` | `GratingFixer` | Thin fixer/retainer plate. Use as a pattern for simple retaining plates instead of overbuilding. |
| `LED holder.step` | 2 | `30.001 x 11.600 x 30.036` | `Cylinder (1)`, `Light bottom` | Original LED holder. It inspired the clean Lumileds cage holder rule: use the PCB outline/hole positions as source of truth and avoid unnecessary sinks unless needed. |
| `Lens B holder.step` | 1 | `40.734 x 40.734 x 85.367` | `Lens B holder chopped (2)* (1)` | Exact Lens B holder source. The exact-regeneration folder preserves this B-rep; print-fit variants should surgically rebuild only the 30 mm female receiver while keeping side holes, oblique sink, and outer envelope. |
| `Lens C holder.step` | 2 | `50.000 x 40.000 x 40.000` | `Thread BS`, `T branch head (1)` | Exact Lens C holder source. The two named bodies matter: preserve `Thread BS` and rebuild the positive-X receiver only when changing the 30 mm female fit. |
| `Light switch holder.step` | 5 | `72.958 x 20.000 x 66.000` | `Limit switch*`, `Motor holder**` bodies | Multi-body switch/motor fixture. Keep as reference for limit switch positioning and simple stacked motor brackets. |
| `Locks.step` | 2 | `10.000 x 50.000 x 20.000` | `R`, `L` | Left/right lock blocks. Useful for simple mirrored retention features. If a future design has mirrored clamps, keep each side separately named. |
| `Microscope yx umot large.step.step` | 2 | `50.000 x 50.000 x 302.000` | `Microscope lower`, `Microscope upper` | Microscope envelope/proxy. Preserve as assembly context. |
| `Motor cap.step` | 1 | `52.000 x 12.000 x 40.000` | `Motor cap` | Motor cover/cap with many holes. Use for enclosure clearance around motor hardware. |
| `Motor cusion.step` | 1 | `15.000 x 15.000 x 3.000` | `Motor cusion` | Small compliant/spacer part. Useful as a reminder to represent spacers explicitly instead of burying them in large bodies. |
| `Motor holder.step` | 1 | `52.000 x 52.000 x 43.250` | `Motor holder` | Main stepper motor mount. Strong reference for a square motor face, centered shaft opening, and corner screw holes. |
| `Motor lid.step` | 1 | `52.000 x 52.000 x 2.750` | `Motor lid (1)` | Thin motor lid. Use as separate cap/cover rather than coupling to the motor holder. |
| `Sensor arm.step` | 4 | `41.000 x 34.500 x 40.000` | `Sensor arm 1-4` | Multi-part sensor arm. Important for modular sensor placement; keep individual arm segments named and exportable. |

## Thread And Fit Lessons

The STEP files contain two different thread families:

- camera/C-mount-like family: labels around `Thread camera 24.4` and `Thread left 24.8`
- larger OpenHI lens/BS/top family: labels around `Thread lens 29.6`, `Thread top`, `Thread BS`, and `Outer thread`

Do not convert the OpenHI 30 mm lens family to C-mount unless the task is a new
adapter. Standard C-mount is `1"-32 UN`, nominal major diameter `25.4 mm`, pitch
`0.79375 mm`. The OpenHI lens/BS family is a printed near-30 mm system.

Local printed thread profile evidence:

- pitch/gap near `0.8 mm`
- tooth radial height around `0.4 mm`
- tooth base around `0.8 mm`
- swept triangular tooth, often expressed by 45 degree side vectors

Female printed threads should be made from a pilot bore plus a male-shaped
thread cutter. Do not make the pilot as large as the nominal crest diameter
unless intentionally designing a loose fit.

For clean thread ends:

- extend the thread cutter by about half a pitch beyond nominal end faces;
- subtract/intersect so the final body is clipped exactly at the cylinder ends;
- for external threads, trim back to the real end face after generating the
  extra half-pitch runout.

## Design Principles Distilled From These Files

1. Preserve exact B-rep baselines before changing anything.
   Exact regeneration folders should prove source path, solid count, bounding
   box, named bodies, face/surface evidence, and regenerated artifact paths.

2. Make physical-fit changes as sibling variants.
   Do not edit or overwrite the exact-regeneration folder. A print-fit fix
   should say exactly which receiver/pocket/thread changed and which faces were
   preserved.

3. Keep datum discipline.
   Optical axis, PCB center, sensor active center, C-mount bore, and cage rod
   pattern must be driven by named datum parameters. If something looks
   off-center, first decide whether the datasheet offset is intentional.

4. Prefer direct, simple solids.
   Avoid bridge cubes, filler cylinders, and decorative support geometry unless
   they are actual functional parts. If two modules should touch, make them
   adjacent named solids or a clean union, not a coupled boolean tangle.

5. Decompose editable parts.
   Export separate STEP/STL bodies for sockets, plates, boards, thread cutters,
   sensor proxies, PCB proxies, rods, and retaining plates. This makes Shapr3D
   editing possible even when the final assembly is also exported.

6. Use the real component as source of truth.
   For PCB and sensor holders, base the holder on the PCB outline, mounting
   holes, connector envelope, socket/wire relief, sensor offset, and active
   aperture. Do not guess from the rendered image.

7. Document protrusions and reliefs.
   Pin headers, sockets, DuPont wires, LEDs on sensor boards, solder joints, and
   screw heads need named clearances. A socket relief should be measured from
   the PCB surface, not from the bottom of the holder if the PCB is recessed.

8. Build clean rebuilds when old B-rep becomes messy.
   If fill-and-recut leaves internal shell slivers in a threaded bore, trim the
   old problematic region away at a stable datum and rebuild that receiver as a
   clean adjacent solid.

9. Validate both engineering and visual outputs.
   Check importability, solid count, bounding box, watertight mesh, artifact
   paths, and full-view render. A pretty render is not enough if the STEP cannot
   be edited or reimported.

## Best Export Formats For Future Shapr Work

Use multiple exports for each important design:

- `.shapr`: original design archive; keep it for Shapr3D, but do not assume it
  can be decoded into features on Ubuntu.
- `STEP` or `Parasolid X_T/X_B`: best for editable solid transfer and exact
  B-rep preservation.
- `STL` or `3MF`: printing and mesh validation only; not a good source for
  editing precision holders.
- `DXF` from sketch: best for 2D profiles, hole patterns, and laser/CNC-style
  outlines.
- `PDF/SVG` from drawing: best for dimensioned documentation.

When exporting for agents, prefer:

```text
Shapr3D archive + STEP + Parasolid (if available) + DXF sketches + PDF drawing
```

## How Future Agents Should Use This

For a new request involving old OpenHI/Nature/Shapr geometry:

1. Run the inspector on `.shapr` and STEP inputs.
2. Identify whether the user wants exact regeneration, a print-fit variant, or a
   new adapter inspired by the old geometry.
3. If exact regeneration is requested, preserve B-rep and prove equivalence.
4. If a new design is requested, use the old body only as reference and make a
   clean parametric model with named dimensions.
5. Update the design README and `cad/references/openhi-print-fit-and-thread-reference.md`
   when new fit evidence appears.
6. Export source, STEP, STL, PNG render, and any sketch/DXF/PDF support files.
