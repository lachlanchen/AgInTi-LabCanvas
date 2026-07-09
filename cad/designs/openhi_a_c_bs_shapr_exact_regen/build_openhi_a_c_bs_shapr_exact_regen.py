#!/usr/bin/env python3
"""Regenerate OpenHI A+C+BS as an exact B-rep reference.

`OpenHI.shapr` stores the OpenHI assembly as imported Parasolid bodies. On
Ubuntu the reliable exact path is therefore to preserve the exported STEP
boundary representation, measure the receiver/thread surfaces, and use this
folder as the immutable baseline before creating printer-fit variants.
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.GeomAbs import (
    GeomAbs_BSplineSurface,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Plane,
    GeomAbs_SurfaceType,
    GeomAbs_Torus,
)
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_a_c_bs_shapr_exact_regen"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/A+ C + BS.step"
SOURCE_SHAPR = ROOT / "cad/extracted/OpenHI.shapr"

SURFACE_NAMES = {
    GeomAbs_Plane: "plane",
    GeomAbs_Cylinder: "cylinder",
    GeomAbs_Cone: "cone",
    GeomAbs_BSplineSurface: "bspline",
    GeomAbs_Torus: "torus",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def bbox_dict(shape: cq.Shape) -> dict[str, Any]:
    bb = shape.BoundingBox()
    return {
        "xlen": round(bb.xlen, 9),
        "ylen": round(bb.ylen, 9),
        "zlen": round(bb.zlen, 9),
        "min": [round(bb.xmin, 9), round(bb.ymin, 9), round(bb.zmin, 9)],
        "max": [round(bb.xmax, 9), round(bb.ymax, 9), round(bb.zmax, 9)],
        "center": [
            round((bb.xmin + bb.xmax) / 2.0, 9),
            round((bb.ymin + bb.ymax) / 2.0, 9),
            round((bb.zmin + bb.zmax) / 2.0, 9),
        ],
    }


def face_bbox(face: Any) -> dict[str, Any]:
    box = Bnd_Box()
    BRepBndLib.Add_s(face, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {
        "min": [round(xmin, 9), round(ymin, 9), round(zmin, 9)],
        "max": [round(xmax, 9), round(ymax, 9), round(zmax, 9)],
        "size": [round(xmax - xmin, 9), round(ymax - ymin, 9), round(zmax - zmin, 9)],
    }


def face_scan(shape: cq.Shape) -> dict[str, Any]:
    exp = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    counts: Counter[str] = Counter()
    cylinders: list[dict[str, Any]] = []
    cones: list[dict[str, Any]] = []
    bsplines: list[dict[str, Any]] = []
    face_index = 0
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        surface = BRepAdaptor_Surface(face, True)
        surface_type: GeomAbs_SurfaceType = surface.GetType()
        surface_name = SURFACE_NAMES.get(surface_type, str(surface_type))
        counts[surface_name] += 1
        bbox = face_bbox(face)

        if surface_type == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            axis = cylinder.Axis()
            direction = axis.Direction()
            location = axis.Location()
            cylinders.append(
                {
                    "face": face_index,
                    "radius_mm": round(cylinder.Radius(), 9),
                    "diameter_mm": round(cylinder.Radius() * 2.0, 9),
                    "axis_direction": [
                        round(direction.X(), 9),
                        round(direction.Y(), 9),
                        round(direction.Z(), 9),
                    ],
                    "axis_location": [
                        round(location.X(), 9),
                        round(location.Y(), 9),
                        round(location.Z(), 9),
                    ],
                    "bbox": bbox,
                }
            )
        elif surface_type == GeomAbs_Cone:
            cone = surface.Cone()
            axis = cone.Axis()
            direction = axis.Direction()
            location = axis.Location()
            cones.append(
                {
                    "face": face_index,
                    "ref_radius_mm": round(cone.RefRadius(), 9),
                    "ref_diameter_mm": round(cone.RefRadius() * 2.0, 9),
                    "semi_angle_rad": round(cone.SemiAngle(), 9),
                    "axis_direction": [
                        round(direction.X(), 9),
                        round(direction.Y(), 9),
                        round(direction.Z(), 9),
                    ],
                    "axis_location": [
                        round(location.X(), 9),
                        round(location.Y(), 9),
                        round(location.Z(), 9),
                    ],
                    "bbox": bbox,
                }
            )
        elif surface_type == GeomAbs_BSplineSurface:
            bsplines.append({"face": face_index, "bbox": bbox})

        face_index += 1
        exp.Next()

    vertical_receiver_cylinders = [
        item
        for item in cylinders
        if abs(item["axis_direction"][2]) > 0.9
        and 29.9 <= item["diameter_mm"] <= 30.5
        and 245.0 <= item["axis_location"][0] <= 265.0
        and 200.0 <= item["axis_location"][1] <= 220.0
    ]
    horizontal_receiver_cylinders = [
        item
        for item in cylinders
        if abs(item["axis_direction"][0]) > 0.9
        and 29.9 <= item["diameter_mm"] <= 30.5
        and 295.0 <= item["axis_location"][0] <= 315.0
        and 590.0 <= item["axis_location"][2] <= 610.0
    ]
    vertical_thread_bsplines = [
        item
        for item in bsplines
        if item["bbox"]["min"][2] >= 539.0
        and item["bbox"]["max"][2] <= 548.0
        and item["bbox"]["size"][0] >= 30.0
        and item["bbox"]["size"][1] >= 30.0
    ]
    horizontal_thread_bsplines = [
        item
        for item in bsplines
        if item["bbox"]["min"][0] >= 270.0
        and item["bbox"]["max"][0] <= 276.0
        and item["bbox"]["size"][1] >= 30.0
        and item["bbox"]["size"][2] >= 30.0
    ]
    center_bores = [
        item
        for item in cylinders
        if 23.8 <= item["diameter_mm"] <= 24.2 and abs(item["axis_direction"][2]) > 0.9
    ]
    lens_seats = [
        item
        for item in cylinders
        if 25.3 <= item["diameter_mm"] <= 25.7 and abs(item["axis_direction"][2]) > 0.9
    ]
    side_pin_holes = [
        item
        for item in cylinders
        if 1.4 <= item["diameter_mm"] <= 1.8 and abs(item["axis_direction"][1]) > 0.9
    ]
    oblique_holes = [
        item
        for item in cylinders
        if 1.3 <= item["diameter_mm"] <= 2.1
        and abs(abs(item["axis_direction"][0]) - 0.707106781) < 0.02
        and abs(abs(item["axis_direction"][2]) - 0.707106781) < 0.02
    ]
    chamfer_cones = [
        item
        for item in cones
        if abs(item["semi_angle_rad"] - 0.785398162) < 1e-6
    ]

    return {
        "face_count": face_index,
        "surface_type_counts": dict(sorted(counts.items())),
        "cylinders": cylinders,
        "cones": cones,
        "bsplines": bsplines,
        "vertical_receiver_cylinder_faces": vertical_receiver_cylinders,
        "horizontal_receiver_cylinder_faces": horizontal_receiver_cylinders,
        "vertical_thread_bspline_faces": vertical_thread_bsplines,
        "horizontal_thread_bspline_faces": horizontal_thread_bsplines,
        "center_bore_cylinder_faces": center_bores,
        "lens_seat_cylinder_faces": lens_seats,
        "side_pin_hole_cylinder_faces": side_pin_holes,
        "oblique_hole_cylinder_faces": oblique_holes,
        "chamfer_cone_faces": chamfer_cones,
    }


def shape_summary(shape: cq.Shape) -> dict[str, Any]:
    return {
        "bbox": bbox_dict(shape),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "volume_mm3": round(shape.Volume(), 9),
        "area_mm2": round(shape.Area(), 9),
    }


def shapr_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "source_shapr": repo_path(SOURCE_SHAPR),
        "available": SOURCE_SHAPR.exists(),
        "package_note": "OpenHI.shapr is a zip package containing a SQLite workspace and metadata.",
        "native_feature_tree_note": (
            "The relevant OpenHI optical bodies are stored as imported Parasolid/STEP-derived bodies. "
            "The workspace contains history/import nodes and names, but not a simple editable Shapr "
            "feature tree that can be replayed directly on Ubuntu."
        ),
    }
    if not SOURCE_SHAPR.exists():
        return evidence

    with tempfile.TemporaryDirectory(prefix="openhi_shapr_") as tmp:
        with zipfile.ZipFile(SOURCE_SHAPR) as zf:
            names = zf.namelist()
            evidence["zip_entries"] = names
            zf.extract("workspace", tmp)
        workspace = Path(tmp) / "workspace"
        raw = workspace.read_bytes()
        hits = []
        for pattern in [
            b"A+ C + BS",
            b"Lens A + BS holder",
            b"Import \"BS lateral.step\"",
            b"Thread BS",
            b"Thread top",
            b"BS cap",
            b"T branch head",
        ]:
            if pattern in raw:
                hits.append(pattern.decode("utf-8"))
        evidence["raw_string_hits"] = hits
        conn = sqlite3.connect(workspace)
        try:
            table_counts = {}
            for table in [
                "HistoryTreeNodes",
                "PersistedCalls",
                "BodyRevisionBlocks",
                "BodyRevisionDeltas",
                "HistoryImportedBodies",
                "HistoryImportedPrototypes",
                "SketchControllers",
                "SketchCurves",
            ]:
                table_counts[table] = conn.execute(f"select count(*) from {table}").fetchone()[0]
            evidence["table_counts"] = table_counts
            nodes = []
            for rowid, node_type, props in conn.execute(
                "select HistoryTreeNodeID, HistoryTreeNodeType, Properties from HistoryTreeNodes order by HistoryTreeNodeID"
            ):
                # The blobs are MessagePack; a full decoder is not needed here.
                strings = [m.decode("utf-8", "ignore") for m in re.findall(rb"[\x20-\x7e]{4,}", props)]
                if strings:
                    title = next((s for s in strings if "Import " in s or "Extrusion" in s or "Sketch" in s or "Movement" in s), strings[0])
                    nodes.append({"id": rowid, "type": node_type, "strings": strings, "title": title})
            evidence["history_nodes_with_strings"] = nodes
        finally:
            conn.close()
    return evidence


def make_inspection_cutaway(shape: cq.Shape) -> cq.Workplane:
    bb = shape.BoundingBox()
    keep_box = (
        cq.Workplane("XY")
        .box(bb.xlen + 20.0, bb.ylen / 2.0 + 10.0, bb.zlen + 20.0)
        .translate(
            (
                (bb.xmin + bb.xmax) / 2.0,
                bb.ymin + (bb.ylen / 2.0 + 10.0) / 2.0 - 5.0,
                (bb.zmin + bb.zmax) / 2.0,
            )
        )
    )
    pieces = []
    for solid in shape.Solids():
        cut = solid.intersect(keep_box.val())
        if cut.Volume() > 1e-6:
            pieces.append(cut)
    if pieces:
        return cq.Workplane().add(cq.Compound.makeCompound(pieces))

    # Some imported B-reps refuse this auxiliary boolean even though the main
    # body is valid. The cutaway is only an inspection artifact, so preserve the
    # exact source body instead of failing the exact-regeneration build.
    return cq.Workplane().add(shape)


def write_readme(manifest: dict[str, Any]) -> None:
    ref = manifest["reference_geometry"]
    regen = manifest["regenerated_geometry"]
    verification = manifest["verification"]
    scan = manifest["face_scan"]
    outputs = manifest["outputs"]
    lines = [
        "# OpenHI A+C+BS Shapr Exact Regeneration",
        "",
        "This folder regenerates `cad/extracted/OpenHI_STEP/A+ C + BS.step` as the exact B-rep baseline before any thread-fit edits.",
        "",
        "The Shapr workspace confirms this part belongs to the imported OpenHI/BS lateral group. It does not expose a replayable native feature tree for this body on Ubuntu, so the exact rebuild preserves the exported STEP boundary representation and records measured feature evidence.",
        "",
        "## Geometry Summary",
        "",
        f"- Bounding box: `{ref['bbox']['xlen']} x {ref['bbox']['ylen']} x {ref['bbox']['zlen']} mm`",
        f"- Solids: `{ref['solid_count']}`",
        f"- Faces: `{ref['face_count']}`",
        f"- Volume: `{ref['volume_mm3']} mm^3`",
        f"- Surface counts: `{scan['surface_type_counts']}`",
        "",
        "## Thread Evidence",
        "",
        "Both receiver starts in the exported STEP measure as 30.2 mm diameter surfaces:",
        "",
        f"- Bottom/away-from-BS receiver, Z axis: `{[(item['face'], item['diameter_mm'], item['axis_location'], item['axis_direction']) for item in scan['vertical_receiver_cylinder_faces']]}`.",
        f"- BS/B-side receiver, X axis: `{[(item['face'], item['diameter_mm'], item['axis_location'], item['axis_direction']) for item in scan['horizontal_receiver_cylinder_faces']]}`.",
        f"- Bottom helical B-spline faces: `{[item['face'] for item in scan['vertical_thread_bspline_faces']]}`.",
        f"- BS/B-side helical B-spline faces: `{[item['face'] for item in scan['horizontal_thread_bspline_faces']]}`.",
        "- In this STEP there is no measured evidence that the BS/B-side receiver was already smaller than the bottom receiver; both expose 30.2 mm cylindrical start/root faces.",
        "",
        "Related preserved features:",
        "",
        f"- Center bore faces: `{[(item['face'], item['diameter_mm']) for item in scan['center_bore_cylinder_faces']]}`.",
        f"- Lens seat faces: `{[(item['face'], item['diameter_mm']) for item in scan['lens_seat_cylinder_faces']]}`.",
        f"- 45 degree chamfer cone count: `{len(scan['chamfer_cone_faces'])}`.",
        f"- Side pin holes: `{[(item['face'], item['diameter_mm']) for item in scan['side_pin_hole_cylinder_faces']]}`.",
        f"- Oblique holes/counterbores: `{[(item['face'], item['diameter_mm']) for item in scan['oblique_hole_cylinder_faces']]}`.",
        "",
        "## Verification",
        "",
        f"- Regenerated bounding box: `{regen['bbox']['xlen']} x {regen['bbox']['ylen']} x {regen['bbox']['zlen']} mm`",
        f"- Bounding-box absolute difference: `{verification['bbox_abs_diff_mm']} mm`",
        f"- Face count unchanged: `{verification['face_count_same']}`",
        f"- Solid count unchanged: `{verification['solid_count_same']}`",
        f"- Surface type counts unchanged: `{verification['surface_type_counts_same']}`",
        f"- Volume absolute difference after STEP round trip: `{verification['volume_abs_diff_mm3']} mm^3`",
        "",
        "## Artifacts",
        "",
        "| Artifact | Path |",
        "| --- | --- |",
    ]
    for key, path in outputs.items():
        lines.append(f"| {key} | `{path}` |")
    lines.extend(
        [
            "",
            "## Rebuild",
            "",
            "```bash",
            "cad/.conda/cad-python/bin/python cad/designs/openhi_a_c_bs_shapr_exact_regen/build_openhi_a_c_bs_shapr_exact_regen.py",
            "blender --background --python cad/designs/openhi_a_c_bs_shapr_exact_regen/render_openhi_a_c_bs_shapr_exact_regen.py",
            "```",
            "",
            "## Next Variant",
            "",
            "Keep this folder unchanged. For the print-fit experiment, create a sibling variant that changes only the two OpenHI 30 mm female receiver starts from 30.2 mm to 30.0 mm while preserving the outer body, BS slope area, lens seat, side holes, and chamfers.",
            "",
        ]
    )
    (DESIGN_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"missing STEP source: {SOURCE_STEP}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    source_summary = shape_summary(source_shape)
    source_scan = face_scan(source_shape)

    regen_step = ARTIFACT_DIR / f"{STEM}.step"
    regen_stl = ARTIFACT_DIR / f"{STEM}.stl"
    cutaway_step = ARTIFACT_DIR / f"{STEM}_inspection_cutaway.step"
    cutaway_stl = ARTIFACT_DIR / f"{STEM}_inspection_cutaway.stl"
    exporters.export(source_shape, str(regen_step))
    exporters.export(source_shape, str(regen_stl))
    cutaway = make_inspection_cutaway(source_shape)
    exporters.export(cutaway, str(cutaway_step))
    exporters.export(cutaway, str(cutaway_stl))

    regenerated = cq.importers.importStep(str(regen_step)).val()
    regen_summary = shape_summary(regenerated)
    regen_scan = face_scan(regenerated)
    verification = {
        "bbox_abs_diff_mm": [
            round(abs(source_summary["bbox"][axis] - regen_summary["bbox"][axis]), 12)
            for axis in ("xlen", "ylen", "zlen")
        ],
        "volume_abs_diff_mm3": round(abs(source_summary["volume_mm3"] - regen_summary["volume_mm3"]), 9),
        "area_abs_diff_mm2": round(abs(source_summary["area_mm2"] - regen_summary["area_mm2"]), 9),
        "face_count_same": source_summary["face_count"] == regen_summary["face_count"],
        "solid_count_same": source_summary["solid_count"] == regen_summary["solid_count"],
        "surface_type_counts_same": source_scan["surface_type_counts"] == regen_scan["surface_type_counts"],
    }
    manifest = {
        "name": STEM,
        "units": "mm",
        "design_date": "2026-07-09",
        "source_step": repo_path(SOURCE_STEP),
        "source_shapr": repo_path(SOURCE_SHAPR),
        "shapr_evidence": shapr_evidence(),
        "reference_geometry": source_summary,
        "regenerated_geometry": regen_summary,
        "verification": verification,
        "face_scan": source_scan,
        "outputs": {
            "regenerated_step": repo_path(regen_step),
            "regenerated_stl": repo_path(regen_stl),
            "inspection_cutaway_step": repo_path(cutaway_step),
            "inspection_cutaway_stl": repo_path(cutaway_stl),
            "render_png": repo_path(ARTIFACT_DIR / f"{STEM}_render.png"),
            "thread_detail_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_thread_detail_render.png"),
            "inspection_cutaway_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_inspection_cutaway_render.png"),
            "blend": repo_path(ARTIFACT_DIR / f"{STEM}.blend"),
            "manifest_json": repo_path(ARTIFACT_DIR / "manifest.json"),
        },
    }
    (ARTIFACT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    print(regen_step)
    print(regen_stl)
    print(ARTIFACT_DIR / "manifest.json")


if __name__ == "__main__":
    main()
