# OpenHI hollow rotary stage: retail parts and CAD revision

## Verified selection

The visible Taobao product selectors and cart were checked on 2026-11-04.
Cart preparation was authorized; checkout and payment were not performed.
Stock, price and dispatch estimates can change.

| Part | Selected option | Cart action |
| --- | --- | --- |
| [20T motor pulley](https://item.taobao.com/item.htm?id=599597755167&skuId=4179743856908) | `20齿内孔5高16（高品质）`; 2GT, bore 5 mm, overall height 16 mm, for a 6 mm belt | Added once; quantity 1 verified |
| [Endless timing belt](https://item.taobao.com/item.htm?id=653406155594&skuId=4885322183458) | `2GT-6MM-300MM（防滑环形带）`; 2 mm pitch, 300 mm pitch length, 6 mm width | Added once; quantity 1 verified |
| [6808ZZ bearing](https://item.taobao.com/item.htm?id=640622640655&skuId=5741004041162) | `6808ZZ/P4钢封【日本进口 质保三年】`; nominal 40 x 52 x 7 mm | Already present; quantity 1 preserved, not added again |

The bearing listing is inconsistent: generic parameters mention China, P5 and
6807, while the selected option says imported, P4 and 6808. Its origin,
authenticity and precision grade are unverified. The dimensional basis is the
6808 designation and the linked manufacturer catalogue in the design README,
not the seller's precision claim. Measure the received bearing before assembly.

The [pulley supplier diagram](https://img.alicdn.com/imgextra/i3/2786671363/O1CN011LwIISizHlGaVnV_!!2786671363.png)
identifies 20 teeth, 5 mm bore, 16 mm total height and 16 mm flange/hub diameter.
It does not dimension the individual channel, flange and hub axial lengths.
The model uses a reference split of 7.5 + 1 + 1 + 6.5 mm. Do not present that
split as supplier-measured CAD; slide the real pulley along the shaft to align
its tooth channel with the belt before locking it.

## Belt width and hollow driven pulley

- The timing belt needs teeth. The selected belt and both pulleys use 2GT/GT2
  with 2 mm pitch; MXL and T2.5 are not substitutes.
- Some listings use "7 mm" for the pulley groove width, not belt width. This
  purchase uses a 6 mm belt. Verify the exact selected SKU rather than inferring
  belt width from a pulley title.
- The 300 mm belt has 150 belt teeth. The driven wheel has 120 teeth. Those
  quantities describe different parts; the drive ratio remains 120 / 20 = 6.
- The 120T wheel is a printed annular cup. Do not buy a solid wheel: the bare
  stage must retain a 30 mm through-bore. The removable polarizer insert reduces
  the clear optical aperture to 24 mm.

## Stock-driven CAD change

Project: `cad/designs/diy_hollow_rotary_stage_openhi_nema17/`.

Baseline:
`run-5-common-carrier-30mm-bore-85mm-datum-prototype-20261104T105605Z`.

Current:
`run-6-stock-300mm-belt-16mm-pulley-prototype-20261104T130416Z`.

The original 320 mm belt option showed a seven-day presale. Another listing
required a length note and otherwise defaulted to the maximum listed length.
The explicit same-shop 300 mm SKU was selected instead. This changes the nominal
center distance from 83.884885 to 72.937066 mm, with the existing +/-3 mm tension
adjustment retained. The exact open-belt pitch-length equation is used, not a
global model scale.

At the shorter center distance, the unrotated motor pattern puts two vertical
4 mm tool envelopes into the belt. Rotating the exact OpenHI motor and its four
mounting slots by 10 degrees clears all four tool paths. Apply that transform
to the motor, screw/washer positions, body relief and optional shim consistently.
This changes only the printed carrier and optional 5 mm height shim.

The six other printed parts were compared with run 5 after STEP re-import:
rotor cup, rotor cap, inner-race retainer, footed stand, polarizer insert and
polarizer retainer. Bounding boxes match and both directional boolean difference
volumes are zero. The run records this in `continuity_checks.json`.

The run also verifies:

- unobstructed 30 mm bare-stage bore;
- sampled and conservative full-rotation interference checks;
- motor-to-carrier clearance at both tension-slot extremes;
- screw-head/belt separation and 4 mm vertical tool access;
- valid STEP round-trip;
- 15 individual parts/coupons, each one connected watertight object at Z=0,
  with one millimetre-unit 3MF build item;
- 19 uncropped CPU-rendered views with safe camera margins;
- checksummed full-run Nutstore copy.

These checks establish modeled compatibility, not physical bearing fit, belt
quality, motor screw depth, load capacity or angular accuracy. Print the fit
coupons first. Preserve run 5 rather than mixing its carrier with the 300 mm belt.

## Reusable browser method

Use one isolated CAD-sourcing desktop/profile, not JLC, Xiaoyunque or Books.
The private runtime handoff is `output/cad_sourcing/runtime/handoff.json`;
account data, raw cart screenshots and the browser profile remain local/ignored.
No cookie extraction or hidden shopping API was used.

1. Attach Playwright to the recorded CDP endpoint. Locate each tab by its
   observed URL/product ID, never `context.pages[0]`: page order can change on
   reconnect. Reuse existing tabs instead of opening many new ones.
2. Inspect the visible selected SKU state. Clicking an already selected option
   can deselect it. Verify the option and quantity before adding anything.
3. On this Taobao UI, the yellow add-to-cart control was icon-only:
   `i.icon-taobaojiarugouwuche-xianxing`. Do not confuse it with the adjacent
   purchase button. This selector is an observation, not a permanent API.
4. Add only once. If a toast or count wait times out, inspect the cart first;
   blindly retrying can duplicate quantities.
5. Reload the cart, locate each item by product ID, read its selected option
   and quantity in that item's card, and capture private evidence. Preserve
   unrelated products and checkbox state. Stop before checkout/payment.
6. Keep the isolated browser only while cart review is pending. Then stop its
   exact owned runtime, preserving its reusable profile and evidence.

Normalized public product data is in `taobao_selection.json`. The private
supplier dimension image is copied into the ignored/synced run references;
raw account/cart screenshots are not included in git or the CAD handoff.

## Rebuild and delivery

Use the existing `build_stage.py`, `render_stage.py` and `package_stage.py`.
Rendering uses the shared Blender installation in CPU mode, not a second GPU
job. Packaging requires ReportLab, Pandoc, XeLaTeX and Noto CJK fonts.

The full package contains separate printable STEP/STL/3MF files, assembly STEP,
render previews, fit coupons, English guide and Chinese tutorial with practical
mechanical English. Nutstore destination:
`Projects/LabCanvas/diy_hollow_rotary_stage_openhi_nema17/<run-name>/`.
The project-level `USE_THIS` assembly and Chinese tutorial point to the current
checked run; previous run folders remain intact.
