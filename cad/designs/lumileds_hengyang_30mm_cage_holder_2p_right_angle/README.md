# Lumileds Hengyang 30 mm Cage Holder With 2P Right-Angle Header Clearance

This is a new independent sibling of `cad/designs/lumileds_hengyang_30mm_cage_holder`.
The old design is not edited. This version keeps the same Hengyang-style 30 mm
cage interface and adds explicit clearance for a 2P right-angle pin header,
front-side pin/solder protrusions, a female Dupont plug, and wire exit.

## Design Intent

- Keep the GT-090101/Hengyang-compatible four-rod 30 mm cage interface.
- Keep the Lumileds round PCB rear pocket and M2-style PCB mounting holes.
- Add two 2.54 mm pitch pin-relief holes near the PCB edge.
- Add `+0.4 mm` diameter print clearance to the pin holes: nominal `2.0 mm`
  becomes `2.4 mm`.
- Add front/LED-side popup relief so solder or header pin tips do not collide
  with the holder face.
- Add a larger rear/right-side open pocket for the 90-degree header body,
  female Dupont 2P plug, and wire bend.
- Use a `2.6 mm` M3 pilot hole, not a loose
  3.0 mm M3 clearance hole.

## OpenHI Reference Used

`cad/extracted/OpenHI_STEP/LED holder.step` was imported with CadQuery. It measures
about `30.0 x 11.6 x 30.0 mm` and has two solids: a `10 mm` body and a `1.6 mm`
LED-board layer. Cylindrical face inspection shows four about `1.8 mm` mount
holes and two about `2.0 mm` pin holes separated by about `2.54 mm`. This new
holder applies the same pin-hole idea but adds the requested `0.4 mm` diameter
clearance for printing.

## Outputs

| Output | Path |
| --- | --- |
| holder STEP | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle.step` |
| holder STL | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle.stl` |
| assembly STEP | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle_assembly.step` |
| assembly STL | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle_assembly.stl` |
| dimension sketch SVG | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle_dimension_sketch.svg` |
| dimension sketch PNG | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle_dimension_sketch.png` |
| dimension sketch PDF | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle_dimension_sketch.pdf` |
| rear Dupont/header render PNG | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle_rear_dupont_render.png` |
| front pin-relief render PNG | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle_front_pin_relief_render.png` |
| Blender inspection scene | `cad/designs/lumileds_hengyang_30mm_cage_holder_2p_right_angle/artifacts/lumileds_hengyang_30mm_cage_holder_2p_right_angle.blend` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `lumileds_hengyang_30mm_cage_holder_2p_right_angle` |
| `reference_family` | `Hengyang Optics 30 mm cage components` |
| `primary_reference` | `GT-090101` |
| `reference_folder` | `cad/references/hengyang-optics` |
| `openhi_led_holder_reference` | `cad/extracted/OpenHI_STEP/LED holder.step` |
| `openhi_led_holder_observation` | `Imported OpenHI LED holder is about 30.0 x 11.6 x 30.0 mm with a 10 mm main body, a 1.6 mm LED board layer, four about 1.8 mm mount holes, and two about 2.0 mm pin holes on 2.54 mm pitch.` |
| `body_width_mm` | `40.0` |
| `body_height_mm` | `41.5` |
| `body_thickness_mm` | `11.0` |
| `front_lip_depth_mm` | `1.2` |
| `front_lip_diameter_mm` | `17.0` |
| `corner_radius_mm` | `2.0` |
| `cage_rod_pitch_mm` | `30.0` |
| `cage_rod_clearance_diameter_mm` | `6.35` |
| `rod_boss_diameter_mm` | `9.6` |
| `light_aperture_diameter_mm` | `9.6` |
| `pcb_outer_diameter_mm` | `24.0` |
| `pcb_pocket_diameter_mm` | `24.7` |
| `pcb_pocket_depth_mm` | `2.05` |
| `pcb_thickness_mm` | `1.6` |
| `pcb_mount_pattern_mm` | `12.0` |
| `pcb_mount_hole_diameter_mm` | `2.35` |
| `pcb_mount_counterbore_diameter_mm` | `4.8` |
| `pcb_mount_counterbore_depth_mm` | `2.1` |
| `right_angle_header_pin_x_mm` | `10.2` |
| `right_angle_header_pin_pair_center_y_mm` | `-1.25` |
| `right_angle_header_pin_pitch_mm` | `2.54` |
| `right_angle_header_nominal_pin_hole_diameter_mm` | `2.0` |
| `right_angle_header_pin_hole_diameter_add_mm` | `0.4` |
| `right_angle_header_pin_relief_diameter_mm` | `2.4` |
| `right_angle_header_front_popup_relief_diameter_mm` | `3.2` |
| `right_angle_header_front_popup_relief_depth_mm` | `2.2` |
| `right_angle_header_body_clearance_reach_mm` | `17.5` |
| `right_angle_header_body_clearance_width_mm` | `8.8` |
| `right_angle_header_body_clearance_height_mm` | `6.8` |
| `dupont_plug_clearance_reach_mm` | `24.0` |
| `dupont_plug_clearance_width_mm` | `10.0` |
| `dupont_plug_clearance_height_mm` | `8.8` |
| `dupont_wire_exit_channel_width_mm` | `12.0` |
| `dupont_wire_exit_channel_height_mm` | `5.4` |
| `m3_pilot_hole_diameter_mm` | `2.6` |
| `m3_pilot_depth_mm` | `6.0` |
| `m3_pilot_note` | `M3 pilot/tapping hole, intentionally smaller than 3.0 mm; tune after print or tap/heat-set.` |
| `print_clearance_note` | `Pin relief holes use nominal 2.0 mm plus 0.4 mm diameter clearance, following the OpenHI LED holder pattern.` |

## Notes

- The purple rectangle in the dimension sketch is the right-side Dupont/header
  clearance pocket in top view.
- Red circles are the two pin-relief holes and the dashed red circles are the
  larger front-side popup relief pockets.
- The STEP/STL `holder` files contain only the printable holder. The `assembly`
  files include PCB/header/Dupont/wire proxies for fit checking.
- Print one prototype and tune pin-hole/header pocket clearance from that first
  fit test before machining or ordering.
