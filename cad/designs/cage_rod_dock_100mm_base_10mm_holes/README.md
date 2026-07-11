# Cage Rod Dock, 100 mm Base With 10 mm Holes

This is a clean parametric dock for the cage-system rods. It follows the
standard 30 mm cage square, with four vertical blind holes centered at `x/y =
±15 mm`.

## Latest M6 Print Run

Use
`runs/run-4-m6-strong-ears-10mm-side-contact-20260711T123000Z/PRINT_THIS_cage_rod_dock_100mm_base_m6_10mm_side_contact_ears.*`
for the corrected M6 dock. That run keeps the same `100 x 100 x 30 mm` dock and
30 mm cage square, changes the blind rod sockets to `6.4 mm` diameter for 6 mm
rods, and uses stronger filled anti-warp ears. The ears are `1.0 mm` thick and
now touch the true corner plus `10 mm` along each of the two adjacent side
edges, then pull outward in both side directions and along the corner diagonal.

The print-ready copy is synced to:

`/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_rod_dock_100mm_base_10mm_holes/run-4-m6-strong-ears-10mm-side-contact-print-ready/`

## Geometry

- Base: `100.0 x 100.0 x 30.0 mm`.
- Rod dock holes: `10.0 mm` diameter.
- Hole depth: `25.0 mm`, leaving `5.0 mm` floor.
- Cage geometry: `30.0 mm` square, hole centers at `±15.0 mm`.

## Shapr3D Import Notes

This design deliberately avoids threads, helixes, fragile cutter fragments,
and B-spline surfaces. The final STEP is a simple block with four vertical
cylindrical blind holes and small exterior chamfers, so it should import into
Shapr3D without a long repair pass.

## Print Notes

Print flat on the 100 x 100 mm base. The holes open upward. The assembly files
include blue 6 mm rod proxies only for checking placement.

The latest root output includes four removable anti-warp ears on the bottom
face. Each corner has two side pulls plus one diagonal full-corner pull, so a
large flat print is held down from the actual corner direction as well as along
the two edges. Trim the ears away after printing.

Use the root `PRINT_THIS_*` STEP/STL/3MF files for direct printing. Those files
contain only the dock body with anti-warp ears. Rod proxies stay in the assembly
artifacts for geometry checking and are intentionally excluded from the direct
print layout.

The previous no-ear version is archived under
`cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-1-original-no-ears-20260710T130229Z/`.

## Outputs

| Output | Path |
| --- | --- |
| dock_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes.step` |
| dock_stl | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes.stl` |
| assembly_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_assembly.step` |
| assembly_stl | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_assembly.stl` |
| print_layout_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_print_layout.step` |
| print_layout_stl | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_print_layout.stl` |
| print_layout_3mf | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_print_layout.3mf` |
| top_view_svg | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_top_view.svg` |
| top_view_png | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_top_view.png` |
| render_png | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_render.png` |
| assembly_render_png | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_assembly_render.png` |
| blender_scene | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes.blend` |
| use_this_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/USE_THIS_cage_rod_dock_100mm_base_10mm_holes.step` |
| print_this_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/PRINT_THIS_cage_rod_dock_100mm_base_10mm_holes_with_ears.step` |
| print_this_stl | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/PRINT_THIS_cage_rod_dock_100mm_base_10mm_holes_with_ears.stl` |
| print_this_3mf | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/PRINT_THIS_cage_rod_dock_100mm_base_10mm_holes_with_ears.3mf` |
| manifest | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_rod_dock_100mm_base_10mm_holes` |
| `design_intent` | `Simple Shapr3D-friendly dock block for cage rods, using the standard 30 mm cage square geometry.` |
| `base_width_mm` | `100.0` |
| `base_height_mm` | `100.0` |
| `base_thickness_mm` | `30.0` |
| `cage_pitch_mm` | `30.0` |
| `rod_hole_centers_mm` | `[[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]]` |
| `rod_hole_diameter_mm` | `10.0` |
| `rod_hole_depth_mm` | `25.0` |
| `bottom_floor_thickness_mm` | `5.0` |
| `rod_proxy_diameter_mm` | `6.0` |
| `rod_proxy_visible_height_mm` | `72.0` |
| `edge_chamfer_mm` | `1.0` |
| `hole_mouth_chamfer_mm` | `0.5` |
| `anti_warp_ears_enabled` | `True` |
| `anti_warp_ear_style` | `four removable 0.5 mm bottom ears with two side pulls plus one diagonal full-corner pull` |
| `anti_warp_ear_thickness_mm` | `0.5` |
| `anti_warp_ear_breakaway_overlap_mm` | `0.35` |
| `anti_warp_ear_side_contact_width_mm` | `4.5` |
| `anti_warp_ear_arm_width_mm` | `4.0` |
| `anti_warp_ear_junction_offset_mm` | `9.0` |
| `anti_warp_ear_tail_reach_mm` | `24.0` |
| `anti_warp_ear_tail_width_mm` | `16.0` |
| `anti_warp_ear_diagonal_neck_width_mm` | `5.0` |
| `anti_warp_ear_note` | `Run-2 adds full-corner anti-warp ears for the broad 100 x 100 mm flat base. Each corner has side pulls plus a diagonal pull so the actual corner is dragged down toward the build plate.` |
| `shapr_friendly_note` | `No threads, no helix, no B-spline surfaces, and no fragile fill-recut operations. Geometry is a simple box minus four vertical cylinders plus simple 0.5 mm anti-warp tabs.` |
| `print_orientation` | `Print flat on the 100 x 100 mm base. The four 10 mm blind holes open upward.` |
