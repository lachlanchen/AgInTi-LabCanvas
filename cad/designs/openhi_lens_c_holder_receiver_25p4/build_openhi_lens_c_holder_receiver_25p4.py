#!/usr/bin/env python3
"""Build a Lens C holder variant with a 25.4 mm nominal female receiver.

This is a surgical proof-of-concept variant from the exact `Lens C holder.step`
B-rep. It preserves the left `Thread BS` solid and the 40 mm Lens C body, fills
the old positive-X 30 mm receiver cavity, then cuts a smaller internal receiver
using a 24.6 mm pilot bore and a 25.4 mm max-diameter thread cutter.
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
STEM = "openhi_lens_c_holder_receiver_25p4"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/Lens C holder.step"
EXACT_REFERENCE = ROOT / "cad/designs/openhi_lens_c_holder_shapr_exact_regen/artifacts/manifest.json"

AXIS_Y = 210.0
AXIS_Z = 600.0
THREAD_OVERLAP = 0.04

PARAMS = {
    "name": STEM,
    "design_date": "2026-07-08",
    "units": "mm",
    "source_step": "cad/extracted/OpenHI_STEP/Lens C holder.step",
    "design_variant": "positive-X female receiver replaced by a 25.4 mm nominal internal thread proof of concept",
    "preserved_left_solid": "Thread BS",
    "modified_body_solid": "T branch head (1)",
    "axis_y_mm": AXIS_Y,
    "axis_z_mm": AXIS_Z,
    "receiver_side": "positive_x",
    "old_receiver_thread_envelope_diameter_mm": 30.2,
    "old_receiver_thread_x_min_mm": 327.35,
    "old_receiver_thread_x_max_mm": 335.9,
    "fill_cylinder_diameter_mm": 32.0,
    "fill_x0_mm": 322.5,
    "fill_length_mm": 17.5,
    "female_nominal_major_diameter_mm": 25.4,
    "female_pilot_bore_diameter_mm": 24.6,
    "female_thread_cutter_max_diameter_mm": 25.4,
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.4,
    "thread_tooth_base_mm": 0.8,
    "thread_runout_extra_length_each_end_mm": 0.4,
    "thread_x0_mm": 327.35,
    "thread_length_mm": 8.55,
    "pilot_bore_x0_mm": 322.0,
    "pilot_bore_length_mm": 18.5,
    "definition_note": "Here 25.4 mm means the nominal internal thread max/major diameter after subtracting the thread cutter. The smooth pilot bore is 24.6 mm.",
    "fit_note": "This is a true-nominal proof of concept. For a looser printed female thread, make a sibling variant with a larger cutter max diameter such as 25.6 or 25.8 mm.",
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


def bbox_size_abs_diff(a: dict[str, Any], b: dict[str, Any]) -> list[float]:
    return [round(abs(a[key] - b[key]), 9) for key in ("xlen", "ylen", "zlen")]


def x_cylinder(diameter: float, length: float, x0: float) -> cq.Workplane:
    return (
        cq.Workplane("YZ")
        .workplane(offset=x0)
        .circle(diameter / 2.0)
        .extrude(length)
        .translate((0, AXIS_Y, AXIS_Z))
    )


def x_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
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
    return thread.intersect(x_clip_box(sweep_x0, sweep_length, cutter_max + 4.0)).translate((0, AXIS_Y, AXIS_Z))


def build_variant() -> tuple[cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane, cq.Workplane]:
    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    solids = source_shape.Solids()
    if len(solids) != 2:
        raise ValueError(f"expected 2 solids in Lens C holder source, got {len(solids)}")
    thread_bs = solids[0]
    body = solids[1]
    fill = x_cylinder(PARAMS["fill_cylinder_diameter_mm"], PARAMS["fill_length_mm"], PARAMS["fill_x0_mm"])
    pilot = x_cylinder(
        PARAMS["female_pilot_bore_diameter_mm"],
        PARAMS["pilot_bore_length_mm"],
        PARAMS["pilot_bore_x0_mm"],
    )
    thread = female_thread_cutter()
    modified_body = cq.Workplane().add(body).union(fill).cut(pilot).cut(thread)
    assembly = cq.Workplane().add(thread_bs).add(modified_body.val())
    return assembly, modified_body, fill, pilot, thread


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
    lines = [
        "# OpenHI Lens C Holder Receiver 25.4",
        "",
        "This is a sibling proof-of-concept variant of the exact Lens C holder regeneration. It keeps the left `Thread BS` solid unchanged, fills the old positive-X receiver, then cuts a new nominal 25.4 mm female/internal receiver.",
        "",
        "## Thread Definition",
        "",
        f"- Nominal female major/max diameter: `{params['female_nominal_major_diameter_mm']} mm`",
        f"- Smooth pilot bore before thread subtraction: `{params['female_pilot_bore_diameter_mm']} mm`",
        f"- Thread cutter max diameter: `{params['female_thread_cutter_max_diameter_mm']} mm`",
        f"- Pitch: `{params['thread_pitch_mm']} mm`",
        f"- Tooth height: `{params['thread_tooth_height_mm']} mm`",
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
        f"- Preserved left solid bbox: `{variant['solids'][0]['bbox']['xlen']} x {variant['solids'][0]['bbox']['ylen']} x {variant['solids'][0]['bbox']['zlen']} mm`",
        f"- Export round-trip bbox difference: `{manifest['verification']['overall_bbox_size_abs_diff_mm']} mm`",
        f"- Left thread export bbox difference: `{manifest['verification']['left_thread_bs_export_bbox_size_abs_diff_mm']} mm`",
        "",
        "The left `Thread BS` solid is reused unchanged by construction. STEP export and re-import can slightly expand reported B-rep tolerance boxes; this build treats differences under 0.01 mm as preserved for the proof of concept.",
        "",
        "## Build Method",
        "",
        "1. Import `Lens C holder.step`.",
        "2. Keep solid 0 (`Thread BS`) unchanged.",
        "3. Union a 32 mm fill cylinder into solid 1 over the old positive-X receiver.",
        "4. Cut a 24.6 mm smooth pilot bore.",
        "5. Subtract a 25.4 mm max-diameter helical thread cutter.",
        "6. Recombine the preserved `Thread BS` solid with the modified body.",
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
            "cad/.conda/cad-python/bin/python cad/designs/openhi_lens_c_holder_receiver_25p4/build_openhi_lens_c_holder_receiver_25p4.py",
            "blender --background --python cad/designs/openhi_lens_c_holder_receiver_25p4/render_openhi_lens_c_holder_receiver_25p4.py",
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
    assembly, modified_body, fill, pilot, thread = build_variant()

    paths = {
        "assembly_step": ARTIFACT_DIR / f"{STEM}.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "modified_body_step": ARTIFACT_DIR / f"{STEM}_modified_body.step",
        "modified_body_stl": ARTIFACT_DIR / f"{STEM}_modified_body.stl",
        "fill_cylinder_step": ARTIFACT_DIR / f"{STEM}_old_receiver_fill_cylinder.step",
        "pilot_bore_cutter_step": ARTIFACT_DIR / f"{STEM}_pilot_bore_cutter.step",
        "thread_cutter_step": ARTIFACT_DIR / f"{STEM}_female_thread_cutter_25p4.step",
        "inspection_cutaway_step": ARTIFACT_DIR / f"{STEM}_inspection_cutaway.step",
        "inspection_cutaway_stl": ARTIFACT_DIR / f"{STEM}_inspection_cutaway.stl",
    }
    exporters.export(assembly, str(paths["assembly_step"]))
    exporters.export(assembly, str(paths["assembly_stl"]))
    exporters.export(modified_body, str(paths["modified_body_step"]))
    exporters.export(modified_body, str(paths["modified_body_stl"]))
    exporters.export(fill, str(paths["fill_cylinder_step"]))
    exporters.export(pilot, str(paths["pilot_bore_cutter_step"]))
    exporters.export(thread, str(paths["thread_cutter_step"]))

    # Re-import the exported assembly for verification. Direct CadQuery compound
    # wrappers can report inflated tolerance boxes, while the written STEP keeps
    # the intended source-size envelope.
    variant_shape = cq.importers.importStep(str(paths["assembly_step"])).val()
    cutaway = make_inspection_cutaway(variant_shape)
    exporters.export(cutaway, str(paths["inspection_cutaway_step"]))
    exporters.export(cutaway, str(paths["inspection_cutaway_stl"]))
    source_summary = shape_summary(source_shape)
    variant_summary = shape_summary(variant_shape)
    source_left_bbox = source_summary["solids"][0]["bbox"]
    variant_left_bbox = variant_summary["solids"][0]["bbox"]
    overall_bbox_size_diff = bbox_size_abs_diff(source_summary["bbox"], variant_summary["bbox"])
    left_bbox_size_diff = bbox_size_abs_diff(source_left_bbox, variant_left_bbox)

    manifest = {
        "name": STEM,
        "params": PARAMS,
        "exact_reference_manifest": repo_path(EXACT_REFERENCE),
        "source_geometry": source_summary,
        "variant_geometry": variant_summary,
        "modified_body_geometry": shape_summary(modified_body.val()),
        "verification": {
            "solid_count_preserved": len(variant_shape.Solids()) == 2,
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
