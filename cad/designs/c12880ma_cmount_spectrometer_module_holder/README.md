# C12880MA C-Mount Spectrometer Module Holder

Parametric holder for the measured `38.3 x 22.8 mm` C12880MA module board. The
sensor package, rather than the PCB center, defines the C-mount optical axis.

## Latest Checked Run

`runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/`

Use the unambiguous root handoff:

`USE_THIS_c12880ma_cmount_spectrometer_module_holder.step`

The latest run contains direct-print STEP, STL, and 3MF files, full renders,
alignment drawings, separate socket/plate/proxy STEP files, a smooth editable
STEP, a female-thread cutter, a manifest, and validation evidence.

## Critical Datums

- C-mount axis and sensor center: `Y=0, Z=0`.
- Structural plate: `42 x 42 x 5 mm`; center shifted `+3.6 mm` along PCB
  length.
- Baseline: the clean run-1 `42 x 42 x 5 mm` plate, with no raised PCB rim.
- Table orientation: PCB back face at `Z=0`; component side, sensor package,
  holder, and C-mount face upward. This is one rigid rotation of the complete
  run-1 coordinate system, not separate feature mirroring.
- C-mount OD: `34 mm`; printable female thread: `25.0 mm` pilot to `25.4 mm`
  nominal groove maximum.
- Board holes: `Y=-13.2/+20.4 mm`, `Z=0`, giving `33.6 mm` spacing.
- M2 printed tap pilots: `1.6 mm`, blind depth `4.5 mm`.
- Verified component-side orientation: sensor up, 6P socket down, sensor closer
  to the left PCB edge, and larger PCB margin on the right.
- Six socket solder-tail clearances: joined `3.0 mm` reliefs at `2.54 mm`
  pitch, centered at `Y=+7.6 mm`, `Z=-9.3 mm` on the PCB seating surface.
- In the authoritative component-side top view (sensor up, socket down), the
  pin centers have `16.8 mm` left and `8.8 mm` right margins, matching the
  measured `17/9 mm` values within `1 mm`. The relief provides `1.0 mm` radial
  clearance around the `1.0 mm` pin proxy.

The 6P connector clearance is intentionally based on the protruding PCB pins,
not on the connector housing. The component-side source images are the datum:
sensor up, socket down, sensor closer to the left edge. A rear inspection view
is mirrored and must not be used to reverse the physical feature coordinates.
