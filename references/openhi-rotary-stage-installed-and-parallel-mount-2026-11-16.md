# OpenHI rotary stage: installed baseline and optional parallel mount

The owner confirmed on 2026-11-16 that the WeNext-printed run 7 was assembled
and works. The supplied rear photograph shows the motor turned relative to the
stand. That matches the deliberate 10-degree in-plane motor mounting pattern;
it is not a 57 mm motor allowance or a deliberately tilted mounting face.
Accuracy, repeatability, life and payload remain unmeasured.

Canonical project: `cad/designs/diy_hollow_rotary_stage_openhi_nema17/`.
Read `FIELD_VALIDATION.md`, `fastener_contract.json` and `FASTENERS.zh-CN.md`.
The six matched Taobao selections are in `fastener_selection_20261116.json`.
Each cart row was verified against its item identity, exact option and quantity
one. No checkout or payment was made. Keep private cart/session evidence local.

The installed baseline remains
`run-7-upright-chamfered-rotor-prototype-20261106T110659Z`.
It uses only the exact OpenHI NEMA17 motor. The 82 mm output and footprint come
primarily from the 120T belt drive, bearing and mounting clearance, not NEMA23.

Optional run 8 introduces a parallel removable motor plate. Bench-fit the four
motor screws first; four accessible outboard clamps then adjust and retain the
whole motor/plate module. Only the new carrier and motor plate need printing;
the proven stand, rotor, bearing, belt and optical datums are retained. This is
an alignment/access improvement, not a substantially miniaturized stage.

The variant passed 122 clearance/interference checks, STEP round trips and
grounded connected print checks. It is not physically tested. Its STEP/STL/3MF,
source, manifest and uncropped renders are synced under the Nutstore project's
`optional-variants/` folder. `artifacts/latest.json` and the root `USE_THIS`
assembly still identify the installed run; alternatives have separate pointers.

Reusable guidance is in the installed and LazySkills
`parametric-cad-design/references/hollow-rotary-stage.md`. Keep bearing-race
retention, complete tool access, actual fastener head envelopes, process-specific
fits and mechanical versus optical height datums explicit when adapting it.
