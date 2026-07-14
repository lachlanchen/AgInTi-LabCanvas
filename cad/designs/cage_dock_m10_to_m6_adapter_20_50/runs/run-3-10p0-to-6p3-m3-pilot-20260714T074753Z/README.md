# Run 3: Exact 10.00 mm To 6.30 mm Adapter

This run preserves the successful upright 2x2 adapter layout while changing
only the upper post from 6.00 mm to 6.30 mm. The lower insert remains exactly
10.00 mm. A blind M3 pilot/tap hole remains in the upper end.

## Geometry

- Lower insert: `10.0 mm` diameter x `20.0 mm`.
- Upper rod: `6.3 mm` diameter x `50.0 mm`.
- Pilot hole in M6 end: `2.8 mm` diameter x `6.0 mm` deep.
- Direct print grid: `2 x 2` upright adapters.

The M10 and M6 names are smooth diameter classes here. The 6.30 mm upper post
is intentional fit compensation. The small hole is not a
modeled helical thread; it is a cylindrical pilot for an M3 screw/tap/self-
tapping screw.

## Outputs

| Output | Path |
| --- | --- |
| single_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/artifacts/cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_single.step` |
| single_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/artifacts/cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_single.stl` |
| grid_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/artifacts/cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_2x2_print_grid.step` |
| grid_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/artifacts/cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_2x2_print_grid.stl` |
| grid_3mf | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/artifacts/cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_2x2_print_grid.3mf` |
| print_this_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/PRINT_THIS_cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_2x2_print_grid.step` |
| print_this_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/PRINT_THIS_cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_2x2_print_grid.stl` |
| print_this_3mf | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/PRINT_THIS_cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_2x2_print_grid.3mf` |
| print_this_render | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/PRINT_THIS_cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_2x2_print_grid_render.png` |
| use_this_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/USE_THIS_cage_dock_adapter_run3_10p0_to_6p3_m3_pilot_single.step` |
| readme | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/README.md` |
| manifest | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_dock_m10_to_m6_adapter_20_50/run-3-10p0-to-6p3-m3-pilot-20260714T074753Z` |

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
    "vertices": 1197,
    "faces": 2390
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
    "vertices": 4788,
    "faces": 9560
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
| `name` | `cage_dock_adapter_run3_10p0_to_6p3_m3_pilot` |
| `design_intent` | `Smooth dock adapter with an exact 10.00 mm lower insert, 6.30 mm upper post, and a 2.8 mm x 6 mm M3 pilot in the upper end.` |
| `dock_hole_reference_diameter_mm` | `10.0` |
| `lower_insert_diameter_mm` | `10.0` |
| `lower_insert_length_mm` | `20.0` |
| `upper_rod_diameter_mm` | `6.3` |
| `upper_rod_length_mm` | `50.0` |
| `total_height_mm` | `70.0` |
| `m3_pilot_hole_diameter_mm` | `2.8` |
| `m3_pilot_hole_depth_from_top_mm` | `6.0` |
| `lead_in_chamfer_mm` | `0.25` |
| `top_chamfer_mm` | `0.18` |
| `print_grid_rows` | `2` |
| `print_grid_cols` | `2` |
| `print_grid_pitch_mm` | `25.0` |
| `thread_note` | `M10/M6 are smooth diameter classes. The upper post is intentionally 6.30 mm. The 2.8 mm feature is a blind M3 pilot/tap hole, not a modeled helical thread.` |
