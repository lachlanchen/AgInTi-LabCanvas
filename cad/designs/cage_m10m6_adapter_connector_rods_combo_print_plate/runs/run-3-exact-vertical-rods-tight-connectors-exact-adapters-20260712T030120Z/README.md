# Run 3: Exact Vertical Rods, Tight Connectors, Exact Adapters

This print plate uses only the exact-size parts:

- 3x3 vertical rods: `6.0 mm` diameter x `50.0 mm`.
- 3x3 tight connectors: `21.0 mm` long, `6.0 mm` sockets, `10.0 mm` socket depth each end, `1.0 mm` center diaphragm, `1.0 mm` radial wall.
- 2x2 exact adapters: `10.0 mm` lower insert x `20.0 mm`, then `6.0 mm` upper rod x `50.0 mm`.

M10/M6 are smooth diameter classes in these printed parts, not modeled screw
threads.

## Packed Groups

| Group | Bodies | Size mm |
| --- | ---: | --- |
| vertical_rods_3x3 | 9 | `[38.0, 37.998, 50.0]` |
| tight_connectors_3x3 | 9 | `[40.0, 39.998, 21.0]` |
| exact_adapters_2x2 | 4 | `[35.0, 34.997, 70.0]` |

## Validation

```json
{
  "step": {
    "valid": true,
    "solids": 22,
    "bbox_mm": [
      133.0,
      40.0,
      70.0
    ]
  },
  "stl": {
    "watertight": true,
    "component_count": 22,
    "bounds": {
      "min": [
        0.0,
        0.0,
        0.0
      ],
      "max": [
        133.0,
        39.998,
        70.0
      ],
      "size": [
        133.0,
        39.998,
        70.0
      ]
    },
    "vertices": 19152,
    "faces": 38216
  },
  "threemf": {
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
| print_step | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/artifacts/cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters.step` |
| print_stl | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/artifacts/cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters.stl` |
| print_3mf | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/artifacts/cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters.3mf` |
| print_this_step | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/PRINT_THIS_cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters.step` |
| print_this_stl | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/PRINT_THIS_cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters.stl` |
| print_this_3mf | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/PRINT_THIS_cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters.3mf` |
| print_this_render | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/PRINT_THIS_cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters_render.png` |
| readme | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/README.md` |
| manifest | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/runs/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_m10m6_adapter_connector_rods_combo_print_plate/run-3-exact-vertical-rods-tight-connectors-exact-adapters-20260712T030120Z` |
