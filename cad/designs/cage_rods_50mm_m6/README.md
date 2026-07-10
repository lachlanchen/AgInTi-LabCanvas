# Cage Rods, 50 mm M6 / 6 mm Diameter

This is a new clean parametric rod set for the 30 mm cage geometry. The rods are
`50.0 mm` long and `6.0 mm` diameter, matching
the 6 mm rod pockets used in the current cage holders and dock.

## Geometry

- Rod diameter: `6.0 mm`.
- Rod length: `50.0 mm`.
- Cage placement: four rods at `x/y = ±15.0 mm`.
- Optional M3 pilot variant: `2.6 mm` diameter pilot,
  `8.0 mm` deep from each end.
- Direct print grid: `5 x 5` smooth rods,
  printed horizontally with `8.0 mm` X gap and
  `12.0 mm` Y pitch.

## Shapr3D Import Notes

The direct-use STEP is a smooth rod with analytic cylinder and chamfer faces.
There are no helical threads, no fragile boolean thread cutters, and no B-spline
surfaces. If you need true M6 threads, use a bought metal M6 threaded rod or add
native threads in Shapr3D after import.

## Print Notes

Use the root `PRINT_THIS_*_25rod_print_grid` files for direct slicing. The rods
are already laid flat with their axes along X. The 3MF file is generated from
the validated STL as a slicer-friendly handoff; the STEP remains the editable
geometry source.

## Outputs

| Output | Path |
| --- | --- |
| smooth_rod_step | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_smooth_rod.step` |
| smooth_rod_stl | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_smooth_rod.stl` |
| m3_pilot_rod_step | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_m3_pilot_rod.step` |
| m3_pilot_rod_stl | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_m3_pilot_rod.stl` |
| assembly_step | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_four_rod_cage_assembly.step` |
| assembly_stl | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_four_rod_cage_assembly.stl` |
| print_layout_step | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_four_rod_print_layout.step` |
| print_layout_stl | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_four_rod_print_layout.stl` |
| print_grid_step | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_25rod_print_grid.step` |
| print_grid_stl | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_25rod_print_grid.stl` |
| print_grid_3mf | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_25rod_print_grid.3mf` |
| diagram_svg | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_diagram.svg` |
| diagram_png | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_diagram.png` |
| render_png | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_render.png` |
| assembly_render_png | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_assembly_render.png` |
| blender_scene | `cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6.blend` |
| use_this_smooth_rod_step | `cad/designs/cage_rods_50mm_m6/USE_THIS_cage_rods_50mm_m6_smooth_rod.step` |
| use_this_four_rod_assembly_step | `cad/designs/cage_rods_50mm_m6/USE_THIS_cage_rods_50mm_m6_four_rod_cage_assembly.step` |
| print_this_25rod_step | `cad/designs/cage_rods_50mm_m6/PRINT_THIS_cage_rods_50mm_m6_25rod_print_grid.step` |
| print_this_25rod_stl | `cad/designs/cage_rods_50mm_m6/PRINT_THIS_cage_rods_50mm_m6_25rod_print_grid.stl` |
| print_this_25rod_3mf | `cad/designs/cage_rods_50mm_m6/PRINT_THIS_cage_rods_50mm_m6_25rod_print_grid.3mf` |
| manifest | `cad/designs/cage_rods_50mm_m6/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_rods_50mm_m6` |
| `design_intent` | `Simple 50 mm long, 6 mm diameter cage rods for the standard 30 mm cage square.` |
| `rod_length_mm` | `50.0` |
| `rod_diameter_mm` | `6.0` |
| `rod_radius_mm` | `3.0` |
| `cage_pitch_mm` | `30.0` |
| `rod_centers_mm` | `[[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]]` |
| `m3_pilot_diameter_mm` | `2.6` |
| `m3_pilot_depth_each_end_mm` | `8.0` |
| `end_chamfer_mm` | `0.35` |
| `print_spacing_mm` | `12.0` |
| `print_grid_rows` | `5` |
| `print_grid_cols` | `5` |
| `print_grid_x_gap_mm` | `8.0` |
| `print_grid_y_pitch_mm` | `12.0` |
| `shapr_friendly_note` | `No helical threads or B-spline faces. The M6 wording here is treated as a 6 mm cage rod diameter. Use real metal M6 threaded rod if a true screw thread is required.` |
