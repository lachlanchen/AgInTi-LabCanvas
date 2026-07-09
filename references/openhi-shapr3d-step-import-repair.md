# OpenHI Shapr3D STEP Import Repair Lesson

Date: 2026-07-09

This note records why `openhi_a_c_bs_receivers_30p0_30p4_print_fit` finally
imports quickly into Shapr3D after earlier files took a long repair pass, lost
threads, or showed transparent broken regions.

## What Failed

The first print-fit variants directly edited the imported OpenHI STEP B-rep.
Those files were valid according to OCCT, but Shapr3D still had to repair them
slowly. The fragile regions were:

- original helical thread faces stored as B-spline surfaces;
- local boolean edits inside or near the beam-splitter pocket;
- leftover internal shell/sliver faces from fill-and-recut operations;
- thread geometry coupled too tightly to the surrounding imported B-rep.

The important lesson is that "OCCT valid" is not enough for Shapr3D. Shapr3D
is much happier with simple analytic surfaces and clear single-solid topology.

## Source Diagnosis

`cad/extracted/OpenHI.shapr` is a ZIP package containing a SQLite `workspace`.
For this OpenHI body, the workspace records imported Parasolid/STEP bodies and
operation names, but not a clean replayable native Shapr feature tree on
Ubuntu. Therefore the correct strategy is not to reconstruct every Shapr
operation. Use the exported STEP as the geometry baseline and make controlled
variants from it.

The source STEP `cad/extracted/OpenHI_STEP/A+ C + BS.step` measured as:

- one solid;
- bbox `40.0 x 40.0 x 84.9 mm`;
- original receiver starts around `30.2 mm`;
- 6 B-spline thread faces;
- original BS slope/slot geometry worth preserving exactly.

## Fix That Worked

The final builder preserves the original exported STEP body and replaces only
the two fragile receiver/thread regions:

1. Import the original OpenHI A+C+BS STEP body.
2. Add clean analytic sleeve/tube bodies only inside the lower receiver and
   BS-side receiver repair zones.
3. Cut a clean `30.0 mm` pilot through each sleeve.
4. For the directly usable file, cut simple `30.4 mm` ring-groove previews.
5. For the smooth editable file, stop after the clean `30.0 mm` pilots.
6. Export both files and validate the exported STEP by re-importing it.

The key design choice is that the final ring grooves are not true helical
threads. They are simple cylindrical groove previews. This removes the B-spline
thread surfaces that triggered Shapr3D repair. If true editable threads are
needed, import the smooth STEP into Shapr3D and add native Shapr threads or tap
the printed part physically.

## Validation Contract

Before reporting success, validate the actual exported STEP files:

```bash
cad/.conda/cad-python/bin/python - <<'PY'
import cadquery as cq
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_BSplineSurface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

for path in [
    "cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/USE_THIS_openhi_a_c_bs_receivers_30p0_30p4_print_fit.step",
    "cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/artifacts/openhi_a_c_bs_receivers_30p0_30p4_print_fit_smooth_editable.step",
]:
    shape = cq.importers.importStep(path).val()
    exp = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    bspline_faces = 0
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        if BRepAdaptor_Surface(face, True).GetType() == GeomAbs_BSplineSurface:
            bspline_faces += 1
        exp.Next()
    bb = shape.BoundingBox()
    print(path)
    print("solids", len(shape.Solids()), "valid", BRepCheck_Analyzer(shape.wrapped).IsValid())
    print("bbox", round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6))
    print("bspline_faces", bspline_faces)
PY
```

Expected result for the fixed OpenHI A+C+BS files:

- `1` solid;
- valid B-rep;
- bbox `40.0 x 40.0 x 84.9 mm` after STEP round trip;
- `0` B-spline faces in the Shapr-target files.

## Future Rule

When a Shapr import takes a long repair pass, loses threads, or shows
transparent regions, do not keep adding booleans to the same imported B-rep.
First check surface types. If the fragile region contains helical B-spline
thread faces, preserve the stable source body, replace only that region with a
clean analytic sleeve or socket, and export a smooth editable STEP plus one
clear `USE_THIS_*.step` file at the design root.
