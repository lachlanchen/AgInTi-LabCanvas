# Lumileds PCB-Aligned Simple Cage Holder

This is a fourth, simplified replacement candidate for the earlier Lumileds
cage holder attempts. The three older designs are left untouched.

## Design Rule

Use the PCB as the source of truth. The KiCad board center is translated to the
holder origin, then the holder holes are copied from the PCB. The part is one
monolithic centered plate with through-holes only.

No counterbores. No recessed PCB pocket. No bottom post hole. No lightening
cutouts. The PCB sits flat on the rear face and is aligned by screws.

## PCB Geometry Used

- Source PCB: `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb`
- KiCad board center: `(150.0, 100.0) mm`
- PCB outer diameter: `24.0 mm`
- LED center relative to holder: `(0.0, 0.0) mm from LXCL_MN08_4000`

PCB mounting holes relative to the holder origin:

| # | x mm | y mm | source drill mm |
| --- | ---: | ---: | ---: |
| 1 | `-6.0` | `-6.0` | `2.2` |
| 2 | `6.0` | `-6.0` | `2.2` |
| 3 | `-6.0` | `6.0` | `2.2` |
| 4 | `6.0` | `6.0` | `2.2` |

Header pin holes from the KiCad right-angle 2P header:

| Pin | x mm | y mm | source drill mm |
| --- | ---: | ---: | ---: |
| J1-1 | `10.0` | `1.0` | `1.0` |
| J1-2 | `10.0` | `-1.54` | `1.0` |

## Holder Geometry

- Body: `42.0 x 42.0 x 8.0 mm`.
- 30 mm cage rod holes: centered at `(+/-15, +/-15)` with `6.4 mm` through clearance.
- PCB M2 holes: copied from KiCad and opened to `2.4 mm`.
- Header pin relief holes: copied from KiCad and opened to `1.6 mm`.
- LED aperture: `10.0 mm`, centered on the KiCad LED footprint.

## Outputs

| Output | Path |
| --- | --- |
| holder_step | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/lumileds_pcb_aligned_simple_cage_holder.step` |
| holder_stl | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/lumileds_pcb_aligned_simple_cage_holder.stl` |
| assembly_step | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/lumileds_pcb_aligned_simple_cage_holder_assembly.step` |
| assembly_stl | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/lumileds_pcb_aligned_simple_cage_holder_assembly.stl` |
| top_alignment_svg | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/lumileds_pcb_aligned_simple_cage_holder_top_alignment.svg` |
| top_alignment_png | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/lumileds_pcb_aligned_simple_cage_holder_top_alignment.png` |
| pcb_geometry_json | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/lumileds_pcb_aligned_simple_cage_holder_pcb_geometry.json` |
| manifest | `cad/designs/lumileds_pcb_aligned_simple_cage_holder/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `lumileds_pcb_aligned_simple_cage_holder` |
| `source_pcb` | `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb` |
| `body_width_mm` | `42.0` |
| `body_height_mm` | `42.0` |
| `body_thickness_mm` | `8.0` |
| `edge_fillet_mm` | `0.8` |
| `cage_rod_pitch_mm` | `30.0` |
| `cage_rod_clearance_diameter_mm` | `6.4` |
| `pcb_mount_clearance_diameter_mm` | `2.4` |
| `header_pin_relief_diameter_mm` | `1.6` |
| `led_aperture_diameter_mm` | `10.0` |
| `pcb_thickness_mm` | `1.6` |
| `pcb_mount_note` | `No counterbore and no pocket: the PCB sits flat on the rear face and is located by four M2 holes.` |
| `coordinate_rule` | `PCB center is translated to holder origin. Every PCB-derived hole is stored relative to that center.` |

## Notes

- This model is intentionally plain so the physical alignment can be checked
  before adding any nicer clamps, pockets, cable reliefs, or screw-head
  features.
- If the first print is too tight, change only the relevant clearance diameter
  in the script and rebuild.
- The assembly files include PCB, LED, header, and cage-rod proxies only for fit
  checking. The holder-only STEP/STL files are the printable part.
