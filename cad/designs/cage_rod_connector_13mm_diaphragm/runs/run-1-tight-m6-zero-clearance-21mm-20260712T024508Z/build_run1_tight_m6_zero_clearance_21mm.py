#!/usr/bin/env python3
"""Build run 1: tight zero-clearance 21 mm cage rod connector."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import trimesh
from OCP.BRepCheck import BRepCheck_Analyzer
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[5]
DESIGN_DIR = Path(__file__).resolve().parents[2]
RUN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = RUN_DIR / "artifacts"
STEM = "cage_rod_connector_run1_tight_m6_zero_clearance_21mm"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / DESIGN_DIR.name
    / RUN_DIR.name
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "design_intent": "Tighter replacement for the loose 13 mm connector. Uses exact nominal M6/6.0 mm rod sockets with zero extra diameter clearance.",
    "outer_diameter_mm": 8.0,
    "total_height_mm": 21.0,
    "rod_nominal_diameter_mm": 6.0,
    "rod_socket_diameter_mm": 6.0,
    "top_socket_depth_mm": 10.0,
    "bottom_socket_depth_mm": 10.0,
    "center_diaphragm_thickness_mm": 1.0,
    "radial_wall_thickness_mm": 1.0,
    "diameter_clearance_mm": 0.0,
    "fit_note": "Previous connector used 6.4 mm sockets for 6 mm rods and was too loose. This run removes that 0.4 mm diameter clearance.",
    "end_edge_chamfer_mm": 0.18,
    "print_orientation": "Print upright on either flat end. Both ends are symmetric.",
    "print_grid_rows": 3,
    "print_grid_cols": 3,
    "print_grid_pitch_mm": 16.0,
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
    part = part.cut(z_cylinder(socket_d, bottom_depth + 0.1, -0.05, vertices=128))
    part = part.cut(z_cylinder(socket_d, top_depth + 0.1, total_h - top_depth - 0.05, vertices=128))
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
    assembly.add(build_connector(), name="tight_21mm_connector", color=cq.Color(0.16, 0.16, 0.15, 1.0))
    assembly.add(build_rod_proxy(-14.0, 24.0), name="lower_6mm_rod_proxy", color=cq.Color(0.1, 0.45, 0.9, 0.35))
    assembly.add(
        build_rod_proxy(p["total_height_mm"] - p["top_socket_depth_mm"], 24.0),
        name="upper_6mm_rod_proxy",
        color=cq.Color(0.1, 0.45, 0.9, 0.35),
    )
    return assembly


def build_3x3_print_grid() -> cq.Assembly:
    p = PARAMS
    rows = int(p["print_grid_rows"])
    cols = int(p["print_grid_cols"])
    pitch = p["print_grid_pitch_mm"]
    assembly = cq.Assembly(name=f"{STEM}_3x3_print_grid")
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col + 1
            x = (col - (cols - 1) / 2.0) * pitch
            y = (row - (rows - 1) / 2.0) * pitch
            assembly.add(
                build_connector().translate((x, y, 0)),
                name=f"tight_connector_{index:02d}",
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


def validate_step(path: Path) -> dict[str, object]:
    shape = cq.importers.importStep(str(path)).val()
    bb = shape.BoundingBox()
    return {
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "solids": len(shape.Solids()),
        "bbox_mm": [round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6)],
    }


def validate_mesh(path: Path) -> dict[str, object]:
    mesh = trimesh.load(str(path), force="mesh")
    bounds = mesh.bounds
    return {
        "watertight": bool(mesh.is_watertight),
        "component_count": len(mesh.split(only_watertight=False)),
        "bbox_mm": [round(float(v), 6) for v in (bounds[1] - bounds[0])],
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as zf:
        names = sorted(zf.namelist())
    return {"entries": names, "has_model": "3D/3dmodel.model" in names}


def write_section_svg(path: Path) -> None:
    p = PARAMS
    scale = 22.0
    pad = 54.0
    legend_w = 590
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

    def rect(x0: float, z0: float, x1: float, z1: float, fill: str, stroke: str) -> str:
        return (
            f'<rect x="{sx(x0):.2f}" y="{sy(z1):.2f}" width="{(x1 - x0) * scale:.2f}" '
            f'height="{(z1 - z0) * scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
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
        "Tight cage rod connector section",
        f"Outer cylinder: OD {od:.1f} mm x H {total_h:.1f} mm",
        f"Rod pockets: {socket_d:.1f} mm diameter x {top_depth:.1f} mm deep",
        f"Center diaphragm: {p['center_diaphragm_thickness_mm']:.1f} mm solid web",
        f"Radial wall: {p['radial_wall_thickness_mm']:.1f} mm",
        "Diameter clearance: 0.0 mm, exact nominal M6/6.0 mm socket",
        "Previous loose run used 6.4 mm sockets.",
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
    if shutil.which("convert"):
        subprocess.run(["convert", str(svg), str(png)], check=True)


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for the print-ready render")
    subprocess.run([blender, "--background", "--python", str(RUN_DIR / "render_run1_tight_m6_zero_clearance_21mm.py")], check=True)


def sync_print_ready(paths: dict[str, Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for key in (
        "print_this_step",
        "print_this_stl",
        "print_this_3mf",
        "print_this_render",
        "use_this_step",
        "assembly_step",
        "section_png",
        "manifest",
        "readme",
    ):
        source = paths[key]
        if source.exists():
            shutil.copy2(source, NUTSTORE_DIR / source.name)


def write_readme(path: Path, outputs: dict[str, str], validation: dict[str, object]) -> None:
    p = PARAMS
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in p.items())
    path.write_text(
        f"""# Run 1: Tight M6 Zero-Clearance 21 mm Connector

This run replaces the loose connector fit. The old connector used a `6.4 mm`
socket for a nominal `6.0 mm` rod. This run uses a `6.0 mm` socket, so the
diameter clearance is `0.0 mm`.

## Direct Print

Use the root `PRINT_THIS_*` files in this run folder. They contain a 3x3 grid
of nine upright connectors and no rod proxy geometry.

## Geometry

- Outer diameter: `{p['outer_diameter_mm']} mm`.
- Total height: `{p['total_height_mm']} mm`.
- Top socket: `{p['rod_socket_diameter_mm']} mm` diameter x `{p['top_socket_depth_mm']} mm` deep.
- Bottom socket: `{p['rod_socket_diameter_mm']} mm` diameter x `{p['bottom_socket_depth_mm']} mm` deep.
- Center diaphragm: `{p['center_diaphragm_thickness_mm']} mm`.
- Radial wall: `{p['radial_wall_thickness_mm']} mm`.

## Fit Note

This is intentionally very tight. If the printed rod cannot enter, lightly sand
or drill the socket instead of changing the model first.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Validation

```json
{json.dumps(validation, ensure_ascii=False, indent=2)}
```

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
        "single_step": ARTIFACT_DIR / f"{STEM}_single.step",
        "single_stl": ARTIFACT_DIR / f"{STEM}_single.stl",
        "assembly_step": ARTIFACT_DIR / f"{STEM}_assembly.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}_assembly.stl",
        "print_grid_step": ARTIFACT_DIR / f"{STEM}_3x3_print_grid.step",
        "print_grid_stl": ARTIFACT_DIR / f"{STEM}_3x3_print_grid.stl",
        "print_grid_3mf": ARTIFACT_DIR / f"{STEM}_3x3_print_grid.3mf",
        "section_svg": ARTIFACT_DIR / f"{STEM}_section.svg",
        "section_png": ARTIFACT_DIR / f"{STEM}_section.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
        "print_this_step": RUN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid.step",
        "print_this_stl": RUN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid.stl",
        "print_this_3mf": RUN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid.3mf",
        "print_this_render": RUN_DIR / f"PRINT_THIS_{STEM}_3x3_print_grid_render.png",
        "use_this_step": RUN_DIR / f"USE_THIS_{STEM}_single.step",
        "readme": RUN_DIR / "README.md",
    }
    export_part(build_connector(), paths["single_step"], paths["single_stl"])
    export_assembly(build_assembly(), paths["assembly_step"], paths["assembly_stl"])
    export_assembly(build_3x3_print_grid(), paths["print_grid_step"], paths["print_grid_stl"])
    export_stl_as_3mf(paths["print_grid_stl"], paths["print_grid_3mf"], title=f"{STEM} 3x3 print grid")
    write_section_svg(paths["section_svg"])
    svg_to_png(paths["section_svg"], paths["section_png"])

    paths["print_this_step"].write_bytes(paths["print_grid_step"].read_bytes())
    paths["print_this_stl"].write_bytes(paths["print_grid_stl"].read_bytes())
    paths["print_this_3mf"].write_bytes(paths["print_grid_3mf"].read_bytes())
    paths["use_this_step"].write_bytes(paths["single_step"].read_bytes())

    render_with_blender()
    validation = {
        "single_step": validate_step(paths["single_step"]),
        "single_stl": validate_mesh(paths["single_stl"]),
        "print_grid_step": validate_step(paths["print_grid_step"]),
        "print_grid_stl": validate_mesh(paths["print_grid_stl"]),
        "print_grid_3mf": validate_3mf(paths["print_grid_3mf"]),
    }
    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["manifest"] = repo_path(paths["manifest"])
    outputs["nutstore_print_ready_folder"] = str(NUTSTORE_DIR)
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "parameters": PARAMS,
        "outputs": outputs,
        "validation": validation,
    }
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(paths["readme"], outputs, validation)
    sync_print_ready(paths)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
