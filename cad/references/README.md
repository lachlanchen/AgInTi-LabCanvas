# CAD References

This folder stores source-backed reference notes for AppAutoAction mechanical design work. Keep concise scale tables here so generated parts can be checked in CAD, slicers, and printed test coupons.

## Current References

- `cmount-reflector-adapter-scale.md`: 1:1 scale model, C-mount thread assumptions, OpenHI/Nature STEP thread clues, and print-check dimensions for the reflector adapter.
- `cmount-threaded-reflector-assembly-scale.md`: two-part reflector holder assembly scale table, tube threading direction, and old A/B/C 4f design evidence.
- `cad-toolchain.md`: installed OpenSCAD, Blender, FreeCAD, and CAD Python kernel setup for this repository.

## Scale Rule

Use millimetres as the default mechanical unit. A generated part should import into a slicer or CAD viewer at `100%` scale unless the reference file explicitly states otherwise.
