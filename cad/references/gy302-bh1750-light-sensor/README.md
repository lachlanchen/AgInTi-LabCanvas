# GY-302 BH1750 Light Sensor References

Local reference snapshot copied from:

```text
/home/lachlan/Downloads/GY-302 BH1750
```

## Files

- `1. 数据手册/BH1750FVI.pdf`: ROHM BH1750FVI ambient light sensor datasheet.
- `2. 原理图/GY-302原理图.jpg`: GY-302 module schematic with BH1750, regulator, pullups, and 1x5 header.

## Mechanical Notes

This local reference set does not include a STEP, DXF, or dimensioned PCB
drawing. The matching holder at
`cad/designs/gy302_bh1750_cmount_light_sensor_holder/` therefore uses a
parametric `14 x 19 mm` tray from common GY-302 module dimensions, centers the
BH1750 photodiode datum on the optical axis, and exposes editable board-hole,
header-relief, and sensor-offset parameters for caliper correction.
