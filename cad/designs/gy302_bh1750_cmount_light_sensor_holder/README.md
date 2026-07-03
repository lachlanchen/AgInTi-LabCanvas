# GY-302 BH1750 C-Mount Light Sensor Holder

New independent CAD design for holding a GY-302 BH1750 light intensity module
behind an OpenHI-print-fit C-mount receiver. Older CAD designs are not modified.

## Source References

- Local reference snapshot: `cad/references/gy302-bh1750-light-sensor`
- Local BH1750 datasheet: `cad/references/gy302-bh1750-light-sensor/1. 数据手册/BH1750FVI.pdf`
- Local GY-302 schematic: `cad/references/gy302-bh1750-light-sensor/2. 原理图/GY-302原理图.jpg`
- Public module size reference: `https://www.handsontec.com/dataspecs/sensor/BH1750%20Light%20Sensor.pdf`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The local files include the BH1750 datasheet and GY-302 schematic but no module
STEP/DXF/mechanical drawing. Public GY-302 listings commonly give about
`13.9 x 18.5 mm`; this design uses a parametric `14 x 19 mm` board tray.

## Design Intent

- Put the BH1750 photodiode area on the C-mount optical axis.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Provide a rear GY-302 tray with estimated two-hole board mounting and 1x5
  header/cable relief.
- Keep board size, hole locations, and sensor offset editable in this script for
  caliper correction after checking the physical module.

## Geometry Used

Board center relative to the BH1750 photodiode datum:

```json
{
  "y": -0.0,
  "z": -0.0
}
```

Mounting holes:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
| mount_left | `-4.0` | `6.2` | `3.3` |
| mount_right | `4.0` | `6.2` | `3.3` |

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder.step` |
| holder_stl | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder.stl` |
| assembly_step | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_assembly.step` |
| assembly_stl | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_assembly.stl` |
| thread_cutter_step | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_board_proxy.step` |
| board_proxy_stl | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_rear_alignment.pdf` |
| render_png | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_render.png` |
| rear_alignment_render_png | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder_rear_alignment_render.png` |
| blend | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/gy302_bh1750_cmount_light_sensor_holder.blend` |
| manifest | `cad/designs/gy302_bh1750_cmount_light_sensor_holder/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `gy302_bh1750_cmount_light_sensor_holder` |
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
| `sensor_plate_width_y_mm` | `42.0` |
| `sensor_plate_height_z_mm` | `38.0` |
| `sensor_plate_center_z_mm` | `0.0` |
| `gy302_board_width_y_mm` | `14.0` |
| `gy302_board_height_z_mm` | `19.0` |
| `board_size_source_note` | `Common GY-302 BH1750 listings give about 13.9 x 18.5 mm; this design uses a 14 x 19 mm parametric tray.` |
| `board_pocket_clearance_total_mm` | `0.8` |
| `board_pocket_depth_mm` | `2.0` |
| `board_thickness_mm` | `1.6` |
| `bh1750_package_width_y_mm` | `2.0` |
| `bh1750_package_height_z_mm` | `1.6` |
| `bh1750_package_thickness_x_mm` | `0.8` |
| `bh1750_pd_area_width_y_mm` | `0.25` |
| `bh1750_pd_area_height_z_mm` | `0.3` |
| `bh1750_sensor_offset_y_mm` | `0.0` |
| `bh1750_sensor_offset_z_mm` | `0.0` |
| `board_mount_hole_diameter_mm` | `3.0` |
| `board_mount_hole_clearance_diameter_mm` | `3.3` |
| `board_mount_hole_y_abs_mm` | `4.0` |
| `board_mount_hole_z_mm` | `6.2` |
| `header_relief_width_y_mm` | `13.0` |
| `header_relief_height_z_mm` | `7.0` |
| `header_relief_z_mm` | `-7.4` |
| `source_local_datasheet` | `cad/references/gy302-bh1750-light-sensor/1. 数据手册/BH1750FVI.pdf` |
| `source_local_schematic` | `cad/references/gy302-bh1750-light-sensor/2. 原理图/GY-302原理图.jpg` |
| `source_module_size` | `https://www.handsontec.com/dataspecs/sensor/BH1750%20Light%20Sensor.pdf` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/gy302_bh1750_cmount_light_sensor_holder/build_gy302_bh1750_cmount_light_sensor_holder.py
blender --background --python cad/designs/gy302_bh1750_cmount_light_sensor_holder/render_gy302_bh1750_cmount_light_sensor_holder.py
```
