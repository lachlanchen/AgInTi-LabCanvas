#!/usr/bin/env python3
"""Build Shapr-friendly 50 mm rods for the 30 mm cage system."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_rods_50mm_m6"


PARAMS = {
    "name": STEM,
    "design_intent": "Simple 50 mm long, 6 mm diameter cage rods for the standard 30 mm cage square.",
    "rod_length_mm": 50.0,
    "rod_diameter_mm": 6.0,
    "rod_radius_mm": 3.0,
    "cage_pitch_mm": 30.0,
    "rod_centers_mm": [[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]],
    "m3_pilot_diameter_mm": 2.6,
    "m3_pilot_depth_each_end_mm": 8.0,
    "end_chamfer_mm": 0.35,
    "print_spacing_mm": 12.0,
    "shapr_friendly_note": "No helical threads or B-spline faces. The M6 wording here is treated as a 6 mm cage rod diameter. Use real metal M6 threaded rod if a true screw thread is required.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def rod_body(with_m3_pilots: bool = False) -> cq.Workplane:
    p = PARAMS
    rod = cq.Workplane("XY").circle(p["rod_radius_mm"]).extrude(p["rod_length_mm"])
    rod = rod.faces(">Z").edges().chamfer(p["end_chamfer_mm"])
    rod = rod.faces("<Z").edges().chamfer(p["end_chamfer_mm"])
    if not with_m3_pilots:
        return rod

    pilot = (
        cq.Workplane("XY")
        .circle(p["m3_pilot_diameter_mm"] / 2.0)
        .extrude(p["m3_pilot_depth_each_end_mm"] + 0.1)
    )
    rod = rod.cut(pilot.translate((0, 0, -0.05)))
    top_pilot = pilot.translate((0, 0, p["rod_length_mm"] - p["m3_pilot_depth_each_end_mm"]))
    rod = rod.cut(top_pilot)
    return rod


def horizontal_rod(with_m3_pilots: bool = False) -> cq.Workplane:
    return rod_body(with_m3_pilots).rotate((0, 0, 0), (0, 1, 0), 90)


def cage_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    for index, (x, y) in enumerate(PARAMS["rod_centers_mm"], start=1):
        body = rod_body(False).translate((x, y, 0))
        assembly.add(body, name=f"smooth_m6_cage_rod_{index}_50mm", color=cq.Color(0.72, 0.72, 0.68, 1.0))
    return assembly


def print_layout() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_print_layout")
    spacing = PARAMS["print_spacing_mm"]
    for index in range(4):
        body = horizontal_rod(False).translate((0, (index - 1.5) * spacing, PARAMS["rod_diameter_mm"] / 2.0))
        assembly.add(body, name=f"smooth_m6_cage_rod_{index + 1}_horizontal", color=cq.Color(0.72, 0.72, 0.68, 1.0))
    return assembly


def export_part(part: cq.Workplane, step_path: Path, stl_path: Path) -> None:
    exporters.export(part, str(step_path))
    exporters.export(part, str(stl_path))


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    compound = assembly.toCompound()
    exporters.export(compound, str(step_path))
    exporters.export(compound, str(stl_path))


def write_svg(path: Path) -> None:
    p = PARAMS
    scale = 7.0
    pad = 42
    legend_w = 540
    board = 56
    svg_w = int(board * scale + pad * 2 + legend_w)
    svg_h = int(116 * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + board / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (board / 2.0 - y) * scale

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{pad}" y="28" font-family="Arial" font-size="18" font-weight="700" fill="#1a202c">50 mm M6 Cage Rod Set</text>',
        f'<rect x="{sx(-15):.2f}" y="{sy(15):.2f}" width="{30*scale:.2f}" height="{30*scale:.2f}" fill="none" stroke="#805ad5" stroke-width="2" stroke-dasharray="6 5"/>',
    ]
    for x, y in p["rod_centers_mm"]:
        lines.append(
            f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{p["rod_radius_mm"]*scale:.2f}" fill="#edf2f7" stroke="#2d3748" stroke-width="2"/>'
        )
    side_x = pad
    side_y = pad + 82 * scale
    rod_w = p["rod_length_mm"] * scale
    rod_h = p["rod_diameter_mm"] * scale
    lines.extend(
        [
            f'<text x="{side_x}" y="{side_y - 18}" font-family="Arial" font-size="14" fill="#1a202c">Side view of one rod</text>',
            f'<rect x="{side_x}" y="{side_y}" width="{rod_w}" height="{rod_h}" rx="{rod_h/2}" fill="#edf2f7" stroke="#2d3748" stroke-width="2"/>',
            f'<line x1="{side_x}" y1="{side_y + rod_h + 16}" x2="{side_x + rod_w}" y2="{side_y + rod_h + 16}" stroke="#2d3748" stroke-width="1.5"/>',
            f'<text x="{side_x + rod_w/2 - 28}" y="{side_y + rod_h + 35}" font-family="Arial" font-size="13" fill="#1a202c">50 mm</text>',
            f'<text x="{side_x + rod_w + 16}" y="{side_y + rod_h/2 + 5}" font-family="Arial" font-size="13" fill="#1a202c">Ø6 mm</text>',
        ]
    )
    legend_x = pad + board * scale + 40
    legend = [
        "Geometry",
        "Four smooth rods on standard 30 mm cage square",
        "Rod length: 50 mm",
        "Rod diameter: 6 mm",
        "Hole centers in assemblies: x/y = +/-15 mm",
        "Optional M3 pilot-hole variant: Ø2.6 mm x 8 mm each end",
        "No modeled screw threads for fast Shapr3D import",
    ]
    for index, row in enumerate(legend):
        size = 17 if index == 0 else 13
        weight = "700" if index == 0 else "400"
        lines.append(
            f'<text x="{legend_x}" y="{pad + 24 * index}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def svg_to_png(svg_path: Path, png_path: Path) -> None:
    if subprocess.run(["which", "convert"], capture_output=True, text=True).returncode != 0:
        return
    subprocess.run(["convert", str(svg_path), str(png_path)], check=True)


def write_manifest(path: Path, outputs: dict[str, str]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": PARAMS["design_intent"],
        "parameters": PARAMS,
        "outputs": outputs,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    p = PARAMS
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in p.items())
    path.write_text(
        f"""# Cage Rods, 50 mm M6 / 6 mm Diameter

This is a new clean parametric rod set for the 30 mm cage geometry. The rods are
`{p['rod_length_mm']} mm` long and `{p['rod_diameter_mm']} mm` diameter, matching
the 6 mm rod pockets used in the current cage holders and dock.

## Geometry

- Rod diameter: `{p['rod_diameter_mm']} mm`.
- Rod length: `{p['rod_length_mm']} mm`.
- Cage placement: four rods at `x/y = ±{p['cage_pitch_mm'] / 2.0} mm`.
- Optional M3 pilot variant: `{p['m3_pilot_diameter_mm']} mm` diameter pilot,
  `{p['m3_pilot_depth_each_end_mm']} mm` deep from each end.

## Shapr3D Import Notes

The direct-use STEP is a smooth rod with analytic cylinder and chamfer faces.
There are no helical threads, no fragile boolean thread cutters, and no B-spline
surfaces. If you need true M6 threads, use a bought metal M6 threaded rod or add
native threads in Shapr3D after import.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "smooth_rod_step": ARTIFACT_DIR / f"{STEM}_smooth_rod.step",
        "smooth_rod_stl": ARTIFACT_DIR / f"{STEM}_smooth_rod.stl",
        "m3_pilot_rod_step": ARTIFACT_DIR / f"{STEM}_m3_pilot_rod.step",
        "m3_pilot_rod_stl": ARTIFACT_DIR / f"{STEM}_m3_pilot_rod.stl",
        "assembly_step": ARTIFACT_DIR / f"{STEM}_four_rod_cage_assembly.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}_four_rod_cage_assembly.stl",
        "print_layout_step": ARTIFACT_DIR / f"{STEM}_four_rod_print_layout.step",
        "print_layout_stl": ARTIFACT_DIR / f"{STEM}_four_rod_print_layout.stl",
        "diagram_svg": ARTIFACT_DIR / f"{STEM}_diagram.svg",
        "diagram_png": ARTIFACT_DIR / f"{STEM}_diagram.png",
        "render_png": ARTIFACT_DIR / f"{STEM}_render.png",
        "assembly_render_png": ARTIFACT_DIR / f"{STEM}_assembly_render.png",
        "blender_scene": ARTIFACT_DIR / f"{STEM}.blend",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }
    export_part(rod_body(False), paths["smooth_rod_step"], paths["smooth_rod_stl"])
    export_part(rod_body(True), paths["m3_pilot_rod_step"], paths["m3_pilot_rod_stl"])
    export_assembly(cage_assembly(), paths["assembly_step"], paths["assembly_stl"])
    export_assembly(print_layout(), paths["print_layout_step"], paths["print_layout_stl"])
    write_svg(paths["diagram_svg"])
    svg_to_png(paths["diagram_svg"], paths["diagram_png"])

    use_this_rod = DESIGN_DIR / f"USE_THIS_{STEM}_smooth_rod.step"
    use_this_pack = DESIGN_DIR / f"USE_THIS_{STEM}_four_rod_cage_assembly.step"
    use_this_rod.write_bytes(paths["smooth_rod_step"].read_bytes())
    use_this_pack.write_bytes(paths["assembly_step"].read_bytes())

    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["use_this_smooth_rod_step"] = repo_path(use_this_rod)
    outputs["use_this_four_rod_assembly_step"] = repo_path(use_this_pack)
    outputs["manifest"] = repo_path(paths["manifest"])
    write_manifest(paths["manifest"], outputs)
    write_readme(DESIGN_DIR / "README.md", outputs)
    print(json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
