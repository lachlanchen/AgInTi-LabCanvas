#!/usr/bin/env python3
"""Build run 3: exact rods, connectors, and adapters on one print plate."""

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
STEM = "cage_combo_run3_exact_vertical_rods_tight_connectors_exact_adapters"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / DESIGN_DIR.name
    / RUN_DIR.name
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


SOURCES = {
    "vertical_rods_3x3": {
        "step": ROOT
        / "cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/PRINT_THIS_cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_rods_50mm_m6/runs/run-1-exact-6mm-vertical-3x3-print-grid-20260712T025438Z/PRINT_THIS_cage_rods_run1_exact_6mm_vertical_3x3_vertical_3x3_print_grid.stl",
    },
    "tight_connectors_3x3": {
        "step": ROOT
        / "cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/PRINT_THIS_cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_rod_connector_13mm_diaphragm/runs/run-1-tight-m6-zero-clearance-21mm-20260712T024508Z/PRINT_THIS_cage_rod_connector_run1_tight_m6_zero_clearance_21mm_3x3_print_grid.stl",
    },
    "exact_adapters_2x2": {
        "step": ROOT
        / "cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/PRINT_THIS_cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.step",
        "stl": ROOT
        / "cad/designs/cage_dock_m10_to_m6_adapter_20_50/runs/run-1-exact-m10-to-m6-zero-clearance-20260712T030120Z/PRINT_THIS_cage_dock_adapter_run1_exact_m10_to_m6_zero_clearance_2x2_print_grid.stl",
    },
}

PARAMS = {
    "name": STEM,
    "design_intent": "Combined exact print plate: 3x3 vertical rods, 3x3 tight 21 mm connectors, and 2x2 exact M10-to-M6 adapters.",
    "rod_diameter_mm": 6.0,
    "rod_length_mm": 50.0,
    "connector_outer_diameter_mm": 8.0,
    "connector_socket_diameter_mm": 6.0,
    "connector_socket_depth_each_end_mm": 10.0,
    "connector_center_diaphragm_mm": 1.0,
    "adapter_lower_insert_diameter_mm": 10.0,
    "adapter_lower_insert_length_mm": 20.0,
    "adapter_upper_rod_diameter_mm": 6.0,
    "adapter_upper_rod_length_mm": 50.0,
    "clearance_between_groups_mm": 10.0,
    "print_orientation": "All components stand upright exactly as requested.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(str(path), force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [m for m in loaded.geometry.values() if isinstance(m, trimesh.Trimesh) and len(m.faces)]
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh) or not len(loaded.faces):
        raise ValueError(f"No mesh geometry in {path}")
    return loaded.copy()


def bounds_for_mesh(mesh: trimesh.Trimesh) -> dict[str, list[float]]:
    return {
        "min": [round(float(v), 3) for v in mesh.bounds[0]],
        "max": [round(float(v), 3) for v in mesh.bounds[1]],
        "size": [round(float(v), 3) for v in (mesh.bounds[1] - mesh.bounds[0])],
    }


def place_mesh_min(mesh: trimesh.Trimesh, target: tuple[float, float, float]) -> trimesh.Trimesh:
    moved = mesh.copy()
    moved.apply_translation(target - moved.bounds[0])
    return moved


def build_combined_mesh(path: Path) -> dict[str, dict[str, object]]:
    clearance = float(PARAMS["clearance_between_groups_mm"])
    rods = place_mesh_min(load_mesh(SOURCES["vertical_rods_3x3"]["stl"]), (0.0, 0.0, 0.0))
    connectors = load_mesh(SOURCES["tight_connectors_3x3"]["stl"])
    adapters = load_mesh(SOURCES["exact_adapters_2x2"]["stl"])

    connectors = place_mesh_min(connectors, (float(rods.bounds[1][0] + clearance), 0.0, 0.0))
    adapters = place_mesh_min(adapters, (float(connectors.bounds[1][0] + clearance), 0.0, 0.0))
    combined = trimesh.util.concatenate([rods, connectors, adapters])
    combined.export(path)
    return {
        "vertical_rods_3x3": {
            "component_count": len(rods.split(only_watertight=False)),
            "placed_bounds_mm": bounds_for_mesh(rods),
            "source_stl": repo_path(SOURCES["vertical_rods_3x3"]["stl"]),
            "source_step": repo_path(SOURCES["vertical_rods_3x3"]["step"]),
        },
        "tight_connectors_3x3": {
            "component_count": len(connectors.split(only_watertight=False)),
            "placed_bounds_mm": bounds_for_mesh(connectors),
            "source_stl": repo_path(SOURCES["tight_connectors_3x3"]["stl"]),
            "source_step": repo_path(SOURCES["tight_connectors_3x3"]["step"]),
        },
        "exact_adapters_2x2": {
            "component_count": len(adapters.split(only_watertight=False)),
            "placed_bounds_mm": bounds_for_mesh(adapters),
            "source_stl": repo_path(SOURCES["exact_adapters_2x2"]["stl"]),
            "source_step": repo_path(SOURCES["exact_adapters_2x2"]["step"]),
        },
        "combined": {
            "component_count": len(combined.split(only_watertight=False)),
            "watertight": bool(combined.is_watertight),
            "placed_bounds_mm": bounds_for_mesh(combined),
        },
    }


def place_shape_min(shape: cq.Shape, target: tuple[float, float, float]) -> cq.Shape:
    bb = shape.BoundingBox()
    return shape.translate((target[0] - bb.xmin, target[1] - bb.ymin, target[2] - bb.zmin))


def load_step_shape(path: Path) -> cq.Shape:
    return cq.importers.importStep(str(path)).val()


def build_combined_step(path: Path) -> None:
    clearance = float(PARAMS["clearance_between_groups_mm"])
    assembly = cq.Assembly(name=STEM)
    rods = place_shape_min(load_step_shape(SOURCES["vertical_rods_3x3"]["step"]), (0.0, 0.0, 0.0))
    rods_bb = rods.BoundingBox()
    assembly.add(rods, name="vertical_rods_3x3", color=cq.Color(0.64, 0.63, 0.59, 1.0))
    connectors = place_shape_min(
        load_step_shape(SOURCES["tight_connectors_3x3"]["step"]),
        (rods_bb.xlen + clearance, 0.0, 0.0),
    )
    conn_bb = connectors.BoundingBox()
    assembly.add(connectors, name="tight_connectors_3x3", color=cq.Color(0.12, 0.12, 0.11, 1.0))
    adapters = place_shape_min(
        load_step_shape(SOURCES["exact_adapters_2x2"]["step"]),
        (rods_bb.xlen + clearance + conn_bb.xlen + clearance, 0.0, 0.0),
    )
    assembly.add(adapters, name="exact_adapters_2x2", color=cq.Color(0.34, 0.3, 0.23, 1.0))
    exporters.export(assembly.toCompound(), str(path))


def validate_step(path: Path) -> dict[str, object]:
    shape = cq.importers.importStep(str(path)).val()
    bb = shape.BoundingBox()
    return {
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "solids": len(shape.Solids()),
        "bbox_mm": [round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6)],
    }


def validate_mesh(path: Path) -> dict[str, object]:
    mesh = load_mesh(path)
    return {
        "watertight": bool(mesh.is_watertight),
        "component_count": len(mesh.split(only_watertight=False)),
        "bounds": bounds_for_mesh(mesh),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as zf:
        names = sorted(zf.namelist())
    return {"entries": names, "has_model": "3D/3dmodel.model" in names}


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for print-ready render")
    subprocess.run([blender, "--background", "--python", str(RUN_DIR / "render_run3_exact_vertical_rods_tight_connectors_exact_adapters.py")], check=True)


def sync_print_ready(paths: dict[str, Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for key in ("print_this_step", "print_this_stl", "print_this_3mf", "print_this_render", "manifest", "readme"):
        source = paths[key]
        if source.exists():
            shutil.copy2(source, NUTSTORE_DIR / source.name)


def write_readme(path: Path, outputs: dict[str, str], layout: dict[str, object], validation: dict[str, object]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    group_rows = "\n".join(
        f"| {name} | {data['component_count']} | `{data['placed_bounds_mm']['size']}` |"
        for name, data in layout.items()
        if name != "combined"
    )
    path.write_text(
        f"""# Run 3: Exact Vertical Rods, Tight Connectors, Exact Adapters

This print plate uses only the exact-size parts:

- 3x3 vertical rods: `6.0 mm` diameter x `50.0 mm`.
- 3x3 tight connectors: `21.0 mm` long, `6.0 mm` sockets, `10.0 mm` socket depth each end, `1.0 mm` center diaphragm, `1.0 mm` radial wall.
- 2x2 exact adapters: `10.0 mm` lower insert x `20.0 mm`, then `6.0 mm` upper rod x `50.0 mm`.

M10/M6 are smooth diameter classes in these printed parts, not modeled screw
threads.

## Packed Groups

| Group | Bodies | Size mm |
| --- | ---: | --- |
{group_rows}

## Validation

```json
{json.dumps(validation, ensure_ascii=False, indent=2)}
```

## Outputs

| Output | Path |
| --- | --- |
{output_rows}
""",
        encoding="utf-8",
    )


def main() -> None:
    for source in SOURCES.values():
        for item in source.values():
            if not item.exists():
                raise FileNotFoundError(item)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "print_step": ARTIFACT_DIR / f"{STEM}.step",
        "print_stl": ARTIFACT_DIR / f"{STEM}.stl",
        "print_3mf": ARTIFACT_DIR / f"{STEM}.3mf",
        "manifest": ARTIFACT_DIR / "manifest.json",
        "print_this_step": RUN_DIR / f"PRINT_THIS_{STEM}.step",
        "print_this_stl": RUN_DIR / f"PRINT_THIS_{STEM}.stl",
        "print_this_3mf": RUN_DIR / f"PRINT_THIS_{STEM}.3mf",
        "print_this_render": RUN_DIR / f"PRINT_THIS_{STEM}_render.png",
        "readme": RUN_DIR / "README.md",
    }
    layout = build_combined_mesh(paths["print_stl"])
    build_combined_step(paths["print_step"])
    export_stl_as_3mf(paths["print_stl"], paths["print_3mf"], title=STEM)
    paths["print_this_step"].write_bytes(paths["print_step"].read_bytes())
    paths["print_this_stl"].write_bytes(paths["print_stl"].read_bytes())
    paths["print_this_3mf"].write_bytes(paths["print_3mf"].read_bytes())
    render_with_blender()
    validation = {
        "step": validate_step(paths["print_step"]),
        "stl": validate_mesh(paths["print_stl"]),
        "threemf": validate_3mf(paths["print_3mf"]),
    }
    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["manifest"] = repo_path(paths["manifest"])
    outputs["nutstore_print_ready_folder"] = str(NUTSTORE_DIR)
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "parameters": PARAMS,
        "sources": {name: {key: repo_path(path) for key, path in values.items()} for name, values in SOURCES.items()},
        "layout": layout,
        "validation": validation,
        "outputs": outputs,
    }
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_readme(paths["readme"], outputs, layout, validation)
    sync_print_ready(paths)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
