# OpenHI A+C+BS A 29.8 / C 29.6 mm Female-Pivot Variant

## Use This File

`USE_THIS_openhi_a_c_bs_a29p8_c29p6_female_pivots.step`

For a direct mesh handoff, use `USE_THIS_openhi_a_c_bs_a29p8_c29p6_female_pivots.3mf`.

This is a sibling tight-fit variant of only `A+ C + BS.step`. The source STEP, `OpenHI.shapr`, `A.step`, and `C.step` are untouched.

## Requested Change

- Lower/A-branch female pivot: `29.6 -> 29.8 mm`.
- Side/C-branch female pivot: unchanged at `29.6 mm`.
- Thread pitch remains `0.8 mm`.
- Radial tooth height remains `0.4 mm`: A groove `30.6 mm`, C groove `30.4 mm`.
- Hand remains right-hand and the `0.8 mm` tooth base remains unchanged.

## Preserved Geometry

The builder imports the authoritative source STEP and modifies only the two female receiver interiors. It preserves the outer body, BS slope and pocket, axes, center bore, pin holes, `25.5 mm` lens seat, and all unrelated geometry. The lower mouth and lens-seat transitions preserve their original axial endpoints and remain straight conical chamfers. Enlarging only the receiver-side diameter necessarily changes their slopes from `45 degrees` to `44.443748 degrees` and `46.363928 degrees`; keeping both endpoints and exactly `45 degrees` would be geometrically impossible.

The helix is constructed with extra runout at both ends and clipped back to the exact receiver interval. This prevents the thread from protruding through the mouth, transition, or adjacent body.

## Fit Warning

The unchanged A top male is approximately `29.8/30.6 mm` root/crest, and the revised A receiver is `29.8/30.6 mm` pilot/groove. This is a zero-nominal-clearance printed fit, enlarged by `0.2 mm` in diameter from yesterday's nearly fitting receiver. The C receiver remains the accepted `29.6/30.4 mm` geometry. Test the A fit before committing to the complete optical assembly.

## Validation

- Source and output bbox: `[40.0, 40.0, 84.9]` mm; preserved: `True`.
- All material changes are confined to the two receiver envelopes: `True`.
- Relative to accepted run 1, the deltas match the A fit revision plus the bounded C-membrane removal: `True`.
- One solid: `True`; OCCT valid after STEP round trip: `True`.
- Lower/A receiver measured `29.8/30.6 mm`: `True`.
- Side/C receiver remained `29.6/30.4 mm`: `True`.
- BS-to-C optical core is clear: `True`.
- C receiver has no fusion membrane: `True`.
- Thread runouts remain bounded: `True`.
- Lower transition endpoints and required slopes preserved: `True`.
- Render mesh is one watertight, consistently wound component: `True`.
- Welded 3MF reopens as one watertight, consistently wound component with matching bounds: `True`.

## Run History

- `run-1-dual-female-29p6-20260814T132555Z`: accepted A/C `29.6/29.6 mm` female-pivot build.
- `run-2-a-female-29p8-c-female-29p6-20260815T035628Z`: current A/C `29.8/29.6 mm` female-pivot build.
- `run-3-clear-c-optical-bore-20260830T052552Z`: preserves those pivots and removes the accidental `0.10 mm` C-bore fusion membrane.
- Root `USE_THIS_*` files always point to the current checked build.

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/openhi_a_c_bs_dual_female_29p6_pivot/build_openhi_a_c_bs_a29p8_c29p6_female_pivots.py
blender --background --python cad/designs/openhi_a_c_bs_dual_female_29p6_pivot/render_openhi_a_c_bs_a29p8_c29p6_female_pivots.py
```
