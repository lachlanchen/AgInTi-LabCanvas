# OpenHI NEMA 17 hollow rotary stage

A light-duty, timing-belt-driven prototype with a 30 mm open bore, a metal
6808 bearing, and a removable polarizer insert. The shared upper carrier locates
the motor and bearing. A separate footed stand establishes the table height.
This is a new design, not a modification of the working OpenHI microscope.

Chinese purchasing/assembly tutorial with practical English:
[ASSEMBLY_GUIDE.zh-CN.md](ASSEMBLY_GUIDE.zh-CN.md). Its illustrated XeLaTeX PDF
is exported as `rotary_stage_tutorial_zh.pdf` in the current run and at the
Nutstore project root. The Markdown's render links resolve inside the run copy.

**Status: CAD-checked prototype, not physically tested. Print the fit coupons
first. No angular accuracy or payload rating has been measured.**

## Exact OpenHI motor

The reference is the leaf body `42 stepper motor` inside
`cad/extracted/OpenHI_STEP/42 stepper FH PLP.step.step`. That STEP also contains
unrelated parts, which are excluded. `OpenHI.shapr` identifies the corresponding
`42 stepper motor` folder. The motor is preserved as B-rep, not redrawn as a box.

| Feature | Saved model, mm |
| --- | ---: |
| Body | 42 x 42 x 40 |
| Four mounting-hole centers | 31 x 31 square |
| Locating boss | diameter 22, height 2 |
| Shaft | diameter 5 |
| Shaft beyond motor front face | 22, including the 2 mm boss |

The source shows diameter-3 holes through the body. This does **not** establish
the physical motor's threaded depth, electrical current, wiring, or exact model
number. Check these on the real motor. The reference transform and input hashes
are recorded in each run manifest.

## Mechanism and space

The motor drives a printed 120-tooth ring through a purchased 20-tooth GT2 pulley
and a closed 320-2GT-6 belt. The calculated center distance is 83.884885 mm, with
plus/minus 3 mm motor adjustment. The reduction is 6:1. A 1.8-degree motor gives
0.3 degrees per full step, or 0.01875 degrees per 16x microstep **command**;
these are not accuracy claims. Home sensing and output feedback are not included.

The bearing inner race is stationary. Its outer race turns with the rotor cup.
Separate inner and outer retainers touch only their respective races. The motor
shaft carries its small pulley, not the tray's weight. One bearing keeps this
first build simple; use light, balanced optics and low belt tension. Bearing
play, plastic flex and belt error must be measured before quantitative work.

The output disk is diameter 82 mm. Four M3 holes on a 30 mm square accept an
interchangeable holder; they are **not** passages for fixed cage rods. A complete
GT090101 needs its own carrier adapter and a physical sweep/load check. It is
not included or claimed to fit directly. Keep all stationary rods below the
carrier underside, preferably Z74 or lower in this build.

### Height datums

All Z values are measured from the optical table, not the print bed.

| Surface | Z, mm |
| --- | ---: |
| Foot underside | 0 |
| Carrier underside | 75 |
| Floor under rotating cup | 78 |
| Lowest rotating cup | 79 |
| Motor front face | 80 |
| Bearing bottom / top | 81 / 88 |
| Main rotating tray underside | **85** |
| Belt midplane | 89.75 |
| Output mounting face | 98.5 |
| Polarizer insert top | 101.5 |
| Polarizer retaining ring top | 103.5 |

The 85 mm tray datum does **not** mean that the entire volume below Z85 is empty.
The bare stage has a continuous diameter-30 central optical passage. The outer
cup extends to Z79 and the stationary carrier to Z75. Around the shaft axis,
the old 30 mm dock/lamp/lower-polarizer/LCD stack reaches Z79 and clashes with
this carrier. The previously printed 25 mm dock would lower that stack to Z74,
leaving only 1 mm. Measure the real stack; do not assemble against a collision.
The optional 5 mm stand shim raises the whole upper module and motor together
to a 90 mm tray datum. No drive spacing changes. Longer M4 bolts are then needed.
The open center is reserved for the optical path, not a 42 mm sample holder.

The side foot occupies X58..118, Y-42..42 mm; the optical axis is X=Y=0.
It leaves an 8 mm nominal table-plane gap from a centered 100 x 100 mm dock.
Remove print ears before installation and check the actual dock's feet/tabs.
M6 clearance slots centered at (75,+/-25) and (100,+/-25) follow a 25 mm table
grid. Use an installed screw head and washer envelope when checking neighbors.

## Buy / Taobao search terms

Dimensions, rather than a seller's name, define compatibility. Prices and stock
have not been verified. Buy one bearing and belt before printing the final fits.

| Item | Qty | Search / selection |
| --- | ---: | --- |
| Existing OpenHI motor | 1 | 42 stepper, 5 mm shaft; use the existing motor |
| Metal bearing | 1 | `6808 ZZ 40 52 7 薄壁轴承`; 6808-2RS has the same boundary dimensions but more seal drag |
| Motor pulley | 1 | `2GT 20齿 内孔5mm 带宽6mm 同步轮`; channel 7.5, flanges 1 each, hub 5.5, total 15 mm in this reference |
| Closed timing belt | 1 | `320-2GT-6 闭口同步带`; 2 mm pitch, 320 mm pitch length, 6 mm width |
| Motor screws | 4 | M3 x 6 socket-head, with **1 mm total washer thickness** each |
| Motor washers | 4 sets | M3 OD7 max, total thickness 1 mm; two 0.5 mm washers are acceptable |
| Rotor cap screws | 3 | M3 x 12 countersunk, head diameter <=6.4 mm |
| Rotor captive nuts | 3 | Standard M3, AF5.5, approximately 2.4 mm thick |
| Fixed bearing retainer screws | 3 | M2 x 14 socket-head; head <=3.8 diameter x 2 high |
| Fixed bearing retainer nuts | 3 | M2, AF4, approximately 1.6 mm thick |
| Stand bolts / nuts / washers | 4 each | M4 x 16, standard M4 nuts, 1 mm washers |
| Optional shim bolts | 4 | M4 x 20 with 1 mm washers; verify engagement |
| Accessory nuts | 4 | M3 standard, captured under output disk |
| Insert-to-tray screws | 4 | M3 x 8 socket-head for 3 mm insert; penetration 5 mm below mounting face |
| Polarizer clip screws / nuts | 3 each | M2 x 5 socket-head and standard M2 nuts |
| Table bolts / washers | 2 minimum, 4 optional | M6; length chosen for the real table's permitted engagement plus 8 mm foot and washers |
| Optional driver | 1 | TMC2209 STEP/DIR driver with an existing controller; choose voltage/current from the real motor, not its CAD |

Invert the purchased motor pulley: the short hub is **above** the teeth, not
against the motor. This gives full shaft engagement and accessible grub screws.
Confirm the supplier's actual pulley dimensions before ordering. A taller hub,
different belt width, or different motor shaft length needs a local revision.
Never buy an MXL or T2.5 belt for the modeled GT2 teeth.

## Print files and tolerances

`artifacts/latest.json` identifies the current checked run. `print/<part>/`
contains one grounded, centered, connected print in STEP, STL and 3MF, with a
preview. The assembly STEP is for editing, **not** for slicing as one object.
Purchased components and hardware references never enter print files.

| Printed part | Quantity | Orientation / supports |
| --- | ---: | --- |
| `carrier` | 1 | Underside down, ears included. Local support under raised motor roof is necessary. Keep support out of bearing journal and nut pockets. |
| `footed_stand` | 1 | Flat foot down, ears included. Inspect small nut-pocket roofs; use local support only if the slicer needs it. |
| `rotor_cup` | 1 | Inverted in the supplied print file; tooth-ring face down. Check small flange overhang and nut-pocket bridges. |
| `rotor_cap` | 1 | Inverted: flat top down, bearing boss up. No large unsupported shelf. |
| `inner_race_retainer` | 1 | Flat ring down. |
| `polarizer_insert` | 1 optional | Inverted, broad top face down; locating pilot up. |
| `polarizer_retainer` | 1 optional | Flat down. |
| `height_shim_5mm` | 1 optional | Flat down; only for the raised configuration. |

Starting settings: PETG or another dimensionally stable engineering filament,
0.2 mm layers, 5-6 walls, 40-50% infill. Keep the small gear teeth and retaining
rings effectively solid. PLA is acceptable for a fit trial, but keep motor heat
and creep in mind. These are starting settings, not validated printer profiles.
The 1 mm sacrificial corner tabs are print-only and must be removed for assembly.

| Fit | Model choice | Meaning |
| --- | --- | --- |
| Motor body relief | 42.4 mm, plus X tension travel | 0.2 mm each side |
| Motor boss slot width | 22.4 mm | 0.2 mm radial |
| Bearing rotor seat | 52.1 mm | 0.1 mm diametral allowance |
| Fixed bearing journal | 39.9 mm | 0.1 mm diametral reduction |
| Insert pilot / mating hole | 29.8 / 30.0 mm | 0.2 mm diametral clearance |
| M6 table clearance | 6.4 mm | Clearance, not an M6 printed thread |
| Main M3 clearances | 3.3-3.4 mm | Metal screws and captive nuts |
| Polarizer pocket | 25.7 mm | 0.3 mm diametral clearance for a 25.4 mm reference optic |

There is no universal printer compensation. The coupon set includes bearing
bores 52.0 / 52.1 / 52.2, journals 39.8 / 39.9 / 40.0, and a 120T belt-fit ring.
Print coupons in the final material and orientation. Select a sliding fit that
does not distort the bearing. Never hammer a bearing into the rotor or force
through its seals. If another fit is needed, revise only the seat/journal
parameters and regenerate; do not scale the assembly or change tooth pitch.

The polarizer insert assumes a 25.4 mm diameter, 1 mm thick reference optic.
With it fitted, the clear optical aperture is **24 mm**, not 30 mm. A thinner
film needs a soft peripheral shim. The clip must rest on the insert's perimeter,
never clamp the optic hard or push the optical center. Maximum accessory screw
penetration below the output face is **6 mm**; longer screws can hit fixed parts.

## Assembly and first test

1. Print and test the bearing and belt coupons. Confirm the real motor/pulley.
2. Clean ears and support material. Load the carrier's three M2 nuts from below.
3. Place the bearing over the fixed journal and secure its inner-race retainer
   with M2 x 14 screws. Tighten gently and evenly; do not clamp the seals.
4. Preload three M3 nuts into the rotor cup's underside nut channels; use a
   small piece of removable tape to hold them while starting the screws. Fit the
   cup around the outer race and loosely loop the belt around its teeth. Load
   the four accessory nuts under the cap before closing it. Add the cap with
   M3 x 12 countersunk screws. The
   cap's lower annular boss contacts only the outer race. The two races are
   retained independently, not tightened together into a locked bearing.
5. Confirm the cap's own screw heads are flush. Hand-turn the ring through a
   full revolution before tensioning the belt.
6. Fit the motor from below. Use M3 x 6 screws with 1 mm total washer thickness
   in the recessed slots. Modeled metal engagement is 3 mm. Verify it physically.
7. Fit the inverted 20T pulley inside the loose belt, align both tooth channels, move the
   motor just enough to remove slack, then tighten its four screws. Hand-turn
   again. Belt teeth must seat without climbing; do not overtension.
8. Load the stand's M4 nuts through the inward-facing slots. Attach the carrier
   with M4 x 16 and 1 mm washers. Add the optional shim only if height is needed.
   Bolt the foot to the table with at least two well-spaced M6 bolts.
9. Terminate fixed cage rods below the carrier. Check the real lower optical
   stack, cables and all moving accessory corners. Attach the removable insert
   only after the empty ring turns freely. Use a soft peripheral optical shim.
10. Start slowly at a conservative motor current. Test repeated forward/reverse
    moves with an independent angular reference. Settle before measuring. Do not
    infer precision from microsteps or transfer a published stage's performance.

## Rebuild and validation

```bash
cad/.conda/cad-python/bin/python cad/designs/diy_hollow_rotary_stage_openhi_nema17/build_stage.py
/home/lachlan/.local/share/labcanvas/blender/blender-4.0.2-linux-x64/blender \
  --background --python cad/designs/diy_hollow_rotary_stage_openhi_nema17/render_stage.py
python3 cad/designs/diy_hollow_rotary_stage_openhi_nema17/package_stage.py
```

Packaging the Chinese tutorial requires Pandoc, XeLaTeX and Noto CJK fonts.
For a documentation-only update, use `package_stage.py --chinese-only`; this
preserves geometry and the English PDF, adds the Chinese/English-learning
tutorial and updates the verified Nutstore handoff without a new CAD run.

The builder isolates the exact motor, checks the empty optical bore, four sampled
angles and a conservative full-rotation envelope, verifies belt/head separation,
round-trips STEP, and checks each print's connected watertight mesh, true Z=0,
nonempty first layer and one millimeter-unit 3MF build item. Renders check camera
margins. The package script copies the current run to Nutstore and verifies file
hashes. CAD checks do not replace physical fit, vibration or accuracy testing.

## Sources and licensing

- [Open Photonics, HardwareX 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11639585/):
  an optical rotation-stage precedent using belt drive and printed mechanics.
  Its NEMA 11 design is not copied as a ready-made NEMA 17 stage; none of its
  measured performance is claimed here. Design files: <https://osf.io/6gd27/>.
- [JTEKT 6808 boundary/mounting dimensions](https://www.jtekt.co.jp/products/bearing/en/p/detail/?pno=6808+2RS):
  40 x 52 x 7 mm, with 42 mm inner shoulder and maximum 50 mm outer shoulder.
  The reference is the 2RS catalog entry; the proposed purchase is ZZ.
- [NopSCADlib pulley.scad](https://github.com/nophead/NopSCADlib/blob/master/vitamins/pulley.scad)
  and [pulleys.scad](https://github.com/nophead/NopSCADlib/blob/master/vitamins/pulleys.scad):
  rounded GT2 grooves and the 20T purchased-pulley envelope. Copyright Chris
  Palmer 2018, GPL-3.0-or-later. The groove construction is adapted in Python;
  this design's new code/geometry is distributed under that license. See LICENSE.
  Owner-supplied OpenHI motor/reference geometry retains its original rights.
- [EasyPrintedStages](https://github.com/SGTHANKI/EasyPrintedStages): useful
  alternative architecture, not a drop-in motorized hollow stage; not copied.

Chinese terms: hollow rotary stage = 中空旋转台; timing-belt drive = 同步带传动;
drive pulley = 主动同步轮; driven pulley = 从动同步轮; captive nut = 防转螺母槽内螺母;
bearing seat = 轴承座; locating boss = 定位凸台; mounting foot = 安装底脚.
