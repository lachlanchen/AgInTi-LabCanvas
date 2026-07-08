#!/usr/bin/env python3
"""Regenerate the OpenHI Lens B holder as an exact B-rep reference.

This is not a native Shapr feature-tree reconstruction. `Nature.shapr` stores
the Lens B holder as an imported Parasolid body. On Ubuntu we can inspect the
Shapr SQLite database and recover the body mapping, but the practical exact
geometry path is to use the exported STEP B-rep and re-export it with measured
thread/chamfer metadata.
"""

from __future__ import annotations

import json
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
STEM = "openhi_lens_b_holder_shapr_exact_regen"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/Lens B holder.step"
SOURCE_SHAPR = Path("/home/lachlan/Downloads/Nature.shapr")


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


def face_bbox(face) -> dict[str, Any]:
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

    lens_thread_cylinders = [
        item
        for item in cylinders
        if 14.8 <= item["radius_mm"] <= 15.2
        and abs(item["axis_direction"][2]) > 0.9
        and item["bbox"]["size"][2] < 1.7
    ]
    lens_thread_splines = [
        item
        for item in bsplines
        if item["bbox"]["size"][0] > 30.0
        and item["bbox"]["size"][1] > 30.0
        and 7.0 <= item["bbox"]["size"][2] <= 9.5
    ]
    chamfer_cones = [
        item
        for item in cones
        if 12.0 <= item["ref_radius_mm"] <= 15.1
        and abs(item["axis_direction"][2]) > 0.9
    ]

    return {
        "face_count": face_index,
        "surface_type_counts": dict(sorted(counts.items())),
        "cylinders": cylinders,
        "cones": cones,
        "bsplines": bsplines,
        "lens_thread_cylinder_faces": lens_thread_cylinders,
        "lens_thread_bspline_faces": lens_thread_splines,
        "lens_chamfer_cone_faces": chamfer_cones,
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


def preserved_feature_evidence(scan: dict[str, Any]) -> dict[str, Any]:
    small_end_sink = [
        item
        for item in scan["cylinders"]
        if 1.8 <= item["diameter_mm"] <= 3.2
        and abs(item["axis_direction"][0]) > 0.6
        and abs(item["axis_direction"][2]) > 0.6
    ]
    side_pin_holes = [
        item
        for item in scan["cylinders"]
        if 1.4 <= item["diameter_mm"] <= 1.8 and abs(item["axis_direction"][1]) > 0.9
    ]
    axial_chamfers = [
        item
        for item in scan["lens_chamfer_cone_faces"]
        if abs(item["axis_direction"][2]) > 0.9
    ]
    return {
        "small_oblique_end_sink_cylindrical_faces": small_end_sink,
        "side_pin_hole_cylindrical_faces": side_pin_holes,
        "chamfer_cone_faces": scan["lens_chamfer_cone_faces"],
        "axial_end_chamfer_cone_faces": axial_chamfers,
        "notes": [
            "The small oblique end sink/counterbore is represented by the 2.0 mm and 3.0 mm coaxial cylindrical faces.",
            "The two axial end chamfer zones and the lens-seat chamfers are conical faces with about 0.785398 rad / 45 degree semi-angle.",
            "These are not approximated in this proof of concept; they are preserved because the regenerated STEP is the original B-rep round-tripped from the exported STEP.",
        ],
    }


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
    cutaway = shape.intersect(keep_box.val())
    return cq.Workplane().add(cutaway)


def shapr_body_mapping() -> dict[str, Any]:
    mapping = {
        "source_shapr": str(SOURCE_SHAPR),
        "available": SOURCE_SHAPR.exists(),
        "import_node": 1018368,
        "import_title": 'Import "BS lateral.step"',
        "folder_name": "Lens B holder",
        "folder_id": "b49e82d3f4bab8173088e5084c58f6e6",
        "visible_element_metadata_id": 86095,
        "primary_label_metadata_id": 86071,
        "primary_label": "Lens B holder chopped (2)* (1)",
        "primary_history_name_id": 697878,
        "primary_source_history_name_id": 697876,
        "primary_imported_body_id": 248,
        "related_labels": [
            {"metadata_id": 86065, "label": "Thread lens 29.6*", "imported_body_id": 245},
            {"metadata_id": 86073, "label": "Lens B camera (1)**", "imported_body_id": 249},
            {"metadata_id": 86075, "label": "Lens B camera (2)*", "imported_body_id": 250},
        ],
        "parasolid_note": "Shapr stores this object as imported Parasolid; this build uses the exported STEP B-rep for exact Ubuntu regeneration.",
    }
    if not SOURCE_SHAPR.exists():
        return mapping

    with tempfile.TemporaryDirectory(prefix="lens_b_shapr_") as tmp:
        with zipfile.ZipFile(SOURCE_SHAPR) as zf:
            zf.extract("workspace", tmp)
        conn = sqlite3.connect(Path(tmp) / "workspace")
        try:
            row = conn.execute(
                "select length(BodyData) from HistoryImportedBodies where ImportedBodyID=?",
                (mapping["primary_imported_body_id"],),
            ).fetchone()
            mapping["primary_imported_body_bytes"] = int(row[0]) if row else None
            for rel in mapping["related_labels"]:
                row = conn.execute(
                    "select length(BodyData) from HistoryImportedBodies where ImportedBodyID=?",
                    (rel["imported_body_id"],),
                ).fetchone()
                rel["imported_body_bytes"] = int(row[0]) if row else None
        finally:
            conn.close()
    return mapping


def write_readme(manifest: dict[str, Any]) -> None:
    outputs = manifest["outputs"]
    reference = manifest["reference_geometry"]
    regenerated = manifest["regenerated_geometry"]
    verification = manifest["verification"]
    shapr = manifest["shapr_mapping"]
    features = manifest["preserved_feature_evidence"]
    lines = [
        "# OpenHI Lens B Holder Shapr Exact Regeneration",
        "",
        "This folder regenerates the OpenHI `Lens B holder.step` as an exact B-rep reference.",
        "",
        "The source Shapr file confirms the object mapping:",
        "",
        f"- Shapr folder: `{shapr['folder_name']}`",
        f"- Shapr import node: `{shapr['import_node']}` / `{shapr['import_title']}`",
        f"- Shapr primary label: `{shapr['primary_label']}`",
        f"- Imported body ID: `{shapr['primary_imported_body_id']}`",
        "",
        "Because `Nature.shapr` stores this holder as an imported Parasolid body, not as editable native Shapr sketches/features, the exact Ubuntu path is to use the exported STEP B-rep and preserve its geometry. Use this as the baseline before changing only the larger female receiver/thread fit.",
        "",
        "## Geometry Summary",
        "",
        f"- Bounding box: `{reference['bbox']['xlen']} x {reference['bbox']['ylen']} x {reference['bbox']['zlen']} mm`",
        f"- Solids: `{reference['solid_count']}`",
        f"- Faces: `{reference['face_count']}`",
        f"- Volume: `{reference['volume_mm3']} mm^3`",
        f"- Surface counts: `{manifest['face_scan']['surface_type_counts']}`",
        "",
        "## Proof Of Concept Verification",
        "",
        "This proof of concept preserves the original STEP boundary representation instead of rebuilding an approximate parametric clone.",
        "",
        f"- Regenerated bounding box: `{regenerated['bbox']['xlen']} x {regenerated['bbox']['ylen']} x {regenerated['bbox']['zlen']} mm`",
        f"- Bounding-box absolute difference: `{verification['bbox_abs_diff_mm']} mm`",
        f"- Face count unchanged: `{verification['face_count_same']}`",
        f"- Solid count unchanged: `{verification['solid_count_same']}`",
        f"- Volume absolute difference after STEP round trip: `{verification['volume_abs_diff_mm3']} mm^3`",
        f"- Area absolute difference after STEP round trip: `{verification['area_abs_diff_mm2']} mm^2`",
        f"- Surface type counts unchanged: `{verification['surface_type_counts_same']}`",
        f"- Small oblique end sink face count unchanged: `{verification['small_oblique_end_sink_face_count_same']}`",
        f"- Chamfer cone face count unchanged: `{verification['chamfer_cone_face_count_same']}`",
        "",
        "Use the regenerated STEP as the exact baseline for later variants. If the next variant changes the female receiver to `25.4 mm`, keep this folder unchanged and create a sibling folder.",
        "",
        "## Thread And Chamfer Evidence",
        "",
        "- Small oblique end sink/counterbore faces are preserved:",
        f"  `{[(item['face'], item['diameter_mm']) for item in features['small_oblique_end_sink_cylindrical_faces']]}` as `(face, diameter_mm)`.",
        "- Side pin holes are preserved:",
        f"  `{[(item['face'], item['diameter_mm']) for item in features['side_pin_hole_cylindrical_faces']]}` as `(face, diameter_mm)`.",
        f"- Chamfer cone face count: `{len(features['chamfer_cone_faces'])}`.",
        "- Larger lens-thread axis is along `Z` around `(x=254.633, y=210.0)`.",
        "- Repeated cylindrical tooth faces use radius about `15.1 mm` / diameter `30.2 mm`.",
        "- Two large B-spline faces span the helical threaded zone, about `31 mm` in X/Y and `8.15 mm` in Z.",
        "- Conical end/chamfer faces are preserved by the B-rep export; their measured semi-angle is about `0.7854 rad`.",
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
            "cad/.conda/cad-python/bin/python cad/designs/openhi_lens_b_holder_shapr_exact_regen/build_openhi_lens_b_holder_shapr_exact_regen.py",
            "blender --background --python cad/designs/openhi_lens_b_holder_shapr_exact_regen/render_openhi_lens_b_holder_shapr_exact_regen.py",
            "```",
            "",
            "## Next Editable Variant",
            "",
            "For the next printer-fit experiment, create a sibling parametric/surgical variant from this exact baseline and change only the requested female receiver/thread construction, such as a normal `25.4 mm` C-mount-sized receiver. Keep this proof-of-concept folder unchanged.",
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
    source_face_scan = face_scan(source_shape)
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
    regenerated_face_scan = face_scan(regenerated)
    verification = {
        "bbox_abs_diff_mm": [
            round(abs(source_summary["bbox"][axis] - regen_summary["bbox"][axis]), 12)
            for axis in ("xlen", "ylen", "zlen")
        ],
        "volume_abs_diff_mm3": round(abs(source_summary["volume_mm3"] - regen_summary["volume_mm3"]), 9),
        "area_abs_diff_mm2": round(abs(source_summary["area_mm2"] - regen_summary["area_mm2"]), 9),
        "face_count_same": source_summary["face_count"] == regen_summary["face_count"],
        "solid_count_same": source_summary["solid_count"] == regen_summary["solid_count"],
        "surface_type_counts_same": source_face_scan["surface_type_counts"] == regenerated_face_scan["surface_type_counts"],
        "small_oblique_end_sink_face_count_same": len(
            preserved_feature_evidence(source_face_scan)["small_oblique_end_sink_cylindrical_faces"]
        )
        == len(preserved_feature_evidence(regenerated_face_scan)["small_oblique_end_sink_cylindrical_faces"]),
        "chamfer_cone_face_count_same": len(preserved_feature_evidence(source_face_scan)["chamfer_cone_faces"])
        == len(preserved_feature_evidence(regenerated_face_scan)["chamfer_cone_faces"]),
    }

    manifest = {
        "name": STEM,
        "units": "mm",
        "design_date": "2026-07-08",
        "source_step": repo_path(SOURCE_STEP),
        "source_shapr": str(SOURCE_SHAPR),
        "shapr_mapping": shapr_body_mapping(),
        "reference_geometry": source_summary,
        "regenerated_geometry": regen_summary,
        "verification": verification,
        "face_scan": source_face_scan,
        "regenerated_face_scan_summary": {
            "surface_type_counts": regenerated_face_scan["surface_type_counts"],
            "lens_chamfer_cone_face_count": len(regenerated_face_scan["lens_chamfer_cone_faces"]),
            "lens_thread_cylinder_face_count": len(regenerated_face_scan["lens_thread_cylinder_faces"]),
            "lens_thread_bspline_face_count": len(regenerated_face_scan["lens_thread_bspline_faces"]),
        },
        "preserved_feature_evidence": preserved_feature_evidence(source_face_scan),
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
