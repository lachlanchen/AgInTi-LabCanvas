# Vertical Multimodal OpenHI Microscope Setup

This project reconstructs the photographed vertical apparatus as two aligned CAD assemblies. It reuses the accepted source parts rather than redrawing them:

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

## Files To Use

- `USE_THIS_openhi_vertical_multimodal_microscope_setup_single_4f.step`
- `USE_THIS_openhi_vertical_multimodal_microscope_setup_dual_4f.step`
- `artifacts/figures/Figure_1_vertical_multimodal_openhi_setup.pdf`
- `artifacts/figures/Figure_1_vertical_multimodal_openhi_setup.svg`
- `artifacts/renders/single_4f_nature.png`
- `artifacts/renders/dual_4f_nature.png`

`artifacts/manifest.json` is the source of truth for source hashes, component identity, placements, optical paths and validation.

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
