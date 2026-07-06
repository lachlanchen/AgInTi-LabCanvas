# TSL25911 C-Mount Intensity Sensor Holder Printable Saddle

This is a new printable variant of `tsl25911_cmount_intensity_sensor_holder`. The original clean,
aligned holder is left unchanged.

## What Changed

- Added an integrated flat-bottom saddle below the C-mount socket/tube so the
  round receiver no longer starts as a suspended cliff when printed flat.
- Re-cut the female C-mount bore, printed internal thread, optical bore, and
  screw/clamp holes after adding the saddle.
- Preserved the original board pocket, sensor datum, thread convention, and
  source reference assumptions.

## Sensor Center Check

`TSL25911 window` is placed on the optical axis:

```json
{
  "sensor_label": "TSL25911 window",
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
    "y": 6.0,
    "z": 0.0
  },
  "note": "The active sensor datum is at Y=0, Z=0. Board center may be offset when the sensor is not at board center."
}
```

## Print Saddle

```json
{
  "type": "integrated flat-bottom C-mount saddle",
  "x_range_mm": [
    0.0,
    30.25
  ],
  "y_range_mm": [
    -17.0,
    17.0
  ],
  "z_range_mm": [
    -18.0,
    0.0
  ],
  "purpose": "Fill the underside of the round C-mount socket/tube down to the print plane."
}
```

Use the holder STL for printing. Use the assembly STEP/STL to inspect the board
proxy, sensor datum, thread cutter, optical axis, and added saddle together.

## Source Design

- Source design: `cad/designs/tsl25911_cmount_intensity_sensor_holder`
- Source README: `cad/designs/tsl25911_cmount_intensity_sensor_holder/README.md`
- Local OpenHI thread reference: `cad/references/openhi-print-fit-and-thread-reference.md`

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_holder.step` |
| holder_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_holder.stl` |
| support_saddle_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_support_saddle.step` |
| support_saddle_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_support_saddle.stl` |
| board_proxy_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_board_proxy.step` |
| board_proxy_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_board_proxy.stl` |
| sensor_proxy_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_sensor_proxy.step` |
| sensor_proxy_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_sensor_proxy.stl` |
| accessory_proxy_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_accessory_proxy.step` |
| accessory_proxy_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_accessory_proxy.stl` |
| thread_cutter_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_thread_cutter.stl` |
| axis_proxy_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_axis_proxy.step` |
| axis_proxy_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_axis_proxy.stl` |
| assembly_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_assembly.step` |
| assembly_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_assembly.stl` |
| render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_render.png` |
| print_orientation_render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/tsl25911_cmount_intensity_sensor_holder_printable_saddle_print_orientation_render.png` |
| manifest | `cad/designs/tsl25911_cmount_intensity_sensor_holder_printable_saddle/artifacts/manifest.json` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/tools/build_printable_cmount_sensor_holder_variants.py tsl25911
blender --background --python cad/tools/render_printable_cmount_sensor_holder_variants.py -- tsl25911
```
