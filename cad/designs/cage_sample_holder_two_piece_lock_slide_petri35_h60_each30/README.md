# 60 mm Two-Piece Locking Cage Sample Holder

This is a new independent design based on the successful
`cage_sample_holder_openhi_slide_petri35` geometry. The older design is not
changed.

## Design Intent

The holder is split into two printable parts:

1. `bottom_part`: tray for the sample, lower rod sockets, four male lock feet.
2. `top_part`: open frame, upper rod sockets, four matching lock holes.

The sample zone is intentionally large (`80.0 x 40.0 mm`) so it can hold both the OpenHI-style strip
seat and a small petri dish seat in the same center. The top frame is open over
the sample zone and the assembled chamber gap is `22.0 mm`, so
there is room to place and remove the slide or dish with fingers.

## Height Contract

- Finished assembly height: `60.0 mm`.
- Top frame body: `30.0 mm`, placed from z=`30.0 mm` to z=`60.0 mm`.
- Bottom tray body: `8.0 mm`, with tall lock posts for the interface.
- Bottom printable part height including lock posts: `35.2 mm`.
- Top printable part height: `30.0 mm`.
- Note: a real foot-in-hole lock needs overlap. Exact two printed parts of 30 mm plus inserted lock engagement cannot also produce a 60 mm final height, so this variant keeps the 60 mm final assembly and records the lock-post protrusion explicitly.

## Fit Choices

- Lock feet: `5.8 mm`, from nominal 6 mm minus 0.2 mm.
- Lock holes: `6.2 mm`, from nominal 6 mm plus 0.2 mm.
- Rod sockets: `6.4 mm` blind pockets for nominal 6 mm rods.
- M3 pilot/thread places: `2.6 mm`, intended as a tight printed/tapped pilot rather than a loose clearance hole.

## Sample Seats

- OpenHI strip reference: `72.96 x 20.0 mm`.
- Printed slide sink: `75.0 x 22.0 mm`, `1.2 mm` deep.
- Petri seat: `35.4 mm` for a nominal `33.0 mm` dish, `1.8 mm` deep.
- The slide sink and petri sink overlap at the center by design.

## Outputs

| Output | Path |
| --- | --- |
| bottom_part_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_bottom_part.step` |
| bottom_part_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_bottom_part.stl` |
| top_part_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_top_part.step` |
| top_part_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_top_part.stl` |
| assembled_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_assembled.step` |
| assembled_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_assembled.stl` |
| reference_assembly_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_reference_assembly.step` |
| reference_assembly_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_reference_assembly.stl` |
| print_layout_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_print_layout.step` |
| print_layout_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_print_layout.stl` |
| exploded_step | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_exploded.step` |
| exploded_stl | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_exploded.stl` |
| top_alignment_svg | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_top_alignment.svg` |
| top_alignment_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_top_alignment.png` |
| assembled_render_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_assembled_render.png` |
| exploded_render_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_exploded_render.png` |
| print_layout_render_png | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30_print_layout_render.png` |
| blender_scene | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30.blend` |
| manifest | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35_h60_each30/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_sample_holder_two_piece_lock_slide_petri35_h60_each30` |
| `architecture` | `60 mm assembled holder: bottom tray with tall male lock feet plus a 30 mm top frame with matching holes` |
| `outer_width_mm` | `110.0` |
| `outer_height_mm` | `70.0` |
| `bottom_tray_body_height_mm` | `8.0` |
| `top_frame_body_height_mm` | `30.0` |
| `top_frame_z_mm` | `30.0` |
| `chamber_gap_mm` | `22.0` |
| `assembled_height_mm` | `60.0` |
| `top_inner_window_mm` | `[82.0, 42.0]` |
| `usable_sample_zone_mm` | `[80.0, 40.0]` |
| `edge_fillet_mm` | `0.8` |
| `lock_nominal_diameter_mm` | `6.0` |
| `lock_foot_diameter_mm` | `5.8` |
| `lock_hole_diameter_mm` | `6.2` |
| `lock_engagement_mm` | `5.2` |
| `lock_foot_total_height_mm` | `27.2` |
| `lock_hole_depth_mm` | `6.0` |
| `bottom_print_height_mm` | `35.2` |
| `top_print_height_mm` | `30.0` |
| `lock_points_mm` | `[[-47.0, -27.0], [47.0, -27.0], [-47.0, 27.0], [47.0, 27.0]]` |
| `rod_diameter_nominal_mm` | `6.0` |
| `rod_socket_diameter_mm` | `6.4` |
| `rod_socket_depth_mm` | `6.0` |
| `m3_thread_pilot_diameter_mm` | `2.6` |
| `rod_socket_x_pitch_mm` | `60.0` |
| `rod_socket_y_pitch_mm` | `56.0` |
| `top_rod_socket_centers_mm` | `[[-30.0, 28.0], [30.0, 28.0]]` |
| `bottom_rod_socket_centers_mm` | `[[-30.0, -28.0], [30.0, -28.0]]` |
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
| `print_fit_note` | `Male lock feet are nominal -0.2 mm, matching holes are nominal +0.2 mm. Rod sockets use 6.4 mm clearance; M3 pilot/thread places use 2.6 mm.` |
| `height_note` | `The finished assembly is 60 mm tall: the top frame starts at z=30 mm and is 30 mm tall. The bottom tray body is 8 mm tall with 27.2 mm lock posts; the posts engage 5.2 mm into the top frame, so the lower printable part is 35.2 mm high. Exact 30 mm + 30 mm printed parts cannot also have an inserted foot/hole lock without overlap.` |
| `orientation_note` | `Bottom part owns the lower rod sockets and sample seats. Top part owns the upper rod sockets and the open viewing/access window.` |

## Print Notes

- Print `bottom_part` and `top_part`.
- The `assembled` files are for checking fit.
- The `reference_assembly` files include transparent rod/sample proxies and are not intended as print files.
- If the lock is too tight, lightly sand the four printed feet first; keep the holes unchanged unless necessary.
