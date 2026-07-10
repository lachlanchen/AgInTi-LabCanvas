#!/usr/bin/env python3
"""Build a small double-ended connector for the 30 mm cage rods."""

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
STEM = "cage_rod_connector_13mm_diaphragm"
TOOLS_DIR = ROOT / "cad" / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "design_intent": "Double-ended printed connector for nominal 6 mm cage rods, matching the 6.4 mm rod socket fit used in the current sample-holder design.",
    "reference_fit": "cad/designs/cage_sample_holder_two_piece_lock_slide_petri35 uses 6.4 mm blind rod sockets for nominal 6 mm rods.",
    "outer_diameter_mm": 13.0,
    "total_height_mm": 13.0,
    "rod_nominal_diameter_mm": 6.0,
    "rod_socket_diameter_mm": 6.4,
    "top_socket_depth_mm": 5.0,
    "bottom_socket_depth_mm": 5.0,
    "center_diaphragm_thickness_mm": 3.0,
    "actual_radial_wall_mm": 3.3,
    "wall_note": "13.0 mm OD with a 6.4 mm rod socket gives 3.3 mm radial wall. A strict 2.0 mm wall would imply 10.4 mm OD.",
    "end_edge_chamfer_mm": 0.35,
    "print_orientation": "Print upright on either flat end. Both ends are symmetric.",
    "print_grid_rows": 3,
    "print_grid_cols": 3,
    "print_grid_pitch_mm": 20.0,
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float, vertices: int = 128) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def build_connector() -> cq.Workplane:
    p = PARAMS
    total_h = p["total_height_mm"]
    socket_d = p["rod_socket_diameter_mm"]
    top_depth = p["top_socket_depth_mm"]
    bottom_depth = p["bottom_socket_depth_mm"]

    part = z_cylinder(p["outer_diameter_mm"], total_h, 0.0)
    part = part.cut(z_cylinder(socket_d, bottom_depth + 0.1, -0.05, vertices=96))
    part = part.cut(z_cylinder(socket_d, top_depth + 0.1, total_h - top_depth - 0.05, vertices=96))

    # Chamfer only the exposed end edges. Keep the blind-pocket bottoms flat so
    # the 3 mm central diaphragm remains easy to measure in section.
    chamfer = p["end_edge_chamfer_mm"]
    if chamfer > 0:
        part = part.faces(">Z").edges().chamfer(chamfer)
        part = part.faces("<Z").edges().chamfer(chamfer)
    return part


def build_rod_proxy(z_min: float, length: float) -> cq.Workplane:
    return z_cylinder(PARAMS["rod_nominal_diameter_mm"], length, z_min, vertices=96)


def build_assembly() -> cq.Assembly:
    p = PARAMS
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_connector(), name="13mm_double_rod_connector", color=cq.Color(0.16, 0.16, 0.15, 1.0))
    assembly.add(build_rod_proxy(-18.0, 23.0), name="lower_6mm_rod_proxy", color=cq.Color(0.1, 0.45, 0.9, 0.42))
    assembly.add(
        build_rod_proxy(p["total_height_mm"] - p["top_socket_depth_mm"], 23.0),
        name="upper_6mm_rod_proxy",
        color=cq.Color(0.1, 0.45, 0.9, 0.42),
    )
    return assembly


def build_print_layout() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_print_layout")
    assembly.add(build_connector(), name="upright_connector_print_body", color=cq.Color(0.16, 0.16, 0.15, 1.0))
    return assembly


def build_3x3_print_grid() -> cq.Assembly:
    p = PARAMS
    assembly = cq.Assembly(name=f"{STEM}_3x3_print_grid")
    rows = int(p["print_grid_rows"])
    cols = int(p["print_grid_cols"])
    pitch = p["print_grid_pitch_mm"]
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col + 1
            x = (col - (cols - 1) / 2.0) * pitch
            y = (row - (rows - 1) / 2.0) * pitch
            assembly.add(
                build_connector().translate((x, y, 0)),
                name=f"upright_connector_{index:02d}_print_body",
                color=cq.Color(0.16, 0.16, 0.15, 1.0),
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
    scale = 24.0
    pad = 54.0
    legend_w = 500
    od = p["outer_diameter_mm"]
    total_h = p["total_height_mm"]
    socket_d = p["rod_socket_diameter_mm"]
    top_depth = p["top_socket_depth_mm"]
    bottom_depth = p["bottom_socket_depth_mm"]
    svg_w = int(od * scale + pad * 2 + legend_w)
    svg_h = int(total_h * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + od / 2.0) * scale

    def sy(z: float) -> float:
        return pad + (total_h - z) * scale

    def rect(x0: float, z0: float, x1: float, z1: float, fill: str, stroke: str, dashed: bool = False) -> str:
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        return (
            f'<rect x="{sx(x0):.2f}" y="{sy(z1):.2f}" width="{(x1 - x0) * scale:.2f}" '
            f'height="{(z1 - z0) * scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>'
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        rect(-od / 2.0, 0, od / 2.0, total_h, "#f7fafc", "#1a202c"),
        rect(-socket_d / 2.0, 0, socket_d / 2.0, bottom_depth, "#ffffff", "#3182ce"),
        rect(-socket_d / 2.0, total_h - top_depth, socket_d / 2.0, total_h, "#ffffff", "#3182ce"),
        rect(-socket_d / 2.0, bottom_depth, socket_d / 2.0, total_h - top_depth, "rgba(221,107,32,0.22)", "#dd6b20"),
        f'<line x1="{sx(0):.2f}" y1="{sy(0):.2f}" x2="{sx(0):.2f}" y2="{sy(total_h):.2f}" stroke="#718096" stroke-width="1" stroke-dasharray="5 4"/>',
    ]
    legend_x = pad + od * scale + 40
    legend = [
        "Cage rod connector section",
        f"Outer cylinder: OD {od:.1f} mm x H {total_h:.1f} mm",
        f"Top/bottom rod pockets: {socket_d:.1f} mm diameter x {top_depth:.1f} mm deep",
        f"Center diaphragm: {p['center_diaphragm_thickness_mm']:.1f} mm solid web",
        f"Nominal rods: {p['rod_nominal_diameter_mm']:.1f} mm; print-fit socket: {socket_d:.1f} mm",
        f"Actual radial wall: {p['actual_radial_wall_mm']:.1f} mm",
        "Print upright on either flat end.",
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
        f"""# Cage Rod Connector, 13 mm With Center Diaphragm

This is a new clean parametric connector for the 30 mm cage system rods. It is
intended to join two nominal 6 mm rods from opposite sides using the same
printed rod fit that worked well in the two-piece sample holder.

## Geometry

- Outer body: `{p['outer_diameter_mm']} mm` diameter x `{p['total_height_mm']} mm` high.
- Top pocket: `{p['rod_socket_diameter_mm']} mm` diameter x `{p['top_socket_depth_mm']} mm` deep.
- Bottom pocket: `{p['rod_socket_diameter_mm']} mm` diameter x `{p['bottom_socket_depth_mm']} mm` deep.
- Center diaphragm: `{p['center_diaphragm_thickness_mm']} mm` solid material between the two blind pockets.
- Actual radial wall: `{p['actual_radial_wall_mm']} mm`.

## Fit Notes

The rod pockets use `{p['rod_socket_diameter_mm']} mm`, matching the current cage holder's rod socket clearance for nominal `{p['rod_nominal_diameter_mm']} mm` rods.
With a `{p['outer_diameter_mm']} mm` outer diameter, the radial wall is `{p['actual_radial_wall_mm']} mm`; a strict 2 mm wall would require an outer diameter near `10.4 mm`.

## Print Notes

Print the connector upright on either flat end. The part is symmetric. The
`assembly` files include transparent rod proxies for checking only; print the
single connector STEP/STL.

For batch printing, use the root `PRINT_THIS_*_3x3_print_grid` files. They
contain nine upright connectors on a `{p['print_grid_pitch_mm']} mm` center
pitch, with no rod proxy geometry.

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
        "connector_step": ARTIFACT_DIR / f"{STEM}.step",
        "connector_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "assembly_step": ARTIFACT_DIR / f"{STEM}_assembly.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}_assembly.stl",
        "print_layout_step": ARTIFACT_DIR / f"{STEM}_print_layout.step",
        "print_layout_stl": ARTIFACT_DIR / f"{STEM}_print_layout.stl",
        "print_grid_step": ARTIFACT_DIR / f"{STEM}_3x3_print_grid.step",
        "print_grid_stl": ARTIFACT_DIR / f"{STEM}_3x3_print_grid.stl",
        "print_grid_3mf": ARTIFACT_DIR / f"{STEM}_3x3_print_grid.3mf",
        "section_svg": ARTIFACT_DIR / f"{STEM}_section.svg",
        "section_png": ARTIFACT_DIR / f"{STEM}_section.png",
        "render_png": ARTIFACT_DIR / f"{STEM}_render.png",
        "assembly_render_png": ARTIFACT_DIR / f"{STEM}_assembly_render.png",
        "blender_scene": ARTIFACT_DIR / f"{STEM}.blend",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }

    export_part(build_connector(), paths["connector_step"], paths["connector_stl"])
    export_assembly(build_assembly(), paths["assembly_step"], paths["assembly_stl"])
    export_assembly(build_print_layout(), paths["print_layout_step"], paths["print_layout_stl"])
    export_assembly(build_3x3_print_grid(), paths["print_grid_step"], paths["print_grid_stl"])
    export_stl_as_3mf(paths["print_grid_stl"], paths["print_grid_3mf"], title=f"{STEM} 3x3 print grid")
    write_section_svg(paths["section_svg"])
    svg_to_png(paths["section_svg"], paths["section_png"])

    use_this = DESIGN_DIR / f"USE_THIS_{STEM}.step"
    print_this_step = DESIGN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid.step"
    print_this_stl = DESIGN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid.stl"
    print_this_3mf = DESIGN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid.3mf"
    use_this.write_bytes(paths["connector_step"].read_bytes())
    print_this_step.write_bytes(paths["print_grid_step"].read_bytes())
    print_this_stl.write_bytes(paths["print_grid_stl"].read_bytes())
    print_this_3mf.write_bytes(paths["print_grid_3mf"].read_bytes())

    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["use_this_step"] = repo_path(use_this)
    outputs["print_this_3x3_step"] = repo_path(print_this_step)
    outputs["print_this_3x3_stl"] = repo_path(print_this_stl)
    outputs["print_this_3x3_3mf"] = repo_path(print_this_3mf)
    outputs["manifest"] = repo_path(paths["manifest"])
    write_manifest(paths["manifest"], outputs)
    write_readme(DESIGN_DIR / "README.md", outputs)
    print(json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
