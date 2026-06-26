# Modular Cage Sample Holder: OpenHI Strip and 33 mm Petri Dish

This is a new independent cage sample-holder design. It leaves the earlier
Lumileds holders untouched.

## Concept

The design is intentionally split into a clean two-part working assembly:

1. `frame`: a hollow 30 mm cage frame. The cage rods sit in the top and bottom
   rod holes, and the middle is removed.
2. `cartridge`: one swappable sample holder. Use either the OpenHI strip
   cartridge or the 33 mm petri cartridge.

This avoids forcing every sample into one complicated part. The frame stays on
the cage, while the sample cartridge can be replaced.

## Slide Size Used

I did not find a dedicated `slide holder` STEP in the local OpenHI files. The
closest local OpenHI dimensions are:

| OpenHI file | Bounding box mm | Note |
| --- | --- | --- |
| `Light switch holder.step` | `[72.958, 20.0, 66.0]` | Local OpenHI STEP file with a 72.958 x 20 mm dimension, matching the remembered 70+ x 20+ strip. |
| `Collimator holder FHPLP.step` | `[71.0, 50.0, 10.0]` | Another local OpenHI part with a 71 mm long dimension. |

So the slide cartridge uses a strip seat of `74.5 x 21.5 mm`, sized for an inferred OpenHI strip around `72.96 x 20.0 mm`.

A standard `76.0 x 26.0 mm` microscope slide is shown only as a dashed red outline in the sketch. It is too wide for a centered 30 mm cage using `6.4 mm` rod holes: the clear gap between the upper and lower rod holes is only about `23.6 mm`.

## Geometry

- Frame: `90.0 x 54.0 x 6.0 mm`.
- Hollow frame window: `76.0 x 22.0 mm`.
- Cage rod holes: four holes at `(+/-15, +/-15)`.
- Cartridge screw holes: two through holes at `x = +/-40.5 mm`.
- Optical window: `20.0 mm` through the center.
- Petri cartridge: `35.2 mm` loose cup for a nominal `33.0 mm` dish.
- Rod reliefs are intentionally cut through each cartridge, so cartridge edges and rings do not collide with the cage rods.

## Outputs

| Output | Path |
| --- | --- |
| frame_step | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_frame.step` |
| frame_stl | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_frame.stl` |
| slide_cartridge_step | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_slide_cartridge.step` |
| slide_cartridge_stl | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_slide_cartridge.stl` |
| petri_cartridge_step | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_petri_cartridge.step` |
| petri_cartridge_stl | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_petri_cartridge.stl` |
| slide_assembly_step | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_slide_assembly.step` |
| slide_assembly_stl | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_slide_assembly.stl` |
| petri_assembly_step | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_petri_assembly.step` |
| petri_assembly_stl | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_petri_assembly.stl` |
| exploded_step | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_exploded.step` |
| exploded_stl | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_exploded.stl` |
| top_alignment_svg | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_top_alignment.svg` |
| top_alignment_png | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_top_alignment.png` |
| slide_assembly_render_png | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_slide_assembly_render.png` |
| petri_assembly_render_png | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_petri_assembly_render.png` |
| exploded_render_png | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35_exploded_render.png` |
| blender_scene | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/cage_sample_holder_openhi_slide_petri35.blend` |
| manifest | `cad/designs/cage_sample_holder_openhi_slide_petri35/artifacts/manifest.json` |

## Parameters

| Name | Value |
| --- | --- |
| `name` | `cage_sample_holder_openhi_slide_petri35` |
| `architecture` | `two-part-in-use: cage frame plus one swappable sample cartridge` |
| `frame_width_mm` | `90.0` |
| `frame_height_mm` | `54.0` |
| `frame_thickness_mm` | `6.0` |
| `frame_window_width_mm` | `76.0` |
| `frame_window_height_mm` | `22.0` |
| `edge_fillet_mm` | `0.8` |
| `cartridge_width_mm` | `86.0` |
| `cartridge_height_mm` | `46.0` |
| `cartridge_thickness_mm` | `3.2` |
| `cartridge_gap_from_frame_mm` | `0.4` |
| `cage_rod_pitch_mm` | `30.0` |
| `frame_rod_clearance_diameter_mm` | `6.4` |
| `cartridge_rod_relief_diameter_mm` | `7.0` |
| `mount_screw_x_mm` | `40.5` |
| `mount_screw_clearance_diameter_mm` | `2.7` |
| `optical_window_diameter_mm` | `20.0` |
| `openhi_strip_nominal_mm` | `[72.96, 20.0]` |
| `openhi_strip_seat_clearance_mm` | `[74.5, 21.5]` |
| `slide_rail_width_mm` | `2.0` |
| `slide_rail_height_mm` | `2.0` |
| `slide_end_stop_width_mm` | `1.8` |
| `petri_nominal_diameter_mm` | `33.0` |
| `petri_clearance_diameter_mm` | `35.2` |
| `petri_outer_ring_diameter_mm` | `39.4` |
| `petri_ring_height_mm` | `2.2` |
| `standard_slide_reference_mm` | `[76.0, 26.0]` |
| `fit_warning` | `A full 75-76 x 25-26 mm microscope slide is too wide for a centered 30 mm cage with 6 mm rods. Use the OpenHI narrow strip cartridge or an external slide tray.` |

## Print Notes

- Print `frame` plus only the cartridge you need.
- The assembly files are for checking, not a single fused printable part.
- If you need a full standard microscope slide, make a later external tray that
  sits outside the cage rod plane. A centered 26 mm-wide slide does not fit
  cleanly between 6 mm rods in a 30 mm cage.
