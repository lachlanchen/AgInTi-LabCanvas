# Lumileds Hengyang 30 mm Cage Holder

This is a new independent holder for the Lumileds no-resistor round PCB. It uses
Hengyang Optics 30 mm cage dimensions as references, especially GT-090101 and
HCT rods, but it does not copy the GT-090101 rotating waveplate mechanics.

## Design Intent

- Share the same four-rod 30 mm cage setup as Hengyang 30 mm cage parts.
- Hold the Lumileds PCB from the rear with a printable pocket and M2 screws.
- Keep the center aperture small enough to preserve screw material around the
  12 x 12 mm Lumileds mounting pattern.
- Provide an optional bottom M4 pilot for a post or adapter, but the primary
  mechanical reference is the cage rod interface.

## Reference Materials

- Main reference folder: `cad/references/hengyang-optics`
- Primary reference: GT-090101 30 mm cage waveplate/polarizer holder.
- Similar references: HCP/HCP-08/GT-0803 lens holders, HCM-3 beam-splitter
  holders, HCM-3 45-degree flat holders, HKCB1PM right-angle mirror holder,
  and HCT 6 mm cage rods.

## Outputs

| Output | Path |
| --- | --- |
| holder STEP | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder.step` |
| holder STL | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder.stl` |
| assembly STEP | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder_assembly.step` |
| assembly STL | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder_assembly.stl` |
| dimension sketch SVG | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder_dimension_sketch.svg` |
| dimension sketch PNG | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder_dimension_sketch.png` |
| dimension sketch PDF | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder_dimension_sketch.pdf` |
| inspection render PNG | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder_render.png` |
| Blender inspection scene | `cad/designs/lumileds_hengyang_30mm_cage_holder/artifacts/lumileds_hengyang_30mm_cage_holder.blend` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `lumileds_hengyang_30mm_cage_holder` |
| `reference_family` | `Hengyang Optics 30 mm cage components` |
| `primary_reference` | `GT-090101` |
| `reference_folder` | `cad/references/hengyang-optics` |
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
| `rear_connector_relief_width_mm` | `10.5` |
| `rear_connector_relief_height_mm` | `4.2` |
| `rear_connector_relief_reach_mm` | `18.0` |
| `bottom_post_mount_hole_diameter_mm` | `4.2` |
| `bottom_post_mount_depth_mm` | `7.0` |
| `bottom_post_mount_note` | `M4 clearance pilot for optional post/adapter; tap or heat-set after print if needed.` |
| `print_clearance_note` | `Cage and PCB pockets include practical print clearance; tune after test print.` |

## Notes

- The holder envelope is close to the GT-090101 measured reference envelope, but
  thickness is reduced because this is a fixed LED PCB holder rather than a
  rotating optic mount.
- The shared cage geometry is four rod holes on 30 mm pitch, not the internal
  Ø25.4 mm optic clamp.
- Print one prototype before committing to metal machining; tune rod and PCB
  pocket clearances from that first fit test.
