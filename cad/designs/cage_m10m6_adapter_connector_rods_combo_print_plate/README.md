# Cage Combo Print Plate: M10-M6 Adapters, Connectors, And Rods

This design simply packs three already validated direct-print layouts onto one
build plate:

- 2x2 M10 dock to M6 rod adapters.
- 3x3 13 mm rod connectors with center diaphragm.
- 5x5 horizontal 50 mm M6 / 6 mm cage rods.

No individual part geometry is redesigned here. The script imports the existing
direct-print STEP/STL sources, normalizes each source group to the build plate,
and places them with `8.0 mm` clearance.

## Print Notes

Use the root `PRINT_THIS_*` files for slicing. The combined plate has
`38` separate printable bodies and is
watertight as an STL mesh. Its bounding box is
`[282.0, 114.994, 70.0] mm`; allow extra slicer margin
around that footprint. The tall parts are the M10-to-M6 adapters, which remain
upright exactly like their source 2x2 print grid.

## Runs

- Root / run 1: 5x5 horizontal rods, 3x3 connectors, 2x2 M10-to-M6 adapters.
- `runs/run-2-3x3-rods-3x3-connectors-2x2-adapters-20260711T112746Z/`: smaller print plate with 3x3 horizontal rods, 3x3 connectors, and 2x2 M10-to-M6 adapters. Use this run when the 25-rod plate is too large or unnecessary.

## Packed Groups

| Group | Bodies | Size mm | Placed min XYZ mm |
| --- | ---: | --- | --- |
| rods_5x5 | 25 | `[282.0, 53.998, 6.0]` | `[0.0, 0.0, 0.0]` |
| connectors_3x3 | 9 | `[53.0, 52.996, 13.0]` | `[0.0, 61.998, 0.0]` |
| adapters_2x2 | 4 | `[33.8, 33.797, 70.0]` | `[61.0, 61.998, 0.0]` |

## Outputs

| Output | Path |
| --- | --- |
| print_step | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/artifacts/cage_m10m6_adapter_connector_rods_combo_print_plate.step` |
| print_stl | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/artifacts/cage_m10m6_adapter_connector_rods_combo_print_plate.stl` |
| print_3mf | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/artifacts/cage_m10m6_adapter_connector_rods_combo_print_plate.3mf` |
| root_print_step | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/PRINT_THIS_cage_m10m6_adapter_connector_rods_combo_print_plate.step` |
| root_print_stl | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/PRINT_THIS_cage_m10m6_adapter_connector_rods_combo_print_plate.stl` |
| root_print_3mf | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/PRINT_THIS_cage_m10m6_adapter_connector_rods_combo_print_plate.3mf` |
| render_png | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/artifacts/cage_m10m6_adapter_connector_rods_combo_print_plate_render.png` |
| root_render_png | `cad/designs/cage_m10m6_adapter_connector_rods_combo_print_plate/PRINT_THIS_cage_m10m6_adapter_connector_rods_combo_print_plate_render.png` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/cage_m10m6_adapter_connector_rods_combo_print_plate/run-1-combo-print-ready` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_m10m6_adapter_connector_rods_combo_print_plate` |
| `design_intent` | `Single build-plate packing of the existing 2x2 M10-to-M6 adapters, 3x3 rod connectors, and 5x5 horizontal rods.` |
| `clearance_between_groups_mm` | `8.0` |
| `packing_rule` | `Preserve each source print orientation, normalize every source group to the build plate, place rods first, then use the upper-left free space for connectors and adapters.` |
| `source_groups` | `{'rods_5x5': '5x5 grid of 50 mm M6 / 6 mm cage rods', 'connectors_3x3': '3x3 grid of 13 mm rod connectors', 'adapters_2x2': '2x2 grid of M10 dock to M6 rod adapters'}` |
| `print_plate_note` | `The 25-rod source grid is already long, so the combined plate needs a roughly 290 x 125 mm usable bed after slicer margin.` |
