# Run 1: Exact M10 To M6 Adapter

This is the exact zero-clearance smooth adapter. The old adapter used a
`9.8 mm` lower insert for the `10.0 mm` dock hole and fit well. This run uses
`10.0 mm` lower insert and `6.0 mm` upper rod exactly.

## Geometry

- Lower insert: `10.0 mm` diameter x `20.0 mm`.
- Upper rod: `6.0 mm` diameter x `50.0 mm`.
- Total height: `70.0 mm`.
- Diameter clearance: `0.0 mm`.

## Direct Print

Use the root `PRINT_THIS_*` files. They contain a 2x2 upright adapter grid.

## Outputs

| Output | Path |
| --- | --- |
| single_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_single.step` |
| single_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_single.stl` |
| grid_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.step` |
| grid_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.stl` |
| grid_3mf | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.3mf` |
| section_svg | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_section.svg` |
| section_png | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_section.png` |
| print_this_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/PRINT_THIS_cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.step` |
| print_this_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/PRINT_THIS_cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.stl` |
| print_this_3mf | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/PRINT_THIS_cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.3mf` |
| print_this_render | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/PRINT_THIS_cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid_render.png` |
| use_this_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/USE_THIS_cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_single.step` |
| readme | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/README.md` |
| manifest | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_dock_m10_to_m6_adapter_20_50/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z` |

## Validation

```json
{
  "single_step": {
    "valid": true,
    "solids": 1,
    "bbox_mm": [
      10.0,
      10.0,
      70.0
    ]
  },
  "single_stl": {
    "watertight": true,
    "component_count": 1,
    "bbox_mm": [
      10.0,
      9.996892,
      70.0
    ],
    "vertices": 819,
    "faces": 1634
  },
  "grid_step": {
    "valid": true,
    "solids": 4,
    "bbox_mm": [
      35.0,
      35.0,
      70.0
    ]
  },
  "grid_stl": {
    "watertight": true,
    "component_count": 4,
    "bbox_mm": [
      35.0,
      34.996891,
      70.0
    ],
    "vertices": 3276,
    "faces": 6536
  },
  "grid_3mf": {
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
| `name` | `cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance` |
| `design_intent` | `Exact smooth-diameter adapter: M10-class 10.0 mm lower insert to M6-class 6.0 mm upper rod.` |
| `dock_hole_reference_diameter_mm` | `10.0` |
| `lower_insert_diameter_mm` | `10.0` |
| `lower_insert_length_mm` | `20.0` |
| `upper_rod_diameter_mm` | `6.0` |
| `upper_rod_length_mm` | `50.0` |
| `total_height_mm` | `70.0` |
| `diameter_clearance_mm` | `0.0` |
| `previous_insert_diameter_mm` | `9.8` |
| `previous_clearance_mm` | `0.2` |
| `lead_in_chamfer_mm` | `0.25` |
| `top_chamfer_mm` | `0.25` |
| `print_grid_rows` | `2` |
| `print_grid_cols` | `2` |
| `print_grid_pitch_mm` | `25.0` |
| `fit_note` | `M10/M6 mean smooth exact diameters in this model, not modeled screw threads.` |
