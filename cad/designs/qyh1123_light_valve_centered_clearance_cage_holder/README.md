# QYH1123 Light-Valve Centered Clearance Cage Holder

## Full-Through Pin And Dupont Clearance

The latest holders remove the blind floor beneath the two perpendicular LCD
terminals. One connected **12 x 9 mm through-window** clears both pins, the
space between them, and a generous connector region. The opening spans local
LCD coordinates `x=-6..6`, `y=-16.5..-7.5 mm` and the full 8 mm body thickness.
It rotates with the seat in the 45-degree version.

- `runs/run-3-0deg-full-through-pin-dupont-clearance-print-ready-20261028T120038Z/`:
  accepted unrotated holder with the through-window.
- `runs/run-4-45deg-full-through-pin-dupont-clearance-print-ready-20261028T120038Z/`:
  accepted 45-degree holder with the same local through-window.

Only this window is subtracted from the accepted STEP. The 42 x 42 x 8 mm
body, 18.6 x 20.6 mm LCD pocket, nominal 2.2 mm pocket depth, 13 x 13 mm optical
aperture and all four cage bores remain unchanged. A 1 mm ledge remains between
the optical aperture and the connector opening. The original shallow outbound
channel is retained outside the new through-window; the window does not cut
through a cage-rod collar in either orientation. Earlier runs remain available.

Use each run's holder-only `PRINT_THIS_*.3mf`, `.stl` or `.step`. Assembly STEP
files include separate glass, rear-facing pins, rods and an illustrative
6 x 4 x 10 mm connector envelope. These references are excluded from print
files. The connector envelope is not measured supplier CAD. The holder remains
8 mm thick, so longer pins, plugs and wires may project beyond its rear face;
this is not a closed, flush connector enclosure.

Each run includes front, rear, connector-reference and direct-print PNGs,
source snapshots, a geometry/print manifest, and a checksum-verified Nutstore
copy under the matching project/run folder. The manifests verify a single
valid holder solid, unchanged cage collars, unobstructed pin/plug envelopes,
STEP round-trip equivalence, watertight print mesh, and a nonempty first layer.

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/build_pin_clearance_handoff.py
python -m unittest tests.test_qyh1123_full_pin_clearance
```

The builder renders and syncs both runs. Optional `--references PHOTO ...`
copies local reference photos into ignored run folders using neutral filenames;
private attachment names are not included in manifests or tracked source.

## Exact Copy And 45-Degree Seat

The 2026-10-28 handoff preserves this accepted tolerance-adjusted design and
adds a second orientation. Original source STEP/STL/assembly files remain
unchanged, including every fit allowance.

- `runs/run-1-exact-tolerance-adjusted-original-print-ready-20261028T053648Z/`:
  byte-identical holder and assembly copies, plus grounded holder-only prints.
- `runs/run-2-lcd-seat-45deg-print-ready-20261028T053648Z/`: only the LCD seat,
  optical window, pin relief and LCD/pin reference rotate 45 degrees about Z,
  counterclockwise viewed from the pocket face. The outer 42 x 42 x 8 mm body
  and four 6.4 mm bores on the 30 mm cage pattern remain fixed.

Each run contains a separate alignment assembly, holder-only `PRINT_THIS`
STEP/STL/3MF, top/assembly/print renders, source copies and validation manifest.
No new ears, fastener holes or fit adjustments are added. The 45-degree pin
relief meets a corner rod opening at the front; rear bore geometry is retained
and the modeled pins clear the rods. Keep external wires clear of that rod.

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/build_seat45_handoff.py
blender --background --threads 6 --python-exit-code 1 --python \
  cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/render_seat45_handoff.py
python cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/sync_seat45_handoff.py
python -m unittest tests.test_qyh1123_seat45_handoff
```

Nutstore copies use the matching run folders under
`/home/lachlan/Nutstore Files/Projects/LabCanvas/qyh1123_light_valve_centered_clearance_cage_holder/`.

This is a new independent 30 mm cage holder for the Qiyun Display QYH1123 LCD
light valve. It follows the clean Lumileds cage-holder style and keeps the old
design unchanged, but fixes the practical alignment issue seen in the print:
the LCD body, active window, pin pair, pin relief, and cage center are all
centered on the same datum.

## Design Rule

The 15 x 15 mm visible aperture is the optical origin and is also used as the
physical glass/pin center for this centered-fit variant. This intentionally
removes the previous `0.9 mm` lateral shift so the margin on the side parallel
to the pin-header side is equal left/right. The LCD sink is enlarged by
`0.1 mm` on each side relative to the previous holder.

The holder is a single printable body with separate CAD proxies for the valve
and rods. There are no fragile clamps or decorative cuts.

## QYH1123 Dimensions Used

- Outer body: `18.0 x 20.0 x 2.0 mm`.
- Visible area: `15.0 x 15.0 mm`.
- Through light window: `13.0 x 13.0 mm`, derived from the
  `15.0 x 15.0 mm` visible area minus a `1.0 mm`
  terrace on each side.
- Pin connector: two metal pins, `2.54 mm` pitch, `8.0 mm` tail length.
- Drawing tolerance: `+/-0.2 mm`.
- Electrical table: pin 1 = `COM`, pin 2 = `SEG`.
- Official page: `http://www.qiyun-display.cn/Products_1/59.html`.
- Reference folder: `cad/references/qiyun-display-qyh1123-light-valve`.

## Holder Geometry

- Body: `42.0 x 42.0 x 8.0 mm`.
- Cage rod holes: 30 mm pitch at `(+/-15, +/-15)`, `6.4 mm` clearance.
- LCD sink: `18.6 x 20.6 x 2.2 mm`, centered on the cage datum.
- Optical through-window: `13.0 x 13.0 mm`, derived from the QYH1123 visible area.
- Support terrace: `1.0 mm` per side between the 15 x 15 mm V.A. and the through-window.
- Pin relief: shallow bottom channel for the two metal tails, centered on x=0 and widened by `0.1 mm` on each side.

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder.step` |
| holder_stl | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder.stl` |
| valve_proxy_step | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_valve_proxy.step` |
| valve_proxy_stl | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_valve_proxy.stl` |
| cage_rods_proxy_step | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_cage_rods_proxy.step` |
| cage_rods_proxy_stl | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_cage_rods_proxy.stl` |
| assembly_step | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_assembly.step` |
| assembly_stl | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_assembly.stl` |
| top_alignment_svg | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_top_alignment.svg` |
| top_alignment_png | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/qyh1123_light_valve_centered_clearance_cage_holder_top_alignment.png` |
| manifest | `cad/designs/qyh1123_light_valve_centered_clearance_cage_holder/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `qyh1123_light_valve_centered_clearance_cage_holder` |
| `reference_folder` | `cad/references/qiyun-display-qyh1123-light-valve` |
| `body_width_mm` | `42.0` |
| `body_height_mm` | `42.0` |
| `body_thickness_mm` | `8.0` |
| `edge_fillet_mm` | `0.8` |
| `cage_rod_pitch_mm` | `30.0` |
| `cage_rod_clearance_diameter_mm` | `6.4` |
| `valve_outer_width_mm` | `18.0` |
| `valve_outer_height_mm` | `20.0` |
| `valve_thickness_mm` | `2.0` |
| `valve_pocket_clearance_mm` | `0.6` |
| `valve_pocket_extra_clearance_each_side_from_previous_mm` | `0.1` |
| `valve_pocket_depth_mm` | `2.2` |
| `active_aperture_width_mm` | `15.0` |
| `active_aperture_height_mm` | `15.0` |
| `terrace_lip_per_side_mm` | `1.0` |
| `terrace_rule` | `The full 18 x 20 mm LCD body sits in a 2.2 mm sink; the through-window is V.A. minus the terrace lip on each side.` |
| `active_center_offset_from_valve_center_x_mm` | `0.0` |
| `active_center_offset_from_valve_center_y_mm` | `0.0` |
| `alignment_override` | `Centered fit variant: LCD body, active aperture, pin pair, pin relief, and 30 mm cage datum all share x=0/y=0. This intentionally removes the prior -0.9 mm active-area offset assumption.` |
| `pin_pitch_mm` | `2.54` |
| `pin_width_mm` | `0.7` |
| `pin_thickness_mm` | `0.5` |
| `pin_length_mm` | `8.0` |
| `pin_exit_relief_width_mm` | `6.6` |
| `pin_exit_relief_depth_mm` | `2.7` |
| `drawing_tolerance_mm` | `0.2` |
| `coordinate_rule` | `Holder origin is the QYH1123 active aperture center, LCD body center, pin relief center, and 30 mm cage center.` |

## Notes

- Print/check the holder-only STEP or STL. The assembly includes transparent
  valve and rod proxies only for alignment inspection.
- If the physical valve is too tight, increase only `valve_pocket_clearance_mm`.
- If the pins need more room, increase `pin_exit_relief_width_mm` or
  `pin_exit_relief_depth_mm`; avoid changing cage-hole coordinates.
