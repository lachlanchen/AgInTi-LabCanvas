# AS7341 C-Mount Sensor Holder

New independent CAD design for holding a Waveshare AS7341 Spectral Color Sensor
behind an OpenHI-print-fit C-mount receiver. Older CAD designs are not modified.

## Source References

- Waveshare wiki: `https://www.waveshare.com/wiki/AS7341_Spectral_Color_Sensor`
- Waveshare product page: `https://www.waveshare.com/as7341-spectral-color-sensor.htm`
- Official 3D package: `cad/references/waveshare-as7341-spectral-sensor/3d/`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The vendor drawing gives a `30.5 x 23 mm` breakout, two `2.0 mm` mounting
holes, and a `0.9 mm` AS7341 optical aperture. The official STEP/DXF/PDF are
downloaded under the reference folder above.

## Design Intent

- Put the AS7341 optical aperture on the C-mount optical axis.
- Keep the PCB pocket asymmetric because the sensor aperture is near the top of
  the breakout, not at the board center.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Keep the back side serviceable: a shallow board pocket, two M2 clearance
  holes, and a bottom PH2.0 cable relief.

## Board Geometry Used

Mounting holes are relative to the AS7341 aperture/optical axis:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
| M2_1 | `-9.4` | `1.1` | `2.4` |
| M2_2 | `9.4` | `1.1` | `2.4` |

Board center relative to aperture:

```json
{
  "y": 0.0,
  "z": -11.95
}
```

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder.step` |
| holder_stl | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder.stl` |
| assembly_step | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_assembly.step` |
| assembly_stl | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_assembly.stl` |
| thread_cutter_step | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_board_proxy.step` |
| board_proxy_stl | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_rear_alignment.pdf` |
| render_png | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_render.png` |
| rear_alignment_render_png | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder_rear_alignment_render.png` |
| blend | `cad/designs/as7341_cmount_sensor_holder/artifacts/as7341_cmount_sensor_holder.blend` |
| manifest | `cad/designs/as7341_cmount_sensor_holder/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `as7341_cmount_sensor_holder` |
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
| `sensor_plate_width_y_mm` | `38.0` |
| `sensor_plate_height_z_mm` | `50.0` |
| `sensor_plate_center_z_mm` | `-12.0` |
| `waveshare_board_width_y_mm` | `23.0` |
| `waveshare_board_height_z_mm` | `30.5` |
| `board_pocket_clearance_total_mm` | `0.8` |
| `board_pocket_depth_mm` | `2.0` |
| `board_thickness_mm` | `1.6` |
| `as7341_aperture_diameter_mm` | `0.9` |
| `as7341_aperture_x_from_left_edge_mm` | `11.5` |
| `as7341_aperture_from_board_top_mm` | `3.3` |
| `mount_hole_diameter_mm` | `2.0` |
| `mount_hole_clearance_diameter_mm` | `2.4` |
| `mount_hole_centers_from_left_edge_mm` | `[2.1, 20.9]` |
| `mount_hole_from_board_top_mm` | `2.2` |
| `cable_relief_width_y_mm` | `16.0` |
| `cable_relief_height_z_mm` | `11.0` |
| `source_wiki` | `https://www.waveshare.com/wiki/AS7341_Spectral_Color_Sensor` |
| `source_product` | `https://www.waveshare.com/as7341-spectral-color-sensor.htm` |
| `source_3d_package` | `https://files.waveshare.com/wiki/AS7341%20Spectral%20Color%20Sensor/As7341_spectral_color_sensor.rar` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/as7341_cmount_sensor_holder/build_as7341_cmount_sensor_holder.py
blender --background --python cad/designs/as7341_cmount_sensor_holder/render_as7341_cmount_sensor_holder.py
```
