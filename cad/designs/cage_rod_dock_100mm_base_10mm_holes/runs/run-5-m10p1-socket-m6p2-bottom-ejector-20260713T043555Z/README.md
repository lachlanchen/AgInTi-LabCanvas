# Run 5: M10.1 Socket With M6.2 Bottom Ejector

This run preserves run 4's 100 mm square body, 30 mm cage-center geometry,
edge chamfers, and strong 1 mm anti-warp ears with 10 mm contact along both
adjacent sides. Only the plate thickness and four coaxial hole profiles change.

## Geometry

- Base: `100 x 100 x 25 mm`.
- Socket centers: `x/y = +/-15 mm`, unchanged from run 4.
- Top sockets: `10.1 mm` diameter and `20.0 mm` deep.
- Bottom ejector passages: `6.2 mm` diameter through the remaining `5.0 mm`.
- Internal shoulder: annulus from radius `3.1 mm` to `5.05 mm` at `z = 5 mm`.
- Ears: unchanged run-4 filled full-corner design, `1.0 mm` thick with
  `10.0 mm` contact along both adjoining edges.

The bottom passage is not another mounting socket. It is an ejector access hole:
insert a 6 mm steel rod from below and tap it to push a tight M10 adapter upward.

## Print Notes

Use the root `PRINT_THIS_*` file in this run folder. Print the dock flat with the
M10.1 sockets facing upward. The M6.2 openings will be on the build plate; clear
any first-layer elephant-foot or bridging residue before using the ejector rod.

Validation: STEP imports as `1` solid; STL watertight
is `True` with
`1` component and bounds
`[228.0, 228.0, 25.0] mm`.

## Outputs

| Output | Path |
| --- | --- |
| dock_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector.step` |
| dock_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector.stl` |
| assembly_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_assembly.step` |
| assembly_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_assembly.stl` |
| print_layout_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_print_layout.step` |
| print_layout_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_print_layout.stl` |
| print_layout_3mf | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_print_layout.3mf` |
| top_view_svg | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_top_view.svg` |
| top_view_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_top_view.png` |
| render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_render.png` |
| assembly_render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_assembly_render.png` |
| use_this_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/USE_THIS_cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector.step` |
| print_this_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/PRINT_THIS_cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector.step` |
| print_this_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/PRINT_THIS_cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector.stl` |
| print_this_3mf | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/PRINT_THIS_cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector.3mf` |
| root_render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/PRINT_THIS_cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_render.png` |
| root_assembly_render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/USE_THIS_cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_assembly_render.png` |
| manifest | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_rod_dock_100mm_base_10mm_holes/run-5-m10p1-socket-m6p2-bottom-ejector-print-ready` |
| bottom_ejector_render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-5-m10p1-socket-m6p2-bottom-ejector-20260713T043555Z/artifacts/cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector_bottom_ejector_render.png` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_rod_dock_100mm_base_m10p1_socket_m6p2_bottom_ejector` |
| `design_intent` | `Preserve run-4 cage geometry and strong ears while changing the dock to a 25 mm plate with four top M10.1 sockets and coaxial M6.2 bottom ejector holes.` |
| `base_width_mm` | `100.0` |
| `base_height_mm` | `100.0` |
| `base_thickness_mm` | `25.0` |
| `cage_pitch_mm` | `30.0` |
| `rod_hole_centers_mm` | `[[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]]` |
| `rod_nominal_diameter_mm` | `6.0` |
| `rod_hole_diameter_mm` | `10.1` |
| `rod_hole_depth_mm` | `20.0` |
| `bottom_floor_thickness_mm` | `5.0` |
| `rod_proxy_diameter_mm` | `10.0` |
| `rod_proxy_visible_height_mm` | `72.0` |
| `edge_chamfer_mm` | `1.0` |
| `hole_mouth_chamfer_mm` | `0.35` |
| `anti_warp_ear_style` | `four filled full-corner ears with 10 mm side contact strips on both adjacent sides` |
| `anti_warp_ear_thickness_mm` | `1.0` |
| `anti_warp_ear_breakaway_overlap_mm` | `1.0` |
| `anti_warp_ear_side_contact_length_mm` | `10.0` |
| `anti_warp_ear_side_length_mm` | `36.0` |
| `anti_warp_ear_side_width_mm` | `18.0` |
| `anti_warp_ear_diagonal_reach_mm` | `48.0` |
| `anti_warp_ear_tail_width_mm` | `32.0` |
| `anti_warp_ear_note` | `Each corner is one filled polygon. It overlaps the dock at the true corner and along two 10 mm side-edge strips, then pulls outward along both side directions and the diagonal direction.` |
| `print_orientation` | `Print flat on the 100 x 100 mm base with the four 10.1 mm sockets opening upward; the four 6.2 mm ejector passages open against the build plate.` |
| `shapr_friendly_note` | `No threads, no helix, no B-spline surfaces, and no fragile fill-recut operations.` |
| `top_socket_nominal_diameter_mm` | `10.0` |
| `top_socket_diameter_mm` | `10.1` |
| `top_socket_depth_mm` | `20.0` |
| `bottom_ejector_nominal_diameter_mm` | `6.0` |
| `bottom_ejector_diameter_mm` | `6.2` |
| `bottom_ejector_depth_mm` | `5.0` |
| `socket_shoulder_z_mm` | `5.0` |
| `ejector_function` | `Insert a 6 mm metal push rod from the underside through the 6.2 mm passage to drive a tight M10 adapter out of the top socket.` |
