#!/usr/bin/env python3
"""Build one combined print plate for cage adapters, connectors, and rods."""

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


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "cage_m10m6_adapter_connector_rods_combo_print_plate"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / STEM
    / "run-1-combo-print-ready"
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


SOURCES = {
    "rods_5x5": {
        "label": "5x5 grid of 50 mm M6 / 6 mm cage rods",
        "step": ROOT
        / "cad/designs/cage_rods_50mm_m6/PRINT_THIS_cage_rods_50mm_m6_25rod_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_rods_50mm_m6/PRINT_THIS_cage_rods_50mm_m6_25rod_print_grid.stl",
        "color": [0.72, 0.72, 0.68, 1.0],
    },
    "connectors_3x3": {
        "label": "3x3 grid of 13 mm rod connectors",
        "step": ROOT
        / "cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_rod_connector_13mm_diaphragm/PRINT_THIS_cage_rod_connector_13mm_diaphragm_3x3_print_grid.stl",
        "color": [0.12, 0.12, 0.11, 1.0],
    },
    "adapters_2x2": {
        "label": "2x2 grid of M10 dock to M6 rod adapters",
        "step": ROOT
        / "cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_dock_m10_to_m6_adapter_20_50/PRINT_THIS_cage_dock_m10_to_m6_adapter_20_50_2x2_print_grid.stl",
        "color": [0.20, 0.20, 0.18, 1.0],
    },
}

PARAMS = {
    "name": STEM,
    "design_intent": "Single build-plate packing of the existing 2x2 M10-to-M6 adapters, 3x3 rod connectors, and 5x5 horizontal rods.",
    "clearance_between_groups_mm": 8.0,
    "packing_rule": "Preserve each source print orientation, normalize every source group to the build plate, place rods first, then use the upper-left free space for connectors and adapters.",
    "source_groups": {key: value["label"] for key, value in SOURCES.items()},
    "print_plate_note": "The 25-rod source grid is already long, so the combined plate needs a roughly 290 x 125 mm usable bed after slicer margin.",
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


def source_meshes() -> dict[str, trimesh.Trimesh]:
    return {name: load_mesh(source["stl"]) for name, source in SOURCES.items()}


def compute_placements(meshes: dict[str, trimesh.Trimesh]) -> dict[str, tuple[float, float, float]]:
    clearance = float(PARAMS["clearance_between_groups_mm"])
    rods_size = meshes["rods_5x5"].bounds[1] - meshes["rods_5x5"].bounds[0]
    connectors_size = meshes["connectors_3x3"].bounds[1] - meshes["connectors_3x3"].bounds[0]
    y_above_rods = float(rods_size[1] + clearance)
    return {
        "rods_5x5": (0.0, 0.0, 0.0),
        "connectors_3x3": (0.0, y_above_rods, 0.0),
        "adapters_2x2": (float(connectors_size[0] + clearance), y_above_rods, 0.0),
    }


def placed_mesh(name: str, mesh: trimesh.Trimesh, placement: tuple[float, float, float]) -> trimesh.Trimesh:
    moved = mesh.copy()
    translation = [
        placement[0] - float(moved.bounds[0][0]),
        placement[1] - float(moved.bounds[0][1]),
        placement[2] - float(moved.bounds[0][2]),
    ]
    moved.apply_translation(translation)
    return moved


def build_combined_stl(stl_path: Path) -> dict[str, dict[str, object]]:
    meshes = source_meshes()
    placements = compute_placements(meshes)
    placed = []
    layout: dict[str, dict[str, object]] = {}
    for name, mesh in meshes.items():
        moved = placed_mesh(name, mesh, placements[name])
        placed.append(moved)
        layout[name] = {
            "placement_min_xyz_mm": [round(float(v), 3) for v in placements[name]],
            "source_bounds_mm": bounds_for_mesh(mesh),
            "placed_bounds_mm": bounds_for_mesh(moved),
            "component_count": len(moved.split(only_watertight=False)),
            "source_stl": repo_path(SOURCES[name]["stl"]),
            "source_step": repo_path(SOURCES[name]["step"]),
        }

    combined = trimesh.util.concatenate(placed)
    stl_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(stl_path)
    layout["combined"] = {
        "placed_bounds_mm": bounds_for_mesh(combined),
        "component_count": len(combined.split(only_watertight=False)),
        "watertight": bool(combined.is_watertight),
    }
    return layout


def normalize_and_translate_shape(path: Path, placement: tuple[float, float, float]) -> cq.Shape:
    shape = cq.importers.importStep(str(path)).val()
    bb = shape.BoundingBox()
    return shape.translate(
        (
            placement[0] - bb.xmin,
            placement[1] - bb.ymin,
            placement[2] - bb.zmin,
        )
    )


def build_combined_step(step_path: Path, placements: dict[str, tuple[float, float, float]]) -> None:
    assembly = cq.Assembly(name=STEM)
    for name, source in SOURCES.items():
        color = source["color"]
        assembly.add(
            normalize_and_translate_shape(source["step"], placements[name]),
            name=name,
            color=cq.Color(*color),
        )
    exporters.export(assembly.toCompound(), str(step_path))


def write_readme(path: Path, outputs: dict[str, str], layout: dict[str, dict[str, object]]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    source_rows = "\n".join(
        f"| {name} | {data['component_count']} | `{data['placed_bounds_mm']['size']}` | `{data['placement_min_xyz_mm']}` |"
        for name, data in layout.items()
        if name in SOURCES
    )
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# Cage Combo Print Plate: M10-M6 Adapters, Connectors, And Rods

This design simply packs three already validated direct-print layouts onto one
build plate:

- 2x2 M10 dock to M6 rod adapters.
- 3x3 13 mm rod connectors with center diaphragm.
- 5x5 horizontal 50 mm M6 / 6 mm cage rods.

No individual part geometry is redesigned here. The script imports the existing
direct-print STEP/STL sources, normalizes each source group to the build plate,
and places them with `{PARAMS['clearance_between_groups_mm']} mm` clearance.

## Print Notes

Use the root `PRINT_THIS_*` files for slicing. The combined plate has
`{layout['combined']['component_count']}` separate printable bodies and is
watertight as an STL mesh. Its bounding box is
`{layout['combined']['placed_bounds_mm']['size']} mm`; allow extra slicer margin
around that footprint. The tall parts are the M10-to-M6 adapters, which remain
upright exactly like their source 2x2 print grid.

## Packed Groups

| Group | Bodies | Size mm | Placed min XYZ mm |
| --- | ---: | --- | --- |
{source_rows}

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


def write_manifest(path: Path, outputs: dict[str, str], layout: dict[str, dict[str, object]]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": PARAMS["design_intent"],
        "parameters": PARAMS,
        "sources": {
            name: {
                "label": source["label"],
                "step": repo_path(source["step"]),
                "stl": repo_path(source["stl"]),
            }
            for name, source in SOURCES.items()
        },
        "layout": layout,
        "outputs": outputs,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        print("warning: blender not found; skipping render", file=sys.stderr)
        return
    subprocess.run(
        [blender, "--background", "--python", str(DESIGN_DIR / f"render_{STEM}.py")],
        check=True,
    )


def sync_print_ready(outputs: dict[str, str]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        DESIGN_DIR / f"PRINT_THIS_{STEM}.step",
        DESIGN_DIR / f"PRINT_THIS_{STEM}.stl",
        DESIGN_DIR / f"PRINT_THIS_{STEM}.3mf",
        DESIGN_DIR / f"PRINT_THIS_{STEM}_render.png",
        DESIGN_DIR / "README.md",
        ARTIFACT_DIR / "manifest.json",
    ]
    for src in files:
        if src.exists():
            shutil.copy2(src, NUTSTORE_DIR / src.name)
    (NUTSTORE_DIR / "README.md").write_text((DESIGN_DIR / "README.md").read_text(encoding="utf-8"), encoding="utf-8")


def validate_outputs(paths: dict[str, Path]) -> dict[str, object]:
    mesh = load_mesh(paths["print_stl"])
    checks = {
        "stl_watertight": bool(mesh.is_watertight),
        "stl_component_count": len(mesh.split(only_watertight=False)),
        "stl_bounds_mm": bounds_for_mesh(mesh),
    }
    with zipfile.ZipFile(paths["print_3mf"]) as archive:
        checks["threemf_entries"] = sorted(archive.namelist())
    return checks


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "print_step": ARTIFACT_DIR / f"{STEM}.step",
        "print_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "print_3mf": ARTIFACT_DIR / f"{STEM}.3mf",
        "render_png": ARTIFACT_DIR / f"{STEM}_render.png",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }

    meshes = source_meshes()
    placements = compute_placements(meshes)
    layout = build_combined_stl(paths["print_stl"])
    build_combined_step(paths["print_step"], placements)
    export_stl_as_3mf(paths["print_stl"], paths["print_3mf"], title=STEM)

    root_print_step = DESIGN_DIR / f"PRINT_THIS_{STEM}.step"
    root_print_stl = DESIGN_DIR / f"PRINT_THIS_{STEM}.stl"
    root_print_3mf = DESIGN_DIR / f"PRINT_THIS_{STEM}.3mf"
    shutil.copy2(paths["print_step"], root_print_step)
    shutil.copy2(paths["print_stl"], root_print_stl)
    shutil.copy2(paths["print_3mf"], root_print_3mf)

    outputs = {
        "print_step": repo_path(paths["print_step"]),
        "print_stl": repo_path(paths["print_stl"]),
        "print_3mf": repo_path(paths["print_3mf"]),
        "root_print_step": repo_path(root_print_step),
        "root_print_stl": repo_path(root_print_stl),
        "root_print_3mf": repo_path(root_print_3mf),
        "render_png": repo_path(paths["render_png"]),
        "root_render_png": repo_path(DESIGN_DIR / f"PRINT_THIS_{STEM}_render.png"),
        "nutstore_print_ready_folder": str(NUTSTORE_DIR),
    }
    checks = validate_outputs(paths)
    layout["validation"] = checks
    write_manifest(paths["manifest"], outputs, layout)
    write_readme(DESIGN_DIR / "README.md", outputs, layout)

    render_with_blender()
    root_render = DESIGN_DIR / f"PRINT_THIS_{STEM}_render.png"
    if paths["render_png"].exists():
        shutil.copy2(paths["render_png"], root_render)
    sync_print_ready(outputs)

    print(json.dumps({"outputs": outputs, "validation": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
