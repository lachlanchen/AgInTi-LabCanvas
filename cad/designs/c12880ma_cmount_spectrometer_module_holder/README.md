# C12880MA C-Mount Spectrometer Module Holder

Parametric holder for the measured `38.3 x 22.8 mm` C12880MA module board. The
sensor package, rather than the PCB center, defines the C-mount optical axis.

## Latest Checked Run

`runs/run-3-component-side-orientation-pin-row-refined-print-ready-20260718T101655Z/`

Use the unambiguous root handoff:

`USE_THIS_c12880ma_cmount_spectrometer_module_holder.step`

The latest run contains direct-print STEP, STL, and 3MF files, full renders,
alignment drawings, separate socket/plate/proxy STEP files, a smooth editable
STEP, a female-thread cutter, a manifest, and validation evidence.

## Critical Datums

- C-mount axis and sensor center: `Y=0, Z=0`.
- Structural plate: `42 x 42 x 5 mm`; center shifted `+3.6 mm` along PCB
  length.
- PCB sink: a `2 mm` raised rim exists only outside the `38.7 x 23.2 mm`
  board pocket. The 1.5 mm board finishes `0.5 mm` below the rim without
  moving the original board/sensor seating datum.
- C-mount OD: `34 mm`; printable female thread: `25.0 mm` pilot to `25.4 mm`
  nominal groove maximum.
- Board holes: `Y=-13.2/+20.4 mm`, `Z=0`, giving `33.6 mm` spacing.
- M2 printed tap pilots: `1.6 mm`, blind depth `4.5 mm`.
- Verified component-side orientation: sensor up, 6P socket down, sensor closer
  to the left PCB edge, and larger PCB margin on the right.
- Six socket solder-tail clearances: joined `3.0 mm` reliefs at `2.54 mm`
  pitch, centered at `Y=-0.4 mm`, `Z=-9.3 mm` on the PCB seating surface.
- Pin-row center margins are approximately `8.8 mm` left and `16.8 mm` right;
  the relief gives `1.0 mm` radial clearance around the `1.0 mm` pin proxy.

The 6P connector clearance is intentionally based on the protruding PCB pins,
not on the connector housing. Front/rear camera views may mirror the drawing,
but the physical feature coordinates preserve the component-side orientation.
