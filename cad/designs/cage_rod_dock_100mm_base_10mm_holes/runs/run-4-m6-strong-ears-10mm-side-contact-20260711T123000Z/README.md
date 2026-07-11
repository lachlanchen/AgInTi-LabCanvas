# Run 4: M6 Dock With 10 mm Side-Contact Ears

This run keeps the previous 100 x 100 x 30 mm cage dock geometry, but changes
the rod sockets from the old 10 mm dock holes to `6.4 mm`
M6/6 mm rod-fit blind holes. It also replaces the previous 0.5 mm Y-style ears
with larger filled ears that touch the corner and both adjacent side edges.
Each ear overlaps the two side edges by `10.0 mm`.

## Geometry

- Base: `100.0 x 100.0 x 30.0 mm`.
- Cage centers: `x/y = +/-15 mm`.
- Rod holes: `6.4 mm` diameter, `25.0 mm` deep.
- Bottom floor under sockets: `5.0 mm`.
- Ears: `1.0 mm` thick, filled, full corner coverage.
- Side contact: `10.0 mm` along each adjacent side.
- Ear side length: `36.0 mm`; diagonal reach: `48.0 mm`; tail width: `32.0 mm`.

## Print Notes

Use the root `PRINT_THIS_*` files in this run folder. Print flat with the M6-fit
blind holes opening upward. These ears are intentionally stronger than before;
they should hold the full corner and nearby side edges better but require more
trimming force than run 3.

Validation: STEP imports as `1` solid, STL watertight
is `True`, STL components
`1`, bounds
`[228.0, 228.0, 30.0] mm`.

## Outputs

| Output | Path |
| --- | --- |
| dock_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears.step` |
| dock_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears.stl` |
| assembly_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_assembly.step` |
| assembly_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_assembly.stl` |
| print_layout_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_print_layout.step` |
| print_layout_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_print_layout.stl` |
| print_layout_3mf | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_print_layout.3mf` |
| top_view_svg | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_top_view.svg` |
| top_view_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_top_view.png` |
| render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_render.png` |
| assembly_render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_assembly_render.png` |
| use_this_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/USE_THIS_cage_rod_dock_100mm_base_m6_10mm_side_contact_ears.step` |
| print_this_step | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/PRINT_THIS_cage_rod_dock_100mm_base_m6_10mm_side_contact_ears.step` |
| print_this_stl | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/PRINT_THIS_cage_rod_dock_100mm_base_m6_10mm_side_contact_ears.stl` |
| print_this_3mf | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/PRINT_THIS_cage_rod_dock_100mm_base_m6_10mm_side_contact_ears.3mf` |
| root_render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/PRINT_THIS_cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_render.png` |
| root_assembly_render_png | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/USE_THIS_cage_rod_dock_100mm_base_m6_10mm_side_contact_ears_assembly_render.png` |
| manifest | `/home/lachlan/ProjectsLFS/AgenticApp/cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_rod_dock_100mm_base_10mm_holes/run-4-m6-strong-ears-10mm-side-contact-print-ready` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_rod_dock_100mm_base_m6_10mm_side_contact_ears` |
| `design_intent` | `100 mm cage rod dock using M6/6 mm rod-fit holes and stronger removable anti-warp ears with 10 mm contact along both adjacent side edges.` |
| `base_width_mm` | `100.0` |
| `base_height_mm` | `100.0` |
| `base_thickness_mm` | `30.0` |
| `cage_pitch_mm` | `30.0` |
| `rod_hole_centers_mm` | `[[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]]` |
| `rod_nominal_diameter_mm` | `6.0` |
| `rod_hole_diameter_mm` | `6.4` |
| `rod_hole_depth_mm` | `25.0` |
| `bottom_floor_thickness_mm` | `5.0` |
| `rod_proxy_diameter_mm` | `6.0` |
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
| `print_orientation` | `Print flat on the 100 x 100 mm base. The four M6-fit blind holes open upward.` |
| `shapr_friendly_note` | `No threads, no helix, no B-spline surfaces, and no fragile fill-recut operations.` |
