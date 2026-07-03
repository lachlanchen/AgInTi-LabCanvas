# AS7343 C-Mount Spectral Module Holder

New independent CAD design for holding an AS7343 spectral analysis module behind
an OpenHI-print-fit C-mount receiver. Older CAD designs are not modified.

## Source References

- Local reference snapshot: `cad/references/as7343-spectral-analysis-module`
- Local AS7343 datasheet: `cad/references/as7343-spectral-analysis-module/资料/AS7343_DS001046_6-00.pdf`
- Local module schematic: `cad/references/as7343-spectral-analysis-module/AS7343光谱分析模块原理图.png`
- ams OSRAM product page: `https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7343-spectral-sensor`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The supplied module references include the AS7343 datasheet, app notes, example
code, and a schematic image, but no mechanical board outline. The holder is
therefore parametric: it centers the AS7343 package on the optical axis and uses
an estimated centered module tray. Measure the real PCB and update the
`estimated_module_board_*` and `as7343_sensor_offset_*` parameters if needed.

## Design Intent

- Put the AS7343 sensing package on the C-mount optical axis.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Provide a rear module tray with left-side 1x5 header/cable relief.
- Add four optional M2 clamp/lid holes outside the estimated module footprint.

## Geometry Used

Board center relative to the AS7343 package:

```json
{
  "y": -0.0,
  "z": -0.0
}
```

Optional clamp holes:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
| clamp_bottom_left | `-20.0` | `-16.0` | `2.4` |
| clamp_top_left | `-20.0` | `16.0` | `2.4` |
| clamp_bottom_right | `20.0` | `-16.0` | `2.4` |
| clamp_top_right | `20.0` | `16.0` | `2.4` |

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder.step` |
| holder_stl | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder.stl` |
| assembly_step | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_assembly.step` |
| assembly_stl | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_assembly.stl` |
| thread_cutter_step | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_board_proxy.step` |
| board_proxy_stl | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_rear_alignment.pdf` |
| render_png | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_render.png` |
| rear_alignment_render_png | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder_rear_alignment_render.png` |
| blend | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/as7343_cmount_spectral_module_holder.blend` |
| manifest | `cad/designs/as7343_cmount_spectral_module_holder/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `as7343_cmount_spectral_module_holder` |
| `design_date` | `2026-07-03` |
| `units` | `mm` |
| `cmount_standard_note` | `Industrial C-mount is 1-32 UNS, 0.79375 mm pitch; this part follows the local OpenHI printed 0.8 mm pitch convention.` |
| `openhi_female_root_diameter_mm` | `24.8` |
| `openhi_female_thread_cutter_crest_diameter_mm` | `25.6` |
| `thread_pitch_mm` | `0.8` |
| `thread_tooth_height_mm` | `0.4` |
| `thread_tooth_base_mm` | `0.8` |
| `female_socket_length_mm` | `12.0` |
| `female_thread_length_mm` | `10.0` |
| `socket_outer_diameter_mm` | `34.0` |
| `body_tube_outer_diameter_mm` | `30.0` |
| `optical_bore_diameter_mm` | `8.0` |
| `tube_length_mm` | `18.0` |
| `sensor_plate_thickness_mm` | `7.0` |
| `sensor_plate_width_y_mm` | `50.0` |
| `sensor_plate_height_z_mm` | `42.0` |
| `sensor_plate_center_z_mm` | `0.0` |
| `estimated_module_board_width_y_mm` | `32.0` |
| `estimated_module_board_height_z_mm` | `24.0` |
| `module_board_size_source` | `No board mechanical drawing was found in the supplied AS7343 module files; this is a parametric tray estimate.` |
| `board_pocket_clearance_total_mm` | `1.0` |
| `board_pocket_depth_mm` | `2.2` |
| `board_thickness_mm` | `1.6` |
| `as7343_package_width_y_mm` | `3.1` |
| `as7343_package_height_z_mm` | `2.0` |
| `as7343_package_thickness_x_mm` | `1.0` |
| `as7343_window_diameter_mm` | `1.0` |
| `as7343_sensor_offset_y_mm` | `0.0` |
| `as7343_sensor_offset_z_mm` | `0.0` |
| `header_relief_side` | `negative_y` |
| `header_relief_width_y_mm` | `12.0` |
| `header_relief_height_z_mm` | `18.0` |
| `optional_clamp_hole_diameter_mm` | `2.4` |
| `optional_clamp_hole_margin_y_mm` | `4.0` |
| `optional_clamp_hole_margin_z_mm` | `4.0` |
| `source_chip_product` | `https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7343-spectral-sensor` |
| `source_chip_datasheet_local` | `cad/references/as7343-spectral-analysis-module/资料/AS7343_DS001046_6-00.pdf` |
| `source_module_schematic_local` | `cad/references/as7343-spectral-analysis-module/AS7343光谱分析模块原理图.png` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/as7343_cmount_spectral_module_holder/build_as7343_cmount_spectral_module_holder.py
blender --background --python cad/designs/as7343_cmount_spectral_module_holder/render_as7343_cmount_spectral_module_holder.py
```
