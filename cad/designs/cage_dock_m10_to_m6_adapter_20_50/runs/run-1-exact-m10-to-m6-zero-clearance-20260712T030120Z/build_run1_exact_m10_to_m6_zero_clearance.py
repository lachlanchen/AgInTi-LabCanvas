#!/usr/bin/env python3
"""Build run 1: exact smooth M10-to-M6 dock adapters."""

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
STEM = "cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance"
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
    "design_intent": "Exact smooth-diameter adapter: M10-class 10.0 mm lower insert to M6-class 6.0 mm upper rod.",
    "dock_hole_reference_diameter_mm": 10.0,
    "lower_insert_diameter_mm": 10.0,
    "lower_insert_length_mm": 20.0,
    "upper_rod_diameter_mm": 6.0,
    "upper_rod_length_mm": 50.0,
    "total_height_mm": 70.0,
    "diameter_clearance_mm": 0.0,
    "previous_insert_diameter_mm": 9.8,
    "previous_clearance_mm": 0.2,
    "lead_in_chamfer_mm": 0.25,
    "top_chamfer_mm": 0.25,
    "print_grid_rows": 2,
    "print_grid_cols": 2,
    "print_grid_pitch_mm": 25.0,
    "fit_note": "M10/M6 mean smooth exact diameters in this model, not modeled screw threads.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float, vertices: int = 128) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def build_adapter() -> cq.Workplane:
    p = PARAMS
    lower = z_cylinder(p["lower_insert_diameter_mm"], p["lower_insert_length_mm"], 0.0)
    upper = z_cylinder(
        p["upper_rod_diameter_mm"],
        p["upper_rod_length_mm"],
        p["lower_insert_length_mm"],
        vertices=128,
    )
    part = lower.union(upper)
    part = part.faces("<Z").edges().chamfer(p["lead_in_chamfer_mm"])
    part = part.faces(">Z").edges().chamfer(p["top_chamfer_mm"])
    return part


def build_2x2_grid() -> cq.Assembly:
    p = PARAMS
    assembly = cq.Assembly(name=f"{STEM}_2x2_print_grid")
    rows = int(p["print_grid_rows"])
    cols = int(p["print_grid_cols"])
    pitch = p["print_grid_pitch_mm"]
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col + 1
            x = (col - (cols - 1) / 2.0) * pitch
            y = (row - (rows - 1) / 2.0) * pitch
            assembly.add(
                build_adapter().translate((x, y, 0)),
                name=f"exact_m10_to_m6_adapter_{index:02d}",
                color=cq.Color(0.24, 0.22, 0.18, 1.0),
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
    scale = 9.0
    pad = 54
    legend_w = 640
    max_d = p["lower_insert_diameter_mm"]
    h = p["total_height_mm"]
    lower_d = p["lower_insert_diameter_mm"]
    upper_d = p["upper_rod_diameter_mm"]
    lower_h = p["lower_insert_length_mm"]
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
    ]
    legend_x = pad + max_d * scale + 42
    legend = [
        "Exact M10-to-M6 smooth adapter",
        f"Lower insert: {lower_d:.1f} mm diameter x {lower_h:.1f} mm",
        f"Upper rod: {upper_d:.1f} mm diameter x {p['upper_rod_length_mm']:.1f} mm",
        f"Total height: {h:.1f} mm",
        "Diameter clearance: 0.0 mm",
        "Previous version: 9.8 mm insert for 10.0 mm hole",
        "M10/M6 are smooth diameter classes, not screw threads.",
    ]
    for index, row in enumerate(legend):
        size = 17 if index == 0 else 13
        weight = "700" if index == 0 else "400"
        lines.append(
            f'<text x="{legend_x}" y="{pad + 25 * index}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def svg_to_png(svg: Path, png: Path) -> None:
    if shutil.which("convert"):
        subprocess.run(["convert", str(svg), str(png)], check=True)


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for print-ready renders")
    subprocess.run([blender, "--background", "--python", str(RUN_DIR / "render_run1_exact_m10_to_m6_zero_clearance.py")], check=True)


def sync_print_ready(paths: dict[str, Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for key in (
        "print_this_step",
        "print_this_stl",
        "print_this_3mf",
        "print_this_render",
        "use_this_step",
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
        f"""# Run 1: Exact M10 To M6 Adapter

This is the exact zero-clearance smooth adapter. The old adapter used a
`9.8 mm` lower insert for the `10.0 mm` dock hole and fit well. This run uses
`10.0 mm` lower insert and `6.0 mm` upper rod exactly.

## Geometry

- Lower insert: `{p['lower_insert_diameter_mm']} mm` diameter x `{p['lower_insert_length_mm']} mm`.
- Upper rod: `{p['upper_rod_diameter_mm']} mm` diameter x `{p['upper_rod_length_mm']} mm`.
- Total height: `{p['total_height_mm']} mm`.
- Diameter clearance: `{p['diameter_clearance_mm']} mm`.

## Direct Print

Use the root `PRINT_THIS_*` files. They contain a 2x2 upright adapter grid.

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
        "grid_step": ARTIFACT_DIR / f"{STEM}_2x2_print_grid.step",
        "grid_stl": ARTIFACT_DIR / f"{STEM}_2x2_print_grid.stl",
        "grid_3mf": ARTIFACT_DIR / f"{STEM}_2x2_print_grid.3mf",
        "section_svg": ARTIFACT_DIR / f"{STEM}_section.svg",
        "section_png": ARTIFACT_DIR / f"{STEM}_section.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
        "print_this_step": RUN_DIR / f"PRINT_THIS_{STEM}_2x2_print_grid.step",
        "print_this_stl": RUN_DIR / f"PRINT_THIS_{STEM}_2x2_print_grid.stl",
        "print_this_3mf": RUN_DIR / f"PRINT_THIS_{STEM}_2x2_print_grid.3mf",
        "print_this_render": RUN_DIR / f"PRINT_THIS_{STEM}_2x2_print_grid_render.png",
        "use_this_step": RUN_DIR / f"USE_THIS_{STEM}_single.step",
        "readme": RUN_DIR / "README.md",
    }
    export_part(build_adapter(), paths["single_step"], paths["single_stl"])
    export_assembly(build_2x2_grid(), paths["grid_step"], paths["grid_stl"])
    export_stl_as_3mf(paths["grid_stl"], paths["grid_3mf"], title=f"{STEM} 2x2 print grid")
    write_section_svg(paths["section_svg"])
    svg_to_png(paths["section_svg"], paths["section_png"])
    paths["print_this_step"].write_bytes(paths["grid_step"].read_bytes())
    paths["print_this_stl"].write_bytes(paths["grid_stl"].read_bytes())
    paths["print_this_3mf"].write_bytes(paths["grid_3mf"].read_bytes())
    paths["use_this_step"].write_bytes(paths["single_step"].read_bytes())
    render_with_blender()
    validation = {
        "single_step": validate_step(paths["single_step"]),
        "single_stl": validate_mesh(paths["single_stl"]),
        "grid_step": validate_step(paths["grid_step"]),
        "grid_stl": validate_mesh(paths["grid_stl"]),
        "grid_3mf": validate_3mf(paths["grid_3mf"]),
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
