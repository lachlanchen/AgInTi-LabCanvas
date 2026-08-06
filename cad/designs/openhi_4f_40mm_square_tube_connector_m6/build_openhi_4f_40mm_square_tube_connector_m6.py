#!/usr/bin/env python3
"""Build a square sleeve that joins two 40 mm OpenHI 4F tubes."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import trimesh
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_BSplineSurface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
RUN_NAME = (
    "run-1-40mm-id-8x-m6-chamfered-center-stop-print-ready-"
    "20260806T022512Z"
)
RUN_DIR = DESIGN_DIR / "runs" / RUN_NAME
RUN_ARTIFACT_DIR = RUN_DIR / "artifacts"
STEM = "openhi_4f_40mm_square_tube_connector_m6"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / STEM / RUN_NAME
)

sys.path.insert(0, str(ROOT / "cad" / "tools"))
from simple_3mf import export_stl_as_3mf  # noqa: E402


THREAD_OVERLAP = 0.02
PARAMS = {
    "name": STEM,
    "design_mode": "new clean parametric print-fit design",
    "tube_measured_outer_diameter_mm": 39.8,
    "connector_bore_diameter_mm": 40.0,
    "tube_total_diametral_clearance_mm": 0.2,
    "tube_radial_clearance_mm": 0.1,
    "outer_square_mm": 42.0,
    "connector_length_mm": 62.0,
    "nominal_face_wall_thickness_mm": 1.0,
    "center_stop_z_mm": 31.0,
    "center_stop_radial_height_mm": 2.0,
    "center_stop_minimum_opening_diameter_mm": 36.0,
    "center_stop_chamfer_angle_deg": 45.0,
    "center_stop_axial_base_width_mm": 4.0,
    "center_stop_lower_z_mm": 29.0,
    "center_stop_upper_z_mm": 33.0,
    "center_stop_profile": (
        "triangular annular ridge: 40 mm opening at z=29, 36 mm at z=31, "
        "40 mm at z=33"
    ),
    "radial_fastener_count": 8,
    "fasteners_per_tube_end": 4,
    "fastener_axial_stations_z_mm": [15.5, 46.5],
    "fastener_tangential_offset_mm": 14.5,
    "fastener_pattern": (
        "one radially inward set screw per square face at each axial station; "
        "face locations rotate cyclically around the tube"
    ),
    "female_thread_nominal": "M6 x 1.0 right-hand",
    "female_thread_pitch_mm": 1.0,
    "female_thread_pilot_diameter_mm": 5.0,
    "female_thread_cutter_crest_diameter_mm": 6.0,
    "female_thread_tooth_radial_height_mm": 0.5,
    "thread_triangle_base_width_mm": 0.58,
    "female_thread_cutter_axis_length_mm": 12.0,
    "thread_runout_extra_cycles_each_end": 0.5,
    "thread_runout_extra_length_each_end_mm": 0.5,
    "thread_hand": "right-hand; matching cutter and screw helices",
    "male_set_screw_crest_diameter_mm": 5.8,
    "male_set_screw_root_diameter_mm": 4.8,
    "male_diametral_print_reduction_mm": 0.2,
    "male_thread_length_mm": 12.0,
    "male_head_style": "hex head",
    "male_head_across_flats_mm": 10.0,
    "male_head_height_mm": 4.0,
    "male_set_screw_print_count": 8,
    "male_set_screw_grid": "4 x 2, printed vertically with hex heads on bed",
    "print_orientation_connector": (
        "42 x 42 mm end face on build plate; tube axis vertical"
    ),
    "print_orientation_set_screw": "hex head on build plate; thread axis vertical",
    "physical_fit_note": (
        "The 40.0 mm bore gives 0.2 mm diametral clearance around the measured "
        "39.8 mm tube. Print one connector and one screw first; clean horizontal "
        "female threads with an M6 x 1.0 tap if the printer leaves rough crests."
    ),
}


def x_cylinder(diameter: float, length: float, x0: float) -> cq.Workplane:
    return (
        cq.Workplane("YZ")
        .workplane(offset=x0)
        .circle(diameter / 2.0)
        .extrude(length)
    )


def z_cylinder(diameter: float, height: float, z0: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .workplane(offset=z0)
        .circle(diameter / 2.0)
        .extrude(height)
    )


def z_cone(
    diameter0: float,
    diameter1: float,
    height: float,
    z0: float,
) -> cq.Workplane:
    solid = cq.Solid.makeCone(
        diameter0 / 2.0,
        diameter1 / 2.0,
        height,
        cq.Vector(0.0, 0.0, z0),
        cq.Vector(0.0, 0.0, 1.0),
    )
    return cq.Workplane(obj=solid)


def x_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(length, span, span, centered=(False, True, True))
        .translate((x0, 0.0, 0.0))
    )


def x_thread_tooth(
    *,
    x0: float,
    length: float,
    root_diameter: float,
    crest_diameter: float,
    pitch: float,
    triangle_base: float,
    extra_each_end: float,
) -> cq.Workplane:
    """Sweep one bounded triangular thread with half-pitch runout."""
    tooth_height = (crest_diameter - root_diameter) / 2.0
    sweep_x0 = x0 - extra_each_end
    sweep_length = length + 2.0 * extra_each_end
    root_radius = root_diameter / 2.0 - THREAD_OVERLAP
    path = cq.Wire.makeHelix(
        pitch,
        sweep_length,
        root_radius,
        center=(sweep_x0, 0.0, 0.0),
        dir=(1.0, 0.0, 0.0),
        lefthand=False,
    )
    profile = (
        cq.Workplane("XY")
        .center(sweep_x0, root_radius)
        .polyline(
            [
                (0.0, 0.0),
                (triangle_base / 2.0, tooth_height + THREAD_OVERLAP),
                (triangle_base, 0.0),
            ]
        )
        .close()
    )
    swept = profile.sweep(path, isFrenet=True, combine=False)
    return swept.intersect(x_clip_box(x0, length, crest_diameter + 4.0))


def build_base_connector() -> cq.Workplane:
    """Build the square shell and support-friendly center stop."""
    p = PARAMS
    body = cq.Workplane("XY").box(
        p["outer_square_mm"],
        p["outer_square_mm"],
        p["connector_length_mm"],
        centered=(True, True, False),
    )
    # Four cutter segments leave a triangular annular stop at the middle.
    body = body.cut(
        z_cylinder(
            p["connector_bore_diameter_mm"],
            p["center_stop_lower_z_mm"] + 0.1,
            -0.1,
        )
    )
    body = body.cut(
        z_cone(
            p["connector_bore_diameter_mm"],
            p["center_stop_minimum_opening_diameter_mm"],
            p["center_stop_z_mm"] - p["center_stop_lower_z_mm"],
            p["center_stop_lower_z_mm"],
        )
    )
    body = body.cut(
        z_cone(
            p["center_stop_minimum_opening_diameter_mm"],
            p["connector_bore_diameter_mm"],
            p["center_stop_upper_z_mm"] - p["center_stop_z_mm"],
            p["center_stop_z_mm"],
        )
    )
    body = body.cut(
        z_cylinder(
            p["connector_bore_diameter_mm"],
            p["connector_length_mm"] - p["center_stop_upper_z_mm"] + 0.1,
            p["center_stop_upper_z_mm"],
        )
    )
    return body.clean()


def radial_hole_frames() -> list[dict[str, float | str]]:
    p = PARAMS
    offset = p["fastener_tangential_offset_mm"]
    faces = [
        {
            "face": "-X",
            "start_x": -p["outer_square_mm"] / 2.0,
            "start_y": -offset,
            "rotation_z_deg": 0.0,
        },
        {
            "face": "-Y",
            "start_x": offset,
            "start_y": -p["outer_square_mm"] / 2.0,
            "rotation_z_deg": 90.0,
        },
        {
            "face": "+X",
            "start_x": p["outer_square_mm"] / 2.0,
            "start_y": offset,
            "rotation_z_deg": 180.0,
        },
        {
            "face": "+Y",
            "start_x": -offset,
            "start_y": p["outer_square_mm"] / 2.0,
            "rotation_z_deg": -90.0,
        },
    ]
    return [
        {**face, "z": z}
        for z in p["fastener_axial_stations_z_mm"]
        for face in faces
    ]


def orient_local_x(shape: cq.Workplane, frame: dict[str, float | str]) -> cq.Workplane:
    return shape.rotate(
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        float(frame["rotation_z_deg"]),
    ).translate(
        (
            float(frame["start_x"]),
            float(frame["start_y"]),
            float(frame["z"]),
        )
    )


def female_pilot_local() -> cq.Workplane:
    # Extend outside both endpoints so every face and bore mouth is fully cut.
    return x_cylinder(
        PARAMS["female_thread_pilot_diameter_mm"],
        PARAMS["female_thread_cutter_axis_length_mm"] + 1.0,
        -0.5,
    )


def female_thread_local() -> cq.Workplane:
    p = PARAMS
    return x_thread_tooth(
        x0=0.0,
        length=p["female_thread_cutter_axis_length_mm"],
        root_diameter=p["female_thread_pilot_diameter_mm"],
        crest_diameter=p["female_thread_cutter_crest_diameter_mm"],
        pitch=p["female_thread_pitch_mm"],
        triangle_base=p["thread_triangle_base_width_mm"],
        extra_each_end=p["thread_runout_extra_length_each_end_mm"],
    )


def female_cutter_local() -> cq.Workplane:
    return female_pilot_local().union(female_thread_local()).clean()


def build_connector(*, threaded: bool) -> cq.Workplane:
    body = build_base_connector()
    local = female_cutter_local() if threaded else female_pilot_local()
    for frame in radial_hole_frames():
        body = body.cut(orient_local_x(local, frame))
    return body.clean()


def build_all_female_thread_cutters() -> cq.Workplane:
    result: cq.Workplane | None = None
    for frame in radial_hole_frames():
        cutter = orient_local_x(female_cutter_local(), frame)
        result = cutter if result is None else result.union(cutter)
    if result is None:
        raise RuntimeError("No female thread cutters were generated")
    return result


def build_set_screw_local() -> cq.Workplane:
    """Build one M6-class printed set screw, axis along local +X."""
    p = PARAMS
    head_circumscribed_diameter = p["male_head_across_flats_mm"] / math.cos(
        math.radians(30.0)
    )
    head = (
        cq.Workplane("YZ")
        .workplane(offset=-p["male_head_height_mm"])
        .polygon(6, head_circumscribed_diameter)
        .extrude(p["male_head_height_mm"])
    )
    root = x_cylinder(
        p["male_set_screw_root_diameter_mm"],
        p["male_thread_length_mm"] + 0.05,
        -0.05,
    )
    thread = x_thread_tooth(
        x0=0.0,
        length=p["male_thread_length_mm"],
        root_diameter=p["male_set_screw_root_diameter_mm"],
        crest_diameter=p["male_set_screw_crest_diameter_mm"],
        pitch=p["female_thread_pitch_mm"],
        triangle_base=p["thread_triangle_base_width_mm"],
        extra_each_end=p["thread_runout_extra_length_each_end_mm"],
    )
    return head.union(root).union(thread).clean()


def build_set_screw_print_vertical() -> cq.Workplane:
    # Rotate +X to +Z, then raise the head bottom to z=0.
    return build_set_screw_local().rotate(
        (0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        -90.0,
    ).translate((0.0, 0.0, PARAMS["male_head_height_mm"]))


def build_set_screw_grid() -> cq.Workplane:
    screw = build_set_screw_print_vertical()
    spacing = 14.0
    result: cq.Workplane | None = None
    for row in range(2):
        for col in range(4):
            item = screw.translate(
                ((col - 1.5) * spacing, (row - 0.5) * spacing, 0.0)
            )
            result = item if result is None else result.union(item)
    if result is None:
        raise RuntimeError("No set screws were generated")
    return result


def build_assembled_set_screws() -> cq.Workplane:
    result: cq.Workplane | None = None
    for frame in radial_hole_frames():
        screw = orient_local_x(build_set_screw_local(), frame)
        result = screw if result is None else result.union(screw)
    if result is None:
        raise RuntimeError("No assembled set screws were generated")
    return result


def build_tube_proxy(z0: float, length: float) -> cq.Workplane:
    return z_cylinder(PARAMS["tube_measured_outer_diameter_mm"], length, z0)


def build_section(connector: cq.Workplane) -> cq.Workplane:
    p = PARAMS
    half_box = (
        cq.Workplane("XY")
        .box(
            p["outer_square_mm"] / 2.0,
            p["outer_square_mm"] + 4.0,
            p["connector_length_mm"] + 4.0,
            centered=(False, True, False),
        )
        .translate((0.0, 0.0, -2.0))
    )
    return connector.intersect(half_box).clean()


def build_fit_check_assembly(
    connector: cq.Workplane,
    screws: cq.Workplane,
) -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_fit_check_assembly")
    assembly.add(
        connector,
        name="printed_square_connector_threaded",
        color=cq.Color(0.10, 0.48, 0.72, 1.0),
    )
    assembly.add(
        screws,
        name="eight_printed_m6_set_screws",
        color=cq.Color(0.22, 0.24, 0.28, 1.0),
    )
    assembly.add(
        build_tube_proxy(-11.0, 40.0),
        name="lower_openhi_tube_od39p8",
        color=cq.Color(0.92, 0.42, 0.10, 0.72),
    )
    assembly.add(
        build_tube_proxy(33.0, 40.0),
        name="upper_openhi_tube_od39p8",
        color=cq.Color(0.92, 0.42, 0.10, 0.72),
    )
    return assembly


def export_shape(
    shape: cq.Shape | cq.Workplane,
    step_path: Path,
    stl_path: Path,
) -> None:
    cq.exporters.export(shape, str(step_path))
    cq.exporters.export(
        shape,
        str(stl_path),
        tolerance=0.018,
        angularTolerance=0.06,
    )


def export_assembly(
    assembly: cq.Assembly,
    step_path: Path,
    stl_path: Path,
) -> None:
    export_shape(assembly.toCompound(), step_path, stl_path)


def validate_step(path: Path) -> dict[str, object]:
    imported = cq.importers.importStep(str(path))
    solids = imported.solids().vals()
    bbox = imported.val().BoundingBox()
    faces = TopExp_Explorer(imported.val().wrapped, TopAbs_FACE)
    face_count = 0
    bspline_face_count = 0
    while faces.More():
        face_count += 1
        face = TopoDS.Face_s(faces.Current())
        if (
            BRepAdaptor_Surface(face, True).GetType()
            == GeomAbs_BSplineSurface
        ):
            bspline_face_count += 1
        faces.Next()
    return {
        "exists": path.is_file(),
        "bytes": path.stat().st_size,
        "solid_count": len(solids),
        "all_brep_valid": bool(solids)
        and all(BRepCheck_Analyzer(solid.wrapped).IsValid() for solid in solids),
        "bbox_mm": [round(bbox.xlen, 4), round(bbox.ylen, 4), round(bbox.zlen, 4)],
        "volume_mm3": round(sum(solid.Volume() for solid in solids), 4),
        "face_count": face_count,
        "bspline_face_count": bspline_face_count,
    }


def validate_stl(path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(path, force="mesh")
    return {
        "exists": path.is_file(),
        "bytes": path.stat().st_size,
        "watertight": bool(mesh.is_watertight),
        "component_count": len(mesh.split(only_watertight=False)),
        "body_count": int(mesh.body_count),
        "bbox_mm": [round(float(value), 4) for value in mesh.extents],
        "face_count": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.namelist())
        bad_member = archive.testzip()
    return {
        "exists": path.is_file(),
        "bytes": path.stat().st_size,
        "zip_valid": bad_member is None and "3D/3dmodel.model" in members,
        "members": members,
    }


def geometry_checks() -> dict[str, object]:
    p = PARAMS
    hole_radius = p["female_thread_cutter_crest_diameter_mm"] / 2.0
    minimum_offset_radius = p["fastener_tangential_offset_mm"] - hole_radius
    maximum_offset_radius = p["fastener_tangential_offset_mm"] + hole_radius
    min_thread_engagement = p["outer_square_mm"] / 2.0 - math.sqrt(
        (p["connector_bore_diameter_mm"] / 2.0) ** 2
        - minimum_offset_radius**2
    )
    centerline_engagement = p["outer_square_mm"] / 2.0 - math.sqrt(
        (p["connector_bore_diameter_mm"] / 2.0) ** 2
        - p["fastener_tangential_offset_mm"] ** 2
    )
    return {
        "tube_diametral_clearance_mm": round(
            p["connector_bore_diameter_mm"]
            - p["tube_measured_outer_diameter_mm"],
            4,
        ),
        "tube_radial_clearance_mm": round(
            (
                p["connector_bore_diameter_mm"]
                - p["tube_measured_outer_diameter_mm"]
            )
            / 2.0,
            4,
        ),
        "center_stop_radial_height_mm": p["center_stop_radial_height_mm"],
        "center_stop_axial_base_width_mm": p["center_stop_axial_base_width_mm"],
        "center_stop_chamfer_angle_deg": p["center_stop_chamfer_angle_deg"],
        "minimum_thread_material_length_over_full_crest_mm": round(
            min_thread_engagement, 4
        ),
        "thread_material_length_at_hole_centerline_mm": round(
            centerline_engagement, 4
        ),
        "thread_hole_outer_edge_ligament_mm": round(
            p["outer_square_mm"] / 2.0 - maximum_offset_radius,
            4,
        ),
        "female_thread_pitch_mm": p["female_thread_pitch_mm"],
        "male_thread_pitch_mm": p["female_thread_pitch_mm"],
        "male_crest_clearance_to_female_cutter_mm": round(
            p["female_thread_cutter_crest_diameter_mm"]
            - p["male_set_screw_crest_diameter_mm"],
            4,
        ),
        "expected_connector_bbox_mm": [42.0, 42.0, 62.0],
        "expected_set_screw_bbox_mm": [
            round(p["male_head_across_flats_mm"] / math.cos(math.radians(30.0)), 4),
            10.0,
            16.0,
        ],
    }


def feature_checks(connector: cq.Workplane, tap_ready: cq.Workplane) -> dict[str, object]:
    threaded = connector.val()
    smooth = tap_ready.val()
    checks = {
        "bore_clear_at_r19_z10": not threaded.isInside(
            cq.Vector(19.0, 0.0, 10.0), 1e-6
        ),
        "center_stop_material_at_r19_z31": threaded.isInside(
            cq.Vector(19.0, 0.0, 31.0), 1e-6
        ),
        "center_stop_open_at_r17p5_z31": not threaded.isInside(
            cq.Vector(17.5, 0.0, 31.0), 1e-6
        ),
        "center_stop_open_at_r19_z29": not threaded.isInside(
            cq.Vector(19.0, 0.0, 29.0), 1e-6
        ),
        "lower_face_thread_mouth_open": not threaded.isInside(
            cq.Vector(-20.5, -14.5, 15.5), 1e-6
        ),
        "upper_face_thread_mouth_open": not threaded.isInside(
            cq.Vector(20.5, 14.5, 46.5), 1e-6
        ),
        "tap_ready_pilot_mouth_open": not smooth.isInside(
            cq.Vector(-20.5, -14.5, 15.5), 1e-6
        ),
        "corner_material_present": threaded.isInside(
            cq.Vector(19.5, 19.5, 10.0), 1e-6
        ),
    }
    return checks


def write_readme(path: Path, validation: dict[str, object]) -> None:
    geometry = validation["geometry"]
    path.write_text(
        f"""# OpenHI 4F 40 mm Square Tube Connector With Eight M6 Set Screws

This clean parametric connector joins two measured `39.8 mm` OpenHI 4F tubes.
The connector is `42 x 42 x 62 mm`, with a `40.0 mm` bore and eight radial
M6-class printed set screws.

## Geometry

- Tube axis / print axis: `Z`.
- Connector envelope: `42 x 42 x 62 mm`.
- Bore: `40.0 mm`; measured tube: `39.8 mm`.
- Fit: `0.2 mm` diametral / `0.1 mm` radial clearance.
- Center stop: a `2.0 mm` inward annular ridge at `z=31 mm`.
- The stop is a triangular cross-section with straight `45 degree` chamfers:
  bore `40 -> 36 -> 40 mm` over `z=29 -> 31 -> 33 mm`.
- Optical opening remains `36 mm`; the stop is not a blocking disk.
- Eight radial threaded holes: four at `z=15.5 mm`, four at `z=46.5 mm`.
- The holes are offset `14.5 mm` toward the corners. This preserves
  `{geometry['minimum_thread_material_length_over_full_crest_mm']} mm` minimum
  material across the full M6 crest and
  `{geometry['thread_material_length_at_hole_centerline_mm']} mm` at each hole
  centerline. A centered face hole would have only `1 mm` wall.

## Threads

- Female: M6-class right-hand, `1.0 mm` pitch, `5.0 mm` pilot/root,
  `6.0 mm` cutter crest.
- Male screw: `5.8 mm` crest (`0.2 mm` diametral reduction), `4.8 mm` root,
  `12 mm` threaded length.
- Triangle profile: `0.58 mm` base, `0.5 mm` radial tooth height.
- Both cutters and male threads are swept an extra half pitch beyond each end,
  then clipped to the exact parent length. Threads reach both end planes but
  create no overflow bodies.
- Head: printed hex, `10 mm` across flats, `4 mm` high.

Horizontal printed M6 holes can be rough depending on layer height and cooling.
The main print file contains real helical threads. A separate tap-ready STEP/STL
uses only `5.0 mm` pilot holes so an M6 x 1.0 metal tap can clean or replace the
printed female thread without changing the connector envelope.

## Direct Print Files

- `PRINT_THIS_{STEM}_threaded_connector.step/.stl/.3mf`: one connector,
  printed upright on a `42 x 42 mm` end face.
- `PRINT_THIS_{STEM}_8x_set_screws.step/.stl/.3mf`: eight screws in a `4 x 2`
  grid, heads on the build plate.
- `PRINT_THIS_{STEM}_single_set_screw.step/.stl/.3mf`: one fit-test screw.
- `USE_THIS_{STEM}_threaded_connector.step`: editable threaded connector.
- `USE_THIS_{STEM}_tap_ready_connector.step`: smooth `5.0 mm` pilot version.
- `USE_THIS_{STEM}_fit_check_assembly.step`: connector, two tube proxies, and
  eight screws as separate assembly solids.

## Validation

- Threaded connector STEP: `{validation['threaded_connector_step']['solid_count']}`
  valid solid; bbox `{validation['threaded_connector_step']['bbox_mm']} mm`.
- Printable helical STEP topology: `{validation['threaded_connector_step']['face_count']}`
  faces, including `{validation['threaded_connector_step']['bspline_face_count']}`
  B-spline faces from real helices.
- Tap-ready Shapr STEP topology: `{validation['tap_ready_step']['face_count']}`
  faces and `{validation['tap_ready_step']['bspline_face_count']}` B-spline
  faces; use this file when fast, clean downstream editing matters.
- Threaded connector STL: watertight
  `{validation['threaded_connector_stl']['watertight']}`; components
  `{validation['threaded_connector_stl']['component_count']}`.
- Eight-screw print grid STEP: `{validation['set_screw_grid_step']['solid_count']}`
  solids; STL components `{validation['set_screw_grid_stl']['component_count']}`.
- Connector 3MF valid: `{validation['threaded_connector_3mf']['zip_valid']}`.
- Screw-grid 3MF valid: `{validation['set_screw_grid_3mf']['zip_valid']}`.

Print one screw first and test it in one hole. If the screw is too tight, clean
the female hole with an M6 x 1.0 tap; do not scale either part.
""",
        encoding="utf-8",
    )


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for checked CAD renders")
    subprocess.run(
        [blender, "--background", "--python", str(DESIGN_DIR / f"render_{STEM}.py")],
        check=True,
    )
    expected = [
        ARTIFACT_DIR / f"{STEM}_connector_render.png",
        ARTIFACT_DIR / f"{STEM}_fit_check_render.png",
        ARTIFACT_DIR / f"{STEM}_center_stop_section_render.png",
        ARTIFACT_DIR / f"{STEM}_8x_set_screw_grid_render.png",
    ]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError(f"Blender did not create expected renders: {missing}")


def copy_files(source_dir: Path, destination: Path, names: list[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(source_dir / name, destination / name)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    connector = build_connector(threaded=True)
    tap_ready = build_connector(threaded=False)
    screw_local = build_set_screw_local()
    screw_vertical = build_set_screw_print_vertical()
    screw_grid = build_set_screw_grid()
    screws_assembled = build_assembled_set_screws()
    section = build_section(connector)
    lower_tube = build_tube_proxy(-11.0, 40.0)
    upper_tube = build_tube_proxy(33.0, 40.0)
    thread_cutters = build_all_female_thread_cutters()

    paths = {
        "threaded_connector_step": ARTIFACT_DIR / f"{STEM}_threaded_connector.step",
        "threaded_connector_stl": ARTIFACT_DIR / f"{STEM}_threaded_connector.stl",
        "threaded_connector_3mf": ARTIFACT_DIR / f"{STEM}_threaded_connector.3mf",
        "tap_ready_step": ARTIFACT_DIR / f"{STEM}_tap_ready_connector.step",
        "tap_ready_stl": ARTIFACT_DIR / f"{STEM}_tap_ready_connector.stl",
        "set_screw_step": ARTIFACT_DIR / f"{STEM}_single_set_screw.step",
        "set_screw_stl": ARTIFACT_DIR / f"{STEM}_single_set_screw.stl",
        "set_screw_3mf": ARTIFACT_DIR / f"{STEM}_single_set_screw.3mf",
        "set_screw_grid_step": ARTIFACT_DIR / f"{STEM}_8x_set_screw_grid.step",
        "set_screw_grid_stl": ARTIFACT_DIR / f"{STEM}_8x_set_screw_grid.stl",
        "set_screw_grid_3mf": ARTIFACT_DIR / f"{STEM}_8x_set_screw_grid.3mf",
        "assembled_screws_step": ARTIFACT_DIR / f"{STEM}_assembled_set_screws.step",
        "assembled_screws_stl": ARTIFACT_DIR / f"{STEM}_assembled_set_screws.stl",
        "section_step": ARTIFACT_DIR / f"{STEM}_half_section.step",
        "section_stl": ARTIFACT_DIR / f"{STEM}_half_section.stl",
        "lower_tube_step": ARTIFACT_DIR / f"{STEM}_lower_tube_proxy.step",
        "lower_tube_stl": ARTIFACT_DIR / f"{STEM}_lower_tube_proxy.stl",
        "upper_tube_step": ARTIFACT_DIR / f"{STEM}_upper_tube_proxy.step",
        "upper_tube_stl": ARTIFACT_DIR / f"{STEM}_upper_tube_proxy.stl",
        "thread_cutters_step": ARTIFACT_DIR / f"{STEM}_8x_female_thread_cutters.step",
        "thread_cutters_stl": ARTIFACT_DIR / f"{STEM}_8x_female_thread_cutters.stl",
        "fit_assembly_step": ARTIFACT_DIR / f"{STEM}_fit_check_assembly.step",
        "fit_assembly_stl": ARTIFACT_DIR / f"{STEM}_fit_check_assembly.stl",
    }

    export_shape(connector, paths["threaded_connector_step"], paths["threaded_connector_stl"])
    export_stl_as_3mf(
        paths["threaded_connector_stl"],
        paths["threaded_connector_3mf"],
        title=f"{STEM} threaded connector",
    )
    export_shape(tap_ready, paths["tap_ready_step"], paths["tap_ready_stl"])
    export_shape(screw_vertical, paths["set_screw_step"], paths["set_screw_stl"])
    export_stl_as_3mf(
        paths["set_screw_stl"],
        paths["set_screw_3mf"],
        title=f"{STEM} single set screw",
    )
    export_shape(
        screw_grid,
        paths["set_screw_grid_step"],
        paths["set_screw_grid_stl"],
    )
    export_stl_as_3mf(
        paths["set_screw_grid_stl"],
        paths["set_screw_grid_3mf"],
        title=f"{STEM} eight set screws",
    )
    export_shape(
        screws_assembled,
        paths["assembled_screws_step"],
        paths["assembled_screws_stl"],
    )
    export_shape(section, paths["section_step"], paths["section_stl"])
    export_shape(lower_tube, paths["lower_tube_step"], paths["lower_tube_stl"])
    export_shape(upper_tube, paths["upper_tube_step"], paths["upper_tube_stl"])
    export_shape(
        thread_cutters,
        paths["thread_cutters_step"],
        paths["thread_cutters_stl"],
    )
    export_assembly(
        build_fit_check_assembly(connector, screws_assembled),
        paths["fit_assembly_step"],
        paths["fit_assembly_stl"],
    )

    validation = {
        "geometry": geometry_checks(),
        "features": feature_checks(connector, tap_ready),
        "threaded_connector_step": validate_step(paths["threaded_connector_step"]),
        "threaded_connector_stl": validate_stl(paths["threaded_connector_stl"]),
        "threaded_connector_3mf": validate_3mf(paths["threaded_connector_3mf"]),
        "tap_ready_step": validate_step(paths["tap_ready_step"]),
        "set_screw_step": validate_step(paths["set_screw_step"]),
        "set_screw_stl": validate_stl(paths["set_screw_stl"]),
        "set_screw_3mf": validate_3mf(paths["set_screw_3mf"]),
        "set_screw_grid_step": validate_step(paths["set_screw_grid_step"]),
        "set_screw_grid_stl": validate_stl(paths["set_screw_grid_stl"]),
        "set_screw_grid_3mf": validate_3mf(paths["set_screw_grid_3mf"]),
        "thread_cutters_step": validate_step(paths["thread_cutters_step"]),
        "fit_assembly_step": validate_step(paths["fit_assembly_step"]),
    }

    if validation["threaded_connector_step"]["solid_count"] != 1:
        raise RuntimeError("Threaded connector STEP must contain one solid")
    if not validation["threaded_connector_step"]["all_brep_valid"]:
        raise RuntimeError("Threaded connector STEP is not a valid B-rep")
    if (
        validation["threaded_connector_step"]["bbox_mm"]
        != validation["geometry"]["expected_connector_bbox_mm"]
    ):
        raise RuntimeError("Threaded connector envelope changed")
    if not validation["threaded_connector_stl"]["watertight"]:
        raise RuntimeError("Threaded connector STL is not watertight")
    if validation["threaded_connector_stl"]["component_count"] != 1:
        raise RuntimeError("Threaded connector STL must be one printable component")
    if validation["set_screw_step"]["solid_count"] != 1:
        raise RuntimeError("Single set screw STEP must contain one solid")
    if validation["set_screw_grid_step"]["solid_count"] != 8:
        raise RuntimeError("Set screw print grid must contain eight separate screws")
    if validation["set_screw_grid_stl"]["component_count"] != 8:
        raise RuntimeError("Set screw STL must contain eight watertight components")
    if not validation["threaded_connector_3mf"]["zip_valid"]:
        raise RuntimeError("Connector 3MF is invalid")
    if not validation["set_screw_grid_3mf"]["zip_valid"]:
        raise RuntimeError("Set screw grid 3MF is invalid")
    if not all(validation["features"].values()):
        raise RuntimeError(f"Feature checks failed: {validation['features']}")

    render_with_blender()

    root_aliases = {
        f"USE_THIS_{STEM}_threaded_connector.step": paths["threaded_connector_step"],
        f"USE_THIS_{STEM}_tap_ready_connector.step": paths["tap_ready_step"],
        f"USE_THIS_{STEM}_fit_check_assembly.step": paths["fit_assembly_step"],
        f"PRINT_THIS_{STEM}_threaded_connector.step": paths["threaded_connector_step"],
        f"PRINT_THIS_{STEM}_threaded_connector.stl": paths["threaded_connector_stl"],
        f"PRINT_THIS_{STEM}_threaded_connector.3mf": paths["threaded_connector_3mf"],
        f"PRINT_THIS_{STEM}_8x_set_screws.step": paths["set_screw_grid_step"],
        f"PRINT_THIS_{STEM}_8x_set_screws.stl": paths["set_screw_grid_stl"],
        f"PRINT_THIS_{STEM}_8x_set_screws.3mf": paths["set_screw_grid_3mf"],
        f"PRINT_THIS_{STEM}_single_set_screw.step": paths["set_screw_step"],
        f"PRINT_THIS_{STEM}_single_set_screw.stl": paths["set_screw_stl"],
        f"PRINT_THIS_{STEM}_single_set_screw.3mf": paths["set_screw_3mf"],
        f"USE_THIS_{STEM}_connector_render.png": ARTIFACT_DIR / f"{STEM}_connector_render.png",
        f"USE_THIS_{STEM}_fit_check_render.png": ARTIFACT_DIR / f"{STEM}_fit_check_render.png",
        f"USE_THIS_{STEM}_center_stop_section_render.png": ARTIFACT_DIR / f"{STEM}_center_stop_section_render.png",
        f"PRINT_THIS_{STEM}_8x_set_screws_render.png": ARTIFACT_DIR / f"{STEM}_8x_set_screw_grid_render.png",
    }
    for alias, source in root_aliases.items():
        shutil.copy2(source, DESIGN_DIR / alias)

    write_readme(DESIGN_DIR / "README.md", validation)
    manifest = {
        "name": STEM,
        "run": RUN_NAME,
        "created_by": Path(__file__).name,
        "parameters": PARAMS,
        "validation": validation,
        "outputs": {
            key: str(path.relative_to(DESIGN_DIR))
            for key, path in paths.items()
        },
        "root_aliases": sorted(root_aliases),
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, DESIGN_DIR / "manifest.json")

    for stale in RUN_ARTIFACT_DIR.iterdir():
        if stale.is_file():
            stale.unlink()
    for source in ARTIFACT_DIR.iterdir():
        if source.is_file() and source.suffix != ".blend1":
            shutil.copy2(source, RUN_ARTIFACT_DIR / source.name)
    shutil.copy2(Path(__file__), RUN_DIR / Path(__file__).name)
    shutil.copy2(DESIGN_DIR / f"render_{STEM}.py", RUN_DIR / f"render_{STEM}.py")

    handoff_names = [*root_aliases.keys(), "README.md"]
    copy_files(DESIGN_DIR, RUN_DIR, handoff_names)
    shutil.copy2(manifest_path, RUN_DIR / "manifest.json")
    copy_files(DESIGN_DIR, NUTSTORE_DIR, handoff_names)
    shutil.copy2(manifest_path, NUTSTORE_DIR / "manifest.json")

    nutstore_root = NUTSTORE_DIR.parents[1]
    nutstore_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        paths["fit_assembly_step"],
        nutstore_root / f"{STEM}_fit_check_assembly.step",
    )
    shutil.copy2(
        paths["threaded_connector_step"],
        nutstore_root / f"USE_THIS_{STEM}_threaded_connector.step",
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
