# OpenHI Same-Lens 4f Final Mechanical And Optical Audit

Date: 2026-08-30

## Scope

This audit covers the four same-lens OpenHI families:

- `openhi_4f_jh042_same_lens`
- `openhi_4f_jh036_same_lens`
- `openhi_4f_gla11_025_025_same_lens`
- `openhi_4f_gla11_025_050_same_lens`

The source authority remains `cad/extracted/OpenHI.shapr`, the flattened
OpenHI STEP family, the accepted refined thread variants, and the supplied
lens specification/image folders. The beam-splitter B-rep and its center at
`(255, 210, 600) mm` are unchanged.

## Final Finding

The holder geometry, lens clearances, support lands, 30 mm lens-retainer
threads, bounded thread runout, transition chamfers, B-axis shift, nominal
focal datums, and complete physical path lengths are internally consistent.
All generated mechanical STEP parts are valid and all printable meshes are
watertight.

The audit found and corrected one lens-model-only defect: the earlier lens
proxies approximated spherical surfaces with many conical bands, and the
short-focus GLA bevel could locally extend above its specified sphere. The
four lens models now use analytic spherical B-reps. The two GLA lenses use
true `0.2 mm` CAD chamfers on both rim edges. No holder, thread, seat, arm,
beam-splitter, or outer-end datum changed. All 24 regenerated mechanical parts
retain exactly the previous solid count, bounding box, and volume.

## Lens Fit And Manufacturability

| Lens | Lens diameter | Pocket | Radial clearance per side | Aperture | Holder/cap support land | Minimum radial holder wall | 45-degree pocket transition |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JH042 | 22.00 | 22.25 | 0.125 | 20.50 | 0.875 / 0.750 | 8.875 | 3.775 axial |
| JH036 | 24.90 | 25.15 | 0.125 | 23.40 | 0.875 / 0.750 | 7.425 | 2.325 axial |
| GLA11-025-025 | 25.00 | 25.25 | 0.125 | 23.50 | 0.875 / 0.750 | 7.375 | 2.275 axial |
| GLA11-025-050 | 25.00 | 25.25 | 0.125 | 23.50 | 0.875 / 0.750 | 7.375 | 2.275 axial |

Dimensions are millimetres. The `0.25 mm` diametric pocket allowance is
symmetrical. The holder shoulder is wider than the cap land because it spans
from the clear aperture to the cleared pocket. The cap has `0.20 mm` axial
tightening travel at the actual annular support radius. B-rep intersection
checks show zero lens-to-holder and zero lens-to-cap interference at A, B, and
C for all four lens types.

The JH042 adaptation is not a 22 mm lens floating in the old 24 mm opening.
Its aperture is reduced to `20.50 mm`, leaving a real `0.75 mm` cap retainer
land and `0.875 mm` holder shoulder. The pocket-to-thread transition grows over
`3.775 mm` at 45 degrees, and the remaining radial wall is `8.875 mm`. This is
the most structurally generous of the four variants.

The holder transition is exactly 45 degrees. The complementary cap transition
is between `45.189` and `45.313` degrees because the cap retains the lens at
its nominal diameter while the pocket includes `0.25 mm` clearance. The radial
gap therefore remains positive throughout the transition instead of closing
at the chamfer.

## Thread Audit

The regenerated A/B/C lens-retainer pairs are clearance fits:

- pitch: `0.8 mm`
- radial tooth height: `0.4 mm`
- female pivot/groove: `29.8 / 30.6 mm`
- male root/crest: `29.6 / 30.4 mm`
- root radial clearance: `0.1 mm`
- crest radial clearance: `0.1 mm`
- bounded engagement: `7.75 mm`
- construction runout: `0.4 mm` beyond each end, clipped back to the exact
  parent interval

Direct construction-body checks place the first and last tooth within
`0.0000001 mm` of the requested end planes. No thread tooth enters a lens
pocket, transition, or outer body.

The central C interface is deliberately different. The A+C+BS side/C female
is the requested preserved `29.6 / 30.4 mm`, while the Lens C holder central
male remains the unchanged `29.8 / 30.6 mm`. This is `0.2 mm` nominal
diametric interference, so it is a tight printed legacy fit, not a CAD
clearance fit. The generated central overlap is approximately `85.195 mm3`;
the accepted source pair is approximately `84.848 mm3`. The small difference
comes from the sub-print-resolution fusion sleeve used to make the Lens C
holder one watertight export. This tight interface was preserved intentionally
and must not be confused with the three new retainer threads.

The B-side central pair has only a sub-`0.01 mm3` numerical boolean sliver and
matches the noninterfering source interface.

The B/C output thread remains the source OpenHI printed C-mount-like profile:
`24.4 mm` root, `25.2 mm` crest, `0.8 mm` pitch, and `4.7 mm` bounded thread
length. It is not exact standard `1"-32 UN` C-mount, whose nominal major
diameter is `25.4 mm` and pitch is `0.79375 mm`. This is source preservation,
not an unnoticed standards conversion.

## Optical Distance Chain

The nominal lens plane is the inward annular mechanical seat used by the
original OpenHI design. It is not automatically the thick-lens principal
plane.

| Lens | `f`, BS to each nominal seat | A-B and A-C seat spacing `2f` | A seat to A outer end `f+0.2` | B/C seat to outer end `f+4.4` | A end to BS `2f+0.2` | BS to B/C end `2f+4.4` | Complete path `4f+4.6` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JH042 | 27.48499 | 54.96998 | 27.68499 | 31.88499 | 55.16998 | 59.36998 | 114.53996 |
| JH036 | 45.99900 | 91.99800 | 46.19900 | 50.39900 | 92.19800 | 96.39800 | 188.59600 |
| GLA11-025-025 | 25.40000 | 50.80000 | 25.60000 | 29.80000 | 51.00000 | 55.20000 | 106.20000 |
| GLA11-025-050 | 50.00000 | 100.00000 | 50.20000 | 54.40000 | 100.20000 | 104.40000 | 204.60000 |

The thread is inside these physical envelopes and is not added again. This is
the same source rule as ST018: `A seat -> A end = f + 0.2 mm`, `output seat ->
output end = f + 4.4 mm`, and complete A-B/A-C path `= 4f + 4.6 mm`.

JH042 and both GLA lenses have a plane inward surface, so their inward
optical-axis vertex lies on the nominal seat and is exactly `f` from the beam
splitter. JH036 has a curved inward surface and is supported on an annulus at
radius `11.7 mm`; its axial vertex is `0.185269 mm` closer to the beam splitter
than that annular seat. Its modeled BS-to-inward-vertex distance is therefore
`45.813731 mm`, while the source-compatible nominal seat remains at
`45.999 mm`.

For the GLA plano-convex lenses, the plane faces point toward the beam splitter
on A, B, and C. The manufacturer BFL values differ from EFL by `-7.72 mm` for
GLA11-025-025 and `-3.50 mm` for GLA11-025-050. Therefore the CAD certifies the
source-compatible mechanical `f` spacing, not an exact thick-lens principal-
plane solution. Final collimation/focus still needs normal bench tuning.

JH042 and JH036 also lack signed vendor radii, individual element center
thicknesses, and principal-plane/BFL data. Their external mechanical envelopes
and holders are valid, but the internal cemented prescription remains an
explicit reconstruction assumption.

## Alignment And Geometry Preservation

- A and C use the beam-splitter datum at `X = 255.000 mm`.
- The complete B chain remains at `X = 254.633 mm`, preserving the accepted
  `-0.367 mm` beam-splitter offset.
- Protected beam-splitter geometry difference is zero within the B-rep check.
- All 24 mechanical parts match the pre-audit run in solid count, bounding box,
  and volume.
- Lens STEP face counts are now `6` for each doublet and `5` for each GLA
  plano-convex lens, replacing the prior 100-386 faceted faces.
- All assembly STEP files pass OCCT validity checks.
- All separate part and lens meshes are watertight.

## Remaining Physical Checks

1. Print one 30 mm thread coupon if the central C tight fit has not already
   been proven on the target printer.
2. Check the `0.25 mm` diametric lens pocket with the physical coated lenses;
   do not force a coated optic into a tight printed pocket.
3. Bench-focus each system. Treat EFL-to-seat placement as the initial OpenHI
   datum, then tune for the actual principal planes and source/detector setup.
4. Obtain the signed JH042/JH036 vendor section drawings before using these
   lens proxies as certified optical prescriptions in ray tracing.

The per-design `artifacts/manifest.json` files contain the same audit as
machine-readable `final_dimensional_audit` fields and retain all source hashes.
