#!/usr/bin/env python3
"""Keep the C receiver at 29.6 mm and enlarge only the A receiver to 29.8 mm.

The OpenHI Shapr archive stores this object as imported geometry, so the source
STEP remains authoritative. This builder keeps that B-rep and uses the proven
fill-and-recut method only inside the lower/A and side/C receiver envelopes.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

import cadquery as cq
import trimesh
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_BSplineSurface, GeomAbs_Cone, GeomAbs_Cylinder


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_a_c_bs_a29p8_c29p6_female_pivots"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/A+ C + BS.step"
SOURCE_SHAPR = ROOT / "cad/extracted/OpenHI.shapr"
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
NUTSTORE_DIR = NUTSTORE_ROOT / DESIGN_DIR.name
RUN_1_NAME = "run-1-dual-female-29p6-20260814T132555Z"
RUN_2_NAME = "run-2-a-female-29p8-c-female-29p6-20260815T035628Z"
RUN_3_NAME = "run-3-clear-c-optical-bore-20260830T052552Z"
ACCEPTED_RUN_STEP = (
    DESIGN_DIR
    / "runs"
    / RUN_1_NAME
    / "artifacts"
    / "openhi_a_c_bs_dual_female_29p6_pivot.step"
)

PITCH = 0.8
TOOTH_RADIAL_HEIGHT = 0.4
TOOTH_BASE = 0.8
RUNOUT = 0.4
THREAD_OVERLAP = 0.10
FEMALE_PHASE_SHIFT = -0.20

LOWER_A_FEMALE_PIVOT = 29.8
LOWER_A_FEMALE_GROOVE = (
    LOWER_A_FEMALE_PIVOT + 2.0 * TOOTH_RADIAL_HEIGHT
)
SIDE_C_FEMALE_PIVOT = 29.6
SIDE_C_FEMALE_GROOVE = (
    SIDE_C_FEMALE_PIVOT + 2.0 * TOOTH_RADIAL_HEIGHT
)

LOWER_CENTER = (255.0, 210.0)
LOWER_MOUTH_Z0 = 535.1
LOWER_MOUTH_OUTER_DIAMETER = 40.0
LOWER_THREAD_Z0 = 540.3
LOWER_THREAD_LENGTH = 7.65
LOWER_TRANSITION_Z0 = 547.95
LOWER_LENS_SEAT_Z = 550.0
LOWER_LENS_SEAT_DIAMETER = 25.5
LOWER_MOUTH_ANGLE_DEG = math.degrees(
    math.atan(
        ((LOWER_MOUTH_OUTER_DIAMETER - LOWER_A_FEMALE_PIVOT) / 2.0)
        / (LOWER_THREAD_Z0 - LOWER_MOUTH_Z0)
    )
)
LOWER_LENS_TRANSITION_ANGLE_DEG = math.degrees(
    math.atan(
        ((LOWER_A_FEMALE_PIVOT - LOWER_LENS_SEAT_DIAMETER) / 2.0)
        / (LOWER_LENS_SEAT_Z - LOWER_TRANSITION_Z0)
    )
)

SIDE_CENTER = (210.0, 600.0)
SIDE_THREAD_X0 = 270.0
SIDE_THREAD_LENGTH = 5.0
SIDE_FILL_X0 = 269.9
SIDE_FILL_LENGTH = 5.1
SIDE_PILOT_X0 = SIDE_FILL_X0
SIDE_PILOT_LENGTH = SIDE_THREAD_X0 + SIDE_THREAD_LENGTH - SIDE_PILOT_X0
SIDE_RECEIVER_PROBE_DIAMETER = SIDE_C_FEMALE_PIVOT - 0.2
C_PATH_CORE_PROBE_DIAMETER = 4.0
C_PATH_CORE_X0 = 255.05
C_PATH_CORE_X1 = 274.95


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def near(value: float | None, target: float, tolerance: float = 0.015) -> bool:
    return value is not None and math.isclose(value, target, abs_tol=tolerance)


def workplane(shape: cq.Shape) -> cq.Workplane:
    return cq.Workplane().add(shape)


def largest_solid(part: cq.Workplane) -> cq.Workplane:
    solids = part.val().Solids()
    if not solids:
        raise RuntimeError("boolean operation produced no solid")
    return workplane(max(solids, key=lambda item: item.Volume()))


def bbox_dict(shape: cq.Shape) -> dict[str, list[float]]:
    box = shape.BoundingBox()
    return {
        "min": [round(box.xmin, 6), round(box.ymin, 6), round(box.zmin, 6)],
        "max": [round(box.xmax, 6), round(box.ymax, 6), round(box.zmax, 6)],
        "size": [round(box.xlen, 6), round(box.ylen, 6), round(box.zlen, 6)],
    }


def shape_summary(shape: cq.Shape) -> dict[str, Any]:
    return {
        "bbox": bbox_dict(shape),
        "solid_count": len(shape.Solids()),
        "shell_count": len(shape.Shells()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "volume_mm3": round(shape.Volume(), 6),
        "area_mm2": round(shape.Area(), 6),
        "occt_valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
    }


def z_cylinder(
    diameter: float,
    z0: float,
    length: float,
    center_x: float,
    center_y: float,
) -> cq.Workplane:
    return workplane(
        cq.Solid.makeCylinder(
            diameter / 2.0,
            length,
            cq.Vector(center_x, center_y, z0),
            cq.Vector(0.0, 0.0, 1.0),
        )
    )


def x_cylinder(
    diameter: float,
    x0: float,
    length: float,
    center_y: float,
    center_z: float,
) -> cq.Workplane:
    return workplane(
        cq.Solid.makeCylinder(
            diameter / 2.0,
            length,
            cq.Vector(x0, center_y, center_z),
            cq.Vector(1.0, 0.0, 0.0),
        )
    )


def z_cone(
    diameter0: float,
    diameter1: float,
    z0: float,
    length: float,
    center_x: float,
    center_y: float,
) -> cq.Workplane:
    return workplane(
        cq.Solid.makeCone(
            diameter0 / 2.0,
            diameter1 / 2.0,
            length,
            cq.Vector(center_x, center_y, z0),
            cq.Vector(0.0, 0.0, 1.0),
        )
    )


def x_clip(x0: float, length: float, span: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(length, span, span, centered=(False, True, True))
        .translate((x0, 0.0, 0.0))
    )


def z_clip(
    z0: float,
    length: float,
    span: float,
    center_x: float,
    center_y: float,
) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(span, span, length, centered=(True, True, False))
        .translate((center_x, center_y, z0))
    )


def x_thread_tooth(
    root_diameter: float,
    crest_diameter: float,
    length: float,
    *,
    x0: float,
    phase_shift: float,
) -> cq.Workplane:
    """Create the source-style right-hand helix and clip both runout ends."""
    tooth_height = (crest_diameter - root_diameter) / 2.0
    construction_margin = RUNOUT + PITCH
    sweep_x0 = x0 - construction_margin + phase_shift
    sweep_length = length + 2.0 * construction_margin
    root_radius = root_diameter / 2.0 - THREAD_OVERLAP
    path = cq.Wire.makeHelix(
        PITCH,
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
                (TOOTH_BASE / 2.0, tooth_height + THREAD_OVERLAP),
                (TOOTH_BASE, 0.0),
            ]
        )
        .close()
    )
    tooth = profile.sweep(path, isFrenet=True, combine=False)
    return tooth.intersect(x_clip(x0, length, crest_diameter + 4.0))


def x_thread_at(
    root_diameter: float,
    crest_diameter: float,
    x0: float,
    length: float,
    center_y: float,
    center_z: float,
) -> cq.Workplane:
    return x_thread_tooth(
        root_diameter,
        crest_diameter,
        length,
        x0=x0,
        phase_shift=FEMALE_PHASE_SHIFT,
    ).translate((0.0, center_y, center_z))


def z_thread_at(
    root_diameter: float,
    crest_diameter: float,
    z0: float,
    length: float,
    center_x: float,
    center_y: float,
) -> cq.Workplane:
    tooth = (
        x_thread_tooth(
            root_diameter,
            crest_diameter,
            length,
            x0=z0,
            phase_shift=FEMALE_PHASE_SHIFT,
        )
        .rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)
        .translate((center_x, center_y, 0.0))
    )
    return tooth.intersect(
        z_clip(z0, length, crest_diameter + 4.0, center_x, center_y)
    )


def make_compound(parts: Iterable[cq.Workplane]) -> cq.Workplane:
    shapes = [part.val() for part in parts]
    return workplane(cq.Compound.makeCompound(shapes))


def make_receiver_cutters() -> dict[str, cq.Workplane]:
    lower_mouth_length = LOWER_THREAD_Z0 - LOWER_MOUTH_Z0
    lower_transition_length = LOWER_LENS_SEAT_Z - LOWER_TRANSITION_Z0
    lower_mouth = z_cone(
        LOWER_MOUTH_OUTER_DIAMETER,
        LOWER_A_FEMALE_PIVOT,
        LOWER_MOUTH_Z0,
        lower_mouth_length,
        *LOWER_CENTER,
    )
    lower_pilot = z_cylinder(
        LOWER_A_FEMALE_PIVOT,
        LOWER_THREAD_Z0,
        LOWER_THREAD_LENGTH,
        *LOWER_CENTER,
    )
    lower_thread = z_thread_at(
        LOWER_A_FEMALE_PIVOT,
        LOWER_A_FEMALE_GROOVE,
        LOWER_THREAD_Z0,
        LOWER_THREAD_LENGTH,
        *LOWER_CENTER,
    )
    lower_transition = z_cone(
        LOWER_A_FEMALE_PIVOT,
        LOWER_LENS_SEAT_DIAMETER,
        LOWER_TRANSITION_Z0,
        lower_transition_length,
        *LOWER_CENTER,
    )
    side_pilot = x_cylinder(
        SIDE_C_FEMALE_PIVOT,
        SIDE_PILOT_X0,
        SIDE_PILOT_LENGTH,
        *SIDE_CENTER,
    )
    side_thread = x_thread_at(
        SIDE_C_FEMALE_PIVOT,
        SIDE_C_FEMALE_GROOVE,
        SIDE_THREAD_X0,
        SIDE_THREAD_LENGTH,
        *SIDE_CENTER,
    )
    return {
        "lower_mouth": lower_mouth,
        "lower_pilot": lower_pilot,
        "lower_thread": lower_thread,
        "lower_transition": lower_transition,
        "side_pilot": side_pilot,
        "side_thread": side_thread,
        "lower_compound": make_compound(
            [lower_mouth, lower_pilot, lower_thread, lower_transition]
        ),
        "side_compound": make_compound([side_pilot, side_thread]),
    }


def build() -> tuple[cq.Workplane, dict[str, cq.Workplane]]:
    source = cq.importers.importStep(str(SOURCE_STEP)).val()
    if len(source.Solids()) != 1:
        raise RuntimeError("A+ C + BS source must contain exactly one solid")

    cutters = make_receiver_cutters()
    body = workplane(source)

    # Start below the mouth where the 31.4 mm fill overlaps real source wall.
    # This heals the old 30.2/31.0 lower receiver before the new analytic cut.
    lower_fill = z_cylinder(31.4, 539.5, 10.5, *LOWER_CENTER)
    body = body.union(lower_fill)
    for key in ("lower_mouth", "lower_pilot", "lower_thread", "lower_transition"):
        body = body.cut(cutters[key])
    body = body.clean()

    # Extend the smooth pilot through the 0.1 mm fusion overlap. Starting both
    # cuts at x=270 left an optically opaque membrane at the C receiver mouth.
    # The helical thread itself still starts at x=270 and remains unchanged.
    side_fill = x_cylinder(31.4, SIDE_FILL_X0, SIDE_FILL_LENGTH, *SIDE_CENTER)
    body = body.union(side_fill)
    body = body.cut(cutters["side_pilot"]).cut(cutters["side_thread"]).clean()
    return largest_solid(body), cutters


def radial_probe(
    shape: cq.Shape,
    *,
    axis: str,
    center_a: float,
    center_b: float,
    axial_min: float,
    axial_max: float,
    pivot_diameter: float,
    groove_diameter: float,
) -> dict[str, Any]:
    cylinder_diameters: list[float] = []
    groove_samples: list[float] = []
    matched_bspline_bounds: list[list[float]] = []
    cone_angles: list[dict[str, Any]] = []
    for face in shape.Faces():
        box = face.BoundingBox()
        face_min = box.zmin if axis == "z" else box.xmin
        face_max = box.zmax if axis == "z" else box.xmax
        if face_max < axial_min - 1e-5 or face_min > axial_max + 1e-5:
            continue
        adaptor = BRepAdaptor_Surface(face.wrapped, True)
        surface_type = adaptor.GetType()
        if surface_type == GeomAbs_Cylinder:
            cylinder_diameters.append(2.0 * adaptor.Cylinder().Radius())
        elif surface_type == GeomAbs_Cone:
            cone_angles.append(
                {
                    "semi_angle_deg": round(
                        abs(math.degrees(adaptor.Cone().SemiAngle())), 6
                    ),
                    "axial_bounds_mm": [round(face_min, 6), round(face_max, 6)],
                }
            )
        if surface_type != GeomAbs_BSplineSurface:
            continue
        face_groove_samples: list[float] = []
        vertices, _ = face.tessellate(0.015)
        for vertex in vertices:
            axial = vertex.z if axis == "z" else vertex.x
            if not (axial_min - 1e-4 <= axial <= axial_max + 1e-4):
                continue
            if axis == "z":
                radius = math.hypot(vertex.x - center_a, vertex.y - center_b)
            else:
                radius = math.hypot(vertex.y - center_a, vertex.z - center_b)
            diameter = 2.0 * radius
            if pivot_diameter - 0.2 <= diameter <= groove_diameter + 0.2:
                face_groove_samples.append(diameter)
        if face_groove_samples:
            groove_samples.extend(face_groove_samples)
            matched_bspline_bounds.append(
                [round(face_min, 6), round(face_max, 6)]
            )
    return {
        "cylinder_diameters_mm": sorted(
            {round(value, 6) for value in cylinder_diameters}
        ),
        "bspline_sample_min_diameter_mm": (
            round(min(groove_samples), 4) if groove_samples else None
        ),
        "bspline_sample_max_diameter_mm": (
            round(max(groove_samples), 4) if groove_samples else None
        ),
        "matched_bspline_axial_bounds_mm": matched_bspline_bounds,
        "cone_surfaces": cone_angles,
    }


def all_bounds_within(
    bounds: list[list[float]], minimum: float, maximum: float, tolerance: float = 0.02
) -> bool:
    return bool(bounds) and all(
        low >= minimum - tolerance and high <= maximum + tolerance
        for low, high in bounds
    )


def validate_change_scope(source: cq.Shape, output: cq.Shape) -> dict[str, float]:
    """Prove that all material changes stay inside the two receiver zones."""
    lower_envelope = z_cylinder(40.2, 535.0, 15.2, *LOWER_CENTER)
    side_envelope = x_cylinder(40.2, 269.9, 5.2, *SIDE_CENTER)
    removed = workplane(source).cut(workplane(output))
    added = workplane(output).cut(workplane(source))
    removed_outside = removed.cut(lower_envelope).cut(side_envelope)
    added_outside = added.cut(lower_envelope).cut(side_envelope)
    return {
        "removed_total_mm3": round(removed.val().Volume(), 6),
        "added_total_mm3": round(added.val().Volume(), 6),
        "removed_outside_receiver_envelopes_mm3": round(
            removed_outside.val().Volume(), 9
        ),
        "added_outside_receiver_envelopes_mm3": round(
            added_outside.val().Volume(), 9
        ),
    }


def validate_delta_from_accepted_run(
    accepted: cq.Shape, output: cq.Shape
) -> dict[str, float]:
    """Compare bounded receiver geometry without coincident-face booleans."""
    lower_envelope = z_cylinder(40.2, 535.0, 15.2, *LOWER_CENTER)
    side_envelope = x_cylinder(40.2, 269.9, 5.2, *SIDE_CENTER)
    accepted_lower = workplane(accepted).intersect(lower_envelope).val()
    output_lower = workplane(output).intersect(lower_envelope).val()
    accepted_side = workplane(accepted).intersect(side_envelope).val()
    output_side = workplane(output).intersect(side_envelope).val()
    return {
        "accepted_lower_A_volume_mm3": round(accepted_lower.Volume(), 9),
        "output_lower_A_volume_mm3": round(output_lower.Volume(), 9),
        "lower_A_material_delta_mm3": round(
            output_lower.Volume() - accepted_lower.Volume(), 9
        ),
        "accepted_side_C_volume_mm3": round(accepted_side.Volume(), 9),
        "output_side_C_volume_mm3": round(output_side.Volume(), 9),
        "side_C_volume_delta_mm3": round(
            output_side.Volume() - accepted_side.Volume(), 9
        ),
        "accepted_side_C_area_mm2": round(accepted_side.Area(), 9),
        "output_side_C_area_mm2": round(output_side.Area(), 9),
        "side_C_area_delta_mm2": round(
            output_side.Area() - accepted_side.Area(), 9
        ),
    }


def axial_probe_overlap_mm3(
    shape: cq.Shape,
    *,
    diameter: float,
    x0: float,
    x1: float,
) -> float:
    probe = x_cylinder(diameter, x0, x1 - x0, *SIDE_CENTER)
    return abs(shape.intersect(probe.val()).Volume())


def validate_export(source: cq.Shape, output_path: Path) -> dict[str, Any]:
    if not ACCEPTED_RUN_STEP.exists():
        raise FileNotFoundError(
            f"missing accepted run baseline STEP: {ACCEPTED_RUN_STEP}"
        )
    output = cq.importers.importStep(str(output_path)).val()
    accepted = cq.importers.importStep(str(ACCEPTED_RUN_STEP)).val()
    source_summary = shape_summary(source)
    output_summary = shape_summary(output)
    lower = radial_probe(
        output,
        axis="z",
        center_a=LOWER_CENTER[0],
        center_b=LOWER_CENTER[1],
        axial_min=LOWER_MOUTH_Z0,
        axial_max=LOWER_LENS_SEAT_Z,
        pivot_diameter=LOWER_A_FEMALE_PIVOT,
        groove_diameter=LOWER_A_FEMALE_GROOVE,
    )
    side = radial_probe(
        output,
        axis="x",
        center_a=SIDE_CENTER[0],
        center_b=SIDE_CENTER[1],
        axial_min=SIDE_THREAD_X0,
        axial_max=SIDE_THREAD_X0 + SIDE_THREAD_LENGTH,
        pivot_diameter=SIDE_C_FEMALE_PIVOT,
        groove_diameter=SIDE_C_FEMALE_GROOVE,
    )
    change_scope = validate_change_scope(source, output)
    accepted_run_delta = validate_delta_from_accepted_run(accepted, output)
    optical_bore_probes = {
        "beam_splitter_to_c_core": {
            "diameter_mm": C_PATH_CORE_PROBE_DIAMETER,
            "x_range_mm": [C_PATH_CORE_X0, C_PATH_CORE_X1],
            "solid_overlap_mm3": round(
                axial_probe_overlap_mm3(
                    output,
                    diameter=C_PATH_CORE_PROBE_DIAMETER,
                    x0=C_PATH_CORE_X0,
                    x1=C_PATH_CORE_X1,
                ),
                9,
            ),
        },
        "c_receiver_smooth_core": {
            "diameter_mm": SIDE_RECEIVER_PROBE_DIAMETER,
            "x_range_mm": [SIDE_FILL_X0 + 0.01, C_PATH_CORE_X1],
            "solid_overlap_mm3": round(
                axial_probe_overlap_mm3(
                    output,
                    diameter=SIDE_RECEIVER_PROBE_DIAMETER,
                    x0=SIDE_FILL_X0 + 0.01,
                    x1=C_PATH_CORE_X1,
                ),
                9,
            ),
        },
    }

    measured_lower_angles = [
        item["semi_angle_deg"] for item in lower["cone_surfaces"]
    ]
    lower_transitions_match_fixed_endpoints = all(
        any(near(measured, expected, 0.01) for measured in measured_lower_angles)
        for expected in (
            LOWER_MOUTH_ANGLE_DEG,
            LOWER_LENS_TRANSITION_ANGLE_DEG,
        )
    )
    checks = {
        "single_solid": output_summary["solid_count"] == 1,
        "occt_valid": output_summary["occt_valid"],
        "external_bbox_preserved": (
            source_summary["bbox"] == output_summary["bbox"]
        ),
        "changes_confined_to_two_receiver_envelopes": (
            change_scope["removed_outside_receiver_envelopes_mm3"] < 1e-6
            and change_scope["added_outside_receiver_envelopes_mm3"] < 1e-6
        ),
        "changes_from_run1_match_A_fit_and_C_membrane_fix": (
            accepted_run_delta["lower_A_material_delta_mm3"] < -1e-3
            and -75.0 < accepted_run_delta["side_C_volume_delta_mm3"] < -60.0
        ),
        "lower_A_pivot_is_29p8": any(
            near(value, LOWER_A_FEMALE_PIVOT)
            for value in lower["cylinder_diameters_mm"]
        ),
        "lower_A_groove_is_30p6": near(
            lower["bspline_sample_max_diameter_mm"],
            LOWER_A_FEMALE_GROOVE,
        ),
        "side_C_pivot_is_29p6": any(
            near(value, SIDE_C_FEMALE_PIVOT)
            for value in side["cylinder_diameters_mm"]
        ),
        "side_C_groove_is_30p4": near(
            side["bspline_sample_max_diameter_mm"],
            SIDE_C_FEMALE_GROOVE,
        ),
        "lower_thread_clipped_to_receiver": all_bounds_within(
            lower["matched_bspline_axial_bounds_mm"],
            LOWER_THREAD_Z0,
            LOWER_THREAD_Z0 + LOWER_THREAD_LENGTH,
        ),
        "side_thread_clipped_to_receiver": all_bounds_within(
            side["matched_bspline_axial_bounds_mm"],
            SIDE_THREAD_X0,
            SIDE_THREAD_X0 + SIDE_THREAD_LENGTH,
        ),
        "lower_transition_endpoints_and_slopes_match": (
            lower_transitions_match_fixed_endpoints
        ),
        "beam_splitter_to_C_centerline_is_clear": (
            optical_bore_probes["beam_splitter_to_c_core"]["solid_overlap_mm3"]
            < 1e-6
        ),
        "C_receiver_has_no_fusion_membrane": (
            optical_bore_probes["c_receiver_smooth_core"]["solid_overlap_mm3"]
            < 1e-6
        ),
    }
    checks["all_pass"] = all(checks.values())
    return {
        "source": source_summary,
        "output": output_summary,
        "change_scope": change_scope,
        "accepted_run_delta": accepted_run_delta,
        "optical_bore_probes": optical_bore_probes,
        "thread_probes": {"lower_A_receiver": lower, "side_C_receiver": side},
        "checks": checks,
    }


def validate_mesh(mesh_path: Path) -> dict[str, Any]:
    mesh = trimesh.load(mesh_path, force="mesh", process=True)
    components = mesh.split(only_watertight=False)
    return {
        "path": repo_path(mesh_path),
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "component_count": len(components),
        "body_count": int(mesh.body_count),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_mm3": round(float(mesh.volume), 6),
        "bounds_mm": [[round(float(value), 6) for value in row] for row in mesh.bounds],
    }


def validate_3mf(mesh_path: Path) -> dict[str, Any]:
    """Validate native 3MF geometry without optional trimesh graph packages."""
    with zipfile.ZipFile(mesh_path) as archive:
        model_name = next(
            name for name in archive.namelist() if name.lower().endswith(".model")
        )
        root = ElementTree.fromstring(archive.read(model_name))
    namespace_uri = root.tag.split("}", 1)[0].lstrip("{")
    namespace = {"m": namespace_uri}
    meshes = root.findall(".//m:object/m:mesh", namespace)
    if len(meshes) != 1:
        raise RuntimeError(f"expected one 3MF mesh object, found {len(meshes)}")
    mesh = meshes[0]
    vertices = [
        (
            float(vertex.attrib["x"]),
            float(vertex.attrib["y"]),
            float(vertex.attrib["z"]),
        )
        for vertex in mesh.findall("./m:vertices/m:vertex", namespace)
    ]
    triangles = [
        (
            int(triangle.attrib["v1"]),
            int(triangle.attrib["v2"]),
            int(triangle.attrib["v3"]),
        )
        for triangle in mesh.findall("./m:triangles/m:triangle", namespace)
    ]
    if not vertices or not triangles:
        raise RuntimeError("3MF contains no usable mesh")

    parent = list(range(len(vertices)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    edge_counts: Counter[tuple[int, int]] = Counter()
    edge_orientation: Counter[tuple[int, int]] = Counter()
    referenced: set[int] = set()
    valid_indices = True
    for triangle in triangles:
        if any(index < 0 or index >= len(vertices) for index in triangle):
            valid_indices = False
            continue
        referenced.update(triangle)
        union(triangle[0], triangle[1])
        union(triangle[1], triangle[2])
        for start, end in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        ):
            edge = (min(start, end), max(start, end))
            edge_counts[edge] += 1
            edge_orientation[edge] += 1 if start < end else -1

    component_count = len({find(index) for index in referenced})
    minimum = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maximum = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    return {
        "path": repo_path(mesh_path),
        "unit": root.attrib.get("unit"),
        "mesh_object_count": len(meshes),
        "vertices": len(vertices),
        "faces": len(triangles),
        "component_count": component_count,
        "body_count": component_count,
        "indices_valid": valid_indices,
        "watertight": bool(edge_counts) and all(
            count == 2 for count in edge_counts.values()
        ),
        "winding_consistent": bool(edge_orientation) and all(
            orientation == 0 for orientation in edge_orientation.values()
        ),
        "bounds_mm": [
            [round(value, 6) for value in minimum],
            [round(value, 6) for value in maximum],
        ],
    }


def export_watertight_3mf(stl_path: Path, output_path: Path) -> None:
    """Package the processed B-rep tessellation as a welded 3MF mesh."""
    mesh = trimesh.load(stl_path, force="mesh", process=True)
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise RuntimeError("refusing to package a non-watertight STL as 3MF")

    core_namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ElementTree.register_namespace("", core_namespace)
    model = ElementTree.Element(
        f"{{{core_namespace}}}model",
        {"unit": "millimeter"},
    )
    metadata = ElementTree.SubElement(
        model,
        f"{{{core_namespace}}}metadata",
        {"name": "Application"},
    )
    metadata.text = "AgInTi LabCanvas OpenHI CAD builder"
    resources = ElementTree.SubElement(model, f"{{{core_namespace}}}resources")
    object_node = ElementTree.SubElement(
        resources,
        f"{{{core_namespace}}}object",
        {"id": "1", "name": STEM, "type": "model"},
    )
    mesh_node = ElementTree.SubElement(object_node, f"{{{core_namespace}}}mesh")
    vertices_node = ElementTree.SubElement(
        mesh_node, f"{{{core_namespace}}}vertices"
    )
    for x_value, y_value, z_value in mesh.vertices:
        ElementTree.SubElement(
            vertices_node,
            f"{{{core_namespace}}}vertex",
            {
                "x": format(float(x_value), ".9g"),
                "y": format(float(y_value), ".9g"),
                "z": format(float(z_value), ".9g"),
            },
        )
    triangles_node = ElementTree.SubElement(
        mesh_node, f"{{{core_namespace}}}triangles"
    )
    for first, second, third in mesh.faces:
        ElementTree.SubElement(
            triangles_node,
            f"{{{core_namespace}}}triangle",
            {"v1": str(first), "v2": str(second), "v3": str(third)},
        )
    build_node = ElementTree.SubElement(model, f"{{{core_namespace}}}build")
    ElementTree.SubElement(
        build_node,
        f"{{{core_namespace}}}item",
        {"objectid": "1"},
    )
    model_xml = ElementTree.tostring(
        model,
        encoding="utf-8",
        xml_declaration=True,
    )

    content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""
    relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("3D/3dmodel.model", model_xml)


def bounds_match(
    left: list[list[float]], right: list[list[float]], tolerance: float = 0.001
) -> bool:
    return all(
        abs(left_value - right_value) <= tolerance
        for left_row, right_row in zip(left, right)
        for left_value, right_value in zip(left_row, right_row)
    )


def export_parts(
    assembly: cq.Workplane, cutters: dict[str, cq.Workplane]
) -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    assembly_step = ARTIFACT_DIR / f"{STEM}.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}.stl"
    assembly_3mf = ARTIFACT_DIR / f"{STEM}.3mf"
    lower_cutter_step = ARTIFACT_DIR / f"{STEM}_lower_receiver_cutter.step"
    side_cutter_step = ARTIFACT_DIR / f"{STEM}_side_receiver_cutter.step"
    root_step = DESIGN_DIR / f"USE_THIS_{STEM}.step"
    root_3mf = DESIGN_DIR / f"USE_THIS_{STEM}.3mf"

    exporters.export(assembly, str(assembly_step))
    exporters.export(
        assembly,
        str(assembly_stl),
        tolerance=0.02,
        angularTolerance=0.10,
    )
    export_watertight_3mf(assembly_stl, assembly_3mf)
    exporters.export(cutters["lower_compound"], str(lower_cutter_step))
    exporters.export(cutters["side_compound"], str(side_cutter_step))
    shutil.copy2(assembly_step, root_step)
    shutil.copy2(assembly_3mf, root_3mf)
    return {
        "root_step": repo_path(root_step),
        "root_3mf": repo_path(root_3mf),
        "assembly_step": repo_path(assembly_step),
        "assembly_stl": repo_path(assembly_stl),
        "assembly_3mf": repo_path(assembly_3mf),
        "lower_receiver_cutter_step": repo_path(lower_cutter_step),
        "side_receiver_cutter_step": repo_path(side_cutter_step),
        "full_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_render.png"),
        "cutaway_render_png": repo_path(
            ARTIFACT_DIR / f"{STEM}_thread_cutaway.png"
        ),
        "blend": repo_path(ARTIFACT_DIR / f"{STEM}.blend"),
        "manifest": repo_path(ARTIFACT_DIR / "manifest.json"),
    }


def write_readme(manifest: dict[str, Any]) -> None:
    checks = manifest["validation"]["checks"]
    lines = [
        "# OpenHI A+C+BS A 29.8 / C 29.6 mm Female-Pivot Variant",
        "",
        "## Use This File",
        "",
        f"`USE_THIS_{STEM}.step`",
        "",
        f"For a direct mesh handoff, use `USE_THIS_{STEM}.3mf`.",
        "",
        "This is a sibling tight-fit variant of only `A+ C + BS.step`. The source STEP, `OpenHI.shapr`, `A.step`, and `C.step` are untouched.",
        "",
        "## Requested Change",
        "",
        "- Lower/A-branch female pivot: `29.6 -> 29.8 mm`.",
        "- Side/C-branch female pivot: unchanged at `29.6 mm`.",
        "- Thread pitch remains `0.8 mm`.",
        "- Radial tooth height remains `0.4 mm`: A groove `30.6 mm`, C groove `30.4 mm`.",
        "- Hand remains right-hand and the `0.8 mm` tooth base remains unchanged.",
        "",
        "## Preserved Geometry",
        "",
        "The builder imports the authoritative source STEP and modifies only the two female receiver interiors. It preserves the outer body, BS slope and pocket, axes, center bore, pin holes, `25.5 mm` lens seat, and all unrelated geometry. The lower mouth and lens-seat transitions preserve their original axial endpoints and remain straight conical chamfers. Enlarging only the receiver-side diameter necessarily changes their slopes from `45 degrees` to `44.443748 degrees` and `46.363928 degrees`; keeping both endpoints and exactly `45 degrees` would be geometrically impossible.",
        "",
        "The helix is constructed with extra runout at both ends and clipped back to the exact receiver interval. This prevents the thread from protruding through the mouth, transition, or adjacent body.",
        "",
        "## Fit Warning",
        "",
        "The unchanged A top male is approximately `29.8/30.6 mm` root/crest, and the revised A receiver is `29.8/30.6 mm` pilot/groove. This is a zero-nominal-clearance printed fit, enlarged by `0.2 mm` in diameter from yesterday's nearly fitting receiver. The C receiver remains the accepted `29.6/30.4 mm` geometry. Test the A fit before committing to the complete optical assembly.",
        "",
        "## Validation",
        "",
        f"- Source and output bbox: `{manifest['validation']['output']['bbox']['size']}` mm; preserved: `{checks['external_bbox_preserved']}`.",
        f"- All material changes are confined to the two receiver envelopes: `{checks['changes_confined_to_two_receiver_envelopes']}`.",
        f"- Relative to accepted run 1, the deltas match the A fit revision plus the bounded C-membrane removal: `{checks['changes_from_run1_match_A_fit_and_C_membrane_fix']}`.",
        f"- One solid: `{checks['single_solid']}`; OCCT valid after STEP round trip: `{checks['occt_valid']}`.",
        f"- Lower/A receiver measured `29.8/30.6 mm`: `{checks['lower_A_pivot_is_29p8'] and checks['lower_A_groove_is_30p6']}`.",
        f"- Side/C receiver remained `29.6/30.4 mm`: `{checks['side_C_pivot_is_29p6'] and checks['side_C_groove_is_30p4']}`.",
        f"- BS-to-C optical core is clear: `{checks['beam_splitter_to_C_centerline_is_clear']}`.",
        f"- C receiver has no fusion membrane: `{checks['C_receiver_has_no_fusion_membrane']}`.",
        f"- Thread runouts remain bounded: `{checks['lower_thread_clipped_to_receiver'] and checks['side_thread_clipped_to_receiver']}`.",
        f"- Lower transition endpoints and required slopes preserved: `{checks['lower_transition_endpoints_and_slopes_match']}`.",
        f"- Render mesh is one watertight, consistently wound component: `{checks['mesh_is_watertight'] and checks['mesh_winding_is_consistent'] and checks['mesh_is_one_component']}`.",
        f"- Welded 3MF reopens as one watertight, consistently wound component with matching bounds: `{checks['three_mf_is_watertight'] and checks['three_mf_winding_is_consistent'] and checks['three_mf_indices_are_valid'] and checks['three_mf_is_one_component'] and checks['three_mf_bounds_match_stl']}`.",
        "",
        "## Run History",
        "",
        f"- `{RUN_1_NAME}`: accepted A/C `29.6/29.6 mm` female-pivot build.",
        f"- `{RUN_2_NAME}`: current A/C `29.8/29.6 mm` female-pivot build.",
        f"- `{RUN_3_NAME}`: preserves those pivots and removes the accidental `0.10 mm` C-bore fusion membrane.",
        "- Root `USE_THIS_*` files always point to the current checked build.",
        "",
        "## Rebuild",
        "",
        "```bash",
        f"cad/.conda/cad-python/bin/python {repo_path(Path(__file__))}",
        f"blender --background --python {repo_path(DESIGN_DIR / 'render_openhi_a_c_bs_a29p8_c29p6_female_pivots.py')}",
        "```",
        "",
    ]
    (DESIGN_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def sync_nutstore(root_step: Path, root_3mf: Path) -> dict[str, str]:
    NUTSTORE_ROOT.mkdir(parents=True, exist_ok=True)
    direct_step = NUTSTORE_ROOT / root_step.name
    direct_3mf = NUTSTORE_ROOT / root_3mf.name
    shutil.copy2(root_step, direct_step)
    shutil.copy2(root_3mf, direct_3mf)
    shutil.copytree(
        DESIGN_DIR,
        NUTSTORE_DIR,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return {
        "folder": str(NUTSTORE_DIR),
        "direct_step": str(direct_step),
        "direct_3mf": str(direct_3mf),
    }


def main() -> None:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"missing source STEP: {SOURCE_STEP}")
    if not SOURCE_SHAPR.exists():
        raise FileNotFoundError(f"missing source Shapr archive: {SOURCE_SHAPR}")

    assembly, cutters = build()
    outputs = export_parts(assembly, cutters)
    source = cq.importers.importStep(str(SOURCE_STEP)).val()
    output_step = ROOT / outputs["assembly_step"]
    validation = validate_export(source, output_step)
    mesh_validation = validate_mesh(ROOT / outputs["assembly_stl"])
    three_mf_validation = validate_3mf(ROOT / outputs["assembly_3mf"])
    validation["mesh"] = mesh_validation
    validation["three_mf"] = three_mf_validation
    validation["checks"].pop("all_pass", None)
    validation["checks"].update(
        {
            "mesh_is_watertight": mesh_validation["watertight"],
            "mesh_winding_is_consistent": mesh_validation[
                "winding_consistent"
            ],
            "mesh_is_one_component": (
                mesh_validation["component_count"] == 1
                and mesh_validation["body_count"] == 1
            ),
            "three_mf_is_watertight": three_mf_validation["watertight"],
            "three_mf_indices_are_valid": three_mf_validation["indices_valid"],
            "three_mf_winding_is_consistent": three_mf_validation[
                "winding_consistent"
            ],
            "three_mf_is_one_component": (
                three_mf_validation["component_count"] == 1
                and three_mf_validation["body_count"] == 1
            ),
            "three_mf_bounds_match_stl": (
                bounds_match(
                    three_mf_validation["bounds_mm"],
                    mesh_validation["bounds_mm"],
                )
            ),
        }
    )
    validation["checks"]["all_pass"] = all(validation["checks"].values())
    if not validation["checks"]["all_pass"]:
        failed = [
            name for name, passed in validation["checks"].items() if not passed
        ]
        raise RuntimeError(f"validation failed: {failed}")

    manifest: dict[str, Any] = {
        "name": STEM,
        "design_date": "2026-08-30",
        "units": "mm",
        "source": {
            "step": repo_path(SOURCE_STEP),
            "step_sha256": sha256_file(SOURCE_STEP),
            "shapr": repo_path(SOURCE_SHAPR),
            "shapr_sha256": sha256_file(SOURCE_SHAPR),
            "authority": "STEP B-rep; Shapr stores this object as imported bodies",
        },
        "accepted_baseline": {
            "run": RUN_1_NAME,
            "step": repo_path(ACCEPTED_RUN_STEP),
            "step_sha256": sha256_file(ACCEPTED_RUN_STEP),
            "comparison_contract": (
                "source delta stays inside the two receiver envelopes; "
                "accepted-run C receiver volume and area remain identical; "
                "A receiver material delta is nonzero"
            ),
        },
        "scope": {
            "modified": [
                "A+ C + BS lower/A-branch female receiver pivot and groove diameters",
                "C receiver smooth bore extended 0.1 mm through the fusion overlap",
            ],
            "explicitly_unchanged": [
                "A+ C + BS side/C-branch 29.6/30.4 mm thread geometry",
                "cad/extracted/OpenHI_STEP/A.step",
                "cad/extracted/OpenHI_STEP/C.step",
                "all A+ C + BS geometry outside the two receiver interiors",
            ],
        },
        "thread": {
            "lower_A_female_pivot_mm": LOWER_A_FEMALE_PIVOT,
            "lower_A_female_groove_mm": round(
                LOWER_A_FEMALE_GROOVE,
                6,
            ),
            "side_C_female_pivot_mm": SIDE_C_FEMALE_PIVOT,
            "side_C_female_groove_mm": round(
                SIDE_C_FEMALE_GROOVE,
                6,
            ),
            "pitch_mm": PITCH,
            "radial_tooth_height_mm": TOOTH_RADIAL_HEIGHT,
            "tooth_base_mm": TOOTH_BASE,
            "hand": "right-hand",
            "construction_runout_each_end_mm": round(RUNOUT + PITCH, 6),
            "runout_policy": "construct beyond both ends, then clip to true interval",
        },
        "lower_receiver": {
            "axis": "Z",
            "center_mm": list(LOWER_CENTER),
            "mouth_z_range_mm": [LOWER_MOUTH_Z0, LOWER_THREAD_Z0],
            "thread_z_range_mm": [
                LOWER_THREAD_Z0,
                round(LOWER_THREAD_Z0 + LOWER_THREAD_LENGTH, 6),
            ],
            "lens_transition_z_range_mm": [
                LOWER_TRANSITION_Z0,
                LOWER_LENS_SEAT_Z,
            ],
            "mouth_chamfer_angle_deg": round(LOWER_MOUTH_ANGLE_DEG, 6),
            "lens_transition_angle_deg": round(
                LOWER_LENS_TRANSITION_ANGLE_DEG, 6
            ),
            "transition_policy": (
                "preserve source axial endpoints and continuously meet revised pivot"
            ),
            "lens_seat_diameter_mm": LOWER_LENS_SEAT_DIAMETER,
        },
        "side_receiver": {
            "axis": "X",
            "center_mm": list(SIDE_CENTER),
            "thread_x_range_mm": [
                SIDE_THREAD_X0,
                round(SIDE_THREAD_X0 + SIDE_THREAD_LENGTH, 6),
            ],
            "pilot_x_range_mm": [
                SIDE_PILOT_X0,
                round(SIDE_PILOT_X0 + SIDE_PILOT_LENGTH, 6),
            ],
            "fusion_overlap_clearance_mm": round(
                SIDE_THREAD_X0 - SIDE_PILOT_X0,
                6,
            ),
        },
        "outputs": outputs,
        "validation": validation,
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    root_step = ROOT / outputs["root_step"]
    root_3mf = ROOT / outputs["root_3mf"]
    manifest["nutstore"] = {
        "folder": str(NUTSTORE_DIR),
        "direct_step": str(NUTSTORE_ROOT / root_step.name),
        "direct_3mf": str(NUTSTORE_ROOT / root_3mf.name),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    sync_nutstore(root_step, root_3mf)
    print(
        json.dumps(
            {
                "root_step": outputs["root_step"],
                "manifest": outputs["manifest"],
                "nutstore": manifest["nutstore"],
                "validation": validation["checks"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
