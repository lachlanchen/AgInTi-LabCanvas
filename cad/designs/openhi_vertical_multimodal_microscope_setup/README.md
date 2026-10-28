# Vertical Multimodal OpenHI Microscope Setup

## Updated Dual-LCD Stack

The latest assembly follows the revised photographed order, bottom to top:

**Dock -> lamp/PCB -> GT090101 -> LCD holder -> specimen holder/dish/cap ->
LCD holder -> GT090101 -> microscope -> relay(s) -> detectors.**

`artifacts/dual_lcd_stack_latest.json` points to the current timestamped run.
It provides single-relay, horizontal-cascade and vertical-cascade assemblies,
each with a full-frame overview. Two opposite-side lower-stack close-ups and
two detector close-ups accompany the overviews. The combined PDF/SVG panel
keeps titles and captions editable and uses the same verified renders.

Both LCD holders use the accepted 45-degree seat with full-through pin/plug
clearance. All fixture and relay geometry is reused; the microscope, accepted
relay(s), adapters and detector branches receive one common +22 mm translation.
Lens seats, threads, per-relay beam-splitter compensation and the 3 mm cascade
interface gap are unchanged. The rotary-stage project is not modified.
The GT090101 bodies come from the frozen accepted assembly rather than a new
conversion of the raw supplier STEP. Named-part solid/shell/face counts,
analytic bounds and volumes are checked again after assembly export.

The photograph establishes the sequence, not exact axial distances. This
layout uses six 5 mm spacer layers. Holder/mount envelopes are at Z=35..43
(lamp), 48..66 (lower GT090101), 71..79 (lower LCD), 84..118 (sample),
123..131 (upper LCD), and 136..154 mm (upper GT090101); the microscope begins
at Z=162 mm. Each value is explicit in the run manifest. Both LCD seats are
shown populated with glass/pin references; drive state and polarizer angles
are not inferred. Focus and working distance still require physical adjustment.

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/openhi_vertical_multimodal_microscope_setup/build_dual_lcd_stack.py
blender --background --threads 6 --python-exit-code 1 --python \
  cad/designs/openhi_vertical_multimodal_microscope_setup/render_dual_lcd_stack.py
cad/.conda/cad-python/bin/python \
  cad/designs/openhi_vertical_multimodal_microscope_setup/package_dual_lcd_stack.py
python -m unittest tests.test_openhi_dual_lcd_stack
```

Optional `--photo PATH` saves a neutrally named reference photograph in the
ignored run. The package step checksum-verifies the complete run in
`/home/lachlan/Nutstore Files/Projects/LabCanvas/openhi_vertical_multimodal_microscope_setup/`
and refreshes three descriptive `USE_THIS_openhi_dual_lcd_stack_*.step` handoffs.
These apparatus assemblies are for review, not whole-apparatus printing.
Earlier runs and their accepted source bodies remain unchanged.

## Original Run 1/2 Layout

This project reconstructs the photographed vertical apparatus as three aligned CAD assemblies. It reuses the accepted source parts rather than redrawing them:

- 100 mm cage dock and 30 mm cage datum;
- axial spacer collars;
- Lumileds PCB holder carrying the 3 mm tungsten source;
- QYH1123 light-valve holder and valve;
- two-piece slide/petri sample holder and cap;
- Hengyang GT090101 rotation mount;
- the OpenHI microscope body;
- the validated `f = 50 mm` OpenHI relay;
- the accepted C12880MA holder/module geometry.

The bulb envelope, thin polarizer film, sample volume, short adapter sleeves, frame-camera housing and event-camera housing are explicitly recorded as visualization proxies. They are not manufacturing drawings.

The three real-apparatus photographs used to establish the vertical order and
branch orientation are preserved under `reference_media/`. They are layout
evidence rather than dimensional substitutes for the accepted STEP sources.

## Optical Architecture

The lower train shares one vertical axis: source, LCD, sample, analyzer, microscope and the first relay input. The cage rods remain on the standard `30 mm` square (`x/y = +/-15 mm`). One 5 mm spacer layer separates the dock and lamp holder; two 5 mm layers separate the lamp and LCD holders.

The single-relay version routes the straight output to a frame-camera proxy and the split output to the C12880MA assembly. The cascaded version keeps the frame branch, places the second relay directly on the first split port, and terminates its outputs at an event-camera proxy and C12880MA. The second relay is a rigid `+90 deg` rotation about `Y`; its A-input plane is `3 mm` beyond the first C-output plane.

The additional **vertical cascade** places the second A input above the first
B output with the same 3 mm interface gap. The first lateral port carries the
frame camera, the second lateral port carries C12880MA, and the second straight
port carries the event-camera proxy. The second input is shifted X=-0.367 mm
to match the first relay's actual B axis. The second B axis then finishes at
X=-0.734 mm; the accepted per-relay beam-splitter compensation is preserved.
This is a mechanically positioned visualization, not a new optical-performance
or exact sensor conjugate qualification.

## Files To Use

- `USE_THIS_openhi_vertical_multimodal_microscope_setup_single_4f.step`
- `USE_THIS_openhi_vertical_multimodal_microscope_setup_dual_4f.step`
- `USE_THIS_openhi_vertical_multimodal_microscope_setup_dual_4f_vertical.step`
- `artifacts/figures/Figure_1_vertical_multimodal_openhi_setup.pdf`
- `artifacts/figures/Figure_1_vertical_multimodal_openhi_setup.svg`
- `artifacts/renders/single_4f_nature.png`
- `artifacts/renders/dual_4f_nature.png`
- `artifacts/renders/dual_4f_vertical_nature.png`
- `artifacts/figures/Figure_2_vertical_cascade_openhi_setup.pdf`

`artifacts/manifest.json` is the source of truth for source hashes, component identity, placements, optical paths and validation.

Run 1 is preserved at `runs/run-1-apparatus-single-dual-4f-20261027T132540Z/`,
including its initial figures. Run 2 is
`runs/run-2-vertical-cascade-full-frame-20261027T140302Z/` and contains the new
vertical assembly plus corrected full-frame renders. The accepted lower-stack
close-up remains unchanged. All full views and detector details now use
`cad/tools/blender_camera_fit.py`, with camera-space bounding-box checks and
an 8% margin. `artifacts/renders/camera_validation.json` records that evidence.

## Rebuild

```bash
cad/.conda/cad-python/bin/python \
  cad/designs/openhi_vertical_multimodal_microscope_setup/build_openhi_vertical_multimodal_microscope_setup.py

blender --background --python \
  cad/designs/openhi_vertical_multimodal_microscope_setup/render_openhi_vertical_multimodal_microscope_setup.py

python cad/designs/openhi_vertical_multimodal_microscope_setup/compose_nature_figure.py
```

## Scope

These STEP files are assembly and publication-figure models. Existing printable component projects remain authoritative for fabrication. The detector proxies require measured vendor CAD before they should be used to manufacture adapters.
