# Shapr3D Batch Design History Analysis

Date: 2026-07-09

## Scope

This note analyzes the Shapr3D archive batch synced at:

```text
/home/lachlan/Nutstore Files/Projects/shapr3d/BACKUP/BATCHEXPORT/
```

It covers 82 `.shapr` files. The goal is not only to list files, but to learn
how the designs were built and convert that history into better future CAD
practice for OpenHI, LabCanvas, optical holders, sensor/PCB holders, and
3D-printable lab hardware.

## What Can Be Read From `.shapr`

Each `.shapr` file is a zip package with a SQLite `workspace` database. The
most useful tables are:

- `HistoryTreeNodes`: operation graph;
- `SketchControllers`: sketch planes, sketch names, hidden state;
- `HistoryImportedBodies`: imported STEP/Parasolid/vendor bodies;
- `HistoryNames`: topology/name database;
- `Drawings`, `Images`, `Shapes`: usually empty or not the useful geometry.

`HistoryTreeNodes.Properties` decodes as MessagePack. Type `2` nodes usually
have this shape:

```text
[version, version, display_name, operation_name, child_node_ids]
```

So the recoverable edit history includes operation order and operation families
such as `Extrude`, `OffsetFace`, `Transform`, `Chamfer`, `Revolve`, `Boolean`,
`Split`, `Sweep`, `Loft`, `Align`, and `MaterializeImportedBodies`.

Important limitation: Shapr's full proprietary feature parameters are not fully
documented here. The operation history is good enough to learn workflow and
identify design intent, but exact geometry still needs STEP/Parasolid export,
B-rep labels, and measured bounding boxes.

## Batch Summary

- Files: `82`
- Decoded history operations: `11,880`
- Most common operations:
  - `OffsetFace`: `2,974`
  - `Transform`: `1,872`
  - `MaterializeSketchPlane`: `1,760`
  - `Extrude`: `1,550`
  - `Delete`: `715`
  - `Boolean`: `495`
  - `Split`: `407`
  - `Chamfer`: `394`
  - `Revolve`: `366`
  - `CreateCGPlaneWithFaceOffset`: `352`
  - `Align`: `250`
  - `Scale`: `140`
  - `MaterializeImportedBodies`: `125`

Interpretation: your strongest Shapr workflow is iterative direct modeling:
start from imported references or sketches, extrude/revolve basic bodies,
position them with transforms/alignments, then tune real-world fit using face
offsets, splits, booleans, and chamfers.

## Per-Design Analysis

| Design | Family | Rev | Imports / Sketches / Ops | History signature | Design reading and lesson |
| --- | --- | ---: | ---: | --- | --- |
| `36HKY0402-8D4-200.shapr` | motion/motor reference | 2 | `1 / 0 / 1` | import only | Vendor motor/reference geometry. Treat as a measurement envelope, not editable source. |
| `36HSY3402-18-85.shapr` | motion/motor reference | 1 | `3 / 0 / 1` | import only | Imported motor body set. Use it to define shaft, body, and screw envelope for holders. |
| `3D_PCB1_2024-08-22.shapr` | PCB/electronics | 19 | `1 / 2 / 29` | import, sketches, many extrudes and offsets | Small PCB enclosure/holder design. The edits show a clean board-reference start, then thickness/clearance tuning through `OffsetFace`; future versions should turn those offsets into named pocket/clearance parameters. |
| `3D_PCB1_2024-08-22_with_elements.shapr` | PCB/electronics | 1 | `30 / 0 / 1` | imported elements | Board plus many component bodies. Use as component collision/envelope reference beside the simpler editable PCB holder. |
| `42 + umot.shapr` | motion/microscope assembly | 7 | `14 / 79 / 754` | imports, transforms, sketches, extrudes, offsets, booleans | Large mixed assembly. It combines imported motors/microscope references with many custom holder edits. Lesson: split future rebuilds into motor mount, optical holder, sensor holder, and rail subassemblies. |
| `42 stepper (Mac).shapr` | motion assembly variant | 638 | `13 / 73 / 705` | same family as 42 stepper | Mature Mac-side variant. High revision count means it is a design-history reference for fit iteration, but future CAD should not continue the same direct-modeling chain. |
| `42 stepper FH PLP.shapr` | motion/illumination assembly | 63 | `13 / 81 / 767` | imports, transforms, 89 extrudes, 188 offsets | Rich source for stepper/illumination holder structure. Many `OffsetFace` operations indicate printed-fit tuning; convert to named tolerances before regenerating. |
| `42 stepper HPLED.shapr` | motion/LED assembly | 39 | `13 / 79 / 748` | similar to FH PLP with LED changes | High-power LED branch variant. Useful for comparing LED holder and illumination packaging choices. |
| `50 ml Falcon tube Basic.shapr` | labware reference | 1 | `1 / 0 / 1` | import only | Falcon tube reference. Use for sample-holder envelope only. |
| `BS frame and events equal.shapr` | optical/event-camera frame | 47 | `4 / 75 / 468` | sketches, extrudes, offsets, deletes, chamfers | Beamsplitter/event-camera frame with equalized geometry. It is a good example of optical datum iteration; make future frames parameter-driven around optical axis and sensor planes. |
| `BS frame and events.shapr` | optical/event-camera frame | 473 | `4 / 69 / 415` | same family, older/more revised | Earlier frame. Compare with `equal` variant to understand why symmetry/equalization was needed. |
| `BS lateral.shapr` | 4f/BS lateral assembly | 30 | `4 / 77 / 495` | sketches, extrudes, offsets, revolves, splits | Core lateral optical branch. This file shows the 40 mm optical module pattern and the split/boolean approach used for old holders. |
| `Brush pen moist.shapr` | sample/fluidic accessory | 51 | `0 / 11 / 59` | sketches, revolved/extruded body, transforms | Small native design, not import-heavy. Good example of sketch-first part design. |
| `COSI A.shapr` | optical module A | 5 | `6 / 77 / 499` | BS lateral-like history | Optical A branch variant. It shares the BS-lateral workflow: sketches define datums, then offsets tune fits. |
| `COSI B.shapr` | optical module B | 14 | `40 / 26 / 142` | imported connector/camera bodies plus holder sketches | Mixed custom holder around many imported components. Lesson: separate imported references from editable holder solids. |
| `COSI C.shapr` | optical module C | 7 | `43 / 28 / 154` | imported references and holder edits | Similar to COSI B with more imports. Use for connector/camera clearance lessons. |
| `CS-cam_to_C-lens_adapter_vII.shapr` | camera-to-C adapter | 1 | `1 / 0 / 1` | import only | Imported adapter reference. Needs STEP measurement before reuse; no native edit history. |
| `Cam V2.1 v1.shapr` | camera reference | 3 | `1 / 0 / 1` | import only | Camera module reference. Use for board/case holder envelope. |
| `Centrifuge.shapr` | labware/mechanism | 22 | `0 / 6 / 23` | sketch/extrude, axes, align, booleans | Compact native design. Shows a clean low-operation workflow; good model for future small lab fixtures. |
| `Chamber slide (iPad).shapr` | chamber slide | 3 | `5 / 9 / 20` | import plus sketch/extrude/offset | iPad-side chamber slide variant. Compare with non-iPad version for tolerance differences. |
| `Chamber slide.shapr` | chamber slide | 43 | `5 / 9 / 20` | same as iPad variant | Mature chamber slide holder. Low operation count and repeated sketches suggest a simple, stable design. |
| `Chip.shapr` | simple chip proxy | 5 | `0 / 1 / 2` | sketch and extrude | Minimal native geometry. Use as a proxy pattern. |
| `Chroma corrected lens.shapr` | optical imported lens pair | 2 | `4 / 0 / 3` | two lens imports plus transform | Optical component reference. Use imported bodies for envelope/spacing only. |
| `D42HS3418-24B22.shapr` | motor reference | 1 | `5 / 0 / 1` | import only | Imported stepper/motor reference. |
| `DAVIS346.shapr` | event-camera reference | 1 | `2 / 0 / 1` | import only | DAVIS event-camera reference; use for exact holder envelope. |
| `DVX mini.shapr` | event-camera/custom sensor | 150 | `0 / 34 / 178` | native sketch/extrude/offset/chamfer | Rich native sensor/camera holder. Strong example of starting from board/case sketches and iterating reliefs. |
| `Davis holder.shapr` | event-camera holder | 39 | `0 / 4 / 21` | mostly extrudes and offsets | Clean small holder. Good candidate for parametric recreation. |
| `EVK 5 holder.shapr` | camera holder | 44 | `0 / 6 / 58` | extrudes, offsets, chamfers | Focused EVK holder. The history shows face-offset tuning after base extrudes; future version should name the board, screw, and clearance offsets. |
| `EVK 5.shapr` | camera/reference holder | 13 | `0 / 9 / 65` | similar to EVK 5 holder | Board/holder geometry with repeated offsets. |
| `Evk5.shapr` | camera proxy | 7 | `0 / 3 / 7` | sketch/extrude/one offset | Minimal EVK proxy. |
| `FSK40 X200Y150Z100-L T40 罗翔0702-S.shapr` | imported stage/reference | 2 | `310 / 0 / 1` | massive import | Linear stage or mechanical assembly reference. Use as collision/envelope model only. |
| `Fluigent.shapr` | fluidics/electronics fixture | 27 | `13 / 26 / 124` | imported connectors plus custom holder edits | Mixed instrument holder with RS232-style imported parts. Future design should separate connector footprints and body holders. |
| `Fluorescent.shapr` | fluorescence optical/illumination | 87 | `4 / 88 / 571` | sketches, extrudes, offsets, transforms, splits | Complex illumination/fluorescence assembly. It is a major reference for optical path, source holder, and split-body iteration. |
| `GLA.shapr` | optical/lens fixture | 1 | `4 / 47 / 263` | sketches, offsets, chamfers, deletes | Optical fixture with substantial native edits. Use as lens-holder design reference after measuring the related STEP bodies. |
| `GLA12-025-050.shapr` | lens reference | 1 | `1 / 0 / 1` | import only | Imported lens model; envelope reference. |
| `High power LED.shapr` | LED source | 21 | `0 / 6 / 27` | extrudes, offsets, revolves | Clean native LED holder/source design. Useful for compact round-light geometry. |
| `Hikang camera case.shapr` | camera case | 37 | `2 / 9 / 40` | imported case, split, sketches, extrudes | Camera case holder. It shows import-first, split/trim, then add custom case features. |
| `Hikang.shapr` | camera sketch/reference | 1 | `0 / 1 / 1` | sketch only | Minimal reference sketch. Needs external dimensions before use. |
| `Incubator thinner.shapr` | incubator/enclosure | 523 | `81 / 119 / 799` | many imports, sketches, offsets, transforms, aligns | Very mature enclosure. High offset/align counts show extensive fit iteration. Future rebuild should define panels, cover, hardware, and clearances as separate modules. |
| `Incubator thinner_Back cover.shapr` | incubator cover | 1 | `1 / 0 / 1` | import only | Back cover reference, likely exported from main incubator. |
| `Incubator.shapr` | incubator/enclosure | 180 | `81 / 75 / 216` | imports, sketch planes, transforms, offsets | Earlier incubator body. Compare with `thinner` to learn what was reduced or made more printable. |
| `LASERLAND 1668-650L-200-5V.shapr` | laser module reference | 1 | `2 / 0 / 1` | import only | Laser module reference for holder design. |
| `Laser.shapr` | laser holder/source | 10 | `0 / 4 / 19` | sketch/extrude/revolve/chamfer | Small native laser-related holder. |
| `Lego.shapr` | mechanical toy/reference | 17 | `0 / 7 / 12` | sketches, sweep, split, transform | Simple mechanical exercise/reference. Useful for learning feature combinations but not core lab hardware. |
| `Lens.shapr` | lens body | 14 | `0 / 1 / 3` | one sketch, two revolves | Very clean rotational design. This is the ideal pattern for lenses and cylindrical adapters: sketch section, revolve, keep axis explicit. |
| `Light holder.shapr` | light holder | 9 | `0 / 2 / 10` | sketch/extrude/offset | Compact holder. Good for parametric recreation. |
| `Light source holder.shapr` | light source holder | 112 | `75 / 20 / 123` | imports, axes/planes, extrudes, offsets, aligns | Mixed source holder with many imported references. Use for light-source packaging and alignment conventions. |
| `MLA UM3 0.5mm tolerance.shapr` | microlens/tolerance variant | 23 | `0 / 21 / 148` | offsets, extrudes, booleans | Explicit tolerance experiment. The filename records the fit hypothesis; future CAD should store the same in a manifest table. |
| `MLA UM3 1mm.shapr` | microlens/tolerance variant | 51 | `0 / 24 / 151` | same as 0.5 mm variant | Compare with 0.5 mm variant to infer print-fit sensitivity. |
| `MLA.shapr` | microlens holder | 189 | `0 / 16 / 109` | offsets, extrudes, booleans | Main microlens holder. Use tolerance variants rather than continuing face-offset edits blindly. |
| `MV-CB120-10UMUC-C (1).shapr` | camera sketch reference | 2 | `0 / 11 / 11` | sketch planes only | Likely outline/sketch-only camera reference. Needs STEP/board dimensions for holder work. |
| `MV-CB120-10UMUC-C.shapr` | camera reference | 12 | `2 / 6 / 16` | import, split, transforms, sketches | Imported camera model plus simple holder/reference sketches. |
| `Metasurface.shapr` | metasurface proxy | 5 | `0 / 1 / 2` | sketch and extrude | Simple flat proxy; use as aperture/sample plane placeholder. |
| `Microscope yx umot large.shapr` | microscope assembly | 91 | `17 / 49 / 470` | revolve/extrude/offset/transform | Large microscope/umot reference. It includes real custom modeling, not just imports. Use as a system envelope and optical-height reference. |
| `Microscope yx umot.shapr` | microscope assembly | 265 | `14 / 42 / 344` | extrudes, offsets, transforms | Earlier/related microscope assembly. Compare with large version for evolution. |
| `Microscope yx.shapr` | microscope holder/proxy | 97 | `13 / 19 / 122` | extrude/transform/offset, cylindrical axes | Smaller microscope design. Useful for axial datum conventions. |
| `Motor holder.shapr` | motor holder | 16 | `81 / 123 / 781` | imports, many sketches, offsets, transforms | Despite the name, this is a mature multi-body motor-holder design. It should be decomposed before reuse. |
| `NEMA23_ST57H703.shapr` | NEMA23 motor reference | 17 | `1 / 2 / 23` | import, split, transform, boolean, offset | Imported motor trimmed/processed for fit. Good example of adapting vendor bodies. |
| `NHI.shapr` | NHI assembly/reference | 43 | `59 / 34 / 72` | many imports plus sketch planes/axes | Assembly/reference file. Most value is component placement, not native geometry. |
| `Nature.shapr` | integrated OpenHI/Nature assembly | 24 | `77 / 2 / 12` | imports and transforms | Assembly of exported subassemblies. Use flattened STEP exports for detailed work. |
| `PHASE.shapr` | phase/optical holder | 243 | `0 / 33 / 260` | offsets, transforms, extrudes, chamfers | Native optical holder with heavy fit iteration. Convert offsets to named optical and print-fit parameters. |
| `PVA test.shapr` | material/test coupon | 1 | `0 / 1 / 3` | sketch and two extrudes | Small test piece. Good pattern for material/tolerance coupons. |
| `Pi%20Camera%20Module%20v3.shapr` | camera module reference | 2 | `5 / 0 / 1` | import only | Raspberry Pi camera v3 reference. Use for holder envelope. |
| `Polaritrum.shapr` | large optical instrument | 361 | `15 / 128 / 1094` | offsets, transforms, extrudes, booleans | Largest rich native optical design. Strong evidence that future tools need modular subassemblies, named datums, and versioned print-fit parameters. |
| `RMS20X-Solidworks.shapr` | objective/lens references | 2 | `6 / 0 / 3` | imported SolidWorks parts | Objective/lens reference pack. Use for optical component envelopes. |
| `SPW602-Step.shapr` | imported reference | 3 | `2 / 0 / 1` | import only | Vendor component reference. |
| `Servo motor holder.shapr` | motor holder | 19 | `0 / 1 / 12` | extrude, offsets, fillets | Small native servo holder. Fillet-heavy; future parametric version should keep fillet radii named. |
| `Slit.shapr` | optical slit | 9 | `0 / 2 / 9` | extrudes and chamfers | Very clean small optical aperture. Good reusable pattern for slit/light-valve apertures. |
| `Test.shapr` | experiment/test geometry | 23 | `0 / 9 / 33` | sketches, transforms, offsets, fillets, sweeps | Scratch/test file. Use only for feature experiments. |
| `Tripod.shapr` | mechanical fixture | 15 | `0 / 8 / 40` | extrudes, transforms, planes, mirror | Good example for symmetric fixture construction. Mirror operations should become symmetric parameters in code. |
| `Tube.shapr` | tube/fluidics | 1 | `0 / 4 / 10` | sweeps and loft | Good reference for tube/sweep/loft operations. Keep path and profile sketches separate in future. |
| `VWR_50ml_centrifuge_tube_lid (1).shapr` | labware reference | 1 | `1 / 0 / 1` | import only | Imported lid reference. |
| `VWR_50ml_centrifuge_tube_lid.shapr` | labware/lid holder | 49 | `2 / 4 / 42` | revolves, offsets, booleans | Good rotational lid design with boolean refinement. |
| `Voltrum.shapr` | optical/mechanical assembly | 10 | `21 / 12 / 65` | imports, align, axes, transforms, extrudes | Imported components plus custom alignment. Good example of axis-driven assembly. |
| `Yuxing_8c0a6269-008f-404b-95f8-c2173cf8a62f.shapr` | reference/empty | 6 | `0 / 0 / 0` | no decoded ops | No useful decoded history. Treat as placeholder unless external export exists. |
| `holder.shapr` | generic holder | 6 | `0 / 3 / 36` | offsets and chamfers | Small native holder. Offset-heavy; convert clearances to parameters. |
| `involute_gear (1).shapr` | gear sketch reference | 1 | `0 / 5 / 5` | sketches only | Sketch-only gear reference. Need exported sketch/DXF for serious gear work. |
| `involute_gear.shapr` | gear | 3 | `0 / 5 / 7` | sketches and two extrudes | Minimal gear model. Prefer a generated involute-gear script for future designs. |
| `pla chamberslide.shapr` | chamber slide material variant | 6 | `0 / 2 / 11` | extrudes, transforms, offset | PLA-specific chamber slide variant. Use for material-fit comparison. |
| `reflector.shapr` | reflector holder | 62 | `0 / 27 / 124` | sketches, extrudes, offsets, booleans | Native reflector holder design. Relevant to the later C-mount reflector workflow; keep cube pocket and tube/cylinder as separate solids. |
| `shapr3d_export_71c4460b-853d-4680-b6d5-c35c580a1bc8.shapr` | imported reference | 1 | `10 / 0 / 1` | import only | Generic imported export; inspect names/STEP before use. |
| `tee junction.shapr` | junction/fixture | 3 | `0 / 3 / 9` | extrudes and chamfers | Simple tee junction. Good example of compact extrusion-based design. |

## Design Patterns Learned From The Edit Histories

### 1. Imported References Are Common And Useful, But Not Editable Design

Many archives contain only `MaterializeImportedBodies`. These are best used as
vendor/reference geometry: motors, cameras, laser modules, lenses, linear
stages, objective parts, and labware. Future CAD should import these as locked
reference bodies and build clean parametric holders around them.

### 2. The Native Design Core Is Sketch -> Extrude/Revolve -> OffsetFace

Most custom parts start from sketch planes and extrusions or revolves, then use
`OffsetFace` to tune clearances. This matches your physical workflow: design
the shape, print/test it, then nudge faces. For maintainable code, turn each
repeated face offset into a named parameter:

```text
pcb_clearance_xy = 0.2
socket_relief_extra_y = 2.0
thread_pilot_diameter = 25.0
thread_cutter_max_diameter = 25.4
```

### 3. OffsetFace Count Is A Maintainability Warning

Large files such as `Polaritrum`, `Incubator thinner`, `42 stepper FH PLP`,
`Motor holder`, and `Fluorescent` have hundreds of `OffsetFace` operations.
They are valuable as history, but fragile as future edit sources. Rebuild
critical regions parametrically once the fit rule is known.

### 4. Transforms And Alignments Show Assembly Intent

Complex assemblies use many `Transform` and `Align` operations. This means the
design intent is often component placement, not just single-part geometry.
Future scripts should preserve:

- local part coordinate systems;
- assembly placement transforms;
- optical axis;
- sensor plane;
- motor shaft axis;
- cage rod centers;
- component envelope proxies.

### 5. Clean Rotational Parts Should Stay Revolve-Based

`Lens`, `Laser`, `VWR_50ml_centrifuge_tube_lid`, and some microscope parts use
`Revolve`. Future cylindrical optical or tube parts should use section sketches
and revolve operations rather than many stacked cylinders.

### 6. Tolerance Experiments Should Become Formal Variants

Files such as `MLA UM3 0.5mm tolerance`, `MLA UM3 1mm`, `Incubator thinner`,
and `pla chamberslide` show that material/printer fit matters. Future output
folders should record:

- printer/material;
- nominal part size;
- male/female clearance;
- actual successful fit;
- variant name.

### 7. Booleans And Splits Should Be Decomposed

Many old designs use `Boolean` and `Split`. In script-generated CAD, keep the
cutter bodies exportable:

- bore cutter;
- thread cutter;
- slot cutter;
- board pocket cutter;
- connector relief cutter;
- aperture cutter.

This makes failures visible and keeps Shapr3D edits easier.

## Better Future CAD Workflow

For new work, follow this structure:

1. **Reference stage**
   - Import Shapr/STEP/vendor geometry as locked reference.
   - Measure body labels, bounding boxes, holes, axes, and critical offsets.

2. **Datum stage**
   - Define optical axis, sensor plane, PCB coordinate frame, motor shaft, or
     cage rod pattern before modeling the part.

3. **Parametric stage**
   - Build the main body from sketches/extrusions/revolves.
   - Encode all `OffsetFace` style changes as named dimensions.
   - Keep imported references separate from generated solids.

4. **Decomposition stage**
   - Export separate STEP/STL for body, plate, socket, thread cutter, board
     proxy, sensor proxy, and final assembly.

5. **Validation stage**
   - Reimport STEP.
   - Check bounding boxes and solid counts.
   - Render full view and detail view.
   - Save fit notes in README and reference docs.

6. **Iteration stage**
   - Create a new sibling variant for every physical-fit change.
   - Do not overwrite exact regeneration or known-good printed designs.

## Commands

Inspect one file:

```bash
python ~/.codex/skills/parametric-cad-design/scripts/inspect_shapr_step_sources.py \
  --shapr "/home/lachlan/Nutstore Files/Projects/shapr3d/BACKUP/BATCHEXPORT/Lens.shapr" \
  --markdown
```

Inspect the full batch:

```bash
python ~/.codex/skills/parametric-cad-design/scripts/inspect_shapr_step_sources.py \
  --shapr-dir "/home/lachlan/Nutstore Files/Projects/shapr3d/BACKUP/BATCHEXPORT" \
  --markdown
```

Use CadQuery/STEP exports for actual geometry measurement whenever exact
dimensions matter. The Shapr history tells how the part evolved; STEP/Parasolid
confirms what the part physically is.
