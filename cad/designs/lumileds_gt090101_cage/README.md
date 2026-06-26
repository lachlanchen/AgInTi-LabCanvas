# Lumileds GT-090101-Style Cage Holder

This is a printable 30 mm cage-compatible holder for the Lumileds round PCB.
It borrows the GT-090101 cage interface, but replaces the large waveplate
aperture with a smaller LED aperture and a rear PCB pocket.

## Reference

- Product: Hengyang Optics GT-090101 30 mm cage waveplate/polarizer holder.
- Public product page: https://www.hengyangbuy.com/Product3?cid=790
- Downloaded reference STEP: `cad/references/hengyang-gt090101/GT-090101.stp`
- Downloaded reference PDF: `cad/references/hengyang-gt090101/GT-090101.pdf`
- Reference dimensions checked from STEP: about 40.0 x 41.5 x 18.0 mm.
- Product data: 30 mm cage, four Ø6 mm rod holes, Ø25.4 mm optic clamp,
  Ø23 mm clear aperture, SM1 lock ring, aluminum black anodized.

## Lumileds PCB Interface

- Board source: `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb`.
- Board outline: Ø24 mm circle.
- Mount holes: four Ø2.2 mm holes on a 12 x 12 mm square pattern.
- Holder pocket: Ø24.6 mm x 1.9 mm rear pocket with M2 clearance holes and
  counterbores.

## Parameters

| Name | Value |
| --- | --- |
| `name` | `lumileds_gt090101_cage` |
| `reference_product` | `Hengyang Optics GT-090101` |
| `reference_page` | `https://www.hengyangbuy.com/Product3?cid=790` |
| `reference_stp` | `cad/references/hengyang-gt090101/GT-090101.stp` |
| `reference_pdf` | `cad/references/hengyang-gt090101/GT-090101.pdf` |
| `body_width_mm` | `42.0` |
| `body_height_mm` | `42.0` |
| `body_thickness_mm` | `9.0` |
| `corner_radius_mm` | `2.0` |
| `cage_rod_pitch_mm` | `30.0` |
| `cage_rod_clearance_diameter_mm` | `6.35` |
| `light_aperture_diameter_mm` | `9.5` |
| `front_chamfer_diameter_mm` | `13.5` |
| `pcb_outer_diameter_mm` | `24.0` |
| `pcb_pocket_diameter_mm` | `24.6` |
| `pcb_thickness_mm` | `1.6` |
| `pcb_pocket_depth_mm` | `1.9` |
| `pcb_mount_pattern_mm` | `12.0` |
| `pcb_mount_hole_diameter_mm` | `2.35` |
| `pcb_mount_counterbore_diameter_mm` | `4.8` |
| `pcb_mount_counterbore_depth_mm` | `2.2` |
| `connector_relief_width_mm` | `10.5` |
| `connector_relief_depth_mm` | `2.4` |
| `connector_relief_reach_mm` | `16.0` |
| `print_clearance_note` | `Rod and PCB pockets include clearance for FDM/resin printed prototypes; tune after first print.` |

## Notes

- The central aperture is Ø9.5 mm, not the GT-090101 Ø23 mm aperture, because
  the Lumileds board's four M2 holes sit inside a 12 x 12 mm pattern. A Ø23 mm
  aperture would remove the material needed to mount the PCB.
- The four cage holes keep the 30 mm pitch and use Ø6.35 mm printed clearance.
- Tune rod and PCB pocket clearances after the first print if the printer runs
  tight or loose.
