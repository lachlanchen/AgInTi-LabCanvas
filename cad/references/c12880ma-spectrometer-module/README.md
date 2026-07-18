# C12880MA Spectrometer Module References

This folder preserves the exact evidence used for the C12880MA module holder.

## Sources

- `hamamatsu-c12880ma-datasheet.pdf`: [official Hamamatsu C12880MA/C16767MA
  datasheet](https://www.hamamatsu.com/content/dam/hamamatsu-photonics/sites/documents/99_SALES_LIBRARY/ssd/c12880ma_c16767ma_kacc1226e.pdf).
  It defines the bare sensor package, not the third-party PCB. The corresponding
  [C12880MA product page](https://www.hamamatsu.com/us/en/product/optical-sensors/spectrometers/mini-spectrometer/C12880MA.html)
  is the authoritative product overview.
- `vendor-board-dimensions.jpg`: vendor image showing a nominal `38.5 x 22.9
  mm` board, `33.6 mm` mounting-hole spacing, and `13.2 mm` from the left hole
  to the sensor axis.
- `user-measured-dimensions.jpg`: caliper-derived module corrections used for
  fit: PCB `38.3 x 22.8 mm`, package up to `20.5 x 13 mm`, package height `15
  mm`, and asymmetric package margins.
- `CCD3D.stp`, `光谱仪C12880使用说明.pdf`, calibration spreadsheets, and
  `file_config.ini`: inert files extracted from the user's vendor archive.

`CCD3D.stp` contains a much larger assembly and TCD1304 identifiers. It is
retained for provenance but is not treated as the exact small C12880MA module
geometry.

## Design Derivation

Using the corrected `38.3 mm` board length and the `33.6 mm` hole spacing gives
`2.35 mm` from either board end to its mounting-hole center. The sensor axis is
therefore `2.35 + 13.2 = 15.55 mm` from the left board edge. Relative to that
axis, the mounting holes are at `-13.2 mm` and `+20.4 mm`; the PCB bounds are
`-15.55 .. +22.75 mm`.

The holder's 42 mm plate is centered at `+3.6 mm`, so both mounting holes are
`16.8 mm` from the plate center and both PCB end margins are `1.85 mm`. The
sensor remains exactly on the C-mount axis even though it is not at the PCB
center.

The six connector solder-tail reliefs use `3.0 mm` overlapping holes on a
`2.54 mm` pitch. Their row position is photo-derived and should be checked
against the physical board before a production print.

## Integrity

| File | SHA-256 |
| --- | --- |
| `CCD3D.stp` | `1f14e417fe9d861bd07ea66f3835aa773098aec803374d5d0e0c2b4bacaacec1` |
| `hamamatsu-c12880ma-datasheet.pdf` | `4ff596fb8aec2cdb813c90076804444bfc0024c82cbab5e9ec4479c7d6dfb08f` |
| `user-measured-dimensions.jpg` | `322e966a3028d82ed94216b57e28e369cd81a121ee602129ccd672ff16ff0f89` |
| `vendor-board-dimensions.jpg` | `23706900b81dee6bbc57c2e240448e4f63a9e89c0e580a5ae8b8f358848e7d53` |
| `光谱仪C12880使用说明.pdf` | `046b0b94e5758e0144d6f1b9cdbbcb1f1ce6bef5886755401ad9042c9fb35719` |
