# QYH1123 Light-Valve Aligned Cage Holder

This is a new independent 30 mm cage holder for the Qiyun Display QYH1123 LCD
light valve. It follows the clean Lumileds cage-holder style but uses the
QYH1123 drawing as the source of truth.

## Design Rule

The 15 x 15 mm visible aperture is the optical origin. The drawing dimensions
show the V.A. center is 0.9 mm left of the 18 x 20 mm glass body center, so the
pocket is shifted while the aperture remains on the 30 mm cage center.

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
- LCD sink: `18.4 x 20.4 x 2.2 mm`.
- Optical through-window: `13.0 x 13.0 mm`, derived from the QYH1123 visible area.
- Support terrace: `1.0 mm` per side between the 15 x 15 mm V.A. and the through-window.
- Pin relief: shallow bottom channel for the two metal tails.

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder.step` |
| holder_stl | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder.stl` |
| valve_proxy_step | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_valve_proxy.step` |
| valve_proxy_stl | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_valve_proxy.stl` |
| cage_rods_proxy_step | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_cage_rods_proxy.step` |
| cage_rods_proxy_stl | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_cage_rods_proxy.stl` |
| assembly_step | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_assembly.step` |
| assembly_stl | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_assembly.stl` |
| top_alignment_svg | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_top_alignment.svg` |
| top_alignment_png | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/qyh1123_light_valve_aligned_cage_holder_top_alignment.png` |
| manifest | `cad/designs/qyh1123_light_valve_aligned_cage_holder/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `qyh1123_light_valve_aligned_cage_holder` |
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
| `valve_pocket_clearance_mm` | `0.4` |
| `valve_pocket_depth_mm` | `2.2` |
| `active_aperture_width_mm` | `15.0` |
| `active_aperture_height_mm` | `15.0` |
| `terrace_lip_per_side_mm` | `1.0` |
| `terrace_rule` | `The full 18 x 20 mm LCD body sits in a 2.2 mm sink; the through-window is V.A. minus the terrace lip on each side.` |
| `active_center_offset_from_valve_center_x_mm` | `-0.9` |
| `active_center_offset_from_valve_center_y_mm` | `0.0` |
| `pin_pitch_mm` | `2.54` |
| `pin_width_mm` | `0.7` |
| `pin_thickness_mm` | `0.5` |
| `pin_length_mm` | `8.0` |
| `pin_exit_relief_width_mm` | `6.4` |
| `pin_exit_relief_depth_mm` | `2.7` |
| `drawing_tolerance_mm` | `0.2` |
| `coordinate_rule` | `Holder origin is the QYH1123 active aperture center and 30 mm cage center.` |

## Notes

- Print/check the holder-only STEP or STL. The assembly includes transparent
  valve and rod proxies only for alignment inspection.
- If the physical valve is too tight, increase only `valve_pocket_clearance_mm`.
- If the pins need more room, increase `pin_exit_relief_width_mm` or
  `pin_exit_relief_depth_mm`; avoid changing cage-hole coordinates.
