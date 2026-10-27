# Motorized Analyzer And Full-Frame CAD Handoff

## Purchased Hardware And Source Authority

The purchased rotary stage is the Yixuan YXRA100 with a 40 mm / 100 W servo.
It carries the complete Hengyang GT090101 mount, not only a loose polarizer.
The manufacturer customer library supplies genuine STEP and dimension sheets;
`cad/references/yixuan-yxra100/download_references.py` retrieves them without
admin login. Catalog identities, byte counts and checksums are recorded in
`downloads.json`. The servo model must not be replaced with the similar-looking
42 mm stepper or 57 mm motor envelope.

The servo STEP has five solids and additional open motor surfaces. Preserve
those vendor surfaces as reference geometry; never silently drop them by
exporting only `.solids()`, and never pass them to a slicer as printable parts.
Measure hole axes from final cylindrical faces. The three mounting holes are
asymmetric, so their coordinates cannot be assumed to lie on a breadboard grid.

## Fixture Design

Project: `cad/designs/yxra100_servo_analyzer_breadboard_mount/`.

The design separates three functions into editable and individually printable
parts: an M6/25 mm breadboard foot, a gusseted motor-side L support, and a
rotating analyzer adapter. The shelf bolts into the stationary stage base;
the motor casing is not its primary load path and the rotor stays free. Four 5.9 mm locating pins
on the 30 mm cage pattern carry the GT090101. Its existing side screws retain
the pins and its manual rotation should be locked. A cage rod must not bridge
the rotating assembly and the stationary sample holder.

The stage is 45 mm thick. It cannot occupy the accepted sample-holder volume.
The current integration puts its bottom at Z=122 mm, its adapter/GT at
Z=167..193 mm, and raises the microscope by 61 mm. The objective is currently
absent, so this gap is acceptable for the illustration. Future objective focus
and working distance are separate checks, not implied by coaxial CAD placement.

No hardware motion, motor connection or acquisition command was issued.
The printed stand is a fit/clearance prototype; no load/creep/thermal safety
qualification is claimed for supporting the roughly 1.85 kg servo stage.
Final metrology benefits from a metal support and a physical load/clearance test.

`build_mount.py` proves source hole coordinates, STEP round trips, relevant
part intersections, a sampled rotation sweep, and the print package contract.
`render_mount.py` supplies full, detail, exploded and exact-print views.
`sync_handoff.py` copies a clean checksum-verified run to Nutstore.

## Removable Motor Yoke Extension

Run 2 adds a square-Y lower fork and a removable top bridge without changing
the three accepted run-1 fixture bodies. One lower variant shares the existing
stand-foot M6 screws; the other has an outboard foot on the 25 mm table grid.
Install only one lower variant. The same cap fits both.

Use two real M3 x 16 screws and captive metal M3 nuts, rather than small printed
threads. The cap's screw holes are 3.4 mm and the nut pockets are 5.7 mm across
flats x 2.6 mm high. Motor support remains secondary to the stage-base screws.
The 41 mm square envelope leaves 0.5 mm around the genuine 40 mm casing;
optional thin compliant pads can take up clearance without crushing the case.

The motor reference includes open surfaces, so measuring only closed solids
misses the casing. `build_motor_yoke.py` sections the complete motor with OCCT
at X=91, 97, 103 and 105. The selected X=91..103 band clears the connectors.
It checks rotor, support, casing, M3/M6 paths and the central aperture before
export. The genuine 30 mm opening is unchanged; a 29.8 mm through-core is clear.

Anti-warp ears must attach to the actual print-bed footprint. On an offset
yoke, the overall XY bounding box includes the elevated fork. Placing ears
at those bounds can leave detached islands. Pass explicit foot bounds to
`ears(..., base_bounds=...)`, then reject any print mesh with more than one
connected component. The cap prints upside down on its broad top face.

## Stable Direct-Print Exports

The foot prints flat, the L support prints on its outer upright face, and the
rotating adapter prints flat with pins upward. The large flat contact faces
receive 1 mm sacrificial full-corner ears. Each `PRINT_THIS` package is one
physical part, grounded at Z=0, watertight, with one 3MF build item and a
nonempty first layer. Stage/microscope/reference bodies stay out of print files.

OCCT can return conservative padded bounding boxes extending slightly below
a planar base. Grounding only by that box caused a roughly 0.001 mm artificial
lift. Ground the real planar vertices and verify the exported mesh's actual
minimum Z; do not disable the first-layer check or alter correct geometry.

## Full-Frame Rendering

The earlier fixed-analyzer figure cropped an edge detector because it used a
fixed orthographic zoom. `cad/tools/blender_camera_fit.py` now projects every
selected object's world bounding-box corners into the actual camera, adjusts
for Blender's aspect/sensor-fit behavior, and enforces an 8% image margin.
Both fixture and apparatus renderers share that helper. Do not equate a
reasonable camera distance with proof that all output detectors fit the image.

The earlier lower-stack detail is intentionally local and remains unchanged.
All full-apparatus views and detector details now include their complete
selected objects. Camera-space bounds are retained in `camera_validation.json`.
Use auto-smoothed, angle-limited normals on curved CAD surfaces and keep sharp
planar edges; unconstrained smooth shading creates misleading triangular bands.

## Vertical Cascade Variant

Project: `cad/designs/openhi_vertical_multimodal_microscope_setup/`.
Run 1 remains archived, including its original images. Run 2 adds
`dual_4f_vertical` and fixes full-frame camera placement without changing the
existing single/lateral-cascade geometry. Those two configurations retain
identical solid counts, bounds and volume relative to run 1.

The vertical variant joins first B output to second A input with a 3 mm gap.
The first lateral output carries the frame camera; the second lateral output
carries C12880MA; the second straight output carries the event-camera proxy.
The original B-axis correction is -0.367 mm per relay. Therefore the second
A input is X=-0.367 mm and its B output is X=-0.734 mm, not zero. Preserving
mechanical alignment still does not certify exact detector conjugates.

Both source CAD and all earlier runs are preserved. Final full assemblies,
figures and manifests are synced to descriptive run folders under
`/home/lachlan/Nutstore Files/Projects/LabCanvas/`.

## Remote Context Boundary

CSG1175-P and its DualLampHI/SPICE sessions were requested as experiment
context, but this workstation's installed LazyTunnel fleet did not include
that host. Its configured native UU terminal refused a new shell because
another remote controller owns the device. No takeover or logout was attempted.
No claim is made that those session histories or the remote polarizer project
were read. Local accepted experiment CAD and supplier files are the verified
sources for this run. Read-only remote integration can resume when an authorized
non-disruptive shell route becomes available.
