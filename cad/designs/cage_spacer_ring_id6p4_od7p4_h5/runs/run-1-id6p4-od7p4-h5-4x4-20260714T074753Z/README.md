# Run 1: ID 6.4 / OD 7.4 / H 5 Spacer Rings

This run creates sixteen independent rings in a flat 4x4 direct-print layout.

## Geometry

- Inner diameter: `6.4 mm`.
- Outer diameter: `7.4 mm`.
- Height: `5.0 mm`.
- Radial wall: `0.5 mm`.
- Grid: `4 x 4` at `12.0 mm` pitch.

The requested OD is preserved. Because wall thickness is radial,
`(7.4 - 6.4) / 2 = 0.5 mm`; a true 1 mm radial wall would have 8.4 mm OD.

## Validation

```json
{
  "single_step": {
    "valid": true,
    "solids": 1,
    "bbox_mm": [
      7.4,
      7.4,
      5.0
    ]
  },
  "single_stl": {
    "watertight": true,
    "component_count": 1,
    "bbox_mm": [
      7.4,
      7.3977,
      5.0
    ],
    "vertices": 504,
    "faces": 1008
  },
  "grid_step": {
    "valid": true,
    "solids": 16,
    "bbox_mm": [
      43.4,
      43.4,
      5.0
    ]
  },
  "grid_stl": {
    "watertight": true,
    "component_count": 16,
    "bbox_mm": [
      43.400002,
      43.397701,
      5.0
    ],
    "vertices": 8064,
    "faces": 16128
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

## Outputs

| Output | Path |
| --- | --- |
| single_step | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/artifacts/cage_spacer_ring_run1_id6p4_od7p4_h5_single.step` |
| single_stl | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/artifacts/cage_spacer_ring_run1_id6p4_od7p4_h5_single.stl` |
| grid_step | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/artifacts/cage_spacer_ring_run1_id6p4_od7p4_h5_4x4_print_grid.step` |
| grid_stl | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/artifacts/cage_spacer_ring_run1_id6p4_od7p4_h5_4x4_print_grid.stl` |
| grid_3mf | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/artifacts/cage_spacer_ring_run1_id6p4_od7p4_h5_4x4_print_grid.3mf` |
| print_this_step | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/PRINT_THIS_cage_spacer_ring_run1_id6p4_od7p4_h5_4x4_print_grid.step` |
| print_this_stl | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/PRINT_THIS_cage_spacer_ring_run1_id6p4_od7p4_h5_4x4_print_grid.stl` |
| print_this_3mf | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/PRINT_THIS_cage_spacer_ring_run1_id6p4_od7p4_h5_4x4_print_grid.3mf` |
| print_this_render | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/PRINT_THIS_cage_spacer_ring_run1_id6p4_od7p4_h5_4x4_print_grid_render.png` |
| use_this_step | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/USE_THIS_cage_spacer_ring_run1_id6p4_od7p4_h5_single.step` |
| readme | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/README.md` |
| manifest | `cad/designs/cage_spacer_ring_id6p4_od7p4_h5/runs/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_spacer_ring_id6p4_od7p4_h5/run-1-id6p4-od7p4-h5-4x4-20260714T074753Z` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_spacer_ring_run1_id6p4_od7p4_h5` |
| `design_intent` | `Thin cage-element spacer ring following the explicit 6.4 mm ID and 7.4 mm OD request.` |
| `inner_diameter_mm` | `6.4` |
| `outer_diameter_mm` | `7.4` |
| `height_mm` | `5.0` |
| `diametral_wall_difference_mm` | `1.0` |
| `radial_wall_thickness_mm` | `0.5` |
| `true_1mm_radial_wall_outer_diameter_mm` | `8.4` |
| `print_grid_rows` | `4` |
| `print_grid_cols` | `4` |
| `print_grid_pitch_mm` | `12.0` |
| `print_orientation` | `Flat on either annular end face; sixteen independent rings with no raft or connector.` |
