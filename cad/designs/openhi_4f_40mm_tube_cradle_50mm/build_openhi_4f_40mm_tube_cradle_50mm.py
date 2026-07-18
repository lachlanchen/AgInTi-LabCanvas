#!/usr/bin/env python3
"""Build a compact flat-bottom cradle for the 40 mm OpenHI 4F tube."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import trimesh
from OCP.BRepCheck import BRepCheck_Analyzer


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
RUN_NAME = "run-1-40p2mm-curve-2mm-floor-15mm-shoulders-print-ready-20260718T074246Z"
RUN_DIR = DESIGN_DIR / "runs" / RUN_NAME
RUN_ARTIFACT_DIR = RUN_DIR / "artifacts"
STEM = "openhi_4f_40mm_tube_cradle_50mm"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas") / STEM / RUN_NAME
)

sys.path.insert(0, str(ROOT / "cad" / "tools"))
from simple_3mf import export_stl_as_3mf  # noqa: E402


PARAMS = {
    "name": STEM,
    "design_mode": "new clean parametric print-fit design",
    "tube_nominal_outer_diameter_mm": 40.0,
    "seat_diameter_mm": 40.2,
    "seat_total_diametral_clearance_mm": 0.2,
    "seat_radial_clearance_mm": 0.1,
    "holder_length_along_tube_mm": 50.0,
    "holder_width_mm": 40.0,
    "holder_max_height_mm": 15.0,
    "minimum_floor_thickness_mm": 2.0,
    "grid_columns": 2,
    "grid_rows": 2,
    "grid_gap_x_mm": 5.0,
    "grid_gap_y_mm": 5.0,
    "print_orientation": "flat 50 x 40 mm face on build plate; concave seat upward",
    "anti_warp_ears": False,
    "anti_warp_ear_reason": (
        "Omitted to preserve the requested simple outline; the body is compact and 15 mm thick."
    ),
}


def x_cylinder(
    diameter: float,
    length: float,
    x_min: float,
    y: float = 0.0,
    z: float = 0.0,
) -> cq.Workplane:
    return (
        cq.Workplane("YZ")
        .workplane(offset=x_min)
        .center(y, z)
        .circle(diameter / 2.0)
        .extrude(length)
    )


def seat_center_z() -> float:
    return PARAMS["minimum_floor_thickness_mm"] + PARAMS["seat_diameter_mm"] / 2.0


def build_holder() -> cq.Workplane:
    p = PARAMS
    body = cq.Workplane("XY").box(
        p["holder_length_along_tube_mm"],
        p["holder_width_mm"],
        p["holder_max_height_mm"],
        centered=(True, True, False),
    )
    cutter_margin = 1.0
    seat = x_cylinder(
        p["seat_diameter_mm"],
        p["holder_length_along_tube_mm"] + 2.0 * cutter_margin,
        -p["holder_length_along_tube_mm"] / 2.0 - cutter_margin,
        z=seat_center_z(),
    )
    return body.cut(seat).clean()


def build_tube_proxy() -> cq.Workplane:
    p = PARAMS
    # The nominal tube rests at the seat's lowest point. The 0.1 mm radial
    # clearance therefore appears above and beside the tube, not under it.
    tube_center_z = p["minimum_floor_thickness_mm"] + p["tube_nominal_outer_diameter_mm"] / 2.0
    return x_cylinder(
        p["tube_nominal_outer_diameter_mm"],
        p["holder_length_along_tube_mm"] + 10.0,
        -p["holder_length_along_tube_mm"] / 2.0 - 5.0,
        z=tube_center_z,
    )


def grid_positions() -> list[tuple[float, float]]:
    p = PARAMS
    pitch_x = p["holder_length_along_tube_mm"] + p["grid_gap_x_mm"]
    pitch_y = p["holder_width_mm"] + p["grid_gap_y_mm"]
    return [
        (column * pitch_x, row * pitch_y)
        for column in (-0.5, 0.5)
        for row in (-0.5, 0.5)
    ]


def build_print_grid() -> cq.Compound:
    holder = build_holder()
    return cq.Compound.makeCompound(
        [holder.translate((x, y, 0.0)).val() for x, y in grid_positions()]
    )


def build_holder_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(
        build_holder(),
        name="printed_40mm_tube_cradle",
        color=cq.Color(0.10, 0.48, 0.72, 1.0),
    )
    return assembly


def build_fit_check_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_fit_check_assembly")
    assembly.add(
        build_holder(),
        name="printed_40p2mm_seat_cradle",
        color=cq.Color(0.10, 0.48, 0.72, 1.0),
    )
    assembly.add(
        build_tube_proxy(),
        name="openhi_4f_tube_proxy_od40mm",
        color=cq.Color(0.92, 0.42, 0.10, 0.82),
    )
    return assembly


def export_shape(shape: cq.Shape | cq.Workplane, step_path: Path, stl_path: Path) -> None:
    cq.exporters.export(shape, str(step_path))
    cq.exporters.export(shape, str(stl_path), tolerance=0.02, angularTolerance=0.08)


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    export_shape(assembly.toCompound(), step_path, stl_path)


def validate_step(path: Path) -> dict[str, object]:
    imported = cq.importers.importStep(str(path))
    solids = imported.solids().vals()
    bbox = imported.val().BoundingBox()
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "solid_count": len(solids),
        "all_brep_valid": bool(solids)
        and all(BRepCheck_Analyzer(solid.wrapped).IsValid() for solid in solids),
        "bbox_mm": [round(bbox.xlen, 4), round(bbox.ylen, 4), round(bbox.zlen, 4)],
    }


def validate_stl(path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(path, force="mesh")
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "watertight": bool(mesh.is_watertight),
        "component_count": len(mesh.split(only_watertight=False)),
        "body_count": int(mesh.body_count),
        "bbox_mm": [round(float(value), 4) for value in mesh.extents],
        "face_count": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.namelist())
        bad_member = archive.testzip()
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "zip_valid": bad_member is None and "3D/3dmodel.model" in members,
        "members": members,
    }


def geometry_checks() -> dict[str, object]:
    p = PARAMS
    radius = p["seat_diameter_mm"] / 2.0
    dz_at_top = seat_center_z() - p["holder_max_height_mm"]
    intersection_y = math.sqrt(max(0.0, radius * radius - dz_at_top * dz_at_top))
    shoulder_width = p["holder_width_mm"] / 2.0 - intersection_y
    tube_center_z = p["minimum_floor_thickness_mm"] + p["tube_nominal_outer_diameter_mm"] / 2.0
    return {
        "seat_center_z_mm": round(seat_center_z(), 4),
        "tube_rest_center_z_mm": round(tube_center_z, 4),
        "minimum_floor_thickness_mm": p["minimum_floor_thickness_mm"],
        "flat_shoulder_width_each_side_mm": round(shoulder_width, 4),
        "seat_intersection_y_at_top_mm": round(intersection_y, 4),
        "nominal_tube_tangent_to_seat_at_bottom": math.isclose(
            seat_center_z() - radius,
            tube_center_z - p["tube_nominal_outer_diameter_mm"] / 2.0,
            abs_tol=1e-9,
        ),
        "grid_pitch_x_mm": p["holder_length_along_tube_mm"] + p["grid_gap_x_mm"],
        "grid_pitch_y_mm": p["holder_width_mm"] + p["grid_gap_y_mm"],
        "expected_single_bbox_mm": [50.0, 40.0, 15.0],
        "expected_grid_bbox_mm": [105.0, 85.0, 15.0],
    }


def write_readme(path: Path, validation: dict[str, object]) -> None:
    p = PARAMS
    shoulder = validation["geometry"]["flat_shoulder_width_each_side_mm"]
    path.write_text(
        f"""# OpenHI 4F 40 mm Tube Cradle, 50 mm Long

This is a new, clean parametric cradle for the `40 mm` OD OpenHI/4F tube. It is
not derived by editing any earlier holder.

## Geometry

- Tube axis: along the `50 mm` holder length.
- Holder envelope: `50 x 40 x 15 mm`.
- Tube seat: `40.2 mm` diameter, giving `0.2 mm` diametral / `0.1 mm` radial
  clearance around a nominal `40.0 mm` tube.
- Minimum material directly under the tube: `2.0 mm`.
- Maximum side shoulder height: `15.0 mm`.
- Flat top shoulder remaining at each outer edge: about `{shoulder} mm`.
- Bottom: fully flat. Print with the concave seat facing upward.

The slightly oversize seat compensates for printed fit while retaining the same
circular profile as the tube. The tube proxy rests at the bottom tangent point;
the clearance is above and beside it rather than underneath it.

## Print Files

- `PRINT_THIS_{STEM}_single.stl/.step/.3mf`: one holder.
- `PRINT_THIS_{STEM}_2x2_print_grid.stl/.step/.3mf`: four separate holders with
  `5 mm` gaps; no connecting sprues.
- `USE_THIS_{STEM}.step`: editable single-holder handoff for Shapr3D.

The 2x2 layout measures `105 x 85 x 15 mm`. Anti-warp ears were intentionally
omitted because this compact part has a thick `15 mm` body and the requested
outline is simple. Add ears in a later run only if the physical print curls.

## Validation

- Single STEP: `{validation['single_step']['solid_count']}` valid solid,
  bounding box `{validation['single_step']['bbox_mm']} mm`.
- Single STL: watertight `{validation['single_stl']['watertight']}`, component
  count `{validation['single_stl']['component_count']}`.
- 2x2 STEP: `{validation['grid_step']['solid_count']}` valid solids, bounding
  box `{validation['grid_step']['bbox_mm']} mm`.
- 2x2 STL: watertight `{validation['grid_stl']['watertight']}`, component count
  `{validation['grid_stl']['component_count']}`.
- 3MF archives: single `{validation['single_3mf']['zip_valid']}`, grid
  `{validation['grid_3mf']['zip_valid']}`.

Physically test one holder before relying on the fit. If the tube is too loose
or tight, revise only `seat_diameter_mm`; do not scale the whole model.
""",
        encoding="utf-8",
    )


def render_with_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for the checked render outputs")
    subprocess.run(
        [blender, "--background", "--python", str(DESIGN_DIR / f"render_{STEM}.py")],
        check=True,
    )


def copy_print_handoff(destination: Path, validation: dict[str, object]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    aliases = [
        f"PRINT_THIS_{STEM}_single.step",
        f"PRINT_THIS_{STEM}_single.stl",
        f"PRINT_THIS_{STEM}_single.3mf",
        f"PRINT_THIS_{STEM}_2x2_print_grid.step",
        f"PRINT_THIS_{STEM}_2x2_print_grid.stl",
        f"PRINT_THIS_{STEM}_2x2_print_grid.3mf",
        f"PRINT_THIS_{STEM}_single_render.png",
        f"PRINT_THIS_{STEM}_2x2_print_grid_render.png",
        f"USE_THIS_{STEM}.step",
        f"USE_THIS_{STEM}_assembly_render.png",
        "README.md",
    ]
    for name in aliases:
        shutil.copy2(DESIGN_DIR / name, destination / name)
    shutil.copy2(ARTIFACT_DIR / "manifest.json", destination / "manifest.json")


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    holder = build_holder()
    tube_proxy = build_tube_proxy()
    grid = build_print_grid()

    holder_step = ARTIFACT_DIR / f"{STEM}_holder.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}_holder.stl"
    holder_3mf = ARTIFACT_DIR / f"{STEM}_holder.3mf"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    tube_step = ARTIFACT_DIR / f"{STEM}_tube_proxy_od40.step"
    tube_stl = ARTIFACT_DIR / f"{STEM}_tube_proxy_od40.stl"
    fit_step = ARTIFACT_DIR / f"{STEM}_fit_check_assembly.step"
    fit_stl = ARTIFACT_DIR / f"{STEM}_fit_check_assembly.stl"
    grid_step = ARTIFACT_DIR / f"{STEM}_2x2_print_grid.step"
    grid_stl = ARTIFACT_DIR / f"{STEM}_2x2_print_grid.stl"
    grid_3mf = ARTIFACT_DIR / f"{STEM}_2x2_print_grid.3mf"

    export_shape(holder, holder_step, holder_stl)
    export_stl_as_3mf(holder_stl, holder_3mf, title=f"{STEM} single holder")
    export_assembly(build_holder_assembly(), assembly_step, assembly_stl)
    export_shape(tube_proxy, tube_step, tube_stl)
    export_assembly(build_fit_check_assembly(), fit_step, fit_stl)
    export_shape(grid, grid_step, grid_stl)
    export_stl_as_3mf(grid_stl, grid_3mf, title=f"{STEM} 2x2 print grid")

    validation = {
        "geometry": geometry_checks(),
        "single_step": validate_step(holder_step),
        "single_stl": validate_stl(holder_stl),
        "single_3mf": validate_3mf(holder_3mf),
        "assembly_step": validate_step(assembly_step),
        "tube_proxy_step": validate_step(tube_step),
        "fit_check_step": validate_step(fit_step),
        "grid_step": validate_step(grid_step),
        "grid_stl": validate_stl(grid_stl),
        "grid_3mf": validate_3mf(grid_3mf),
    }

    if validation["single_step"]["solid_count"] != 1:
        raise RuntimeError("Single-holder STEP must contain exactly one solid")
    if validation["grid_step"]["solid_count"] != 4:
        raise RuntimeError("2x2 STEP must contain exactly four solids")
    if not validation["single_stl"]["watertight"]:
        raise RuntimeError("Single-holder STL is not watertight")
    if validation["grid_stl"]["component_count"] != 4:
        raise RuntimeError("2x2 STL must contain four disconnected printable components")

    render_with_blender()

    aliases = {
        f"USE_THIS_{STEM}.step": holder_step,
        f"USE_THIS_{STEM}_assembly_render.png": ARTIFACT_DIR / f"{STEM}_fit_check_render.png",
        f"PRINT_THIS_{STEM}_single.step": holder_step,
        f"PRINT_THIS_{STEM}_single.stl": holder_stl,
        f"PRINT_THIS_{STEM}_single.3mf": holder_3mf,
        f"PRINT_THIS_{STEM}_single_render.png": ARTIFACT_DIR / f"{STEM}_single_render.png",
        f"PRINT_THIS_{STEM}_2x2_print_grid.step": grid_step,
        f"PRINT_THIS_{STEM}_2x2_print_grid.stl": grid_stl,
        f"PRINT_THIS_{STEM}_2x2_print_grid.3mf": grid_3mf,
        f"PRINT_THIS_{STEM}_2x2_print_grid_render.png": ARTIFACT_DIR / f"{STEM}_2x2_print_grid_render.png",
    }
    for alias, source in aliases.items():
        shutil.copy2(source, DESIGN_DIR / alias)

    write_readme(DESIGN_DIR / "README.md", validation)

    manifest = {
        "name": STEM,
        "run": RUN_NAME,
        "created_by": Path(__file__).name,
        "parameters": PARAMS,
        "validation": validation,
        "outputs": {
            "single_holder_step": str(holder_step.relative_to(DESIGN_DIR)),
            "single_holder_stl": str(holder_stl.relative_to(DESIGN_DIR)),
            "single_holder_3mf": str(holder_3mf.relative_to(DESIGN_DIR)),
            "holder_assembly_step": str(assembly_step.relative_to(DESIGN_DIR)),
            "tube_proxy_step": str(tube_step.relative_to(DESIGN_DIR)),
            "fit_check_assembly_step": str(fit_step.relative_to(DESIGN_DIR)),
            "print_grid_step": str(grid_step.relative_to(DESIGN_DIR)),
            "print_grid_stl": str(grid_stl.relative_to(DESIGN_DIR)),
            "print_grid_3mf": str(grid_3mf.relative_to(DESIGN_DIR)),
            "single_render": f"artifacts/{STEM}_single_render.png",
            "fit_check_render": f"artifacts/{STEM}_fit_check_render.png",
            "cross_section_render": f"artifacts/{STEM}_cross_section_fit_render.png",
            "print_grid_render": f"artifacts/{STEM}_2x2_print_grid_render.png",
        },
    }
    (ARTIFACT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for source in ARTIFACT_DIR.iterdir():
        if source.is_file():
            shutil.copy2(source, RUN_ARTIFACT_DIR / source.name)
    shutil.copy2(Path(__file__), RUN_DIR / Path(__file__).name)
    shutil.copy2(DESIGN_DIR / f"render_{STEM}.py", RUN_DIR / f"render_{STEM}.py")
    copy_print_handoff(RUN_DIR, validation)
    copy_print_handoff(NUTSTORE_DIR, validation)

    # Keep the final single-part assembly STEP easy to find at the LabCanvas root.
    nutstore_root = NUTSTORE_DIR.parents[1]
    nutstore_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(assembly_step, nutstore_root / assembly_step.name)
    shutil.copy2(DESIGN_DIR / f"USE_THIS_{STEM}.step", nutstore_root / f"USE_THIS_{STEM}.step")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
