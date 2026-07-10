#!/usr/bin/env python3
"""Build a Shapr-friendly dock for standard 30 mm cage rods."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_rod_dock_100mm_base_10mm_holes"


PARAMS = {
    "name": STEM,
    "design_intent": "Simple Shapr3D-friendly dock block for cage rods, using the standard 30 mm cage square geometry.",
    "base_width_mm": 100.0,
    "base_height_mm": 100.0,
    "base_thickness_mm": 30.0,
    "cage_pitch_mm": 30.0,
    "rod_hole_centers_mm": [[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]],
    "rod_hole_diameter_mm": 10.0,
    "rod_hole_depth_mm": 25.0,
    "bottom_floor_thickness_mm": 5.0,
    "rod_proxy_diameter_mm": 6.0,
    "rod_proxy_visible_height_mm": 72.0,
    "edge_chamfer_mm": 1.0,
    "hole_mouth_chamfer_mm": 0.5,
    "anti_warp_ears_enabled": True,
    "anti_warp_ear_style": "four removable 0.5 mm bottom ears with two side pulls plus one diagonal full-corner pull",
    "anti_warp_ear_thickness_mm": 0.5,
    "anti_warp_ear_breakaway_overlap_mm": 0.35,
    "anti_warp_ear_side_contact_width_mm": 4.5,
    "anti_warp_ear_arm_width_mm": 4.0,
    "anti_warp_ear_junction_offset_mm": 9.0,
    "anti_warp_ear_tail_reach_mm": 24.0,
    "anti_warp_ear_tail_width_mm": 16.0,
    "anti_warp_ear_diagonal_neck_width_mm": 5.0,
    "anti_warp_ear_note": "Run-2 adds full-corner anti-warp ears for the broad 100 x 100 mm flat base. Each corner has side pulls plus a diagonal pull so the actual corner is dragged down toward the build plate.",
    "shapr_friendly_note": "No threads, no helix, no B-spline surfaces, and no fragile fill-recut operations. Geometry is a simple box minus four vertical cylinders plus simple 0.5 mm anti-warp tabs.",
    "print_orientation": "Print flat on the 100 x 100 mm base. The four 10 mm blind holes open upward.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def z_poly(points: list[tuple[float, float]], height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).polyline(points).close().extrude(height)


def z_cylinder(diameter: float, height: float, z_min: float, vertices: int = 128) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def anti_warp_corner_ear(sx: int, sy: int) -> cq.Workplane:
    """Build one detachable anti-warp ear at a bottom corner."""
    p = PARAMS
    half_w = p["base_width_mm"] / 2.0
    half_h = p["base_height_mm"] / 2.0
    thickness = p["anti_warp_ear_thickness_mm"]
    overlap = p["anti_warp_ear_breakaway_overlap_mm"]
    contact = p["anti_warp_ear_side_contact_width_mm"]
    arm = p["anti_warp_ear_arm_width_mm"]
    junction = p["anti_warp_ear_junction_offset_mm"]
    reach = p["anti_warp_ear_tail_reach_mm"]
    tail = p["anti_warp_ear_tail_width_mm"]
    neck = p["anti_warp_ear_diagonal_neck_width_mm"]

    def local_box(u_center: float, v_center: float, u_size: float, v_size: float) -> cq.Workplane:
        return z_box(
            (u_size, v_size, thickness),
            (sx * (half_w + u_center), sy * (half_h + v_center), thickness / 2.0),
        )

    def local_poly(local_points: list[tuple[float, float]]) -> cq.Workplane:
        points = [(sx * (half_w + u), sy * (half_h + v)) for u, v in local_points]
        return z_poly(points, thickness, 0.0)

    # Two side tabs grip the adjacent edges. The slight overlap fuses to the
    # dock, while the 0.5 mm Z thickness keeps the ears easy to trim away.
    ear = local_box((junction - overlap) / 2.0, -contact / 2.0, junction + overlap, contact)
    ear = ear.union(local_box(-contact / 2.0, (junction - overlap) / 2.0, contact, junction + overlap))

    # Short Y arms route both side tabs into the diagonal corner pull.
    ear = ear.union(local_box(junction, junction / 2.0, arm, junction + arm))
    ear = ear.union(local_box(junction / 2.0, junction, junction + arm, arm))
    ear = ear.union(local_box(junction, junction, arm * 2.0, arm * 2.0))

    # Diagonal neck and square pad pull the true corner outward on the diagonal.
    ear = ear.union(
        local_poly(
            [
                (junction - neck / 2.0, junction + neck / 2.0),
                (junction + neck / 2.0, junction - neck / 2.0),
                (reach + neck / 2.0, reach - neck / 2.0),
                (reach - neck / 2.0, reach + neck / 2.0),
            ]
        )
    )
    ear = ear.union(local_box(reach, reach, tail, tail))
    return ear


def add_anti_warp_ears(part: cq.Workplane) -> cq.Workplane:
    if not PARAMS["anti_warp_ears_enabled"]:
        return part
    for sx in (-1, 1):
        for sy in (-1, 1):
            part = part.union(anti_warp_corner_ear(sx, sy))
    return part


def build_dock() -> cq.Workplane:
    p = PARAMS
    part = z_box(
        (p["base_width_mm"], p["base_height_mm"], p["base_thickness_mm"]),
        (0, 0, p["base_thickness_mm"] / 2.0),
    )
    for x, y in p["rod_hole_centers_mm"]:
        cutter = z_cylinder(
            p["rod_hole_diameter_mm"],
            p["rod_hole_depth_mm"] + 0.2,
            p["base_thickness_mm"] - p["rod_hole_depth_mm"],
        ).translate((x, y, 0))
        part = part.cut(cutter)

    edge_chamfer = p["edge_chamfer_mm"]
    if edge_chamfer > 0:
        part = part.edges("|Z").chamfer(edge_chamfer)

    mouth_chamfer = p["hole_mouth_chamfer_mm"]
    if mouth_chamfer > 0:
        part = part.faces(">Z").edges().chamfer(mouth_chamfer)
    part = add_anti_warp_ears(part)
    return part


def build_rod_proxy(x: float, y: float) -> cq.Workplane:
    p = PARAMS
    return z_cylinder(
        p["rod_proxy_diameter_mm"],
        p["rod_hole_depth_mm"] + p["rod_proxy_visible_height_mm"],
        p["base_thickness_mm"] - p["rod_hole_depth_mm"],
        vertices=96,
    ).translate((x, y, 0))


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_dock(), name="100mm_cage_rod_dock", color=cq.Color(0.15, 0.15, 0.14, 1.0))
    for index, (x, y) in enumerate(PARAMS["rod_hole_centers_mm"], start=1):
        assembly.add(
            build_rod_proxy(x, y),
            name=f"rod_proxy_{index}_6mm_on_cage_square",
            color=cq.Color(0.1, 0.45, 0.9, 0.38),
        )
    return assembly


def build_print_layout() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_print_layout")
    assembly.add(build_dock(), name="printable_rod_dock", color=cq.Color(0.15, 0.15, 0.14, 1.0))
    return assembly


def export_part(part: cq.Workplane, step_path: Path, stl_path: Path) -> None:
    exporters.export(part, str(step_path))
    exporters.export(part, str(stl_path))


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    compound = assembly.toCompound()
    exporters.export(compound, str(step_path))
    exporters.export(compound, str(stl_path))


def write_top_svg(path: Path) -> None:
    p = PARAMS
    scale = 6.0
    pad = 48
    legend_w = 520
    w = p["base_width_mm"]
    h = p["base_height_mm"]
    svg_w = int(w * scale + pad * 2 + legend_w)
    svg_h = int(h * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (h / 2.0 - y) * scale

    def circle(x: float, y: float, diameter: float, fill: str, stroke: str) -> str:
        return (
            f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{diameter / 2.0 * scale:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-w/2):.2f}" y="{sy(h/2):.2f}" width="{w*scale:.2f}" height="{h*scale:.2f}" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        f'<rect x="{sx(-15):.2f}" y="{sy(15):.2f}" width="{30*scale:.2f}" height="{30*scale:.2f}" fill="none" stroke="#805ad5" stroke-width="2" stroke-dasharray="7 5"/>',
    ]
    for x, y in p["rod_hole_centers_mm"]:
        lines.append(circle(x, y, p["rod_hole_diameter_mm"], "#ffffff", "#3182ce"))
        lines.append(circle(x, y, p["rod_proxy_diameter_mm"], "rgba(49,130,206,0.18)", "#2b6cb0"))
    legend_x = pad + w * scale + 34
    legend = [
        "Cage rod dock top view",
        "Base: 100 x 100 mm",
        "Thickness: 30 mm",
        "Hole centers: +/-15 mm, standard 30 mm cage square",
        "Dock holes: 10 mm diameter, 25 mm deep",
        "Bottom floor: 5 mm",
        "Run-2: bottom anti-warp ears add side + diagonal corner pull",
        "Blue inner circles show nominal 6 mm rods",
        "Simple analytic STEP, designed for fast Shapr3D import",
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
        f"""# Cage Rod Dock, 100 mm Base With 10 mm Holes

This is a clean parametric dock for the cage-system rods. It follows the
standard 30 mm cage square, with four vertical blind holes centered at `x/y =
±15 mm`.

## Geometry

- Base: `{p['base_width_mm']} x {p['base_height_mm']} x {p['base_thickness_mm']} mm`.
- Rod dock holes: `{p['rod_hole_diameter_mm']} mm` diameter.
- Hole depth: `{p['rod_hole_depth_mm']} mm`, leaving `{p['bottom_floor_thickness_mm']} mm` floor.
- Cage geometry: `{p['cage_pitch_mm']} mm` square, hole centers at `±{p['cage_pitch_mm'] / 2.0} mm`.

## Shapr3D Import Notes

This design deliberately avoids threads, helixes, fragile cutter fragments,
and B-spline surfaces. The final STEP is a simple block with four vertical
cylindrical blind holes and small exterior chamfers, so it should import into
Shapr3D without a long repair pass.

## Print Notes

Print flat on the 100 x 100 mm base. The holes open upward. The assembly files
include blue 6 mm rod proxies only for checking placement.

The latest root output includes four removable anti-warp ears on the bottom
face. Each corner has two side pulls plus one diagonal full-corner pull, so a
large flat print is held down from the actual corner direction as well as along
the two edges. Trim the ears away after printing.

The previous no-ear version is archived under
`cad/designs/cage_rod_dock_100mm_base_10mm_holes/runs/run-1-original-no-ears-20260710T130229Z/`.

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
        "dock_step": ARTIFACT_DIR / f"{STEM}.step",
        "dock_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "assembly_step": ARTIFACT_DIR / f"{STEM}_assembly.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}_assembly.stl",
        "print_layout_step": ARTIFACT_DIR / f"{STEM}_print_layout.step",
        "print_layout_stl": ARTIFACT_DIR / f"{STEM}_print_layout.stl",
        "top_view_svg": ARTIFACT_DIR / f"{STEM}_top_view.svg",
        "top_view_png": ARTIFACT_DIR / f"{STEM}_top_view.png",
        "render_png": ARTIFACT_DIR / f"{STEM}_render.png",
        "assembly_render_png": ARTIFACT_DIR / f"{STEM}_assembly_render.png",
        "blender_scene": ARTIFACT_DIR / f"{STEM}.blend",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }
    export_part(build_dock(), paths["dock_step"], paths["dock_stl"])
    export_assembly(build_assembly(), paths["assembly_step"], paths["assembly_stl"])
    export_assembly(build_print_layout(), paths["print_layout_step"], paths["print_layout_stl"])
    write_top_svg(paths["top_view_svg"])
    svg_to_png(paths["top_view_svg"], paths["top_view_png"])

    use_this = DESIGN_DIR / f"USE_THIS_{STEM}.step"
    use_this.write_bytes(paths["dock_step"].read_bytes())

    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["use_this_step"] = repo_path(use_this)
    outputs["manifest"] = repo_path(paths["manifest"])
    write_manifest(paths["manifest"], outputs)
    write_readme(DESIGN_DIR / "README.md", outputs)
    print(json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
