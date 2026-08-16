#!/usr/bin/env python3
"""Regenerate the original OpenHI A, B, and C bodies without fit edits.

The Shapr3D archive stores these parts as imported bodies, so the exported STEP
B-reps are the exact geometry authority.  The default path round-trips every
complete compound without changing any face.  Named pivot parameters and the
localized thread builders are kept here so a later variant can adjust only one
interface while retaining all unrelated source solids.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import (
    GeomAbs_BSplineSurface,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Plane,
    GeomAbs_Torus,
)
import trimesh


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
RUNS_DIR = DESIGN_DIR / "runs"
SOURCE_DIR = ROOT / "cad/extracted/OpenHI_STEP"
SOURCE_SHAPR = ROOT / "cad/extracted/OpenHI.shapr"
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
NUTSTORE_DESIGN_DIR = NUTSTORE_ROOT / DESIGN_DIR.name
DEFAULT_RUN_NAME = (
    "run-1-exact-current-geometry-parametric-baseline-20260816T131516Z"
)

PITCH_MM = 0.8
TOOTH_RADIAL_HEIGHT_MM = 0.4
TOOTH_BASE_MM = 0.8
RUNOUT_MM = 0.4

# These are measured source values.  Keep them unchanged in this baseline.
ORIGINAL_PIVOTS_MM = {
    "a_top": 29.8,
    "b_lens": 29.6,
    "b_camera": 24.4,
    "c_lens": 29.6,
    "c_camera": 24.4,
}

SOURCE_PATHS = {
    "A": SOURCE_DIR / "A.step",
    "B": SOURCE_DIR / "B.step",
    "C": SOURCE_DIR / "C.step",
}

OUTPUT_STEMS = {
    "A": "OpenHI_A_exact_current_geometry",
    "B": "OpenHI_B_exact_current_geometry",
    "C": "OpenHI_C_exact_current_geometry",
}

EXPECTED_SOLIDS = {"A": 3, "B": 4, "C": 4}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def format_mesh_float(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".") or "0"


def export_component_meshes_as_3mf(
    component_stls: list[Path],
    target: Path,
    *,
    title: str,
) -> None:
    """Write one 3MF object per original B-rep solid."""
    objects: list[str] = []
    build_items: list[str] = []
    for object_id, component_path in enumerate(component_stls, start=1):
        mesh = trimesh.load_mesh(component_path, force="mesh", process=True)
        if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
            raise ValueError(f"empty component mesh: {component_path}")
        vertices = "\n".join(
            f'          <vertex x="{format_mesh_float(x)}" y="{format_mesh_float(y)}" z="{format_mesh_float(z)}"/>'
            for x, y, z in mesh.vertices
        )
        triangles = "\n".join(
            f'          <triangle v1="{int(a)}" v2="{int(b)}" v3="{int(c)}"/>'
            for a, b, c in mesh.faces
        )
        objects.append(
            f'''    <object id="{object_id}" type="model" name="{escape(component_path.stem)}">
      <mesh>
        <vertices>
{vertices}
        </vertices>
        <triangles>
{triangles}
        </triangles>
      </mesh>
    </object>'''
        )
        build_items.append(f'    <item objectid="{object_id}"/>')

    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""
    model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Title">{escape(title)}</metadata>
  <resources>
{chr(10).join(objects)}
  </resources>
  <build>
{chr(10).join(build_items)}
  </build>
</model>
'''
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("3D/3dmodel.model", model)


def export_single_mesh_as_3mf(
    mesh: trimesh.Trimesh,
    target: Path,
    *,
    title: str,
) -> None:
    """Write one build-plate-ready 3MF object, even for multiple mesh shells."""
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError(f"empty print mesh: {target}")
    vertices = "\n".join(
        f'          <vertex x="{format_mesh_float(x)}" y="{format_mesh_float(y)}" z="{format_mesh_float(z)}"/>'
        for x, y, z in mesh.vertices
    )
    triangles = "\n".join(
        f'          <triangle v1="{int(a)}" v2="{int(b)}" v3="{int(c)}"/>'
        for a, b, c in mesh.faces
    )
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""
    model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Title">{escape(title)}</metadata>
  <resources>
    <object id="1" type="model" name="{escape(title)}">
      <mesh>
        <vertices>
{vertices}
        </vertices>
        <triangles>
{triangles}
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1"/>
  </build>
</model>
'''
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("3D/3dmodel.model", model)


def close(a: float, b: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(a, b, abs_tol=tolerance, rel_tol=0.0)


def workplane(shape: cq.Shape) -> cq.Workplane:
    return cq.Workplane().add(shape)


def compound(parts: Iterable[cq.Shape | cq.Workplane]) -> cq.Workplane:
    shapes: list[cq.Shape] = []
    for part in parts:
        shape = part.val() if isinstance(part, cq.Workplane) else part
        shapes.extend(shape.Solids() or [shape])
    return workplane(cq.Compound.makeCompound(shapes))


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
) -> cq.Workplane:
    """Build the measured right-hand 0.8 mm triangular thread tooth."""
    margin = RUNOUT_MM + PITCH_MM
    sweep_x0 = x0 - margin
    sweep_length = length + 2.0 * margin
    root_radius = root_diameter / 2.0
    path = cq.Wire.makeHelix(
        PITCH_MM,
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
                (TOOTH_BASE_MM / 2.0, (crest_diameter - root_diameter) / 2.0),
                (TOOTH_BASE_MM, 0.0),
            ]
        )
        .close()
    )
    swept = profile.sweep(path, isFrenet=True, combine=False)
    return swept.intersect(x_clip(x0, length, crest_diameter + 4.0))


def z_thread_at(
    root_diameter: float,
    z0: float,
    length: float,
    center_x: float,
    center_y: float,
) -> cq.Workplane:
    crest = root_diameter + 2.0 * TOOTH_RADIAL_HEIGHT_MM
    placed = (
        x_thread_tooth(root_diameter, crest, length, x0=z0)
        .rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)
        .translate((center_x, center_y, 0.0))
    )
    return placed.intersect(z_clip(z0, length, crest + 4.0, center_x, center_y))


def x_thread_at(
    root_diameter: float,
    x0: float,
    length: float,
    center_y: float,
    center_z: float,
) -> cq.Workplane:
    crest = root_diameter + 2.0 * TOOTH_RADIAL_HEIGHT_MM
    return x_thread_tooth(root_diameter, crest, length, x0=x0).translate(
        (0.0, center_y, center_z)
    )


def adjust_z_root(
    body: cq.Shape,
    old_diameter: float,
    new_diameter: float,
    z0: float,
    length: float,
    center_x: float,
    center_y: float,
) -> cq.Workplane:
    if close(old_diameter, new_diameter):
        return workplane(body)
    if new_diameter > old_diameter:
        outer = z_cylinder(new_diameter, z0, length, center_x, center_y)
        inner = z_cylinder(
            old_diameter - 0.10,
            z0 - 0.05,
            length + 0.10,
            center_x,
            center_y,
        )
        return workplane(body).union(outer.cut(inner)).clean()
    outer = z_cylinder(
        old_diameter + 0.20,
        z0 - 0.05,
        length + 0.10,
        center_x,
        center_y,
    )
    inner = z_cylinder(new_diameter, z0 - 0.10, length + 0.20, center_x, center_y)
    return workplane(body).cut(outer.cut(inner)).clean()


def adjust_x_root(
    body: cq.Shape,
    old_diameter: float,
    new_diameter: float,
    x0: float,
    length: float,
    center_y: float,
    center_z: float,
) -> cq.Workplane:
    if close(old_diameter, new_diameter):
        return workplane(body)
    if new_diameter > old_diameter:
        outer = x_cylinder(new_diameter, x0, length, center_y, center_z)
        inner = x_cylinder(
            old_diameter - 0.10,
            x0 - 0.05,
            length + 0.10,
            center_y,
            center_z,
        )
        return workplane(body).union(outer.cut(inner)).clean()
    outer = x_cylinder(
        old_diameter + 0.20,
        x0 - 0.05,
        length + 0.10,
        center_y,
        center_z,
    )
    inner = x_cylinder(new_diameter, x0 - 0.10, length + 0.20, center_y, center_z)
    return workplane(body).cut(outer.cut(inner)).clean()


def current_pivots(args: argparse.Namespace) -> dict[str, float]:
    return {
        "a_top": args.a_top_pivot,
        "b_lens": args.b_lens_pivot,
        "b_camera": args.b_camera_pivot,
        "c_lens": args.c_lens_pivot,
        "c_camera": args.c_camera_pivot,
    }


def is_original(key: str, value: float) -> bool:
    return close(value, ORIGINAL_PIVOTS_MM[key])


def build_a(pivots: dict[str, float]) -> cq.Workplane:
    source = cq.importers.importStep(str(SOURCE_PATHS["A"])).val()
    solids = source.Solids()
    if len(solids) != EXPECTED_SOLIDS["A"]:
        raise ValueError(f"A source solid count changed: {len(solids)}")
    if is_original("a_top", pivots["a_top"]):
        return compound(solids)

    top_tooth = z_thread_at(pivots["a_top"], 519.3, 8.35, 255.0, 210.0)
    main_body = adjust_z_root(
        solids[1],
        ORIGINAL_PIVOTS_MM["a_top"],
        pivots["a_top"],
        520.1,
        7.55,
        255.0,
        210.0,
    )
    return compound([top_tooth, main_body, solids[2]])


def build_b(pivots: dict[str, float]) -> cq.Workplane:
    source = cq.importers.importStep(str(SOURCE_PATHS["B"])).val()
    solids = source.Solids()
    if len(solids) != EXPECTED_SOLIDS["B"]:
        raise ValueError(f"B source solid count changed: {len(solids)}")
    if is_original("b_lens", pivots["b_lens"]) and is_original(
        "b_camera", pivots["b_camera"]
    ):
        return compound(solids)

    lens_tooth: cq.Shape | cq.Workplane = solids[0]
    lens_body: cq.Shape | cq.Workplane = solids[2]
    camera_tooth: cq.Shape | cq.Workplane = solids[1]
    camera_body: cq.Shape | cq.Workplane = solids[3]
    if not is_original("b_lens", pivots["b_lens"]):
        lens_tooth = z_thread_at(pivots["b_lens"], 671.75, 9.05, 255.0, 210.0)
        lens_body = adjust_z_root(
            solids[2], 29.6, pivots["b_lens"], 672.05, 7.95, 255.0, 210.0
        )
    if not is_original("b_camera", pivots["b_camera"]):
        camera_tooth = z_thread_at(
            pivots["b_camera"], 719.3, 5.1, 255.0, 210.0
        )
        camera_body = adjust_z_root(
            solids[3], 24.4, pivots["b_camera"], 719.3, 4.7, 255.0, 210.0
        )
    return compound([lens_tooth, camera_tooth, lens_body, camera_body])


def build_c(pivots: dict[str, float]) -> cq.Workplane:
    source = cq.importers.importStep(str(SOURCE_PATHS["C"])).val()
    solids = source.Solids()
    if len(solids) != EXPECTED_SOLIDS["C"]:
        raise ValueError(f"C source solid count changed: {len(solids)}")
    if is_original("c_lens", pivots["c_lens"]) and is_original(
        "c_camera", pivots["c_camera"]
    ):
        return compound(solids)

    camera_tooth: cq.Shape | cq.Workplane = solids[0]
    lens_tooth: cq.Shape | cq.Workplane = solids[1]
    lens_body: cq.Shape | cq.Workplane = solids[2]
    camera_body: cq.Shape | cq.Workplane = solids[3]
    if not is_original("c_lens", pivots["c_lens"]):
        lens_tooth = x_thread_at(pivots["c_lens"], 377.05, 8.75, 210.0, 600.0)
        lens_body = adjust_x_root(
            solids[2], 29.6, pivots["c_lens"], 377.05, 7.95, 210.0, 600.0
        )
    if not is_original("c_camera", pivots["c_camera"]):
        camera_tooth = x_thread_at(
            pivots["c_camera"], 424.3, 4.7, 210.0, 600.0
        )
        camera_body = adjust_x_root(
            solids[3], 24.4, pivots["c_camera"], 424.3, 4.7, 210.0, 600.0
        )
    return compound([camera_tooth, lens_tooth, lens_body, camera_body])


def build_parts(pivots: dict[str, float]) -> dict[str, cq.Workplane]:
    return {"A": build_a(pivots), "B": build_b(pivots), "C": build_c(pivots)}


def bbox_dict(shape: cq.Shape) -> dict[str, list[float]]:
    bb = shape.BoundingBox()
    return {
        "min": [round(bb.xmin, 9), round(bb.ymin, 9), round(bb.zmin, 9)],
        "max": [round(bb.xmax, 9), round(bb.ymax, 9), round(bb.zmax, 9)],
        "size": [round(bb.xlen, 9), round(bb.ylen, 9), round(bb.zlen, 9)],
    }


def surface_counts(shape: cq.Shape) -> dict[str, int]:
    names = {
        GeomAbs_Plane: "plane",
        GeomAbs_Cylinder: "cylinder",
        GeomAbs_Cone: "cone",
        GeomAbs_BSplineSurface: "bspline",
        GeomAbs_Torus: "torus",
    }
    counts: Counter[str] = Counter()
    for face in shape.Faces():
        kind = BRepAdaptor_Surface(face.wrapped, True).GetType()
        counts[names.get(kind, str(kind))] += 1
    return dict(sorted(counts.items()))


def sorted_solid_summaries(shape: cq.Shape) -> list[dict[str, Any]]:
    rows = []
    for solid in shape.Solids():
        rows.append(
            {
                "bbox": bbox_dict(solid),
                "faces": len(solid.Faces()),
                "edges": len(solid.Edges()),
                "volume_mm3": round(solid.Volume(), 9),
                "area_mm2": round(solid.Area(), 9),
                "valid": bool(BRepCheck_Analyzer(solid.wrapped).IsValid()),
                "surface_counts": surface_counts(solid),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["bbox"]["min"],
            row["bbox"]["max"],
            row["volume_mm3"],
        ),
    )


def shape_summary(shape: cq.Shape) -> dict[str, Any]:
    return {
        "shape_type": shape.ShapeType(),
        "bbox": bbox_dict(shape),
        "solid_count": len(shape.Solids()),
        "shell_count": len(shape.Shells()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "volume_mm3": round(shape.Volume(), 9),
        "area_mm2": round(shape.Area(), 9),
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "surface_counts": surface_counts(shape),
        "solids": sorted_solid_summaries(shape),
    }


def list_abs_delta(a: list[float], b: list[float]) -> list[float]:
    return [round(abs(x - y), 9) for x, y in zip(a, b)]


def compare_geometry(source: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    bbox_min_delta = list_abs_delta(source["bbox"]["min"], output["bbox"]["min"])
    bbox_max_delta = list_abs_delta(source["bbox"]["max"], output["bbox"]["max"])
    bbox_size_delta = list_abs_delta(source["bbox"]["size"], output["bbox"]["size"])
    volume_delta = round(abs(source["volume_mm3"] - output["volume_mm3"]), 9)
    area_delta = round(abs(source["area_mm2"] - output["area_mm2"]), 9)
    same_topology = all(
        source[key] == output[key]
        for key in ("solid_count", "shell_count", "face_count", "edge_count")
    ) and source["surface_counts"] == output["surface_counts"]
    return {
        "bbox_min_abs_delta_mm": bbox_min_delta,
        "bbox_max_abs_delta_mm": bbox_max_delta,
        "bbox_size_abs_delta_mm": bbox_size_delta,
        "volume_abs_delta_mm3": volume_delta,
        "area_abs_delta_mm2": area_delta,
        "topology_counts_same": same_topology,
        "source_valid": source["valid"],
        "output_valid": output["valid"],
        "all_geometry_checks_pass": (
            max(bbox_min_delta + bbox_max_delta + bbox_size_delta) <= 1e-5
            and volume_delta <= 0.02
            and area_delta <= 0.005
            and same_topology
            and source["valid"]
            and output["valid"]
        ),
    }


def compare_rigid_geometry(
    source: dict[str, Any], output: dict[str, Any]
) -> dict[str, Any]:
    sorted_bbox_delta = [
        round(abs(float(actual) - float(expected)), 9)
        for actual, expected in zip(
            sorted(output["bbox"]["size"]), sorted(source["bbox"]["size"])
        )
    ]
    volume_delta = round(abs(source["volume_mm3"] - output["volume_mm3"]), 9)
    area_delta = round(abs(source["area_mm2"] - output["area_mm2"]), 9)
    same_topology = all(
        source[key] == output[key]
        for key in ("solid_count", "shell_count", "face_count", "edge_count")
    ) and source["surface_counts"] == output["surface_counts"]
    return {
        "sorted_bbox_size_abs_delta_mm": sorted_bbox_delta,
        "volume_abs_delta_mm3": volume_delta,
        "area_abs_delta_mm2": area_delta,
        "topology_counts_same": same_topology,
        "source_valid": source["valid"],
        "output_valid": output["valid"],
        "all_rigid_geometry_checks_pass": (
            max(sorted_bbox_delta) <= 1e-5
            and volume_delta <= 0.02
            and area_delta <= 0.005
            and same_topology
            and source["valid"]
            and output["valid"]
        ),
    }


def validate_stl(
    path: Path,
    component_paths: list[Path],
    expected_bbox: list[float],
) -> dict[str, Any]:
    loaded = trimesh.load_mesh(path, force="mesh", process=False)
    if not isinstance(loaded, trimesh.Trimesh) or not len(loaded.faces):
        raise TypeError(f"STL did not load as a mesh: {path}")
    components = [
        trimesh.load_mesh(component, force="mesh", process=True)
        for component in component_paths
    ]
    if not all(isinstance(component, trimesh.Trimesh) for component in components):
        raise TypeError(f"component STL did not load as a mesh: {path}")
    bbox_delta = [
        round(abs(float(actual) - expected), 6)
        for actual, expected in zip(loaded.extents, expected_bbox)
    ]
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "vertices": int(len(loaded.vertices)),
        "faces": int(len(loaded.faces)),
        "component_count": len(components),
        "component_face_counts": [int(len(component.faces)) for component in components],
        "assembly_triangle_count_matches_components": len(loaded.faces)
        == sum(len(component.faces) for component in components),
        "all_components_watertight": bool(components)
        and all(component.is_watertight for component in components),
        "bbox_mm": [round(float(value), 6) for value in loaded.extents],
        "bbox_abs_delta_mm": bbox_delta,
        "bbox_matches": max(bbox_delta) <= TOOTH_RADIAL_HEIGHT_MM + 0.02,
        "bbox_note": (
            "A tessellated mesh may omit a zero-area half-pitch runout extremum; "
            "the authoritative STEP retains the complete analytic/B-spline B-rep."
        ),
    }


def validate_print_stl(
    path: Path,
    component_paths: list[Path],
    expected_bbox: list[float],
) -> dict[str, Any]:
    loaded = trimesh.load_mesh(path, force="mesh", process=False)
    if not isinstance(loaded, trimesh.Trimesh) or not len(loaded.faces):
        raise TypeError(f"print STL did not load as a mesh: {path}")
    components = [
        trimesh.load_mesh(component, force="mesh", process=True)
        for component in component_paths
    ]
    if not all(isinstance(component, trimesh.Trimesh) for component in components):
        raise TypeError(f"print component STL did not load as a mesh: {path}")
    bounds = loaded.bounds
    triangle_z = loaded.triangles[:, :, 2]
    first_layer_count = int(
        ((triangle_z.min(axis=1) <= 0.2) & (triangle_z.max(axis=1) >= 0.0)).sum()
    )
    sorted_bbox_delta = [
        round(abs(float(actual) - float(expected)), 6)
        for actual, expected in zip(sorted(loaded.extents), sorted(expected_bbox))
    ]
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "vertices": int(len(loaded.vertices)),
        "faces": int(len(loaded.faces)),
        "component_count": len(components),
        "all_components_watertight": bool(components)
        and all(component.is_watertight for component in components),
        "bbox_mm": [round(float(value), 6) for value in loaded.extents],
        "sorted_bbox_abs_delta_mm": sorted_bbox_delta,
        "bbox_matches_rigid_transform": max(sorted_bbox_delta) <= 0.42,
        "min_z_mm": round(float(bounds[0][2]), 6),
        "max_z_mm": round(float(bounds[1][2]), 6),
        "on_build_plate": abs(float(bounds[0][2])) <= 1e-5,
        "first_layer_triangle_count": first_layer_count,
        "first_layer_nonempty": first_layer_count > 0,
    }


def validate_3mf(
    path: Path,
    expected_triangle_count: int,
    expected_object_count: int,
) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.namelist())
        bad_member = archive.testzip()
        model = archive.read("3D/3dmodel.model")
    root = ElementTree.fromstring(model)
    namespace = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    vertices = root.findall(".//m:vertex", namespace)
    triangles = root.findall(".//m:triangle", namespace)
    objects = root.findall(".//m:object", namespace)
    build_items = root.findall(".//m:build/m:item", namespace)
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "members": members,
        "zip_valid": bad_member is None,
        "model_present": "3D/3dmodel.model" in members,
        "vertex_count": len(vertices),
        "triangle_count": len(triangles),
        "triangle_count_matches_stl": len(triangles) == expected_triangle_count,
        "object_count": len(objects),
        "build_item_count": len(build_items),
        "object_count_matches_solids": len(objects) == expected_object_count
        and len(build_items) == expected_object_count,
    }


def fused_print_shape(shape: cq.Shape) -> cq.Shape:
    """Union source tooth/root solids into one slicer-facing physical body."""
    solids = shape.Solids()
    if not solids:
        raise ValueError("cannot make a print body without solids")
    fused = solids[0].fuse(*solids[1:]) if len(solids) > 1 else solids[0]
    if len(fused.Solids()) != 1:
        raise ValueError(f"print union still has {len(fused.Solids())} solids")
    if not BRepCheck_Analyzer(fused.wrapped).IsValid():
        raise ValueError("print union is not a valid B-rep")
    return fused


def print_oriented_part(key: str, part: cq.Workplane) -> cq.Workplane:
    """Rigidly place one exact part on Z=0 in a stable thread-axis orientation."""
    shape = fused_print_shape(part.val())
    bb = shape.BoundingBox()
    if key in {"A", "B"}:
        oriented = workplane(shape).translate(
            (-(bb.xmin + bb.xmax) / 2.0, -(bb.ymin + bb.ymax) / 2.0, -bb.zmin)
        )
    elif key == "C":
        # C is stored on the assembly X axis.  Put that axis on print Z with
        # the broad lens-side end at the build plate.
        oriented = (
            workplane(shape)
            .translate(
                (
                    -bb.xmin,
                    -(bb.ymin + bb.ymax) / 2.0,
                    -(bb.zmin + bb.zmax) / 2.0,
                )
            )
            .rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)
        )
    else:
        raise KeyError(f"unknown OpenHI part: {key}")

    print_bb = oriented.val().BoundingBox()
    return oriented.translate(
        (
            -(print_bb.xmin + print_bb.xmax) / 2.0,
            -(print_bb.ymin + print_bb.ymax) / 2.0,
            -print_bb.zmin,
        )
    )


def output_paths(key: str) -> dict[str, Path]:
    stem = OUTPUT_STEMS[key]
    return {
        "step": ARTIFACT_DIR / f"{stem}.step",
        "stl": ARTIFACT_DIR / f"{stem}.stl",
        "3mf": ARTIFACT_DIR / f"{stem}.3mf",
        "root_step": DESIGN_DIR / f"USE_THIS_{stem}.step",
        "print_step": ARTIFACT_DIR / f"PRINT_THIS_{stem}.step",
        "print_stl": ARTIFACT_DIR / f"PRINT_THIS_{stem}.stl",
        "print_3mf": ARTIFACT_DIR / f"PRINT_THIS_{stem}.3mf",
        "root_print_step": DESIGN_DIR / f"PRINT_THIS_{stem}.step",
        "root_print_stl": DESIGN_DIR / f"PRINT_THIS_{stem}.stl",
        "root_print_3mf": DESIGN_DIR / f"PRINT_THIS_{stem}.3mf",
        "render": ARTIFACT_DIR / f"{stem}_render.png",
    }


def export_parts(parts: dict[str, cq.Workplane]) -> dict[str, dict[str, Any]]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    component_dir = ARTIFACT_DIR / "components"
    component_dir.mkdir(parents=True, exist_ok=True)
    print_component_dir = ARTIFACT_DIR / "print_components"
    print_component_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, dict[str, Any]] = {}
    for key, part in parts.items():
        paths = output_paths(key)
        exporters.export(part, str(paths["step"]))
        component_paths: list[Path] = []
        component_meshes: list[trimesh.Trimesh] = []
        for index, solid in enumerate(part.val().Solids(), start=1):
            component_path = component_dir / f"{OUTPUT_STEMS[key]}_solid_{index}.stl"
            exporters.export(
                solid,
                str(component_path),
                tolerance=0.02,
                angularTolerance=0.08,
            )
            component_mesh = trimesh.load_mesh(
                component_path, force="mesh", process=True
            )
            if not isinstance(component_mesh, trimesh.Trimesh):
                raise TypeError(f"component mesh load failed: {component_path}")
            component_paths.append(component_path)
            component_meshes.append(component_mesh)
        assembly_mesh = trimesh.util.concatenate(component_meshes)
        assembly_mesh.export(paths["stl"], file_type="stl")
        export_component_meshes_as_3mf(
            component_paths,
            paths["3mf"],
            title=f"OpenHI {key} exact current geometry",
        )

        print_part = print_oriented_part(key, part)
        exporters.export(print_part, str(paths["print_step"]))
        print_component_paths: list[Path] = []
        print_component_meshes: list[trimesh.Trimesh] = []
        for index, solid in enumerate(print_part.val().Solids(), start=1):
            component_path = (
                print_component_dir / f"PRINT_THIS_{OUTPUT_STEMS[key]}_solid_{index}.stl"
            )
            exporters.export(
                solid,
                str(component_path),
                tolerance=0.02,
                angularTolerance=0.08,
            )
            component_mesh = trimesh.load_mesh(
                component_path, force="mesh", process=True
            )
            if not isinstance(component_mesh, trimesh.Trimesh):
                raise TypeError(f"print component mesh load failed: {component_path}")
            print_component_paths.append(component_path)
            print_component_meshes.append(component_mesh)
        print_mesh = trimesh.util.concatenate(print_component_meshes)
        print_mesh.export(paths["print_stl"], file_type="stl")
        export_single_mesh_as_3mf(
            print_mesh,
            paths["print_3mf"],
            title=f"PRINT THIS OpenHI {key} exact current geometry",
        )

        shutil.copy2(paths["step"], paths["root_step"])
        for extension in ("step", "stl", "3mf"):
            shutil.copy2(
                paths[f"print_{extension}"], paths[f"root_print_{extension}"]
            )
        for stale_extension in ("stl", "3mf"):
            stale = DESIGN_DIR / f"USE_THIS_{OUTPUT_STEMS[key]}.{stale_extension}"
            if stale.exists():
                stale.unlink()
        outputs[key] = {name: repo_path(path) for name, path in paths.items()}
        outputs[key]["component_stls"] = [repo_path(path) for path in component_paths]
        outputs[key]["print_component_stls"] = [
            repo_path(path) for path in print_component_paths
        ]
    return outputs


def validate_outputs(outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    validation: dict[str, Any] = {}
    for key in ("A", "B", "C"):
        source_path = SOURCE_PATHS[key]
        output_step = ROOT / outputs[key]["step"]
        output_stl = ROOT / outputs[key]["stl"]
        output_3mf = ROOT / outputs[key]["3mf"]
        print_step = ROOT / outputs[key]["print_step"]
        print_stl = ROOT / outputs[key]["print_stl"]
        print_3mf = ROOT / outputs[key]["print_3mf"]
        component_stls = [ROOT / path for path in outputs[key]["component_stls"]]
        print_component_stls = [
            ROOT / path for path in outputs[key]["print_component_stls"]
        ]
        source_shape = cq.importers.importStep(str(source_path)).val()
        output_shape = cq.importers.importStep(str(output_step)).val()
        print_shape = cq.importers.importStep(str(print_step)).val()
        source_summary = shape_summary(source_shape)
        output_summary = shape_summary(output_shape)
        fused_source_summary = shape_summary(fused_print_shape(source_shape))
        print_summary = shape_summary(print_shape)
        geometry = compare_geometry(source_summary, output_summary)
        print_geometry = compare_rigid_geometry(fused_source_summary, print_summary)
        stl = validate_stl(
            output_stl, component_stls, source_summary["bbox"]["size"]
        )
        threemf = validate_3mf(
            output_3mf,
            stl["faces"],
            source_summary["solid_count"],
        )
        print_mesh = validate_print_stl(
            print_stl, print_component_stls, source_summary["bbox"]["size"]
        )
        print_threemf = validate_3mf(print_3mf, print_mesh["faces"], 1)
        validation[key] = {
            "source_step": repo_path(source_path),
            "source_sha256": sha256_file(source_path),
            "regenerated_step_sha256": sha256_file(output_step),
            "source": source_summary,
            "regenerated": output_summary,
            "geometry_comparison": geometry,
            "stl": stl,
            "3mf": threemf,
            "print_ready": {
                "fused_source": fused_source_summary,
                "step": print_summary,
                "rigid_geometry_comparison": print_geometry,
                "stl": print_mesh,
                "3mf": print_threemf,
                "all_pass": (
                    print_geometry["all_rigid_geometry_checks_pass"]
                    and print_mesh["bbox_matches_rigid_transform"]
                    and print_mesh["all_components_watertight"]
                    and print_mesh["on_build_plate"]
                    and print_mesh["first_layer_nonempty"]
                    and print_threemf["zip_valid"]
                    and print_threemf["model_present"]
                    and print_threemf["triangle_count_matches_stl"]
                    and print_threemf["object_count"] == 1
                    and print_threemf["build_item_count"] == 1
                ),
            },
            "all_pass": (
                geometry["all_geometry_checks_pass"]
                and stl["bbox_matches"]
                and stl["all_components_watertight"]
                and stl["assembly_triangle_count_matches_components"]
                and threemf["zip_valid"]
                and threemf["model_present"]
                and threemf["triangle_count_matches_stl"]
                and threemf["object_count_matches_solids"]
                and print_geometry["all_rigid_geometry_checks_pass"]
                and print_mesh["bbox_matches_rigid_transform"]
                and print_mesh["all_components_watertight"]
                and print_mesh["on_build_plate"]
                and print_mesh["first_layer_nonempty"]
                and print_threemf["zip_valid"]
                and print_threemf["model_present"]
                and print_threemf["triangle_count_matches_stl"]
                and print_threemf["object_count"] == 1
                and print_threemf["build_item_count"] == 1
            ),
        }
    validation["all_pass"] = all(validation[key]["all_pass"] for key in ("A", "B", "C"))
    return validation


def shapr_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "path": repo_path(SOURCE_SHAPR),
        "exists": SOURCE_SHAPR.exists(),
        "role": (
            "Identity/history evidence. The exact geometry authority is the flattened "
            "OpenHI_STEP export because the Shapr package stores imported bodies."
        ),
    }
    if SOURCE_SHAPR.exists():
        evidence["sha256"] = sha256_file(SOURCE_SHAPR)
        with zipfile.ZipFile(SOURCE_SHAPR) as archive:
            evidence["zip_entry_count"] = len(archive.namelist())
            evidence["contains_workspace"] = "workspace" in archive.namelist()
    return evidence


def render_paths() -> list[Path]:
    return [
        output_paths(key)["render"] for key in ("A", "B", "C")
    ] + [
        ARTIFACT_DIR / "OpenHI_ABC_exact_current_geometry_overview.png",
        ARTIFACT_DIR / "OpenHI_ABC_PRINT_THIS_build_plate_overview.png",
    ]


def write_readme(manifest: dict[str, Any]) -> None:
    outputs = manifest["outputs"]
    validation = manifest["validation"]
    lines = [
        "# OpenHI A/B/C Exact Parametric Baseline",
        "",
        "This project regenerates the complete current geometry of `A.step`, `B.step`, and `C.step` without changing any pivot, pitch, thread, chamfer, hole, lens seat, body placement, or compound topology.",
        "",
        "The `.shapr` archive is used to confirm the imported-body history and naming. The flattened STEP B-reps remain the exact geometry authority on Ubuntu.",
        "",
        "## Original Editable Parameters",
        "",
        "- Thread pitch: `0.8 mm`.",
        "- Radial tooth height: `0.4 mm` (`0.8 mm` diameter difference).",
        "- A top male pivot/crest: `29.8 / 30.6 mm`.",
        "- B lens male pivot/crest: `29.6 / 30.4 mm`.",
        "- B camera male pivot/crest: `24.4 / 25.2 mm`.",
        "- C lens male pivot/crest: `29.6 / 30.4 mm`.",
        "- C camera male pivot/crest: `24.4 / 25.2 mm`.",
        "",
        "These values are named command-line parameters in the builder. The current run leaves all of them unchanged. When all targets equal the source values, the builder preserves every original solid and only performs a clean STEP round trip. A future variant may change one pivot and rebuild only that localized tooth/root interface.",
        "",
        "## Direct Files",
        "",
        "| Part | Exact editable STEP | Print-ready STEP | Print-ready STL | Print-ready 3MF | Full render |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key in ("A", "B", "C"):
        item = outputs[key]
        lines.append(
            f"| {key} | `{item['root_step']}` | `{item['root_print_step']}` | `{item['root_print_stl']}` | `{item['root_print_3mf']}` | `{item['render']}` |"
        )
    lines.extend(
        [
            "",
            "## Validation",
            "",
        ]
    )
    for key in ("A", "B", "C"):
        item = validation[key]
        source = item["source"]
        comparison = item["geometry_comparison"]
        lines.append(
            f"- {key}: `{source['solid_count']}` solids, `{source['face_count']}` faces, bbox `{source['bbox']['size']}` mm, volume delta `{comparison['volume_abs_delta_mm3']}` mm^3, all checks `{item['all_pass']}`."
        )
    lines.extend(
        [
            "",
            "The STEP files are authoritative editable B-reps. STL and 3MF are deterministic tessellations of those regenerated B-reps; they are not mathematical B-rep formats.",
            "",
            "Use `USE_THIS_*.step` for Shapr3D editing. Use `PRINT_THIS_*.3mf` or `PRINT_THIS_*.stl` in Qidi Studio. The print-only body unions the source tooth/root solids into one valid watertight solid, is rigidly moved to `Z=0`, and packages exactly one 3MF model/build object. C is rotated from its assembly X axis onto print Z. The exact editable STEP remains an unchanged multi-solid B-rep.",
            "",
            "## Rebuild",
            "",
            "```bash",
            "cad/.conda/cad-python/bin/python3.11 cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py",
            "blender --background --python cad/designs/openhi_abc_exact_parametric_baseline/render_openhi_abc_exact_parametric_baseline.py",
            f"cad/.conda/cad-python/bin/python3.11 cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py --sync-only --run-name {manifest['run_name']}",
            "```",
            "",
            "Example future variant (not used for this baseline):",
            "",
            "```bash",
            "cad/.conda/cad-python/bin/python3.11 cad/designs/openhi_abc_exact_parametric_baseline/build_openhi_abc_exact_parametric_baseline.py --b-lens-pivot 29.8 --run-name run-3-b-lens-29p8-YYYYMMDDTHHMMSSZ",
            "```",
            "",
            "Use a new run name for every physical geometry change. Never overwrite the original extracted STEP sources.",
            "",
        ]
    )
    (DESIGN_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def run_directory(run_name: str) -> Path:
    return RUNS_DIR / run_name


def copy_project_handoff(run_name: str, manifest_path: Path) -> list[Path]:
    run_dir = run_directory(run_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in [
        DESIGN_DIR / "README.md",
        manifest_path,
        Path(__file__),
        DESIGN_DIR / "render_openhi_abc_exact_parametric_baseline.py",
        *[output_paths(key)["root_step"] for key in ("A", "B", "C")],
        *[
            output_paths(key)[f"root_print_{extension}"]
            for key in ("A", "B", "C")
            for extension in ("step", "stl", "3mf")
        ],
        *render_paths(),
    ]:
        if not source.exists():
            continue
        target = run_dir / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def sync_nutstore(run_name: str, manifest_path: Path) -> list[Path]:
    run_dir = run_directory(run_name)
    nutstore_run = NUTSTORE_DESIGN_DIR / run_name
    nutstore_run.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in sorted(run_dir.iterdir()):
        if not source.is_file():
            continue
        target = nutstore_run / source.name
        shutil.copy2(source, target)
        copied.append(target)
    NUTSTORE_DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    for key in ("A", "B", "C"):
        for stale_extension in ("stl", "3mf"):
            stale = NUTSTORE_DESIGN_DIR / (
                f"USE_THIS_{OUTPUT_STEMS[key]}.{stale_extension}"
            )
            if stale.exists():
                stale.unlink()
    for key in ("A", "B", "C"):
        for source in [
            output_paths(key)["root_step"],
            *[
                output_paths(key)[f"root_print_{extension}"]
                for extension in ("step", "stl", "3mf")
            ],
        ]:
            if source.exists():
                target = NUTSTORE_DESIGN_DIR / source.name
                shutil.copy2(source, target)
                copied.append(target)
    for source in [DESIGN_DIR / "README.md", manifest_path, *render_paths()]:
        if source.exists():
            target = NUTSTORE_DESIGN_DIR / source.name
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-top-pivot", type=float, default=ORIGINAL_PIVOTS_MM["a_top"])
    parser.add_argument("--b-lens-pivot", type=float, default=ORIGINAL_PIVOTS_MM["b_lens"])
    parser.add_argument("--b-camera-pivot", type=float, default=ORIGINAL_PIVOTS_MM["b_camera"])
    parser.add_argument("--c-lens-pivot", type=float, default=ORIGINAL_PIVOTS_MM["c_lens"])
    parser.add_argument("--c-camera-pivot", type=float, default=ORIGINAL_PIVOTS_MM["c_camera"])
    parser.add_argument("--run-name", default=DEFAULT_RUN_NAME)
    parser.add_argument("--sync-only", action="store_true")
    parser.add_argument("--no-nutstore", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = ARTIFACT_DIR / "manifest.json"
    if args.sync_only:
        if not manifest_path.exists():
            raise FileNotFoundError("build the baseline before using --sync-only")
        copy_project_handoff(args.run_name, manifest_path)
        copied = [] if args.no_nutstore else sync_nutstore(args.run_name, manifest_path)
        print(json.dumps({"synced": [str(path) for path in copied]}, indent=2))
        return

    missing = [str(path) for path in [*SOURCE_PATHS.values(), SOURCE_SHAPR] if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing OpenHI sources: {missing}")
    pivots = current_pivots(args)
    parts = build_parts(pivots)
    outputs = export_parts(parts)
    validation = validate_outputs(outputs)
    if not validation["all_pass"]:
        raise RuntimeError(json.dumps(validation, indent=2))

    manifest: dict[str, Any] = {
        "name": DESIGN_DIR.name,
        "purpose": "exact current A/B/C geometry with reusable pivot parameters",
        "units": "mm",
        "source_shapr": shapr_evidence(),
        "sources": {key: repo_path(path) for key, path in SOURCE_PATHS.items()},
        "source_hashes": {key: sha256_file(path) for key, path in SOURCE_PATHS.items()},
        "original_pivots_mm": ORIGINAL_PIVOTS_MM,
        "requested_pivots_mm": pivots,
        "geometry_changed": pivots != ORIGINAL_PIVOTS_MM,
        "thread_spec": {
            "pitch_mm": PITCH_MM,
            "radial_tooth_height_mm": TOOTH_RADIAL_HEIGHT_MM,
            "diameter_tooth_height_mm": 2.0 * TOOTH_RADIAL_HEIGHT_MM,
            "tooth_base_mm": TOOTH_BASE_MM,
            "hand": "right-hand",
        },
        "construction_contract": {
            "default_mode": "preserve complete imported source compounds",
            "variant_mode": "rebuild only explicitly changed thread tooth and root region",
            "source_files_modified": False,
            "simplified_threads": False,
            "placement_preserved": True,
            "compound_solid_counts_preserved": True,
        },
        "run_name": args.run_name,
        "outputs": outputs,
        "renders": [repo_path(path) for path in render_paths()],
        "validation": validation,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    run_files = copy_project_handoff(args.run_name, manifest_path)
    nutstore_files = [] if args.no_nutstore else sync_nutstore(args.run_name, manifest_path)
    manifest["run_files"] = [str(path) for path in run_files]
    manifest["nutstore_files"] = [str(path) for path in nutstore_files]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    copy_project_handoff(args.run_name, manifest_path)
    if not args.no_nutstore:
        sync_nutstore(args.run_name, manifest_path)
    print(
        json.dumps(
            {
                "manifest": repo_path(manifest_path),
                "run": repo_path(run_directory(args.run_name)),
                "all_pass": validation["all_pass"],
                "outputs": outputs,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
