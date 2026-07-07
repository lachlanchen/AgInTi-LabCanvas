# AS7343 C-Mount Spectral Module Holder Direct Socket PCB Pin Holes

New independent CAD design for holding an AS7343 spectral analysis module behind
an OpenHI-print-fit C-mount receiver. This version removes both intermediate
connector shapes: no rectangular bridge/cube and no middle cylinder/tube. The
left C-mount socket directly touches the rear sensor plate at x=`12.0`.
The C-mount socket and the sensor plate are exported as adjacent independent
bodies so Shapr3D can select and edit them separately. Older CAD designs are
not modified. This variant fixes the pin-header placeholder: the five pin holes
are reserved on the PCB placeholder itself, not next to the PCB.

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
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Keep the female thread cutter fully inside the `12 mm` C-mount socket:
  x=`0.2` to
  x=`10.2`.
- Export the C-mount socket and sensor plate as separate adjacent solids; they
  touch at x=`12.0` without a bridge cube, middle cylinder, or
  boolean union.
- Provide a rear module tray for the `15 x 23 mm` board.
- Add a five-hole pin-header clearance row on the PCB placeholder, 2.5 mm
  inside the negative-Y board edge.
- Cut the same five-hole row through the printed holder plate, so the visual
  PCB placeholder and physical clearance match.
- Add four optional M2 clamp/lid holes outside the corrected module footprint.

## C-Mount Size

The printed receiver uses the local OpenHI print-fit size: `24.8 mm` female
root/bore. It is not modeled as a raw `25.4 mm` cylinder. Standard C-mount is
`1-32 UNS` with `0.79375 mm` pitch; this printed design keeps the existing
OpenHI-compatible `0.8 mm` pitch thread convention.

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

PCB pin-header reserved holes:

| Hole | y mm | z mm | holder/PCB cut dia mm |
| --- | ---: | ---: | ---: |
| pcb_pin_header_1 | `-14.5` | `-5.08` | `1.4` |
| pcb_pin_header_2 | `-14.5` | `-2.54` | `1.4` |
| pcb_pin_header_3 | `-14.5` | `0.0` | `1.4` |
| pcb_pin_header_4 | `-14.5` | `2.54` | `1.4` |
| pcb_pin_header_5 | `-14.5` | `5.08` | `1.4` |

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
| multibody_holder_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_multibody_holder.step` |
| multibody_holder_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_multibody_holder.stl` |
| cmount_socket_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_cmount_socket.step` |
| cmount_socket_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_cmount_socket.stl` |
| sensor_plate_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_sensor_plate.step` |
| sensor_plate_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_sensor_plate.stl` |
| assembly_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_assembly.step` |
| assembly_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_assembly.stl` |
| thread_cutter_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_female_thread_cutter.step` |
| thread_cutter_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_female_thread_cutter.stl` |
| board_proxy_step | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_board_proxy.step` |
| board_proxy_stl | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_board_proxy.stl` |
| rear_alignment_svg | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_rear_alignment.svg` |
| rear_alignment_png | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_rear_alignment.png` |
| rear_alignment_pdf | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_rear_alignment.pdf` |
| render_png | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_render.png` |
| rear_alignment_render_png | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes_rear_alignment_render.png` |
| blend | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes.blend` |
| manifest | `cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes` |
| `design_variant` | `direct C-mount socket to sensor holder plate; five pin-header reserved holes placed on the PCB placeholder, not outside the PCB` |
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
| `pin_header_hole_side` | `negative_y_short_edge_on_pcb` |
| `pin_header_hole_count` | `5` |
| `pin_header_hole_pitch_z_mm` | `2.54` |
| `pin_header_hole_diameter_mm` | `1.4` |
| `pin_header_hole_y_offset_inside_board_from_negative_y_edge_mm` | `2.5` |
| `optional_clamp_hole_diameter_mm` | `2.4` |
| `optional_clamp_hole_margin_y_mm` | `4.0` |
| `optional_clamp_hole_margin_z_mm` | `4.0` |
| `source_chip_product` | `https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7343-spectral-sensor` |
| `source_chip_datasheet_local` | `cad/references/as7343-spectral-analysis-module/资料/AS7343_DS001046_6-00.pdf` |
| `source_module_schematic_local` | `cad/references/as7343-spectral-analysis-module/AS7343光谱分析模块原理图.png` |

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/build_as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes.py
blender --background --python cad/designs/as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes/render_as7343_cmount_spectral_module_holder_direct_socket_pcb_pin_holes.py
```
