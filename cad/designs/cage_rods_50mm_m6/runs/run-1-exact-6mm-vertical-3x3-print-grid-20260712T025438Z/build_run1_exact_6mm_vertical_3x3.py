#!/usr/bin/env python3
"""Build run 1: exact 6 mm rods in a vertical 3x3 print grid."""

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
STEM = "cage_rods_run1_exact_6mm_vertical_3x3"
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
    "design_intent": "Exact 6.0 mm smooth rods for the tight M6 connector, printed upright in a 3x3 grid.",
    "rod_diameter_mm": 6.0,
    "rod_radius_mm": 3.0,
    "rod_length_mm": 50.0,
    "diameter_clearance_mm": 0.0,
    "end_chamfer_mm": 0.18,
    "print_grid_rows": 3,
    "print_grid_cols": 3,
    "print_grid_pitch_mm": 16.0,
    "print_orientation": "Vertical/upright. Each rod stands on its circular 6 mm end face.",
    "print_note": "No horizontal rods and no auxiliary brim geometry. If bed adhesion is weak, add slicer brim rather than changing the rod diameter.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def rod_body() -> cq.Workplane:
    p = PARAMS
    rod = cq.Workplane("XY").circle(p["rod_radius_mm"]).extrude(p["rod_length_mm"])
    chamfer = p["end_chamfer_mm"]
    if chamfer > 0:
        rod = rod.faces(">Z").edges().chamfer(chamfer)
        rod = rod.faces("<Z").edges().chamfer(chamfer)
    return rod


def build_3x3_vertical_grid() -> cq.Assembly:
    p = PARAMS
    rows = int(p["print_grid_rows"])
    cols = int(p["print_grid_cols"])
    pitch = p["print_grid_pitch_mm"]
    assembly = cq.Assembly(name=f"{STEM}_print_grid")
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col + 1
            x = (col - (cols - 1) / 2.0) * pitch
            y = (row - (rows - 1) / 2.0) * pitch
            assembly.add(
                rod_body().translate((x, y, 0)),
                name=f"exact_6mm_vertical_rod_{index:02d}",
                color=cq.Color(0.68, 0.68, 0.64, 1.0),
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


def write_diagram_svg(path: Path) -> None:
    p = PARAMS
    scale = 7.0
    pad = 48
    legend_w = 620
    footprint = 46
    side_h = 68
    svg_w = int(footprint * scale + pad * 2 + legend_w)
    svg_h = int((footprint + side_h) * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + footprint / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (footprint / 2.0 - y) * scale

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{pad}" y="28" font-family="Arial" font-size="18" font-weight="700" fill="#1a202c">Exact 6 mm Vertical Rod Grid</text>',
    ]
    for row in range(3):
        for col in range(3):
            x = (col - 1) * p["print_grid_pitch_mm"]
            y = (row - 1) * p["print_grid_pitch_mm"]
            lines.append(
                f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{p["rod_radius_mm"]*scale:.2f}" fill="#edf2f7" stroke="#2d3748" stroke-width="2"/>'
            )

    side_x = pad
    side_y = pad + (footprint + 16) * scale
    rod_w = p["rod_diameter_mm"] * scale
    rod_h = p["rod_length_mm"] * scale
    lines.extend(
        [
            f'<text x="{side_x}" y="{side_y - 18}" font-family="Arial" font-size="14" fill="#1a202c">Side view of one upright rod</text>',
            f'<rect x="{side_x}" y="{side_y - rod_h}" width="{rod_w}" height="{rod_h}" rx="{rod_w/2}" fill="#edf2f7" stroke="#2d3748" stroke-width="2"/>',
            f'<text x="{side_x + rod_w + 16}" y="{side_y - rod_h/2}" font-family="Arial" font-size="13" fill="#1a202c">50 mm</text>',
            f'<text x="{side_x - 6}" y="{side_y + 24}" font-family="Arial" font-size="13" fill="#1a202c">Ø6 mm</text>',
        ]
    )
    legend_x = pad + footprint * scale + 42
    legend = [
        "Geometry",
        "Rod diameter: exact 6.0 mm",
        "Rod length: 50.0 mm",
        "Print grid: 3 x 3 upright rods",
        "Grid pitch: 16 mm",
        "No horizontal rods in this run",
        "No auxiliary brim geometry; add slicer brim if needed",
    ]
    for index, row in enumerate(legend):
        size = 17 if index == 0 else 13
        weight = "700" if index == 0 else "400"
        lines.append(
            f'<text x="{legend_x}" y="{pad + 24 * index}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
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
    subprocess.run([blender, "--background", "--python", str(RUN_DIR / "render_run1_exact_6mm_vertical_3x3.py")], check=True)


def sync_print_ready(paths: dict[str, Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for key in (
        "print_this_step",
        "print_this_stl",
        "print_this_3mf",
        "print_this_render",
        "use_this_step",
        "diagram_png",
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
        f"""# Run 1: Exact 6 mm Vertical 3x3 Rod Grid

This run provides exact smooth rods for the tight M6 connector. The previous
rod model was already `6.0 mm` diameter, but the direct print grid was a
horizontal 5x5 layout. This run is a vertical 3x3 layout only.

## Direct Print

Use the root `PRINT_THIS_*` files in this run folder. They contain nine upright
rods and no horizontal rods.

## Geometry

- Rod diameter: `{p['rod_diameter_mm']} mm`.
- Rod length: `{p['rod_length_mm']} mm`.
- Diameter clearance: `{p['diameter_clearance_mm']} mm`.
- Grid: `{p['print_grid_rows']} x {p['print_grid_cols']}`.
- Grid pitch: `{p['print_grid_pitch_mm']} mm`.
- End chamfer: `{p['end_chamfer_mm']} mm`.

## Print Note

The rods stand on a 6 mm circular end face. This keeps the geometry exact. If
the printer bed adhesion is weak, add a slicer brim instead of changing the CAD
diameter.

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
        "print_grid_step": ARTIFACT_DIR / f"{STEM}_vertical_3x3_print_grid.step",
        "print_grid_stl": ARTIFACT_DIR / f"{STEM}_vertical_3x3_print_grid.stl",
        "print_grid_3mf": ARTIFACT_DIR / f"{STEM}_vertical_3x3_print_grid.3mf",
        "diagram_svg": ARTIFACT_DIR / f"{STEM}_diagram.svg",
        "diagram_png": ARTIFACT_DIR / f"{STEM}_diagram.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
        "print_this_step": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.step",
        "print_this_stl": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.stl",
        "print_this_3mf": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.3mf",
        "print_this_render": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid_render.png",
        "use_this_step": RUN_DIR / f"USE_THIS_{STEM}_single.step",
        "readme": RUN_DIR / "README.md",
    }
    export_part(rod_body(), paths["single_step"], paths["single_stl"])
    export_assembly(build_3x3_vertical_grid(), paths["print_grid_step"], paths["print_grid_stl"])
    export_stl_as_3mf(paths["print_grid_stl"], paths["print_grid_3mf"], title=f"{STEM} vertical 3x3 print grid")
    write_diagram_svg(paths["diagram_svg"])
    svg_to_png(paths["diagram_svg"], paths["diagram_png"])
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
