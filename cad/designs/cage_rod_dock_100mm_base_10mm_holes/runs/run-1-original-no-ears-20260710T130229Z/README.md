# Cage Rod Dock, 100 mm Base With 10 mm Holes

This is a clean parametric dock for the cage-system rods. It follows the
standard 30 mm cage square, with four vertical blind holes centered at `x/y =
±15 mm`.

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

## Outputs

| Output | Path |
| --- | --- |
| dock_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes.step` |
| dock_stl | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes.stl` |
| assembly_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_assembly.step` |
| assembly_stl | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_assembly.stl` |
| print_layout_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_print_layout.step` |
| print_layout_stl | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_print_layout.stl` |
| top_view_svg | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_top_view.svg` |
| top_view_png | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_top_view.png` |
| render_png | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_render.png` |
| assembly_render_png | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes_assembly_render.png` |
| blender_scene | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/artifacts/cage_rod_dock_100mm_base_10mm_holes.blend` |
| use_this_step | `cad/designs/cage_rod_dock_100mm_base_10mm_holes/USE_THIS_cage_rod_dock_100mm_base_10mm_holes.step` |
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
| `shapr_friendly_note` | `No threads, no helix, no B-spline surfaces, and no fragile fill-recut operations. Geometry is a simple box minus four vertical cylinders with small chamfers.` |
| `print_orientation` | `Print flat on the 100 x 100 mm base. The four 10 mm blind holes open upward.` |
