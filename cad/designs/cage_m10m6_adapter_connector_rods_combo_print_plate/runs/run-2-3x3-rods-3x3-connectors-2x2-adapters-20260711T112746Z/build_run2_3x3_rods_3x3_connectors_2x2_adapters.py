#!/usr/bin/env python3
"""Build run 2: 3x3 rods, 3x3 connectors, and 2x2 M10-to-M6 adapters."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import cadquery as cq
from cadquery import exporters
import trimesh
import trimesh.transformations as tf


def find_repo_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "cad/tools/simple_3mf.py").exists():
            return parent
    raise RuntimeError("Could not locate AgenticApp repository root")


DESIGN_DIR = Path(__file__).resolve().parent
ROOT = find_repo_root(DESIGN_DIR)
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_combo_run2_3x3rods_3x3connectors_2x2adapters"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "cage_m10m6_adapter_connector_rods_combo_print_plate"
    / "run-2-3x3-rods-3x3-connectors-2x2-adapters-print-ready"
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


SOURCES = {
    "single_rod": {
        "step": ROOT / "cad/designs/cage_rods_50mm_m6/USE_THIS_cage_rods_50mm_m6_smooth_rod.step",
        "stl": ROOT / "cad/designs/cage_rods_50mm_m6/artifacts/cage_rods_50mm_m6_smooth_rod.stl",
    },
    "connectors_3x3": {
        "step": ROOT
        / "cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.stl",
    },
    "adapters_2x2": {
        "step": ROOT
        / "cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.stl",
    },
}

PARAMS = {
    "name": STEM,
    "design_intent": "Smaller combined print run: nine horizontal rods, nine upright connectors, and four upright M10-to-M6 adapters.",
    "rod_count_rows": 3,
    "rod_count_cols": 3,
    "rod_length_mm": 50.0,
    "rod_diameter_mm": 6.0,
    "rod_x_pitch_mm": 58.0,
    "rod_y_pitch_mm": 12.0,
    "clearance_between_groups_mm": 8.0,
    "orientation_note": "Rods are kept horizontal for print stability. Vertical rods have rounder XY cross-section but are fragile 50 mm towers.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geom
            for geom in loaded.geometry.values()
            if isinstance(geom, trimesh.Trimesh) and len(geom.faces) > 0
        ]
        if not meshes:
            raise ValueError(f"No mesh geometry found in {path}")
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ValueError(f"No triangle mesh found in {path}")
    return loaded.copy()


def bounds_for_mesh(mesh: trimesh.Trimesh) -> dict[str, list[float]]:
    return {
        "min": [round(float(v), 3) for v in mesh.bounds[0]],
        "max": [round(float(v), 3) for v in mesh.bounds[1]],
        "size": [round(float(v), 3) for v in (mesh.bounds[1] - mesh.bounds[0])],
    }


def place_mesh_min(mesh: trimesh.Trimesh, target: tuple[float, float, float]) -> trimesh.Trimesh:
    moved = mesh.copy()
    moved.apply_translation(
        [
            target[0] - float(moved.bounds[0][0]),
            target[1] - float(moved.bounds[0][1]),
            target[2] - float(moved.bounds[0][2]),
        ]
    )
    return moved


def horizontal_rod_mesh() -> trimesh.Trimesh:
    rod = load_mesh(SOURCES["single_rod"]["stl"])
    rod.apply_transform(tf.rotation_matrix(math.radians(90.0), [0, 1, 0]))
    return rod


def rod_grid_mesh() -> trimesh.Trimesh:
    p = PARAMS
    rod = horizontal_rod_mesh()
    rods = []
    for row in range(int(p["rod_count_rows"])):
        for col in range(int(p["rod_count_cols"])):
            rods.append(
                place_mesh_min(
                    rod,
                    (
                        col * float(p["rod_x_pitch_mm"]),
                        row * float(p["rod_y_pitch_mm"]),
                        0.0,
                    ),
                )
            )
    return trimesh.util.concatenate(rods)


def build_combined_stl(path: Path) -> dict[str, dict[str, object]]:
    rods = rod_grid_mesh()
    connectors = load_mesh(SOURCES["connectors_3x3"]["stl"])
    adapters = load_mesh(SOURCES["adapters_2x2"]["stl"])

    clearance = float(PARAMS["clearance_between_groups_mm"])
    y_above_rods = float(rods.bounds[1][1] - rods.bounds[0][1] + clearance)
    connectors = place_mesh_min(connectors, (0.0, y_above_rods, 0.0))
    adapters = place_mesh_min(
        adapters,
        (float(connectors.bounds[1][0] - connectors.bounds[0][0] + clearance), y_above_rods, 0.0),
    )
    combined = trimesh.util.concatenate([rods, connectors, adapters])
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(path)
    return {
        "rods_3x3": {
            "placed_bounds_mm": bounds_for_mesh(rods),
            "component_count": len(rods.split(only_watertight=False)),
            "source_stl": repo_path(SOURCES["single_rod"]["stl"]),
            "source_step": repo_path(SOURCES["single_rod"]["step"]),
        },
        "connectors_3x3": {
            "placed_bounds_mm": bounds_for_mesh(connectors),
            "component_count": len(connectors.split(only_watertight=False)),
            "source_stl": repo_path(SOURCES["connectors_3x3"]["stl"]),
            "source_step": repo_path(SOURCES["connectors_3x3"]["step"]),
        },
        "adapters_2x2": {
            "placed_bounds_mm": bounds_for_mesh(adapters),
            "component_count": len(adapters.split(only_watertight=False)),
            "source_stl": repo_path(SOURCES["adapters_2x2"]["stl"]),
            "source_step": repo_path(SOURCES["adapters_2x2"]["step"]),
        },
        "combined": {
            "placed_bounds_mm": bounds_for_mesh(combined),
            "component_count": len(combined.split(only_watertight=False)),
            "watertight": bool(combined.is_watertight),
        },
    }


def place_shape_min(shape: cq.Shape, target: tuple[float, float, float]) -> cq.Shape:
    bb = shape.BoundingBox()
    return shape.translate((target[0] - bb.xmin, target[1] - bb.ymin, target[2] - bb.zmin))


def horizontal_rod_shape() -> cq.Shape:
    shape = cq.importers.importStep(str(SOURCES["single_rod"]["step"])).val()
    return shape.rotate((0, 0, 0), (0, 1, 0), 90)


def add_rod_grid_to_assembly(assembly: cq.Assembly) -> cq.Shape:
    p = PARAMS
    rod = horizontal_rod_shape()
    rod_shapes = []
    for row in range(int(p["rod_count_rows"])):
        for col in range(int(p["rod_count_cols"])):
            index = row * int(p["rod_count_cols"]) + col + 1
            placed = place_shape_min(
                rod,
                (
                    col * float(p["rod_x_pitch_mm"]),
                    row * float(p["rod_y_pitch_mm"]),
                    0.0,
                ),
            )
            assembly.add(placed, name=f"horizontal_rod_{index:02d}", color=cq.Color(0.72, 0.72, 0.68, 1.0))
            rod_shapes.append(placed)
    return cq.Compound.makeCompound(rod_shapes)


def build_combined_step(path: Path) -> None:
    assembly = cq.Assembly(name=STEM)
    rod_compound = add_rod_grid_to_assembly(assembly)
    rods_bb = rod_compound.BoundingBox()
    y_above_rods = rods_bb.ylen + float(PARAMS["clearance_between_groups_mm"])

    connectors = cq.importers.importStep(str(SOURCES["connectors_3x3"]["step"])).val()
    connectors = place_shape_min(connectors, (0.0, y_above_rods, 0.0))
    assembly.add(connectors, name="connectors_3x3", color=cq.Color(0.12, 0.12, 0.11, 1.0))

    conn_bb = connectors.BoundingBox()
    adapters = cq.importers.importStep(str(SOURCES["adapters_2x2"]["step"])).val()
    adapters = place_shape_min(
        adapters,
        (conn_bb.xlen + float(PARAMS["clearance_between_groups_mm"]), y_above_rods, 0.0),
    )
    assembly.add(adapters, name="adapters_2x2", color=cq.Color(0.36, 0.32, 0.24, 1.0))
    exporters.export(assembly.toCompound(), str(path))


def validate(paths: dict[str, Path]) -> dict[str, object]:
    mesh = load_mesh(paths["print_stl"])
    checks: dict[str, object] = {
        "stl_watertight": bool(mesh.is_watertight),
        "stl_component_count": len(mesh.split(only_watertight=False)),
        "stl_bounds_mm": bounds_for_mesh(mesh),
    }
    with zipfile.ZipFile(paths["print_3mf"]) as archive:
        checks["threemf_entries"] = sorted(archive.namelist())
    shape = cq.importers.importStep(str(paths["print_step"])).val()
    bb = shape.BoundingBox()
    checks["step_solid_count"] = len(shape.Solids())
    checks["step_bounds_mm"] = [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)]
    return checks


def write_manifest(path: Path, outputs: dict[str, str], layout: dict[str, dict[str, object]], checks: dict[str, object]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "parameters": PARAMS,
        "layout": layout,
        "validation": checks,
        "outputs": outputs,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str], layout: dict[str, dict[str, object]], checks: dict[str, object]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    group_rows = "\n".join(
        f"| {name} | {data['component_count']} | `{data['placed_bounds_mm']['size']}` |"
        for name, data in layout.items()
        if name != "combined"
    )
    path.write_text(
        f"""# Run 2: 3x3 Rods, 3x3 Connectors, 2x2 M10-M6 Adapters

This run is a smaller combined print plate than the first 25-rod batch. It keeps
the rods horizontal for print reliability and preserves the source orientation
for the connectors and M10-to-M6 adapters.

## Horizontal vs Vertical Rods

For these printed 50 mm x 6 mm rods, horizontal is the safer default: less tall
wobble, much better bed stability, and lower failure risk. Vertical gives a
rounder XY cross-section, but a 50 mm tall 6 mm tower is fragile without a brim
or raft. For precision cage rods, bought metal rods are still better.

## Packed Groups

| Group | Bodies | Size mm |
| --- | ---: | --- |
{group_rows}

Combined STL: `{checks['stl_component_count']}` bodies, watertight:
`{checks['stl_watertight']}`, bounds `{checks['stl_bounds_mm']['size']} mm`.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}
""",
        encoding="utf-8",
    )


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        print("warning: blender not found; skipping render", file=sys.stderr)
        return
    subprocess.run(
        [blender, "--background", "--python", str(DESIGN_DIR / "render_run2_3x3_rods_3x3_connectors_2x2_adapters.py")],
        check=True,
    )


def sync_print_ready(files: list[Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for src in files:
        if src.exists():
            shutil.copy2(src, NUTSTORE_DIR / src.name)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for source in SOURCES.values():
        for key in ("step", "stl"):
            if not source[key].exists():
                raise FileNotFoundError(source[key])

    paths = {
        "print_step": ARTIFACT_DIR / f"{STEM}.step",
        "print_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "print_3mf": ARTIFACT_DIR / f"{STEM}.3mf",
        "render_png": ARTIFACT_DIR / f"{STEM}_render.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }
    layout = build_combined_stl(paths["print_stl"])
    build_combined_step(paths["print_step"])
    export_stl_as_3mf(paths["print_stl"], paths["print_3mf"], title=STEM)

    root_step = DESIGN_DIR / f"PRINT_THIS_{STEM}.step"
    root_stl = DESIGN_DIR / f"PRINT_THIS_{STEM}.stl"
    root_3mf = DESIGN_DIR / f"PRINT_THIS_{STEM}.3mf"
    for src, dst in ((paths["print_step"], root_step), (paths["print_stl"], root_stl), (paths["print_3mf"], root_3mf)):
        shutil.copy2(src, dst)

    outputs = {
        "print_step": str(paths["print_step"].resolve()),
        "print_stl": str(paths["print_stl"].resolve()),
        "print_3mf": str(paths["print_3mf"].resolve()),
        "root_print_step": str(root_step.resolve()),
        "root_print_stl": str(root_stl.resolve()),
        "root_print_3mf": str(root_3mf.resolve()),
        "render_png": str(paths["render_png"].resolve()),
        "root_render_png": str((DESIGN_DIR / f"PRINT_THIS_{STEM}_render.png").resolve()),
        "nutstore_print_ready_folder": str(NUTSTORE_DIR),
    }
    checks = validate(paths)
    write_manifest(paths["manifest"], outputs, layout, checks)
    write_readme(DESIGN_DIR / "README.md", outputs, layout, checks)
    render_with_blender()
    root_render = DESIGN_DIR / f"PRINT_THIS_{STEM}_render.png"
    if paths["render_png"].exists():
        shutil.copy2(paths["render_png"], root_render)
    sync_print_ready([root_step, root_stl, root_3mf, root_render, DESIGN_DIR / "README.md", paths["manifest"]])

    print(json.dumps({"outputs": outputs, "validation": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
