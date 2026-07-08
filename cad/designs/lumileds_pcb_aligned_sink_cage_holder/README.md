# Lumileds PCB-Aligned Sink Cage Holder

This is a sibling of `cad/designs/lumileds_pcb_aligned_simple_cage_holder`.
It keeps the same clean monolithic holder geometry and adds only a rear PCB
sink.

## PCB Geometry Used

- Source PCB: `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb`
- PCB outer diameter: `24.0 mm`
- PCB thickness used for sink depth: `1.6 mm`
- LED center: `(0.0, 0.0) mm from LXCL_MN08_4000`
- Mount holes: `(+/-6, +/-6) mm`, opened to `2.4 mm`
- Header relief pins: `(10, 1)` and `(10, -1.54) mm`, opened to `1.6 mm`

## Design Rule

Use the PCB as the source of truth. The KiCad board center is translated to the
holder origin. The rear circular sink is concentric with the 24 mm PCB outline,
opened to `24.4 mm`, and cut `1.6 mm` deep.

The sink is the only functional change from the clean base holder.

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder.step` |
| holder_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder.stl` |
| pcb_proxy_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_pcb_proxy.step` |
| pcb_proxy_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_pcb_proxy.stl` |
| assembly_step | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_assembly.step` |
| assembly_stl | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_assembly.stl` |
| top_alignment_svg | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_top_alignment.svg` |
| top_alignment_png | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_top_alignment.png` |
| pcb_geometry_json | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/lumileds_pcb_aligned_sink_cage_holder_pcb_geometry.json` |
| manifest | `cad/designs/lumileds_pcb_aligned_sink_cage_holder/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `lumileds_pcb_aligned_sink_cage_holder` |
| `source_pcb` | `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb` |
| `base_design` | `cad/designs/lumileds_pcb_aligned_simple_cage_holder` |
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
| `pcb_mount_clearance_diameter_mm` | `2.4` |
| `header_pin_relief_diameter_mm` | `1.6` |
| `led_aperture_diameter_mm` | `10.0` |
| `coordinate_rule` | `PCB center is translated to holder origin. The rear PCB sink is concentric with the KiCad board outline.` |

## Notes

- Print/check the holder-only STEP/STL. The assembly STEP/STL includes PCB,
  LED, header, and cage-rod proxies only for fit checking.
- If the PCB is too tight, change `pcb_sink_diameter_mm`; keep the mount-hole
  coordinates unchanged.
