#!/usr/bin/env python3
"""Rebuild only the right Lens C female receiver at a 29.8 mm pivot.

The authoritative body is imported from ``Lens C holder.step``.  The source
contains a separate left male helical tooth and a main body.  This script
reuses that male tooth exactly, preserves the main body through the 25.5 mm
lens-seat plane, and cleanly rebuilds only the positive-X female receiver.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import numpy as np
from pathlib import Path
import shutil
import sys
from typing import Any
import zipfile
from xml.etree import ElementTree

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import (
    GeomAbs_BSplineSurface,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
)
import trimesh


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_lens_c_holder_right_female_29p8_pivot"
RUN_NAME = "run-1-right-female-29p8-pivot-20260815T050539Z"
RUN_DIR = DESIGN_DIR / "runs" / RUN_NAME
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/Lens C holder.step"
SOURCE_SHAPR = ROOT / "cad/extracted/OpenHI.shapr"
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
NUTSTORE_RUN = NUTSTORE_ROOT / DESIGN_DIR.name / RUN_NAME

TOOLS_DIR = ROOT / "cad/tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from simple_3mf import export_stl_as_3mf  # noqa: E402


AXIS_Y = 210.0
AXIS_Z = 600.0
PITCH = 0.8
TOOTH_RADIAL_HEIGHT = 0.4
TOOTH_BASE = 0.8
RUNOUT = 0.4
THREAD_OVERLAP = 0.10
FEMALE_PHASE_SHIFT = -0.30

SOURCE_PIVOT = 30.2
SOURCE_GROOVE = 31.0
TARGET_PIVOT = 29.8
TARGET_GROOVE = TARGET_PIVOT + 2.0 * TOOTH_RADIAL_HEIGHT
LENS_SEAT_DIAMETER = 25.5
OUTER_MOUTH_DIAMETER = 40.0

LENS_SEAT_END_X = 325.0
LOWER_TRANSITION_LENGTH = (TARGET_PIVOT - LENS_SEAT_DIAMETER) / 2.0
THREAD_X0 = LENS_SEAT_END_X + LOWER_TRANSITION_LENGTH
THREAD_LENGTH = 7.75
THREAD_X1 = THREAD_X0 + THREAD_LENGTH
UPPER_MOUTH_LENGTH = (OUTER_MOUTH_DIAMETER - TARGET_PIVOT) / 2.0
UPPER_MOUTH_X1 = THREAD_X1 + UPPER_MOUTH_LENGTH


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
        "center": [
            round((box.xmin + box.xmax) / 2.0, 6),
            round((box.ymin + box.ymax) / 2.0, 6),
            round((box.zmin + box.zmax) / 2.0, 6),
        ],
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


def compound(parts: list[cq.Shape | cq.Workplane]) -> cq.Workplane:
    shapes: list[cq.Shape] = []
    for part in parts:
        shape = part.val() if isinstance(part, cq.Workplane) else part
        shapes.extend(shape.Solids() or [shape])
    return workplane(cq.Compound.makeCompound(shapes))


def x_cylinder(
    diameter: float,
    x0: float,
    length: float,
    center_y: float = AXIS_Y,
    center_z: float = AXIS_Z,
) -> cq.Workplane:
    return workplane(
        cq.Solid.makeCylinder(
            diameter / 2.0,
            length,
            cq.Vector(x0, center_y, center_z),
            cq.Vector(1.0, 0.0, 0.0),
        )
    )


def x_cone(
    diameter0: float,
    diameter1: float,
    x0: float,
    length: float,
    center_y: float = AXIS_Y,
    center_z: float = AXIS_Z,
) -> cq.Workplane:
    return workplane(
        cq.Solid.makeCone(
            diameter0 / 2.0,
            diameter1 / 2.0,
            length,
            cq.Vector(x0, center_y, center_z),
            cq.Vector(1.0, 0.0, 0.0),
        )
    )


def x_clip(x0: float, length: float, span: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(length, span, span, centered=(False, True, True))
        .translate((x0, 0.0, 0.0))
    )


def keep_through_x(shape: cq.Shape, xmax: float) -> cq.Workplane:
    box = shape.BoundingBox()
    xmin = box.xmin - 1.0
    return (
        cq.Workplane("XY")
        .box(
            xmax - xmin,
            box.ylen + 2.0,
            box.zlen + 2.0,
            centered=(False, True, True),
        )
        .translate(
            (
                xmin,
                (box.ymin + box.ymax) / 2.0,
                (box.zmin + box.zmax) / 2.0,
            )
        )
    )


def x_thread_tooth(
    root_diameter: float,
    crest_diameter: float,
    length: float,
    *,
    x0: float,
    phase_shift: float,
) -> cq.Workplane:
    """Build the source-style right-hand helix beyond both ends, then clip."""
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
    swept = profile.sweep(path, isFrenet=True, combine=False)
    return swept.intersect(x_clip(x0, length, crest_diameter + 4.0))


def female_thread_cutter() -> cq.Workplane:
    return x_thread_tooth(
        TARGET_PIVOT,
        TARGET_GROOVE,
        THREAD_LENGTH,
        x0=THREAD_X0,
        phase_shift=FEMALE_PHASE_SHIFT,
    ).translate((0.0, AXIS_Y, AXIS_Z))


def make_receiver() -> tuple[cq.Workplane, cq.Workplane, dict[str, cq.Workplane]]:
    outer = x_cylinder(
        OUTER_MOUTH_DIAMETER,
        LENS_SEAT_END_X,
        UPPER_MOUTH_X1 - LENS_SEAT_END_X,
    )
    cutters = {
        "lens_transition": x_cone(
            LENS_SEAT_DIAMETER,
            TARGET_PIVOT,
            LENS_SEAT_END_X,
            LOWER_TRANSITION_LENGTH,
        ),
        "pilot": x_cylinder(TARGET_PIVOT, THREAD_X0, THREAD_LENGTH),
        "thread": female_thread_cutter(),
        "mouth": x_cone(
            TARGET_PIVOT,
            OUTER_MOUTH_DIAMETER,
            THREAD_X1,
            UPPER_MOUTH_LENGTH,
        ),
    }
    # These cutter solids overlap only at a narrow radial seam. A small fuzzy
    # tolerance preserves that union for either helix hand; zero tolerance can
    # collapse the result even though both source solids are individually valid.
    cutters["threaded_bore"] = cutters["pilot"].union(
        cutters["thread"],
        clean=True,
        glue=False,
        tol=0.002,
    )
    smooth = (
        outer.cut(cutters["lens_transition"])
        .cut(cutters["pilot"])
        .cut(cutters["mouth"])
        .clean()
    )
    threaded = (
        outer.cut(cutters["lens_transition"])
        .cut(cutters["threaded_bore"])
        .cut(cutters["mouth"])
        .clean()
    )
    return largest_solid(threaded), largest_solid(smooth), {"outer": outer, **cutters}


def build() -> tuple[cq.Workplane, cq.Workplane, dict[str, cq.Workplane]]:
    source = cq.importers.importStep(str(SOURCE_STEP)).val()
    solids = source.Solids()
    if len(solids) != 2:
        raise RuntimeError("Lens C holder source must contain exactly two solids")
    preserved_male = min(solids, key=lambda item: item.Volume())
    source_body = max(solids, key=lambda item: item.Volume())
    trimmed_body = source_body.intersect(
        keep_through_x(source_body, LENS_SEAT_END_X).val()
    )
    threaded_receiver, smooth_receiver, parts = make_receiver()
    threaded_body = largest_solid(
        workplane(trimmed_body).union(threaded_receiver).clean()
    )
    smooth_body = largest_solid(
        workplane(trimmed_body).union(smooth_receiver).clean()
    )
    parts.update(
        {
            "preserved_male": workplane(preserved_male),
            "trimmed_body": workplane(trimmed_body),
            "threaded_receiver": threaded_receiver,
            "smooth_receiver": smooth_receiver,
            "threaded_body": threaded_body,
            "smooth_body": smooth_body,
        }
    )
    return (
        compound([preserved_male, threaded_body]),
        compound([preserved_male, smooth_body]),
        parts,
    )


def radial_probe(shape: cq.Shape) -> dict[str, Any]:
    cylinders: list[float] = []
    grooves: list[float] = []
    groove_bounds: list[list[float]] = []
    cones: list[dict[str, Any]] = []
    for face in shape.Faces():
        box = face.BoundingBox()
        if box.xmax < 324.4 or box.xmin > UPPER_MOUTH_X1 + 0.01:
            continue
        adaptor = BRepAdaptor_Surface(face.wrapped, True)
        surface_type = adaptor.GetType()
        if surface_type == GeomAbs_Cylinder:
            cylinders.append(2.0 * adaptor.Cylinder().Radius())
        elif surface_type == GeomAbs_Cone:
            cones.append(
                {
                    "semi_angle_deg": round(
                        abs(math.degrees(adaptor.Cone().SemiAngle())), 6
                    ),
                    "x_bounds_mm": [round(box.xmin, 6), round(box.xmax, 6)],
                }
            )
        if surface_type != GeomAbs_BSplineSurface:
            continue
        samples: list[float] = []
        vertices, _ = face.tessellate(0.015)
        for vertex in vertices:
            if THREAD_X0 - 0.02 <= vertex.x <= THREAD_X1 + 0.02:
                diameter = 2.0 * math.hypot(
                    vertex.y - AXIS_Y,
                    vertex.z - AXIS_Z,
                )
                if TARGET_PIVOT - 0.2 <= diameter <= TARGET_GROOVE + 0.2:
                    samples.append(diameter)
        if samples:
            grooves.extend(samples)
            groove_bounds.append([round(box.xmin, 6), round(box.xmax, 6)])
    return {
        "cylinder_diameters_mm": sorted(
            {round(value, 6) for value in cylinders}
        ),
        "bspline_sample_min_diameter_mm": (
            round(min(grooves), 4) if grooves else None
        ),
        "bspline_sample_max_diameter_mm": (
            round(max(grooves), 4) if grooves else None
        ),
        "matched_bspline_x_bounds_mm": groove_bounds,
        "cone_surfaces": cones,
    }


def male_probe(shape: cq.Shape) -> dict[str, Any]:
    cylinders: list[float] = []
    tooth_samples: list[float] = []
    bspline_bounds: list[list[float]] = []
    for face in shape.Faces():
        box = face.BoundingBox()
        if box.xmin > 296.0 or box.xmax < 289.9:
            continue
        adaptor = BRepAdaptor_Surface(face.wrapped, True)
        surface_type = adaptor.GetType()
        if surface_type == GeomAbs_Cylinder:
            direction = adaptor.Cylinder().Axis().Direction()
            if abs(direction.X()) > 0.99:
                cylinders.append(2.0 * adaptor.Cylinder().Radius())
        if surface_type != GeomAbs_BSplineSurface:
            continue
        samples: list[float] = []
        vertices, _ = face.tessellate(0.015)
        for vertex in vertices:
            if 289.9 <= vertex.x <= 296.0:
                diameter = 2.0 * math.hypot(
                    vertex.y - AXIS_Y,
                    vertex.z - AXIS_Z,
                )
                if 29.6 <= diameter <= 30.8:
                    samples.append(diameter)
        if samples:
            tooth_samples.extend(samples)
            bspline_bounds.append([round(box.xmin, 6), round(box.xmax, 6)])
    return {
        "cylinder_diameters_mm": sorted(
            {round(value, 6) for value in cylinders}
        ),
        "bspline_sample_min_diameter_mm": (
            round(min(tooth_samples), 4) if tooth_samples else None
        ),
        "bspline_sample_max_diameter_mm": (
            round(max(tooth_samples), 4) if tooth_samples else None
        ),
        "matched_bspline_x_bounds_mm": bspline_bounds,
    }


def receiver_helix_probe(shape: cq.Shape) -> dict[str, Any]:
    crest_points: list[tuple[float, float]] = []
    for face in shape.Faces():
        box = face.BoundingBox()
        adaptor = BRepAdaptor_Surface(face.wrapped, True)
        if adaptor.GetType() != GeomAbs_BSplineSurface or box.xmin < 320.0:
            continue
        vertices, _ = face.tessellate(0.01)
        samples = [
            (
                vertex.x,
                math.hypot(vertex.y - AXIS_Y, vertex.z - AXIS_Z),
                math.atan2(vertex.z - AXIS_Z, vertex.y - AXIS_Y),
            )
            for vertex in vertices
        ]
        maximum_radius = max(radius for _, radius, _ in samples)
        crest_points.extend(
            (x_value, angle)
            for x_value, radius, angle in samples
            if radius >= maximum_radius - 0.015
        )
    buckets: dict[float, list[float]] = {}
    for x_value, angle in crest_points:
        buckets.setdefault(round(x_value, 3), []).append(angle)
    x_values: list[float] = []
    angles: list[float] = []
    for x_value in sorted(buckets):
        values = buckets[x_value]
        angles.append(
            math.atan2(
                sum(math.sin(value) for value in values),
                sum(math.cos(value) for value in values),
            )
        )
        x_values.append(x_value)
    if len(x_values) < 20:
        return {"available": False, "crest_sample_count": len(x_values)}
    unwrapped = np.unwrap(np.asarray(angles))
    slope = float(np.polyfit(np.asarray(x_values), unwrapped, 1)[0])
    return {
        "available": True,
        "crest_sample_count": len(x_values),
        "angle_slope_rad_per_mm": round(slope, 6),
        "turns_per_mm": round(slope / (2.0 * math.pi), 6),
        "pitch_mm": round(abs(2.0 * math.pi / slope), 6),
        "slope_sign": 1 if slope > 0.0 else -1,
    }


def validate_change_scope(source: cq.Shape, output: cq.Shape) -> dict[str, float]:
    envelope = x_cylinder(41.0, 324.9, UPPER_MOUTH_X1 - 324.9 + 0.1)
    source_body = max(source.Solids(), key=lambda item: item.Volume())
    output_body = max(output.Solids(), key=lambda item: item.Volume())

    def cut_shape(left: cq.Shape, right: cq.Shape) -> cq.Shape | None:
        operation = BRepAlgoAPI_Cut(left.wrapped, right.wrapped)
        operation.Build()
        if not operation.IsDone():
            raise RuntimeError("OCCT change-scope Boolean did not complete")
        result = operation.Shape()
        if result.IsNull():
            return None
        return cq.Shape.cast(result)

    def volume(shape: cq.Shape | None) -> float:
        return 0.0 if shape is None else shape.Volume()

    removed = cut_shape(source_body, output_body)
    added = cut_shape(output_body, source_body)
    removed_outside = (
        None if removed is None else cut_shape(removed, envelope.val())
    )
    added_outside = None if added is None else cut_shape(added, envelope.val())
    return {
        "removed_total_mm3": round(volume(removed), 6),
        "added_total_mm3": round(volume(added), 6),
        "removed_outside_receiver_envelope_mm3": round(volume(removed_outside), 9),
        "added_outside_receiver_envelope_mm3": round(volume(added_outside), 9),
    }


def validate_mesh(path: Path) -> dict[str, Any]:
    mesh = trimesh.load(path, force="mesh", process=True)
    components = list(mesh.split(only_watertight=False))
    component_checks = [
        {
            "vertices": len(component.vertices),
            "faces": len(component.faces),
            "watertight": bool(component.is_watertight),
            "winding_consistent": bool(component.is_winding_consistent),
            "volume_mm3": round(float(component.volume), 6),
        }
        for component in components
    ]
    parent = list(range(len(mesh.vertices)))

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

    referenced: set[int] = set()
    for first, second, third in mesh.faces:
        indices = (int(first), int(second), int(third))
        referenced.update(indices)
        union(indices[0], indices[1])
        union(indices[1], indices[2])
    component_count = len(components)
    return {
        "path": repo_path(path),
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "component_count": component_count,
        "body_count": component_count,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "all_components_watertight": all(
            item["watertight"] for item in component_checks
        ),
        "all_components_winding_consistent": all(
            item["winding_consistent"] for item in component_checks
        ),
        "components": component_checks,
        "volume_mm3": round(float(mesh.volume), 6),
        "bounds_mm": [
            [round(float(value), 6) for value in row] for row in mesh.bounds
        ],
    }


def repair_bounded_planar_tessellation_seam(path: Path) -> dict[str, Any]:
    """Cap the source STEP's one tiny planar STL seam under strict guards.

    OCCT validates the source and revised STEP as closed solids.  CadQuery's
    STL tessellator nevertheless emits one four-edge planar opening in a reused
    source face at z=635.  This mesh-only repair is rejected unless the opening
    is a single, tiny, planar loop and the repaired result is watertight.
    """
    mesh = trimesh.load(path, force="mesh", process=True)
    components = list(mesh.split(only_watertight=False))
    counts = np.bincount(mesh.edges_unique_inverse)
    boundary_edges = mesh.edges_unique[counts == 1]
    if (
        len(components) == 2
        and all(component.is_watertight for component in components)
        and len(boundary_edges) == 0
    ):
        return {
            "applied": False,
            "reason": (
                "the source-preserved split male tooth and main body are two "
                "closed printable shells; no mesh repair is appropriate"
            ),
            "boundary_edges_before": 0,
            "faces_added": 0,
            "closed_component_count": 2,
        }
    if mesh.is_watertight:
        return {
            "applied": False,
            "reason": "mesh was already watertight",
            "boundary_edges_before": 0,
            "faces_added": 0,
        }
    boundary_edges = mesh.edges_unique[counts == 1]
    nonmanifold_edges = mesh.edges_unique[counts > 2]
    if len(nonmanifold_edges) != 0 or len(boundary_edges) > 8:
        raise RuntimeError(
            "refusing broad mesh repair: opening is not one tiny manifold seam"
        )

    adjacency: dict[int, list[int]] = {}
    unused: set[tuple[int, int]] = set()
    for left_raw, right_raw in boundary_edges:
        left, right = int(left_raw), int(right_raw)
        adjacency.setdefault(left, []).append(right)
        adjacency.setdefault(right, []).append(left)
        unused.add(tuple(sorted((left, right))))
    loops: list[list[int]] = []
    while unused:
        first_edge = next(iter(unused))
        loop = [first_edge[0]]
        current = first_edge[0]
        while True:
            candidates = [
                neighbor
                for neighbor in adjacency[current]
                if tuple(sorted((current, neighbor))) in unused
            ]
            if not candidates:
                break
            next_vertex = candidates[0]
            unused.remove(tuple(sorted((current, next_vertex))))
            if next_vertex == loop[0]:
                break
            loop.append(next_vertex)
            current = next_vertex
        loops.append(loop)
    if len(loops) != 1 or not 3 <= len(loops[0]) <= 8:
        raise RuntimeError(f"refusing unexpected boundary loops: {loops}")

    boundary_points = mesh.vertices[np.unique(boundary_edges)]
    extents = np.ptp(boundary_points, axis=0)
    planar_axis = int(np.argmin(extents))
    if extents[planar_axis] > 0.001 or max(extents) > 2.5:
        raise RuntimeError(
            f"refusing non-planar or large STL opening, extents={extents.tolist()}"
        )

    directed_edges: Counter[tuple[int, int]] = Counter()
    for first_raw, second_raw, third_raw in mesh.faces:
        first, second, third = int(first_raw), int(second_raw), int(third_raw)
        for start, end in ((first, second), (second, third), (third, first)):
            directed_edges[(start, end)] += 1
    loop = loops[0]
    if directed_edges[(loop[0], loop[1])] > 0:
        loop = list(reversed(loop))
    cap_faces = [
        [loop[0], loop[index], loop[index + 1]]
        for index in range(1, len(loop) - 1)
    ]
    repaired = trimesh.Trimesh(
        vertices=mesh.vertices.copy(),
        faces=np.vstack((mesh.faces, np.asarray(cap_faces, dtype=np.int64))),
        process=False,
    )
    if not repaired.is_watertight or not repaired.is_winding_consistent:
        raise RuntimeError("bounded planar seam repair did not produce a closed mesh")
    repaired.export(path)
    return {
        "applied": True,
        "reason": "capped one tiny planar source-tessellation seam",
        "boundary_edges_before": int(len(boundary_edges)),
        "boundary_loop_vertices": int(len(loop)),
        "planar_axis": ("x", "y", "z")[planar_axis],
        "opening_extents_mm": [round(float(value), 6) for value in extents],
        "faces_added": len(cap_faces),
        "watertight_after": bool(repaired.is_watertight),
        "winding_consistent_after": bool(repaired.is_winding_consistent),
    }


def validate_3mf(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        model_name = next(
            name for name in archive.namelist() if name.lower().endswith(".model")
        )
        root = ElementTree.fromstring(archive.read(model_name))
    namespace_uri = root.tag.split("}", 1)[0].lstrip("{")
    namespace = {"m": namespace_uri}
    mesh_nodes = root.findall(".//m:object/m:mesh", namespace)
    if len(mesh_nodes) != 1:
        raise RuntimeError(f"expected one 3MF mesh, found {len(mesh_nodes)}")
    mesh_node = mesh_nodes[0]
    vertices = [
        (
            float(vertex.attrib["x"]),
            float(vertex.attrib["y"]),
            float(vertex.attrib["z"]),
        )
        for vertex in mesh_node.findall("./m:vertices/m:vertex", namespace)
    ]
    triangles = [
        (
            int(triangle.attrib["v1"]),
            int(triangle.attrib["v2"]),
            int(triangle.attrib["v3"]),
        )
        for triangle in mesh_node.findall("./m:triangles/m:triangle", namespace)
    ]
    indices_valid = all(
        0 <= index < len(vertices)
        for triangle in triangles
        for index in triangle
    )
    model_mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(triangles, dtype=np.int64),
        process=True,
    )
    components = list(model_mesh.split(only_watertight=False))
    minimum = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maximum = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    return {
        "path": repo_path(path),
        "unit": root.attrib.get("unit"),
        "vertices": len(vertices),
        "faces": len(triangles),
        "component_count": len(components),
        "indices_valid": indices_valid,
        "overall_watertight": bool(model_mesh.is_watertight),
        "watertight": bool(components)
        and all(component.is_watertight for component in components),
        "winding_consistent": bool(components)
        and all(component.is_winding_consistent for component in components),
        "bounds_mm": [
            [round(value, 6) for value in minimum],
            [round(value, 6) for value in maximum],
        ],
    }


def bounds_match(
    left: list[list[float]],
    right: list[list[float]],
    tolerance: float = 0.001,
) -> bool:
    return all(
        abs(left_value - right_value) <= tolerance
        for left_row, right_row in zip(left, right)
        for left_value, right_value in zip(left_row, right_row)
    )


def validate_step(source: cq.Shape, output_path: Path) -> dict[str, Any]:
    output = cq.importers.importStep(str(output_path)).val()
    source_summary = shape_summary(source)
    output_summary = shape_summary(output)
    probe = radial_probe(output)
    source_male = min(source.Solids(), key=lambda item: item.Volume())
    output_male = min(output.Solids(), key=lambda item: item.Volume())
    source_male_summary = shape_summary(source_male)
    output_male_summary = shape_summary(output_male)
    source_male_probe = male_probe(source)
    output_male_probe = male_probe(output)
    source_helix_probe = receiver_helix_probe(source)
    output_helix_probe = receiver_helix_probe(output)
    scope = validate_change_scope(source, output)
    cone_45_bounds = [
        item["x_bounds_mm"]
        for item in probe["cone_surfaces"]
        if near(item["semi_angle_deg"], 45.0, 0.01)
    ]
    upper_intervals = sorted(
        (
            max(bounds[0], THREAD_X1),
            min(bounds[1], UPPER_MOUTH_X1),
        )
        for bounds in cone_45_bounds
        if bounds[1] >= THREAD_X1 - 0.01
        and bounds[0] <= UPPER_MOUTH_X1 + 0.01
    )
    upper_cursor = THREAD_X1
    for low, high in upper_intervals:
        if low <= upper_cursor + 0.01:
            upper_cursor = max(upper_cursor, high)
    thread_bounds = probe["matched_bspline_x_bounds_mm"]
    male_bbox_delta = max(
        abs(left - right)
        for left, right in zip(
            source_male_summary["bbox"]["min"] + source_male_summary["bbox"]["max"],
            output_male_summary["bbox"]["min"] + output_male_summary["bbox"]["max"],
        )
    )
    checks = {
        "two_source_solids_preserved": output_summary["solid_count"] == 2,
        "occt_valid": output_summary["occt_valid"],
        "external_bbox_preserved": source_summary["bbox"] == output_summary["bbox"],
        "changes_confined_to_right_receiver": (
            scope["removed_outside_receiver_envelope_mm3"] < 1e-6
            and scope["added_outside_receiver_envelope_mm3"] < 1e-6
        ),
        "target_pivot_is_29p8": any(
            near(value, TARGET_PIVOT)
            for value in probe["cylinder_diameters_mm"]
        ),
        "target_groove_is_30p6": near(
            probe["bspline_sample_max_diameter_mm"], TARGET_GROOVE
        ),
        "thread_root_is_29p8": near(
            probe["bspline_sample_min_diameter_mm"], TARGET_PIVOT
        ),
        "thread_hand_matches_source": (
            source_helix_probe.get("available", False)
            and output_helix_probe.get("available", False)
            and source_helix_probe["slope_sign"]
            == output_helix_probe["slope_sign"]
        ),
        "thread_pitch_matches_source": (
            source_helix_probe.get("available", False)
            and output_helix_probe.get("available", False)
            and abs(
                source_helix_probe["pitch_mm"]
                - output_helix_probe["pitch_mm"]
            )
            < 0.01
        ),
        "thread_is_clipped_to_true_interval": bool(thread_bounds)
        and all(
            low >= THREAD_X0 - 0.02 and high <= THREAD_X1 + 0.02
            for low, high in thread_bounds
        ),
        "both_45_degree_transitions_present": any(
            near(bounds[0], LENS_SEAT_END_X, 0.01)
            and near(bounds[1], THREAD_X0, 0.01)
            for bounds in cone_45_bounds
        )
        and upper_cursor >= UPPER_MOUTH_X1 - 0.01,
        "lens_seat_25p5_preserved": any(
            near(value, LENS_SEAT_DIAMETER)
            for value in probe["cylinder_diameters_mm"]
        ),
        "source_30p2_receiver_removed": not any(
            near(value, SOURCE_PIVOT)
            for value in probe["cylinder_diameters_mm"]
        ),
        "left_male_bbox_unchanged": male_bbox_delta < 0.0001,
        "left_male_volume_unchanged": abs(
            source_male_summary["volume_mm3"] - output_male_summary["volume_mm3"]
        ) < 0.05,
        "left_male_probe_unchanged": source_male_probe == output_male_probe,
        "left_male_pivot_is_29p8": any(
            near(value, 29.8)
            for value in output_male_probe["cylinder_diameters_mm"]
        ),
        "left_male_crest_is_30p6": near(
            output_male_probe["bspline_sample_max_diameter_mm"], 30.6
        ),
    }
    return {
        "source": source_summary,
        "output": output_summary,
        "change_scope": scope,
        "receiver_probe": probe,
        "source_left_male": source_male_summary,
        "output_left_male": output_male_summary,
        "source_left_male_probe": source_male_probe,
        "output_left_male_probe": output_male_probe,
        "source_receiver_helix_probe": source_helix_probe,
        "output_receiver_helix_probe": output_helix_probe,
        "left_male_bbox_max_delta_mm": round(male_bbox_delta, 9),
        "checks": checks,
    }


def export_geometry() -> tuple[dict[str, Path], dict[str, Any]]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    threaded, smooth, parts = build()
    paths = {
        "assembly_step": ARTIFACT_DIR / f"{STEM}.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "assembly_3mf": ARTIFACT_DIR / f"{STEM}.3mf",
        "smooth_editable_step": ARTIFACT_DIR / f"{STEM}_smooth_editable.step",
        "receiver_cutters_step": ARTIFACT_DIR / f"{STEM}_receiver_cutters.step",
        "preserved_left_male_step": ARTIFACT_DIR / f"{STEM}_preserved_left_male.step",
        "threaded_body_step": ARTIFACT_DIR / f"{STEM}_threaded_body.step",
        "smooth_body_step": ARTIFACT_DIR / f"{STEM}_smooth_body.step",
        "threaded_receiver_step": ARTIFACT_DIR / f"{STEM}_threaded_receiver.step",
        "root_step": DESIGN_DIR / f"USE_THIS_{STEM}.step",
        "root_3mf": DESIGN_DIR / f"USE_THIS_{STEM}.3mf",
        "root_smooth_step": DESIGN_DIR / f"USE_THIS_{STEM}_smooth_editable.step",
    }
    exporters.export(threaded, str(paths["assembly_step"]))
    exporters.export(
        threaded,
        str(paths["assembly_stl"]),
        tolerance=0.02,
        angularTolerance=0.10,
    )
    mesh_repair = repair_bounded_planar_tessellation_seam(paths["assembly_stl"])
    export_stl_as_3mf(
        paths["assembly_stl"],
        paths["assembly_3mf"],
        title=STEM,
    )
    exporters.export(smooth, str(paths["smooth_editable_step"]))
    cutter_compound = cq.Compound.makeCompound(
        [
            parts[key].val()
            for key in ("lens_transition", "pilot", "thread", "mouth")
        ]
    )
    exporters.export(workplane(cutter_compound), str(paths["receiver_cutters_step"]))
    exporters.export(parts["preserved_male"], str(paths["preserved_left_male_step"]))
    exporters.export(parts["threaded_body"], str(paths["threaded_body_step"]))
    exporters.export(parts["smooth_body"], str(paths["smooth_body_step"]))
    exporters.export(parts["threaded_receiver"], str(paths["threaded_receiver_step"]))
    shutil.copy2(paths["assembly_step"], paths["root_step"])
    shutil.copy2(paths["assembly_3mf"], paths["root_3mf"])
    shutil.copy2(paths["smooth_editable_step"], paths["root_smooth_step"])

    source = cq.importers.importStep(str(SOURCE_STEP)).val()
    validation = validate_step(source, paths["assembly_step"])
    smooth_roundtrip = cq.importers.importStep(str(paths["smooth_editable_step"])).val()
    validation["smooth_editable"] = shape_summary(smooth_roundtrip)
    validation["mesh_repair"] = mesh_repair
    validation["mesh"] = validate_mesh(paths["assembly_stl"])
    validation["three_mf"] = validate_3mf(paths["assembly_3mf"])
    checks = validation["checks"]
    checks.update(
        {
            "smooth_editable_is_valid_two_solid_source_structure": (
                validation["smooth_editable"]["occt_valid"]
                and validation["smooth_editable"]["solid_count"] == 2
            ),
            "mesh_has_two_closed_source_components": (
                validation["mesh"]["all_components_watertight"]
                and validation["mesh"]["all_components_winding_consistent"]
                and validation["mesh"]["component_count"] == 2
                and validation["mesh"]["body_count"] == 2
            ),
            "mesh_repair_is_bounded": (
                not mesh_repair["applied"]
                or (
                    mesh_repair["boundary_edges_before"] <= 8
                    and mesh_repair["faces_added"] <= 6
                    and mesh_repair["watertight_after"]
                    and mesh_repair["winding_consistent_after"]
                )
            ),
            "three_mf_has_two_closed_source_components": (
                validation["three_mf"]["watertight"]
                and validation["three_mf"]["winding_consistent"]
                and validation["three_mf"]["indices_valid"]
                and validation["three_mf"]["component_count"] == 2
            ),
            "three_mf_bounds_match_stl": bounds_match(
                validation["three_mf"]["bounds_mm"],
                validation["mesh"]["bounds_mm"],
            ),
        }
    )
    checks["all_pass"] = all(checks.values())
    if not checks["all_pass"]:
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"validation failed: {failed}")
    return paths, validation


def manifest_payload(paths: dict[str, Path], validation: dict[str, Any]) -> dict[str, Any]:
    outputs = {key: repo_path(path) for key, path in paths.items()}
    outputs.update(
        {
            "full_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_render.png"),
            "thread_detail_render_png": repo_path(
                ARTIFACT_DIR / f"{STEM}_thread_detail.png"
            ),
            "cutaway_render_png": repo_path(
                ARTIFACT_DIR / f"{STEM}_thread_cutaway.png"
            ),
            "blend": repo_path(ARTIFACT_DIR / f"{STEM}.blend"),
            "manifest": repo_path(ARTIFACT_DIR / "manifest.json"),
        }
    )
    return {
        "name": STEM,
        "design_date": "2026-08-15",
        "units": "mm",
        "run": RUN_NAME,
        "source": {
            "step": repo_path(SOURCE_STEP),
            "step_sha256": sha256_file(SOURCE_STEP),
            "shapr": repo_path(SOURCE_SHAPR),
            "shapr_sha256": sha256_file(SOURCE_SHAPR),
            "authority": (
                "STEP B-rep is authoritative; OpenHI.shapr confirms the Lens C "
                "holder context but stores these bodies as imported geometry"
            ),
        },
        "scope": {
            "modified": [
                "positive-X Lens C female receiver pivot 30.2 -> 29.8 mm",
                "positive-X Lens C female groove 31.0 -> 30.6 mm",
                "adjacent two 45-degree transitions moved to meet the new pivot",
            ],
            "preserved": [
                "complete negative-X Thread BS male tooth source solid",
                "negative-X 29.8 mm male root in the source main body",
                "25.5 mm lens seat",
                "0.8 mm right-hand pitch and 0.4 mm radial tooth height",
                "7.75 mm threaded interval",
                "outer body and external envelope",
                "24.0 mm center bore and every feature through x=325.0 mm",
            ],
        },
        "thread": {
            "source_female_pivot_mm": SOURCE_PIVOT,
            "source_female_groove_mm": SOURCE_GROOVE,
            "target_female_pivot_mm": TARGET_PIVOT,
            "target_female_groove_mm": TARGET_GROOVE,
            "pitch_mm": PITCH,
            "radial_tooth_height_mm": TOOTH_RADIAL_HEIGHT,
            "tooth_base_mm": TOOTH_BASE,
            "hand": "source-style right-hand along positive X",
            "construction_runout_each_end_mm": round(RUNOUT + PITCH, 6),
            "runout_policy": "construct beyond both ends, then clip to true interval",
            "phase_shift_mm": FEMALE_PHASE_SHIFT,
        },
        "receiver": {
            "axis": "positive X",
            "center_yz_mm": [AXIS_Y, AXIS_Z],
            "lens_seat_diameter_mm": LENS_SEAT_DIAMETER,
            "lens_transition_x_range_mm": [LENS_SEAT_END_X, THREAD_X0],
            "thread_x_range_mm": [THREAD_X0, THREAD_X1],
            "mouth_x_range_mm": [THREAD_X1, UPPER_MOUTH_X1],
            "transition_angle_deg": 45.0,
        },
        "fit_warning": (
            "The requested 29.8/30.6 mm female profile has zero nominal diameter "
            "clearance against this holder's unchanged 29.8/30.6 mm left male. "
            "Verify the physical printer/material fit before a full assembly print."
        ),
        "outputs": outputs,
        "validation": validation,
        "nutstore": {
            "run_folder": str(NUTSTORE_RUN),
            "direct_step": str(NUTSTORE_ROOT / paths["root_step"].name),
            "direct_3mf": str(NUTSTORE_ROOT / paths["root_3mf"].name),
        },
    }


def package_and_sync() -> dict[str, str]:
    manifest_path = ARTIFACT_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("build artifacts before packaging")
    required_renders = [
        ARTIFACT_DIR / f"{STEM}_render.png",
        ARTIFACT_DIR / f"{STEM}_thread_detail.png",
        ARTIFACT_DIR / f"{STEM}_thread_cutaway.png",
    ]
    missing = [str(path) for path in required_renders if not path.exists()]
    if missing:
        raise FileNotFoundError(f"render artifacts before packaging: {missing}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package"] = {
        "run_folder": repo_path(RUN_DIR),
        "nutstore_run_folder": str(NUTSTORE_RUN),
        "render_files_verified": [repo_path(path) for path in required_renders],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    (RUN_DIR / "artifacts").mkdir(parents=True, exist_ok=True)
    for path in ARTIFACT_DIR.iterdir():
        if path.is_file():
            shutil.copy2(path, RUN_DIR / "artifacts" / path.name)
    for path in (
        DESIGN_DIR / "README.md",
        Path(__file__),
        DESIGN_DIR / f"render_{STEM}.py",
    ):
        shutil.copy2(path, RUN_DIR / path.name)
    for path in DESIGN_DIR.glob("USE_THIS_*"):
        if path.is_file():
            shutil.copy2(path, RUN_DIR / path.name)

    NUTSTORE_RUN.parent.mkdir(parents=True, exist_ok=True)
    if NUTSTORE_RUN.exists():
        shutil.rmtree(NUTSTORE_RUN)
    shutil.copytree(RUN_DIR, NUTSTORE_RUN)
    root_step = DESIGN_DIR / f"USE_THIS_{STEM}.step"
    root_3mf = DESIGN_DIR / f"USE_THIS_{STEM}.3mf"
    shutil.copy2(root_step, NUTSTORE_ROOT / root_step.name)
    shutil.copy2(root_3mf, NUTSTORE_ROOT / root_3mf.name)
    return {
        "run_folder": repo_path(RUN_DIR),
        "nutstore_run_folder": str(NUTSTORE_RUN),
        "nutstore_direct_step": str(NUTSTORE_ROOT / root_step.name),
        "nutstore_direct_3mf": str(NUTSTORE_ROOT / root_3mf.name),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package-only",
        action="store_true",
        help="Package existing checked outputs and renders into the run and Nutstore.",
    )
    args = parser.parse_args()
    if args.package_only:
        print(json.dumps(package_and_sync(), indent=2))
        return

    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"missing source STEP: {SOURCE_STEP}")
    if not SOURCE_SHAPR.exists():
        raise FileNotFoundError(f"missing Shapr reference: {SOURCE_SHAPR}")
    paths, validation = export_geometry()
    manifest = manifest_payload(paths, validation)
    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "root_step": repo_path(paths["root_step"]),
                "root_3mf": repo_path(paths["root_3mf"]),
                "manifest": repo_path(manifest_path),
                "validation": validation["checks"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
