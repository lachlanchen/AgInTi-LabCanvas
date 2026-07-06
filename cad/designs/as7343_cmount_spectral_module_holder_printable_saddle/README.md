# AS7343 C-Mount Spectral Module Holder Clean Printable

This folder keeps the historical `as7343_cmount_spectral_module_holder_printable_saddle` name, but the generated
geometry is now the clean holder shape with no flat-bottom saddle/fill body.
The source holder remains the authoritative parametric design.

## What Changed

- Removed the integrated flat-bottom saddle and overflow fill because it made
  the design visually bulky.
- Preserved the original board pocket, sensor datum, thread convention, and
  source reference assumptions.
- Re-exported the holder, board proxy, sensor proxy, connector/header proxy,
  thread cutter, optical axis, assembly, render, and print-orientation render.

## Sensor Center Check

`AS7343 package/window` is placed on the optical axis:

```json
{
  "sensor_label": "AS7343 package/window",
  "optical_axis_yz_mm": {
    "y": 0.0,
    "z": 0.0
  },
  "sensor_datum_yz_mm": {
    "y": 0.0,
    "z": 0.0
  },
  "sensor_datum_is_on_optical_axis": true,
  "board_center_relative_to_sensor_or_window_mm": {
    "y": -0.0,
    "z": -0.0
  },
  "note": "The active sensor datum is at Y=0, Z=0. Board center may be offset when the sensor is not at board center."
}
```

## Print Policy

```json
{
  "type": "clean holder without extra saddle or overflow fill",
  "legacy_folder_name": "as7343_cmount_spectral_module_holder_printable_saddle",
  "saddle_fill_removed": true,
  "holder_bounding_box_mm": {
    "x": [
      -0.0061,
      37.0004
    ],
    "y": [
      -25.0002,
      25.0002
    ],
    "z": [
      -21.0002,
      21.0002
    ]
  },
  "print_note": "Use normal slicer-generated supports if needed. The CAD no longer adds a custom fill block under the C-mount tube."
}
```

Use the holder STL for printing. Use the assembly STEP/STL to inspect the board
proxy, sensor datum, thread cutter, and optical axis together.

## Source Design

- Source design: `cad/designs/as7343_cmount_spectral_module_holder`
- Source README: `cad/designs/as7343_cmount_spectral_module_holder/README.md`
- Local OpenHI thread reference: `cad/references/openhi-print-fit-and-thread-reference.md`

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_holder.step` |
| holder_stl | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_holder.stl` |
| board_proxy_step | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_board_proxy.step` |
| board_proxy_stl | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_board_proxy.stl` |
| sensor_proxy_step | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_sensor_proxy.step` |
| sensor_proxy_stl | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_sensor_proxy.stl` |
| accessory_proxy_step | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_accessory_proxy.step` |
| accessory_proxy_stl | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_accessory_proxy.stl` |
| thread_cutter_step | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_thread_cutter.stl` |
| axis_proxy_step | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_axis_proxy.step` |
| axis_proxy_stl | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_axis_proxy.stl` |
| assembly_step | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_assembly.step` |
| assembly_stl | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_assembly.stl` |
| render_png | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_render.png` |
| print_orientation_render_png | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/as7343_cmount_spectral_module_holder_printable_saddle_print_orientation_render.png` |
| manifest | `cad/designs/as7343_cmount_spectral_module_holder_printable_saddle/artifacts/manifest.json` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/tools/build_printable_cmount_sensor_holder_variants.py as7343
blender --background --python cad/tools/render_printable_cmount_sensor_holder_variants.py -- as7343
```
