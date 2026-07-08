#!/usr/bin/env python3
"""Build a clean Lens C holder 30.0/30.4 mm receiver variant.

The previous proof-of-concept filled the old threaded receiver and then cut a
new one. That preserved the envelope, but the old receiver B-rep could leave
small internal sliver faces in Shapr3D. This variant trims the source body at
the lens-seat plane and rebuilds the positive-X receiver as clean geometry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_BSplineSurface, GeomAbs_Cylinder, GeomAbs_Plane
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_lens_c_holder_receiver_30p0_30p4_clean_rebuild"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/Lens C holder.step"
OLD_VARIANT = ROOT / "cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit"

AXIS_Y = 210.0
AXIS_Z = 600.0
THREAD_OVERLAP = 0.04

PARAMS: dict[str, Any] = {
    "name": STEM,
    "design_date": "2026-07-08",
    "units": "mm",
    "source_step": "cad/extracted/OpenHI_STEP/Lens C holder.step",
    "previous_variant": "cad/designs/openhi_lens_c_holder_receiver_30p0_30p4_print_fit",
    "design_variant": "clean positive-X OpenHI female receiver rebuilt from the lens-seat plane",
    "preserved_left_solid": "Thread BS",
    "trimmed_body_solid": "T branch head (1)",
    "axis_y_mm": AXIS_Y,
    "axis_z_mm": AXIS_Z,
    "trim_x_mm": 325.0,
    "outer_receiver_diameter_mm": 40.0,
    "outer_receiver_x0_mm": 325.0,
    "outer_receiver_length_mm": 15.0,
    "preserved_lens_seat_diameter_mm": 25.5,
    "preserved_lens_seat_x_min_mm": 324.5,
    "preserved_lens_seat_x_max_mm": 325.0,
    "transition_chamfer_start_x_mm": 325.0,
    "transition_chamfer_start_diameter_mm": 25.5,
    "transition_chamfer_end_diameter_mm": 30.0,
    "transition_chamfer_length_mm": 2.25,
    "transition_chamfer_end_x_mm": 327.25,
    "female_pilot_bore_diameter_mm": 30.0,
    "female_pilot_bore_x0_mm": 327.25,
    "female_pilot_bore_length_mm": 12.75,
    "female_thread_cutter_max_diameter_mm": 30.4,
    "female_groove_max_diameter_mm": 30.4,
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.2,
    "thread_tooth_base_mm": 0.8,
    "thread_runout_extra_length_each_end_mm": 0.4,
    "thread_x0_mm": 327.25,
    "thread_length_mm": 8.65,
    "thread_x1_mm": 335.9,
    "front_mouth_chamfer_x0_mm": 336.0,
    "front_mouth_chamfer_start_diameter_mm": 30.0,
    "front_mouth_chamfer_end_diameter_mm": 40.0,
    "front_mouth_chamfer_length_mm": 4.0,
    "method_note": (
        "Trim the imported body at x=325.0, preserve the 25.5 mm lens seat, "
        "then union a new clean receiver. The helical cutter is swept with "
        "half-pitch runout but clipped to x=327.25..335.9, so no tooth crosses "
        "into the lens-side chamfer. The front mouth chamfer starts at x=336.0 "
        "after the full threaded section."
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
    solids = []
    for index, solid in enumerate(shape.Solids()):
        solids.append(
            {
                "index": index,
                "bbox": bbox_dict(solid),
                "face_count": len(solid.Faces()),
                "shell_count": len(solid.Shells()),
                "volume_mm3": round(solid.Volume(), 9),
            }
        )
    return {
        "bbox": bbox_dict(shape),
        "solid_count": len(shape.Solids()),
        "shell_count": len(shape.Shells()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "volume_mm3": round(shape.Volume(), 9),
        "area_mm2": round(shape.Area(), 9),
        "solids": solids,
    }


def bbox_size_abs_diff(a: dict[str, Any], b: dict[str, Any]) -> list[float]:
    return [round(abs(a[key] - b[key]), 9) for key in ("xlen", "ylen", "zlen")]


def face_bbox(face: cq.Face) -> dict[str, Any]:
    bb = face.BoundingBox()
    return {
        "min": [round(bb.xmin, 9), round(bb.ymin, 9), round(bb.zmin, 9)],
        "max": [round(bb.xmax, 9), round(bb.ymax, 9), round(bb.zmax, 9)],
        "size": [round(bb.xlen, 9), round(bb.ylen, 9), round(bb.zlen, 9)],
    }


def receiver_face_scan(shape: cq.Shape) -> dict[str, Any]:
    """Scan receiver faces for old internal-shell signatures."""
    faces: list[dict[str, Any]] = []
    exposed_32mm_shell_faces: list[dict[str, Any]] = []
    prethread_bspline_faces: list[dict[str, Any]] = []
    thread_bspline_faces: list[dict[str, Any]] = []
    exp = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    index = 0
    while exp.More():
        face = cq.Face(TopoDS.Face_s(exp.Current()))
        surface = BRepAdaptor_Surface(face.wrapped, True)
        bbox = face_bbox(face)
        item: dict[str, Any] = {
            "index": index,
            "type": str(face.geomType()).lower(),
            "area_mm2": round(face.Area(), 9),
            "bbox": bbox,
        }
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            item["diameter_mm"] = round(cylinder.Radius() * 2.0, 9)
            if (
                31.8 <= item["diameter_mm"] <= 32.2
                and bbox["max"][0] >= PARAMS["outer_receiver_x0_mm"]
            ):
                exposed_32mm_shell_faces.append(item)
        if surface.GetType() == GeomAbs_BSplineSurface:
            if bbox["max"][0] >= PARAMS["transition_chamfer_start_x_mm"]:
                if bbox["min"][0] < PARAMS["thread_x0_mm"] - 1e-6:
                    prethread_bspline_faces.append(item)
                elif bbox["max"][0] <= PARAMS["thread_x1_mm"] + 1e-6:
                    thread_bspline_faces.append(item)
        if surface.GetType() in {GeomAbs_BSplineSurface, GeomAbs_Cylinder, GeomAbs_Plane}:
            if bbox["max"][0] >= PARAMS["transition_chamfer_start_x_mm"]:
                faces.append(item)
        index += 1
        exp.Next()
    return {
        "receiver_relevant_faces": faces,
        "thread_bspline_faces": thread_bspline_faces,
        "prethread_bspline_faces": prethread_bspline_faces,
        "exposed_32mm_shell_faces": exposed_32mm_shell_faces,
        "clean_receiver_checks": {
            "no_exposed_32mm_fill_shell": len(exposed_32mm_shell_faces) == 0,
            "no_bspline_before_thread_start": len(prethread_bspline_faces) == 0,
            "thread_bspline_face_count": len(thread_bspline_faces),
        },
    }


def x_cylinder(diameter: float, length: float, x0: float) -> cq.Workplane:
    return (
        cq.Workplane("YZ")
        .workplane(offset=x0)
        .circle(diameter / 2.0)
        .extrude(length)
        .translate((0, AXIS_Y, AXIS_Z))
    )


def x_frustum(start_diameter: float, end_diameter: float, length: float, x0: float) -> cq.Workplane:
    return (
        cq.Workplane("YZ")
        .workplane(offset=x0)
        .circle(start_diameter / 2.0)
        .workplane(offset=length)
        .circle(end_diameter / 2.0)
        .loft(combine=True)
        .translate((0, AXIS_Y, AXIS_Z))
    )


def keep_xmax_box(xmax: float, shape: cq.Shape) -> cq.Workplane:
    bb = shape.BoundingBox()
    x0 = bb.xmin - 10.0
    length = xmax - x0
    return (
        cq.Workplane("XY")
        .box(length, bb.ylen + 20.0, bb.zlen + 20.0, centered=(False, True, True))
        .translate((x0, (bb.ymin + bb.ymax) / 2.0, (bb.zmin + bb.zmax) / 2.0))
    )


def x_thread_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
    return cq.Workplane("XY").box(length, span, span, centered=(False, True, True)).translate((x0, 0, 0))


def female_thread_cutter() -> cq.Workplane:
    pitch = PARAMS["thread_pitch_mm"]
    height = PARAMS["thread_tooth_height_mm"]
    base = PARAMS["thread_tooth_base_mm"]
    extra = PARAMS["thread_runout_extra_length_each_end_mm"]
    cutter_max = PARAMS["female_thread_cutter_max_diameter_mm"]
    root_d = cutter_max - 2.0 * height
    x0 = PARAMS["thread_x0_mm"]
    length = PARAMS["thread_length_mm"]
    sweep_x0 = x0 - extra
    sweep_length = length + 2.0 * extra
    root_r = root_d / 2.0 - THREAD_OVERLAP
    path = cq.Wire.makeHelix(
        pitch,
        sweep_length,
        root_r,
        center=(sweep_x0, 0, 0),
        dir=(1, 0, 0),
        lefthand=True,
    )
    profile = (
        cq.Workplane("XY")
        .center(sweep_x0, root_r)
        .polyline([(0, 0), (base / 2.0, height + THREAD_OVERLAP), (base, 0)])
        .close()
    )
    thread = profile.sweep(path, isFrenet=True, combine=False)
    thread = thread.intersect(x_thread_clip_box(x0, length, cutter_max + 4.0))
    return thread.translate((0, AXIS_Y, AXIS_Z))


def make_clean_receiver() -> tuple[cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane]:
    outer = x_cylinder(
        PARAMS["outer_receiver_diameter_mm"],
        PARAMS["outer_receiver_length_mm"],
        PARAMS["outer_receiver_x0_mm"],
    )
    transition_chamfer = x_frustum(
        PARAMS["transition_chamfer_start_diameter_mm"],
        PARAMS["transition_chamfer_end_diameter_mm"],
        PARAMS["transition_chamfer_length_mm"],
        PARAMS["transition_chamfer_start_x_mm"],
    )
    pilot = x_cylinder(
        PARAMS["female_pilot_bore_diameter_mm"],
        PARAMS["female_pilot_bore_length_mm"],
        PARAMS["female_pilot_bore_x0_mm"],
    )
    front_mouth = x_frustum(
        PARAMS["front_mouth_chamfer_start_diameter_mm"],
        PARAMS["front_mouth_chamfer_end_diameter_mm"],
        PARAMS["front_mouth_chamfer_length_mm"],
        PARAMS["front_mouth_chamfer_x0_mm"],
    )
    thread = female_thread_cutter()
    receiver = outer.cut(transition_chamfer).cut(thread).cut(pilot).cut(front_mouth).clean()
    return receiver, outer, transition_chamfer, pilot, thread, front_mouth


def build_variant() -> tuple[cq.Workplane, cq.Workplane, cq.Workplane, dict[str, cq.Workplane]]:
    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    solids = source_shape.Solids()
    if len(solids) != 2:
        raise ValueError(f"expected 2 solids in Lens C holder source, got {len(solids)}")
    thread_bs = solids[0]
    body = solids[1]
    trim_box = keep_xmax_box(PARAMS["trim_x_mm"], body)
    trimmed_body = body.intersect(trim_box.val())
    receiver, outer, transition_chamfer, pilot, thread, front_mouth = make_clean_receiver()
    modified_body = cq.Workplane().add(trimmed_body).union(receiver).clean()
    assembly = cq.Workplane().add(thread_bs).add(modified_body.val())
    parts = {
        "trimmed_body": cq.Workplane().add(trimmed_body),
        "clean_receiver_body": receiver,
        "receiver_outer_blank": outer,
        "transition_chamfer_cutter": transition_chamfer,
        "pilot_bore_cutter": pilot,
        "thread_cutter": thread,
        "front_mouth_chamfer_cutter": front_mouth,
    }
    return assembly, modified_body, cq.Workplane().add(thread_bs), parts


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
    params = manifest["params"]
    outputs = manifest["outputs"]
    source = manifest["source_geometry"]
    variant = manifest["variant_geometry"]
    checks = manifest["receiver_face_scan"]["clean_receiver_checks"]
    lines = [
        "# OpenHI Lens C Holder Receiver 30.0/30.4 Clean Rebuild",
        "",
        "This sibling variant fixes the messy receiver in the earlier proof-of-concept. The old version filled the original female thread and then re-cut it, which could leave a small internal shell/sliver inside the thread. This version trims the old receiver away at the lens-seat plane and rebuilds the positive-X receiver as clean geometry.",
        "",
        "## Thread Definition",
        "",
        f"- Female smooth pilot/start diameter: `{params['female_pilot_bore_diameter_mm']} mm`",
        f"- Female groove/thread-cutter max diameter: `{params['female_thread_cutter_max_diameter_mm']} mm`",
        f"- Preserved lens seat: `{params['preserved_lens_seat_diameter_mm']} mm`, x `{params['preserved_lens_seat_x_min_mm']} to {params['preserved_lens_seat_x_max_mm']} mm`",
        f"- Rebuilt lens-side chamfer: `{params['transition_chamfer_start_diameter_mm']} -> {params['transition_chamfer_end_diameter_mm']} mm` over `{params['transition_chamfer_length_mm']} mm`",
        f"- Threaded section: x `{params['thread_x0_mm']} to {params['thread_x1_mm']} mm`",
        f"- Pitch: `{params['thread_pitch_mm']} mm`; tooth height: `{params['thread_tooth_height_mm']} mm`; tooth base: `{params['thread_tooth_base_mm']} mm`",
        f"- Front mouth lead-in: `{params['front_mouth_chamfer_start_diameter_mm']} -> {params['front_mouth_chamfer_end_diameter_mm']} mm`, x `{params['front_mouth_chamfer_x0_mm']} to 340.0 mm`",
        "",
        "## Clean-Rebuild Method",
        "",
        "1. Import `Lens C holder.step`.",
        "2. Preserve the left `Thread BS` solid unchanged.",
        "3. Trim the main body at x=325.0 mm, preserving the lens seat up to that plane.",
        "4. Build a new 40 mm OD receiver blank from x=325.0 to 340.0 mm.",
        "5. Cut the lens-side 25.5 -> 30.0 mm chamfer.",
        "6. Cut the bounded 30.4 mm helical thread cutter.",
        "7. Cut the 30.0 mm pilot bore and front mouth lead-in.",
        "8. Union the clean receiver to the trimmed body.",
        "",
        params["method_note"],
        "",
        "## Validation",
        "",
        f"- Source bbox: `{source['bbox']['xlen']} x {source['bbox']['ylen']} x {source['bbox']['zlen']} mm`",
        f"- Variant bbox: `{variant['bbox']['xlen']} x {variant['bbox']['ylen']} x {variant['bbox']['zlen']} mm`",
        f"- Source solids: `{source['solid_count']}`; variant solids: `{variant['solid_count']}`",
        f"- Modified body solids: `{manifest['modified_body_geometry']['solid_count']}`",
        f"- No exposed 32 mm fill-shell face: `{checks['no_exposed_32mm_fill_shell']}`",
        f"- No B-spline before thread start: `{checks['no_bspline_before_thread_start']}`",
        f"- Thread B-spline face count: `{checks['thread_bspline_face_count']}`",
        f"- Overall bbox size difference from source: `{manifest['verification']['overall_bbox_size_abs_diff_mm']} mm`",
        "",
        "The design intentionally changes only the positive-X receiver internals and cleanly rebuilds that end. The front mouth lead-in begins after the full threaded section, so the helical cutter does not cross into the lens-side chamfer.",
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
            f"cad/.conda/cad-python/bin/python cad/designs/{STEM}/build_{STEM}.py",
            f"blender --background --python cad/designs/{STEM}/render_{STEM}.py",
            "```",
            "",
        ]
    )
    (DESIGN_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"missing STEP source: {SOURCE_STEP}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    assembly, modified_body, thread_bs, parts = build_variant()

    paths = {
        "assembly_step": ARTIFACT_DIR / f"{STEM}.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "modified_body_step": ARTIFACT_DIR / f"{STEM}_modified_body.step",
        "modified_body_stl": ARTIFACT_DIR / f"{STEM}_modified_body.stl",
        "preserved_thread_bs_step": ARTIFACT_DIR / f"{STEM}_preserved_thread_bs.step",
        "trimmed_body_step": ARTIFACT_DIR / f"{STEM}_trimmed_body.step",
        "clean_receiver_body_step": ARTIFACT_DIR / f"{STEM}_clean_receiver_body.step",
        "receiver_outer_blank_step": ARTIFACT_DIR / f"{STEM}_receiver_outer_blank.step",
        "transition_chamfer_cutter_step": ARTIFACT_DIR / f"{STEM}_transition_chamfer_cutter.step",
        "pilot_bore_cutter_step": ARTIFACT_DIR / f"{STEM}_pilot_bore_cutter.step",
        "thread_cutter_step": ARTIFACT_DIR / f"{STEM}_female_thread_cutter_30p4.step",
        "front_mouth_chamfer_cutter_step": ARTIFACT_DIR / f"{STEM}_front_mouth_chamfer_cutter.step",
        "inspection_cutaway_step": ARTIFACT_DIR / f"{STEM}_inspection_cutaway.step",
        "inspection_cutaway_stl": ARTIFACT_DIR / f"{STEM}_inspection_cutaway.stl",
    }

    exporters.export(assembly, str(paths["assembly_step"]))
    exporters.export(assembly, str(paths["assembly_stl"]))
    exporters.export(modified_body, str(paths["modified_body_step"]))
    exporters.export(modified_body, str(paths["modified_body_stl"]))
    exporters.export(thread_bs, str(paths["preserved_thread_bs_step"]))
    for key, part in parts.items():
        export_key = f"{key}_step"
        if export_key in paths:
            exporters.export(part, str(paths[export_key]))

    variant_shape = cq.importers.importStep(str(paths["assembly_step"])).val()
    modified_shape = cq.importers.importStep(str(paths["modified_body_step"])).val()
    cutaway = make_inspection_cutaway(variant_shape)
    exporters.export(cutaway, str(paths["inspection_cutaway_step"]))
    exporters.export(cutaway, str(paths["inspection_cutaway_stl"]))

    source_summary = shape_summary(source_shape)
    variant_summary = shape_summary(variant_shape)
    modified_summary = shape_summary(modified_shape)
    overall_bbox_size_diff = bbox_size_abs_diff(source_summary["bbox"], variant_summary["bbox"])
    left_bbox_size_diff = bbox_size_abs_diff(source_summary["solids"][0]["bbox"], variant_summary["solids"][0]["bbox"])

    manifest = {
        "name": STEM,
        "params": PARAMS,
        "old_variant": repo_path(OLD_VARIANT),
        "source_geometry": source_summary,
        "variant_geometry": variant_summary,
        "modified_body_geometry": modified_summary,
        "receiver_face_scan": receiver_face_scan(modified_shape),
        "verification": {
            "solid_count_preserved": len(variant_shape.Solids()) == 2,
            "modified_body_is_single_solid": len(modified_shape.Solids()) == 1,
            "left_thread_bs_reused_unchanged_by_construction": True,
            "overall_bbox_size_abs_diff_mm": overall_bbox_size_diff,
            "overall_bbox_within_0p01_mm": max(overall_bbox_size_diff) < 0.01,
            "left_thread_bs_export_bbox_size_abs_diff_mm": left_bbox_size_diff,
            "left_thread_bs_export_bbox_within_0p01_mm": max(left_bbox_size_diff) < 0.01,
            "step_round_trip_note": "The left Thread BS solid is reused from the source model. Exported STEP re-import can shift reported tolerance bboxes by a few microns.",
        },
        "outputs": {
            **{key: repo_path(path) for key, path in paths.items()},
            "render_png": repo_path(ARTIFACT_DIR / f"{STEM}_render.png"),
            "receiver_detail_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_receiver_detail_render.png"),
            "inspection_cutaway_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_inspection_cutaway_render.png"),
            "blend": repo_path(ARTIFACT_DIR / f"{STEM}.blend"),
            "manifest_json": repo_path(ARTIFACT_DIR / "manifest.json"),
        },
    }
    (ARTIFACT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    print(paths["assembly_step"])
    print(paths["assembly_stl"])
    print(ARTIFACT_DIR / "manifest.json")


if __name__ == "__main__":
    main()
