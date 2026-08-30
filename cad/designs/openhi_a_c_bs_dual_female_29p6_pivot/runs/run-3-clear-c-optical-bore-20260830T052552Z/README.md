# Run 3: Clear C Optical Bore

This run preserves the accepted Run 2 external geometry and thread sizes:

- lower A receiver: `29.8 mm` female pivot, `30.6 mm` groove;
- side C receiver: `29.6 mm` female pivot, `30.4 mm` groove;
- thread pitch: `0.8 mm`;
- radial tooth height: `0.4 mm`.

The only C-side source correction is the removal of an accidental `0.10 mm`
fusion membrane between the side fill and smooth receiver bore. The change
removes `68.811593844 mm3` from the accepted side-receiver region while keeping
the external bounding box and all geometry outside the two receiver envelopes
unchanged.

Validation in `artifacts/manifest.json` proves:

- one valid OCCT solid;
- a clear `4.0 mm` beam-splitter-to-C optical core;
- zero overlap across a `29.4 mm` smooth C-receiver bore probe;
- bounded A and C helical threads;
- one watertight STL/3MF component with matching bounds.

Use `USE_THIS_openhi_a_c_bs_a29p8_c29p6_female_pivots.step` for editable CAD
handoff. The source-coordinate STEP remains the geometry authority for all four
same-lens 4f systems.
