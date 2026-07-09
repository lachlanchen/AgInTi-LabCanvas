#!/usr/bin/env python3
"""Build a Shapr3D-friendly OpenHI A+C+BS receiver variant.

The source Shapr file stores this body as an imported Parasolid/STEP body, not
as a replayable feature tree. The robust path is therefore to preserve the
original exported body and replace only the fragile receiver/thread zones.

This builder keeps the original OpenHI A+C+BS outer body, BS slope, lens seat,
pin holes, and chamfers. It adds clean analytic sleeves inside the two 30 mm
receiver regions, cuts 30.0 mm pilots, and optionally adds simple 30.4 mm
ring-groove previews. The ring grooves deliberately replace helical B-spline
thread faces because those are what made Shapr3D repair slowly, drop threads,
or show transparent broken faces.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
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
STEM = "openhi_a_c_bs_receivers_30p0_30p4_print_fit"
SOURCE_STEP = ROOT / "cad/extracted/OpenHI_STEP/A+ C + BS.step"
SOURCE_SHAPR = ROOT / "cad/extracted/OpenHI.shapr"

SURFACE_NAMES = {
    GeomAbs_Plane: "plane",
    GeomAbs_Cylinder: "cylinder",
    GeomAbs_Cone: "cone",
    GeomAbs_BSplineSurface: "bspline",
    GeomAbs_Torus: "torus",
}

PARAMS: dict[str, Any] = {
    "name": STEM,
    "design_date": "2026-07-09",
    "units": "mm",
    "source_step": "cad/extracted/OpenHI_STEP/A+ C + BS.step",
    "source_shapr": "cad/extracted/OpenHI.shapr",
    "builder": "source_body_with_clean_receiver_sleeves",
    "origin_note": "Coordinates preserve the original OpenHI exported placement.",
    "preserved_original_geometry": [
        "outer 40 mm vertical body",
        "outer 40 mm BS-side cylinder",
        "BS slope and slot faces",
        "24 mm center bore",
        "25.5 mm lens seat",
        "side pin holes",
        "oblique BS-frame holes",
        "original chamfers outside the receiver repair zones",
    ],
    "lower_receiver_repair": {
        "axis": "Z",
        "center_x": 255.0,
        "center_y": 210.0,
        "sleeve_z0": 539.55,
        "sleeve_length": 8.25,
        "sleeve_outer_diameter": 31.4,
        "pilot_diameter": 30.0,
        "ring_preview_groove_diameter": 30.4,
        "ring_preview_pitch": 0.8,
        "ring_preview_width": 0.28,
        "ring_preview_start_offset": 0.32,
        "ring_preview_end_margin": 0.18,
    },
    "bs_receiver_repair": {
        "axis": "X",
        "center_y": 210.0,
        "center_z": 600.0,
        "sleeve_x0": 270.0,
        "sleeve_length": 5.0,
        "sleeve_outer_diameter": 31.4,
        "pilot_diameter": 30.0,
        "ring_preview_groove_diameter": 30.4,
        "ring_preview_pitch": 0.8,
        "ring_preview_width": 0.28,
        "ring_preview_start_offset": 0.22,
        "ring_preview_end_margin": 0.18,
    },
    "thread_policy": (
        "The original STEP contains helical B-spline thread faces. This variant "
        "removes those fragile faces from the two repaired receiver zones. The "
        "default STEP has simple ring-groove previews; the smooth STEP has no "
        "thread preview and is the safest file for Shapr editing or physical tapping."
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


def surface_type_counts(shape: cq.Shape) -> dict[str, int]:
    exp = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    counts: Counter[str] = Counter()
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        surface = BRepAdaptor_Surface(face, True)
        surface_type: GeomAbs_SurfaceType = surface.GetType()
        counts[SURFACE_NAMES.get(surface_type, str(surface_type))] += 1
        exp.Next()
    return dict(sorted(counts.items()))


def shape_summary(shape: cq.Shape) -> dict[str, Any]:
    return {
        "bbox": bbox_dict(shape),
        "solid_count": len(shape.Solids()),
        "face_count": len(shape.Faces()),
        "edge_count": len(shape.Edges()),
        "volume_mm3": round(shape.Volume(), 9),
        "area_mm2": round(shape.Area(), 9),
        "surface_type_counts": surface_type_counts(shape),
        "occt_valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
    }


def z_cylinder(diameter: float, length: float, z0: float) -> cq.Workplane:
    lower = PARAMS["lower_receiver_repair"]
    return (
        cq.Workplane("XY")
        .workplane(offset=z0)
        .circle(diameter / 2.0)
        .extrude(length)
        .translate((lower["center_x"], lower["center_y"], 0))
    )


def x_cylinder(diameter: float, length: float, x0: float) -> cq.Workplane:
    bs = PARAMS["bs_receiver_repair"]
    return (
        cq.Workplane("YZ")
        .workplane(offset=x0)
        .circle(diameter / 2.0)
        .extrude(length)
        .translate((0, bs["center_y"], bs["center_z"]))
    )


def tube_z(outer_diameter: float, inner_diameter: float, length: float, z0: float) -> cq.Workplane:
    return z_cylinder(outer_diameter, length, z0).cut(
        z_cylinder(inner_diameter, length + 0.2, z0 - 0.1)
    )


def tube_x(outer_diameter: float, inner_diameter: float, length: float, x0: float) -> cq.Workplane:
    return x_cylinder(outer_diameter, length, x0).cut(
        x_cylinder(inner_diameter, length + 0.2, x0 - 0.1)
    )


def keep_largest_solid(body: cq.Workplane) -> cq.Workplane:
    solids = body.val().Solids()
    if len(solids) <= 1:
        return body
    largest = max(solids, key=lambda solid: solid.Volume())
    return cq.Workplane().add(largest)


def make_lower_sleeve() -> cq.Workplane:
    lower = PARAMS["lower_receiver_repair"]
    return tube_z(
        lower["sleeve_outer_diameter"],
        lower["pilot_diameter"],
        lower["sleeve_length"],
        lower["sleeve_z0"],
    )


def make_bs_sleeve() -> cq.Workplane:
    bs = PARAMS["bs_receiver_repair"]
    return tube_x(
        bs["sleeve_outer_diameter"],
        bs["pilot_diameter"],
        bs["sleeve_length"],
        bs["sleeve_x0"],
    )


def make_lower_ring_cutters() -> list[cq.Workplane]:
    lower = PARAMS["lower_receiver_repair"]
    cutters = []
    z = lower["sleeve_z0"] + lower["ring_preview_start_offset"]
    z_stop = lower["sleeve_z0"] + lower["sleeve_length"] - lower["ring_preview_end_margin"]
    while z <= z_stop:
        cutters.append(z_cylinder(lower["ring_preview_groove_diameter"], lower["ring_preview_width"], z))
        z += lower["ring_preview_pitch"]
    return cutters


def make_bs_ring_cutters() -> list[cq.Workplane]:
    bs = PARAMS["bs_receiver_repair"]
    cutters = []
    x = bs["sleeve_x0"] + bs["ring_preview_start_offset"]
    x_stop = bs["sleeve_x0"] + bs["sleeve_length"] - bs["ring_preview_end_margin"]
    while x <= x_stop:
        cutters.append(x_cylinder(bs["ring_preview_groove_diameter"], bs["ring_preview_width"], x))
        x += bs["ring_preview_pitch"]
    return cutters


def make_compound(parts: list[cq.Workplane]) -> cq.Workplane:
    return cq.Workplane().add(cq.Compound.makeCompound([part.val() for part in parts]))


def build_smooth(source: cq.Shape) -> cq.Workplane:
    lower = PARAMS["lower_receiver_repair"]
    bs = PARAMS["bs_receiver_repair"]
    body = cq.Workplane().add(source)

    # These sleeves intentionally overlap the old helical receiver surfaces.
    # The final clean pilot cuts define the actual 30.0 mm openings.
    body = body.union(make_lower_sleeve())
    body = body.cut(
        z_cylinder(lower["pilot_diameter"], lower["sleeve_length"] + 0.4, lower["sleeve_z0"] - 0.2)
    )
    body = body.union(make_bs_sleeve())
    body = body.cut(
        x_cylinder(bs["pilot_diameter"], bs["sleeve_length"] + 0.4, bs["sleeve_x0"] - 0.2)
    )
    return keep_largest_solid(body)


def add_ring_thread_preview(smooth: cq.Workplane) -> tuple[cq.Workplane, cq.Workplane, cq.Workplane]:
    body = smooth
    lower_cutters = make_lower_ring_cutters()
    bs_cutters = make_bs_ring_cutters()
    for cutter in lower_cutters + bs_cutters:
        body = body.cut(cutter)
    return keep_largest_solid(body), make_compound(lower_cutters), make_compound(bs_cutters)


def build() -> dict[str, cq.Workplane]:
    source = cq.importers.importStep(str(SOURCE_STEP)).val()
    smooth = build_smooth(source)
    threaded_preview, lower_ring_cutters, bs_ring_cutters = add_ring_thread_preview(smooth)
    return {
        "smooth_editable": smooth,
        "modified": threaded_preview,
        "lower_receiver_healing_sleeve": make_lower_sleeve(),
        "bs_receiver_healing_sleeve": make_bs_sleeve(),
        "lower_ring_groove_cutters": lower_ring_cutters,
        "bs_ring_groove_cutters": bs_ring_cutters,
    }


def export_all(parts: dict[str, cq.Workplane]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for stale in ARTIFACT_DIR.glob(f"{STEM}*.step"):
        stale.unlink()
    for stale in ARTIFACT_DIR.glob(f"{STEM}*.stl"):
        stale.unlink()

    for key, part in parts.items():
        if key == "modified":
            step_path = ARTIFACT_DIR / f"{STEM}.step"
            stl_path = ARTIFACT_DIR / f"{STEM}.stl"
            out_prefix = "assembly"
        else:
            step_path = ARTIFACT_DIR / f"{STEM}_{key}.step"
            stl_path = step_path.with_suffix(".stl")
            out_prefix = key
        exporters.export(part, str(step_path))
        outputs[f"{out_prefix}_step"] = repo_path(step_path)
        if key in {"modified", "smooth_editable"}:
            exporters.export(part, str(stl_path))
            outputs[f"{out_prefix}_stl"] = repo_path(stl_path)

    outputs["render_png"] = repo_path(ARTIFACT_DIR / f"{STEM}_render.png")
    outputs["receiver_detail_render_png"] = repo_path(ARTIFACT_DIR / f"{STEM}_receiver_detail_render.png")
    outputs["blend"] = repo_path(ARTIFACT_DIR / f"{STEM}.blend")
    outputs["manifest_json"] = repo_path(ARTIFACT_DIR / "manifest.json")
    return outputs


def write_readme(manifest: dict[str, Any]) -> None:
    source = manifest["source_geometry"]
    assembly = manifest["assembly_geometry"]
    smooth = manifest["smooth_geometry"]
    outputs = manifest["outputs"]
    lines = [
        "# OpenHI A+C+BS Shapr-Friendly 30.0/30.4 Print Fit",
        "",
        "This folder contains a Shapr-friendly print-fit variant of the OpenHI A+C+BS receiver body. It keeps the original exported STEP body and replaces only the fragile receiver/thread zones with clean analytic sleeves.",
        "",
        "## Why This Rebuild Exists",
        "",
        "The earlier edited STEP was OCCT-valid, but Shapr3D spent a long time repairing it and then dropped thread faces or showed transparent broken regions. The problem was the combination of imported helical B-spline thread faces and local boolean edits near the BS pocket.",
        "",
        "This version does not approximate the whole BS body. It preserves the original outer body, BS slope/slot area, lens seat, pin holes, and chamfers, then heals only the two 30 mm receiver zones. The default file uses simple ring-groove thread previews. The smooth file has no thread preview and is the safest one for Shapr editing or physical tapping.",
        "",
        "## Geometry Basis",
        "",
        f"- Original source bbox: `{source['bbox']['xlen']} x {source['bbox']['ylen']} x {source['bbox']['zlen']} mm`",
        f"- Rebuilt bbox: `{assembly['bbox']['xlen']} x {assembly['bbox']['ylen']} x {assembly['bbox']['zlen']} mm`",
        f"- Rebuilt solids: `{assembly['solid_count']}`; OCCT valid: `{assembly['occt_valid']}`",
        f"- Smooth editable solids: `{smooth['solid_count']}`; OCCT valid: `{smooth['occt_valid']}`",
        f"- Original surface counts: `{source['surface_type_counts']}`",
        f"- Rebuilt surface counts: `{assembly['surface_type_counts']}`",
        f"- Smooth editable surface counts: `{smooth['surface_type_counts']}`",
        "- Fit change: receiver pilots use `30.0 mm`; ring-groove previews cut to `30.4 mm`.",
        "- Thread policy: original helical B-spline thread faces are removed from the repaired receiver zones for Shapr import stability.",
        "",
        "## Recommended Files",
        "",
        f"- Shapr import with visible ring-groove preview: `{outputs['assembly_step']}`",
        f"- Shapr edit/tap-ready smooth version: `{outputs['smooth_editable_step']}`",
        f"- Sleeve references: `{outputs['lower_receiver_healing_sleeve_step']}`, `{outputs['bs_receiver_healing_sleeve_step']}`",
        f"- Ring cutter references: `{outputs['lower_ring_groove_cutters_step']}`, `{outputs['bs_ring_groove_cutters_step']}`",
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
    parts = build()
    outputs = export_all(parts)

    source_shape = cq.importers.importStep(str(SOURCE_STEP)).val()
    assembly_shape = parts["modified"].val()
    smooth_shape = parts["smooth_editable"].val()
    manifest = {
        "name": STEM,
        "units": "mm",
        "design_date": PARAMS["design_date"],
        "params": PARAMS,
        "source_step": repo_path(SOURCE_STEP),
        "source_shapr": repo_path(SOURCE_SHAPR) if SOURCE_SHAPR.exists() else None,
        "source_geometry": shape_summary(source_shape),
        "assembly_geometry": shape_summary(assembly_shape),
        "smooth_geometry": shape_summary(smooth_shape),
        "outputs": outputs,
    }
    (ARTIFACT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_readme(manifest)
    print(ARTIFACT_DIR / f"{STEM}.step")
    print(ARTIFACT_DIR / f"{STEM}_smooth_editable.step")
    print(ARTIFACT_DIR / "manifest.json")


if __name__ == "__main__":
    main()
