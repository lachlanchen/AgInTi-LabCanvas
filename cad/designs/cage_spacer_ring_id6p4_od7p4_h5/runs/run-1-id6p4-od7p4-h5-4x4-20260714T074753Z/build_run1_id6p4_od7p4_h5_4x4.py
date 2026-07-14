#!/usr/bin/env python3
"""Build a 4x4 print grid of 6.4 ID / 7.4 OD / 5 mm spacer rings."""

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
STEM = "cage_spacer_ring_run1_id6p4_od7p4_h5"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / DESIGN_DIR.name / RUN_DIR.name
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "design_intent": "Thin cage-element spacer ring following the explicit 6.4 mm ID and 7.4 mm OD request.",
    "inner_diameter_mm": 6.4,
    "outer_diameter_mm": 7.4,
    "height_mm": 5.0,
    "diametral_wall_difference_mm": 1.0,
    "radial_wall_thickness_mm": 0.5,
    "true_1mm_radial_wall_outer_diameter_mm": 8.4,
    "print_grid_rows": 4,
    "print_grid_cols": 4,
    "print_grid_pitch_mm": 12.0,
    "print_orientation": "Flat on either annular end face; sixteen independent rings with no raft or connector.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def spacer_ring() -> cq.Workplane:
    p = PARAMS
    outer = cylinder(p["outer_diameter_mm"], p["height_mm"], 0.0)
    bore = cylinder(p["inner_diameter_mm"], p["height_mm"] + 0.2, -0.1)
    return outer.cut(bore)


def build_4x4_grid() -> cq.Assembly:
    p = PARAMS
    rows = int(p["print_grid_rows"])
    cols = int(p["print_grid_cols"])
    pitch = float(p["print_grid_pitch_mm"])
    assembly = cq.Assembly(name=f"{STEM}_4x4_print_grid")
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col + 1
            x = (col - (cols - 1) / 2.0) * pitch
            y = (row - (rows - 1) / 2.0) * pitch
            assembly.add(
                spacer_ring().translate((x, y, 0)),
                name=f"spacer_ring_{index:02d}",
                color=cq.Color(0.30, 0.58, 0.68, 1.0),
            )
    return assembly


def export_part(part: cq.Workplane, step_path: Path, stl_path: Path) -> None:
    exporters.export(part, str(step_path))
    exporters.export(part, str(stl_path))


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    exporters.export(assembly.toCompound(), str(step_path))
    exporters.export(assembly.toCompound(), str(stl_path))


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
    return {
        "watertight": bool(mesh.is_watertight),
        "component_count": len(mesh.split(only_watertight=False)),
        "bbox_mm": [round(float(value), 6) for value in (mesh.bounds[1] - mesh.bounds[0])],
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        names = sorted(archive.namelist())
    return {"entries": names, "has_model": "3D/3dmodel.model" in names}


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for print-ready render")
    subprocess.run(
        [blender, "--background", "--python", str(RUN_DIR / "render_run1_id6p4_od7p4_h5_4x4.py")],
        check=True,
    )


def sync_print_ready(paths: dict[str, Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for key in (
        "print_this_step",
        "print_this_stl",
        "print_this_3mf",
        "print_this_render",
        "use_this_step",
        "manifest",
        "readme",
    ):
        source = paths[key]
        if source.exists():
            shutil.copy2(source, NUTSTORE_DIR / source.name)


def write_readme(path: Path, outputs: dict[str, str], validation: dict[str, object]) -> None:
    p = PARAMS
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    parameter_rows = "\n".join(f"| `{name}` | `{value}` |" for name, value in p.items())
    path.write_text(
        f"""# Run 1: ID 6.4 / OD 7.4 / H 5 Spacer Rings

This run creates sixteen independent rings in a flat 4x4 direct-print layout.

## Geometry

- Inner diameter: `{p['inner_diameter_mm']} mm`.
- Outer diameter: `{p['outer_diameter_mm']} mm`.
- Height: `{p['height_mm']} mm`.
- Radial wall: `{p['radial_wall_thickness_mm']} mm`.
- Grid: `{p['print_grid_rows']} x {p['print_grid_cols']}` at `{p['print_grid_pitch_mm']} mm` pitch.

The requested OD is preserved. Because wall thickness is radial,
`(7.4 - 6.4) / 2 = 0.5 mm`; a true 1 mm radial wall would have 8.4 mm OD.

## Validation

```json
{json.dumps(validation, ensure_ascii=False, indent=2)}
```

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{parameter_rows}
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "single_step": ARTIFACT_DIR / f"{STEM}_single.step",
        "single_stl": ARTIFACT_DIR / f"{STEM}_single.stl",
        "grid_step": ARTIFACT_DIR / f"{STEM}_4x4_print_grid.step",
        "grid_stl": ARTIFACT_DIR / f"{STEM}_4x4_print_grid.stl",
        "grid_3mf": ARTIFACT_DIR / f"{STEM}_4x4_print_grid.3mf",
        "manifest": ARTIFACT_DIR / "manifest.json",
        "print_this_step": RUN_DIR / f"PRINT_THIS_{STEM}_4x4_print_grid.step",
        "print_this_stl": RUN_DIR / f"PRINT_THIS_{STEM}_4x4_print_grid.stl",
        "print_this_3mf": RUN_DIR / f"PRINT_THIS_{STEM}_4x4_print_grid.3mf",
        "print_this_render": RUN_DIR / f"PRINT_THIS_{STEM}_4x4_print_grid_render.png",
        "use_this_step": RUN_DIR / f"USE_THIS_{STEM}_single.step",
        "readme": RUN_DIR / "README.md",
    }
    export_part(spacer_ring(), paths["single_step"], paths["single_stl"])
    export_assembly(build_4x4_grid(), paths["grid_step"], paths["grid_stl"])
    export_stl_as_3mf(paths["grid_stl"], paths["grid_3mf"], title=f"{STEM} 4x4 print grid")
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
        "validation": validation,
        "outputs": outputs,
    }
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(paths["readme"], outputs, validation)
    sync_print_ready(paths)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
