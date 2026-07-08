# TSL25911 C-Mount Intensity Sensor Holder 25.0/25.4

New independent CAD design for holding a Waveshare-style TSL25911 light sensor
module behind a nominal `25.4 mm` C-mount receiver with a `25.0 mm` pilot/root.
This version follows the
clean direct-socket lesson from the AS7343 holder: no rectangular bridge/cube
and no middle cylinder. It also fixes the previous visualization mistake by
placing the TSL25911 package on the C-mount-facing side of the PCB.
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
connector/socket edge. The connector edge stays the same; only the component
side visualization is flipped so the sensor package faces the C-mount.

## Design Intent

- Put the TSL25911 sensing package on the C-mount optical axis.
- Use a nominal C-mount receiver size:
  `25.0 mm` female bore/root,
  `25.4 mm` internal
  thread-cutter crest, `0.8 mm` pitch, `0.2 mm`
  radial tooth height.
- Keep the female thread cutter fully inside the `12 mm` C-mount socket:
  x=`0.2` to
  x=`10.2`.
- Generate the female thread cutter with an extra
  `0.4 mm` half-pitch runout
  beyond each nominal end before subtraction, so the internal thread reaches
  the socket end faces more completely without changing pitch or tooth shape.
- Export the C-mount socket and sensor plate as separate adjacent solids; they
  touch at x=`12.0` without a bridge cube, middle cylinder, or
  boolean union.
- Provide a rear module tray for the `20 x 27 mm` board.
- Add an XH2.54-style 5-pin socket relief, nominal body
  `14 mm` along Z x `6 mm` along Y x `5.5 mm` high along X, on the connector
  edge.
- Cut the socket relief as a net clearance measured from the PCB sink floor:
  `6.5 mm`
  beyond the `2.25 mm` PCB sink, for
  `8.75 mm` total depth from the holder rear
  surface.
- Extend the connector relief to the positive-Y holder edge so a Dupont jumper,
  matching male header, or cable can exit without hitting the printed wall.
- Expand the socket/wire relief by
  `2.0 mm` toward
  the sensor-side/opposite connector edge. This lets the PCB slide deeper into
  the tray so the two far M2 holes can reach their holder holes even when the
  XH2.54 socket or wire bundle is slightly wider than the first estimate.
- Add two M2 clearance holes matching the published board-hole pattern.

## C-Mount Size

This nominal C-mount variant uses `25.4 mm` as the internal thread/groove
maximum, not as the smooth female bore. The pilot/root is `25.0 mm`, then the
thread cutter reaches `25.4 mm` nominally. A small `0.02 mm` cutter
overlap is kept only to make the boolean robust, so this is much closer to the
standard nominal diameter than the earlier `25.4 mm` pilot plus larger groove
experiment. Standard C-mount is `1-32 UNS` with `25.4 mm` nominal major diameter
and `0.79375 mm` pitch; the modeled thread still uses the local proven
triangular `0.8 mm` pitch for printability unless a real tap/chase workflow
replaces it.

Thread runout rule used here:

- Female/internal thread by subtraction: generate the cutter with an extra
  half pitch beyond each end, then subtract it from the socket. No extra trim is
  needed because only the intersection with the socket body remains.
- Male/external thread: generate the thread with an extra half pitch beyond the
  nominal end, then cut/trim the final solid back to the mount end face so the
  thread is complete but does not overflow.

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
  "y_min": 11.0,
  "y_max": 21.0,
  "z_min": -7.5,
  "z_max": 7.5,
  "height_x_mm": 5.5,
  "net_relief_height_from_pcb_sink_floor_x_mm": 6.5,
  "total_relief_depth_from_holder_rear_x_mm": 8.75,
  "extra_clearance_toward_sensor_side_y_mm": 2.0,
  "nominal_socket_body_y_min": 13.5,
  "nominal_socket_body_y_max": 19.5,
  "nominal_body_mm": {
    "parallel_to_short_edge_z": 14.0,
    "height_x": 5.5,
    "parallel_to_long_edge_y": 6.0
  }
}
```

Wire/header exit relief:

```json
{
  "name": "Dupont_or_male_header_wire_exit_relief",
  "y_min": 11.0,
  "y_max": 25.6,
  "z_min": -7.5,
  "z_max": 7.5,
  "net_relief_height_from_pcb_sink_floor_x_mm": 6.5,
  "total_relief_depth_from_holder_rear_x_mm": 8.75,
  "note": "This relief extends the socket cutout to the positive-Y holder edge and expands 2.0 mm toward the sensor-side/opposite connector edge, allowing the PCB to slide deeper before the socket or wire bundle hits the printed wall."
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
| multibody_holder_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_multibody_holder.step` |
| multibody_holder_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_multibody_holder.stl` |
| cmount_socket_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_cmount_socket.step` |
| cmount_socket_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_cmount_socket.stl` |
| sensor_plate_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_sensor_plate.step` |
| sensor_plate_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_sensor_plate.stl` |
| assembly_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_assembly.step` |
| assembly_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_assembly.stl` |
| thread_cutter_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_board_proxy.step` |
| board_proxy_stl | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_rear_alignment.pdf` |
| render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_render.png` |
| rear_alignment_render_png | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y_rear_alignment_render.png` |
| blend | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y.blend` |
| manifest | `cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y` |
| `design_variant` | `direct C-mount socket to TSL25911 sensor holder plate; nominal 25.4 mm female C-mount thread with 25.0 mm pilot/root; half-pitch thread runout cutter for fully developed end threads; TSL25911 package visualized on C-mount-facing PCB side; XH2.54 5P socket relief opens fully to holder edge for Dupont/male-header wire exit; socket/wire relief widened 2.0 mm toward the sensor-side/opposite connector edge so the PCB can seat deeper and the far M2 holes can align` |
| `design_date` | `2026-07-08` |
| `units` | `mm` |
| `cmount_standard_note` | `Industrial C-mount is 1-32 UNS, 25.4 mm nominal major diameter and 0.79375 mm pitch. This print-fit variant treats 25.4 mm as the nominal internal groove/cutter maximum, not the smooth pilot bore, so the female pilot/root is 25.0 mm.` |
| `openhi_female_root_diameter_mm` | `25.0` |
| `openhi_female_thread_cutter_crest_diameter_mm` | `25.4` |
| `thread_pitch_mm` | `0.8` |
| `thread_tooth_height_mm` | `0.2` |
| `thread_tooth_base_mm` | `0.8` |
| `thread_runout_extra_cycles_each_end` | `0.5` |
| `thread_runout_extra_length_each_end_mm` | `0.4` |
| `female_socket_length_mm` | `12.0` |
| `female_thread_start_mm` | `0.2` |
| `female_thread_length_mm` | `10.0` |
| `socket_outer_diameter_mm` | `34.0` |
| `optical_bore_diameter_mm` | `8.0` |
| `omitted_middle_connector_length_mm` | `0.0` |
| `sensor_plate_thickness_mm` | `8.75` |
| `sensor_plate_width_y_mm` | `50.0` |
| `sensor_plate_height_z_mm` | `36.0` |
| `sensor_plate_center_z_mm` | `0.0` |
| `module_board_long_y_mm` | `27.0` |
| `module_board_short_z_mm` | `20.0` |
| `sensor_to_sensor_side_short_edge_y_mm` | `7.5` |
| `connector_side` | `positive_y_edge_opposite_sensor_side` |
| `component_side` | `c_mount_facing_negative_x_side_of_board` |
| `module_board_size_source` | `User-corrected TSL25911 module geometry: PCB is 20 x 27 mm; TSL25911 sensing window is centered across the 20 mm short edge and 7.5 mm from the sensor-side short edge opposite the connector/socket edge. The TSL25911 package is on the C-mount-facing side of the PCB.` |
| `board_pocket_clearance_total_mm` | `1.0` |
| `board_pocket_depth_mm` | `2.25` |
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
| `xh254_socket_net_relief_height_from_pcb_sink_floor_x_mm` | `6.5` |
| `xh254_socket_clearance_total_mm` | `1.0` |
| `xh254_socket_relief_extra_y_mm` | `1.0` |
| `xh254_socket_relief_expand_toward_sensor_side_y_mm` | `2.0` |
| `wire_exit_relief_to_holder_edge_mm` | `0.6` |
| `source_wiki` | `https://www.waveshare.net/wiki/TSL25911_Light_Sensor` |
| `source_product` | `https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm` |
| `source_github` | `https://github.com/waveshare/TSL2591X-Light-Sensor` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/build_tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y.py
blender --background --python cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y/render_tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_25p0_25p4_socket_plus2y.py
```
