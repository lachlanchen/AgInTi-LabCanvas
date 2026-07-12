#!/usr/bin/env python3
"""Build run 2: 50 mm rods with 2.8 mm M3 pilot holes at both ends."""

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
STEM = "cage_rods_run2_2p8mm_m3_pilot_both_ends"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / DESIGN_DIR.name / RUN_DIR.name
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "design_intent": "Exact 6 mm cage rods with measured 2.8 mm x 6 mm M3 pilot/thread holes on both ends.",
    "rod_diameter_mm": 6.0,
    "rod_length_mm": 50.0,
    "m3_pilot_hole_diameter_mm": 2.8,
    "m3_pilot_hole_depth_each_end_mm": 6.0,
    "end_chamfer_mm": 0.18,
    "print_grid_rows": 3,
    "print_grid_cols": 3,
    "print_grid_pitch_mm": 16.0,
    "print_orientation": "Vertical/upright rods on the 6 mm circular end face.",
    "thread_note": "The 2.8 mm hole is a blind pilot for an M3 screw/tap/self-tapping screw; no helical thread is modeled.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def rod_body() -> cq.Workplane:
    p = PARAMS
    rod = cylinder(p["rod_diameter_mm"], p["rod_length_mm"], 0.0)
    hole_d = p["m3_pilot_hole_diameter_mm"]
    hole_depth = p["m3_pilot_hole_depth_each_end_mm"]
    lower_hole = cylinder(hole_d, hole_depth + 0.1, -0.05)
    upper_hole = cylinder(hole_d, hole_depth + 0.1, p["rod_length_mm"] - hole_depth)
    rod = rod.cut(lower_hole).cut(upper_hole)
    if p["end_chamfer_mm"] > 0:
        rod = rod.faces(">Z").edges().chamfer(p["end_chamfer_mm"])
        rod = rod.faces("<Z").edges().chamfer(p["end_chamfer_mm"])
    return rod


def build_3x3_vertical_grid() -> cq.Assembly:
    p = PARAMS
    assembly = cq.Assembly(name=f"{STEM}_vertical_3x3_print_grid")
    for row in range(int(p["print_grid_rows"])):
        for col in range(int(p["print_grid_cols"])):
            index = row * int(p["print_grid_cols"]) + col + 1
            x = (col - (int(p["print_grid_cols"]) - 1) / 2.0) * p["print_grid_pitch_mm"]
            y = (row - (int(p["print_grid_rows"]) - 1) / 2.0) * p["print_grid_pitch_mm"]
            assembly.add(
                rod_body().translate((x, y, 0)),
                name=f"m3_pilot_rod_{index:02d}",
                color=cq.Color(0.68, 0.67, 0.62, 1.0),
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
        "bbox_mm": [round(float(v), 6) for v in (mesh.bounds[1] - mesh.bounds[0])],
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
    subprocess.run([blender, "--background", "--python", str(RUN_DIR / "render_run2_2p8mm_m3_pilot_both_ends.py")], check=True)


def sync_print_ready(paths: dict[str, Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for key in ("print_this_step", "print_this_stl", "print_this_3mf", "print_this_render", "use_this_step", "manifest", "readme"):
        source = paths[key]
        if source.exists():
            shutil.copy2(source, NUTSTORE_DIR / source.name)


def write_readme(path: Path, outputs: dict[str, str], validation: dict[str, object]) -> None:
    p = PARAMS
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in p.items())
    path.write_text(
        f"""# Run 2: 2.8 mm M3 Pilot Holes On Both Rod Ends

This run keeps the rod body exact at `6.0 mm` diameter x `50.0 mm` length and
adds a blind pilot hole at both ends.

## Geometry

- Rod diameter: `{p['rod_diameter_mm']} mm`.
- Rod length: `{p['rod_length_mm']} mm`.
- Pilot hole: `{p['m3_pilot_hole_diameter_mm']} mm` diameter.
- Pilot depth: `{p['m3_pilot_hole_depth_each_end_mm']} mm` from each end.
- Print grid: `{p['print_grid_rows']} x {p['print_grid_cols']}` upright rods.

The hole is a clean cylindrical pilot for an M3 screw/tap/self-tapping screw.
No helical thread is modeled, so STEP import should stay fast and editable.

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
        "grid_step": ARTIFACT_DIR / f"{STEM}_vertical_3x3_print_grid.step",
        "grid_stl": ARTIFACT_DIR / f"{STEM}_vertical_3x3_print_grid.stl",
        "grid_3mf": ARTIFACT_DIR / f"{STEM}_vertical_3x3_print_grid.3mf",
        "manifest": ARTIFACT_DIR / "manifest.json",
        "print_this_step": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.step",
        "print_this_stl": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.stl",
        "print_this_3mf": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid.3mf",
        "print_this_render": RUN_DIR / f"PRINT_THIS_{STEM}_vertical_3x3_print_grid_render.png",
        "use_this_step": RUN_DIR / f"USE_THIS_{STEM}_single.step",
        "readme": RUN_DIR / "README.md",
    }
    export_part(rod_body(), paths["single_step"], paths["single_stl"])
    export_assembly(build_3x3_vertical_grid(), paths["grid_step"], paths["grid_stl"])
    export_stl_as_3mf(paths["grid_stl"], paths["grid_3mf"], title=f"{STEM} vertical 3x3 print grid")
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
