# OpenHI Same-Lens 4f Input Receiver And Lens-Cavity Correction

Date: 2026-09-01

## Scope

This correction applies to all four same-lens OpenHI systems:

- `openhi_4f_jh042_same_lens`
- `openhi_4f_jh036_same_lens`
- `openhi_4f_gla11_025_025_same_lens`
- `openhi_4f_gla11_025_050_same_lens`

The prior run preserved the central beam-splitter body and generated valid
print meshes, but it had two design errors: A used a shallow plain input
chamfer instead of the original internal receiver, and the mechanical annular
lens seat was incorrectly treated as the optical focal datum. Run 4 corrects
both errors in the shared builder rather than patching four outputs separately.

## Source Authority

- Shapr assembly: `cad/extracted/OpenHI.shapr`
- Flattened source A: `cad/extracted/OpenHI_STEP/A.step`
- Accepted central body:
  `cad/designs/openhi_a_c_bs_dual_female_29p6_pivot/USE_THIS_openhi_a_c_bs_a29p8_c29p6_female_pivots.step`
- Accepted B holder:
  `cad/designs/openhi_lens_b_holder_upper_female_29p8_pivot/USE_THIS_openhi_lens_b_holder_upper_female_29p8_pivot.step`
- Accepted C holder:
  `cad/designs/openhi_lens_c_holder_right_female_29p8_pivot/USE_THIS_openhi_lens_c_holder_right_female_29p8_pivot.step`

The source A STEP contains three solids. Its lower solid spans
`Z = 479.800000..492.274000 mm`, so the input receiver is `12.474000 mm`
deep. Subtracting that solid from a bounded 30 mm cylinder recovers the exact
internal void: a 25.0 mm pilot with a 25.8 mm helical groove envelope. The
source thread-relief volume outside a smooth 25.0 mm pilot is
`60.434582 mm3`; this is a real threaded cavity, not a plain bore.

## Datum Contract

For every lens and every A/B/C branch, keep these datums separate:

1. **Inward optical-axis surface vertex**: exactly one catalog EFL from the
   beam-splitter center.
2. **Inward annular support contact**: the surface sag at the chosen support
   radius. It may differ from the axis vertex.
3. **Outward annular support contact**: the opposite surface position at the
   same support radius.
4. **Fully inserted cap contact**: outward support plus the established
   `0.20 mm` tightening allowance.

The finite lens thickness is contained inside the holder/cap cavity. It is not
added again to `2f` or `4f`. Likewise, the A input receiver depth lies inside
the A arm. A mating input device's flange seats at the A outer face; the
`12.474 mm` insertion depth is not another external seat-height term.

For A, the lens extends away from the beam splitter in `-Z`. For B it extends
in `+Z`; for C it extends in `+X`. The GLA11 plane faces point inward toward
the beam splitter, while their convex faces point outward.

## Four-Lens Audit

All dimensions are millimetres.

| Lens | EFL | Diameter | Inward support sag | Outward support | Required cavity | Fully inserted cavity | Pocket | Aperture | A-B/A-C outer path |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JH042 | 27.48499 | 22.000 | 0.000000 | 6.802839 | 6.802839 | 7.002839 | 22.250 | 20.500 | 114.53996 |
| JH036 | 45.99900 | 24.900 | 0.185269 | 7.388298 | 7.203029 | 7.403029 | 25.150 | 23.400 | 188.59600 |
| GLA11-025-025 | 25.40000 | 25.000 | 0.000000 | 4.366642 | 4.366642 | 4.566642 | 25.250 | 23.500 | 106.20000 |
| GLA11-025-050 | 50.00000 | 25.000 | 0.000000 | 2.462878 | 2.462878 | 2.662878 | 25.250 | 23.500 | 204.60000 |

JH036 demonstrates why the separation matters. Its inward optical vertex is
exactly `45.999 mm` from the beam splitter, but its annular support plane is
`46.184269 mm` away because the support sag is `0.185269 mm`. The old run put
the support plane at `f`, moving the axis vertex by that amount.

For each lens, all three A/B/C cavities have the same lens-specific required
envelope and exactly `0.20 mm` fully inserted axial clearance. Each lens-side
thread overlaps its receiver for the full bounded `7.75 mm`. B-rep
intersection checks report zero lens-to-holder, lens-to-cap, and mating-part
collision on all three arms.

## A Input Stack

From the input flange toward the A lens:

1. exact source internal female receiver, `12.474 mm` deep;
2. source 25.0 mm pilot at the receiver top;
3. 45-degree transition from 25.0 mm to the lens-specific clear aperture;
4. straight clear aperture to the A cap's annular lens contact;
5. bounded 29.6/30.4 mm male lens-retainer thread and source-style outer
   transition.

The exact receiver void is compared with the generated A void inside the same
bounded cylinder. For all four systems, both missing-source-void and
excess-void volumes are `0.0 mm3`. The smallest wall where the receiver passes
inside the 29.6 mm lens-thread root is `1.9 mm` radial.

## Preserved Interfaces

- lens-retainer female pivot/groove: `29.8/30.6 mm`;
- lens-retainer male root/crest: `29.6/30.4 mm`;
- pitch: `0.8 mm`;
- bounded lens thread length: `7.75 mm`;
- A+C+BS side/C female: preserved `29.6/30.4 mm`;
- Lens C holder central male: preserved `29.8/30.6 mm`;
- B/C output male: preserved source-style `24.4/25.2 mm`, `0.8 mm` pitch;
- B optical axis: preserved `X = 254.633 mm`, or `-0.367 mm` from A/C.

The accepted central beam-splitter B-rep above `Z = 580.1 mm` remains
unchanged, and the C optical bore remains free of the previously corrected
fusion membrane.

## Verification

Each generated manifest requires all of the following before packaging:

- valid, single-solid mechanical STEP parts;
- one watertight print object per STL and 3MF;
- `Z = 0` direct-print placement and first-layer triangles;
- measured B-rep inward and outward axis vertices at their expected positions;
- exact source A receiver cavity equivalence;
- nonzero source thread relief and at least `1.5 mm` receiver wall;
- exact `0.20 mm` fully inserted lens-cavity clearance on A, B, and C;
- zero lens/mechanical and mating-part collision;
- centered A/C axes and the intentional B-axis shift;
- clear 4 mm mechanical optical cores;
- complete end paths equal to `4f + 4.6 mm`.

The run includes two inspection renders in addition to the assembly, exploded,
optical-axis, and print-layout renders:

- `openhi_4f_a_input_receiver_section.png`
- `openhi_4f_a_lens_cavity_section.png`

These section models are visual evidence only and are not print parts.

## Print Release

Use only the run named:

`run-4-a-input-receiver-optical-vertex-lens-clearance-print-ready-20260901T040031Z`

It exists under each design's `runs/` directory and is mirrored under:

`/home/lachlan/Nutstore Files/Projects/LabCanvas/<design>/`

Each run contains the six separate `PRINT_THIS_*.step`, `*.stl`, and `*.3mf`
parts, the reference assembly and lens, manifests, README, builder snapshot,
and six checked renders. The assembly STEP is for inspection and Shapr3D
handoff; print the six mechanical parts separately.

## Remaining Physical Validation

The CAD proves geometry, spacing, and modeled clearance. It cannot certify the
JH042/JH036 internal optical prescription because the supplied vendor evidence
does not include a complete signed prescription and element-thickness split.
Catalog EFL is therefore a mechanical layout datum, not a guaranteed
principal-plane solution. Bench collimation/focus testing remains necessary,
especially for the thick GLA11 lenses where BFL differs from EFL.
