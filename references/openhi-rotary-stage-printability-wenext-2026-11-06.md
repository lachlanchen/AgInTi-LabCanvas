# OpenHI rotary stage: printable rotor and manufacturing handoff

## Revision boundary

Project: `cad/designs/diy_hollow_rotary_stage_openhi_nema17/`.
Accepted comparison baseline: run 6, the 300 mm belt / 16 mm pulley version.
New output: `run-7-upright-chamfered-rotor-prototype-20261106T110659Z`.
Previous runs remain intact.

Repeated print failures were reported without a failure photograph or slicer
project. The 120T rotor cup was the immediate discussion context. Its broad
unsupported flange and inverted orientation were revised; this is not a proven
diagnosis of every failed print.

The revised cup prints upright, starting with a roughly 67.6 mm outside-diameter
bottom ring. A 6 mm-high, 45-degree annular transition supports the wide flange.
Only a 0.2 mm radial outer lip remains. The three hex-nut passages extend to the
underside: adding a taper without reopening these passages would trap the nuts
outside their insertion route. The nut roofs remain at the accepted height.

The 52.1 mm bearing seat, 2GT teeth, cap interface and nut roofs were compared
after STEP re-import using bounded domains and bidirectional boolean differences.
All comparison volumes are zero. All seven other printed parts also compare
equal. The 30 mm optical bore, 85 mm outer flange datum, belt center distance,
motor pattern and fastener geometry remain unchanged.

## Verification

`build_stage.py` now includes `validate_rotor_revision()` and
`manufacturing_exports()`. The first compares exported meshes and STEP solids
against accepted run 6, restored from the repository run folder or Nutstore.
The second creates a clean, quantity-scoped factory set. No global scaling or
new bearing/drive architecture was introduced.

Mesh faces steeper than 50 degrees from vertical, excluding the first 0.3 mm,
total 985.76 mm2 for the old inverted cup and 151.39 mm2 for the new upright cup.
The approximately 85% reduction includes both geometry and print orientation;
it is not a measured print-success rate. Small nut-pocket roofs still bridge.
The carrier's motor roof retains its documented FDM support requirement.

PrusaSlicer 2.7.2 completed a generic diagnostic slice with 0.2 mm layers,
0.4 mm nozzle, five perimeters, 40% infill and supports disabled. It generated
73 layers with a nonempty first layer. This was not the owner's QIDI profile;
the diagnostic G-code is deliberately not delivered as a printer-ready file.
Successful slicing does not prove bed adhesion or physical bridge performance.

The verified reusable slicer runtime is installed once at
`~/.local/share/labcanvas/prusaslicer-2.7.2/`. Its binary is
`usr/bin/prusa-slicer`; use its bundled `usr/lib/x86_64-linux-gnu` in
`LD_LIBRARY_PATH`. Ubuntu package 2.7.2+dfsg-1build2 and the small missing
libraries were extracted locally, without replacing system libraries.

## Factory files

`manufacturing/wenext/` contains eight independent, grounded, millimetre-unit
STL/STEP pairs with quantities and checksums:

- carrier;
- rotor cup and rotor cap;
- fixed inner-race retainer;
- footed stand;
- optional 5 mm height shim;
- optional polarizer insert and retainer.

Each is supplied once. Optional means optional in the installed configuration,
not omitted from the ordered set. Factory files exclude removable FDM ears,
fit coupons, motor, bearing, belt, metal pulley, fasteners and optical glass.
The assembly STEP must never be uploaded as one manufactured part.

## WeNext ordering method

The existing WeNext profile and CAD sourcing desktop were reused. The prior
Taobao browser was closed without deleting its profile or changing its cart.
The current noVNC URL and owned profile/process contract remain in ignored
`output/cad_sourcing/runtime/handoff.json`.

The saved password was rejected. The owner completed login in the same browser;
no new password or cookies were exported. Files were uploaded once through the
visible file input. All eight parsed successfully; the toothed cup took longer
than the simpler parts, so a pending parser was not mistaken for a failed file.

The visible batch-material menu uses **批量编辑 → 按列表样式选择 → 尼龙**.
The native checkbox input is visually hidden: click its visible label and verify
the selected class. After confirming a material, wait for all eight product rows
to update before testing the new state or adding to cart.

The selected material is **未来7000尼龙 / 未来7000（华曙）, white**, four-day
production, without coating or optional finishing. Observed quote on 2026-11-06:
parts RMB333.80, shipping RMB12.00, total RMB345.80. HP PA12 and basic/tough
resin alternatives were compared but not added as duplicate products.
The supplier's [nylon information](https://www.wenext.com/materials/3d-plastic/nylon)
describes powder-supported printing and functional applications. The selected
quote lists +/-0.3 mm or +/-0.3%; this does not guarantee the nominal 0.1 mm
bearing clearance. Measure and gently finish mating surfaces as necessary;
never force the bearing or globally scale the model.

Before the single submit click, verify exact filenames, eight quantities of one,
material/color, total, and the existing shipping identity against private config.
An onboarding **下一步 → 完成指引** overlay may need finishing first.
The hidden `sendInviteText` textarea is not an order-note field: do not force-fill
it. The visible special-service checkbox requests paid assembly and was left off.

A private intent record was written before submitting once. The cashier amount
was verified and all payment controls were left untouched. Order identity,
checkout/payment screenshots and the recovery record remain under
`~/.config/wenext-3d-order/submissions/china/rotary-stage-20261106/`, not git.
Never repeat submission after an uncertain timeout without checking that record
and the existing order page first.

The legacy China-flow script contains two-product assumptions, so it was not
blindly used for this eight-part order. CDP/Playwright operated the visible UI
with the current manufacturing manifest as the exact file/quantity contract.

## Delivery

The full run is checksum-synced to
`Projects/LabCanvas/diy_hollow_rotary_stage_openhi_nema17/<run-name>/` in
Nutstore, including single-part STEP/STL/3MF, manufacturing files, assembly STEP,
19 render previews, editable source, validation records and the revised Chinese
and English tutorials. Earlier runs remain available. The project-level
`USE_THIS` assembly points to the latest checked geometry.
