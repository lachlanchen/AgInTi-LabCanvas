# Cage Rod Connector, 13 mm With Center Diaphragm

This is a new clean parametric connector for the 30 mm cage system rods. It is
intended to join two nominal 6 mm rods from opposite sides using the same
printed rod fit that worked well in the two-piece sample holder.

## Geometry

- Outer body: `13.0 mm` diameter x `13.0 mm` high.
- Top pocket: `6.4 mm` diameter x `5.0 mm` deep.
- Bottom pocket: `6.4 mm` diameter x `5.0 mm` deep.
- Center diaphragm: `3.0 mm` solid material between the two blind pockets.
- Actual radial wall: `3.3 mm`.

## Fit Notes

The rod pockets use `6.4 mm`, matching the current cage holder's rod socket clearance for nominal `6.0 mm` rods.
With a `13.0 mm` outer diameter, the radial wall is `3.3 mm`; a strict 2 mm wall would require an outer diameter near `10.4 mm`.

## Print Notes

Print the connector upright on either flat end. The part is symmetric. The
`assembly` files include transparent rod proxies for checking only; print the
single connector STEP/STL.

For batch printing, use the root `PRINT_THIS_*_3x3_print_grid` files. They
contain nine upright connectors on a `20.0 mm` center
pitch, with no rod proxy geometry.

## Outputs

| Output | Path |
| --- | --- |
| connector_step | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm.step` |
| connector_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm.stl` |
| assembly_step | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_assembly.step` |
| assembly_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_assembly.stl` |
| print_layout_step | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_print_layout.step` |
| print_layout_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_print_layout.stl` |
| print_grid_step | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_3x3_print_grid.step` |
| print_grid_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_3x3_print_grid.stl` |
| print_grid_3mf | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_3x3_print_grid.3mf` |
| section_svg | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_section.svg` |
| section_png | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_section.png` |
| render_png | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_render.png` |
| assembly_render_png | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm_assembly_render.png` |
| blender_scene | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/cage_rod_connector_13mm_diaphragm.blend` |
| use_this_step | `cad/designs/cage_rod_connector_13mm_diaphragm/USE_THIS_cage_rod_connector_13mm_diaphragm.step` |
| print_this_3x3_step | `cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.step` |
| print_this_3x3_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.stl` |
| print_this_3x3_3mf | `cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.3mf` |
| manifest | `cad/designs/cage_rod_connector_13mm_diaphragm/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_rod_connector_13mm_diaphragm` |
| `design_intent` | `Double-ended printed connector for nominal 6 mm cage rods, matching the 6.4 mm rod socket fit used in the current sample-holder design.` |
| `reference_fit` | `cad/designs/cage_sample_holder_two_piece_lock_slide_petri35 uses 6.4 mm blind rod sockets for nominal 6 mm rods.` |
| `outer_diameter_mm` | `13.0` |
| `total_height_mm` | `13.0` |
| `rod_nominal_diameter_mm` | `6.0` |
| `rod_socket_diameter_mm` | `6.4` |
| `top_socket_depth_mm` | `5.0` |
| `bottom_socket_depth_mm` | `5.0` |
| `center_diaphragm_thickness_mm` | `3.0` |
| `actual_radial_wall_mm` | `3.3` |
| `wall_note` | `13.0 mm OD with a 6.4 mm rod socket gives 3.3 mm radial wall. A strict 2.0 mm wall would imply 10.4 mm OD.` |
| `end_edge_chamfer_mm` | `0.35` |
| `print_orientation` | `Print upright on either flat end. Both ends are symmetric.` |
| `print_grid_rows` | `3` |
| `print_grid_cols` | `3` |
| `print_grid_pitch_mm` | `20.0` |
