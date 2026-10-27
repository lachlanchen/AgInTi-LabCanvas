# YXRA100 Servo Analyzer Breadboard Mount

This fixture holds the stationary base of a purchased Yixuan YXRA100 100 W
servo rotary stage on a metric optical breadboard. A separate rotating adapter
carries the complete Hengyang GT090101 analyzer mount. Existing OpenHI CAD
parts and their previous runs remain unchanged.

## Current Deliverables

- `USE_THIS_yxra100_servo_analyzer_breadboard_mount_assembly.step`: complete
  integration model with supplier stage, GT090101, fixture, current dock,
  illumination/LCD/sample stack, relocated microscope, first 4f relay,
  frame-camera proxy and C12880 assembly.
- `artifacts/vendor_YXRA100_servo_positioned.step`: genuine supplier geometry
  placed on the optical axis; no speculative replacement stage was drawn.
- `artifacts/renders/complete_rotary_analyzer_setup.png`: full assembly.
- `artifacts/renders/stage_stand_and_sample_clearance.png`: lower detail.
- `artifacts/renders/sample_access_opposite_view.png`: unobstructed sample-side view.
- `artifacts/renders/exploded_rotary_mount.png`: separate mating parts.
- `artifacts/manifest.json`: dimensions, source identity, checks, limitations,
  bill of hardware, and print-package validation.

The timestamped run is
`runs/run-1-servo-full-gt090101-clearance-prototype-20261027T140000Z/`.
Its three `PRINT_THIS` packages are separate, each in STEP, STL and 3MF:

1. `yxra100_breadboard_foot_with_ears`: flat on the breadboard mating face.
2. `yxra100_L_support_on_back_with_ears`: outer upright face on the print bed;
   the tall shelf and ribs build upward rather than as unsupported bridges.
3. `yxra100_full_GT090101_rotating_adapter`: flat ring down, locating pins up.

These print files contain only the named new fixture part. They never include
the motor, stage, GT090101, microscope, specimen, dock, or other reference parts.
All three are mechanical fit/clearance prototypes, not load-certified parts.
Check the overall integration height before printing the large L support.

## Datums And Layout

All values are millimetres. The common optical axis is world Z at X=Y=0.
The vendor model is rigidly normalized to its bore center and bottom face,
rotated +90 degrees around Z, and lifted to Z=122. The servo is on the +X side.

| Feature | Value |
| --- | --- |
| Metric breadboard grid | 25 mm, M6 threads in the table |
| Foot screw centers | X=100/125, Y=-50/0/50 |
| Foot slots | 6.4 mm wide, 10.4 mm overall long |
| Stationary stage attachment | (-37.5,-43), (37.5,-43), (-43,50) |
| Stage attachment clearance | diameter 6.6 |
| Foot / shelf thickness | 8 / 8 |
| Upright thickness | 16 |
| Shelf clear opening | diameter 60 |
| Sample cap top / shelf bottom | Z=109 / 114; 5 mm separation |
| Stage bottom / rotating face | Z=122 / 167 |
| Rotating adapter | diameter 78 x 8, aperture diameter 30.4 |
| GT090101 base / top | Z=175 / 193 |
| GT locating pins | diameter 5.9 x 16; 30 mm square |

The shelf uses the three actual supplier through holes, with captured M6 nuts
accessible from below. A gusseted L support and separate foot transmit the
load to the breadboard. The motor casing is not a structural clamp and is not
compressed or used as the only support. The support is on the motor side but
remains below its casing. Neither the rotor nor its optical aperture is clamped.

The adapter bolts to four of the rotor's M6 taps at X=+/-25, Y=+/-12.5.
Use low-head M6 screws within the 4.5 mm counterbores and verify screw length
against the actual 8 mm tapped depth. The GT090101 slides onto four short
printed locating pins and is retained with its existing side-lock screws.
Its manual inner rotation should be locked during motorized acquisition.
No rod may connect this rotating GT frame to the stationary sample holder.

## Integration Limits

The 45 mm rotary stage cannot occupy the existing sample holder's volume.
This layout keeps the sample and dock unchanged and raises the microscope by
61 mm relative to the previous visualization. The microscope currently has no
objective, so the gap is intentional in this illustration. Installing an
objective later requires a separate working-distance/focus check. Mechanical
coaxiality does not prove preserved sample focus or optical performance.

The supplier drawing lists approximately 1.85 kg for the servo stage. The
fixture has not undergone a load, deflection, fatigue, thermal or creep test.
For final stable metrology, metal construction is preferable; a printed part
must be treated as a fit prototype, protected from lamp/motor heat, and tested
with a restrained load before supporting the purchased equipment. Confirm
actual fastener lengths, cable bend radius and specimen access in the lab.

The CSG1175-P/DualLampHI/SPICE session context was requested but not read:
the available native UU terminal refused access because another remote
controller owns that device. No remote session was interrupted, no rollout
was edited, and no device was taken over. The local accepted experiment CAD
and the supplier documents are the verified sources for this run.

## Rebuild And Verify

```bash
python cad/references/yixuan-yxra100/download_references.py
cad/.conda/cad-python/bin/python \
  cad/designs/yxra100_servo_analyzer_breadboard_mount/build_mount.py
blender --background --threads 6 --python-exit-code 1 --python \
  cad/designs/yxra100_servo_analyzer_breadboard_mount/render_mount.py
```

The builder measures the source hole centers, rejects mismatched patterns,
checks fixture/reference intersections and a 15-degree sampled rotational
sweep, re-imports STEP, and verifies each serialized print mesh and 3MF.
The renderer projects every object bounding-box corner into each camera and
rejects views whose bounds leave the safe image margin. The bottom detail
explicitly hides the microscope; the full assembly view includes it entirely.

Supplier references: `../../references/yixuan-yxra100/README.md`.
Nutstore handoff: `/home/lachlan/Nutstore Files/Projects/LabCanvas/` under this
project name and the identical timestamped run name.
