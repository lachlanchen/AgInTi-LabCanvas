# AS7343 Spectral Analysis Module References

Local reference snapshot copied from:

```text
/home/lachlan/Downloads/AS7343光谱分析模块
```

## Files

- `AS7343光谱分析模块原理图.png`: module schematic image from `www.mjkdz.com`.
- `资料/AS7343_DS001046_6-00.pdf`: ams OSRAM AS7343 datasheet.
- `资料/AS7343_UG001009_2-00.pdf`: AS7343 evaluation kit user guide.
- `资料/AS7343_*`: calibration, quick guide, register, and SMUX notes.
- `arduino函数库/AMS_OSRAM_AS7343-master.zip`: AS7343 Arduino example library.

## Mechanical Notes

The provided files do not include a module PCB outline, STEP, DXF, or measured
mounting-hole drawing. The C-mount holder in
`cad/designs/as7343_cmount_spectral_module_holder/` therefore uses a parametric
centered tray and centers the AS7343 package on the optical axis. Measure the
real PCB before printing if the board must fit tightly.

Chip-level values used by the holder:

- AS7343 package: `3.1 x 2 x 1 mm`.
- Spectral range: approximately `380-1000 nm`.
- I2C address: `0x39`.
