# Incubator thinner: EVK 5 holder moved onto the sensor board

Date: 2026-09-16

## Use This

- `USE_THIS_incubator_thinner_evk5_holder_on_sensor_board_assembly_moved.step`:
  the complete export with only the `EVK 5 holder` group translated. Import it
  into Shapr3D to see the result; names are preserved as
  `root > group > part`.
- `artifacts/evk5_holder_group_moved.step` (`.stl`, `.3mf`): only the five
  holder solids at the new position.
- `artifacts/evk5_holder_group_original_position.step`: the same five solids
  exactly as exported, for comparison.
- `artifacts/incubator_context_unchanged.step`: every other solid, untouched.
- `artifacts/light_path_axis_reference.step`: a 1 mm rod on the optical axis
  from below the sensor plate to above the grating. Reference only.
- `artifacts/manifest.json`: numbers, checks, source hashes.
- `artifacts/renders/`: engineering check views (overview with the original
  position as a ghost, inside view, top view, side elevation, holder detail).
- `artifacts/paper_figure/`: publication renders, 2400 x 1800 px, EEVEE, white
  background. For each of `figA_incubator_overview`, `figB_optical_stack`,
  `figC_holder_under_grating_closeup`, `figD_top_view_centred`,
  `figE_section_through_light_path` there is a plain `.png`, a
  `_transparent.png` for compositing, and a `_labelled` `.png`/`.pdf`/`.svg`
  with leader-line labels (EVK5 holder, sensor board, diffraction grating,
  light path, shelf window, incubator). Regenerate with
  `render_paper_figure_incubator_thinner_evk5_holder.py` (Blender) followed by
  `compose_paper_figure_labels.py` (CAD Python); label wording and positions
  are the `LABELS` and `FIGS` tables in the compose script.

## What Was Asked

Move the `EVK 5 holder` group from outside the incubator to above the sensor
board, centred and aligned on the light path, and change nothing else.

## What Was Done

One rigid translation applied to all five solids under the `EVK 5 holder`
folder of the user's Shapr3D export `incubator+thinner.step`. Those five bodies
are, by their STEP labels: `EVK 5 holder (3)` (base with the camera pocket),
`Dam 1 (3)` and `Dam 2 (3)` (light-dam walls), `Sample holder outskirt (8)` and
`(9)` (light-dam sides). The folder's `Aux` subfolder is empty in the export.

```text
dx = 0.000 mm
dy = +220.000 mm
dz = +129.000 mm
```

To repeat the move natively in Shapr3D: select the `EVK 5 holder` folder and
Move by `Y +220 mm`, `Z +129 mm`.

Rule that produced the vector:

1. Optical axis: the sensor board (`Sensor board EBS 0cm (2)*2 (2)` under
   `NHI in incubator / Sensor`) is `200 x 100 x 3 mm`; its XY centre `(141.250, 143.073)` is identical to the
   `Diffraction grating` centre and to the centre of the grating's innermost
   `25.5 mm` square window, so that vertical line is the light path.
2. Lateral: the holder group's XY bounding-box centre, which is also the centre
   of its `26 x 26 mm` camera pocket and of the four light-dam walls, is placed
   on that axis.
3. Vertical: the holder base's lowest face is placed on the sensor plate's top
   face (`z = 129.302 mm`), so the group sits on the board.

## Result Numbers

| Item | Value |
| --- | --- |
| Holder group after move (bbox, mm) | `x 102.75..179.75`, `y 110.82..175.32`, `z 129.30..146.30` |
| Base contact area on the plate | `911 mm2` (35 x 35 base minus its holes) |
| Clearance holder top to grating bottom | `51.0 mm` |
| Holder to plate edge | `61.5 mm` in X, `17.75 mm` in Y |
| Upper shelf window above the holder | `100 x 100 mm`, holder footprint inside it |
| Interference with any unchanged solid | none |
| Holder solid count and volume | unchanged (5 solids) |

All checks are recorded in `manifest.json` under `checks`.

## Not Included

- The export contains no `EVK 5` camera body. In the archive the `EVK 5`
  folder (five imported camera bodies) sits under the hidden `NHI` folder, not
  under `EVK 5 holder`, so Shapr3D skipped it. Unhide `NHI` > `EVK 5` and export
  it, and the build can align the camera's lens axis instead of the pocket
  centre and add the camera to the renders.
- Nothing else in the model was edited. One vendor stage solid
  (`零件41^FSL30-BC-B35`, 796 faces) is reported invalid by OCCT already in the
  source export; it is copied through unchanged.

## Observation (not acted on)

The sensor plate sits exactly `17.0 mm` above the lower shelf, and the holder
group is exactly `17.0 mm` tall, while the lower shelf carries a plate-sized
`3 mm` pocket. If the intended stack is shelf pocket, holder, plate on top of
the holder, say so and the translation becomes `dz = +109.0 mm` with the plate
untouched; the build script only needs the target face changed.

## Rebuild

```bash
cad/.conda/cad-python/bin/python cad/designs/incubator_thinner_evk5_holder_on_sensor_board/build_incubator_thinner_evk5_holder_on_sensor_board.py --no-sync
blender --background --python cad/designs/incubator_thinner_evk5_holder_on_sensor_board/render_incubator_thinner_evk5_holder_on_sensor_board.py
cad/.conda/cad-python/bin/python cad/designs/incubator_thinner_evk5_holder_on_sensor_board/build_incubator_thinner_evk5_holder_on_sensor_board.py --package
```

`--package` creates `runs/run-1-holder-on-sensor-board-<timestamp>/` and mirrors
it with the `USE_THIS` file to
`/home/lachlan/Nutstore Files/Projects/LabCanvas/incubator_thinner_evk5_holder_on_sensor_board/`.

## Sources

- STEP: `/home/lachlan/Downloads/incubator+thinner.step` (Shapr3D 26.113 export,
  2026-09-16 17:09 +08:00), SHA-256 in the manifest.
- Archive: `/home/lachlan/Nutstore Files/Projects/shapr3d/BACKUP/BATCHEXPORT/Incubator thinner.shapr`,
  decoded for folder names, placement history, and sketches with the
  `parametric-cad-design` skill's `shapr_native_decoder.py`.
