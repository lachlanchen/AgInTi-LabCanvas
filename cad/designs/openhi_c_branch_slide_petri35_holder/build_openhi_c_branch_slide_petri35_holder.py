#!/usr/bin/env python3
"""Build a slide/Petri holder that seats on the OpenHI C branch.

The accepted two-piece cage sample holder remains the authority for every
sample-facing feature.  This design replaces only the lower cage-rod sockets
with a separate, smooth, non-threaded adapter measured from OpenHI C.step.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import trimesh
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.GeomAbs import GeomAbs_BSplineSurface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "openhi_c_branch_slide_petri35_holder"
RUN_NAME = "run-1-25mm-smooth-c-branch-socket-print-ready-20260806T030109Z"
RUN_DIR = DESIGN_DIR / "runs" / RUN_NAME
RUN_ARTIFACT_DIR = RUN_DIR / "artifacts"
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
NUTSTORE_DIR = NUTSTORE_ROOT / STEM / RUN_NAME

ACCEPTED_DIR = ROOT / "cad/designs/cage_sample_holder_two_piece_lock_slide_petri35"
ACCEPTED_BUILDER_PATH = ACCEPTED_DIR / "build_cage_sample_holder_two_piece_lock_slide_petri35.py"
OPENHI_C_STEP = ROOT / "cad/extracted/OpenHI_STEP/C.step"

sys.path.insert(0, str(ROOT / "cad/tools"))
from simple_3mf import export_stl_as_3mf  # noqa: E402


def load_accepted_builder():
    spec = importlib.util.spec_from_file_location("accepted_sample_holder", ACCEPTED_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load accepted holder builder: {ACCEPTED_BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ACCEPTED = load_accepted_builder()


PARAMS = {
    "name": STEM,
    "design_mode": "new clean decoupled adapter using an unchanged accepted sample-holder upper geometry",
    "accepted_geometry_source": str(ACCEPTED_BUILDER_PATH.relative_to(ROOT)),
    "measured_reference_source": str(OPENHI_C_STEP.relative_to(ROOT)),
    "sample_holder_outer_mm": [110.0, 70.0],
    "sample_tray_thickness_mm": 8.0,
    "chamber_gap_mm": 18.0,
    "top_frame_z_mm": 26.0,
    "slide_nominal_mm": [72.96, 20.0],
    "slide_seat_mm": [75.0, 22.0],
    "slide_seat_depth_mm": 1.2,
    "petri_nominal_diameter_mm": 33.0,
    "petri_seat_diameter_mm": 35.4,
    "petri_seat_depth_mm": 1.8,
    "optical_window_diameter_mm": 18.0,
    "c_branch_reference_plain_nose_diameter_mm": 24.4,
    "c_branch_reference_thread_crest_diameter_mm": 25.2,
    "c_branch_reference_plain_nose_length_mm": 3.9,
    "c_branch_reference_taper_length_mm": 7.8,
    "c_branch_reference_taper_large_diameter_mm": 40.0,
    "adapter_outer_diameter_mm": 40.0,
    "adapter_smooth_socket_id_mm": 25.0,
    "adapter_smooth_socket_length_mm": 5.0,
    "adapter_taper_length_mm": 7.8,
    "adapter_taper_mouth_id_mm": 39.0,
    "adapter_mouth_radial_lip_mm": 0.5,
    "adapter_main_length_mm": 12.8,
    "adapter_registration_spigot_od_mm": 38.0,
    "adapter_registration_spigot_height_mm": 2.0,
    "tray_registration_pocket_id_mm": 38.2,
    "tray_registration_pocket_depth_mm": 2.2,
    "registration_diametral_clearance_mm": 0.2,
    "registration_axial_clearance_mm": 0.2,
    "c_reference_tip_offset_for_fit_render_mm": -1.6,
    "fit_coupon_outer_diameter_mm": 32.0,
    "fit_coupon_inner_diameter_mm": 25.0,
    "fit_coupon_height_mm": 5.0,
    "fit_coupon_entry_diameter_mm": 25.8,
    "fit_coupon_entry_chamfer_height_mm": 0.4,
    "thread_policy": "no thread is generated; the socket is intentionally smooth",
    "physical_fit_warning": (
        "The measured reference thread crest is about 25.2 mm while the user-confirmed "
        "socket ID is 25.0 mm. This is intentionally tight; print the fit coupon first."
    ),
    "print_orientation_adapter": (
        "registration-spigot/18 mm optical side on the build plate; 39 mm tapered mouth upward"
    ),
}


def z_cylinder(diameter: float, height: float, z0: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z0)).circle(diameter / 2.0).extrude(height)


def z_cone(diameter0: float, diameter1: float, height: float, z0: float) -> cq.Workplane:
    solid = cq.Solid.makeCone(
        diameter0 / 2.0,
        diameter1 / 2.0,
        height,
        cq.Vector(0.0, 0.0, z0),
        cq.Vector(0.0, 0.0, 1.0),
    )
    return cq.Workplane(obj=solid)


def build_bottom_tray() -> cq.Workplane:
    """Reuse all accepted sample geometry and replace only the lower interface."""
    part = ACCEPTED.base_plate()
    part = ACCEPTED.cut_bottom_sample_seats(part)
    part = ACCEPTED.add_lock_feet(part)
    part = ACCEPTED.add_anti_warp_ears(part, bed_face="bottom")
    pocket = z_cylinder(
        PARAMS["tray_registration_pocket_id_mm"],
        PARAMS["tray_registration_pocket_depth_mm"] + 0.1,
        -0.1,
    )
    return part.cut(pocket).clean()


def build_top_frame() -> cq.Workplane:
    return ACCEPTED.build_top_part()


def build_top_frame_print() -> cq.Workplane:
    return ACCEPTED.build_top_part_180deg_print()


def build_c_branch_adapter() -> cq.Workplane:
    """Build the actual-use adapter at z=-12.8..2.0 beneath the sample tray."""
    p = PARAMS
    main = z_cylinder(p["adapter_outer_diameter_mm"], p["adapter_main_length_mm"], -p["adapter_main_length_mm"])
    spigot = z_cylinder(
        p["adapter_registration_spigot_od_mm"],
        p["adapter_registration_spigot_height_mm"],
        0.0,
    )
    part = main.union(spigot)
    taper = z_cone(
        p["adapter_taper_mouth_id_mm"],
        p["adapter_smooth_socket_id_mm"],
        p["adapter_taper_length_mm"],
        -p["adapter_main_length_mm"],
    )
    nose = z_cylinder(
        p["adapter_smooth_socket_id_mm"],
        p["adapter_smooth_socket_length_mm"] + 0.05,
        -p["adapter_smooth_socket_length_mm"],
    )
    optical = z_cylinder(
        p["optical_window_diameter_mm"],
        p["adapter_registration_spigot_height_mm"] + 0.1,
        -0.05,
    )
    return part.cut(taper).cut(nose).cut(optical).clean()


def build_adapter_print() -> cq.Workplane:
    """Flip the adapter so the supported narrow end rests on the build plate."""
    p = PARAMS
    return (
        build_c_branch_adapter()
        .rotate((0, 0, 0), (1, 0, 0), 180)
        .translate((0, 0, p["adapter_registration_spigot_height_mm"]))
    )


def build_fit_coupon() -> cq.Workplane:
    p = PARAMS
    part = z_cylinder(p["fit_coupon_outer_diameter_mm"], p["fit_coupon_height_mm"], 0.0)
    entry = z_cone(
        p["fit_coupon_entry_diameter_mm"],
        p["fit_coupon_inner_diameter_mm"],
        p["fit_coupon_entry_chamfer_height_mm"],
        0.0,
    )
    bore = z_cylinder(
        p["fit_coupon_inner_diameter_mm"],
        p["fit_coupon_height_mm"],
        p["fit_coupon_entry_chamfer_height_mm"] - 0.05,
    )
    return part.cut(entry).cut(bore).clean()


def build_openhi_c_reference() -> cq.Workplane:
    """Move and bound the actual C STEP to its upward mating branch only."""
    reference = cq.importers.importStep(str(OPENHI_C_STEP))
    transformed = (
        reference
        .translate((-429.0, -210.0, -600.0))
        .rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((0, 0, PARAMS["c_reference_tip_offset_for_fit_render_mm"]))
    )
    # The source STEP also contains distant construction/assembly bodies. Keep
    # only the measured 40 mm branch and its nose so the fit-check is readable.
    branch_clip = z_cylinder(40.1, 22.0, -22.0)
    return transformed.intersect(branch_clip)


def build_assembly(include_samples: bool = False) -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_bottom_tray(), name="unchanged_sample_tray_new_registration_pocket", color=cq.Color(0.55, 0.54, 0.50, 1.0))
    assembly.add(build_c_branch_adapter(), name="separate_smooth_c_branch_adapter", color=cq.Color(0.10, 0.38, 0.76, 1.0))
    assembly.add(build_top_frame().translate((0, 0, ACCEPTED.top_part_z())), name="unchanged_top_frame", color=cq.Color(0.82, 0.80, 0.72, 1.0))
    if include_samples:
        assembly.add(ACCEPTED.build_slide_proxy(), name="slide_proxy", color=cq.Color(0.1, 0.8, 0.95, 0.35))
        assembly.add(ACCEPTED.build_petri_proxy(), name="petri_proxy", color=cq.Color(0.95, 0.95, 1.0, 0.35))
    return assembly


def build_fit_check_assembly() -> cq.Assembly:
    assembly = build_assembly(include_samples=True)
    assembly.add(build_openhi_c_reference(), name="measured_openhi_c_reference_not_printable", color=cq.Color(0.95, 0.35, 0.06, 0.38))
    return assembly


def build_exploded_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_exploded")
    assembly.add(build_c_branch_adapter().translate((0, 0, -12)), name="smooth_adapter", color=cq.Color(0.10, 0.38, 0.76, 1.0))
    assembly.add(build_bottom_tray().translate((0, 0, 10)), name="sample_tray", color=cq.Color(0.55, 0.54, 0.50, 1.0))
    assembly.add(build_top_frame().translate((0, 0, 56)), name="top_frame", color=cq.Color(0.82, 0.80, 0.72, 1.0))
    assembly.add(ACCEPTED.build_slide_proxy().translate((0, -48, 18)), name="slide_proxy", color=cq.Color(0.1, 0.8, 0.95, 0.35))
    assembly.add(ACCEPTED.build_petri_proxy().translate((0, 48, 18)), name="petri_proxy", color=cq.Color(0.95, 0.95, 1.0, 0.35))
    return assembly


def build_print_layout() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_print_layout")
    assembly.add(build_bottom_tray().translate((0, -62, 0)), name="bottom_tray", color=cq.Color(0.55, 0.54, 0.50, 1.0))
    assembly.add(build_top_frame_print().translate((0, 62, 0)), name="top_frame_180deg", color=cq.Color(0.82, 0.80, 0.72, 1.0))
    assembly.add(build_adapter_print().translate((82, 0, 0)), name="adapter_supported_orientation", color=cq.Color(0.10, 0.38, 0.76, 1.0))
    assembly.add(build_fit_coupon().translate((-82, 0, 0)), name="25mm_fit_coupon", color=cq.Color(0.95, 0.62, 0.15, 1.0))
    return assembly


def build_adapter_half_section() -> cq.Workplane:
    clip = cq.Workplane("XY").box(24, 50, 30, centered=(False, True, True)).translate((0, 0, -5))
    return build_c_branch_adapter().intersect(clip).clean()


def export_shape(shape: cq.Workplane | cq.Shape, step_path: Path, stl_path: Path) -> None:
    cq.exporters.export(shape, str(step_path))
    cq.exporters.export(shape, str(stl_path), tolerance=0.018, angularTolerance=0.06)


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    export_shape(assembly.toCompound(), step_path, stl_path)


def validate_step(path: Path) -> dict[str, object]:
    imported = cq.importers.importStep(str(path))
    solids = imported.solids().vals()
    bbox = imported.val().BoundingBox()
    explorer = TopExp_Explorer(imported.val().wrapped, TopAbs_FACE)
    face_count = 0
    bspline_count = 0
    while explorer.More():
        face_count += 1
        face = TopoDS.Face_s(explorer.Current())
        if BRepAdaptor_Surface(face, True).GetType() == GeomAbs_BSplineSurface:
            bspline_count += 1
        explorer.Next()
    return {
        "exists": path.is_file(),
        "bytes": path.stat().st_size,
        "solid_count": len(solids),
        "all_brep_valid": bool(solids) and all(BRepCheck_Analyzer(s.wrapped).IsValid() for s in solids),
        "bbox_mm": [round(bbox.xlen, 4), round(bbox.ylen, 4), round(bbox.zlen, 4)],
        "volume_mm3": round(sum(s.Volume() for s in solids), 4),
        "face_count": face_count,
        "bspline_face_count": bspline_count,
    }


def validate_stl(path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(path, force="mesh")
    return {
        "exists": path.is_file(),
        "bytes": path.stat().st_size,
        "watertight": bool(mesh.is_watertight),
        "component_count": len(mesh.split(only_watertight=False)),
        "bbox_mm": [round(float(v), 4) for v in mesh.extents],
        "face_count": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(archive.namelist())
        bad = archive.testzip()
    return {
        "exists": path.is_file(),
        "bytes": path.stat().st_size,
        "zip_valid": bad is None and "3D/3dmodel.model" in members,
        "members": members,
    }


def point_checks() -> dict[str, bool]:
    tray = build_bottom_tray().val()
    adapter = build_c_branch_adapter().val()
    accepted_top = build_top_frame().val()
    return {
        "tray_optical_axis_open": not tray.isInside(cq.Vector(0, 0, 4), 1e-6),
        "tray_slide_seat_open_at_top": not tray.isInside(cq.Vector(30, 0, 7.5), 1e-6),
        "tray_petri_seat_open_at_top": not tray.isInside(cq.Vector(0, 15, 7.0), 1e-6),
        "old_lower_rod_socket_location_is_solid": tray.isInside(cq.Vector(15, 15, 3.5), 1e-6),
        "registration_pocket_open": not tray.isInside(cq.Vector(12, 0, 1.0), 1e-6),
        "registration_pocket_has_roof": tray.isInside(cq.Vector(12, 0, 3.0), 1e-6),
        "adapter_optical_axis_open": not adapter.isInside(cq.Vector(0, 0, 1.0), 1e-6),
        "adapter_25mm_bore_open": not adapter.isInside(cq.Vector(12.4, 0, -2.0), 1e-6),
        "adapter_bore_wall_present": adapter.isInside(cq.Vector(13.0, 0, -2.0), 1e-6),
        "adapter_mouth_open": not adapter.isInside(cq.Vector(19.4, 0, -12.7), 1e-6),
        "adapter_mouth_lip_present": adapter.isInside(cq.Vector(19.8, 0, -12.7), 1e-6),
        "top_center_open": not accepted_top.isInside(cq.Vector(0, 0, 4), 1e-6),
    }


def run_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for checked CAD renders")
    subprocess.run([blender, "--background", "--python", str(DESIGN_DIR / f"render_{STEM}.py")], check=True)
    expected = [
        ARTIFACT_DIR / f"{STEM}_assembly_render.png",
        ARTIFACT_DIR / f"{STEM}_exploded_render.png",
        ARTIFACT_DIR / f"{STEM}_c_branch_fit_render.png",
        ARTIFACT_DIR / f"{STEM}_adapter_section_render.png",
        ARTIFACT_DIR / f"{STEM}_print_layout_render.png",
    ]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing checked renders: {missing}")


def copy_named(source_dir: Path, destination: Path, names: list[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(source_dir / name, destination / name)


def write_readme(path: Path, validation: dict[str, object]) -> None:
    path.write_text(
        f"""# OpenHI C-Branch Slide And Petri 35 Holder

This is a clean, decoupled variant of the accepted two-piece slide/Petri holder.
Every sample-facing feature is rebuilt by importing the accepted parametric
functions from `{PARAMS['accepted_geometry_source']}`. Only the lower four cage
rod sockets are removed and replaced by a separate smooth OpenHI C-branch
adapter.

## Measured C Interface

Source: `{PARAMS['measured_reference_source']}`.

- Plain nose/body: `24.4 mm` measured diameter.
- Thread crest envelope in the reference: about `25.2 mm`.
- Taper: `7.8 mm` axial length, from approximately `40 mm` to the nose.
- User-confirmed new socket: `25.0 mm` smooth ID, no generated thread.
- Adapter OD: `40.0 mm`, matching the OpenHI 4F tube OD.
- Taper mouth: `39.0 mm`; this leaves a printable `0.5 mm` radial lip and seats
  just before the original 40 mm shoulder.

The `25.0 mm` ID is intentionally tighter than the measured `25.2 mm` thread
crest. Print `PRINT_THIS_{STEM}_25mm_fit_coupon.*` before the full holder. Sand
or ream the coupon only after checking the physical C branch.

## Unchanged Sample Geometry

- Tray: `110 x 70 x 8 mm`.
- Slide seat: `75 x 22 mm`, `1.2 mm` deep, for the accepted `72.96 x 20 mm` strip.
- Petri seat: `35.4 mm`, `1.8 mm` deep, for a nominal `33 mm` dish.
- Optical opening: `18 mm`.
- Chamber gap: `18 mm`.
- Lock feet, finger access, anti-warp ears, and top frame are unchanged.

## Decoupled Parts

1. `bottom_tray`: accepted sample tray without lower cage holes; adds a
   `38.2 x 2.2 mm` underside registration pocket.
2. `c_branch_adapter`: independent `40 mm` OD socket with a `38.0 x 2.0 mm`
   registration spigot. Use adhesive after confirming fit.
3. `top_frame_180deg_print`: accepted top frame in its validated print orientation.
4. `25mm_fit_coupon`: fast physical fit check for the user-confirmed socket ID.

The assembly STEP keeps these as separate solids for clean Shapr3D editing.

## Print Files

- `PRINT_THIS_{STEM}_bottom_tray.*`
- `PRINT_THIS_{STEM}_c_branch_adapter_supported_orientation.*`
- `PRINT_THIS_{STEM}_top_frame_180deg.*`
- `PRINT_THIS_{STEM}_25mm_fit_coupon.*`
- `PRINT_THIS_{STEM}_all_parts_layout.*`

Print the adapter with the small registration/optical face on the build plate
and its wide tapered mouth upward. This avoids an unsupported 39 mm first-layer
opening.

## Validation

- Adapter STEP: {validation['adapter_step']['solid_count']} solid, bbox
  `{validation['adapter_step']['bbox_mm']} mm`, B-spline faces
  `{validation['adapter_step']['bspline_face_count']}`.
- Adapter STL watertight: `{validation['adapter_stl']['watertight']}`.
- Tray STEP: {validation['bottom_tray_step']['solid_count']} solids; STL
  watertight `{validation['bottom_tray_stl']['watertight']}`.
- Top frame matches accepted bbox and volume: `{validation['accepted_top_invariant']}`.
- 3MF files valid: `{validation['all_3mf_valid']}`.
- Feature checks: `{validation['point_checks']}`.

The OpenHI C body in the fit-check file is visualization-only and must not be
printed.
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    parts = {
        "bottom_tray": build_bottom_tray(),
        "top_frame": build_top_frame(),
        "top_frame_180deg": build_top_frame_print(),
        "c_branch_adapter": build_c_branch_adapter(),
        "c_branch_adapter_supported_orientation": build_adapter_print(),
        "25mm_fit_coupon": build_fit_coupon(),
        "adapter_half_section": build_adapter_half_section(),
        "openhi_c_reference_visualization_only": build_openhi_c_reference(),
    }
    paths: dict[str, Path] = {}
    for key, shape in parts.items():
        step = ARTIFACT_DIR / f"{STEM}_{key}.step"
        stl = ARTIFACT_DIR / f"{STEM}_{key}.stl"
        export_shape(shape, step, stl)
        paths[f"{key}_step"] = step
        paths[f"{key}_stl"] = stl

    for key in ("bottom_tray", "top_frame_180deg", "c_branch_adapter_supported_orientation", "25mm_fit_coupon"):
        target = ARTIFACT_DIR / f"{STEM}_{key}.3mf"
        export_stl_as_3mf(paths[f"{key}_stl"], target, title=f"{STEM} {key}")
        paths[f"{key}_3mf"] = target

    assemblies = {
        "assembly": build_assembly(),
        "reference_assembly": build_assembly(include_samples=True),
        "c_branch_fit_check": build_fit_check_assembly(),
        "exploded": build_exploded_assembly(),
        "all_parts_layout": build_print_layout(),
    }
    for key, assembly in assemblies.items():
        step = ARTIFACT_DIR / f"{STEM}_{key}.step"
        stl = ARTIFACT_DIR / f"{STEM}_{key}.stl"
        export_assembly(assembly, step, stl)
        paths[f"{key}_step"] = step
        paths[f"{key}_stl"] = stl
    layout_3mf = ARTIFACT_DIR / f"{STEM}_all_parts_layout.3mf"
    export_stl_as_3mf(paths["all_parts_layout_stl"], layout_3mf, title=f"{STEM} all printable parts")
    paths["all_parts_layout_3mf"] = layout_3mf

    validation = {
        "bottom_tray_step": validate_step(paths["bottom_tray_step"]),
        "bottom_tray_stl": validate_stl(paths["bottom_tray_stl"]),
        "top_frame_step": validate_step(paths["top_frame_step"]),
        "adapter_step": validate_step(paths["c_branch_adapter_step"]),
        "adapter_stl": validate_stl(paths["c_branch_adapter_stl"]),
        "adapter_print_stl": validate_stl(paths["c_branch_adapter_supported_orientation_stl"]),
        "fit_coupon_step": validate_step(paths["25mm_fit_coupon_step"]),
        "fit_coupon_stl": validate_stl(paths["25mm_fit_coupon_stl"]),
        "assembly_step": validate_step(paths["assembly_step"]),
        "print_layout_step": validate_step(paths["all_parts_layout_step"]),
        "print_layout_stl": validate_stl(paths["all_parts_layout_stl"]),
        "point_checks": point_checks(),
    }
    accepted_top_path = ACCEPTED_DIR / "artifacts/cage_sample_holder_two_piece_lock_slide_petri35_top_part.step"
    accepted_top = validate_step(accepted_top_path)
    validation["accepted_top_source"] = accepted_top
    validation["accepted_top_invariant"] = (
        validation["top_frame_step"]["bbox_mm"] == accepted_top["bbox_mm"]
        and validation["top_frame_step"]["solid_count"] == accepted_top["solid_count"]
        and abs(validation["top_frame_step"]["volume_mm3"] - accepted_top["volume_mm3"]) < 0.01
    )
    three_mf_keys = [key for key in paths if key.endswith("_3mf")]
    validation["three_mf"] = {key: validate_3mf(paths[key]) for key in three_mf_keys}
    validation["all_3mf_valid"] = all(item["zip_valid"] for item in validation["three_mf"].values())

    if validation["adapter_step"]["solid_count"] != 1 or not validation["adapter_step"]["all_brep_valid"]:
        raise RuntimeError("Adapter must be one valid B-rep solid")
    if validation["adapter_step"]["bbox_mm"] != [40.0, 40.0, 14.8]:
        raise RuntimeError(f"Unexpected adapter envelope: {validation['adapter_step']['bbox_mm']}")
    if validation["adapter_step"]["bspline_face_count"] != 0:
        raise RuntimeError("Smooth adapter must not contain fragile B-spline/thread faces")
    if not validation["adapter_stl"]["watertight"] or validation["adapter_stl"]["component_count"] != 1:
        raise RuntimeError("Adapter STL must be one watertight component")
    if not validation["bottom_tray_stl"]["watertight"]:
        raise RuntimeError("Bottom tray STL is not watertight")
    if not validation["accepted_top_invariant"]:
        raise RuntimeError("Accepted top-frame geometry drifted")
    if not all(validation["point_checks"].values()):
        raise RuntimeError(f"Feature checks failed: {validation['point_checks']}")
    if not validation["all_3mf_valid"]:
        raise RuntimeError("At least one 3MF package is invalid")

    run_blender()

    aliases = {
        f"USE_THIS_{STEM}_assembly.step": paths["assembly_step"],
        f"USE_THIS_{STEM}_c_branch_fit_check.step": paths["c_branch_fit_check_step"],
        f"PRINT_THIS_{STEM}_bottom_tray.step": paths["bottom_tray_step"],
        f"PRINT_THIS_{STEM}_bottom_tray.stl": paths["bottom_tray_stl"],
        f"PRINT_THIS_{STEM}_bottom_tray.3mf": paths["bottom_tray_3mf"],
        f"PRINT_THIS_{STEM}_c_branch_adapter_supported_orientation.step": paths["c_branch_adapter_supported_orientation_step"],
        f"PRINT_THIS_{STEM}_c_branch_adapter_supported_orientation.stl": paths["c_branch_adapter_supported_orientation_stl"],
        f"PRINT_THIS_{STEM}_c_branch_adapter_supported_orientation.3mf": paths["c_branch_adapter_supported_orientation_3mf"],
        f"PRINT_THIS_{STEM}_top_frame_180deg.step": paths["top_frame_180deg_step"],
        f"PRINT_THIS_{STEM}_top_frame_180deg.stl": paths["top_frame_180deg_stl"],
        f"PRINT_THIS_{STEM}_top_frame_180deg.3mf": paths["top_frame_180deg_3mf"],
        f"PRINT_THIS_{STEM}_25mm_fit_coupon.step": paths["25mm_fit_coupon_step"],
        f"PRINT_THIS_{STEM}_25mm_fit_coupon.stl": paths["25mm_fit_coupon_stl"],
        f"PRINT_THIS_{STEM}_25mm_fit_coupon.3mf": paths["25mm_fit_coupon_3mf"],
        f"PRINT_THIS_{STEM}_all_parts_layout.step": paths["all_parts_layout_step"],
        f"PRINT_THIS_{STEM}_all_parts_layout.stl": paths["all_parts_layout_stl"],
        f"PRINT_THIS_{STEM}_all_parts_layout.3mf": paths["all_parts_layout_3mf"],
    }
    render_names = [
        f"{STEM}_assembly_render.png",
        f"{STEM}_exploded_render.png",
        f"{STEM}_c_branch_fit_render.png",
        f"{STEM}_adapter_section_render.png",
        f"{STEM}_print_layout_render.png",
    ]
    for alias, source in aliases.items():
        shutil.copy2(source, DESIGN_DIR / alias)
    for name in render_names:
        shutil.copy2(ARTIFACT_DIR / name, DESIGN_DIR / f"USE_THIS_{name}")

    manifest = {
        "name": STEM,
        "run": RUN_NAME,
        "parameters": PARAMS,
        "validation": validation,
        "outputs": {key: str(value.relative_to(DESIGN_DIR)) for key, value in paths.items()},
        "root_aliases": sorted(aliases),
        "renders": render_names,
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(manifest_path, DESIGN_DIR / "manifest.json")
    write_readme(DESIGN_DIR / "README.md", validation)

    for old in RUN_ARTIFACT_DIR.iterdir():
        if old.is_file():
            old.unlink()
    for source in ARTIFACT_DIR.iterdir():
        if source.is_file() and source.suffix != ".blend1":
            shutil.copy2(source, RUN_ARTIFACT_DIR / source.name)
    shutil.copy2(Path(__file__), RUN_DIR / Path(__file__).name)
    shutil.copy2(DESIGN_DIR / f"render_{STEM}.py", RUN_DIR / f"render_{STEM}.py")

    handoff = [*aliases.keys(), "README.md", *[f"USE_THIS_{name}" for name in render_names]]
    copy_named(DESIGN_DIR, RUN_DIR, handoff)
    shutil.copy2(manifest_path, RUN_DIR / "manifest.json")
    copy_named(DESIGN_DIR, NUTSTORE_DIR, handoff)
    shutil.copy2(manifest_path, NUTSTORE_DIR / "manifest.json")
    NUTSTORE_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths["assembly_step"], NUTSTORE_ROOT / f"USE_THIS_{STEM}_assembly.step")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
