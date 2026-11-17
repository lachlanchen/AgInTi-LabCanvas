# GSP-25 4.5 mm polarizer: two floating-cap holders

## Geometry and fit

This upgrade replaces only the optical insert and its retaining cap. The installed run-7 bearing, rotor, carrier, stand and belt are unchanged. It also fits the unchanged output interface of the optional parallel-motor run 8.

The input is the measured **25.4 mm diameter, 4.5 mm thickness** optic. The current [Hengyang GSP family catalog](https://www.hengyangbuy.com/Product3?cid=509) gives an approximate family thickness that differs from this measured part; it is not substituted for the measurement.

Both halves have a **2.0 mm-deep, 25.7 mm-diameter recess**, on the same optical axis. The pockets total 4.0 mm, intentionally less than the glass thickness. Consequently, the plastic faces remain **0.5 mm apart without pads**, or **0.7 mm apart with two nominal 0.1 mm peripheral pads**. This is a floating retaining cap, not a housing whose faces must close together.

The clear aperture remains 24 mm. Each retaining lip is 1.6 mm thick, making each main plastic half 3.6 mm high; the recess depth and total plastic thickness are different dimensions. The lower insert also retains the accepted 29.8 mm-diameter, 2 mm-long locating pilot. The larger lips leave a 1 mm roof over the captive-nut pockets.

Use clean, thin, soft peripheral gaskets or shims; keep adhesive away from optical faces. The two 0.1 mm pads shown in the assembly are reference envelopes, not rigid printed washers or supplied factory items. Actual pad thickness changes the visible gap. Place the optic without force, lower the cap evenly, and tighten only until play is removed. **Never close the remaining gap by tightening the screws against the glass.** Uneven pressure can chip the edge or affect optical performance.

The new cap top is Z106.4 mm with the modeled pads, versus Z103.5 mm for the old 1 mm-optic model. Check the real microscope's overhead clearance before installation. The optical axis, output mounting surface at Z98.5, 30 mm mounting square, 6808 fit and 85 mm tray datum have not moved.

## Two fastening options

| Variant | Insert holes | Cap screws | Nuts |
| --- | --- | --- | --- |
| `direct_pilot` | Three 2.5 mm pilot holes; tap M3 x 0.5 for ordinary machine screws | 3 x M3 x 8 socket-head plus 0.5 mm flat washer each | None |
| `captive_nut` | Three 3.3 mm clearance holes and underside hex pockets, AF5.8 x 2.6 deep | Same 3 x M3 x 8 and 0.5 mm washers | 3 ordinary M3 nuts, AF5.5 x 2.4 high |

The cap geometry is identical in both options. Do not mix up the two inserts: a 2.5 mm pilot is not a 3.3 mm clearance hole. Direct machine screws require a properly formed thread; tapping before the optic is installed is preferred. A screw sold specifically as a plastic thread-forming or self-tapping screw may require another pilot size. A universal "subtract 0.5 mm" rule is not appropriate for every screw.

With the modeled pad stack, screw tips remain 0.4 mm above the tray mounting face, with 3.2 mm engagement in the direct insert or approximately 2.2 mm engagement in the nut. These are nominal stack-up checks, not strength measurements. Confirm actual screw length, washers and pad thickness; a longer screw must not bottom against the rotor. If pads are omitted, use a 1 mm total washer stack to restore tip clearance. Do not use M3 x 10 screws by substitution.

The four existing M3 x 8 insert-to-tray screws and the tray's captive nuts are retained. Their nominal penetration becomes 4.4 mm, below the existing 6 mm maximum. Load the cap's three M3 nuts into the underside pockets **before** mounting the nut-version insert on the tray.

For one of each variant: two inserts, two caps, six M3 x 8 cap screws, six 0.5 mm M3 flat washers and three ordinary M3 nuts. Each installed insert also uses the four existing M3 x 8 tray screws. No new bearing or belt is required.

## Which files to print

Each variant folder has `print/insert/` and `print/retainer/` with grounded STEP/STL/3MF and orientation PNGs. The insert's FDM files include removable 1 mm anti-warp ears. Its optical pocket needs only a short annular bridge in the supplied inverted orientation; inspect the slicer's actual result. The cap prints top-face down. Factory files have **no ears**, glass, hardware, pads or coupons.

`manufacturing/wenext/manufacturing_manifest.json` specifies three unique models: direct insert x1, nut insert x1, and shared cap x2. Do not order the full assembly STEP as a manufactured part. The WeNext preparation targets the same functional white nylon as the accepted print, with current pricing and tolerances checked separately. The [supplier's nylon page](https://www.wenext.com/materials/3d-plastic/nylon) lists process tolerances larger than some nominal fit allowances; finish holes gently if needed, without globally scaling the parts.

## BRG bore, BRG journal and GT2-120T

**BRG** abbreviates **bearing** (轴承). A **bore** is an internal hole (轴承孔/座孔); a **journal** is the external cylindrical locating surface that enters the bearing's inner ring (轴颈/配合轴台).

The files labeled `coupon_bearing_bore_*`, `coupon_bearing_journal_*` and `coupon_GT2_120T_belt_fit` are **fit-test coupons**, not missing assembly parts. They allow a small print to test the bearing fit or belt teeth before printing the whole stage. They need not be printed or installed now that the real assembly fits. The working 120-tooth GT2 pulley is already integrated into the rotor cup; the belt-fit coupon is not a second wheel to add.

The successful bearing fit remains **52.1 mm bore for the 52 mm bearing OD**, and **39.9 mm journal for the 40 mm bearing ID**. These 0.1 mm diametral allowances are feature-specific, not a tolerance to apply to every hole.

## Why the inner-race retainer is 42 mm OD

The stationary journal is 39.9 mm OD. The lower shoulder and upper retainer are both 42 mm OD, deliberately larger than the bearing's 40 mm ID. Each overlaps the inner-ring face by approximately **1 mm radially**. The matching diameters form two axial stops on opposite faces of the inner ring; they are not redundant adjacent cylinders.

The retainer is ID30 x OD42 x 1.5 mm thick and sits at Z88..89.5. Three M2 screws secure it to the fixed central support. Its small OD avoids clamping the rotating outer ring or the bearing shield. The bearing may stay down under gravity without it, but the upper retainer limits upward movement. Keep it installed. This is the intended reference contact arrangement; confirm that the printed lip reaches the actual inner metal ring without touching its seal. If the physical ring is only about 40 mm OD, it is not the intended 42 mm retainer and should be measured before use. This upgrade does not enlarge or reorder that working part.

## Fastener vocabulary

- **Screw directly into the printed plastic**: 螺丝直接拧入打印塑料件，泛指这种固定方式。
- **Self-tapping screw**: 自攻螺丝，自行切削或形成内螺纹。
- **Thread-forming screw for plastic**: 塑料用挤压成牙螺丝，以材料变形形成螺纹。
- **Pilot hole / tap-drill hole**: 底孔 / 攻丝底孔。
- **Tap the hole M3 x 0.5**: 用丝锥将孔攻成 M3 x 0.5 内螺纹。
- **Through-bolt with a nut**: 螺栓穿过零件后用螺母固定。
- **Captive nut / nut pocket**: 被限位的螺母 / 螺母槽。
- **Recess / retaining lip / axial gap**: 沉槽 / 挡边或承托边 / 轴向间隙。

Example: "Both fastening methods are fine: screws into tapped holes in the printed part, or through-bolts with captive nuts." 两种固定方式都可以：拧入打印件的攻丝孔，或者使用贯穿螺栓与限位螺母。
