# TSL25911 C-Mount Intensity Sensor Holder

New independent CAD design for holding a Waveshare TSL25911 Light Sensor behind
an OpenHI-print-fit C-mount receiver. Older CAD designs are not modified.

## Source References

- Waveshare wiki: `https://www.waveshare.net/wiki/TSL25911_Light_Sensor`
- Waveshare product page: `https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm`
- Waveshare example code: `https://github.com/waveshare/TSL2591X-Light-Sensor`
- Local reference snapshot: `cad/references/waveshare-tsl25911-light-sensor`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The vendor documentation gives a `27 x 20 mm` breakout, two `2.0 mm`
mounting holes with `16 mm` spacing on the left side, `0-88000 Lux` range, and
I2C address `0x29`. I did not find an official STEP model in the vendor
downloads, so this holder uses the published size image and keeps the sensor
window datum parametric for later caliper adjustment.

## Design Intent

- Put the TSL25911 sensing window on the C-mount optical axis.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Keep the board removable with a shallow rear pocket, two M2 clearance holes,
  and a right-side connector/Dupont wire relief.
- Keep the holder simple and printable: one solid receiver/plate part plus
  separate board, connector, axis, and thread-cutter reference objects.

## Board Geometry Used

Mounting holes are relative to the TSL25911 window/optical axis:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
| M2_bottom | `-5.5` | `-8.0` | `2.4` |
| M2_top | `-5.5` | `8.0` | `2.4` |

Board center relative to the sensor window:

```json
{
  "y": 6.0,
  "z": 0.0
}
```

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder.step` |
| holder_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder.stl` |
| assembly_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_assembly.step` |
| assembly_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_assembly.stl` |
| thread_cutter_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_board_proxy.step` |
| board_proxy_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_rear_alignment.pdf` |
| render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_render.png` |
| rear_alignment_render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder_rear_alignment_render.png` |
| blend | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/tsl25911_cmount_intensity_sensor_holder.blend` |
| manifest | `cad/designs/tsl25911_cmount_intensity_sensor_holder/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `tsl25911_cmount_intensity_sensor_holder` |
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
| `sensor_plate_height_z_mm` | `36.0` |
| `sensor_plate_center_z_mm` | `0.0` |
| `waveshare_board_width_y_mm` | `27.0` |
| `waveshare_board_height_z_mm` | `20.0` |
| `board_pocket_clearance_total_mm` | `0.8` |
| `board_pocket_depth_mm` | `2.0` |
| `board_thickness_mm` | `1.6` |
| `tsl25911_window_diameter_mm` | `1.4` |
| `tsl25911_window_x_from_left_edge_mm` | `7.5` |
| `tsl25911_window_from_board_top_mm` | `10.0` |
| `mount_hole_diameter_mm` | `2.0` |
| `mount_hole_clearance_diameter_mm` | `2.4` |
| `mount_hole_x_from_left_edge_mm` | `2.0` |
| `mount_hole_from_board_edge_z_mm` | `2.0` |
| `connector_relief_width_y_mm` | `10.0` |
| `connector_relief_height_z_mm` | `18.0` |
| `source_wiki` | `https://www.waveshare.net/wiki/TSL25911_Light_Sensor` |
| `source_product` | `https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm` |
| `source_github` | `https://github.com/waveshare/TSL2591X-Light-Sensor` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/tsl25911_cmount_intensity_sensor_holder/build_tsl25911_cmount_intensity_sensor_holder.py
blender --background --python cad/designs/tsl25911_cmount_intensity_sensor_holder/render_tsl25911_cmount_intensity_sensor_holder.py
```
