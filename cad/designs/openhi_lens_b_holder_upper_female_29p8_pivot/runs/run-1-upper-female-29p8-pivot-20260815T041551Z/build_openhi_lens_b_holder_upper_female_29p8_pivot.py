#!/usr/bin/env python3
"""Rebuild only the upper Lens B female receiver at a 29.8 mm pivot.

The authoritative body is imported from ``Lens B holder.step``.  The script
fills the old positive-Z receiver and re-cuts its lens transition, pilot,
source-style helical groove, and mouth.  Every feature outside that bounded
receiver envelope remains inherited from the source B-rep.
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
STEM = "openhi_lens_b_holder_upper_female_29p8_pivot"
RUN_NAME = "run-1-upper-female-29p8-pivot-20260815T041551Z"
RUN_DIR = DESIGN_DIR / "runs" / RUN_NAME
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/Lens B holder.step"
SOURCE_SHAPR = ROOT / "cad/extracted/OpenHI.shapr"
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
NUTSTORE_RUN = NUTSTORE_ROOT / DESIGN_DIR.name / RUN_NAME

TOOLS_DIR = ROOT / "cad/tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from simple_3mf import export_stl_as_3mf  # noqa: E402


AXIS_X = 254.633
AXIS_Y = 210.0
PITCH = 0.8
TOOTH_RADIAL_HEIGHT = 0.4
TOOTH_BASE = 0.8
RUNOUT = 0.4
THREAD_OVERLAP = 0.10
FEMALE_PHASE_SHIFT = -0.20

SOURCE_PIVOT = 30.2
SOURCE_GROOVE = 31.0
TARGET_PIVOT = 29.8
TARGET_GROOVE = TARGET_PIVOT + 2.0 * TOOTH_RADIAL_HEIGHT
LENS_SEAT_DIAMETER = 25.5
OUTER_MOUTH_DIAMETER = 40.734

LENS_SEAT_END_Z = 650.0
LOWER_TRANSITION_LENGTH = (TARGET_PIVOT - LENS_SEAT_DIAMETER) / 2.0
THREAD_Z0 = LENS_SEAT_END_Z + LOWER_TRANSITION_LENGTH
THREAD_LENGTH = 7.75
THREAD_Z1 = THREAD_Z0 + THREAD_LENGTH
UPPER_MOUTH_LENGTH = (OUTER_MOUTH_DIAMETER - TARGET_PIVOT) / 2.0
UPPER_MOUTH_Z1 = THREAD_Z1 + UPPER_MOUTH_LENGTH


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


def z_cylinder(
    diameter: float,
    z0: float,
    length: float,
    center_x: float = AXIS_X,
    center_y: float = AXIS_Y,
) -> cq.Workplane:
    return workplane(
        cq.Solid.makeCylinder(
            diameter / 2.0,
            length,
            cq.Vector(center_x, center_y, z0),
            cq.Vector(0.0, 0.0, 1.0),
        )
    )


def z_cone(
    diameter0: float,
    diameter1: float,
    z0: float,
    length: float,
    center_x: float = AXIS_X,
    center_y: float = AXIS_Y,
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


def z_clip(z0: float, length: float, span: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(span, span, length, centered=(True, True, False))
        .translate((AXIS_X, AXIS_Y, z0))
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
    tooth = (
        x_thread_tooth(
            TARGET_PIVOT,
            TARGET_GROOVE,
            THREAD_LENGTH,
            x0=THREAD_Z0,
            phase_shift=FEMALE_PHASE_SHIFT,
        )
        .rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)
        .translate((AXIS_X, AXIS_Y, 0.0))
    )
    return tooth.intersect(z_clip(THREAD_Z0, THREAD_LENGTH, TARGET_GROOVE + 4.0))


def make_cutters() -> dict[str, cq.Workplane]:
    return {
        "lower_transition": z_cone(
            LENS_SEAT_DIAMETER,
            TARGET_PIVOT,
            LENS_SEAT_END_Z,
            LOWER_TRANSITION_LENGTH,
        ),
        "pilot": z_cylinder(TARGET_PIVOT, THREAD_Z0, THREAD_LENGTH),
        "thread": female_thread_cutter(),
        "upper_mouth": z_cone(
            TARGET_PIVOT,
            OUTER_MOUTH_DIAMETER,
            THREAD_Z1,
            UPPER_MOUTH_LENGTH,
        ),
    }


def build() -> tuple[cq.Workplane, cq.Workplane, dict[str, cq.Workplane]]:
    source = cq.importers.importStep(str(SOURCE_STEP)).val()
    if len(source.Solids()) != 1:
        raise RuntimeError("Lens B holder source must contain exactly one solid")
    cutters = make_cutters()
    fill = z_cylinder(31.4, 650.0, 10.1)
    filled = workplane(source).union(fill)
    smooth = (
        filled.cut(cutters["lower_transition"])
        .cut(cutters["pilot"])
        .cut(cutters["upper_mouth"])
        .clean()
    )
    threaded = smooth.cut(cutters["thread"]).clean()
    return largest_solid(threaded), largest_solid(smooth), {"fill": fill, **cutters}


def radial_probe(shape: cq.Shape) -> dict[str, Any]:
    cylinders: list[float] = []
    grooves: list[float] = []
    groove_bounds: list[list[float]] = []
    cones: list[dict[str, Any]] = []
    for face in shape.Faces():
        box = face.BoundingBox()
        if box.zmax < 649.5 or box.zmin > UPPER_MOUTH_Z1 + 0.01:
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
                    "z_bounds_mm": [round(box.zmin, 6), round(box.zmax, 6)],
                }
            )
        if surface_type != GeomAbs_BSplineSurface:
            continue
        samples: list[float] = []
        vertices, _ = face.tessellate(0.015)
        for vertex in vertices:
            if THREAD_Z0 - 0.02 <= vertex.z <= THREAD_Z1 + 0.02:
                diameter = 2.0 * math.hypot(
                    vertex.x - AXIS_X,
                    vertex.y - AXIS_Y,
                )
                if TARGET_PIVOT - 0.2 <= diameter <= TARGET_GROOVE + 0.2:
                    samples.append(diameter)
        if samples:
            grooves.extend(samples)
            groove_bounds.append([round(box.zmin, 6), round(box.zmax, 6)])
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
        "matched_bspline_z_bounds_mm": groove_bounds,
        "cone_surfaces": cones,
    }


def validate_change_scope(source: cq.Shape, output: cq.Shape) -> dict[str, float]:
    envelope = z_cylinder(41.0, 649.4, UPPER_MOUTH_Z1 - 649.4 + 0.1)
    removed = workplane(source).cut(workplane(output))
    added = workplane(output).cut(workplane(source))
    return {
        "removed_total_mm3": round(removed.val().Volume(), 6),
        "added_total_mm3": round(added.val().Volume(), 6),
        "removed_outside_receiver_envelope_mm3": round(
            removed.cut(envelope).val().Volume(), 9
        ),
        "added_outside_receiver_envelope_mm3": round(
            added.cut(envelope).val().Volume(), 9
        ),
    }


def validate_mesh(path: Path) -> dict[str, Any]:
    mesh = trimesh.load(path, force="mesh", process=True)
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
    component_count = len({find(index) for index in referenced})
    return {
        "path": repo_path(path),
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "component_count": component_count,
        "body_count": component_count,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
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
    if mesh.is_watertight:
        return {
            "applied": False,
            "reason": "mesh was already watertight",
            "boundary_edges_before": 0,
            "faces_added": 0,
        }
    counts = np.bincount(mesh.edges_unique_inverse)
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
    edge_counts: Counter[tuple[int, int]] = Counter()
    edge_orientations: Counter[tuple[int, int]] = Counter()
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

    referenced: set[int] = set()
    indices_valid = True
    for triangle in triangles:
        if any(index < 0 or index >= len(vertices) for index in triangle):
            indices_valid = False
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
            edge_orientations[edge] += 1 if start < end else -1
    minimum = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maximum = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    return {
        "path": repo_path(path),
        "unit": root.attrib.get("unit"),
        "vertices": len(vertices),
        "faces": len(triangles),
        "component_count": len({find(index) for index in referenced}),
        "indices_valid": indices_valid,
        "watertight": bool(edge_counts)
        and all(count == 2 for count in edge_counts.values()),
        "winding_consistent": bool(edge_orientations)
        and all(value == 0 for value in edge_orientations.values()),
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
    scope = validate_change_scope(source, output)
    cone_45_bounds = [
        item["z_bounds_mm"]
        for item in probe["cone_surfaces"]
        if near(item["semi_angle_deg"], 45.0, 0.01)
    ]
    upper_intervals = sorted(
        (
            max(bounds[0], THREAD_Z1),
            min(bounds[1], UPPER_MOUTH_Z1),
        )
        for bounds in cone_45_bounds
        if bounds[1] >= THREAD_Z1 - 0.01
        and bounds[0] <= UPPER_MOUTH_Z1 + 0.01
    )
    upper_cursor = THREAD_Z1
    for low, high in upper_intervals:
        if low <= upper_cursor + 0.01:
            upper_cursor = max(upper_cursor, high)
    thread_bounds = probe["matched_bspline_z_bounds_mm"]
    checks = {
        "single_solid": output_summary["solid_count"] == 1,
        "occt_valid": output_summary["occt_valid"],
        "external_bbox_preserved": source_summary["bbox"] == output_summary["bbox"],
        "changes_confined_to_upper_receiver": (
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
        "thread_is_clipped_to_true_interval": bool(thread_bounds)
        and all(
            low >= THREAD_Z0 - 0.02 and high <= THREAD_Z1 + 0.02
            for low, high in thread_bounds
        ),
        "both_45_degree_transitions_present": any(
            near(bounds[0], LENS_SEAT_END_Z, 0.01)
            and near(bounds[1], THREAD_Z0, 0.01)
            for bounds in cone_45_bounds
        )
        and upper_cursor >= UPPER_MOUTH_Z1 - 0.01,
        "lens_seat_25p5_preserved": any(
            near(value, LENS_SEAT_DIAMETER)
            for value in probe["cylinder_diameters_mm"]
        ),
    }
    return {
        "source": source_summary,
        "output": output_summary,
        "change_scope": scope,
        "receiver_probe": probe,
        "checks": checks,
    }


def export_geometry() -> tuple[dict[str, Path], dict[str, Any]]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    threaded, smooth, cutters = build()
    paths = {
        "assembly_step": ARTIFACT_DIR / f"{STEM}.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "assembly_3mf": ARTIFACT_DIR / f"{STEM}.3mf",
        "smooth_editable_step": ARTIFACT_DIR / f"{STEM}_smooth_editable.step",
        "receiver_cutters_step": ARTIFACT_DIR / f"{STEM}_receiver_cutters.step",
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
            cutters[key].val()
            for key in ("lower_transition", "pilot", "thread", "upper_mouth")
        ]
    )
    exporters.export(workplane(cutter_compound), str(paths["receiver_cutters_step"]))
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
            "smooth_editable_is_valid_single_solid": (
                validation["smooth_editable"]["occt_valid"]
                and validation["smooth_editable"]["solid_count"] == 1
            ),
            "mesh_is_watertight_single_component": (
                validation["mesh"]["watertight"]
                and validation["mesh"]["winding_consistent"]
                and validation["mesh"]["component_count"] == 1
                and validation["mesh"]["body_count"] == 1
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
            "three_mf_is_watertight_single_component": (
                validation["three_mf"]["watertight"]
                and validation["three_mf"]["winding_consistent"]
                and validation["three_mf"]["indices_valid"]
                and validation["three_mf"]["component_count"] == 1
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
                "STEP B-rep is authoritative; OpenHI.shapr confirms the Lens B "
                "holder context but stores this body as imported geometry"
            ),
        },
        "scope": {
            "modified": [
                "positive-Z Lens B female receiver pivot 30.2 -> 29.8 mm",
                "positive-Z Lens B female groove 31.0 -> 30.6 mm",
                "adjacent two 45-degree transitions moved to meet the new pivot",
            ],
            "preserved": [
                "25.5 mm lens seat",
                "0.8 mm right-hand pitch and 0.4 mm radial tooth height",
                "7.75 mm threaded interval",
                "outer body and external envelope",
                "central bore, side pin holes, oblique end sink, and all lower geometry",
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
            "hand": "right-hand",
            "construction_runout_each_end_mm": round(RUNOUT + PITCH, 6),
            "runout_policy": "construct beyond both ends, then clip to true interval",
            "phase_shift_mm": FEMALE_PHASE_SHIFT,
        },
        "receiver": {
            "axis": "positive Z",
            "center_mm": [AXIS_X, AXIS_Y],
            "lens_seat_diameter_mm": LENS_SEAT_DIAMETER,
            "lower_transition_z_range_mm": [LENS_SEAT_END_Z, THREAD_Z0],
            "thread_z_range_mm": [THREAD_Z0, THREAD_Z1],
            "upper_mouth_z_range_mm": [THREAD_Z1, UPPER_MOUTH_Z1],
            "transition_angle_deg": 45.0,
        },
        "fit_warning": (
            "A 29.8/30.6 mm mating male has zero nominal radial clearance against "
            "this 29.8/30.6 mm female profile. Verify the printer/material fit before "
            "committing to the complete optical assembly."
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
