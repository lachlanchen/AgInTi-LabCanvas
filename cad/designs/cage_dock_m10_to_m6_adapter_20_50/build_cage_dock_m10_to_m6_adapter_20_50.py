#!/usr/bin/env python3
"""Build a stepped adapter for a printed 10 mm dock hole to a 6 mm cage rod."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_dock_m10_to_m6_adapter_20_50"
TOOLS_DIR = ROOT / "cad" / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "design_intent": "Smooth stepped adapter for the printed dock that has 10 mm rod holes, converting the hole to a 50 mm tall nominal 6 mm cage rod.",
    "dock_context": "The printed dock ended around 25 mm tall with about 20 mm usable blind-hole depth. The lower insert is therefore 20 mm long.",
    "bottom_nominal_m10_diameter_mm": 10.0,
    "bottom_print_fit_diameter_mm": 9.8,
    "bottom_insert_length_mm": 20.0,
    "upper_nominal_m6_diameter_mm": 6.0,
    "upper_rod_length_mm": 50.0,
    "total_height_mm": 70.0,
    "lead_in_chamfer_mm": 0.35,
    "top_chamfer_mm": 0.35,
    "print_grid_rows": 2,
    "print_grid_cols": 2,
    "print_grid_pitch_mm": 24.0,
    "print_orientation": "Print upright on the wider 9.8 mm lower insert end. The 2x2 grid contains four independent adapters.",
    "fit_note": "M10 is treated as a smooth 10 mm-class insert, not a modeled screw thread. The lower diameter is 9.8 mm so it can slip into a printed 10 mm dock hole more reliably.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float, vertices: int = 128) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def build_adapter() -> cq.Workplane:
    p = PARAMS
    lower = z_cylinder(p["bottom_print_fit_diameter_mm"], p["bottom_insert_length_mm"], 0.0)
    upper = z_cylinder(
        p["upper_nominal_m6_diameter_mm"],
        p["upper_rod_length_mm"],
        p["bottom_insert_length_mm"],
        vertices=128,
    )
    part = lower.union(upper)
    part = part.faces("<Z").edges().chamfer(p["lead_in_chamfer_mm"])
    part = part.faces(">Z").edges().chamfer(p["top_chamfer_mm"])
    return part


def build_2x2_print_grid() -> cq.Assembly:
    p = PARAMS
    rows = int(p["print_grid_rows"])
    cols = int(p["print_grid_cols"])
    pitch = p["print_grid_pitch_mm"]
    assembly = cq.Assembly(name=f"{STEM}_2x2_print_grid")
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col + 1
            x = (col - (cols - 1) / 2.0) * pitch
            y = (row - (rows - 1) / 2.0) * pitch
            assembly.add(
                build_adapter().translate((x, y, 0)),
                name=f"m10_to_m6_adapter_{index:02d}",
                color=cq.Color(0.15, 0.15, 0.14, 1.0),
            )
    return assembly


def export_part(part: cq.Workplane, step_path: Path, stl_path: Path) -> None:
    exporters.export(part, str(step_path))
    exporters.export(part, str(stl_path))


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    compound = assembly.toCompound()
    exporters.export(compound, str(step_path))
    exporters.export(compound, str(stl_path))


def write_section_svg(path: Path) -> None:
    p = PARAMS
    scale = 9.0
    pad = 54.0
    legend_w = 560
    max_d = p["bottom_nominal_m10_diameter_mm"]
    h = p["total_height_mm"]
    lower_d = p["bottom_print_fit_diameter_mm"]
    upper_d = p["upper_nominal_m6_diameter_mm"]
    lower_h = p["bottom_insert_length_mm"]
    svg_w = int(max_d * scale + pad * 2 + legend_w)
    svg_h = int(h * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + max_d / 2.0) * scale

    def sy(z: float) -> float:
        return pad + (h - z) * scale

    def rect(x0: float, z0: float, x1: float, z1: float, fill: str, stroke: str) -> str:
        return (
            f'<rect x="{sx(x0):.2f}" y="{sy(z1):.2f}" width="{(x1 - x0) * scale:.2f}" '
            f'height="{(z1 - z0) * scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        rect(-lower_d / 2.0, 0, lower_d / 2.0, lower_h, "#edf2f7", "#1a202c"),
        rect(-upper_d / 2.0, lower_h, upper_d / 2.0, h, "#f7fafc", "#1a202c"),
        f'<line x1="{sx(0):.2f}" y1="{sy(0):.2f}" x2="{sx(0):.2f}" y2="{sy(h):.2f}" stroke="#718096" stroke-width="1" stroke-dasharray="5 4"/>',
        f'<line x1="{sx(-lower_d/2):.2f}" y1="{sy(lower_h):.2f}" x2="{sx(lower_d/2):.2f}" y2="{sy(lower_h):.2f}" stroke="#dd6b20" stroke-width="2"/>',
    ]
    legend_x = pad + max_d * scale + 42
    legend = [
        "M10-hole to M6-rod dock adapter",
        f"Lower insert: {lower_d:.1f} mm diameter x {lower_h:.1f} mm long",
        f"Nominal target hole: {p['bottom_nominal_m10_diameter_mm']:.1f} mm printed dock hole",
        f"Upper rod: {upper_d:.1f} mm diameter x {p['upper_rod_length_mm']:.1f} mm tall",
        f"Total height: {h:.1f} mm",
        "M10/M6 labels mean smooth diameter class here, not screw threads.",
        "Print upright on the wider lower insert end.",
    ]
    for index, row in enumerate(legend):
        size = 17 if index == 0 else 13
        weight = "700" if index == 0 else "400"
        lines.append(
            f'<text x="{legend_x:.2f}" y="{pad + index * 25:.2f}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def svg_to_png(svg: Path, png: Path) -> None:
    if subprocess.run(["which", "convert"], capture_output=True, text=True).returncode != 0:
        return
    subprocess.run(["convert", str(svg), str(png)], check=True)


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
        f"""# Cage Dock M10-Hole To M6-Rod Adapter

This adapter compensates for the already-printed dock that has `10 mm` rod
holes. It is a smooth stepped cylinder: a short lower insert for the dock hole
and a longer upper 6 mm cage rod.

## Geometry

- Lower insert: `{p['bottom_print_fit_diameter_mm']} mm` diameter x `{p['bottom_insert_length_mm']} mm` long.
- Target dock hole: nominal `{p['bottom_nominal_m10_diameter_mm']} mm`.
- Upper rod: `{p['upper_nominal_m6_diameter_mm']} mm` diameter x `{p['upper_rod_length_mm']} mm` long.
- Total height: `{p['total_height_mm']} mm`.
- Grid: `{p['print_grid_rows']} x {p['print_grid_cols']}` adapters on `{p['print_grid_pitch_mm']} mm` pitch.

## Fit Notes

`M10` and `M6` are used as smooth diameter classes here, not modeled screw
threads. The lower insert is intentionally `0.2 mm` smaller than the nominal
10 mm dock hole so it is more likely to slip into the printed hole. The bottom
edge has a small chamfer to help insertion.

## Print Notes

Use the root `PRINT_THIS_*_2x2_print_grid` files for direct slicing. They
contain four upright adapters with no extra reference bodies.

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
        "adapter_step": ARTIFACT_DIR / f"{STEM}.step",
        "adapter_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "print_grid_step": ARTIFACT_DIR / f"{STEM}_2x2_print_grid.step",
        "print_grid_stl": ARTIFACT_DIR / f"{STEM}_2x2_print_grid.stl",
        "print_grid_3mf": ARTIFACT_DIR / f"{STEM}_2x2_print_grid.3mf",
        "section_svg": ARTIFACT_DIR / f"{STEM}_section.svg",
        "section_png": ARTIFACT_DIR / f"{STEM}_section.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }

    export_part(build_adapter(), paths["adapter_step"], paths["adapter_stl"])
    export_assembly(build_2x2_print_grid(), paths["print_grid_step"], paths["print_grid_stl"])
    export_stl_as_3mf(paths["print_grid_stl"], paths["print_grid_3mf"], title=f"{STEM} 2x2 print grid")
    write_section_svg(paths["section_svg"])
    svg_to_png(paths["section_svg"], paths["section_png"])

    use_this = DESIGN_DIR / f"USE_THIS_{STEM}.step"
    print_this_step = DESIGN_DIR / f"PRINT_THIS_{STEM}_2x2_print_grid.step"
    print_this_stl = DESIGN_DIR / f"PRINT_THIS_{STEM}_2x2_print_grid.stl"
    print_this_3mf = DESIGN_DIR / f"PRINT_THIS_{STEM}_2x2_print_grid.3mf"
    use_this.write_bytes(paths["adapter_step"].read_bytes())
    print_this_step.write_bytes(paths["print_grid_step"].read_bytes())
    print_this_stl.write_bytes(paths["print_grid_stl"].read_bytes())
    print_this_3mf.write_bytes(paths["print_grid_3mf"].read_bytes())

    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["use_this_step"] = repo_path(use_this)
    outputs["print_this_2x2_step"] = repo_path(print_this_step)
    outputs["print_this_2x2_stl"] = repo_path(print_this_stl)
    outputs["print_this_2x2_3mf"] = repo_path(print_this_3mf)
    outputs["manifest"] = repo_path(paths["manifest"])
    write_manifest(paths["manifest"], outputs)
    write_readme(DESIGN_DIR / "README.md", outputs)
    print(json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
