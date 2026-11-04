# OpenHI motor intake and hollow rotary-stage design record

Project: `cad/designs/diy_hollow_rotary_stage_openhi_nema17/`.
The project README contains assembly, purchasing, fits, print orientations and
source licensing. The run manifest is the geometry-validation record.

## Motor identity before design

`OpenHI.shapr` was decoded read-only with the installed
`parametric-cad-design/scripts/shapr_native_decoder.py`. Its `42 stepper motor`
folder contains the motor body. The corresponding STEP is a mixed assembly:
`cad/extracted/OpenHI_STEP/42 stepper FH PLP.step.step`. Select only the leaf
label `42 stepper motor`; do not import the adjacent chamber, PCB and fixture.

Measured body: 42 x 42 x 40 mm. Hole square: 31 mm. Boss: diameter 22 x 2 mm.
Shaft: diameter 5, reaches 22 mm from the motor front face, or 20 mm beyond the
boss. Neutral transform from the source is (-261, -114.5, -61.5) mm. Preserve
the imported B-rep and record hashes. The modeled through-holes do not establish
real motor thread depth, current or winding identity.

## Mechanism choices

- A side-mounted motor and GT2 belt leave the center open. Direct external gears
  are possible but introduce a center-distance/backlash adjustment; the first
  prototype uses a belt and no idler.
- One 6808 bearing reduces the part count for a light balanced polarizer. Inner
  race stationary, outer race rotating; retain each race independently. Shoulder
  relief must clear the bought bearing's corner radii. Do not clamp its shields.
- A purchased 20T pulley and printed 120T ring use a 320 mm closed belt. Solve
  the unequal-pulley tangent geometry, rather than a rough 2C + circumference
  estimate. Nominal C=83.884885 mm; motor slots provide +/-3 mm travel.
- The motor pulley is inverted to engage the actual saved 22 mm shaft while
  keeping the belt above the carrier. The hub stays accessible from above.
- Captive metal nuts are simpler here than many printed small screw threads.
  The rotor cap's nut pockets must sit within the toothed-ring material, not
  dangle below a narrow bearing cup. Three M3x12 countersunk screws are used.
- Check screw heads against the belt, not merely motor-body clearance. Recessed
  motor slots with M3x6 screws and a 1 mm washer stack give 3 mm motor engagement
  and 0.75 mm vertical head-to-belt separation.

## Height and cage interfaces

The 85 mm requirement is a main tray underside datum. The fixed carrier reaches
Z75, rotating cup Z79, output face Z98.5. Document this stack honestly; do not
call all space below Z85 unobstructed. A 5 mm shim raises the complete upper
module without changing drive alignment. The independent footed stand attaches
to M6 breadboard holes on the 25 mm grid.

The removable insert uses a 30 mm square of M3 accessory holes. A fixed cage
cannot continue through those holes while they rotate. Existing rods must end
below the stationary carrier. The old lower optical stack's 79 mm height clashes
with Z75; a 25 mm rather than 30 mm dock gives 74 mm, still only 1 mm clearance.
Measure the real stack and use the height shim when necessary. No original dock,
cage, microscope or experimental data has been altered.

## Export lessons

- Use analytic OCCT `BRepBndLib.AddOptimal_s(..., False, False)` bounds to ground
  print copies. Cached triangulation bounds can introduce a nonzero first-layer
  offset even when the original part is a flat ring.
- Keep assembly coordinates and purchased references out of `PRINT_THIS` files.
  Each print is one connected watertight body at Z=0 with one 3MF build item.
- Invert the cup, cap and optical insert independently for their supplied print
  copies. The carrier still needs local motor-roof support; do not label the
  whole mechanism support-free.
- Bearing fits are not global scaling. Test bores 52.0/52.1/52.2 and journals
  39.8/39.9/40.0 with the real material/bearing before committing to full prints.
- Render each exact print orientation, keep at least 8% camera margins, and save
  a complete white-background overview plus explanatory exploded view.
- Copy only the checked current run to a clean Nutstore project/run folder,
  include source snapshots and checksum verification, and keep all local runs.

## Primary references

- [Open Photonics](https://pmc.ncbi.nlm.nih.gov/articles/PMC11639585/) is a related
  belt-driven optical-stage precedent. Its reported performance does not apply
  to this new, untested prototype.
- [JTEKT 6808 catalog](https://www.jtekt.co.jp/products/bearing/en/p/detail/?pno=6808+2RS)
  supplies the 40 x 52 x 7 mm envelope and mounting shoulder dimensions.
- [NopSCADlib GT2 geometry](https://github.com/nophead/NopSCADlib/blob/master/vitamins/pulley.scad)
  supplies the adapted rounded-groove construction, under GPL-3.0-or-later.
  Keep the copyright notice and project-local license with this derivative.

Commanded microsteps are not measured accuracy. No load rating, repeatability,
software home, encoder or physical validation is claimed by a valid CAD export.
