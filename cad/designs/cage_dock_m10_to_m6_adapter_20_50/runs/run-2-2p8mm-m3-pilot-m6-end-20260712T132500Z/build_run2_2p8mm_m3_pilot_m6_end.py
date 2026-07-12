#!/usr/bin/env python3
"""Build run 2: exact M10-to-M6 adapter with a 2.8 mm M3 pilot in the M6 end."""

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
STEM = "cage_dock_adapter_run2_2p8mm_m3_pilot_m6_end"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / DESIGN_DIR.name / RUN_DIR.name
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "design_intent": "Exact smooth M10-to-M6 dock adapter with a measured 2.8 mm x 6 mm M3 pilot hole in the top M6 end.",
    "dock_hole_reference_diameter_mm": 10.0,
    "lower_insert_diameter_mm": 10.0,
    "lower_insert_length_mm": 20.0,
    "upper_rod_diameter_mm": 6.0,
    "upper_rod_length_mm": 50.0,
    "total_height_mm": 70.0,
    "m3_pilot_hole_diameter_mm": 2.8,
    "m3_pilot_hole_depth_from_top_mm": 6.0,
    "lead_in_chamfer_mm": 0.25,
    "top_chamfer_mm": 0.18,
    "print_grid_rows": 2,
    "print_grid_cols": 2,
    "print_grid_pitch_mm": 25.0,
    "thread_note": "M10/M6 are smooth diameter classes. The 2.8 mm feature is a blind M3 pilot/tap hole, not a modeled helical thread.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def build_adapter() -> cq.Workplane:
    p = PARAMS
    lower = cylinder(p["lower_insert_diameter_mm"], p["lower_insert_length_mm"], 0.0)
    upper = cylinder(p["upper_rod_diameter_mm"], p["upper_rod_length_mm"], p["lower_insert_length_mm"])
    part = lower.union(upper)
    hole = cylinder(
        p["m3_pilot_hole_diameter_mm"],
        p["m3_pilot_hole_depth_from_top_mm"] + 0.1,
        p["total_height_mm"] - p["m3_pilot_hole_depth_from_top_mm"],
    )
    part = part.cut(hole)
    part = part.faces("<Z").edges().chamfer(p["lead_in_chamfer_mm"])
    part = part.faces(">Z").edges().chamfer(p["top_chamfer_mm"])
    return part


def build_2x2_grid() -> cq.Assembly:
    p = PARAMS
    assembly = cq.Assembly(name=f"{STEM}_2x2_print_grid")
    for row in range(int(p["print_grid_rows"])):
        for col in range(int(p["print_grid_cols"])):
            index = row * int(p["print_grid_cols"]) + col + 1
            x = (col - (int(p["print_grid_cols"]) - 1) / 2.0) * p["print_grid_pitch_mm"]
            y = (row - (int(p["print_grid_rows"]) - 1) / 2.0) * p["print_grid_pitch_mm"]
            assembly.add(
                build_adapter().translate((x, y, 0)),
                name=f"m10_to_m6_m3_pilot_adapter_{index:02d}",
                color=cq.Color(0.34, 0.30, 0.23, 1.0),
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
    subprocess.run([blender, "--background", "--python", str(RUN_DIR / "render_run2_2p8mm_m3_pilot_m6_end.py")], check=True)


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
        f"""# Run 2: Exact M10 To M6 Adapter With 2.8 mm M3 Pilot

This run keeps the successful exact smooth dimensions from run 1 and adds a
blind M3 pilot/tap hole in the top M6 end.

## Geometry

- Lower insert: `{p['lower_insert_diameter_mm']} mm` diameter x `{p['lower_insert_length_mm']} mm`.
- Upper rod: `{p['upper_rod_diameter_mm']} mm` diameter x `{p['upper_rod_length_mm']} mm`.
- Pilot hole in M6 end: `{p['m3_pilot_hole_diameter_mm']} mm` diameter x `{p['m3_pilot_hole_depth_from_top_mm']} mm` deep.
- Direct print grid: `{p['print_grid_rows']} x {p['print_grid_cols']}` upright adapters.

The M10 and M6 names are smooth diameter classes here. The small hole is not a
modeled helical thread; it is a cylindrical pilot for an M3 screw/tap/self-
tapping screw.

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
