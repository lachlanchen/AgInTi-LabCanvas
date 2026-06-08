# HYBEC HBL-273 / HBL-667 G4 Halogen Carrier PCB

![3D render of the HYBEC G4 carrier PCB](artifacts/hybec-hbl-273-g4-render.png)

This generated KiCad project adapts the existing NHI LED carrier style to a
two-hole direct-insertion G4 halogen lamp footprint.

- Board outline: circular, 24 mm diameter, matching the old LED carrier files.
- Mounting holes: four M2 NPTH holes at the same coordinates as the old boards.
- Lamp pins: two 1.20 mm plated holes on 4.00 mm G4 pitch.
- Power path: 1.20 mm top-layer copper tracks from the rear 1x02 input header.
- Lamp: 12 V, 20 W tungsten halogen, approximately 1.67 A.

Thermal note: a 20 W halogen lamp runs hot. Treat this PCB as a mechanical and
electrical adapter prototype; verify lamp standoff height, FR4 temperature,
airflow, and enclosure clearance before powering it in an instrument.

## Files

- `hybec-hbl-273-g4.kicad_pcb`: generated KiCad PCB.
- `hybec-hbl-273-hbl-667-lamp-dataset.json`: lamp specification dataset and source links.
- `artifacts/hybec-hbl-273-g4-render.png`: KiCad 3D render for review.
- `artifacts/hybec-hbl-273-g4.step`: STEP export.
- `gerber/`: Gerber and Excellon drill outputs.

## Reproduce

```bash
python3 pcb/scripts/generate_hybec_halogen_g4_board.py
kicad-cli pcb drc --format json --severity-all -o pcb/hybec-hbl-273-g4/artifacts/drc.json pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb
xvfb-run -a kicad-cli pcb render --output pcb/hybec-hbl-273-g4/artifacts/hybec-hbl-273-g4-render.png --width 1400 --height 1000 --background opaque --quality high --floor --perspective --rotate 315,0,35 --zoom 2.2 pcb/hybec-hbl-273-g4/hybec-hbl-273-g4.kicad_pcb
```
