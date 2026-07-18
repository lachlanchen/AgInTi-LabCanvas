#!/usr/bin/env python3
"""Build a table-mount cradle for the 40 mm OpenHI 4F tube."""

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
RUN_NAME = "run-3-four-corner-anti-warp-ears-single-print-ready-20260718T124723Z"
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
    "mounting_wing_width_each_side_mm": 15.0,
    "mounting_wing_thickness_mm": 5.0,
    "overall_width_with_wings_mm": 70.0,
    "mounting_hole_nominal_fastener": "M6",
    "mounting_hole_diameter_mm": 6.4,
    "mounting_hole_center_pitch_mm": 50.0,
    "mounting_hole_centers_xy_mm": [[0.0, -25.0], [0.0, 25.0]],
    "optical_table_grid_pitch_mm": 25.0,
    "print_layout_count": 1,
    "print_orientation": "flat 50 x 70 mm wing face on build plate; concave seat upward",
    "anti_warp_ears": True,
    "anti_warp_ear_style": (
        "four removable filled corner ears with two side contacts and a diagonal pull"
    ),
    "anti_warp_ear_thickness_mm": 1.0,
    "anti_warp_ear_breakaway_overlap_mm": 0.6,
    "anti_warp_ear_side_contact_length_mm": 5.0,
    "anti_warp_ear_side_reach_mm": 12.0,
    "anti_warp_ear_side_width_mm": 6.0,
    "anti_warp_ear_diagonal_reach_mm": 14.0,
    "anti_warp_ear_tail_width_mm": 10.0,
    "anti_warp_ear_note": (
        "The accepted holder stays clean; ears exist only in PRINT_THIS exports. "
        "Each 1 mm sacrificial ear overlaps both adjacent edges by 0.6 mm and "
        "pulls the true corner outward along both side directions and the diagonal."
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
    cradle_body = cq.Workplane("XY").box(
        p["holder_length_along_tube_mm"],
        p["holder_width_mm"],
        p["holder_max_height_mm"],
        centered=(True, True, False),
    )
    mounting_base = cq.Workplane("XY").box(
        p["holder_length_along_tube_mm"],
        p["overall_width_with_wings_mm"],
        p["mounting_wing_thickness_mm"],
        centered=(True, True, False),
    )
    cutter_margin = 1.0
    seat = x_cylinder(
        p["seat_diameter_mm"],
        p["holder_length_along_tube_mm"] + 2.0 * cutter_margin,
        -p["holder_length_along_tube_mm"] / 2.0 - cutter_margin,
        z=seat_center_z(),
    )
    hole_margin = 1.0
    mounting_holes = (
        cq.Workplane("XY")
        .workplane(offset=-hole_margin)
        .pushPoints([tuple(point) for point in p["mounting_hole_centers_xy_mm"]])
        .circle(p["mounting_hole_diameter_mm"] / 2.0)
        .extrude(p["mounting_wing_thickness_mm"] + 2.0 * hole_margin)
    )
    return cradle_body.union(mounting_base).cut(seat).cut(mounting_holes).clean()


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


def z_poly(points: list[tuple[float, float]], height: float) -> cq.Workplane:
    return cq.Workplane("XY").polyline(points).close().extrude(height)


def anti_warp_corner_ear(sx: int, sy: int) -> cq.Workplane:
    """Build one strong but removable ear at a print-bed corner."""
    p = PARAMS
    half_x = p["holder_length_along_tube_mm"] / 2.0
    half_y = p["overall_width_with_wings_mm"] / 2.0
    overlap = p["anti_warp_ear_breakaway_overlap_mm"]
    contact = p["anti_warp_ear_side_contact_length_mm"]
    side_reach = p["anti_warp_ear_side_reach_mm"]
    side_width = p["anti_warp_ear_side_width_mm"]
    diagonal_reach = p["anti_warp_ear_diagonal_reach_mm"]
    tail_width = p["anti_warp_ear_tail_width_mm"]
    thickness = p["anti_warp_ear_thickness_mm"]

    def local_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(sx * (half_x + u), sy * (half_y + v)) for u, v in points]

    # Three simple filled polygons avoid fragile concave booleans. The first
    # pulls the true corner diagonally; the other two grip both adjacent edges.
    diagonal_pull = [
        (-overlap, -overlap),
        (side_reach, -overlap),
        (side_reach, side_width),
        (diagonal_reach + tail_width / 2.0, diagonal_reach - tail_width / 2.0),
        (diagonal_reach + tail_width / 2.0, diagonal_reach + tail_width / 2.0),
        (diagonal_reach - tail_width / 2.0, diagonal_reach + tail_width / 2.0),
        (side_width, side_reach),
        (-overlap, side_reach),
    ]
    side_pull_x = [
        (-contact, -overlap),
        (side_reach, -overlap),
        (side_reach, side_width),
        (-contact, side_width),
    ]
    side_pull_y = [
        (-overlap, -contact),
        (side_width, -contact),
        (side_width, side_reach),
        (-overlap, side_reach),
    ]

    ear = z_poly(local_points(diagonal_pull), thickness)
    ear = ear.union(z_poly(local_points(side_pull_x), thickness))
    ear = ear.union(z_poly(local_points(side_pull_y), thickness))
    return ear.clean()


def build_print_layout() -> cq.Workplane:
    layout = build_holder()
    for sx in (-1, 1):
        for sy in (-1, 1):
            layout = layout.union(anti_warp_corner_ear(sx, sy))
    return layout.clean()


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
        "volume_mm3": round(sum(solid.Volume() for solid in solids), 4),
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
    hole_radius = p["mounting_hole_diameter_mm"] / 2.0
    outer_half_width = p["overall_width_with_wings_mm"] / 2.0
    hole_half_pitch = p["mounting_hole_center_pitch_mm"] / 2.0
    cradle_half_width = p["holder_width_mm"] / 2.0
    ear_extent = (
        p["anti_warp_ear_diagonal_reach_mm"]
        + p["anti_warp_ear_tail_width_mm"] / 2.0
    )
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
        "mounting_hole_diameter_mm": p["mounting_hole_diameter_mm"],
        "mounting_hole_center_pitch_mm": p["mounting_hole_center_pitch_mm"],
        "mounting_hole_pitch_is_two_table_grid_intervals": math.isclose(
            p["mounting_hole_center_pitch_mm"],
            2.0 * p["optical_table_grid_pitch_mm"],
            abs_tol=1e-9,
        ),
        "mounting_hole_outer_edge_ligament_mm": round(
            outer_half_width - hole_half_pitch - hole_radius, 4
        ),
        "mounting_hole_inner_wing_ligament_mm": round(
            hole_half_pitch - hole_radius - cradle_half_width, 4
        ),
        "mounting_hole_end_ligament_mm": round(
            p["holder_length_along_tube_mm"] / 2.0 - hole_radius, 4
        ),
        "accepted_run_2_clean_holder_volume_mm3": 19415.8362,
        "expected_clean_holder_bbox_mm": [50.0, 70.0, 15.0],
        "expected_single_print_bbox_mm": [
            2.0 * (p["holder_length_along_tube_mm"] / 2.0 + ear_extent),
            2.0 * (p["overall_width_with_wings_mm"] / 2.0 + ear_extent),
            15.0,
        ],
    }


def feature_checks(holder: cq.Workplane, print_layout: cq.Workplane) -> dict[str, object]:
    p = PARAMS
    shape = holder.val()
    print_shape = print_layout.val()
    wing_sample_y = p["overall_width_with_wings_mm"] / 2.0 - 3.0
    sample_z = p["mounting_wing_thickness_mm"] / 2.0
    hole_centers_clear = all(
        not shape.isInside(cq.Vector(float(x), float(y), sample_z), 1e-6)
        for x, y in p["mounting_hole_centers_xy_mm"]
    )
    outer_wing_material_present = all(
        shape.isInside(cq.Vector(0.0, y, sample_z), 1e-6)
        for y in (-wing_sample_y, wing_sample_y)
    )
    half_x = p["holder_length_along_tube_mm"] / 2.0
    half_y = p["overall_width_with_wings_mm"] / 2.0
    diagonal_reach = p["anti_warp_ear_diagonal_reach_mm"]
    ear_tail_centers_present = all(
        print_shape.isInside(
            cq.Vector(
                sx * (half_x + diagonal_reach),
                sy * (half_y + diagonal_reach),
                p["anti_warp_ear_thickness_mm"] / 2.0,
            ),
            1e-6,
        )
        for sx in (-1, 1)
        for sy in (-1, 1)
    )
    return {
        "mounting_hole_centers_clear": hole_centers_clear,
        "outer_wing_material_present": outer_wing_material_present,
        "center_floor_present_at_z1mm": shape.isInside(cq.Vector(0.0, 0.0, 1.0), 1e-6),
        "seat_open_above_floor_at_z2p5mm": not shape.isInside(
            cq.Vector(0.0, 0.0, 2.5), 1e-6
        ),
        "four_anti_warp_tail_centers_present": ear_tail_centers_present,
    }


def write_readme(path: Path, validation: dict[str, object]) -> None:
    p = PARAMS
    shoulder = validation["geometry"]["flat_shoulder_width_each_side_mm"]
    path.write_text(
        f"""# OpenHI 4F 40 mm Tube Cradle With Optical-Table Wings

Run 3 preserves the accepted run-2 cradle geometry and adds removable anti-warp
ears only to the direct-print body. The clean Shapr3D STEP has no sacrificial
tabs.

## Geometry

- Tube axis: along the `50 mm` holder length.
- Main cradle envelope: `50 x 40 x 15 mm`.
- Overall table-mount envelope: `50 x 70 x 15 mm`.
- Tube seat: `40.2 mm` diameter, giving `0.2 mm` diametral / `0.1 mm` radial
  clearance around a nominal `40.0 mm` tube.
- Minimum material directly under the tube: `2.0 mm`.
- Maximum side shoulder height: `15.0 mm`.
- Flat top shoulder remaining at each outer edge: about `{shoulder} mm`.
- Two integral mounting wings: `50 x 15 x 5 mm` each.
- Two M6 clearance bores: `6.4 mm` diameter, vertical through the wings.
- Hole centers: `(x, y) = (0, +/-25 mm)`, giving `50 mm` center spacing for a
  standard `25 mm` optical-table grid.
- Outer hole-edge ligament: `6.8 mm`; inner wing ligament: `1.8 mm`, backed by
  the full-height cradle sidewall.
- Bottom: fully flat. Print with the concave seat facing upward.

The slightly oversize seat compensates for printed fit while retaining the same
circular profile as the tube. The tube proxy rests at the bottom tangent point;
the clearance is above and beside it rather than underneath it.

## Print Files

- `PRINT_THIS_{STEM}_single.stl/.step/.3mf`: exactly one holder with four
  removable corner ears; print this set.
- `USE_THIS_{STEM}.step`: editable single-holder handoff for Shapr3D.
- `USE_THIS_{STEM}_mounting_pattern_top_render.png`: top check of both wings
  and the `50 mm` two-hole pattern.

Each corner ear is `{p['anti_warp_ear_thickness_mm']} mm` thick. It contacts both
adjacent edges, includes a diagonal corner pull, and ends in a wider pad. Cut or
peel the ears away after printing. The single print layout measures
`{validation['print_step']['bbox_mm'][0]} x {validation['print_step']['bbox_mm'][1]} x {validation['print_step']['bbox_mm'][2]} mm`.

## Validation

- Clean holder STEP: `{validation['clean_holder_step']['solid_count']}` valid
  solid, bounding box `{validation['clean_holder_step']['bbox_mm']} mm`, volume
  `{validation['clean_holder_step']['volume_mm3']} mm3`.
- Direct-print STEP: `{validation['print_step']['solid_count']}` valid solid,
  bounding box `{validation['print_step']['bbox_mm']} mm`.
- Direct-print STL: watertight `{validation['print_stl']['watertight']}`,
  component count `{validation['print_stl']['component_count']}`.
- Direct-print 3MF ZIP: `{validation['print_3mf']['zip_valid']}`.

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
        f"PRINT_THIS_{STEM}_single_render.png",
        f"PRINT_THIS_{STEM}_single_top_render.png",
        f"USE_THIS_{STEM}.step",
        f"USE_THIS_{STEM}_assembly_render.png",
        f"USE_THIS_{STEM}_mounting_pattern_top_render.png",
        "README.md",
    ]
    for name in aliases:
        shutil.copy2(DESIGN_DIR / name, destination / name)
    shutil.copy2(ARTIFACT_DIR / "manifest.json", destination / "manifest.json")


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # Run 2 remains archived. Do not let its 2x2 outputs masquerade as the
    # latest direct-print layout in the project root or run-3 artifacts.
    for stale in ARTIFACT_DIR.glob(f"{STEM}_2x2_print_grid*"):
        stale.unlink()
    for stale in DESIGN_DIR.glob(f"PRINT_THIS_{STEM}_2x2_print_grid*"):
        stale.unlink()

    holder = build_holder()
    tube_proxy = build_tube_proxy()
    print_layout = build_print_layout()

    holder_step = ARTIFACT_DIR / f"{STEM}_holder.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}_holder.stl"
    holder_3mf = ARTIFACT_DIR / f"{STEM}_holder.3mf"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    tube_step = ARTIFACT_DIR / f"{STEM}_tube_proxy_od40.step"
    tube_stl = ARTIFACT_DIR / f"{STEM}_tube_proxy_od40.stl"
    fit_step = ARTIFACT_DIR / f"{STEM}_fit_check_assembly.step"
    fit_stl = ARTIFACT_DIR / f"{STEM}_fit_check_assembly.stl"
    print_step = ARTIFACT_DIR / f"{STEM}_single_with_anti_warp_ears.step"
    print_stl = ARTIFACT_DIR / f"{STEM}_single_with_anti_warp_ears.stl"
    print_3mf = ARTIFACT_DIR / f"{STEM}_single_with_anti_warp_ears.3mf"

    export_shape(holder, holder_step, holder_stl)
    export_stl_as_3mf(holder_stl, holder_3mf, title=f"{STEM} single holder")
    export_assembly(build_holder_assembly(), assembly_step, assembly_stl)
    export_shape(tube_proxy, tube_step, tube_stl)
    export_assembly(build_fit_check_assembly(), fit_step, fit_stl)
    export_shape(print_layout, print_step, print_stl)
    export_stl_as_3mf(
        print_stl,
        print_3mf,
        title=f"{STEM} single holder with four anti-warp ears",
    )

    validation = {
        "geometry": geometry_checks(),
        "features": feature_checks(holder, print_layout),
        "clean_holder_step": validate_step(holder_step),
        "clean_holder_stl": validate_stl(holder_stl),
        "clean_holder_3mf": validate_3mf(holder_3mf),
        "assembly_step": validate_step(assembly_step),
        "tube_proxy_step": validate_step(tube_step),
        "fit_check_step": validate_step(fit_step),
        "print_step": validate_step(print_step),
        "print_stl": validate_stl(print_stl),
        "print_3mf": validate_3mf(print_3mf),
    }

    if validation["clean_holder_step"]["solid_count"] != 1:
        raise RuntimeError("Clean holder STEP must contain exactly one solid")
    if (
        validation["clean_holder_step"]["bbox_mm"]
        != validation["geometry"]["expected_clean_holder_bbox_mm"]
    ):
        raise RuntimeError("Clean holder bounds changed from accepted run 2")
    if not math.isclose(
        validation["clean_holder_step"]["volume_mm3"],
        validation["geometry"]["accepted_run_2_clean_holder_volume_mm3"],
        abs_tol=0.001,
    ):
        raise RuntimeError("Clean holder volume changed from accepted run 2")
    if validation["print_step"]["solid_count"] != 1:
        raise RuntimeError("Single print STEP must contain one connected solid")
    if (
        validation["print_step"]["bbox_mm"]
        != validation["geometry"]["expected_single_print_bbox_mm"]
    ):
        raise RuntimeError("Single print STEP bounds do not match the ear envelope")
    if not validation["print_stl"]["watertight"]:
        raise RuntimeError("Single print STL is not watertight")
    if validation["print_stl"]["component_count"] != 1:
        raise RuntimeError("Single print STL must be one connected printable component")
    if not all(validation["features"].values()):
        raise RuntimeError("Mounting-wing or saddle feature checks failed")

    render_with_blender()

    aliases = {
        f"USE_THIS_{STEM}.step": holder_step,
        f"USE_THIS_{STEM}_assembly_render.png": ARTIFACT_DIR / f"{STEM}_fit_check_render.png",
        f"PRINT_THIS_{STEM}_single.step": print_step,
        f"PRINT_THIS_{STEM}_single.stl": print_stl,
        f"PRINT_THIS_{STEM}_single.3mf": print_3mf,
        f"PRINT_THIS_{STEM}_single_render.png": ARTIFACT_DIR
        / f"{STEM}_single_with_anti_warp_ears_render.png",
        f"PRINT_THIS_{STEM}_single_top_render.png": ARTIFACT_DIR
        / f"{STEM}_single_with_anti_warp_ears_top_render.png",
        f"USE_THIS_{STEM}_mounting_pattern_top_render.png": ARTIFACT_DIR
        / f"{STEM}_mounting_pattern_top_render.png",
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
            "single_print_step": str(print_step.relative_to(DESIGN_DIR)),
            "single_print_stl": str(print_stl.relative_to(DESIGN_DIR)),
            "single_print_3mf": str(print_3mf.relative_to(DESIGN_DIR)),
            "clean_holder_render": f"artifacts/{STEM}_single_render.png",
            "single_print_render": f"artifacts/{STEM}_single_with_anti_warp_ears_render.png",
            "single_print_top_render": f"artifacts/{STEM}_single_with_anti_warp_ears_top_render.png",
            "fit_check_render": f"artifacts/{STEM}_fit_check_render.png",
            "cross_section_render": f"artifacts/{STEM}_cross_section_fit_render.png",
            "mounting_pattern_top_render": f"artifacts/{STEM}_mounting_pattern_top_render.png",
        },
    }
    (ARTIFACT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Rebuilding the same timestamped run must be deterministic: clear copied
    # artifacts first so files removed from the latest contract cannot linger.
    for stale in RUN_ARTIFACT_DIR.iterdir():
        if stale.is_file():
            stale.unlink()
    for source in ARTIFACT_DIR.iterdir():
        if source.is_file() and source.suffix != ".blend1":
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
