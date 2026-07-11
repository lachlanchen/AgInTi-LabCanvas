# Cage Dock M10-Hole To M6-Rod Adapter

This adapter compensates for the already-printed dock that has `10 mm` rod
holes. It is a smooth stepped cylinder: a short lower insert for the dock hole
and a longer upper 6 mm cage rod.

## Geometry

- Lower insert: `9.8 mm` diameter x `20.0 mm` long.
- Target dock hole: nominal `10.0 mm`.
- Upper rod: `6.0 mm` diameter x `50.0 mm` long.
- Total height: `70.0 mm`.
- Grid: `2 x 2` adapters on `24.0 mm` pitch.

## Fit Notes

`M10` and `M6` are used as smooth diameter classes here, not modeled screw
threads. The lower insert is intentionally `0.2 mm` smaller than the nominal
10 mm dock hole so it is more likely to slip into the printed hole. The bottom
edge has a small chamfer to help insertion.

## Print Notes

Use the root `PRINT_THIS_*_2x2_print_grid` files for direct slicing. They
contain four upright adapters with no extra reference bodies.

## Outputs

| Output | Path |
| --- | --- |
| adapter_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/cage_dock_m10_to_m6_adapter_20_50.step` |
| adapter_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/cage_dock_m10_to_m6_adapter_20_50.stl` |
| print_grid_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.step` |
| print_grid_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.stl` |
| print_grid_3mf | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.3mf` |
| section_svg | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/cage_dock_m10_to_m6_adapter_20_50_section.svg` |
| section_png | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/cage_dock_m10_to_m6_adapter_20_50_section.png` |
| use_this_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/USE_THIS_cage_dock_m10_to_m6_adapter_20_50.step` |
| print_this_2x2_step | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.step` |
| print_this_2x2_stl | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.stl` |
| print_this_2x2_3mf | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.3mf` |
| manifest | `cad/designs/cage_dock_m10_to_m6_adapter_20_50/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_dock_m10_to_m6_adapter_20_50` |
| `design_intent` | `Smooth stepped adapter for the printed dock that has 10 mm rod holes, converting the hole to a 50 mm tall nominal 6 mm cage rod.` |
| `dock_context` | `The printed dock ended around 25 mm tall with about 20 mm usable blind-hole depth. The lower insert is therefore 20 mm long.` |
| `bottom_nominal_m10_diameter_mm` | `10.0` |
| `bottom_print_fit_diameter_mm` | `9.8` |
| `bottom_insert_length_mm` | `20.0` |
| `upper_nominal_m6_diameter_mm` | `6.0` |
| `upper_rod_length_mm` | `50.0` |
| `total_height_mm` | `70.0` |
| `lead_in_chamfer_mm` | `0.35` |
| `top_chamfer_mm` | `0.35` |
| `print_grid_rows` | `2` |
| `print_grid_cols` | `2` |
| `print_grid_pitch_mm` | `24.0` |
| `print_orientation` | `Print upright on the wider 9.8 mm lower insert end. The 2x2 grid contains four independent adapters.` |
| `fit_note` | `M10 is treated as a smooth 10 mm-class insert, not a modeled screw thread. The lower diameter is 9.8 mm so it can slip into a printed 10 mm dock hole more reliably.` |
