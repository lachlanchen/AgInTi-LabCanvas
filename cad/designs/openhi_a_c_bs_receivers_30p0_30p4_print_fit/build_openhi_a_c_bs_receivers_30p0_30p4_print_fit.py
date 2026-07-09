#!/usr/bin/env python3
"""Build OpenHI A+C+BS with the stable 30 mm receiver tightened for printing.

This is a surgical sibling of `openhi_a_c_bs_shapr_exact_regen`. It keeps the
imported A+C+BS body envelope and changes only the lower OpenHI 30 mm female
receiver start from the measured old 30.2 mm to a 30.0 mm pilot/start with a
30.4 mm groove cutter, matching the Lens B/C print-fit convention. The
beam-splitter-side receiver is preserved exactly because local fill/re-cut
booleans in that pocket produced foreign B-rep faces in the optical opening.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_BSplineSurface, GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_a_c_bs_receivers_30p0_30p4_print_fit"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/A+ C + BS.step"
EXACT_BASELINE = ROOT / "cad/designs/openhi_a_c_bs_shapr_exact_regen/artifacts/manifest.json"

THREAD_OVERLAP = 0.04

PARAMS: dict[str, Any] = {
    "name": STEM,
    "design_date": "2026-07-09",
    "units": "mm",
    "source_step": "cad/extracted/OpenHI_STEP/A+ C + BS.step",
    "exact_baseline": "cad/designs/openhi_a_c_bs_shapr_exact_regen",
    "design_variant": "lower OpenHI 30 mm female receiver changed from old 30.2 mm start/root to 30.0 mm pilot plus 30.4 mm groove cutter; BS-side receiver preserved exact",
    "old_receiver_start_diameter_mm": 30.2,
    "female_pilot_bore_diameter_mm": 30.0,
    "female_thread_cutter_max_diameter_mm": 30.4,
    "female_groove_max_diameter_mm": 30.4,
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.2,
    "thread_tooth_base_mm": 0.8,
    "thread_runout_extra_length_each_end_mm": 0.4,
    "vertical_axis_x_mm": 255.0,
    "vertical_axis_y_mm": 210.0,
    "vertical_internal_fill_diameter_mm": 31.0,
    "vertical_internal_fill_z0_mm": 539.6,
    "vertical_internal_fill_length_mm": 10.4,
    "vertical_front_mouth_fill_start_diameter_mm": 40.0,
    "vertical_front_mouth_fill_end_diameter_mm": 30.2,
    "vertical_front_mouth_fill_z0_mm": 535.1,
    "vertical_front_mouth_fill_length_mm": 4.9,
    "vertical_front_mouth_z0_mm": 535.1,
    "vertical_front_mouth_length_mm": 4.9,
    "vertical_front_mouth_diameter_outer_mm": 40.0,
    "vertical_front_mouth_diameter_inner_mm": 30.0,
    "vertical_thread_z0_mm": 540.0,
    "vertical_thread_length_mm": 7.75,
    "vertical_pilot_bore_z0_mm": 540.0,
    "vertical_pilot_bore_length_mm": 7.75,
    "vertical_transition_chamfer_z0_mm": 547.75,
    "vertical_transition_chamfer_length_mm": 2.25,
    "vertical_transition_chamfer_start_diameter_mm": 30.0,
    "vertical_transition_chamfer_end_diameter_mm": 25.5,
    "horizontal_bs_receiver_mode": "preserve_exact_source_geometry",
    "method_note": (
        "The vertical receiver is rebuilt with fill bodies shaped close to the old mouth/thread void, "
        "not a broad oversized tube. The horizontal BS/B-side receiver is left untouched because both "
        "full-cylinder fill and annular wall-fill approaches created unstable or visible foreign B-rep "
        "surfaces in the beam-splitter opening. Preserving that side keeps the optical pocket clean."
    ),
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


def shape_summary(shape: cq.Shape) -> dict[str, Any]:
    return {
        "bbox": bbox_dict(shape),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "volume_mm3": round(shape.Volume(), 9),
        "area_mm2": round(shape.Area(), 9),
    }


def bbox_size_abs_diff(a: dict[str, Any], b: dict[str, Any]) -> list[float]:
    return [round(abs(a[key] - b[key]), 9) for key in ("xlen", "ylen", "zlen")]


def z_cylinder(diameter: float, length: float, z0: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .workplane(offset=z0)
        .circle(diameter / 2.0)
        .extrude(length)
        .translate((PARAMS["vertical_axis_x_mm"], PARAMS["vertical_axis_y_mm"], 0))
    )


def z_frustum(start_diameter: float, end_diameter: float, length: float, z0: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .workplane(offset=z0)
        .circle(start_diameter / 2.0)
        .workplane(offset=length)
        .circle(end_diameter / 2.0)
        .loft(combine=True)
        .translate((PARAMS["vertical_axis_x_mm"], PARAMS["vertical_axis_y_mm"], 0))
    )


def x_thread_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
    return cq.Workplane("XY").box(length, span, span, centered=(False, True, True)).translate((x0, 0, 0))


def z_thread_cutter(z0: float, length: float) -> cq.Workplane:
    pitch = PARAMS["thread_pitch_mm"]
    height = PARAMS["thread_tooth_height_mm"]
    base = PARAMS["thread_tooth_base_mm"]
    extra = PARAMS["thread_runout_extra_length_each_end_mm"]
    cutter_max = PARAMS["female_thread_cutter_max_diameter_mm"]
    root_d = cutter_max - 2.0 * height
    sweep_z0 = z0 - extra
    sweep_length = length + 2.0 * extra
    root_r = root_d / 2.0 - THREAD_OVERLAP
    path = cq.Wire.makeHelix(
        pitch,
        sweep_length,
        root_r,
        center=(sweep_z0, 0, 0),
        dir=(1, 0, 0),
        lefthand=True,
    )
    profile = (
        cq.Workplane("XY")
        .center(sweep_z0, root_r)
        .polyline([(0, 0), (base / 2.0, height + THREAD_OVERLAP), (base, 0)])
        .close()
    )
    thread = profile.sweep(path, isFrenet=True, combine=False)
    thread = thread.intersect(x_thread_clip_box(z0, length, cutter_max + 4.0))
    return (
        thread.rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((PARAMS["vertical_axis_x_mm"], PARAMS["vertical_axis_y_mm"], 0))
    )


def face_scan(shape: cq.Shape) -> dict[str, Any]:
    cylinders: list[dict[str, Any]] = []
    bsplines: list[dict[str, Any]] = []
    exp = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    index = 0
    while exp.More():
        face = cq.Face(TopoDS.Face_s(exp.Current()))
        surface = BRepAdaptor_Surface(face.wrapped, True)
        bb = face.BoundingBox()
        bbox = {
            "min": [round(bb.xmin, 9), round(bb.ymin, 9), round(bb.zmin, 9)],
            "max": [round(bb.xmax, 9), round(bb.ymax, 9), round(bb.zmax, 9)],
            "size": [round(bb.xlen, 9), round(bb.ylen, 9), round(bb.zlen, 9)],
        }
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            axis = cylinder.Axis()
            direction = axis.Direction()
            location = axis.Location()
            cylinders.append(
                {
                    "face": index,
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
        elif surface.GetType() == GeomAbs_BSplineSurface:
            bsplines.append({"face": index, "bbox": bbox})
        index += 1
        exp.Next()

    vertical_old_30p2 = [
        item
        for item in cylinders
        if 30.15 <= item["diameter_mm"] <= 30.25
        and abs(item["axis_direction"][2]) > 0.9
        and 539.0 <= item["bbox"]["min"][2] <= 548.0
    ]
    horizontal_old_30p2 = [
        item
        for item in cylinders
        if 30.15 <= item["diameter_mm"] <= 30.25
        and abs(item["axis_direction"][0]) > 0.9
        and 245.0 <= item["bbox"]["min"][0] <= 276.0
    ]
    new_30p0 = [
        item
        for item in cylinders
        if 29.95 <= item["diameter_mm"] <= 30.05
    ]
    exposed_fill_candidate_faces = [
        item
        for item in cylinders
        if 30.5 <= item["diameter_mm"] <= 39.5
    ]
    thread_bsplines = [
        item
        for item in bsplines
        if (
            item["bbox"]["size"][0] >= 4.0
            and item["bbox"]["size"][1] >= 29.0
            and item["bbox"]["size"][2] >= 29.0
        )
        or (
            item["bbox"]["size"][2] >= 4.0
            and item["bbox"]["size"][0] >= 29.0
            and item["bbox"]["size"][1] >= 29.0
        )
    ]
    return {
        "cylinders": cylinders,
        "bsplines": bsplines,
        "old_30p2_vertical_faces_remaining": vertical_old_30p2,
        "old_30p2_horizontal_faces_remaining": horizontal_old_30p2,
        "new_30p0_cylinder_faces": new_30p0,
        "exposed_mid_diameter_fill_candidate_faces": exposed_fill_candidate_faces,
        "thread_bspline_faces": thread_bsplines,
    }


def make_cutaway(shape: cq.Shape) -> cq.Workplane:
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
        try:
            cut = solid.intersect(keep_box.val())
        except ValueError:
            continue
        if cut.Volume() > 1e-6:
            pieces.append(cut)
    if pieces:
        return cq.Workplane().add(cq.Compound.makeCompound(pieces))
    return cq.Workplane().add(shape)


def build_variant() -> dict[str, cq.Workplane]:
    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    if len(source_shape.Solids()) != 1:
        raise ValueError(f"expected 1 source solid, got {len(source_shape.Solids())}")

    vertical_internal_fill = z_cylinder(
        PARAMS["vertical_internal_fill_diameter_mm"],
        PARAMS["vertical_internal_fill_length_mm"],
        PARAMS["vertical_internal_fill_z0_mm"],
    )
    vertical_front_mouth_fill = z_frustum(
        PARAMS["vertical_front_mouth_fill_start_diameter_mm"],
        PARAMS["vertical_front_mouth_fill_end_diameter_mm"],
        PARAMS["vertical_front_mouth_fill_length_mm"],
        PARAMS["vertical_front_mouth_fill_z0_mm"],
    )
    vertical_mouth = z_frustum(
        PARAMS["vertical_front_mouth_diameter_outer_mm"],
        PARAMS["vertical_front_mouth_diameter_inner_mm"],
        PARAMS["vertical_front_mouth_length_mm"],
        PARAMS["vertical_front_mouth_z0_mm"],
    )
    vertical_pilot = z_cylinder(
        PARAMS["female_pilot_bore_diameter_mm"],
        PARAMS["vertical_pilot_bore_length_mm"],
        PARAMS["vertical_pilot_bore_z0_mm"],
    )
    vertical_chamfer = z_frustum(
        PARAMS["vertical_transition_chamfer_start_diameter_mm"],
        PARAMS["vertical_transition_chamfer_end_diameter_mm"],
        PARAMS["vertical_transition_chamfer_length_mm"],
        PARAMS["vertical_transition_chamfer_z0_mm"],
    )
    vertical_thread = z_thread_cutter(PARAMS["vertical_thread_z0_mm"], PARAMS["vertical_thread_length_mm"])

    body = (
        cq.Workplane()
        .add(source_shape)
        .union(vertical_front_mouth_fill)
        .union(vertical_internal_fill)
        .cut(vertical_mouth)
        .cut(vertical_pilot)
        .cut(vertical_thread)
        .cut(vertical_chamfer)
    )
    return {
        "source": cq.Workplane().add(source_shape),
        "modified": body,
        "vertical_front_mouth_fill": vertical_front_mouth_fill,
        "vertical_internal_fill": vertical_internal_fill,
        "vertical_front_mouth_cutter": vertical_mouth,
        "vertical_pilot_bore_cutter": vertical_pilot,
        "vertical_thread_cutter": vertical_thread,
        "vertical_transition_chamfer_cutter": vertical_chamfer,
        "inspection_cutaway": make_cutaway(body.val()),
    }


def export_all(parts: dict[str, cq.Workplane]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for key, part in parts.items():
        if key == "source":
            continue
        step_path = ARTIFACT_DIR / f"{STEM}_{key}.step" if key != "modified" else ARTIFACT_DIR / f"{STEM}.step"
        exporters.export(part, str(step_path))
        outputs[f"{key}_step" if key != "modified" else "assembly_step"] = repo_path(step_path)
        if key in {"modified", "inspection_cutaway"}:
            stl_path = step_path.with_suffix(".stl")
            exporters.export(part, str(stl_path))
            outputs[f"{key}_stl" if key != "modified" else "assembly_stl"] = repo_path(stl_path)
    outputs["render_png"] = repo_path(ARTIFACT_DIR / f"{STEM}_render.png")
    outputs["receiver_detail_render_png"] = repo_path(ARTIFACT_DIR / f"{STEM}_receiver_detail_render.png")
    outputs["inspection_cutaway_render_png"] = repo_path(ARTIFACT_DIR / f"{STEM}_inspection_cutaway_render.png")
    outputs["blend"] = repo_path(ARTIFACT_DIR / f"{STEM}.blend")
    outputs["manifest_json"] = repo_path(ARTIFACT_DIR / "manifest.json")
    return outputs


def write_readme(manifest: dict[str, Any]) -> None:
    params = manifest["params"]
    source = manifest["source_geometry"]
    variant = manifest["variant_geometry"]
    verification = manifest["verification"]
    outputs = manifest["outputs"]
    lines = [
        "# OpenHI A+C+BS Lower Receiver 30.0/30.4 Print Fit",
        "",
        "This sibling design tightens the lower OpenHI 30 mm female receiver start in `A+ C + BS.step` while preserving the exact source body envelope and the original beam-splitter-side receiver.",
        "",
        "## Thread Definition",
        "",
        f"- Old measured receiver start/root diameter: `{params['old_receiver_start_diameter_mm']} mm`",
        f"- New smooth pilot/start diameter: `{params['female_pilot_bore_diameter_mm']} mm`",
        f"- New groove/thread-cutter max diameter: `{params['female_thread_cutter_max_diameter_mm']} mm`",
        f"- Pitch: `{params['thread_pitch_mm']} mm`; radial tooth height: `{params['thread_tooth_height_mm']} mm`; tooth base: `{params['thread_tooth_base_mm']} mm`",
        "",
        "## Changed Regions",
        "",
        "- Bottom/away-from-BS receiver: rebuilt from the 40 mm mouth to the preserved 25.5 mm lens-seat transition.",
        "- BS/B-side receiver: preserved exactly from the OpenHI source STEP to avoid adding foreign surfaces inside the beam-splitter pocket.",
        "",
        params["method_note"],
        "",
        "## Validation",
        "",
        f"- Source bbox: `{source['bbox']['xlen']} x {source['bbox']['ylen']} x {source['bbox']['zlen']} mm`",
        f"- Variant bbox: `{variant['bbox']['xlen']} x {variant['bbox']['ylen']} x {variant['bbox']['zlen']} mm`",
        f"- Overall bbox size difference: `{verification['overall_bbox_size_abs_diff_mm']} mm`",
        f"- Source solids: `{source['solid_count']}`; variant solids: `{variant['solid_count']}`",
        f"- Old 30.2 mm vertical faces remaining in modified scan: `{len(manifest['variant_face_scan']['old_30p2_vertical_faces_remaining'])}`",
        f"- Old 30.2 mm horizontal faces preserved in modified scan: `{len(manifest['variant_face_scan']['old_30p2_horizontal_faces_remaining'])}`",
        f"- Exposed mid-diameter fill candidate faces: `{len(manifest['variant_face_scan']['exposed_mid_diameter_fill_candidate_faces'])}`",
        f"- New 30.0 mm cylinder faces found: `{[(item['face'], item['diameter_mm'], item['bbox']) for item in manifest['variant_face_scan']['new_30p0_cylinder_faces']]}`",
        "",
        "This is still a surgical B-rep variant. Inspect the exported cutter files and renders before printing. A previous full-cylinder horizontal fill left a visible foreign strip in the beam-splitter opening, and the annular retry was unstable in OCCT; this build intentionally does not edit that BS-side receiver.",
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
            "cad/.conda/cad-python/bin/python cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/build_openhi_a_c_bs_receivers_30p0_30p4_print_fit.py",
            "blender --background --python cad/designs/openhi_a_c_bs_receivers_30p0_30p4_print_fit/render_openhi_a_c_bs_receivers_30p0_30p4_print_fit.py",
            "```",
            "",
        ]
    )
    (DESIGN_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"missing STEP source: {SOURCE_STEP}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in ARTIFACT_DIR.glob(f"{STEM}_horizontal_*.step"):
        stale.unlink()
    parts = build_variant()
    outputs = export_all(parts)

    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    in_memory_variant_shape = parts["modified"].val()
    exported_variant = cq.importers.importStep(str(ARTIFACT_DIR / f"{STEM}.step")).val()
    source_summary = shape_summary(source_shape)
    in_memory_variant_summary = shape_summary(in_memory_variant_shape)
    exported_summary = shape_summary(exported_variant)
    variant_summary = exported_summary
    manifest = {
        "name": STEM,
        "units": "mm",
        "design_date": PARAMS["design_date"],
        "params": PARAMS,
        "source_step": repo_path(SOURCE_STEP),
        "exact_baseline": repo_path(EXACT_BASELINE) if EXACT_BASELINE.exists() else None,
        "source_geometry": source_summary,
        "variant_geometry": variant_summary,
        "in_memory_variant_geometry": in_memory_variant_summary,
        "exported_variant_geometry": exported_summary,
        "verification": {
            "overall_bbox_size_abs_diff_mm": bbox_size_abs_diff(source_summary["bbox"], variant_summary["bbox"]),
            "in_memory_bbox_size_abs_diff_mm": bbox_size_abs_diff(source_summary["bbox"], in_memory_variant_summary["bbox"]),
            "solid_count": variant_summary["solid_count"],
            "exported_solid_count": exported_summary["solid_count"],
        },
        "source_face_scan": face_scan(source_shape),
        "variant_face_scan": face_scan(exported_variant),
        "outputs": outputs,
    }
    (ARTIFACT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    print(ARTIFACT_DIR / f"{STEM}.step")
    print(ARTIFACT_DIR / f"{STEM}.stl")
    print(ARTIFACT_DIR / "manifest.json")


if __name__ == "__main__":
    main()
