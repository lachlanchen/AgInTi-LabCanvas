#!/usr/bin/env python3
"""Build validated print-ready packages for simple cylindrical lab parts."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import zipfile
from typing import Any, Callable

import cadquery as cq
from cadquery import exporters
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_BSplineSurface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
import trimesh

from simple_3mf import export_stl_as_3mf


ShapeFactory = Callable[[], cq.Workplane]


def z_cylinder(diameter_mm: float, height_mm: float, z_min_mm: float = 0.0) -> cq.Workplane:
    return (
        cq.Workplane("XY", origin=(0.0, 0.0, z_min_mm))
        .circle(diameter_mm / 2.0)
        .extrude(height_mm)
    )


def annular_spacer(inner_diameter_mm: float, outer_diameter_mm: float, height_mm: float) -> cq.Workplane:
    if inner_diameter_mm <= 0 or outer_diameter_mm <= inner_diameter_mm or height_mm <= 0:
        raise ValueError("spacer dimensions must satisfy 0 < ID < OD and height > 0")
    outer = z_cylinder(outer_diameter_mm, height_mm)
    bore = z_cylinder(inner_diameter_mm, height_mm + 0.2, -0.1)
    return outer.cut(bore)


def stepped_adapter(
    lower_diameter_mm: float,
    lower_length_mm: float,
    upper_diameter_mm: float,
    upper_length_mm: float,
    chamfer_mm: float = 0.25,
) -> cq.Workplane:
    if min(lower_diameter_mm, lower_length_mm, upper_diameter_mm, upper_length_mm) <= 0:
        raise ValueError("adapter dimensions must be positive")
    lower = z_cylinder(lower_diameter_mm, lower_length_mm)
    upper = z_cylinder(upper_diameter_mm, upper_length_mm, lower_length_mm)
    part = lower.union(upper)
    if chamfer_mm > 0:
        part = part.faces("<Z").edges().chamfer(chamfer_mm)
        part = part.faces(">Z").edges().chamfer(chamfer_mm)
    return part


def grid_assembly(
    factory: ShapeFactory,
    *,
    rows: int,
    cols: int,
    pitch_mm: float,
    name: str,
    part_prefix: str,
    color: tuple[float, float, float, float],
) -> cq.Assembly:
    if rows < 1 or cols < 1 or pitch_mm <= 0:
        raise ValueError("grid dimensions must be positive")
    assembly = cq.Assembly(name=name)
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col + 1
            x = (col - (cols - 1) / 2.0) * pitch_mm
            y = (row - (rows - 1) / 2.0) * pitch_mm
            assembly.add(
                factory().translate((x, y, 0.0)),
                name=f"{part_prefix}_{index:02d}",
                color=cq.Color(*color),
            )
    return assembly


def export_part(part: cq.Workplane, step_path: Path, stl_path: Path) -> None:
    step_path.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(part, str(step_path))
    exporters.export(part, str(stl_path))


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    step_path.parent.mkdir(parents=True, exist_ok=True)
    compound = assembly.toCompound()
    exporters.export(compound, str(step_path))
    exporters.export(compound, str(stl_path))


def validate_step(path: Path) -> dict[str, Any]:
    shape = cq.importers.importStep(str(path)).val()
    bb = shape.BoundingBox()
    face = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    bspline_faces = 0
    while face.More():
        current = TopoDS.Face_s(face.Current())
        if BRepAdaptor_Surface(current, True).GetType() == GeomAbs_BSplineSurface:
            bspline_faces += 1
        face.Next()
    return {
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "solids": len(shape.Solids()),
        "bbox_mm": [round(bb.xlen, 6), round(bb.ylen, 6), round(bb.zlen, 6)],
        "bspline_faces": bspline_faces,
    }


def validate_mesh(path: Path) -> dict[str, Any]:
    mesh = trimesh.load(str(path), force="mesh")
    components = mesh.split(only_watertight=False)
    return {
        "watertight": bool(mesh.is_watertight),
        "component_count": len(components),
        "bbox_mm": [round(float(value), 6) for value in (mesh.bounds[1] - mesh.bounds[0])],
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        entries = sorted(archive.namelist())
        model = archive.read("3D/3dmodel.model")
    return {
        "entries": entries,
        "has_model": "3D/3dmodel.model" in entries,
        "model_bytes": len(model),
    }


def assert_geometry(
    label: str,
    validation: dict[str, Any],
    *,
    solids: int,
    bbox_mm: tuple[float, float, float],
    tolerance_mm: float = 0.02,
) -> None:
    if not validation.get("valid"):
        raise RuntimeError(f"{label} STEP is not a valid B-rep")
    if int(validation.get("solids") or 0) != solids:
        raise RuntimeError(f"{label} has {validation.get('solids')} solids; expected {solids}")
    observed = validation.get("bbox_mm") or []
    if len(observed) != 3 or any(abs(float(got) - expected) > tolerance_mm for got, expected in zip(observed, bbox_mm)):
        raise RuntimeError(f"{label} bbox {observed} does not match expected {bbox_mm}")
    if int(validation.get("bspline_faces") or 0) != 0:
        raise RuntimeError(f"{label} contains unexpected B-spline faces")


def render_stl(root: Path, stl_path: Path, output_path: Path, color: tuple[float, float, float]) -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for CAD render generation")
    subprocess.run(
        [
            blender,
            "--background",
            "--python",
            str(root / "cad" / "tools" / "render_stl_product.py"),
            "--",
            "--input",
            str(stl_path),
            "--output",
            str(output_path),
            "--color",
            *(f"{value:.4f}" for value in color),
        ],
        check=True,
    )


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_named_files(paths: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.is_file():
            copy_file(path, destination / path.name)


def repo_path(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_package(
    *,
    root: Path,
    design_dir: Path,
    run_dir: Path,
    artifact_paths: list[Path],
    direct_paths: list[Path],
    use_paths: list[Path],
    support_paths: list[Path],
) -> dict[str, str]:
    latest_artifacts = design_dir / "artifacts"
    root_labcanvas = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    nutstore_run = root_labcanvas / design_dir.name / run_dir.name
    copy_named_files(artifact_paths, latest_artifacts)
    copy_named_files(direct_paths + use_paths + support_paths, design_dir)
    copy_named_files(direct_paths + use_paths + support_paths, nutstore_run)
    copy_named_files(use_paths, root_labcanvas)
    return {
        "latest_artifacts": repo_path(root, latest_artifacts),
        "nutstore_run": str(nutstore_run),
        "nutstore_root": str(root_labcanvas),
    }


def build_ring_design(
    *,
    root: Path,
    design_dir: Path,
    run_name: str,
    stem: str,
    inner_diameter_mm: float,
    outer_diameter_mm: float,
    short_height_mm: float = 5.0,
    tall_height_mm: float = 50.0,
    rows: int = 4,
    cols: int = 4,
    pitch_mm: float = 15.0,
    color: tuple[float, float, float] = (0.16, 0.58, 0.66),
    source_path: Path | None = None,
) -> dict[str, Any]:
    run_dir = design_dir / "runs" / run_name
    artifacts = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    radial_wall = (outer_diameter_mm - inner_diameter_mm) / 2.0
    short_factory = lambda: annular_spacer(inner_diameter_mm, outer_diameter_mm, short_height_mm)
    tall_factory = lambda: annular_spacer(inner_diameter_mm, outer_diameter_mm, tall_height_mm)
    grid = grid_assembly(
        short_factory,
        rows=rows,
        cols=cols,
        pitch_mm=pitch_mm,
        name=f"{stem}_{rows}x{cols}_h{short_height_mm:g}_print_grid",
        part_prefix="spacer",
        color=(*color, 1.0),
    )

    short_step = artifacts / f"{stem}_single_h{short_height_mm:g}.step"
    short_stl = artifacts / f"{stem}_single_h{short_height_mm:g}.stl"
    grid_step = artifacts / f"{stem}_{rows}x{cols}_h{short_height_mm:g}_print_grid.step"
    grid_stl = artifacts / f"{stem}_{rows}x{cols}_h{short_height_mm:g}_print_grid.stl"
    grid_3mf = artifacts / f"{stem}_{rows}x{cols}_h{short_height_mm:g}_print_grid.3mf"
    tall_step = artifacts / f"{stem}_single_h{tall_height_mm:g}.step"
    tall_stl = artifacts / f"{stem}_single_h{tall_height_mm:g}.stl"
    tall_3mf = artifacts / f"{stem}_single_h{tall_height_mm:g}.3mf"

    export_part(short_factory(), short_step, short_stl)
    export_assembly(grid, grid_step, grid_stl)
    export_part(tall_factory(), tall_step, tall_stl)
    export_stl_as_3mf(grid_stl, grid_3mf, title=f"{stem} {rows}x{cols} short spacer grid")
    export_stl_as_3mf(tall_stl, tall_3mf, title=f"{stem} single {tall_height_mm:g} mm spacer")

    grid_print = [
        run_dir / f"PRINT_THIS_{stem}_{rows}x{cols}_h{short_height_mm:g}_print_grid{suffix}"
        for suffix in (".step", ".stl", ".3mf")
    ]
    tall_print = [
        run_dir / f"PRINT_THIS_{stem}_single_h{tall_height_mm:g}{suffix}"
        for suffix in (".step", ".stl", ".3mf")
    ]
    for source, target in zip((grid_step, grid_stl, grid_3mf), grid_print):
        copy_file(source, target)
    for source, target in zip((tall_step, tall_stl, tall_3mf), tall_print):
        copy_file(source, target)
    use_short = run_dir / f"USE_THIS_{stem}_single_h{short_height_mm:g}.step"
    use_tall = run_dir / f"USE_THIS_{stem}_single_h{tall_height_mm:g}.step"
    copy_file(short_step, use_short)
    copy_file(tall_step, use_tall)
    grid_render = run_dir / f"PRINT_THIS_{stem}_{rows}x{cols}_h{short_height_mm:g}_print_grid_render.png"
    tall_render = run_dir / f"PRINT_THIS_{stem}_single_h{tall_height_mm:g}_render.png"
    render_stl(root, grid_print[1], grid_render, color)
    render_stl(root, tall_print[1], tall_render, color)

    validation = {
        "single_short_step": validate_step(short_step),
        "single_short_stl": validate_mesh(short_stl),
        "short_grid_step": validate_step(grid_step),
        "short_grid_stl": validate_mesh(grid_stl),
        "short_grid_3mf": validate_3mf(grid_3mf),
        "single_tall_step": validate_step(tall_step),
        "single_tall_stl": validate_mesh(tall_stl),
        "single_tall_3mf": validate_3mf(tall_3mf),
    }
    grid_width = (cols - 1) * pitch_mm + outer_diameter_mm
    grid_depth = (rows - 1) * pitch_mm + outer_diameter_mm
    assert_geometry(
        "short spacer",
        validation["single_short_step"],
        solids=1,
        bbox_mm=(outer_diameter_mm, outer_diameter_mm, short_height_mm),
    )
    assert_geometry(
        "short spacer grid",
        validation["short_grid_step"],
        solids=rows * cols,
        bbox_mm=(grid_width, grid_depth, short_height_mm),
    )
    assert_geometry(
        "tall spacer",
        validation["single_tall_step"],
        solids=1,
        bbox_mm=(outer_diameter_mm, outer_diameter_mm, tall_height_mm),
    )
    if validation["short_grid_stl"]["component_count"] != rows * cols:
        raise RuntimeError("short spacer STL does not contain the requested independent grid parts")
    if validation["single_tall_stl"]["component_count"] != 1:
        raise RuntimeError("tall spacer STL must contain exactly one part")

    parameters = {
        "inner_diameter_mm": inner_diameter_mm,
        "outer_diameter_mm": outer_diameter_mm,
        "radial_wall_thickness_mm": radial_wall,
        "short_height_mm": short_height_mm,
        "tall_height_mm": tall_height_mm,
        "short_grid_rows": rows,
        "short_grid_cols": cols,
        "short_grid_pitch_mm": pitch_mm,
        "fit_compensation_mm": 0.0,
        "print_orientation": "All parts upright on an annular end face; use a slicer brim for the 50 mm tube if needed.",
    }
    manifest_path = artifacts / "manifest.json"
    run_readme = run_dir / "README.md"
    outputs = {
        "short_grid_print_step": repo_path(root, grid_print[0]),
        "short_grid_print_stl": repo_path(root, grid_print[1]),
        "short_grid_print_3mf": repo_path(root, grid_print[2]),
        "tall_single_print_step": repo_path(root, tall_print[0]),
        "tall_single_print_stl": repo_path(root, tall_print[1]),
        "tall_single_print_3mf": repo_path(root, tall_print[2]),
        "short_grid_render": repo_path(root, grid_render),
        "tall_single_render": repo_path(root, tall_render),
        "short_single_step": repo_path(root, use_short),
        "tall_single_step": repo_path(root, use_tall),
    }
    manifest = {
        "schema_version": 1,
        "name": stem,
        "design_kind": "annular_spacer",
        "design_intent": "Two exact-diameter hollow spacer print jobs: sixteen short rings and one tall tube.",
        "parameters": parameters,
        "outputs": outputs,
        "validation": validation,
    }
    write_json(manifest_path, manifest)
    write_ring_readme(run_readme, stem, parameters, outputs, validation)
    if source_path and source_path.is_file():
        copy_file(source_path, run_dir / source_path.name)
    sync = sync_package(
        root=root,
        design_dir=design_dir,
        run_dir=run_dir,
        artifact_paths=[short_step, short_stl, grid_step, grid_stl, grid_3mf, tall_step, tall_stl, tall_3mf, manifest_path],
        direct_paths=grid_print + tall_print,
        use_paths=[use_short, use_tall],
        support_paths=[grid_render, tall_render, run_readme],
    )
    manifest["sync"] = sync
    write_json(manifest_path, manifest)
    copy_file(manifest_path, design_dir / "artifacts" / "manifest.json")
    copy_file(manifest_path, Path(sync["nutstore_run"]) / "manifest.json")
    write_design_index(design_dir / "README.md", stem, run_name, outputs, parameters)
    return manifest


def build_adapter_design(
    *,
    root: Path,
    design_dir: Path,
    run_name: str,
    stem: str,
    lower_diameter_mm: float,
    lower_length_mm: float,
    upper_diameter_mm: float,
    upper_length_mm: float,
    rows: int = 2,
    cols: int = 2,
    pitch_mm: float = 25.0,
    chamfer_mm: float = 0.25,
    color: tuple[float, float, float] = (0.82, 0.42, 0.16),
    source_path: Path | None = None,
) -> dict[str, Any]:
    run_dir = design_dir / "runs" / run_name
    artifacts = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    factory = lambda: stepped_adapter(
        lower_diameter_mm,
        lower_length_mm,
        upper_diameter_mm,
        upper_length_mm,
        chamfer_mm,
    )
    grid = grid_assembly(
        factory,
        rows=rows,
        cols=cols,
        pitch_mm=pitch_mm,
        name=f"{stem}_{rows}x{cols}_print_grid",
        part_prefix="adapter",
        color=(*color, 1.0),
    )
    single_step = artifacts / f"{stem}_single.step"
    single_stl = artifacts / f"{stem}_single.stl"
    grid_step = artifacts / f"{stem}_{rows}x{cols}_print_grid.step"
    grid_stl = artifacts / f"{stem}_{rows}x{cols}_print_grid.stl"
    grid_3mf = artifacts / f"{stem}_{rows}x{cols}_print_grid.3mf"
    export_part(factory(), single_step, single_stl)
    export_assembly(grid, grid_step, grid_stl)
    export_stl_as_3mf(grid_stl, grid_3mf, title=f"{stem} {rows}x{cols} print grid")

    print_paths = [
        run_dir / f"PRINT_THIS_{stem}_{rows}x{cols}_print_grid{suffix}"
        for suffix in (".step", ".stl", ".3mf")
    ]
    for source, target in zip((grid_step, grid_stl, grid_3mf), print_paths):
        copy_file(source, target)
    use_single = run_dir / f"USE_THIS_{stem}_single.step"
    copy_file(single_step, use_single)
    grid_render = run_dir / f"PRINT_THIS_{stem}_{rows}x{cols}_print_grid_render.png"
    single_render = run_dir / f"USE_THIS_{stem}_single_render.png"
    render_stl(root, print_paths[1], grid_render, color)
    render_stl(root, single_stl, single_render, color)

    total_height = lower_length_mm + upper_length_mm
    grid_width = (cols - 1) * pitch_mm + lower_diameter_mm
    grid_depth = (rows - 1) * pitch_mm + lower_diameter_mm
    validation = {
        "single_step": validate_step(single_step),
        "single_stl": validate_mesh(single_stl),
        "grid_step": validate_step(grid_step),
        "grid_stl": validate_mesh(grid_stl),
        "grid_3mf": validate_3mf(grid_3mf),
    }
    assert_geometry(
        "adapter",
        validation["single_step"],
        solids=1,
        bbox_mm=(lower_diameter_mm, lower_diameter_mm, total_height),
    )
    assert_geometry(
        "adapter grid",
        validation["grid_step"],
        solids=rows * cols,
        bbox_mm=(grid_width, grid_depth, total_height),
    )
    if validation["grid_stl"]["component_count"] != rows * cols:
        raise RuntimeError("adapter STL does not contain the requested independent grid parts")

    parameters = {
        "lower_insert_diameter_mm": lower_diameter_mm,
        "lower_insert_length_mm": lower_length_mm,
        "upper_shaft_diameter_mm": upper_diameter_mm,
        "upper_shaft_length_mm": upper_length_mm,
        "total_height_mm": total_height,
        "diameter_fit_compensation_mm": 0.0,
        "lead_in_chamfer_mm": chamfer_mm,
        "top_chamfer_mm": chamfer_mm,
        "print_grid_rows": rows,
        "print_grid_cols": cols,
        "print_grid_pitch_mm": pitch_mm,
        "threading": "None; M10/M6 labels refer to smooth diameter classes only.",
        "m3_pilot": "None in this run.",
        "print_orientation": "Upright on the 10.0 mm lower insert; use a slicer brim if needed.",
    }
    manifest_path = artifacts / "manifest.json"
    run_readme = run_dir / "README.md"
    outputs = {
        "adapter_grid_print_step": repo_path(root, print_paths[0]),
        "adapter_grid_print_stl": repo_path(root, print_paths[1]),
        "adapter_grid_print_3mf": repo_path(root, print_paths[2]),
        "adapter_grid_render": repo_path(root, grid_render),
        "single_editable_step": repo_path(root, use_single),
        "single_render": repo_path(root, single_render),
    }
    manifest = {
        "schema_version": 1,
        "name": stem,
        "design_kind": "smooth_stepped_adapter",
        "design_intent": (
            "Four independent exact-diameter M10-class to "
            f"{upper_diameter_mm:g} mm stepped adapters."
        ),
        "parameters": parameters,
        "outputs": outputs,
        "validation": validation,
    }
    write_json(manifest_path, manifest)
    write_adapter_readme(run_readme, stem, parameters, outputs, validation)
    if source_path and source_path.is_file():
        copy_file(source_path, run_dir / source_path.name)
    sync = sync_package(
        root=root,
        design_dir=design_dir,
        run_dir=run_dir,
        artifact_paths=[single_step, single_stl, grid_step, grid_stl, grid_3mf, manifest_path],
        direct_paths=print_paths,
        use_paths=[use_single],
        support_paths=[grid_render, single_render, run_readme],
    )
    manifest["sync"] = sync
    write_json(manifest_path, manifest)
    copy_file(manifest_path, design_dir / "artifacts" / "manifest.json")
    copy_file(manifest_path, Path(sync["nutstore_run"]) / "manifest.json")
    write_design_index(design_dir / "README.md", stem, run_name, outputs, parameters)
    return manifest


def write_ring_readme(
    path: Path,
    stem: str,
    parameters: dict[str, Any],
    outputs: dict[str, str],
    validation: dict[str, Any],
) -> None:
    path.write_text(
        f"""# {stem}

This run contains two independent print jobs. Print the 4x4 short-ring file first,
then print the single 50 mm tube as a separate job.

## Dimensions

- ID: `{parameters['inner_diameter_mm']} mm`
- OD: `{parameters['outer_diameter_mm']} mm`
- Radial wall: `{parameters['radial_wall_thickness_mm']} mm`
- Short rings: `{parameters['short_height_mm']} mm`, `{parameters['short_grid_rows']} x {parameters['short_grid_cols']}`
- Tall tube: `{parameters['tall_height_mm']} mm`, one part
- Added fit compensation: `0.0 mm`

The geometries are simple analytic annular solids with no B-spline surfaces.
Use the files prefixed `PRINT_THIS_`. For the tall tube, enable a slicer brim if
bed adhesion is uncertain; no sacrificial geometry is embedded in the part.

## Outputs

```json
{json.dumps(outputs, ensure_ascii=False, indent=2)}
```

## Validation

```json
{json.dumps(validation, ensure_ascii=False, indent=2)}
```
""",
        encoding="utf-8",
    )


def write_adapter_readme(
    path: Path,
    stem: str,
    parameters: dict[str, Any],
    outputs: dict[str, str],
    validation: dict[str, Any],
) -> None:
    path.write_text(
        f"""# {stem}

This run contains one direct-print job: four independent smooth stepped adapters
in a 2x2 upright layout.

## Dimensions

- Lower insert: `{parameters['lower_insert_diameter_mm']} mm` diameter x `{parameters['lower_insert_length_mm']} mm`
- Upper shaft: `{parameters['upper_shaft_diameter_mm']} mm` diameter x `{parameters['upper_shaft_length_mm']} mm`
- Total height: `{parameters['total_height_mm']} mm`
- Added fit compensation: `0.0 mm`
- Threading: none
- M3 pilot: none

`M10` and `M6` are descriptive smooth-diameter classes here. Use the files
prefixed `PRINT_THIS_`; enable a slicer brim if the upright parts need more bed
adhesion.

## Outputs

```json
{json.dumps(outputs, ensure_ascii=False, indent=2)}
```

## Validation

```json
{json.dumps(validation, ensure_ascii=False, indent=2)}
```
""",
        encoding="utf-8",
    )


def write_design_index(
    path: Path,
    stem: str,
    run_name: str,
    outputs: dict[str, str],
    parameters: dict[str, Any],
) -> None:
    path.write_text(
        f"""# {stem}

Latest checked run: `runs/{run_name}/`

Use the root files prefixed `PRINT_THIS_` for slicing. The run folder preserves
the exact source snapshot, validation manifest, renders, and editable single-part
STEP files.

## Parameters

```json
{json.dumps(parameters, ensure_ascii=False, indent=2)}
```

## Latest Outputs

```json
{json.dumps(outputs, ensure_ascii=False, indent=2)}
```
""",
        encoding="utf-8",
    )
