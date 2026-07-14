# Run 3: 6.30 mm Rods With M3 Pilot Holes

This run increases the rod body to `6.30 mm` diameter while keeping the
`50.0 mm` length and blind pilot holes at both ends.

## Geometry

- Rod diameter: `6.3 mm`.
- Rod length: `50.0 mm`.
- Pilot hole: `2.8 mm` diameter.
- Pilot depth: `6.0 mm` from each end.
- Print grid: `3 x 3` upright rods.

The hole is a clean cylindrical pilot for an M3 screw/tap/self-tapping screw.
No helical thread is modeled, so STEP import should stay fast and editable.

## Outputs

| Output | Path |
| --- | --- |
| single_step | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/artifacts/cage_rods_run3_6p3mm_m3_pilot_both_ends_single.step` |
| single_stl | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/artifacts/cage_rods_run3_6p3mm_m3_pilot_both_ends_single.stl` |
| grid_step | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/artifacts/cage_rods_run3_6p3mm_m3_pilot_both_ends_vertical_3x3_print_grid.step` |
| grid_stl | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/artifacts/cage_rods_run3_6p3mm_m3_pilot_both_ends_vertical_3x3_print_grid.stl` |
| grid_3mf | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/artifacts/cage_rods_run3_6p3mm_m3_pilot_both_ends_vertical_3x3_print_grid.3mf` |
| print_this_step | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/PRINT_THIS_cage_rods_run3_6p3mm_m3_pilot_both_ends_vertical_3x3_print_grid.step` |
| print_this_stl | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/PRINT_THIS_cage_rods_run3_6p3mm_m3_pilot_both_ends_vertical_3x3_print_grid.stl` |
| print_this_3mf | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/PRINT_THIS_cage_rods_run3_6p3mm_m3_pilot_both_ends_vertical_3x3_print_grid.3mf` |
| print_this_render | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/PRINT_THIS_cage_rods_run3_6p3mm_m3_pilot_both_ends_vertical_3x3_print_grid_render.png` |
| use_this_step | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/USE_THIS_cage_rods_run3_6p3mm_m3_pilot_both_ends_single.step` |
| readme | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/README.md` |
| manifest | `cad/designs/cage_rods_50mm_m6/runs/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_rods_50mm_m6/run-3-6p3mm-m3-pilot-both-ends-vertical-3x3-20260714T074753Z` |

## Validation

```json
{
  "single_step": {
    "valid": true,
    "solids": 1,
    "bbox_mm": [
      6.3,
      6.3,
      50.0
    ]
  },
  "single_stl": {
    "watertight": true,
    "component_count": 1,
    "bbox_mm": [
      6.3,
      6.298042,
      50.0
    ],
    "vertices": 1386,
    "faces": 2768
  },
  "grid_step": {
    "valid": true,
    "solids": 9,
    "bbox_mm": [
      38.3,
      38.3,
      50.0
    ]
  },
  "grid_stl": {
    "watertight": true,
    "component_count": 9,
    "bbox_mm": [
      38.299999,
      38.298042,
      50.0
    ],
    "vertices": 12474,
    "faces": 24912
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
| `name` | `cage_rods_run3_6p3mm_m3_pilot_both_ends` |
| `design_intent` | `6.30 mm cage rods with 2.8 mm x 6 mm M3 pilot/thread holes on both ends.` |
| `rod_diameter_mm` | `6.3` |
| `rod_length_mm` | `50.0` |
| `m3_pilot_hole_diameter_mm` | `2.8` |
| `m3_pilot_hole_depth_each_end_mm` | `6.0` |
| `end_chamfer_mm` | `0.18` |
| `print_grid_rows` | `3` |
| `print_grid_cols` | `3` |
| `print_grid_pitch_mm` | `16.0` |
| `print_orientation` | `Vertical/upright rods on the 6.30 mm circular end face.` |
| `thread_note` | `The 2.8 mm hole is a blind pilot for an M3 screw/tap/self-tapping screw; no helical thread is modeled.` |
