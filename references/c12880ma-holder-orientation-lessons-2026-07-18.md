# C12880MA Holder Orientation and Mating-Face Lessons

Date: 2026-07-18

This note records the design reasoning behind the corrected C12880MA C-mount
holder. It is both a project handoff and a reusable method for asymmetric PCB,
sensor, camera, and optical-module holders.

## Files and Final Run

- Design: `cad/designs/c12880ma_cmount_spectrometer_module_holder`
- Physical evidence: `cad/references/c12880ma-spectrometer-module`
- Accepted run: `runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z`
- Direct handoff: `USE_THIS_c12880ma_cmount_spectrometer_module_holder.step`

The accepted holder is deliberately simple. It retains the validated C-mount,
42 mm plate, sensor opening, mounting holes, PCB pocket, and pin-tail relief. The
photos clarify orientation but do not add a connector housing, daughterboard,
notch, bridge, or other unrequested geometry.

## Coordinate and View Contract

The sensor optical center is the origin.

- `X`: optical/depth direction, through the C-mount and sensor.
- `Y`: PCB long direction, along the 38.3 mm edge.
- `Z`: PCB short direction, along the 22.8 mm edge.

The supplied sketch and top photo are a **source component-side view**: the PCB
is on the table, the sensor points upward, the sensor is near the top-left, and
the socket/pin row is below it. The component face then mates against the rear
of the holder. Looking at the holder mating face is therefore looking at the
opposite face of the same footprint.

For this design, map source measurements to holder cutouts with:

```text
Y_holder = Y_source
Z_holder = -Z_source
```

Apply this mapping only to PCB-face features. Do not rotate the C-mount, plate,
thread, optical axis, or depth stack. The mapping is a view conversion, not a
new physical rotation of the complete holder.

| Feature | Source component view | Holder mating view |
| --- | ---: | ---: |
| PCB center Z | `-1.1 mm` | `+1.1 mm` |
| pin-row center Z | `-9.3 mm` | `+9.3 mm` |
| PCB top distance from sensor | `+10.3 mm` | lower side after mapping |
| PCB bottom distance from sensor | `-12.5 mm` | upper side after mapping |
| pin-row center Y | `-0.4 mm` | `-0.4 mm` |

Words such as left, right, top, bottom, front, and back are unsafe without a
named view. Every future drawing and manifest should state the face being
viewed and show axis arrows.

## Authoritative Measurements

The user's measured values control geometry. Photos are used to associate those
values with physical sides and faces.

- PCB: `38.3 x 22.8 x 1.5 mm`.
- Sensor package maximum: `20.5 x 13 x 15 mm`.
- Printed package opening: `20.9 x 13.4 mm`.
- Sensor axis from PCB long edges: `15.55 mm` and `22.75 mm`.
- Mounting holes from sensor axis: `Y=-13.2/+20.4 mm`, spacing `33.6 mm`.
- Plate center: `Y=+3.6 mm`, making the mounting holes symmetric about it.
- Six pin tails: `2.54 mm` pitch, row center `Y=-0.4 mm`.
- Pin relief: overlapping `3.0 mm` cuts joined into one continuous slot.
- Printed M2 tap pilots: `1.6 mm` diameter and `4.5 mm` blind depth.

The `Y=-0.4 mm` pin-row center is intentionally a small correction from the
run-1 value of `0.0 mm`. A request for a slight correction should remain a small
parameter delta unless new measurements clearly require a larger move.

## Preserved Holder Geometry

- Plate: `42 x 42 x 5 mm`.
- C-mount outer diameter: `34 mm`.
- Female C-mount pilot/root: `25.0 mm`.
- Nominal female groove maximum: `25.4 mm`.
- Local printable pitch: `0.8 mm`.
- Threaded length: `5 mm`, with half-pitch construction runout clipped to the
  intended faces.
- Thread-to-package gap: `0.8 mm`.

The PCB sink is implemented as a `2 mm` raised rear rim outside a
`38.7 x 23.2 mm` pocket. The original 5 mm structural plate and PCB seating
plane remain unchanged. A 1.5 mm PCB therefore finishes 0.5 mm below the rim
without moving the sensor toward the thread.

## Failed Interpretations and Why

### Treating a rear view as the source view

A rear inspection view is mirrored. Copying its left/right or top/bottom
coordinates directly reverses the physical cutouts. Start from the named source
face, then calculate the mating-face transform once.

### Rotating the complete holder

The C-mount and depth stack were already correct. Rotating or rebuilding the
whole design to match a table-view description changed unrelated geometry. Only
the PCB-face coordinates needed conversion.

### Over-modeling from photographs

The physical photos show a connector and elevated sensor assembly, but the
requested holder only needs measured clearances. Adding detailed connector,
daughterboard, or socket solids made the design fragmented and obscured the
actual fit problem. Such objects may be assembly proxies, but must not become
holder features without an explicit requirement.

### Replacing the accepted baseline

One attempted correction lost the PCB sink and rear rim. A small orientation
fix should start from the last accepted geometry and change only named
parameters. Preserve accepted features with regression assertions.

### Converting verbal margins into a large move

The `9/17 mm` description was intended to refine the already-near-correct pin
row. Reinterpreting it as a new absolute center produced a large, incorrect
translation. Compare every proposed value with the baseline before rebuilding.

## Reliable Workflow

1. Freeze the accepted baseline and list what is already correct.
2. Define source face, mating face, optical axis, long axis, and short axis.
3. Put each measurement in a table with its face and sign convention.
4. Write the source-to-holder transform explicitly before editing geometry.
5. Change only the affected parameters; keep the rest as assertions.
6. Use board, sensor, pin, and hole proxies for assembly inspection without
   unioning extra proxy geometry into the printable holder.
7. Generate a holder-side alignment drawing and a depth-section drawing.
8. Re-import STEP, validate B-rep and solid count, validate STL watertightness,
   and inspect both direct-print and assembly renders.
9. Compare the new solid with the accepted baseline. Unexpected envelope or
   volume changes are evidence of an accidental geometry change.
10. Promote one root `USE_THIS_*.step`, create STEP/STL/3MF print files, sync
    the organized run to Nutstore, then commit and test.

## Validation Evidence

The accepted run re-imports as one valid solid. Its print STEP and STL both have
a `42 x 42 x 23 mm` envelope; the STL is watertight and one body. The 3MF is a
valid archive. Run 3 and corrected run 5 have the same solid count and envelope:

```text
run 3 volume: 15559.441129 mm^3
run 5 volume: 15559.445164 mm^3
difference:   0.004035 mm^3
```

That negligible numerical difference supports the intended result: existing
geometry was preserved while asymmetric face cutters were mirrored and the pin
row received only its small correction.

## Future Checklist

- Is the source image component-side, solder-side, front, rear, or mating-side?
- Which way are the PCB long and short axes in that view?
- Is the optical center different from the PCB center?
- Which dimensions are measured, and which are only visual estimates?
- Does the mating face require one sign inversion or a full rigid transform?
- Did any feature outside the requested parameter set move?
- Are photo-only details kept as proxies rather than added to the holder?
- Are pocket depth and connector relief measured from the PCB seating surface?
- Do the manifest and drawings use the same view names and signs as the model?
- Do STEP, STL, 3MF, renders, and baseline comparison all agree?

For future prompts, a precise orientation sentence is:

```text
Place the PCB flat with the component side facing up. In that source view, the
sensor is above the socket. The component side mates against the holder, so
mirror only the PCB short-axis coordinates when drawing holder-side cutouts;
keep the optical axis, C-mount, depth stack, and PCB long-axis coordinates fixed.
```
