# cage_spacer_id6p5_od10p5

This run contains two independent print jobs. Print the 4x4 short-ring file first,
then print the single 50 mm tube as a separate job.

## Dimensions

- ID: `6.5 mm`
- OD: `10.5 mm`
- Radial wall: `2.0 mm`
- Short rings: `5.0 mm`, `4 x 4`
- Tall tube: `50.0 mm`, one part
- Added fit compensation: `0.0 mm`

The geometries are simple analytic annular solids with no B-spline surfaces.
Use the files prefixed `PRINT_THIS_`. For the tall tube, enable a slicer brim if
bed adhesion is uncertain; no sacrificial geometry is embedded in the part.

## Outputs

```json
{
  "short_grid_print_step": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_4x4_h5_print_grid.step",
  "short_grid_print_stl": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_4x4_h5_print_grid.stl",
  "short_grid_print_3mf": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_4x4_h5_print_grid.3mf",
  "tall_single_print_step": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_single_h50.step",
  "tall_single_print_stl": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_single_h50.stl",
  "tall_single_print_3mf": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_single_h50.3mf",
  "short_grid_render": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_4x4_h5_print_grid_render.png",
  "tall_single_render": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/PRINT_THIS_cage_spacer_id6p5_od10p5_single_h50_render.png",
  "short_single_step": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/USE_THIS_cage_spacer_id6p5_od10p5_single_h5.step",
  "tall_single_step": "cad/designs/cage_spacer_id6p5_od10p5/runs/run-1-id6p5-od10p5-h5-grid-and-h50-single-print-ready-20260715T085116Z/USE_THIS_cage_spacer_id6p5_od10p5_single_h50.step"
}
```

## Validation

```json
{
  "single_short_step": {
    "valid": true,
    "solids": 1,
    "bbox_mm": [
      10.5,
      10.5,
      5.0
    ],
    "bspline_faces": 0
  },
  "single_short_stl": {
    "watertight": true,
    "component_count": 1,
    "bbox_mm": [
      10.5,
      10.496737,
      5.0
    ],
    "vertices": 504,
    "faces": 1008
  },
  "short_grid_step": {
    "valid": true,
    "solids": 16,
    "bbox_mm": [
      55.5,
      55.5,
      5.0
    ],
    "bspline_faces": 0
  },
  "short_grid_stl": {
    "watertight": true,
    "component_count": 16,
    "bbox_mm": [
      55.5,
      55.496735,
      5.0
    ],
    "vertices": 8064,
    "faces": 16128
  },
  "short_grid_3mf": {
    "entries": [
      "3D/3dmodel.model",
      "[Content_Types].xml",
      "_rels/.rels"
    ],
    "has_model": true,
    "model_bytes": 1266674
  },
  "single_tall_step": {
    "valid": true,
    "solids": 1,
    "bbox_mm": [
      10.5,
      10.5,
      50.0
    ],
    "bspline_faces": 0
  },
  "single_tall_stl": {
    "watertight": true,
    "component_count": 1,
    "bbox_mm": [
      10.5,
      10.496737,
      50.0
    ],
    "vertices": 504,
    "faces": 1008
  },
  "single_tall_3mf": {
    "entries": [
      "3D/3dmodel.model",
      "[Content_Types].xml",
      "_rels/.rels"
    ],
    "has_model": true,
    "model_bytes": 75907
  }
}
```
