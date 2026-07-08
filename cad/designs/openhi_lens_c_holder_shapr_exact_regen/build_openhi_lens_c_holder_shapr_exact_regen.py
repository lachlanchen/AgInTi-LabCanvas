#!/usr/bin/env python3
"""Regenerate the OpenHI Lens C holder as an exact B-rep reference.

`Nature.shapr` stores this part as imported Parasolid bodies. The exact
proof-of-concept path on Ubuntu is therefore to use the exported STEP B-rep,
record the Shapr body mapping, and round-trip the shape without approximating
the native feature tree.
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
STEM = "openhi_lens_c_holder_shapr_exact_regen"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/Lens C holder.step"
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

    thread_bs_cylinders = [
        item
        for item in cylinders
        if 29.6 <= item["diameter_mm"] <= 30.0
        and abs(item["axis_direction"][0]) > 0.9
        and item["bbox"]["max"][0] <= 296.5
    ]
    receiver_thread_cylinders = [
        item
        for item in cylinders
        if 30.0 <= item["diameter_mm"] <= 30.4
        and abs(item["axis_direction"][0]) > 0.9
        and item["bbox"]["min"][0] >= 327.0
    ]
    receiver_thread_splines = [
        item
        for item in bsplines
        if item["bbox"]["min"][0] >= 327.0
        and item["bbox"]["size"][1] > 30.0
        and item["bbox"]["size"][2] > 30.0
    ]
    chamfer_cones = [
        item
        for item in cones
        if abs(item["axis_direction"][0]) > 0.9 and abs(item["semi_angle_rad"] - 0.785398162) < 1e-6
    ]
    center_bores = [
        item
        for item in cylinders
        if 23.8 <= item["diameter_mm"] <= 24.2 and abs(item["axis_direction"][0]) > 0.9
    ]
    return {
        "face_count": face_index,
        "surface_type_counts": dict(sorted(counts.items())),
        "cylinders": cylinders,
        "cones": cones,
        "bsplines": bsplines,
        "thread_bs_cylinder_faces": thread_bs_cylinders,
        "receiver_thread_cylinder_faces": receiver_thread_cylinders,
        "receiver_thread_bspline_faces": receiver_thread_splines,
        "chamfer_cone_faces": chamfer_cones,
        "center_bore_cylinder_faces": center_bores,
    }


def shape_summary(shape: cq.Shape) -> dict[str, Any]:
    solids = []
    for index, solid in enumerate(shape.Solids()):
        solids.append(
            {
                "index": index,
                "bbox": bbox_dict(solid),
                "face_count": len(solid.Faces()),
                "volume_mm3": round(solid.Volume(), 9),
            }
        )
    return {
        "bbox": bbox_dict(shape),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "volume_mm3": round(shape.Volume(), 9),
        "area_mm2": round(shape.Area(), 9),
        "solids": solids,
    }


def shapr_body_mapping() -> dict[str, Any]:
    mapping = {
        "source_shapr": str(SOURCE_SHAPR),
        "available": SOURCE_SHAPR.exists(),
        "import_node": 1018368,
        "import_title": 'Import "BS lateral.step"',
        "labels": [
            {"metadata_id": 86081, "label": "Thread BS", "imported_body_id": 253},
            {"metadata_id": 86067, "label": "T branch head (1)", "imported_body_id": 246},
            {"metadata_id": 86083, "label": "Lens C camera (1)*", "imported_body_id": 254},
            {"metadata_id": 86063, "label": "Lens C camera (2)*", "imported_body_id": 244},
        ],
        "parasolid_note": "Shapr stores these Lens C holder bodies as imported Parasolid data; this proof of concept uses the exported STEP B-rep for exact regeneration.",
    }
    if not SOURCE_SHAPR.exists():
        return mapping
    with tempfile.TemporaryDirectory(prefix="lens_c_shapr_") as tmp:
        with zipfile.ZipFile(SOURCE_SHAPR) as zf:
            zf.extract("workspace", tmp)
        conn = sqlite3.connect(Path(tmp) / "workspace")
        try:
            for label in mapping["labels"]:
                row = conn.execute(
                    "select length(BodyData) from HistoryImportedBodies where ImportedBodyID=?",
                    (label["imported_body_id"],),
                ).fetchone()
                label["imported_body_bytes"] = int(row[0]) if row else None
        finally:
            conn.close()
    return mapping


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
    if not pieces:
        raise ValueError("inspection cutaway produced no solid pieces")
    return cq.Workplane().add(cq.Compound.makeCompound(pieces))


def write_readme(manifest: dict[str, Any]) -> None:
    ref = manifest["reference_geometry"]
    verification = manifest["verification"]
    outputs = manifest["outputs"]
    scan = manifest["face_scan"]
    lines = [
        "# OpenHI Lens C Holder Shapr Exact Regeneration",
        "",
        "This folder regenerates `cad/extracted/OpenHI_STEP/Lens C holder.step` as an exact B-rep proof of concept.",
        "",
        "The source STEP contains two solids: `Thread BS` and `T branch head (1)`. `Nature.shapr` stores the corresponding Lens C holder pieces as imported Parasolid bodies, so this exact regeneration preserves the exported STEP boundary representation rather than rebuilding an approximate feature tree.",
        "",
        "## Geometry Summary",
        "",
        f"- Bounding box: `{ref['bbox']['xlen']} x {ref['bbox']['ylen']} x {ref['bbox']['zlen']} mm`",
        f"- Solids: `{ref['solid_count']}`",
        f"- Faces: `{ref['face_count']}`",
        f"- Volume: `{ref['volume_mm3']} mm^3`",
        f"- Surface counts: `{scan['surface_type_counts']}`",
        "",
        "## Proof Of Concept Verification",
        "",
        f"- Regenerated bounding box: `{manifest['regenerated_geometry']['bbox']['xlen']} x {manifest['regenerated_geometry']['bbox']['ylen']} x {manifest['regenerated_geometry']['bbox']['zlen']} mm`",
        f"- Bounding-box absolute difference: `{verification['bbox_abs_diff_mm']} mm`",
        f"- Face count unchanged: `{verification['face_count_same']}`",
        f"- Solid count unchanged: `{verification['solid_count_same']}`",
        f"- Surface type counts unchanged: `{verification['surface_type_counts_same']}`",
        f"- Volume absolute difference after STEP round trip: `{verification['volume_abs_diff_mm3']} mm^3`",
        "",
        "## Thread And Chamfer Evidence",
        "",
        f"- `Thread BS` cylindrical thread faces: `{[(item['face'], item['diameter_mm']) for item in scan['thread_bs_cylinder_faces']]}` as `(face, diameter_mm)`.",
        f"- Positive-X receiver thread cylindrical faces: `{[(item['face'], item['diameter_mm']) for item in scan['receiver_thread_cylinder_faces']]}` as `(face, diameter_mm)`.",
        f"- Positive-X receiver helical B-spline faces: `{[item['face'] for item in scan['receiver_thread_bspline_faces']]}`.",
        f"- 45 degree chamfer cone face count: `{len(scan['chamfer_cone_faces'])}`.",
        f"- Center bore faces: `{[(item['face'], item['diameter_mm']) for item in scan['center_bore_cylinder_faces']]}` as `(face, diameter_mm)`.",
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
            "cad/.conda/cad-python/bin/python cad/designs/openhi_lens_c_holder_shapr_exact_regen/build_openhi_lens_c_holder_shapr_exact_regen.py",
            "blender --background --python cad/designs/openhi_lens_c_holder_shapr_exact_regen/render_openhi_lens_c_holder_shapr_exact_regen.py",
            "```",
            "",
            "## Next Variant",
            "",
            "Keep this exact proof-of-concept folder unchanged. For the 25.4 mm experiment, use the sibling `openhi_lens_c_holder_receiver_25p4` design.",
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
        "design_date": "2026-07-08",
        "source_step": repo_path(SOURCE_STEP),
        "source_shapr": str(SOURCE_SHAPR),
        "shapr_mapping": shapr_body_mapping(),
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
            "receiver_detail_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_receiver_detail_render.png"),
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
