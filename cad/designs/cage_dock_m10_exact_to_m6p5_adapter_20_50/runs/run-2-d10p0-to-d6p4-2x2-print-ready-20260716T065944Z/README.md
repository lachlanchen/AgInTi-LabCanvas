# cage_dock_m10_exact_to_m6p4_adapter_20_50

This run contains one direct-print job: four independent smooth stepped adapters
in a 2x2 upright layout.

## Dimensions

- Lower insert: `10.0 mm` diameter x `20.0 mm`
- Upper shaft: `6.4 mm` diameter x `50.0 mm`
- Total height: `70.0 mm`
- Added fit compensation: `0.0 mm`
- Threading: none
- M3 pilot: none

`M10` and `M6` are descriptive smooth-diameter classes here. Use the files
prefixed `PRINT_THIS_`; enable a slicer brim if the upright parts need more bed
adhesion.

## Outputs

```json
{
  "adapter_grid_print_step": "cad/designs/cage_dock_m10_exact_to_m6p5_adapter_20_50/runs/run-2-d10p0-to-d6p4-2x2-print-ready-20260716T065944Z/PRINT_THIS_cage_dock_m10_exact_to_m6p4_adapter_20_50_2x2_print_grid.step",
  "adapter_grid_print_stl": "cad/designs/cage_dock_m10_exact_to_m6p5_adapter_20_50/runs/run-2-d10p0-to-d6p4-2x2-print-ready-20260716T065944Z/PRINT_THIS_cage_dock_m10_exact_to_m6p4_adapter_20_50_2x2_print_grid.stl",
  "adapter_grid_print_3mf": "cad/designs/cage_dock_m10_exact_to_m6p5_adapter_20_50/runs/run-2-d10p0-to-d6p4-2x2-print-ready-20260716T065944Z/PRINT_THIS_cage_dock_m10_exact_to_m6p4_adapter_20_50_2x2_print_grid.3mf",
  "adapter_grid_render": "cad/designs/cage_dock_m10_exact_to_m6p5_adapter_20_50/runs/run-2-d10p0-to-d6p4-2x2-print-ready-20260716T065944Z/PRINT_THIS_cage_dock_m10_exact_to_m6p4_adapter_20_50_2x2_print_grid_render.png",
  "single_editable_step": "cad/designs/cage_dock_m10_exact_to_m6p5_adapter_20_50/runs/run-2-d10p0-to-d6p4-2x2-print-ready-20260716T065944Z/USE_THIS_cage_dock_m10_exact_to_m6p4_adapter_20_50_single.step",
  "single_render": "cad/designs/cage_dock_m10_exact_to_m6p5_adapter_20_50/runs/run-2-d10p0-to-d6p4-2x2-print-ready-20260716T065944Z/USE_THIS_cage_dock_m10_exact_to_m6p4_adapter_20_50_single_render.png"
}
```

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
    ],
    "bspline_faces": 0
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
    ],
    "bspline_faces": 0
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
    "has_model": true,
    "model_bytes": 516851
  }
}
```
