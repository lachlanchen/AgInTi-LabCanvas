# Waveshare TSL25911 Light Sensor References

Local reference snapshot for the TSL25911 intensity/light sensor holder.

## Sources

- Wiki: <https://www.waveshare.net/wiki/TSL25911_Light_Sensor>
- Product page: <https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm>
- Example code: <https://github.com/waveshare/TSL2591X-Light-Sensor>

## Downloaded Files

- `wiki.html`: local wiki snapshot.
- `product.html`: local product page snapshot.
- `TSL2591X_Light_Sensor_SchDoc.pdf`: Waveshare schematic.
- `TSL2591.pdf`: TSL2591/TSL25911 datasheet.
- `TSL2591X_Light_Sensor_code.7z`: vendor example code package.
- `TSL25911-Light-Sensor-size_960.jpg`: dimension drawing used for holder geometry.
- `TSL25911-Light-Sensor-*.jpg`, `TSL25911-Pi-WS.jpg`: product and wiring images.

## Design Values Used

- Sensor board: `27 x 20 mm`.
- Mounting holes: two `2.0 mm` holes on the left side, `16 mm` vertical spacing.
- I2C address: `0x29`.
- Measurement range: `0-88000 Lux`.
- Supply/logic compatibility: `3.3V/5V`.

No official STEP package was found in the vendor resources available here. The
holder therefore uses the vendor size image as the board outline source and
keeps the TSL25911 sensing-window offset parametric in the build script.
