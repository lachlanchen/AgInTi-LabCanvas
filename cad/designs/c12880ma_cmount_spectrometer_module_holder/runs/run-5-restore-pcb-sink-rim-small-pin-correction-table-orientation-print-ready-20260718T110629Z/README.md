# C12880MA 42 x 42 C-Mount Module Holder - Mating Orientation

This is the fifth print-ready run for the measured C12880MA spectrometer module.
The C-mount axis is centered on the **sensor package**, not on the PCB. The PCB
is deliberately offset because the sensor sits `15.55 mm` from the left board
edge while the `38.3 mm` board center is `19.15 mm` from that edge.

The supplied sketch and photos are used only to interpret the measured values.
Their top view shows the sensor at the PCB top-left and the pin row below it.
Because that component face mates against the holder, the PCB short-direction
offset and pin-row Z coordinate are inverted in the holder cutouts. No new
module detail, connector housing, or extra holder feature is introduced.

## Use These Files

- Editable design orientation: `USE_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5_assembly.step`
- Direct-print STEP: `PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5.step`
- Direct-print STL: `PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5.stl`
- Direct-print 3MF: `PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5.3mf`
- Exact print preview: `PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5_render.png`
- Partially exploded board/sensor fit preview: `c12880ma_cmount_holder_42x42_mating_orientation_run5_assembly_render.png`

The print files place the 34 mm C-mount front face on the build plate and make
the optical axis vertical. The editable STEP keeps the optical axis along X.

## Alignment

- Structural plate: `42 x 42 x 5 mm`.
- Rear rim: `2 mm` added only outside a `38.7 x 23.2 mm` PCB pocket.
- Installed `1.5 mm` PCB is sunk `0.5 mm` below the surrounding rim.
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

The plate and pocket center are shifted `+3.6 mm` along the PCB long direction. That makes
the two mounting holes symmetric at `-16.8/+16.8 mm` about the plate center,
while the optical axis remains at the measured sensor center.

## 6P Socket Pin-Tail Clearance

The connector housing is not used as the clearance datum. The six solder tails
that protrude from the PCB into the holder surface are cleared directly on the
PCB footprint. Six `3.0 mm` holes at `2.54 mm` pitch overlap and are joined by a
bridge cut, forming one continuous slot with no thin material left between pins.

| Pin | Y mm from sensor axis | Z mm from sensor axis | relief diameter mm |
| ---: | ---: | ---: | ---: |
| 1 | `-6.75` | `9.3` | `3.0` |
| 2 | `-4.21` | `9.3` | `3.0` |
| 3 | `-1.67` | `9.3` | `3.0` |
| 4 | `0.87` | `9.3` | `3.0` |
| 5 | `3.41` | `9.3` | `3.0` |
| 6 | `5.95` | `9.3` | `3.0` |

The source top view has the row below the sensor at
Z=`-9.3 mm`; the mating
holder relief is therefore at Z=`9.3 mm`.
Its refined Y center is `-0.4 mm`, which gives
approximately `8.8 mm` from the left PCB edge to the first pin center and
`16.8 mm` from the last pin center to the right PCB edge. The connected `3.0 mm`
relief gives `1.0 mm` radial clearance around the `1.0 mm` reference pin.

## PCB Sink Construction

The PCB seating surface stays at X=`21.0 mm`, exactly as in run 1.
Instead of cutting 2 mm out of the 5 mm structural plate, this run adds a 2 mm
rim only outside the board footprint. The rim rear face is X=`23.0 mm`;
the installed PCB rear face is X=`22.5 mm`.
This leaves the PCB `0.5 mm` below the rim while preserving the sensor front at
X=`6.0 mm`, the
M2 pilot depth, the 6P pin-tail relief, and the 0.8 mm thread/package gap.

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
- User front photo: `cad/references/c12880ma-spectrometer-module/user-module-front-elevation-20260718.jpg`
- User top photo: `cad/references/c12880ma-spectrometer-module/user-module-top-view-20260718.jpg`
- Hamamatsu datasheet: `cad/references/c12880ma-spectrometer-module/hamamatsu-c12880ma-datasheet.pdf`
- Vendor archive snapshot: `cad/references/c12880ma-spectrometer-module`

The bundled vendor `CCD3D.stp` contains a much larger assembly and TCD1304
labels, so it is retained as reference evidence but is not used as the exact
38.3 x 22.8 module geometry.

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/build_run5_c12880ma_cmount_holder.py
blender --background --python cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/render_run5_c12880ma_cmount_holder.py
```

## Validation

```json
{
  "geometry": {
    "sensor_axis_is_cmount_axis": [
      0.0,
      0.0
    ],
    "source_view_is_sensor_top_left_and_pin_row_below": true,
    "holder_view_is_source_long_edge_flip": true,
    "holder_side_pcb_center_z_mm": 1.1,
    "holder_side_six_pin_row_z_mm": 9.3,
    "sensor_is_closer_to_left_edge": true,
    "six_pin_row_center_refined_y_mm": -0.4,
    "six_pin_y_adjustment_from_run1_is_only_0p4_mm": true,
    "six_pin_first_center_from_left_edge_mm": 8.8,
    "six_pin_last_center_from_right_edge_mm": 16.8,
    "six_pin_radial_clearance_mm": 1.0,
    "hole_spacing_is_33p6_mm": true,
    "holes_are_symmetric_about_plate_center": true,
    "pcb_fits_42x42_plate": true,
    "socket_od_fits_plate": true,
    "rectangular_package_clearance_fits_25mm_chamber": true,
    "thread_to_sensor_front_gap_mm": 0.8,
    "thread_does_not_reach_sensor_package": true,
    "pcb_seating_plane_unchanged_from_run1_mm": 21.0,
    "rim_rear_plane_mm": 23.0,
    "installed_pcb_top_plane_mm": 22.5,
    "installed_pcb_is_sunk_below_rim_mm": 0.5,
    "pcb_sink_is_exactly_0p5_mm_after_install": true,
    "sensor_front_unchanged_at_x_mm": 6.0,
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
      "z_min": -10.3,
      "z_max": 12.5
    }
  },
  "print_step": {
    "exists": true,
    "bytes": 500004,
    "solid_count": 1,
    "all_brep_valid": true,
    "bbox_mm": [
      42.0,
      42.0,
      23.0
    ]
  },
  "print_stl": {
    "exists": true,
    "bytes": 500084,
    "watertight": true,
    "body_count": 1,
    "extents_mm": [
      42.0,
      42.0,
      23.0
    ],
    "face_count": 10000
  },
  "print_3mf": {
    "exists": true,
    "bytes": 121847,
    "zip_valid": true,
    "members": [
      "3D/3dmodel.model",
      "[Content_Types].xml",
      "_rels/.rels"
    ]
  },
  "use_this_design_step": {
    "exists": true,
    "bytes": 501617,
    "solid_count": 1,
    "all_brep_valid": true,
    "bbox_mm": [
      23.0,
      42.0,
      42.0
    ]
  },
  "smooth_editable_step": {
    "exists": true,
    "bytes": 165649,
    "solid_count": 1,
    "all_brep_valid": true,
    "bbox_mm": [
      23.0,
      42.0,
      42.0
    ]
  },
  "decoupled_step": {
    "exists": true,
    "bytes": 484472,
    "solid_count": 2,
    "all_brep_valid": true,
    "bbox_mm": [
      23.0,
      42.0,
      42.0
    ]
  },
  "assembly_with_proxies_step": {
    "exists": true,
    "bytes": 587420,
    "solid_count": 11,
    "all_brep_valid": true,
    "bbox_mm": [
      28.0,
      42.0,
      42.0
    ]
  }
}
```

## Outputs

| Artifact | Path |
| --- | --- |
| print_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5.step` |
| print_stl | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5.stl` |
| print_3mf | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5.3mf` |
| use_this_assembly_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/USE_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5_assembly.step` |
| design_orientation_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_design_orientation.step` |
| smooth_editable_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_smooth_editable.step` |
| decoupled_socket_and_plate_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_decoupled_socket_and_plate.step` |
| cmount_socket_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_cmount_socket.step` |
| holder_plate_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_holder_plate.step` |
| board_proxy_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_board_proxy.step` |
| sensor_package_proxy_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_sensor_package_proxy.step` |
| six_pin_tail_proxy_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_six_pin_tail_proxy.step` |
| female_thread_cutter_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_female_thread_cutter.step` |
| assembly_with_proxies_step | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_assembly_with_proxies.step` |
| holder_side_alignment_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_holder_side_alignment.png` |
| holder_side_alignment_pdf | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_holder_side_alignment.pdf` |
| holder_side_alignment_svg | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_holder_side_alignment.svg` |
| side_section_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_side_section.png` |
| side_section_pdf | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_side_section.pdf` |
| side_section_svg | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/c12880ma_cmount_holder_42x42_mating_orientation_run5_side_section.svg` |
| print_render_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/PRINT_THIS_c12880ma_cmount_holder_42x42_mating_orientation_run5_render.png` |
| assembly_render_png | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/c12880ma_cmount_holder_42x42_mating_orientation_run5_assembly_render.png` |
| manifest | `cad/designs/c12880ma_cmount_spectrometer_module_holder/runs/run-5-restore-pcb-sink-rim-small-pin-correction-table-orientation-print-ready-20260718T110629Z/artifacts/manifest.json` |

## Parameters

| Parameter | Value |
| --- | --- |
| `name` | `c12880ma_cmount_holder_42x42_mating_orientation_run5` |
| `units` | `mm` |
| `design_date` | `2026-07-18` |
| `baseline_run` | `run-3-component-side-orientation-pin-row-refined-print-ready-20260718T101655Z` |
| `holder_plate_size_y_mm` | `42.0` |
| `holder_plate_size_z_mm` | `42.0` |
| `holder_plate_thickness_x_mm` | `5.0` |
| `rear_rim_height_x_mm` | `2.0` |
| `pcb_pocket_clearance_total_y_mm` | `0.4` |
| `pcb_pocket_clearance_total_z_mm` | `0.4` |
| `installed_pcb_recess_below_rim_mm` | `0.5` |
| `orientation_correction` | `The supplied values describe the component-side top view: sensor at the PCB top-left and the six-pin row below. Because that face mates against the holder, only the short-direction coordinates are inverted for the holder-side cutouts. The C-mount, plate, sink, thread, dimensions, and long-direction coordinates remain unchanged.` |
| `pcb_sink_construction_note` | `The original 5 mm plate and PCB seating datum are unchanged. A 2 mm rear rim is added only outside a 38.7 x 23.2 mm PCB pocket, so the 1.5 mm PCB finishes 0.5 mm below the surrounding rim without moving the sensor toward the C-mount thread.` |
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
| `source_component_view_pcb_top_edge_from_sensor_axis_z_mm` | `10.3` |
| `source_component_view_pcb_bottom_edge_from_sensor_axis_z_mm` | `12.5` |
| `source_component_view_pcb_center_z_from_sensor_axis_mm` | `-1.1` |
| `source_component_view_six_pin_row_center_z_mm` | `-9.3` |
| `pcb_top_edge_from_sensor_axis_z_mm` | `12.5` |
| `pcb_bottom_edge_from_sensor_axis_z_mm` | `10.3` |
| `pcb_center_y_from_sensor_axis_mm` | `3.6` |
| `pcb_center_z_from_sensor_axis_mm` | `1.1` |
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
| `six_pin_row_center_y_mm` | `-0.4` |
| `six_pin_row_center_z_mm` | `9.3` |
| `six_pin_left_pcb_edge_margin_measured_mm` | `9.0` |
| `six_pin_right_pcb_edge_margin_measured_mm` | `17.0` |
| `six_pin_tail_relief_diameter_mm` | `3.0` |
| `six_pin_tail_relief_bridge_overlap_mm` | `0.08` |
| `six_pin_tail_reference_diameter_mm` | `1.0` |
| `six_pin_row_position_note` | `The source top view has the row below the sensor at Z=-9.3 mm. Its mating holder relief is therefore at Z=+9.3 mm. The run-1 long-direction position was already nearly correct: Y changes only from 0.0 to -0.4 mm, giving 8.8 and 16.8 mm end margins. The 3.0 mm relief around a roughly 1.0 mm pin provides 1.0 mm radial clearance.` |
| `print_orientation` | `Socket front face on the build plate, C-mount axis vertical. This keeps the internal thread vertical and requires no generated support geometry.` |
| `source_priority` | `User caliper measurements and the exact vendor board image control module fit and mounting-hole placement; the official Hamamatsu datasheet controls the bare C12880MA package reference only.` |
