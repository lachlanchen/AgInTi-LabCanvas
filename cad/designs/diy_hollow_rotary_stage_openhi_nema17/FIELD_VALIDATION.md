# OpenHI hollow rotary stage: installed baseline

## Accepted build

The owner reported on 2026-11-16 that the stage was printed by WeNext, installed
and works. The accepted source is
`runs/run-7-upright-chamfered-rotor-prototype-20261106T110659Z/`.
The installation photograph is retained privately, not committed as a lab or
commercial record. The report does not establish positioning accuracy,
repeatability, motor current, service life, payload or production yield.

This design is for the saved **42 x 42 x 40 mm NEMA 17 motor only**. It does not
silently support a 57 mm NEMA 23. Its 31 mm mounting square, 22 mm pilot boss
and 5 mm shaft must remain distinct from the output bearing and tray dimensions.
The 82 mm rotating cap is sized around the 120-tooth belt drive and bearing,
not around a second motor frame size.

## Alignment lesson

The accepted motor is rotated 10 degrees **in the XY plane**. Its front mounting
face is still parallel to the carrier in CAD. The owner confirmed that it must
be turned relative to the tray to align the mounting screws; the rear photograph
is consistent with that description. Do not interpret this as a leaning shaft,
change the axial height, or enlarge the motor pocket without evidence.

The rotation clears the vertical Allen-key paths from the installed belt.
A future parallel-body layout must check all four screw tools as well as the
motor and belt solids. A removable motor plate, secured by accessible outboard
clamps, can separate motor attachment from belt-tension adjustment. Keep that
as a new, untested run, not an overwrite of the installed baseline.

## Fasteners for the installed build

The exact count and dimensions are in `fastener_contract.json`. Prefer a small
matched purchase over a large box that omits M2 x 5, M2 x 14 or the correct
countersunk head. Plain hex nuts are required in the captured pockets; tall
nyloc and flange nuts are not equivalent.

| Position | Fastener | Installed minimum | Important check |
| --- | --- | ---: | --- |
| Motor | M3 x 6 socket head | 4 | 1 mm total flat washers; 3 mm modeled motor engagement |
| Insert | M3 x 8 socket head | 4 | No more than 6 mm below output face |
| Rotor cap | M3 x 12 countersunk | 3 | Length includes head; 90-degree head, OD no more than 6.4 mm |
| Fixed bearing retainer | M2 x 14 socket head | 3 | Head OD no more than 3.8 mm, height no more than 2 mm |
| Polarizer retaining clip | M2 x 5 socket head | 3 | Do not substitute a long screw and press on glass |
| Stand | M4 x 16 socket head | 4 | 1 mm washers and ordinary M4 nuts |
| Stand with optional shim | M4 x 20 socket head | 4, alternative | Only with the 5 mm shim; verify engagement |
| Optical table | M6 x 16 socket head | 2, preferably 4 | 8 mm foot plus 1 mm washer leaves about 7 mm engagement; check table hole depth |

Nut totals: 6 x M2, 7 x M3, 4 x M4 for the standard full accessory assembly.
Motor washers: either four 1 mm washers or eight 0.5 mm washers, OD at most
7 mm. Do not count a spring washer as a controlled flat spacer.

Normal-series M4 and M6 flat washers are commonly 0.8 and 1.6 mm thick, rather
than the original 1 mm reference stack. The M4 x 16 stand screw has about 2.8 mm
bottom clearance with a 0.8 mm washer. An M6 x 16 table screw through the 8 mm
foot with a 1.6 mm washer has about 6.4 mm nominal engagement. Check the supplied
washer and the real breadboard hole depth before tightening.

For a cylindrical socket-head screw, length excludes the head. For a countersunk
screw, length includes the head. This difference is important for the cap.
An M3 label alone does not establish head fit: supplier drawings can list
different countersunk head envelopes. Select the actual head dimension rather
than assuming all DIN/ISO labels or kit photographs are interchangeable.

## Reuse boundary

Preserve run 7, its manufacturing files and fit parameters. Keep future changes
in timestamped runs. Use a new name and separate optional Nutstore folder for an
untested variant so it cannot replace the owner's proven default by accident.
No new order, payment or cart action is implied by regenerating CAD.
