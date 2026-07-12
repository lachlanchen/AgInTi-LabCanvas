# Run 1: Exact 6 mm Vertical 3x3 Rod Grid

This run provides exact smooth rods for the tight M6 connector. The previous
rod model was already `6.0 mm` diameter, but the direct print grid was a
horizontal 5x5 layout. This run is a vertical 3x3 layout only.

## Direct Print

Use the root `PRINT_THIS_*` files in this run folder. They contain nine upright
rods and no horizontal rods.

## Geometry

- Rod diameter: `6.0 mm`.
- Rod length: `50.0 mm`.
- Diameter clearance: `0.0 mm`.
- Grid: `3 x 3`.
- Grid pitch: `16.0 mm`.
- End chamfer: `0.18 mm`.

## Print Note

The rods stand on a 6 mm circular end face. This keeps the geometry exact. If
the printer bed adhesion is weak, add a slicer brim instead of changing the CAD
diameter.

## Outputs

| Output | Path |
| --- | --- |
| single_step | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/cage_rods_run1_exact_6mm_vertical_3x3_single.step` |
| single_stl | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/cage_rods_run1_exact_6mm_vertical_3x3_single.stl` |
| print_grid_step | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.step` |
| print_grid_stl | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.stl` |
| print_grid_3mf | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.3mf` |
| diagram_svg | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/cage_rods_run1_exact_6mm_vertical_3x3_diagram.svg` |
| diagram_png | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/cage_rods_run1_exact_6mm_vertical_3x3_diagram.png` |
| print_this_step | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/PRINT_THIS_cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.step` |
| print_this_stl | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/PRINT_THIS_cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.stl` |
| print_this_3mf | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/PRINT_THIS_cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.3mf` |
| print_this_render | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/PRINT_THIS_cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid_render.png` |
| use_this_step | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/USE_THIS_cage_rods_run1_exact_6mm_vertical_3x3_single.step` |
| readme | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/README.md` |
| manifest | `cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_rods_50mm_m6/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z` |

## Validation

```json
{
  "single_step": {
    "valid": true,
    "solids": 1,
    "bbox_mm": [
      6.0,
      6.0,
      50.0
    ]
  },
  "single_stl": {
    "watertight": true,
    "component_count": 1,
    "bbox_mm": [
      6.0,
      5.998135,
      50.0
    ],
    "vertices": 504,
    "faces": 1004
  },
  "print_grid_step": {
    "valid": true,
    "solids": 9,
    "bbox_mm": [
      38.0,
      38.0,
      50.0
    ]
  },
  "print_grid_stl": {
    "watertight": true,
    "component_count": 9,
    "bbox_mm": [
      38.0,
      37.998135,
      50.0
    ],
    "vertices": 4536,
    "faces": 9036
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
| `name` | `cage_rods_run1_exact_6mm_vertical_3x3` |
| `design_intent` | `Exact 6.0 mm smooth rods for the tight M6 connector, printed upright in a 3x3 grid.` |
| `rod_diameter_mm` | `6.0` |
| `rod_radius_mm` | `3.0` |
| `rod_length_mm` | `50.0` |
| `diameter_clearance_mm` | `0.0` |
| `end_chamfer_mm` | `0.18` |
| `print_grid_rows` | `3` |
| `print_grid_cols` | `3` |
| `print_grid_pitch_mm` | `16.0` |
| `print_orientation` | `Vertical/upright. Each rod stands on its circular 6 mm end face.` |
| `print_note` | `No horizontal rods and no auxiliary brim geometry. If bed adhesion is weak, add slicer brim rather than changing the rod diameter.` |
