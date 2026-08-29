# OpenHI Same-Lens 4f Regeneration Philosophy

Date: 2026-08-29

## Source Authority

The authoritative mechanical geometry is the flattened OpenHI STEP family and
the matching `OpenHI.shapr` assembly. The Shapr archive records these parts
mostly as imported B-reps, so it is useful for assembly intent and naming but
does not expose a complete native feature history. The checked STEP B-reps are
therefore preserved for the beam-splitter center, central interfaces, cap
geometry, and thread families.

Lens evidence comes from:

- `/home/lachlan/Downloads/lens_images_and_analysis/lens_analysis.md` and its
  source images for JH042/JH036;
- `/home/lachlan/Downloads/Hengyang_GLA11_two_lenses_full_details/lens_specifications.md`
  and its source images for the two GLA11 lenses.

Every design manifest records the exact path, size, and SHA-256 of those input
files so a later agent can distinguish a changed source drawing from a CAD
regression.

The six reusable mechanical roles are:

1. `A`: lower port and lens retainer.
2. `A + C + BS`: lower arm, lateral C receiver, and fixed 45-degree
   beam-splitter pocket.
3. `B`: upper port and lens retainer.
4. `C`: lateral port and lens retainer.
5. `Lens B holder`: complementary beam-splitter body and upper lens arm.
6. `Lens C holder`: lateral bridge from the beam-splitter body to lens C.

The exploded STEP coordinates hide the assembly logic. In the source assembly,
`A` moves +20 mm in Z, `B` moves -20 mm in Z, `C` moves -50 mm in X, and
`Lens C holder` moves -20 mm in X. After those transforms, all three original
ST018 lens contact planes are 50 mm from the beam-splitter center
`(255, 210, 600) mm`.

## Optical Design Rule

For a same-lens system, use one lens type in all three locations:

- lens A is below the beam splitter;
- lens B is above it;
- lens C is on the lateral output;
- each holder contact plane is one catalog focal length from the fixed
  beam-splitter center;
- A-B and A-C are therefore nominal `2f` lens pairs.

This matches the original OpenHI/ST018 design convention and avoids mixing
principal-plane assumptions between unlike lenses. A future mixed-focal system
can use the same builder with separate arm specifications, but it should be a
separate optical design and validation pass.

## Plano-Convex Orientation

For the two GLA11 variants, the requested plane faces point toward the central
beam splitter and the curved faces point outward. This is represented
consistently in A, B, and C.

The manufacturer publishes both EFL and BFL. OpenHI's legacy mechanical layout
uses catalog EFL as the holder-contact distance. A thick plano-convex lens does
not have its principal plane at its physical plane surface, so the manifest
also records BFL and `BFL - EFL`. Bench focusing must verify the final datum,
especially for the thick 25.4 mm focal-length lens. This is an explicit design
assumption, not hidden precision.

## Mechanical Regeneration Rule

Do not scale the complete STEP and do not move the beam-splitter pocket.
Instead:

1. Preserve the exact central B-rep at the beam splitter.
2. Preserve the proven A/B/C cap bodies and male threads.
3. Regenerate only each straight arm from the central datum to the new lens
   plane.
4. Use the measured 40 mm outer envelope and 24 mm optical bore.
5. Give the lens pocket 0.25 mm diametric clearance.
6. Leave a real annular shoulder between the clear aperture and lens pocket.
7. Put the 45-degree transition on the A/B/C-facing receiver side.
8. Reuse the 29.8 mm female pivot, 30.6 mm groove, 0.8 mm pitch, and 0.4 mm
   radial tooth depth.
9. Generate each helix beyond both ends and clip it back to the exact threaded
   interval so no thread enters the lens pocket, mouth, or central body.
10. For a lens smaller than the original 25 mm class, add an integral retainer
    land to A/B/C rather than leaving it unsupported in the 24 mm bore.
11. Seat a curved lens at the actual annular shoulder radius. Do not use its
    optical vertex or extreme outer edge as a generic mechanical datum.
12. Center the B aperture, pocket, transition, and thread on X = 255 mm even
    though the accepted B holder's outer skin is offset to X = 254.633 mm.
    Exterior asymmetry must not move the optical axis.
13. Fuse the legacy tangent-only thread bodies only in the printable export.
    The Lens C male tooth receives a 0.005 mm radial overlap below print
    resolution; its 29.8 mm root and 30.6 mm crest envelope is preserved.

## Four Lens Reconstructions

### JH042

- Diameter: 22.0 mm
- Total center thickness: 8.5 mm
- Catalog EFL: 27.48499 mm
- Catalog surfaces: `0 / 18.867 / 31.801 mm`
- Materials: ZF6/ZF13

The catalog does not provide signed radii or individual element center
thicknesses. The CAD uses explicit `0 / +18.867 / -31.801 mm` signs and a
2.5/6.0 mm center-thickness split to create a mechanically valid positive
doublet envelope. It must not be described as an exact optical prescription
without a vendor section drawing.

### JH036

- Diameter: 24.9 mm
- Total center thickness: 9.9 mm
- Catalog EFL: 45.999 mm
- Catalog surfaces: `369.528 / 42.9171 / 28.5063 mm`
- Materials: H-ZF6/H-ZK11

The CAD uses explicit `+369.528 / +42.9171 / -28.5063 mm` signs and a 2.4/7.5
mm split. With catalog d-line refractive indices, this assumption reproduces
the listed EFL to approximately 0.002 mm, but it is still marked provisional
because the source table omits the signs and split.

### GLA11-025-025-A

- Diameter: 25.0 mm
- EFL: 25.4 mm
- BFL: 17.68 mm
- Center/edge thickness: 11.7/2.5 mm
- Convex radius: 13.08 mm
- Bevel: 0.2 mm x 45 degrees

### GLA11-025-050-A

- Diameter: 25.0 mm
- EFL: 50.0 mm
- BFL: 46.5 mm
- Center/edge thickness: 5.3/2.07 mm
- Convex radius: 25.75 mm
- Bevel: 0.2 mm x 45 degrees

## Validation Contract

Every generated family must contain:

- six separate mechanical STEP files;
- matching STL and 3MF files;
- a standalone lens STEP/STL/3MF;
- an assembly STEP with three identical lens copies and a beam-splitter
  reference;
- a machine-readable manifest;
- an assembled render and optical-axis render;
- STEP round-trip validity and mesh watertightness checks;
- zero lens-to-holder/cap interference at all three locations;
- at least 5 mm of calculated thread engagement on A, B, and C;
- zero measured focal-datum error within numerical tolerance;
- zero geometric difference in the protected beam-splitter B-rep region;
- a descriptive `USE_THIS_*_assembly.step` at the design root;
- a clean Nutstore copy under `Projects/LabCanvas/<design>/`.

This makes the optical assumption, mechanical fit, source provenance, and
print handoff independently inspectable.
