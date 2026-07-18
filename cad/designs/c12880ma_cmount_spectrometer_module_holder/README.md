# C12880MA C-Mount Spectrometer Module Holder

Parametric holder for the measured `38.3 x 22.8 mm` C12880MA module board. The
sensor package, rather than the PCB center, defines the C-mount optical axis.

## Latest Checked Run

`runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/`

Use the unambiguous root handoff:

`USE_THIS_c12880ma_cmount_spectrometer_module_holder.step`

The latest run contains direct-print STEP, STL, and 3MF files, full renders,
alignment drawings, separate socket/plate/proxy STEP files, a smooth editable
STEP, a female-thread cutter, a manifest, and validation evidence.

## Critical Datums

- C-mount axis and sensor center: `Y=0, Z=0`.
- Structural plate: `42 x 42 x 5 mm`; center shifted `+3.6 mm` along PCB
  length.
- Baseline geometry: the clean run-1 holder with the validated run-3 PCB sink.
- Rear rim: `2 mm` outside the `38.7 x 23.2 mm` PCB pocket. A fitted `1.5 mm`
  PCB finishes `0.5 mm` below the rim without moving the sensor or C-mount.
- Source component view: PCB on the table, sensor up, socket/pin row down.
- Holder mating-face view: the component face is turned against the holder, so
  only the PCB short-direction coordinates invert. The C-mount, plate, thread,
  sensor axis, long-direction coordinates, and depth stack do not move.
- C-mount OD: `34 mm`; printable female thread: `25.0 mm` pilot to `25.4 mm`
  nominal groove maximum.
- Board holes: `Y=-13.2/+20.4 mm`, `Z=0`, giving `33.6 mm` spacing.
- M2 printed tap pilots: `1.6 mm`, blind depth `4.5 mm`.
- Verified source orientation: sensor at the PCB top-left, 6P socket/pins below,
  sensor closer to the left PCB edge, and larger PCB margin on the right.
- Six socket solder-tail clearances: joined `3.0 mm` reliefs at `2.54 mm`
  pitch. The source row is at `Z=-9.3 mm`; its mating holder relief is at
  `Z=+9.3 mm`. The refined long-direction center is `Y=-0.4 mm`, only `0.4 mm`
  from run 1.
- In the source component view, the first and last pin centers are about
  `8.8 mm` and `16.8 mm` from the corresponding PCB edges. The relief provides
  `1.0 mm` radial clearance around the `1.0 mm` pin proxy.

The 6P connector clearance is intentionally based on the protruding PCB pins,
not on the connector housing. The photos explain orientation only; they do not
add any housing, daughterboard, notch, or other geometry to the measured holder.

The complete orientation history, failed interpretations, coordinate mapping,
and reusable validation method are documented in
`references/c12880ma-holder-orientation-lessons-2026-07-18.md`.
