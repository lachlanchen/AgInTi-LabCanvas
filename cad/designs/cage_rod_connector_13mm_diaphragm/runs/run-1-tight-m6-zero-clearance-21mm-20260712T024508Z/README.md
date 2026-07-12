# Run 1: Tight M6 Zero-Clearance 21 mm Connector

This run replaces the loose connector fit. The old connector used a `6.4 mm`
socket for a nominal `6.0 mm` rod. This run uses a `6.0 mm` socket, so the
diameter clearance is `0.0 mm`.

## Direct Print

Use the root `PRINT_THIS_*` files in this run folder. They contain a 3x3 grid
of nine upright connectors and no rod proxy geometry.

## Geometry

- Outer diameter: `8.0 mm`.
- Total height: `21.0 mm`.
- Top socket: `6.0 mm` diameter x `10.0 mm` deep.
- Bottom socket: `6.0 mm` diameter x `10.0 mm` deep.
- Center diaphragm: `1.0 mm`.
- Radial wall: `1.0 mm`.

## Fit Note

This is intentionally very tight. If the printed rod cannot enter, lightly sand
or drill the socket instead of changing the model first.

## Outputs

| Output | Path |
| --- | --- |
| single_step | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_single.step` |
| single_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_single.stl` |
| assembly_step | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_assembly.step` |
| assembly_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_assembly.stl` |
| print_grid_step | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.step` |
| print_grid_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.stl` |
| print_grid_3mf | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.3mf` |
| section_svg | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_section.svg` |
| section_png | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/cage_rod_connector_run1_tight_m6_zero_clearance_21mm_section.png` |
| print_this_step | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/PRINT_THIS_cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.step` |
| print_this_stl | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/PRINT_THIS_cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.stl` |
| print_this_3mf | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/PRINT_THIS_cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.3mf` |
| print_this_render | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/PRINT_THIS_cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid_render.png` |
| use_this_step | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/USE_THIS_cage_rod_connector_run1_tight_m6_zero_clearance_21mm_single.step` |
| readme | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/README.md` |
| manifest | `cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_rod_connector_13mm_diaphragm/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z` |

## Validation

```json
{
  "single_step": {
    "valid": true,
    "solids": 1,
    "bbox_mm": [
      8.0,
      8.0,
      21.0
    ]
  },
  "single_stl": {
    "watertight": true,
    "component_count": 1,
    "bbox_mm": [
      8.0,
      7.997513,
      21.0
    ],
    "vertices": 1260,
    "faces": 2516
  },
  "print_grid_step": {
    "valid": true,
    "solids": 9,
    "bbox_mm": [
      40.0,
      40.0,
      21.0
    ]
  },
  "print_grid_stl": {
    "watertight": true,
    "component_count": 9,
    "bbox_mm": [
      40.0,
      39.997513,
      21.0
    ],
    "vertices": 11340,
    "faces": 22644
  },
  "print_grid_3mf": {
    "entries": [
      "3D/3dmodel.model",
      "[Content_Types].xml",
      "_rels/.rels"
    ],
    "has_model": true
  }
}
```

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_rod_connector_run1_tight_m6_zero_clearance_21mm` |
| `design_intent` | `Tighter replacement for the loose 13 mm connector. Uses exact nominal M6/6.0 mm rod sockets with zero extra diameter clearance.` |
| `outer_diameter_mm` | `8.0` |
| `total_height_mm` | `21.0` |
| `rod_nominal_diameter_mm` | `6.0` |
| `rod_socket_diameter_mm` | `6.0` |
| `top_socket_depth_mm` | `10.0` |
| `bottom_socket_depth_mm` | `10.0` |
| `center_diaphragm_thickness_mm` | `1.0` |
| `radial_wall_thickness_mm` | `1.0` |
| `diameter_clearance_mm` | `0.0` |
| `fit_note` | `Previous connector used 6.4 mm sockets for 6 mm rods and was too loose. This run removes that 0.4 mm diameter clearance.` |
| `end_edge_chamfer_mm` | `0.18` |
| `print_orientation` | `Print upright on either flat end. Both ends are symmetric.` |
| `print_grid_rows` | `3` |
| `print_grid_cols` | `3` |
| `print_grid_pitch_mm` | `16.0` |
