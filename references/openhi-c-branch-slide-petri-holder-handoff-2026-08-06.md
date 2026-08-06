# OpenHI C-Branch Slide/Petri Holder Handoff

Date: 2026-08-06

Canonical design:
`cad/designs/openhi_c_branch_slide_petri35_holder/`

Current run:
`runs/run-2-threaded-two-part-c-branch-holder-print-ready-20260806T034958Z/`

## Final Design Contract

The final printable assembly has exactly two independent parts:

1. A bottom slide/Petri sample tray with a female 30 mm OpenHI thread.
2. One socket that covers the upward OpenHI C-branch nose and chamfer and then
   continues into a male 30 mm OpenHI thread that screws into the tray.

There is no top frame, cage interface, coupon, adhesive spigot, or intermediate
connector in run 2. The socket itself is the complete C-branch-to-holder
adapter.

Run 1 remains archived because it documents the earlier smooth socket and
registration-spigot interpretation, but it is not the latest print target.

## Geometry Sources

- Accepted sample tray:
  `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/build_cage_sample_holder_two_piece_lock_slide_petri35.py`
- Measured OpenHI C branch:
  `cad/extracted/OpenHI_STEP/C.step`
- Validated OpenHI female thread convention:
  `cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild/`
- Validated companion receiver work:
  `cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/`

The build imports the accepted tray functions instead of redrawing its slide
seat, Petri seat, finger notches, optical window, plate outline, or anti-warp
ears. It deliberately omits the old lower cage sockets and lock feet.

## C-Branch Socket

The real C branch has:

- approximately 24.4 mm plain nose/body diameter;
- approximately 25.2 mm thread crest envelope;
- approximately 3.9 mm exposed nose length;
- a 7.8 mm axial taper/chamfer;
- an approximately 40 mm large shoulder.

The socket therefore uses:

- 25.5 mm smooth nose receiver ID;
- 40.2 mm taper mouth ID;
- 7.8 mm taper length;
- 42.0 mm outer cup diameter;
- 12.8 mm cup length;
- 18 mm optical opening;
- 5.0 mm male threaded extension;
- 17.8 mm total socket length.

The 42 mm cup is not another connector. It is the lower region of the same
socket and is required to enclose the 40 mm C-branch chamfer. A 29.8 mm OD cup
could not cover that chamfer; 29.8 mm belongs only to the upper male thread
root.

## Thread Terminology And Dimensions

Avoid the ambiguous word `pivot` for thread diameters. Use these terms:

- male root diameter: diameter of the cylinder before the male tooth is added;
- male crest diameter: maximum outside thread diameter;
- female land/pilot diameter: minimum smooth internal diameter before the
  groove cutter expands it;
- female groove diameter: maximum internal diameter after thread subtraction.

Run 2 uses the physically validated OpenHI 30 mm family:

| Feature | Diameter |
| --- | ---: |
| Male root | 29.8 mm |
| Male crest | 30.2 mm |
| Female land/pilot | 30.0 mm |
| Female groove maximum | 30.4 mm |

Other thread parameters:

- pitch: 0.8 mm;
- radial tooth height: 0.2 mm;
- tooth base: 0.8 mm;
- thread length: 5.0 mm;
- diametral clearance at root/land: 0.2 mm;
- diametral clearance at crest/groove: 0.2 mm.

The tooth height is radial. A 0.2 mm radial tooth changes the diameter by 0.4
mm, which is why 29.8 becomes 30.2 on the male and 30.0 becomes 30.4 in the
female groove.

Both male and female helical construction sweeps extend 0.4 mm, half a pitch,
beyond both intended end planes. The sweeps are then intersected with an exact
5 mm clipping solid. This creates complete end teeth without exporting thread
overflow.

## Axial Stack

Socket coordinates in assembly space:

- C-branch cup: `z=0..12.8 mm`;
- male thread: `z=12.8..17.8 mm`;
- tray contact plane: `z=12.8 mm`;
- tray: local `z=0..8 mm`, translated to assembly `z=12.8..20.8 mm`;
- tray female thread: local `z=0..5 mm`.

The male thread occupies the female thread volume with 0.2 mm diametral
clearance. The socket shoulder contacts the tray underside at `z=12.8 mm`.
The aligned real C reference ends at about `z=11.7 mm`, leaving approximately
1.1 mm before the socket's internal optical ledge.

## Print Orientation

- Tray: normal orientation, with its accepted anti-warp ears on the bed.
- Socket: rotate 180 degrees so the male-thread/18 mm optical face rests on the
  bed and the wide 40.2 mm C-branch cavity points upward.

The flipped socket orientation avoids trying to start the print from the thin
0.9 mm radial wall around the wide cavity mouth.

## Artifact Contract

Direct-print files:

- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_sample_holder_female30_thread.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_c_branch_socket_male30_thread.*`
- `PRINT_THIS_openhi_c_branch_slide_petri35_holder_two_part_layout.*`

Unambiguous assembly:

- `USE_THIS_openhi_c_branch_slide_petri35_holder_assembly.step`

The print files are provided as STEP, STL, and 3MF. The assembly, exploded,
real-C fit check, threaded section, and exact direct-print layout each have a
checked PNG render. Reference hardware is visualization-only.

## Validation Results

- holder: one valid B-rep solid, `161 x 121 x 8 mm` including anti-warp ears;
- socket: one valid B-rep solid, `42 x 42 x 17.8 mm`;
- assembly: exactly two solids;
- print-layout STL: exactly two watertight components;
- holder and socket STLs: one watertight component each;
- holder/socket intersection volume: 0;
- socket/real-C reference intersection volume: 0;
- 3MF packages: valid ZIP/model packages;
- helical faces are bounded inside the intended 5 mm thread length;
- visual review confirms no top frame, coupon, shell fragment, or third part.

## Reuse Rules

1. Distinguish the large physical receiver cup from its smaller threaded
   extension. Do not force both regions to share one OD.
2. Define every mating thread using root, crest, land, groove, pitch, radial
   height, and length; do not rely on one ambiguous nominal diameter.
3. Keep the adapter as one continuous solid when it must cover one reference
   interface and screw into another.
4. Keep the sample tray independent so socket fit can be revised without
   rebuilding accepted sample geometry.
5. Extend thread construction by half a pitch, then clip to the exact parent
   length.
6. Export the actual-use and supported print orientations separately.
7. Fit-check against a bounded, transformed copy of the real STEP reference,
   but never include reference hardware in print files.
8. Validate B-rep solid count, bbox, STL topology, 3MF package integrity,
   collision volume, feature probes, and renders before sync.
