# Lumileds PCB-Aligned Sink Cage Holder

This is a sibling of `cad/designs/lumileds_pcb_aligned_simple_cage_holder`.
It keeps the same clean monolithic holder geometry, adds a rear PCB sink, uses
smaller PCB fixation pilot holes for self-tapping screws, opens the pin-header
relief into a connected slot, and provides a rotated direct-print layout with
four small removable ears.

## PCB Geometry Used

- Source PCB: `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb`
- PCB outer diameter: `24.0 mm`
- PCB thickness used for sink depth: `1.6 mm`
- LED center: `(0.0, 0.0) mm from LXCL_MN08_4000`
- Mount holes: `(+/-6, +/-6) mm`, opened to `1.8 mm`
- Header relief: `(10, 1)` and `(10, -1.54) mm`, opened as a connected `3.0 mm` two-hole slot

## Design Rule

Use the PCB as the source of truth. The KiCad board center is translated to the
holder origin. The rear circular sink is concentric with the 24 mm PCB outline,
opened to `24.4 mm`, and cut `1.6 mm` deep.

The PCB sink stays concentric. The four fixation holes are intentionally smaller
than the PCB drill size so roughly 2 mm self-tapping screws can bite into the
printed plastic. The header relief is intentionally larger and connected so pin
overflow does not collide with the holder.

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder.step` |
| holder_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder.stl` |
| print_layout_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_print_layout.step` |
| print_layout_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_print_layout.stl` |
| print_layout_3mf | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_print_layout.3mf` |
| pcb_proxy_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_pcb_proxy.step` |
| pcb_proxy_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_pcb_proxy.stl` |
| assembly_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_assembly.step` |
| assembly_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_assembly.stl` |
| top_alignment_svg | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_top_alignment.svg` |
| top_alignment_png | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_top_alignment.png` |
| pcb_geometry_json | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_pcb_geometry.json` |
| use_this_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/USE_THIS_lumileds_pcb_aligned_sink_cage_holder.step` |
| print_this_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/PRINT_THIS_lumileds_pcb_aligned_sink_cage_holder.step` |
| print_this_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/PRINT_THIS_lumileds_pcb_aligned_sink_cage_holder.stl` |
| print_this_3mf | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/PRINT_THIS_lumileds_pcb_aligned_sink_cage_holder.3mf` |
| manifest | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/manifest.json` |
| nutstore_print_ready_folder | `/home/lachlan/Nutstore Files/Projects/LabCanvas/lumileds_pcb_aligned_sink_cage_holder/pin-header-3mm-relief-print-ready` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `lumileds_pcb_aligned_sink_cage_holder` |
| `source_pcb` | `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb` |
| `base_design` | `self-contained rebuild of cad/designs/lumileds_pcb_aligned_simple_cage_holder geometry` |
| `body_width_mm` | `42.0` |
| `body_height_mm` | `42.0` |
| `body_thickness_mm` | `8.0` |
| `edge_fillet_mm` | `0.8` |
| `cage_rod_pitch_mm` | `30.0` |
| `cage_rod_clearance_diameter_mm` | `6.4` |
| `pcb_outer_diameter_mm` | `24.0` |
| `pcb_sink_diameter_mm` | `24.4` |
| `pcb_thickness_mm` | `1.6` |
| `pcb_sink_depth_mm` | `1.6` |
| `pcb_mount_clearance_diameter_mm` | `1.8` |
| `pcb_mount_hole_note` | `Four PCB fixation holes are 1.8 mm pilot holes for roughly 2 mm self-tapping screws in printed plastic.` |
| `header_pin_relief_diameter_mm` | `3.0` |
| `header_pin_relief_style` | `two overlapping 3.0 mm holes plus a rectangular bridge, forming one fully cleared capsule slot for pin overflow` |
| `led_aperture_diameter_mm` | `10.0` |
| `print_ears_enabled` | `True` |
| `print_ear_thickness_mm` | `1.0` |
| `print_ear_side_contact_mm` | `5.0` |
| `print_ear_breakaway_overlap_mm` | `0.5` |
| `print_ear_side_reach_mm` | `10.0` |
| `print_ear_side_width_mm` | `5.0` |
| `print_ear_diagonal_reach_mm` | `12.0` |
| `print_ear_tail_width_mm` | `10.0` |
| `print_orientation` | `PRINT_THIS files are rotated so the PCB sink faces upward; four 1.0 mm sacrificial ears sit on the build-plate side.` |
| `coordinate_rule` | `PCB center is translated to holder origin. The rear PCB sink is concentric with the KiCad board outline.` |

## Notes

- Use the root `PRINT_THIS_*` files for printing. They are rotated so the PCB
  sink faces upward and include four small removable ears.
- Use the holder-only STEP/STL for clean CAD editing. The assembly STEP/STL
  includes PCB, LED, header, and cage-rod proxies only for fit checking.
- If the PCB is too tight, change `pcb_sink_diameter_mm`; keep the mount-hole
  coordinates unchanged.
- If the self-tapping screws are too tight, increase
  `pcb_mount_clearance_diameter_mm` in small steps such as `0.1 mm`.
