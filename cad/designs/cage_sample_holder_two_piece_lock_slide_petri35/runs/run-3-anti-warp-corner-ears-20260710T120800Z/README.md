# Two-Piece Locking Cage Sample Holder

This is a new independent design based on the successful
`cage_sample_holder_openhi_slide_petri35` geometry. The older design is not
changed.

## Design Intent

The holder is split into two printable parts:

1. `bottom_part`: tray for the sample, lower rod sockets, four male lock feet.
2. `top_part`: open frame, upper rod sockets, four matching lock holes.

The sample zone is intentionally large (`80.0 x 40.0 mm`) so it can hold both the OpenHI-style strip
seat and a small petri dish seat in the same center. The top frame is open over
the sample zone and the assembled chamber gap is `18.0 mm`, so
there is room to place and remove the slide or dish with fingers.

## Fit Choices

- Lock feet: `5.8 mm`, from nominal 6 mm minus 0.2 mm.
- Lock holes: `6.2 mm`, from nominal 6 mm plus 0.2 mm.
- Rod sockets: `6.4 mm` blind pockets for nominal 6 mm rods on a `30.0 mm` cage square, centered at ±15.0 mm from the optical/sample center.
- Top rod bosses: `18.0 mm` local islands reconnect the corrected cage sockets to the top frame after the large access window is cut.
- M3 pilot/thread places: `2.6 mm`, intended as a tight printed/tapped pilot rather than a loose clearance hole.

## Sample Seats

- OpenHI strip reference: `72.96 x 20.0 mm`.
- Printed slide sink: `75.0 x 22.0 mm`, `1.2 mm` deep.
- Petri seat: `35.4 mm` for a nominal `33.0 mm` dish, `1.8 mm` deep.
- The slide sink and petri sink overlap at the center by design.

## Run Convention

This project keeps one design folder and archives each major generation as:

```text
runs/run-N-human-readable-info-YYYYMMDDTHHMMSSZ/
```

The root `artifacts/` directory is the latest checked output. Previous runs:

- `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/runs/run-1-original-wide-rod-socket-layout-20260709T031849Z/`
- `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/runs/run-2-correct-30mm-cage-rod-sockets-20260709T032257Z/`
- `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/runs/run-3-anti-warp-corner-ears-20260710T120800Z/`

## Outputs

| Output | Path |
| --- | --- |
| bottom_part_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_bottom_part.step` |
| bottom_part_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_bottom_part.stl` |
| top_part_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_top_part.step` |
| top_part_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_top_part.stl` |
| top_part_180deg_print_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_top_part_180deg_print.step` |
| top_part_180deg_print_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_top_part_180deg_print.stl` |
| assembled_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_assembled.step` |
| assembled_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_assembled.stl` |
| reference_assembly_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_reference_assembly.step` |
| reference_assembly_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_reference_assembly.stl` |
| print_layout_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_print_layout.step` |
| print_layout_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_print_layout.stl` |
| exploded_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_exploded.step` |
| exploded_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_exploded.stl` |
| top_alignment_svg | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_top_alignment.svg` |
| top_alignment_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_top_alignment.png` |
| assembled_render_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_assembled_render.png` |
| exploded_render_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_exploded_render.png` |
| print_layout_render_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_print_layout_render.png` |
| blender_scene | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/cage_sample_holder_two_piece_lock_slide_petri35.blend` |
| manifest | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35/artifacts/manifest.json` |

## Anti-Warp Ears

The latest printable parts include removable Y-shaped anti-warp ears at all
four outer corners. Each ear attaches through two `0.5 mm`
breakaway necks and grows into a wider diagonal tail pad outside the corner, so
the corner is pulled down during printing but the tab can be cut away cleanly.

Use:

- `bottom_part`: normal print orientation; ears are on the bottom bed face.
- `top_part_180deg_print`: top frame already flipped for the 180 degree print orientation; ears are on the bed face.

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_sample_holder_two_piece_lock_slide_petri35` |
| `architecture` | `two printed parts: bottom tray with four male lock feet plus top frame with four matching holes` |
| `outer_width_mm` | `110.0` |
| `outer_height_mm` | `70.0` |
| `plate_thickness_mm` | `8.0` |
| `chamber_gap_mm` | `18.0` |
| `assembled_height_mm` | `34.0` |
| `top_inner_window_mm` | `[82.0, 42.0]` |
| `usable_sample_zone_mm` | `[80.0, 40.0]` |
| `edge_fillet_mm` | `0.8` |
| `lock_nominal_diameter_mm` | `6.0` |
| `lock_foot_diameter_mm` | `5.8` |
| `lock_hole_diameter_mm` | `6.2` |
| `lock_foot_total_height_mm` | `23.2` |
| `lock_hole_depth_mm` | `5.8` |
| `lock_points_mm` | `[[-47.0, -27.0], [47.0, -27.0], [-47.0, 27.0], [47.0, 27.0]]` |
| `rod_diameter_nominal_mm` | `6.0` |
| `rod_socket_diameter_mm` | `6.4` |
| `rod_socket_depth_mm` | `6.0` |
| `rod_socket_back_wall_mm` | `2.0` |
| `m3_thread_pilot_diameter_mm` | `2.6` |
| `cage_rod_pitch_mm` | `30.0` |
| `rod_socket_x_pitch_mm` | `30.0` |
| `rod_socket_y_pitch_mm` | `30.0` |
| `top_rod_socket_centers_mm` | `[[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]]` |
| `bottom_rod_socket_centers_mm` | `[[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]]` |
| `top_rod_boss_diameter_mm` | `18.0` |
| `openhi_strip_nominal_mm` | `[72.96, 20.0]` |
| `openhi_strip_seat_mm` | `[75.0, 22.0]` |
| `openhi_strip_sink_depth_mm` | `1.2` |
| `petri_nominal_diameter_mm` | `33.0` |
| `petri_clearance_diameter_mm` | `35.4` |
| `petri_sink_depth_mm` | `1.8` |
| `optical_window_diameter_mm` | `18.0` |
| `finger_notch_width_mm` | `18.0` |
| `finger_notch_height_mm` | `28.0` |
| `finger_notch_depth_mm` | `3.0` |
| `anti_warp_ears_enabled` | `True` |
| `anti_warp_ear_style` | `four removable Y corner ears per printed part; top ears are placed on the 180-degree print face` |
| `anti_warp_ear_thickness_mm` | `0.65` |
| `anti_warp_ear_breakaway_neck_width_mm` | `0.5` |
| `anti_warp_ear_breakaway_overlap_mm` | `0.35` |
| `anti_warp_ear_arm_offset_mm` | `3.0` |
| `anti_warp_ear_arm_width_mm` | `2.0` |
| `anti_warp_ear_junction_offset_mm` | `7.0` |
| `anti_warp_ear_tail_reach_mm` | `19.0` |
| `anti_warp_ear_tail_width_mm` | `12.0` |
| `anti_warp_ear_note` | `Each ear uses two 0.5 mm breakaway necks at the corner sides and a wider diagonal tail pad outside the part. Remove after print with a knife or flush cutter.` |
| `print_fit_note` | `Male lock feet are nominal -0.2 mm, matching holes are nominal +0.2 mm. Rod sockets use 6.4 mm clearance on a 30 mm cage square; M3 pilot/thread places use 2.6 mm.` |
| `orientation_note` | `Bottom part owns four lower rod sockets and sample seats. Top part owns four upper rod sockets and the open viewing/access window. Print the top with the 180deg print export so the anti-warp ears touch the build plate.` |

## Print Notes

- Print `bottom_part` and `top_part_180deg_print`.
- The `assembled` files are for checking fit.
- The `reference_assembly` files include transparent rod/sample proxies and are not intended as print files.
- If the lock is too tight, lightly sand the four printed feet first; keep the holes unchanged unless necessary.
