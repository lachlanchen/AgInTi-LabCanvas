#!/usr/bin/env python3
"""Build a Lens B holder variant with a 30.0 mm pilot and 30.4 mm groove receiver.

This is a surgical variant from the exact `Lens B holder.step` B-rep. It keeps
the body, side holes, oblique sink, lower bore, and outer envelope intact, fills
only the old positive-Z OpenHI 30 mm female receiver, then re-cuts a tighter
30.0/30.4 mm print-fit receiver with the adjusted lens-side chamfer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_lens_b_holder_receiver_30p0_30p4_print_fit"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/Lens B holder.step"
EXACT_REFERENCE = ROOT / "cad/designs/openhi_lens_b_holder_shapr_exact_regen/artifacts/manifest.json"

AXIS_X = 254.633
AXIS_Y = 210.0
THREAD_OVERLAP = 0.04

PARAMS = {
    "name": STEM,
    "design_date": "2026-07-08",
    "units": "mm",
    "source_step": "cad/extracted/OpenHI_STEP/Lens B holder.step",
    "source_shapr": "/home/lachlan/Downloads/Nature.shapr",
    "design_variant": "positive-Z OpenHI female receiver replaced by 30.0 mm pilot plus 30.4 mm groove print-fit thread",
    "axis_x_mm": AXIS_X,
    "axis_y_mm": AXIS_Y,
    "receiver_side": "positive_z",
    "old_receiver_thread_envelope_diameter_mm": 30.2,
    "old_receiver_thread_z_min_mm": 652.35,
    "old_receiver_thread_z_max_mm": 660.1,
    "fill_cylinder_diameter_mm": 32.0,
    "fill_z0_mm": 650.0,
    "fill_length_mm": 10.1,
    "preserved_lens_seat_diameter_mm": 25.5,
    "preserved_lens_seat_z_min_mm": 649.6,
    "preserved_lens_seat_z_max_mm": 650.0,
    "transition_chamfer_start_z_mm": 650.0,
    "transition_chamfer_start_diameter_mm": 25.5,
    "transition_chamfer_end_diameter_mm": 30.0,
    "transition_chamfer_length_mm": 2.25,
    "transition_chamfer_end_z_mm": 652.25,
    "transition_chamfer_angle_deg": 45.0,
    "female_groove_max_diameter_mm": 30.4,
    "female_pilot_bore_diameter_mm": 30.0,
    "female_thread_cutter_max_diameter_mm": 30.4,
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.2,
    "thread_tooth_base_mm": 0.8,
    "thread_runout_extra_length_each_end_mm": 0.4,
    "thread_z0_mm": 652.25,
    "thread_length_mm": 7.85,
    "pilot_bore_z0_mm": 652.25,
    "pilot_bore_length_mm": 7.85,
    "definition_note": "This is not a C-mount conversion. It keeps the OpenHI 30 mm family and tightens the positive-Z female receiver from the old 30.2 mm start/root to a 30.0 mm pilot, with a 30.4 mm groove cutter. The lens-side 25.5 mm seat is preserved and the 45 degree chamfer is shortened to land on the new 30.0 mm pilot.",
    "fit_note": "Use this when the old 30.2 mm female receiver is too loose on the newer printer. If it is too tight, make a sibling with a 30.1 or 30.2 mm pilot and/or a 30.5 mm cutter.",
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
        .translate((AXIS_X, AXIS_Y, 0))
    )


def z_frustum(start_diameter: float, end_diameter: float, length: float, z0: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .workplane(offset=z0)
        .circle(start_diameter / 2.0)
        .workplane(offset=length)
        .circle(end_diameter / 2.0)
        .loft(combine=True)
        .translate((AXIS_X, AXIS_Y, 0))
    )


def z_clip_box(z0: float, length: float, span: float) -> cq.Workplane:
    return cq.Workplane("XY").box(span, span, length, centered=(True, True, False)).translate((0, 0, z0))


def female_thread_cutter() -> cq.Workplane:
    """Create the Z-axis thread cutter by rotating the stable X-axis helix.

    A directly constructed Z-axis helix cuts correctly in memory but can export
    to STEP as a split body plus a loose cutter-like fragment. The X-axis helix
    construction has proven stable in the Lens C variant; rotating it into the
    Lens B Z-axis frame keeps the exported STEP as one connected solid.
    """
    pitch = PARAMS["thread_pitch_mm"]
    height = PARAMS["thread_tooth_height_mm"]
    base = PARAMS["thread_tooth_base_mm"]
    extra = PARAMS["thread_runout_extra_length_each_end_mm"]
    cutter_max = PARAMS["female_thread_cutter_max_diameter_mm"]
    root_d = cutter_max - 2.0 * height
    z0 = PARAMS["thread_z0_mm"]
    length = PARAMS["thread_length_mm"]
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
    clip = (
        cq.Workplane("XY")
        .box(sweep_length, cutter_max + 4.0, cutter_max + 4.0, centered=(False, True, True))
        .translate((sweep_z0, 0, 0))
    )
    return (
        thread.intersect(clip)
        .rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((AXIS_X, AXIS_Y, 0))
    )


def build_variant() -> tuple[cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane]:
    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    if len(source_shape.Solids()) != 1:
        raise ValueError(f"expected 1 solid in Lens B holder source, got {len(source_shape.Solids())}")

    fill = z_cylinder(PARAMS["fill_cylinder_diameter_mm"], PARAMS["fill_length_mm"], PARAMS["fill_z0_mm"])
    chamfer = z_frustum(
        PARAMS["transition_chamfer_start_diameter_mm"],
        PARAMS["transition_chamfer_end_diameter_mm"],
        PARAMS["transition_chamfer_length_mm"],
        PARAMS["transition_chamfer_start_z_mm"],
    )
    pilot = z_cylinder(
        PARAMS["female_pilot_bore_diameter_mm"],
        PARAMS["pilot_bore_length_mm"],
        PARAMS["pilot_bore_z0_mm"],
    )
    thread = female_thread_cutter()
    modified_body = cq.Workplane().add(source_shape).union(fill).cut(chamfer).cut(pilot).cut(thread)
    return modified_body, fill, chamfer, pilot, thread, cq.Workplane().add(source_shape)


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
    cut = shape.intersect(keep_box.val())
    if cut.Volume() <= 1e-6:
        raise ValueError("inspection cutaway produced no usable volume")
    return cq.Workplane().add(cut)


def write_readme(manifest: dict[str, Any]) -> None:
    params = manifest["params"]
    outputs = manifest["outputs"]
    source = manifest["source_geometry"]
    variant = manifest["variant_geometry"]
    lines = [
        "# OpenHI Lens B Holder Receiver 30.0/30.4 Print Fit",
        "",
        "This is a sibling variant of the exact Lens B holder regeneration. It keeps the original STEP-derived body and changes only the positive-Z OpenHI female receiver from the old 30.2 mm start/root to a tighter 30.0 mm pilot with a 30.4 mm groove cutter.",
        "",
        "## Thread Definition",
        "",
        f"- Female smooth pilot/start diameter: `{params['female_pilot_bore_diameter_mm']} mm`",
        f"- Female groove/thread-cutter max diameter: `{params['female_thread_cutter_max_diameter_mm']} mm`",
        f"- Preserved lens seat: `{params['preserved_lens_seat_diameter_mm']} mm`, z `{params['preserved_lens_seat_z_min_mm']} to {params['preserved_lens_seat_z_max_mm']} mm`",
        f"- Rebuilt transition chamfer: `{params['transition_chamfer_start_diameter_mm']} -> {params['transition_chamfer_end_diameter_mm']} mm` over `{params['transition_chamfer_length_mm']} mm`",
        f"- Pitch: `{params['thread_pitch_mm']} mm`",
        f"- Tooth height, radial: `{params['thread_tooth_height_mm']} mm`",
        f"- Tooth base: `{params['thread_tooth_base_mm']} mm`",
        f"- Runout extra at each end: `{params['thread_runout_extra_length_each_end_mm']} mm`",
        "",
        params["definition_note"],
        "",
        "## Geometry Summary",
        "",
        f"- Source bbox: `{source['bbox']['xlen']} x {source['bbox']['ylen']} x {source['bbox']['zlen']} mm`",
        f"- Variant bbox: `{variant['bbox']['xlen']} x {variant['bbox']['ylen']} x {variant['bbox']['zlen']} mm`",
        f"- Source solids: `{source['solid_count']}`",
        f"- Variant solids: `{variant['solid_count']}`",
        f"- Export round-trip bbox difference: `{manifest['verification']['overall_bbox_size_abs_diff_mm']} mm`",
        "",
        "The source is a single imported B-rep solid from `Lens B holder.step`. STEP export and re-import can shift reported tolerance boxes by microns; this build treats differences under 0.01 mm as preserved.",
        "",
        "## Build Method",
        "",
        "1. Import `Lens B holder.step`.",
        "2. Union a 32 mm fill cylinder into the old positive-Z receiver only.",
        "3. Preserve the 25.5 mm lens seat up to z=650.0 mm.",
        "4. Re-cut a 45 degree transition chamfer from 25.5 mm to 30.0 mm.",
        "5. Cut a 30.0 mm smooth pilot bore from the adjusted chamfer end.",
        "6. Subtract a 30.4 mm max-diameter helical thread cutter.",
        "",
        "The helical cutter is built as a stable X-axis sweep and then rotated into the Lens B Z-axis frame. This avoids a STEP export failure mode where a direct Z-axis helical cutter can leave a loose cutter-like fragment even though the in-memory boolean looks correct.",
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
            "cad/.conda/cad-python/bin/python cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/build_openhi_lens_b_holder_receiver_30p0_30p4_print_fit.py",
            "blender --background --python cad/designs/openhi_lens_b_holder_receiver_30p0_30p4_print_fit/render_openhi_lens_b_holder_receiver_30p0_30p4_print_fit.py",
            "```",
            "",
            "## Fit Note",
            "",
            params["fit_note"],
            "",
        ]
    )
    (DESIGN_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"missing STEP source: {SOURCE_STEP}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    variant, fill, chamfer, pilot, thread, source_workplane = build_variant()

    paths = {
        "assembly_step": ARTIFACT_DIR / f"{STEM}.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "fill_cylinder_step": ARTIFACT_DIR / f"{STEM}_old_receiver_fill_cylinder.step",
        "transition_chamfer_cutter_step": ARTIFACT_DIR / f"{STEM}_transition_chamfer_cutter.step",
        "pilot_bore_cutter_step": ARTIFACT_DIR / f"{STEM}_pilot_bore_cutter.step",
        "thread_cutter_step": ARTIFACT_DIR / f"{STEM}_female_thread_cutter_30p4.step",
        "source_copy_step": ARTIFACT_DIR / f"{STEM}_source_copy.step",
    }
    exporters.export(variant, str(paths["assembly_step"]))
    exporters.export(variant, str(paths["assembly_stl"]))
    exporters.export(fill, str(paths["fill_cylinder_step"]))
    exporters.export(chamfer, str(paths["transition_chamfer_cutter_step"]))
    exporters.export(pilot, str(paths["pilot_bore_cutter_step"]))
    exporters.export(thread, str(paths["thread_cutter_step"]))
    exporters.export(source_workplane, str(paths["source_copy_step"]))

    variant_shape = cq.importers.importStep(str(paths["assembly_step"])).val()

    source_summary = shape_summary(source_shape)
    variant_summary = shape_summary(variant_shape)
    overall_bbox_size_diff = bbox_size_abs_diff(source_summary["bbox"], variant_summary["bbox"])
    manifest = {
        "name": STEM,
        "params": PARAMS,
        "exact_reference_manifest": repo_path(EXACT_REFERENCE),
        "source_geometry": source_summary,
        "variant_geometry": variant_summary,
        "verification": {
            "solid_count_preserved": len(variant_shape.Solids()) == 1,
            "overall_bbox_size_abs_diff_mm": overall_bbox_size_diff,
            "overall_bbox_within_0p01_mm": max(overall_bbox_size_diff) < 0.01,
            "source_body_reused_by_construction": True,
            "step_round_trip_note": "The source Lens B body is reused and edited only in the positive-Z receiver region. Exported STEP re-import can shift reported tolerance bboxes by a few microns.",
        },
        "outputs": {
            **{key: repo_path(path) for key, path in paths.items()},
            "render_png": repo_path(ARTIFACT_DIR / f"{STEM}_render.png"),
            "thread_detail_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_thread_detail_render.png"),
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
