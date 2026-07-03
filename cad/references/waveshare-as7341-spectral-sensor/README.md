# Waveshare AS7341 Spectral Color Sensor References

Downloaded on 2026-07-03 for the AS7341 C-mount holder design.

## Sources

- Wiki: https://www.waveshare.com/wiki/AS7341_Spectral_Color_Sensor
- Product page: https://www.waveshare.com/as7341-spectral-color-sensor.htm
- Official 3D package: https://files.waveshare.com/wiki/AS7341%20Spectral%20Color%20Sensor/As7341_spectral_color_sensor.rar
- Schematic: https://files.waveshare.com/upload/3/3c/AS7341_Spectral_Color_Sensor_SchDoc.pdf
- Datasheets: https://files.waveshare.com/upload/f/f9/AS7341.pdf and https://files.waveshare.com/upload/f/f9/AS7341_V3.0.pdf

## Files

| File | Purpose |
| --- | --- |
| `wiki.html` | Snapshot of the Waveshare wiki page. |
| `product.html` | Snapshot of the product page. |
| `AS7341_Spectral_Color_Sensor_SchDoc.pdf` | Waveshare schematic. |
| `AS7341.pdf` | AS7341 datasheet. |
| `AS7341_V3.0.pdf` | AS7341 v3.0 datasheet. |
| `As7341_spectral_color_sensor.rar` | Original official 3D drawing archive. |
| `3d/as7341_spectral_color_sensor.stp` | Official STEP reference. |
| `3d/as7341_spectral_color_sensor.dxf` | Official dimension drawing reference. |
| `3d/as7341_spectral_color_sensor.pdf` | Official drawing PDF. |
| `as7341-outline-dimensions.jpg` | Product-page outline-dimension image. |
| `as7341-product-photo.jpg` | Product photo for visual orientation. |
| `previews/as7341_drawing-1.png` | Rasterized drawing preview from the official PDF. |

## Design Values Used

- Breakout outline: `30.5 x 23 mm`.
- Mounting holes: `2 x 2.0 mm`.
- AS7341 optical aperture drawing callout: `0.9 mm`.
- Board thickness from side drawing: `1.6 mm`.
- Overall component envelope from side drawing: about `7.2 mm`.

The new holder in `cad/designs/as7341_cmount_sensor_holder/` uses the AS7341
aperture as the optical origin, not the board center. This matters because the
sensor aperture is close to the top edge of the breakout.
