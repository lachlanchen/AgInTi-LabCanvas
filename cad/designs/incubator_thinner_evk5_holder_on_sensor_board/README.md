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
- `figA2_incubator_overview_clean_slider`: the overview without the two
  vertical rails (`Body 170`, `Body 170 (1)`) and without the light-path line,
  plus a proposed slider carriage under the FSL30 stage rail, the repo's
  Lumileds cage holder (`cad/designs/lumileds_pcb_aligned_sink_cage_holder`)
  screwed under the carriage, and the Lumileds board
  (`pcb/lumileds-no-resistor`, KiCad STEP) seated in the holder's rear sink with
  its LED facing down on the light path (LED proxy 3 x 3 x 1.4 mm because the
  footprint has no 3D model). That layer is illustration only: it lives in
  `artifacts/proposal/stage_slider_with_lumileds_pcb_proposal.step`, is not
  merged into `USE_THIS_*.step`, and its numbers are in `manifest.json` under
  `figure_proposal`. The carriage is measured from the module's own faces at
  the light-path X, not from its bounding box: the body underside is at
  z 334.30 with a 12 mm guide rib to z 330.30 and the ball screw (r 4) at
  z 317.30. The carriage (60 x 30 x 25 mm) runs against the body underside,
  slots over the rib and wraps the screw with a 1 mm clearance bore; the LED
  holder is screwed directly under it (z 301.3..309.3) and the LED sits
  96.7 mm above the grating. No collision with any model part; one 37 mm3
  overlap between the horizontal pin-header body and the holder rim that a
  real build would relieve.
- `artifacts/paper_figure/paper_figures_labelled.pptx` (also copied as
  `FIGURE_paper_figures_labelled_editable.pptx`): one 4:3 slide per figure with
  the render as the picture and every label as a native PowerPoint text box
  (Arial 14 pt, white rounded box, 0.75 pt grey outline) joined to its anchor
  dot by a straight connector, so wording, font, box style and positions can
  be edited directly. Built by `make_paper_figure_pptx.py` (needs python-pptx;
  the miniconda base `python3` has it); label wording and positions are the
  `LABELS` and `FIGS` tables in that script, provenance is in the slide notes.
- The design root and the Nutstore folder carry copies of the key images as
  `FIGURE_overview_clean_with_stage_slider_led.png`,
  `FIGURE_front_elevation_alignment_labelled.png` and
  `FIGURE_overview_with_light_path_line.png` so the latest versions are easy to
  find without opening a run folder.
- `figF_front_elevation_alignment`: orthographic front elevation showing the
  slider, LED holder, grating window and EVK5 holder on one vertical line, which
  proves the slider is at the light-path X (box centre), not at the rail end.

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
