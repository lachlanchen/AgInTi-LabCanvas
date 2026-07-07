# TSL25911 C-Mount Intensity Sensor Holder Direct Socket XH2.54

New independent CAD design for holding a Waveshare-style TSL25911 light sensor
module behind an OpenHI-print-fit C-mount receiver. This version follows the
clean direct-socket lesson from the AS7343 holder: no rectangular bridge/cube
and no middle cylinder.
The left C-mount socket directly touches the rear sensor plate at
x=`12.0`. The C-mount socket and sensor plate are exported as
adjacent independent bodies so Shapr3D can select and edit them separately.
Older CAD designs are not modified.

## Source References

- Local reference snapshot: `cad/references/waveshare-tsl25911-light-sensor`
- Waveshare wiki: `https://www.waveshare.net/wiki/TSL25911_Light_Sensor`
- Waveshare product page: `https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm`
- Waveshare example code: `https://github.com/waveshare/TSL2591X-Light-Sensor`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The physical tray follows the corrected geometry from the latest module check:
the board is `20 x 27 mm`; the TSL25911 sensing window is centered across the
`20 mm` short side and is `7.5 mm` from the sensor-side short edge, opposite the
connector/socket edge.

## Design Intent

- Put the TSL25911 sensing package on the C-mount optical axis.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Keep the female thread cutter fully inside the `12 mm` C-mount socket:
  x=`0.2` to
  x=`10.2`.
- Export the C-mount socket and sensor plate as separate adjacent solids; they
  touch at x=`12.0` without a bridge cube, middle cylinder, or
  boolean union.
- Provide a rear module tray for the `20 x 27 mm` board.
- Add an XH2.54-style 5-pin socket relief, nominal body
  `14 mm` along Z x `6 mm` along Y x `5.5 mm` high along X, on the connector
  edge.
- Add two M2 clearance holes matching the published board-hole pattern.

## C-Mount Size

The printed receiver uses the local OpenHI print-fit size: `24.8 mm` female
root/bore. It is not modeled as a raw `25.4 mm` cylinder. Standard C-mount is
`1-32 UNS` with `0.79375 mm` pitch; this printed design keeps the existing
OpenHI-compatible `0.8 mm` pitch thread convention.

## Geometry Used

Board center relative to the TSL25911 package:

```json
{
  "y": 6.0,
  "z": 0.0
}
```

Board bounds relative to the TSL25911 sensing window:

```json
{
  "y_min": -7.5,
  "y_max": 19.5,
  "z_min": -10.0,
  "z_max": 10.0
}
```

XH2.54 5P socket relief:

```json
{
  "name": "XH2.54_5P_socket_relief",
  "assumed_side": "positive_y_edge_opposite_sensor_side",
  "y_min": 13.0,
  "y_max": 21.0,
  "z_min": -7.5,
  "z_max": 7.5,
  "height_x_mm": 5.5,
  "nominal_body_mm": {
    "parallel_to_short_edge_z": 14.0,
    "height_x": 5.5,
    "parallel_to_long_edge_y": 6.0
  }
}
```

M2 mounting holes:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
| M2_bottom | `-5.5` | `-8.0` | `2.4` |
| M2_top | `-5.5` | `8.0` | `2.4` |

## Outputs

| Output | Path |
| --- | --- |
| multibody_holder_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_multibody_holder.step` |
| multibody_holder_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_multibody_holder.stl` |
| cmount_socket_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_cmount_socket.step` |
| cmount_socket_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_cmount_socket.stl` |
| sensor_plate_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_plate.step` |
| sensor_plate_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_plate.stl` |
| assembly_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_assembly.step` |
| assembly_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_assembly.stl` |
| thread_cutter_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_board_proxy.step` |
| board_proxy_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_rear_alignment.pdf` |
| render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_render.png` |
| rear_alignment_render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_rear_alignment_render.png` |
| blend | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254.blend` |
| manifest | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254` |
| `design_variant` | `direct C-mount socket to TSL25911 sensor holder plate with XH2.54 5P socket relief; no bridge block and no middle tube` |
| `design_date` | `2026-07-07` |
| `units` | `mm` |
| `cmount_standard_note` | `Industrial C-mount is 1-32 UNS, 0.79375 mm pitch; this part follows the local OpenHI printed 0.8 mm pitch convention.` |
| `openhi_female_root_diameter_mm` | `24.8` |
| `openhi_female_thread_cutter_crest_diameter_mm` | `25.6` |
| `thread_pitch_mm` | `0.8` |
| `thread_tooth_height_mm` | `0.4` |
| `thread_tooth_base_mm` | `0.8` |
| `female_socket_length_mm` | `12.0` |
| `female_thread_start_mm` | `0.2` |
| `female_thread_length_mm` | `10.0` |
| `socket_outer_diameter_mm` | `34.0` |
| `optical_bore_diameter_mm` | `8.0` |
| `omitted_middle_connector_length_mm` | `0.0` |
| `sensor_plate_thickness_mm` | `7.0` |
| `sensor_plate_width_y_mm` | `50.0` |
| `sensor_plate_height_z_mm` | `36.0` |
| `sensor_plate_center_z_mm` | `0.0` |
| `module_board_long_y_mm` | `27.0` |
| `module_board_short_z_mm` | `20.0` |
| `sensor_to_sensor_side_short_edge_y_mm` | `7.5` |
| `connector_side` | `positive_y_edge_opposite_sensor_side` |
| `module_board_size_source` | `User-corrected TSL25911 module geometry: PCB is 20 x 27 mm; TSL25911 sensing window is centered across the 20 mm short edge and 7.5 mm from the sensor-side short edge opposite the connector/socket edge.` |
| `board_pocket_clearance_total_mm` | `1.0` |
| `board_pocket_depth_mm` | `2.2` |
| `board_thickness_mm` | `1.6` |
| `tsl25911_package_width_y_mm` | `3.0` |
| `tsl25911_package_height_z_mm` | `3.6` |
| `tsl25911_package_thickness_x_mm` | `1.0` |
| `tsl25911_window_diameter_mm` | `1.4` |
| `mount_hole_diameter_mm` | `2.0` |
| `mount_hole_clearance_diameter_mm` | `2.4` |
| `mount_hole_y_from_sensor_side_edge_mm` | `2.0` |
| `mount_hole_z_from_board_edge_mm` | `2.0` |
| `xh254_5p_socket_width_z_mm` | `14.0` |
| `xh254_5p_socket_depth_y_mm` | `6.0` |
| `xh254_5p_socket_height_x_mm` | `5.5` |
| `xh254_socket_clearance_total_mm` | `1.0` |
| `xh254_socket_relief_extra_y_mm` | `1.0` |
| `source_wiki` | `https://www.waveshare.net/wiki/TSL25911_Light_Sensor` |
| `source_product` | `https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm` |
| `source_github` | `https://github.com/waveshare/TSL2591X-Light-Sensor` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/build_tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254.py
blender --background --python cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254/render_tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254.py
```
