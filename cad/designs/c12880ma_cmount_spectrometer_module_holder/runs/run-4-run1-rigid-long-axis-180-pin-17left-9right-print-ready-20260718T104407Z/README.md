# C12880MA Run 4: Verified Component-Side Table Orientation

This run starts from the clean run-1 holder geometry, without the later raised
PCB rim. The complete holder and module reference are rigidly rotated around
the PCB long axis so the PCB can be placed on a table with its component side
up. In this authoritative top view, the sensor is up, the socket is down, the
sensor is closer to the left PCB edge, and the C-mount is above the PCB.

The C-mount axis remains centered on the **sensor package**, not on the PCB. A
rear inspection view is mirrored by definition; it is not a second geometry
datum and must not be used to flip individual features.

## Use These Files

- Editable table-orientation holder: `USE_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4_assembly.step`
- Direct-print STEP: `PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4.step`
- Direct-print STL: `PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4.stl`
- Direct-print 3MF: `PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4.3mf`
- Exact print preview: `PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4_render.png`
- Table-orientation assembly preview: `c12880ma_cmount_holder_42x42_table_orientation_run4_assembly_render.png`
- Original run-1 optical-axis coordinates: `c12880ma_cmount_holder_42x42_table_orientation_run4_original_axis_design.step`

`USE_THIS` places the PCB back face at table `Z=0`. The sensor, holder plate,
and C-mount rise above it. `PRINT_THIS` is the same physical part rotated so the
34 mm C-mount front face rests on the build plate; this is the proven
support-minimizing manufacturing orientation.

## Alignment

- Holder plate: `42 x 42 x 5 mm`.
- C-mount OD: `34 mm`.
- Module PCB: `38.3 x 22.8 x 1.5 mm`.
- Measured package fit envelope: `20.5 x 13 x 15 mm`.
- Printed package opening: `20.9 x 13.4 mm` with rounded corners.
- Measured mounting-hole spacing: `33.6 mm`.
- Left hole to sensor axis: `13.2 mm`.
- Right hole to sensor axis: `20.4 mm`.
- Two blind `1.6 mm` pilots are intended for tapping M2 x 0.4 in printed
  plastic. Measure the physical PCB hole diameter and choose screw heads before
  committing a production batch.

The plate center is shifted `+3.6 mm` along the PCB long direction. That makes
the two mounting holes symmetric at `-16.8/+16.8 mm` about the plate center,
while the optical axis remains at the measured sensor center.

The source board dimensions are interpreted only in the component-side view:
sensor at the top, socket at the bottom. The `38.3/38.4 mm` dimension is the
long PCB edge. The sensor package is `3.8 mm` from the top edge and about
`6.2 mm` from the bottom edge. The rear view is the mirror of this view.

## 6P Socket Pin-Tail Clearance

The connector housing is not used as the clearance datum. The six solder tails
that protrude from the PCB into the holder surface are cleared directly on the
PCB footprint. Six `3.0 mm` holes at `2.54 mm` pitch overlap and are joined by a
bridge cut, forming one continuous slot with no thin material left between pins.

| Pin | Y mm from sensor axis | Z mm from sensor axis | relief diameter mm |
| ---: | ---: | ---: | ---: |
| 1 | `1.25` | `-9.3` | `3.0` |
| 2 | `3.79` | `-9.3` | `3.0` |
| 3 | `6.33` | `-9.3` | `3.0` |
| 4 | `8.87` | `-9.3` | `3.0` |
| 5 | `11.41` | `-9.3` | `3.0` |
| 6 | `13.95` | `-9.3` | `3.0` |

With sensor up and socket down, the first pin center is `16.8 mm` from the
component-view left PCB edge and the last pin center is `8.8 mm` from the right
edge. These fit the measured `17/9 mm` values within the requested `1 mm`
tolerance. The whole slot is built before the rigid table transform, so it
cannot drift or be mirrored independently from the holder.

## C-Mount Thread

This printable receiver uses a `25.0 mm` pilot/root and a `25.4 mm` nominal
internal groove maximum, with the locally proven `0.8 mm` triangular pitch.
The female cutter extends a half pitch beyond both nominal ends before boolean
subtraction, so the thread reaches the end cleanly without external overflow.
The threaded section is only `5 mm` long. The measured 15 mm package begins
`0.8 mm` behind the nominal thread end, preventing the package from occupying
the active mating-thread region.

## Source Evidence

- User measurement sketch: `cad/references/c12880ma-spectrometer-module/user-measured-dimensions.jpg`
- Vendor board image: `cad/references/c12880ma-spectrometer-module/vendor-board-dimensions.jpg`
- Hamamatsu datasheet: `cad/references/c12880ma-spectrometer-module/hamamatsu-c12880ma-datasheet.pdf`
- Vendor archive snapshot: `cad/references/c12880ma-spectrometer-module`

The bundled vendor `CCD3D.stp` contains a much larger assembly and TCD1304
labels, so it is retained as reference evidence but is not used as the exact
38.3 x 22.8 module geometry.

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/build_run4_c12880ma_cmount_holder.py
blender --background --python cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/render_run4_c12880ma_cmount_holder.py
```

## Validation

```json
{
  "geometry": {
    "sensor_axis_is_cmount_axis": [
      0.0,
      0.0
    ],
    "authoritative_view": "component side up; sensor up; socket down",
    "rear_view_is_mirrored_for_inspection_only": true,
    "sensor_is_up_and_socket_is_down_in_component_view": true,
    "sensor_is_closer_to_left_pcb_edge": true,
    "six_pin_first_center_from_left_edge_mm": 16.8,
    "six_pin_last_center_from_right_edge_mm": 8.8,
    "six_pin_left_margin_within_1mm": true,
    "six_pin_right_margin_within_1mm": true,
    "six_pin_radial_clearance_mm": 1.0,
    "table_pcb_back_face_z_mm": -0.0,
    "table_pcb_component_face_z_mm": 1.5,
    "table_sensor_z_range_mm": [
      1.5,
      17.0
    ],
    "table_cmount_z_range_mm": [
      6.5,
      22.5
    ],
    "pcb_back_face_is_on_table": true,
    "sensor_and_cmount_are_above_pcb": true,
    "rigid_rotation_preserves_holder_volume": true,
    "hole_spacing_is_33p6_mm": true,
    "holes_are_symmetric_about_plate_center": true,
    "pcb_fits_42x42_plate": true,
    "socket_od_fits_plate": true,
    "rectangular_package_clearance_fits_25mm_chamber": true,
    "thread_to_sensor_front_gap_mm": 0.8,
    "thread_does_not_reach_sensor_package": true,
    "six_pin_relief_is_on_pcb_footprint": true,
    "plate_bounds_y_mm": [
      -17.4,
      24.6
    ],
    "plate_bounds_z_mm": [
      -21.0,
      21.0
    ],
    "pcb_bounds_yz_mm": {
      "y_min": -15.55,
      "y_max": 22.75,
      "z_min": -12.5,
      "z_max": 10.3
    }
  },
  "print_step": {
    "exists": true,
    "bytes": 467292,
    "solid_count": 1,
    "all_brep_valid": true,
    "bbox_mm": [
      42.0,
      42.0,
      21.0
    ]
  },
  "print_stl": {
    "exists": true,
    "bytes": 473984,
    "watertight": true,
    "body_count": 1,
    "extents_mm": [
      42.0,
      42.0,
      21.0
    ],
    "face_count": 9478
  },
  "print_3mf": {
    "exists": true,
    "bytes": 118778,
    "zip_valid": true,
    "members": [
      "3D/3dmodel.model",
      "[Content_Types].xml",
      "_rels/.rels"
    ]
  },
  "use_this_table_step": {
    "exists": true,
    "bytes": 467781,
    "solid_count": 1,
    "all_brep_valid": true,
    "bbox_mm": [
      42.0,
      42.0,
      21.0
    ]
  },
  "table_orientation_stl": {
    "exists": true,
    "bytes": 473984,
    "watertight": true,
    "body_count": 1,
    "extents_mm": [
      42.0,
      42.0,
      21.0
    ],
    "face_count": 9478
  },
  "original_axis_design_step": {
    "exists": true,
    "bytes": 468984,
    "solid_count": 1,
    "all_brep_valid": true,
    "bbox_mm": [
      21.0,
      42.0,
      42.0
    ]
  },
  "smooth_editable_step": {
    "exists": true,
    "bytes": 130052,
    "solid_count": 1,
    "all_brep_valid": true,
    "bbox_mm": [
      42.0,
      42.0,
      21.0
    ]
  },
  "decoupled_step": {
    "exists": true,
    "bytes": 454129,
    "solid_count": 2,
    "all_brep_valid": true,
    "bbox_mm": [
      42.0,
      42.0,
      21.0
    ]
  },
  "assembly_with_proxies_step": {
    "exists": true,
    "bytes": 552722,
    "solid_count": 10,
    "all_brep_valid": true,
    "bbox_mm": [
      42.0,
      42.0,
      22.5
    ]
  }
}
```

## Outputs

| Artifact | Path |
| --- | --- |
| print_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4.step` |
| print_stl | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4.stl` |
| print_3mf | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4.3mf` |
| use_this_assembly_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/USE_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4_assembly.step` |
| table_orientation_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_table_orientation.step` |
| table_orientation_stl | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_table_orientation.stl` |
| original_axis_design_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_original_axis_design.step` |
| smooth_editable_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_smooth_editable.step` |
| decoupled_socket_and_plate_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_decoupled_socket_and_plate.step` |
| cmount_socket_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_cmount_socket.step` |
| holder_plate_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_holder_plate.step` |
| board_proxy_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_board_proxy.step` |
| sensor_package_proxy_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_sensor_package_proxy.step` |
| six_pin_tail_proxy_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_six_pin_tail_proxy.step` |
| female_thread_cutter_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_female_thread_cutter.step` |
| assembly_with_proxies_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_assembly_with_proxies.step` |
| component_side_alignment_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_component_side_alignment.png` |
| component_side_alignment_pdf | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_component_side_alignment.pdf` |
| component_side_alignment_svg | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_component_side_alignment.svg` |
| table_side_section_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_table_side_section.png` |
| table_side_section_pdf | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_table_side_section.pdf` |
| table_side_section_svg | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/c12880ma_cmount_holder_42x42_table_orientation_run4_table_side_section.svg` |
| print_render_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/PRINT_THIS_c12880ma_cmount_holder_42x42_table_orientation_run4_render.png` |
| assembly_render_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/c12880ma_cmount_holder_42x42_table_orientation_run4_assembly_render.png` |
| exploded_alignment_render_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/c12880ma_cmount_holder_42x42_table_orientation_run4_exploded_alignment_render.png` |
| manifest | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-4-run1-rigid-long-axis-180-pin-17left-9right-print-ready-20260718T104407Z/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `c12880ma_cmount_holder_42x42_table_orientation_run4` |
| `units` | `mm` |
| `design_date` | `2026-07-18` |
| `baseline_run` | `run-1-42x42-centered-sensor-6p-pin-clearance-print-ready-20260718T064716Z` |
| `orientation_contract` | `The complete run-1 holder and module reference are rotated together by 180 degrees about the PCB long axis relative to the old direct-print view. In the authoritative table view, the PCB underside is at Z=0, the component side faces up, the sensor is up, the socket is down, and the C-mount is above the PCB. Rear inspection is a mirrored view and never changes geometry.` |
| `holder_plate_size_y_mm` | `42.0` |
| `holder_plate_size_z_mm` | `42.0` |
| `holder_plate_thickness_x_mm` | `5.0` |
| `holder_plate_corner_radius_mm` | `1.5` |
| `cmount_socket_outer_diameter_mm` | `34.0` |
| `cmount_socket_length_x_mm` | `16.0` |
| `cmount_female_pilot_root_diameter_mm` | `25.0` |
| `cmount_female_thread_nominal_major_diameter_mm` | `25.4` |
| `cmount_thread_pitch_mm` | `0.8` |
| `cmount_thread_tooth_radial_height_mm` | `0.2` |
| `cmount_thread_tooth_base_mm` | `0.8` |
| `cmount_thread_start_x_mm` | `0.2` |
| `cmount_thread_length_x_mm` | `5.0` |
| `cmount_thread_half_pitch_runout_each_end_mm` | `0.4` |
| `pcb_length_y_mm` | `38.3` |
| `pcb_width_z_mm` | `22.8` |
| `pcb_thickness_x_mm` | `1.5` |
| `pcb_mount_hole_spacing_y_mm` | `33.6` |
| `left_mount_hole_to_sensor_axis_y_mm` | `13.2` |
| `pcb_left_edge_to_sensor_axis_y_mm` | `15.55` |
| `pcb_right_edge_from_sensor_axis_y_mm` | `22.75` |
| `pcb_top_edge_from_sensor_axis_z_mm` | `10.3` |
| `pcb_bottom_edge_from_sensor_axis_z_mm` | `12.5` |
| `pcb_center_y_from_sensor_axis_mm` | `3.6` |
| `pcb_center_z_from_sensor_axis_mm` | `-1.1` |
| `holder_plate_center_y_from_sensor_axis_mm` | `3.6` |
| `holder_plate_center_z_from_sensor_axis_mm` | `0.0` |
| `left_mount_hole_y_mm` | `-13.2` |
| `right_mount_hole_y_mm` | `20.4` |
| `mount_hole_z_mm` | `0.0` |
| `m2_printed_tap_pilot_diameter_mm` | `1.6` |
| `m2_printed_tap_pilot_depth_mm` | `4.5` |
| `pcb_proxy_mount_hole_diameter_mm` | `2.4` |
| `sensor_package_measured_max_y_mm` | `20.5` |
| `sensor_package_measured_max_z_mm` | `13.0` |
| `sensor_package_height_from_pcb_x_mm` | `15.0` |
| `sensor_package_clearance_y_mm` | `20.9` |
| `sensor_package_clearance_z_mm` | `13.4` |
| `sensor_package_clearance_corner_radius_mm` | `1.5` |
| `sensor_window_reference_diameter_mm` | `3.2` |
| `six_pin_count` | `6` |
| `six_pin_pitch_y_mm` | `2.54` |
| `six_pin_row_center_y_mm` | `7.6` |
| `six_pin_row_center_z_mm` | `-9.3` |
| `six_pin_left_pcb_edge_margin_target_mm` | `17.0` |
| `six_pin_right_pcb_edge_margin_target_mm` | `9.0` |
| `six_pin_end_margin_tolerance_mm` | `1.0` |
| `six_pin_tail_relief_diameter_mm` | `3.0` |
| `six_pin_tail_relief_bridge_overlap_mm` | `0.08` |
| `six_pin_tail_reference_diameter_mm` | `1.0` |
| `six_pin_row_position_note` | `With the PCB component side up, sensor up, and socket down, the pin row has about 17 mm from the left PCB edge to the first pin center and 9 mm from the last pin center to the right edge. A 7.6 mm row center gives 16.8 and 8.8 mm with six pins at 2.54 mm pitch, inside the requested 1 mm tolerance.` |
| `print_orientation` | `Socket front face on the build plate, C-mount axis vertical. This keeps the internal thread vertical and requires no generated support geometry. It is a manufacturing rotation of the same table-orientation part.` |
| `source_priority` | `User caliper measurements and the exact vendor board image control module fit and mounting-hole placement; the official Hamamatsu datasheet controls the bare C12880MA package reference only.` |
