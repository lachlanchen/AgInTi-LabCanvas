# OpenHI A Layer-Shift Diagnosis

Date: 2026-08-18

## Conclusion

The failed OpenHI A print shows real XY layer shifts (lost motion), not a
stair-stepped CAD body or a hidden QIDI object transform. Do not regenerate A,
B, or C to address this failure.

The base remained attached to the bed while successive upper sections moved in
one lateral direction. Extrusion then continued partly in air. The first print
shifted roughly seven or eight times and the second roughly twice. A
deterministic geometry or toolpath translation would normally recur at the same
heights; the changing count is strong evidence of intermittent collision or
motion loss.

## Evidence

- Repository A print mesh: one watertight connected component, `8082` vertices,
  `16164` triangles, bounds about `40 x 40 x 50 mm`.
- Repository 3MF: one model object and one build item with no transform.
- QIDI Studio project: one component and one build item. Its object transform is
  identity and the build placement is a single constant translation to the bed.
- The QIDI-saved object has the same vertex count, triangle count, triangle
  indices, and centered coordinates as the repository object. Maximum
  coordinate difference after removing the constant placement translation is
  about `0.0000012 mm`, which is serialization rounding only.
- QIDI metadata reports zero repaired edges, facets, or reversed facets.
- The `0.2 mm` layer-stack audit found no gross translation in any print-ready
  part: A `0.280622 mm`, B `0.280344 mm`, and C `0.278013 mm` maximum
  consecutive section-center change. These sub-`0.3 mm` values are the expected
  rotating helical-tooth envelope, not the multi-millimetre staircase visible
  in the photograph.

The generated evidence is under `artifacts/print_diagnostics/`.

## Risk In The Saved QIDI Profile

The QIDI-saved project used an X-Max 4 custom `0.12 mm` ASA profile with:

- `100%` sparse infill;
- `200 mm/s` outer walls;
- `350 mm/s` inner walls and internal solid infill;
- `430 mm/s` sparse infill;
- `500 mm/s` travel;
- `10000 mm/s^2` default and travel acceleration;
- automatic tree support at a `20 degree` threshold;
- `0.4 mm` Auto Lift and a `20 mm` outer-and-inner brim.

The brim and intact base in the photograph make whole-part bed movement
unlikely. The high acceleration, high infill/travel speeds, dense infill, and
tree-support interactions can instead expose a loose belt/pulley, rail binding,
or a nozzle collision. The profile does not prove which mechanical event
occurred, but it substantially increases the load and collision opportunities.

No uploaded G-code or printer motion log was available locally, so this audit
cannot name the first collision layer or the exact X/Y mechanism that skipped.

## Recommended Next Print

Use the same verified A mesh. For one diagnostic reslice:

- layer height: `0.20 mm`;
- outer wall: `60-80 mm/s`;
- inner wall: `100-120 mm/s`;
- infill: `100-120 mm/s`, `20-30%` rather than `100%`;
- travel: `250-300 mm/s`;
- general acceleration: `3000 mm/s^2` or lower;
- outer-wall acceleration: `1500-2000 mm/s^2`;
- keep Z lift enabled and avoid crossing walls where QIDI exposes that option;
- disable automatic tree support if preview confirms the A cavity and shoulder
  are self-supporting; otherwise use only the minimum required support and
  inspect its clearance from the thread and nozzle path;
- disable scarf-on-circles for this diagnosis so it is not another variable.

Before printing, with power off, check equal X/Y belt tension, pulley and idler
fasteners, smooth rail travel, lubrication, cable and filament clearance, and
the nozzle for accumulated material. Do not change driver current first.

Interpret the result as follows:

- no shift at conservative settings: motion load or collision was the trigger;
- shift at varying heights/different counts: inspect belt, pulley, rail,
  obstruction, and driver cooling;
- repeatable shift at exactly the same height: inspect the sliced layer preview
  and nozzle/support contact at that height, then inspect the exported G-code.

## Reusable Audit

```bash
cad/.conda/cad-python/bin/python3.11 \
  cad/designs/openhi_abc_exact_parametric_baseline/analyze_layer_stack.py \
  cad/designs/openhi_abc_exact_parametric_baseline/PRINT_THIS_OpenHI_A_exact_current_geometry.stl \
  --output-dir cad/designs/openhi_abc_exact_parametric_baseline/artifacts/print_diagnostics \
  --layer-height 0.2 \
  --gross-jump-threshold 1.0
```

This audit catches a mesh whose sections actually jump by millimetres. It does
not diagnose printer belts, pulleys, motors, rails, collisions, or driver
electronics; those require physical inspection or printer logs/G-code.

## Manufacturer References

- [QIDI 3D printing troubleshooting guide](https://us.qidi3d.com/blogs/news/3d-printing-troubleshooting-guide)
- [QIDI layer-shift troubleshooting](https://us.qidi3d.com/blogs/news/stop-layer-shifts-on-3d-printer)
- [QIDI model-specific product support](https://us.qidi3d.com/pages/product-support)
