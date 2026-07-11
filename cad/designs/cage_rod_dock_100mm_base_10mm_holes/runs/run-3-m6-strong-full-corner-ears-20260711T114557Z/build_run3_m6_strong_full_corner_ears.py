#!/usr/bin/env python3
"""Build run 3: M6-fit cage rod dock with stronger full-corner ears."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import cadquery as cq
from cadquery import exporters
import trimesh


def find_repo_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "cad/tools/simple_3mf.py").exists():
            return parent
    raise RuntimeError("Could not locate AgenticApp repository root")


DESIGN_DIR = Path(__file__).resolve().parent
ROOT = find_repo_root(DESIGN_DIR)
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_rod_dock_100mm_base_m6_strong_full_corner_ears"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "cage_rod_dock_100mm_base_10mm_holes"
    / "run-3-m6-strong-full-corner-ears-print-ready"
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "design_intent": "100 mm cage rod dock using M6/6 mm rod-fit holes and stronger removable full-corner anti-warp ears.",
    "base_width_mm": 100.0,
    "base_height_mm": 100.0,
    "base_thickness_mm": 30.0,
    "cage_pitch_mm": 30.0,
    "rod_hole_centers_mm": [[-15.0, -15.0], [15.0, -15.0], [-15.0, 15.0], [15.0, 15.0]],
    "rod_nominal_diameter_mm": 6.0,
    "rod_hole_diameter_mm": 6.4,
    "rod_hole_depth_mm": 25.0,
    "bottom_floor_thickness_mm": 5.0,
    "rod_proxy_diameter_mm": 6.0,
    "rod_proxy_visible_height_mm": 72.0,
    "edge_chamfer_mm": 1.0,
    "hole_mouth_chamfer_mm": 0.35,
    "anti_warp_ear_style": "four filled full-corner ears, doubled thickness and roughly doubled footprint compared with the previous diagonal-ear dock",
    "anti_warp_ear_thickness_mm": 1.0,
    "anti_warp_ear_breakaway_overlap_mm": 0.7,
    "anti_warp_ear_side_length_mm": 36.0,
    "anti_warp_ear_side_width_mm": 18.0,
    "anti_warp_ear_diagonal_reach_mm": 48.0,
    "anti_warp_ear_tail_width_mm": 32.0,
    "anti_warp_ear_note": "Each corner is one filled polygon covering both adjacent edges plus the diagonal corner direction. The larger area improves hold-down but will take more force to trim than the previous 0.5 mm ears.",
    "print_orientation": "Print flat on the 100 x 100 mm base. The four M6-fit blind holes open upward.",
    "shapr_friendly_note": "No threads, no helix, no B-spline surfaces, and no fragile fill-recut operations.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def z_poly(points: list[tuple[float, float]], height: float, z_min: float = 0.0) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).polyline(points).close().extrude(height)


def z_cylinder(diameter: float, height: float, z_min: float, vertices: int = 128) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def full_corner_ear(sx: int, sy: int) -> cq.Workplane:
    """Filled anti-warp ear covering both side directions and the corner diagonal."""
    p = PARAMS
    half_w = p["base_width_mm"] / 2.0
    half_h = p["base_height_mm"] / 2.0
    overlap = p["anti_warp_ear_breakaway_overlap_mm"]
    side_len = p["anti_warp_ear_side_length_mm"]
    side_width = p["anti_warp_ear_side_width_mm"]
    reach = p["anti_warp_ear_diagonal_reach_mm"]
    tail = p["anti_warp_ear_tail_width_mm"]
    thickness = p["anti_warp_ear_thickness_mm"]

    # Local coordinates are measured from the true dock corner. Negative values
    # overlap slightly into the dock, fusing the sacrificial ear to the base.
    local = [
        (-overlap, -overlap),
        (side_len, -overlap),
        (side_len, side_width),
        (reach + tail / 2.0, reach - tail / 2.0),
        (reach + tail / 2.0, reach + tail / 2.0),
        (reach - tail / 2.0, reach + tail / 2.0),
        (side_width, side_len),
        (-overlap, side_len),
    ]
    points = [(sx * (half_w + u), sy * (half_h + v)) for u, v in local]
    return z_poly(points, thickness, 0.0)


def add_anti_warp_ears(part: cq.Workplane) -> cq.Workplane:
    for sx in (-1, 1):
        for sy in (-1, 1):
            part = part.union(full_corner_ear(sx, sy))
    return part


def build_dock() -> cq.Workplane:
    p = PARAMS
    part = z_box(
        (p["base_width_mm"], p["base_height_mm"], p["base_thickness_mm"]),
        (0, 0, p["base_thickness_mm"] / 2.0),
    )
    z_start = p["base_thickness_mm"] - p["rod_hole_depth_mm"]
    for x, y in p["rod_hole_centers_mm"]:
        cutter = z_cylinder(p["rod_hole_diameter_mm"], p["rod_hole_depth_mm"] + 0.2, z_start).translate((x, y, 0))
        part = part.cut(cutter)

    if p["edge_chamfer_mm"] > 0:
        part = part.edges("|Z").chamfer(p["edge_chamfer_mm"])
    if p["hole_mouth_chamfer_mm"] > 0:
        part = part.faces(">Z").edges().chamfer(p["hole_mouth_chamfer_mm"])
    return add_anti_warp_ears(part)


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
    assembly.add(build_dock(), name="m6_fit_100mm_cage_rod_dock", color=cq.Color(0.15, 0.15, 0.14, 1.0))
    for index, (x, y) in enumerate(PARAMS["rod_hole_centers_mm"], start=1):
        assembly.add(
            build_rod_proxy(x, y),
            name=f"rod_proxy_{index}_6mm_on_cage_square",
            color=cq.Color(0.1, 0.45, 0.9, 0.38),
        )
    return assembly


def build_print_layout() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_print_layout")
    assembly.add(build_dock(), name="printable_m6_rod_dock_with_strong_ears", color=cq.Color(0.15, 0.15, 0.14, 1.0))
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
    scale = 4.0
    pad = 54
    legend_w = 620
    w = p["base_width_mm"]
    h = p["base_height_mm"]
    ear_extent = p["anti_warp_ear_diagonal_reach_mm"] + p["anti_warp_ear_tail_width_mm"] / 2.0
    view_w = w + 2 * ear_extent
    view_h = h + 2 * ear_extent
    svg_w = int(view_w * scale + pad * 2 + legend_w)
    svg_h = int(view_h * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + view_w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (view_h / 2.0 - y) * scale

    def poly(points: list[tuple[float, float]], fill: str, stroke: str) -> str:
        pts = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)
        return f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for sx_sign in (-1, 1):
        for sy_sign in (-1, 1):
            half_w = w / 2.0
            half_h = h / 2.0
            overlap = p["anti_warp_ear_breakaway_overlap_mm"]
            side_len = p["anti_warp_ear_side_length_mm"]
            side_width = p["anti_warp_ear_side_width_mm"]
            reach = p["anti_warp_ear_diagonal_reach_mm"]
            tail = p["anti_warp_ear_tail_width_mm"]
            local = [
                (-overlap, -overlap),
                (side_len, -overlap),
                (side_len, side_width),
                (reach + tail / 2.0, reach - tail / 2.0),
                (reach + tail / 2.0, reach + tail / 2.0),
                (reach - tail / 2.0, reach + tail / 2.0),
                (side_width, side_len),
                (-overlap, side_len),
            ]
            points = [(sx_sign * (half_w + u), sy_sign * (half_h + v)) for u, v in local]
            lines.append(poly(points, "#fef5e7", "#dd6b20"))
    lines.append(
        f'<rect x="{sx(-w/2):.2f}" y="{sy(h/2):.2f}" width="{w*scale:.2f}" height="{h*scale:.2f}" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>'
    )
    lines.append(
        f'<rect x="{sx(-15):.2f}" y="{sy(15):.2f}" width="{30*scale:.2f}" height="{30*scale:.2f}" fill="none" stroke="#805ad5" stroke-width="2" stroke-dasharray="7 5"/>'
    )
    for x, y in p["rod_hole_centers_mm"]:
        lines.append(
            f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{p["rod_hole_diameter_mm"]/2*scale:.2f}" fill="#ffffff" stroke="#3182ce" stroke-width="2"/>'
        )
    legend_x = pad + view_w * scale + 34
    legend = [
        "Run 3 M6 dock with stronger ears",
        f"Base: {w:.0f} x {h:.0f} x {p['base_thickness_mm']:.0f} mm",
        f"Rod holes: {p['rod_hole_diameter_mm']:.1f} mm diameter, {p['rod_hole_depth_mm']:.0f} mm deep",
        "Cage square: 30 mm, centers at +/-15 mm",
        f"Ears: {p['anti_warp_ear_thickness_mm']:.1f} mm thick, filled full-corner polygon",
        f"Side reach: {p['anti_warp_ear_side_length_mm']:.0f} mm; diagonal reach: {p['anti_warp_ear_diagonal_reach_mm']:.0f} mm",
        "Print flat. Trim stronger ears after print.",
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


def mesh_checks(stl_path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(stl_path, force="mesh")
    return {
        "watertight": bool(mesh.is_watertight),
        "component_count": len(mesh.split(only_watertight=False)),
        "bounds_mm": {
            "min": [round(float(v), 3) for v in mesh.bounds[0]],
            "max": [round(float(v), 3) for v in mesh.bounds[1]],
            "size": [round(float(v), 3) for v in (mesh.bounds[1] - mesh.bounds[0])],
        },
    }


def validate_3mf(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return sorted(archive.namelist())


def write_manifest(path: Path, outputs: dict[str, str], checks: dict[str, object]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "parameters": PARAMS,
        "outputs": outputs,
        "validation": checks,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str], checks: dict[str, object]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# Run 3: M6 Dock With Strong Full-Corner Ears

This run keeps the previous 100 x 100 x 30 mm cage dock geometry, but changes
the rod sockets from the old 10 mm dock holes to `{PARAMS['rod_hole_diameter_mm']} mm`
M6/6 mm rod-fit blind holes. It also replaces the previous 0.5 mm Y-style ears
with larger filled full-corner ears.

## Geometry

- Base: `{PARAMS['base_width_mm']} x {PARAMS['base_height_mm']} x {PARAMS['base_thickness_mm']} mm`.
- Cage centers: `x/y = +/-15 mm`.
- Rod holes: `{PARAMS['rod_hole_diameter_mm']} mm` diameter, `{PARAMS['rod_hole_depth_mm']} mm` deep.
- Bottom floor under sockets: `{PARAMS['bottom_floor_thickness_mm']} mm`.
- Ears: `{PARAMS['anti_warp_ear_thickness_mm']} mm` thick, filled, full corner coverage.
- Ear side length: `{PARAMS['anti_warp_ear_side_length_mm']} mm`; diagonal reach: `{PARAMS['anti_warp_ear_diagonal_reach_mm']} mm`; tail width: `{PARAMS['anti_warp_ear_tail_width_mm']} mm`.

## Print Notes

Use the root `PRINT_THIS_*` files in this run folder. Print flat with the M6-fit
blind holes opening upward. These ears are intentionally stronger than before;
they should hold the full corner better but require more trimming force.

Validation: STEP imports as `{checks['step_solid_count']}` solid, STL watertight
is `{checks['print_layout_stl']['watertight']}`, STL components
`{checks['print_layout_stl']['component_count']}`, bounds
`{checks['print_layout_stl']['bounds_mm']['size']} mm`.

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


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        print("warning: blender not found; skipping render", file=sys.stderr)
        return
    subprocess.run(
        [blender, "--background", "--python", str(DESIGN_DIR / "render_run3_m6_strong_full_corner_ears.py")],
        check=True,
    )


def sync_print_ready(files: list[Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for src in files:
        if src.exists():
            shutil.copy2(src, NUTSTORE_DIR / src.name)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "dock_step": ARTIFACT_DIR / f"{STEM}.step",
        "dock_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "assembly_step": ARTIFACT_DIR / f"{STEM}_assembly.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}_assembly.stl",
        "print_layout_step": ARTIFACT_DIR / f"{STEM}_print_layout.step",
        "print_layout_stl": ARTIFACT_DIR / f"{STEM}_print_layout.stl",
        "print_layout_3mf": ARTIFACT_DIR / f"{STEM}_print_layout.3mf",
        "top_view_svg": ARTIFACT_DIR / f"{STEM}_top_view.svg",
        "top_view_png": ARTIFACT_DIR / f"{STEM}_top_view.png",
        "render_png": ARTIFACT_DIR / f"{STEM}_render.png",
        "assembly_render_png": ARTIFACT_DIR / f"{STEM}_assembly_render.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }

    export_part(build_dock(), paths["dock_step"], paths["dock_stl"])
    export_assembly(build_assembly(), paths["assembly_step"], paths["assembly_stl"])
    export_assembly(build_print_layout(), paths["print_layout_step"], paths["print_layout_stl"])
    export_stl_as_3mf(paths["print_layout_stl"], paths["print_layout_3mf"], title=f"{STEM} print layout")
    write_top_svg(paths["top_view_svg"])
    svg_to_png(paths["top_view_svg"], paths["top_view_png"])

    use_this = DESIGN_DIR / f"USE_THIS_{STEM}.step"
    print_this_step = DESIGN_DIR / f"PRINT_THIS_{STEM}.step"
    print_this_stl = DESIGN_DIR / f"PRINT_THIS_{STEM}.stl"
    print_this_3mf = DESIGN_DIR / f"PRINT_THIS_{STEM}.3mf"
    shutil.copy2(paths["dock_step"], use_this)
    shutil.copy2(paths["print_layout_step"], print_this_step)
    shutil.copy2(paths["print_layout_stl"], print_this_stl)
    shutil.copy2(paths["print_layout_3mf"], print_this_3mf)

    shape = cq.importers.importStep(str(paths["print_layout_step"])).val()
    bb = shape.BoundingBox()
    checks = {
        "step_solid_count": len(shape.Solids()),
        "step_bounds_mm": [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)],
        "dock_stl": mesh_checks(paths["dock_stl"]),
        "print_layout_stl": mesh_checks(paths["print_layout_stl"]),
        "threemf_entries": validate_3mf(paths["print_layout_3mf"]),
    }

    outputs = {name: str(path.resolve()) for name, path in paths.items() if name != "manifest"}
    outputs["use_this_step"] = str(use_this.resolve())
    outputs["print_this_step"] = str(print_this_step.resolve())
    outputs["print_this_stl"] = str(print_this_stl.resolve())
    outputs["print_this_3mf"] = str(print_this_3mf.resolve())
    outputs["root_render_png"] = str((DESIGN_DIR / f"PRINT_THIS_{STEM}_render.png").resolve())
    outputs["root_assembly_render_png"] = str((DESIGN_DIR / f"USE_THIS_{STEM}_assembly_render.png").resolve())
    outputs["manifest"] = str(paths["manifest"].resolve())
    outputs["nutstore_print_ready_folder"] = str(NUTSTORE_DIR)

    write_manifest(paths["manifest"], outputs, checks)
    write_readme(DESIGN_DIR / "README.md", outputs, checks)
    render_with_blender()
    root_render = DESIGN_DIR / f"PRINT_THIS_{STEM}_render.png"
    root_assembly_render = DESIGN_DIR / f"USE_THIS_{STEM}_assembly_render.png"
    if paths["render_png"].exists():
        shutil.copy2(paths["render_png"], root_render)
    if paths["assembly_render_png"].exists():
        shutil.copy2(paths["assembly_render_png"], root_assembly_render)
    sync_print_ready(
        [
            print_this_step,
            print_this_stl,
            print_this_3mf,
            root_render,
            root_assembly_render,
            paths["top_view_png"],
            DESIGN_DIR / "README.md",
            paths["manifest"],
        ]
    )
    print(json.dumps({"outputs": outputs, "validation": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
