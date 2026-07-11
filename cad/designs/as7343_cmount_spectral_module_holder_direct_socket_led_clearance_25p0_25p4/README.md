# AS7343 C-Mount Spectral Module Holder LED Clearance 25.0/25.4

New independent CAD design for holding an AS7343 spectral analysis module behind
an industrial-size nominal `25.4 mm` C-mount receiver with a `25.0 mm`
pilot/root. This version removes both
intermediate connector shapes: no rectangular bridge/cube and no middle
cylinder/tube. The left C-mount socket directly touches the rear sensor plate at
x=`12.0`.
The C-mount socket and the sensor plate are exported as adjacent independent
bodies so Shapr3D can select and edit them separately. Older CAD designs are
not modified. This variant fixes the pin-header placeholder: the five pin holes
are reserved on the PCB placeholder itself, not next to the PCB. The pin-header
holes are now `3.0 mm` on a `2.54 mm` pitch and are joined into one continuous
slot so the material between adjacent holes is cleared. It also clears the
AS7343 module LED with a through-slot connected to the optical bore.

## Source References

- Local reference snapshot: `cad/references/as7343-spectral-analysis-module`
- Local AS7343 datasheet: `cad/references/as7343-spectral-analysis-module/资料/AS7343_DS001046_6-00.pdf`
- Local module schematic: `cad/references/as7343-spectral-analysis-module/AS7343光谱分析模块原理图.png`
- ams OSRAM product page: `https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7343-spectral-sensor`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The supplied module references include the AS7343 datasheet, app notes, example
code, and a schematic image. The physical tray now follows the corrected module
geometry provided after checking the board: `15 x 23 mm`, pin sockets on the
negative-Y short edge, and the AS7343 package centered across the 15 mm short
edge and `6 mm` from the opposite positive-Y short edge. The board center is
therefore `5.5 mm` toward the pin sockets relative to the optical axis.

## Design Intent

- Put the AS7343 sensing package on the C-mount optical axis.
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
  beyond each nominal end before subtraction, so the internal thread reaches the
  socket end faces more completely. This extra runout is a cutter technique; it
  does not leave external thread overflow on the final socket body.
- Export the C-mount socket and sensor plate as separate adjacent solids; they
  touch at x=`12.0` without a bridge cube, middle cylinder, or
  boolean union.
- Provide a rear module tray for the `15 x 23 mm` board.
- Clear the AS7343 board LED with a `4.0 mm`
  wide through-slot from the optical bore toward the sensor-side short edge.
  The LED reference body is
  `3.3 mm` parallel to the short edge and
  `2.6 mm` parallel to the long edge.
- Add a five-hole `3.0 mm` pin-header clearance row on the PCB placeholder,
  2.5 mm inside the negative-Y board edge.
- Because `3.0 mm` is larger than the `2.54 mm` pitch, join the holes with a
  rectangular bridge cutter so the space between adjacent pin reservations is
  completely clear.
- Cut the same five-hole row through the printed holder plate, so the visual
  PCB placeholder and physical clearance match.
- Add four optional M2 clamp/lid holes outside the corrected module footprint.

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

Board center relative to the AS7343 package:

```json
{
  "y": -5.5,
  "z": -0.0
}
```

Board bounds relative to the AS7343 package:

```json
{
  "y_min": -17.0,
  "y_max": 6.0,
  "z_min": -7.5,
  "z_max": 7.5
}
```

AS7343 LED clearance:

```json
{
  "name": "as7343_board_led_connected_clearance",
  "y_min": 0.0,
  "y_max": 6.5,
  "z_min": -2.0,
  "z_max": 2.0,
  "width_z_mm": 4.0,
  "note": "A 4 mm wide through-slot connects to the central optical bore and opens the holder surface toward the AS7343 sensor-side short edge for the nearby board LED."
}
```

AS7343 LED reference body:

```json
{
  "name": "as7343_board_led_reference_body",
  "y_min": 3.4,
  "y_max": 6.0,
  "z_min": -1.65,
  "z_max": 1.65,
  "body_width_parallel_to_short_edge_z_mm": 3.3,
  "body_length_parallel_to_long_edge_y_mm": 2.6,
  "note": "Approximate AS7343 module LED body near the sensor-side short edge; clearance intentionally uses 4 mm width rather than only the 3.3 mm body width."
}
```

PCB pin-header reserved holes:

| Hole | y mm | z mm | holder/PCB cut dia mm |
| --- | ---: | ---: | ---: |
| pcb_pin_header_1 | `-14.5` | `-5.08` | `3.0` |
| pcb_pin_header_2 | `-14.5` | `-2.54` | `3.0` |
| pcb_pin_header_3 | `-14.5` | `0.0` | `3.0` |
| pcb_pin_header_4 | `-14.5` | `2.54` | `3.0` |
| pcb_pin_header_5 | `-14.5` | `5.08` | `3.0` |

Optional clamp holes:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
| clamp_bottom_left | `-21.0` | `-11.5` | `2.4` |
| clamp_top_left | `-21.0` | `11.5` | `2.4` |
| clamp_bottom_right | `10.0` | `-11.5` | `2.4` |
| clamp_top_right | `10.0` | `11.5` | `2.4` |

## Outputs

| Output | Path |
| --- | --- |
| multibody_holder_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_multibody_holder.step` |
| multibody_holder_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_multibody_holder.stl` |
| cmount_socket_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_cmount_socket.step` |
| cmount_socket_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_cmount_socket.stl` |
| sensor_plate_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_sensor_plate.step` |
| sensor_plate_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_sensor_plate.stl` |
| assembly_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_assembly.step` |
| assembly_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_assembly.stl` |
| thread_cutter_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_board_proxy.step` |
| board_proxy_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_rear_alignment.pdf` |
| render_png | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_render.png` |
| rear_alignment_render_png | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4_rear_alignment_render.png` |
| blend | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4.blend` |
| manifest | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4` |
| `design_variant` | `direct C-mount socket to sensor holder plate; five 3.0 mm overlapping pin-header reserved holes placed on the PCB placeholder and joined into one continuous slot; 4 mm AS7343 board-LED clearance channel connected to the optical bore; nominal 25.4 mm female C-mount thread with 25.0 mm pilot/root; half-pitch thread runout cutter for fully developed end threads` |
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
| `sensor_plate_thickness_mm` | `7.0` |
| `sensor_plate_width_y_mm` | `50.0` |
| `sensor_plate_height_z_mm` | `42.0` |
| `sensor_plate_center_z_mm` | `0.0` |
| `estimated_module_board_width_y_mm` | `23.0` |
| `estimated_module_board_height_z_mm` | `15.0` |
| `module_board_size_source` | `User-corrected AS7343 module geometry: PCB is 15 x 23 mm; pin sockets are on the negative-Y short edge; AS7343 package is centered across the 15 mm short edge and 6 mm from the opposite positive-Y short edge.` |
| `board_pocket_clearance_total_mm` | `1.0` |
| `board_pocket_depth_mm` | `2.2` |
| `board_thickness_mm` | `1.6` |
| `as7343_package_width_y_mm` | `3.1` |
| `as7343_package_height_z_mm` | `2.0` |
| `as7343_package_thickness_x_mm` | `1.0` |
| `as7343_window_diameter_mm` | `1.0` |
| `as7343_sensor_offset_y_mm` | `5.5` |
| `as7343_sensor_offset_z_mm` | `0.0` |
| `as7343_led_body_width_z_mm` | `3.3` |
| `as7343_led_body_length_y_mm` | `2.6` |
| `as7343_led_clearance_width_z_mm` | `4.0` |
| `as7343_led_clearance_y_start_mm` | `0.0` |
| `as7343_led_clearance_to_sensor_side_edge_clearance_mm` | `0.5` |
| `pin_header_hole_side` | `negative_y_short_edge_on_pcb` |
| `pin_header_hole_count` | `5` |
| `pin_header_hole_pitch_z_mm` | `2.54` |
| `pin_header_hole_diameter_mm` | `3.0` |
| `pin_header_connected_slot_enabled` | `True` |
| `pin_header_slot_bridge_overlap_mm` | `0.04` |
| `pin_header_slot_note` | `The 3.0 mm pin-header reservation holes are larger than the 2.54 mm pitch, so the row is intentionally joined by a rectangular bridge cutter to clear the material between adjacent holes.` |
| `pin_header_hole_y_offset_inside_board_from_negative_y_edge_mm` | `2.5` |
| `optional_clamp_hole_diameter_mm` | `2.4` |
| `optional_clamp_hole_margin_y_mm` | `4.0` |
| `optional_clamp_hole_margin_z_mm` | `4.0` |
| `source_chip_product` | `https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7343-spectral-sensor` |
| `source_chip_datasheet_local` | `cad/references/as7343-spectral-analysis-module/资料/AS7343_DS001046_6-00.pdf` |
| `source_module_schematic_local` | `cad/references/as7343-spectral-analysis-module/AS7343光谱分析模块原理图.png` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/build_as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4.py
blender --background --python cad/designs/as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4/render_as7343_cmount_spectral_module_holder_direct_socket_led_clearance_25p0_25p4.py
```
