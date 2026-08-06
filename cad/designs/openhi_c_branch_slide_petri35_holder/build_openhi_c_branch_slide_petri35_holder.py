#!/usr/bin/env python3
"""Build the two-part OpenHI C-branch slide/Petri holder.

The printable assembly contains exactly two independent solids:

1. a sample tray with a bounded female 30 mm OpenHI thread; and
2. a socket that covers the C-branch nose and chamfer, then continues into a
   bounded 5 mm male 30 mm OpenHI thread that screws into the tray.

The accepted slide/Petri seat geometry and anti-warp ears are reused without
recreating their dimensions here.  No top frame, cage socket, coupon, or
adhesive registration piece is part of this run.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

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
RUN_NAME = "run-2-threaded-two-part-c-branch-holder-print-ready-20260806T034958Z"
RUN_DIR = DESIGN_DIR / "runs" / RUN_NAME
RUN_ARTIFACT_DIR = RUN_DIR / "artifacts"
NUTSTORE_ROOT = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
NUTSTORE_DIR = NUTSTORE_ROOT / STEM / RUN_NAME

ACCEPTED_DIR = ROOT / "cad/designs/cage_sample_holder_two_piece_lock_slide_petri35"
ACCEPTED_BUILDER_PATH = ACCEPTED_DIR / "build_cage_sample_holder_two_piece_lock_slide_petri35.py"
OPENHI_C_STEP = ROOT / "cad/extracted/OpenHI_STEP/C.step"

sys.path.insert(0, str(ROOT / "cad/tools"))
from simple_3mf import export_stl_as_3mf  # noqa: E402


THREAD_OVERLAP = 0.04


def load_accepted_builder():
    spec = importlib.util.spec_from_file_location("accepted_sample_holder", ACCEPTED_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load accepted holder builder: {ACCEPTED_BUILDER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ACCEPTED = load_accepted_builder()


PARAMS: dict[str, Any] = {
    "name": STEM,
    "run": RUN_NAME,
    "units": "mm",
    "design_mode": "two independent printable solids with a direct threaded interface",
    "accepted_geometry_source": str(ACCEPTED_BUILDER_PATH.relative_to(ROOT)),
    "measured_reference_source": str(OPENHI_C_STEP.relative_to(ROOT)),
    "printable_part_count": 2,
    "sample_holder_outer_mm": [110.0, 70.0],
    "sample_tray_thickness_mm": 8.0,
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
    "socket_outer_diameter_mm": 42.0,
    "socket_c_receiver_smooth_id_mm": 25.5,
    "socket_c_receiver_smooth_length_mm": 5.0,
    "socket_c_taper_length_mm": 7.8,
    "socket_c_taper_mouth_id_mm": 40.2,
    "socket_cup_length_mm": 12.8,
    "socket_male_thread_length_mm": 5.0,
    "socket_total_length_mm": 17.8,
    "male_thread_root_diameter_mm": 29.8,
    "male_thread_crest_diameter_mm": 30.2,
    "holder_female_thread_land_diameter_mm": 30.0,
    "holder_female_thread_groove_diameter_mm": 30.4,
    "thread_pitch_mm": 0.8,
    "thread_radial_height_mm": 0.2,
    "thread_tooth_base_mm": 0.8,
    "thread_runout_extra_each_end_mm": 0.4,
    "thread_diametral_clearance_at_land_mm": 0.2,
    "thread_diametral_clearance_at_crest_mm": 0.2,
    "socket_shoulder_contact_z_mm": 12.8,
    "holder_assembly_z_mm": 12.8,
    "c_reference_tip_z_mm": 11.7,
    "print_orientation_holder": "sample tray bottom and anti-warp ears on build plate",
    "print_orientation_socket": (
        "rotate 180 degrees so the 30 mm male-thread end rests on the build plate "
        "and the 40.2 mm C-branch cavity faces upward"
    ),
    "interface_note": (
        "The socket is one body: a 42 mm OD cup covers the 40 mm C-branch chamfer, "
        "and its upper end narrows to the 29.8/30.2 mm male thread. The tray is the "
        "second body and contains the matching 30.0/30.4 mm female thread."
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


def x_thread_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(length, span, span, centered=(False, True, True))
        .translate((x0, 0, 0))
    )


def x_thread_tooth(
    *,
    x0: float,
    length: float,
    root_diameter: float,
    crest_diameter: float,
) -> cq.Workplane:
    """Sweep a full-end helical tooth and clip it to the exact parent length."""
    pitch = PARAMS["thread_pitch_mm"]
    base = PARAMS["thread_tooth_base_mm"]
    extra = PARAMS["thread_runout_extra_each_end_mm"]
    height = (crest_diameter - root_diameter) / 2.0
    sweep_x0 = x0 - extra
    sweep_length = length + 2.0 * extra
    root_r = root_diameter / 2.0 - THREAD_OVERLAP
    path = cq.Wire.makeHelix(
        pitch,
        sweep_length,
        root_r,
        center=(sweep_x0, 0, 0),
        dir=(1, 0, 0),
        lefthand=True,
    )
    profile = (
        cq.Workplane("XY")
        .center(sweep_x0, root_r)
        .polyline([(0, 0), (base / 2.0, height + THREAD_OVERLAP), (base, 0)])
        .close()
    )
    tooth = profile.sweep(path, isFrenet=True, combine=False)
    return tooth.intersect(x_thread_clip_box(x0, length, crest_diameter + 4.0))


def z_thread_tooth(
    *,
    z0: float,
    length: float,
    root_diameter: float,
    crest_diameter: float,
) -> cq.Workplane:
    """Use the proven X-axis sweep, then rotate it onto the optical Z axis."""
    return (
        x_thread_tooth(
            x0=0.0,
            length=length,
            root_diameter=root_diameter,
            crest_diameter=crest_diameter,
        )
        .rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((0, 0, z0))
    )


def build_female_thread_cutter() -> cq.Workplane:
    p = PARAMS
    length = p["socket_male_thread_length_mm"]
    land_d = p["holder_female_thread_land_diameter_mm"]
    groove_d = p["holder_female_thread_groove_diameter_mm"]
    pilot = z_cylinder(land_d, length + 0.1, -0.05)
    tooth = z_thread_tooth(
        z0=0.0,
        length=length,
        root_diameter=land_d,
        crest_diameter=groove_d,
    )
    return pilot.union(tooth).clean()


def build_male_thread_local() -> cq.Workplane:
    p = PARAMS
    length = p["socket_male_thread_length_mm"]
    root_d = p["male_thread_root_diameter_mm"]
    crest_d = p["male_thread_crest_diameter_mm"]
    root = z_cylinder(root_d, length, 0.0)
    tooth = z_thread_tooth(
        z0=0.0,
        length=length,
        root_diameter=root_d,
        crest_diameter=crest_d,
    )
    return root.union(tooth).clean()


def build_sample_holder() -> cq.Workplane:
    """Reuse the accepted bottom sample geometry, omitting cage and lock parts."""
    part = ACCEPTED.base_plate()
    part = ACCEPTED.cut_bottom_sample_seats(part)
    part = ACCEPTED.add_anti_warp_ears(part, bed_face="bottom")
    return part.cut(build_female_thread_cutter()).clean()


def build_c_branch_socket() -> cq.Workplane:
    """Build one socket body spanning the C receiver and male tray thread."""
    p = PARAMS
    cup_length = p["socket_cup_length_mm"]
    part = z_cylinder(p["socket_outer_diameter_mm"], cup_length, 0.0)

    # Open the true 40.2 mm mouth explicitly, then continue through the 7.8 mm
    # taper and 25.5 mm smooth nose receiver. Slight cutter overlap avoids a
    # coplanar residual face without changing the specified fit envelope.
    mouth = z_cylinder(p["socket_c_taper_mouth_id_mm"], 0.2, -0.1)
    taper = z_cone(
        p["socket_c_taper_mouth_id_mm"],
        p["socket_c_receiver_smooth_id_mm"],
        p["socket_c_taper_length_mm"],
        0.0,
    )
    nose = z_cylinder(
        p["socket_c_receiver_smooth_id_mm"],
        p["socket_c_receiver_smooth_length_mm"] + 0.1,
        p["socket_c_taper_length_mm"] - 0.05,
    )
    part = part.cut(mouth).cut(taper).cut(nose)

    male = build_male_thread_local().translate((0, 0, cup_length))
    part = part.union(male)
    optical = z_cylinder(
        p["optical_window_diameter_mm"],
        p["socket_male_thread_length_mm"] + 0.2,
        cup_length - 0.1,
    )
    return part.cut(optical).clean()


def build_socket_print_orientation() -> cq.Workplane:
    total = PARAMS["socket_total_length_mm"]
    return (
        build_c_branch_socket()
        .rotate((0, 0, 0), (1, 0, 0), 180)
        .translate((0, 0, total))
    )


def build_openhi_c_reference() -> cq.Workplane:
    """Align and bound the real C-branch STEP for visual/interference checks."""
    reference = cq.importers.importStep(str(OPENHI_C_STEP))
    transformed = (
        reference
        .translate((-429.0, -210.0, -600.0))
        .rotate((0, 0, 0), (0, 1, 0), -90)
        .translate((0, 0, PARAMS["c_reference_tip_z_mm"]))
    )
    branch_clip = z_cylinder(40.2, 32.0, -20.0)
    return transformed.intersect(branch_clip)


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(
        build_c_branch_socket(),
        name="c_branch_socket_with_male30_thread",
        color=cq.Color(0.08, 0.38, 0.76, 1.0),
    )
    assembly.add(
        build_sample_holder().translate((0, 0, PARAMS["holder_assembly_z_mm"])),
        name="sample_holder_with_female30_thread",
        color=cq.Color(0.60, 0.58, 0.51, 1.0),
    )
    return assembly


def build_fit_check_assembly() -> cq.Assembly:
    assembly = build_assembly()
    assembly.add(
        build_openhi_c_reference(),
        name="measured_openhi_c_reference_visualization_only",
        color=cq.Color(0.95, 0.34, 0.05, 0.45),
    )
    return assembly


def build_exploded_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_exploded")
    assembly.add(
        build_c_branch_socket().translate((0, 0, -8.0)),
        name="c_branch_socket_with_male30_thread",
        color=cq.Color(0.08, 0.38, 0.76, 1.0),
    )
    assembly.add(
        build_sample_holder().translate((0, 0, 30.0)),
        name="sample_holder_with_female30_thread",
        color=cq.Color(0.60, 0.58, 0.51, 1.0),
    )
    return assembly


def build_print_layout() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_two_part_print_layout")
    assembly.add(
        build_sample_holder().translate((-92.0, 0, 0)),
        name="print_sample_holder",
        color=cq.Color(0.60, 0.58, 0.51, 1.0),
    )
    assembly.add(
        build_socket_print_orientation().translate((70.0, 0, 0)),
        name="print_c_branch_socket",
        color=cq.Color(0.08, 0.38, 0.76, 1.0),
    )
    return assembly


def build_thread_section() -> cq.Compound:
    holder = build_sample_holder().translate((0, 0, PARAMS["holder_assembly_z_mm"]))
    socket = build_c_branch_socket()
    clip = (
        cq.Workplane("XY")
        .box(55.0, 26.0, 35.0, centered=(True, False, False))
        .translate((0, 0, -2.0))
    )
    solids = [socket.intersect(clip).val(), holder.intersect(clip).val()]
    return cq.Compound.makeCompound(solids)


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


def inside(shape: cq.Shape, x: float, y: float, z: float) -> bool:
    return shape.isInside(cq.Vector(x, y, z), 1e-6)


def point_checks() -> dict[str, bool]:
    holder = build_sample_holder().val()
    socket = build_c_branch_socket().val()
    return {
        "holder_optical_axis_open": not inside(holder, 0, 0, 6.5),
        "holder_slide_seat_open_at_top": not inside(holder, 30, 0, 7.5),
        "holder_petri_seat_open_at_top": not inside(holder, 0, 15, 7.0),
        "old_lower_cage_socket_location_is_solid": inside(holder, 15, 15, 3.5),
        "old_lock_foot_is_absent": not inside(holder, 47, 27, 9.0),
        "female_land_is_open": not inside(holder, 14.9, 0, 2.0),
        "female_outer_wall_is_present": inside(holder, 15.3, 0, 2.0),
        "socket_optical_axis_open": not inside(socket, 0, 0, 15.0),
        "socket_smooth_c_receiver_is_open": not inside(socket, 12.7, 0, 10.0),
        "socket_smooth_receiver_wall_is_present": inside(socket, 13.0, 0, 10.0),
        "socket_taper_mouth_is_open": not inside(socket, 20.0, 0, 0.1),
        "socket_taper_mouth_wall_is_present": inside(socket, 20.8, 0, 0.1),
        "male_thread_root_is_present": inside(socket, 14.85, 0, 15.0),
        "socket_outside_is_empty": not inside(socket, 21.1, 0, 6.0),
    }


def intersection_volume(a: cq.Workplane, b: cq.Workplane) -> float:
    try:
        common = a.intersect(b)
        return round(sum(s.Volume() for s in common.solids().vals()), 6)
    except Exception:
        return -1.0


def run_blender() -> None:
    blender = shutil.which("blender")
    if not blender:
        raise RuntimeError("Blender is required for checked CAD renders")
    subprocess.run(
        [blender, "--background", "--python", str(DESIGN_DIR / f"render_{STEM}.py")],
        check=True,
    )
    expected = [
        ARTIFACT_DIR / f"{STEM}_assembly_render.png",
        ARTIFACT_DIR / f"{STEM}_exploded_render.png",
        ARTIFACT_DIR / f"{STEM}_c_branch_fit_render.png",
        ARTIFACT_DIR / f"{STEM}_thread_section_render.png",
        ARTIFACT_DIR / f"{STEM}_two_part_print_layout_render.png",
    ]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing checked renders: {missing}")


def remove_stale_latest_files() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for path in ARTIFACT_DIR.iterdir():
        if path.is_file():
            path.unlink()
    for pattern in ("PRINT_THIS_*", "USE_THIS_*"):
        for path in DESIGN_DIR.glob(pattern):
            if path.is_file():
                path.unlink()


def copy_named(source_dir: Path, destination: Path, names: list[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(source_dir / name, destination / name)


def write_readme(path: Path, validation: dict[str, object]) -> None:
    path.write_text(
        f"""# OpenHI C-Branch Slide And Petri 35 Holder

This run contains exactly two printable parts. The first is the bottom sample
tray/holder with the accepted slide and Petri-dish seats. The second is one
continuous socket that covers the OpenHI C-branch C-mount nose and chamfer and
then screws directly into the holder.

## Two Parts

1. `sample_holder_female30_thread`: accepted bottom tray geometry, without cage
   rod sockets, lock feet, or top frame. Its underside has a 5 mm female OpenHI
   30 mm thread.
2. `c_branch_socket_male30_thread`: a 42 mm OD cup with a 40.2-to-25.5 mm
   internal C-branch receiver and a 5 mm male OpenHI 30 mm thread at the holder
   end.

There is no coupon, top frame, adhesive spigot, or third connector part.

## C-Branch Receiver

Measured source: `{PARAMS['measured_reference_source']}`.

- Reference C nose/body: 24.4 mm.
- Reference thread crest envelope: about 25.2 mm.
- Smooth receiver ID: 25.5 mm.
- Reference chamfer/taper length: 7.8 mm.
- Receiver taper: 40.2 mm at the branch shoulder to 25.5 mm at the nose.
- Socket cup OD: 42.0 mm, leaving a 0.9 mm radial wall at the wide mouth.

The 42 mm cup is required to cover the approximately 40 mm C-branch chamfer.
The 29.8 mm dimension belongs only to the upper male thread root, not to the
lower C-branch cup.

## Direct Threaded Interface

- Pitch: 0.8 mm.
- Radial tooth height: 0.2 mm.
- Male root/crest: 29.8 / 30.2 mm.
- Female land/groove: 30.0 / 30.4 mm.
- Diametral clearance: 0.2 mm at both the land and crest pairs.
- Thread length: 5.0 mm.
- Both thread sweeps extend half a pitch during construction and are clipped
  back to their exact 5 mm parent length, so no tooth overflows either end.

## Print Files

- `PRINT_THIS_{STEM}_sample_holder_female30_thread.*`
- `PRINT_THIS_{STEM}_c_branch_socket_male30_thread.*`
- `PRINT_THIS_{STEM}_two_part_layout.*`

Print the tray normally with its anti-warp ears on the build plate. The socket
print export is already rotated so the male-thread end rests on the build plate
and the wide C-branch cavity points upward.

## Validation

- Holder STEP: {validation['holder_step']['solid_count']} valid solid; bbox
  `{validation['holder_step']['bbox_mm']} mm`.
- Socket STEP: {validation['socket_step']['solid_count']} valid solid; bbox
  `{validation['socket_step']['bbox_mm']} mm`.
- Assembly solid count: {validation['assembly_step']['solid_count']}.
- Print-layout STL components: {validation['print_layout_stl']['component_count']}.
- Holder/socket STL watertight: {validation['holder_stl']['watertight']} /
  {validation['socket_stl']['watertight']}.
- 3MF packages valid: {validation['all_3mf_valid']}.
- Thread clearances: {validation['thread_clearance_mm']}.
- Feature checks: {validation['point_checks']}.

The OpenHI C body in the fit-check file is visualization-only and must not be
printed.
""",
        encoding="utf-8",
    )


def main() -> None:
    remove_stale_latest_files()
    RUN_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    parts = {
        "sample_holder_female30_thread": build_sample_holder(),
        "c_branch_socket_male30_thread": build_c_branch_socket(),
        "c_branch_socket_male30_thread_print": build_socket_print_orientation(),
        "male30_thread_local": build_male_thread_local(),
        "female30_thread_cutter": build_female_thread_cutter(),
        "openhi_c_reference_visualization_only": build_openhi_c_reference(),
        "thread_section": build_thread_section(),
    }
    paths: dict[str, Path] = {}
    for key, shape in parts.items():
        step = ARTIFACT_DIR / f"{STEM}_{key}.step"
        stl = ARTIFACT_DIR / f"{STEM}_{key}.stl"
        export_shape(shape, step, stl)
        paths[f"{key}_step"] = step
        paths[f"{key}_stl"] = stl

    for key in ("sample_holder_female30_thread", "c_branch_socket_male30_thread_print"):
        target = ARTIFACT_DIR / f"{STEM}_{key}.3mf"
        export_stl_as_3mf(paths[f"{key}_stl"], target, title=f"{STEM} {key}")
        paths[f"{key}_3mf"] = target

    assemblies = {
        "assembly": build_assembly(),
        "c_branch_fit_check": build_fit_check_assembly(),
        "exploded": build_exploded_assembly(),
        "two_part_print_layout": build_print_layout(),
    }
    for key, assembly in assemblies.items():
        step = ARTIFACT_DIR / f"{STEM}_{key}.step"
        stl = ARTIFACT_DIR / f"{STEM}_{key}.stl"
        export_assembly(assembly, step, stl)
        paths[f"{key}_step"] = step
        paths[f"{key}_stl"] = stl

    layout_3mf = ARTIFACT_DIR / f"{STEM}_two_part_print_layout.3mf"
    export_stl_as_3mf(
        paths["two_part_print_layout_stl"],
        layout_3mf,
        title=f"{STEM} two printable parts",
    )
    paths["two_part_print_layout_3mf"] = layout_3mf

    holder_actual = build_sample_holder().translate((0, 0, PARAMS["holder_assembly_z_mm"]))
    validation = {
        "holder_step": validate_step(paths["sample_holder_female30_thread_step"]),
        "holder_stl": validate_stl(paths["sample_holder_female30_thread_stl"]),
        "socket_step": validate_step(paths["c_branch_socket_male30_thread_step"]),
        "socket_stl": validate_stl(paths["c_branch_socket_male30_thread_stl"]),
        "socket_print_stl": validate_stl(paths["c_branch_socket_male30_thread_print_stl"]),
        "male_thread_step": validate_step(paths["male30_thread_local_step"]),
        "female_cutter_step": validate_step(paths["female30_thread_cutter_step"]),
        "assembly_step": validate_step(paths["assembly_step"]),
        "print_layout_step": validate_step(paths["two_part_print_layout_step"]),
        "print_layout_stl": validate_stl(paths["two_part_print_layout_stl"]),
        "point_checks": point_checks(),
        "holder_socket_intersection_volume_mm3": intersection_volume(
            holder_actual,
            build_c_branch_socket(),
        ),
        "socket_c_reference_intersection_volume_mm3": intersection_volume(
            build_c_branch_socket(),
            build_openhi_c_reference(),
        ),
        "thread_clearance_mm": {
            "land_diametral": round(
                PARAMS["holder_female_thread_land_diameter_mm"]
                - PARAMS["male_thread_root_diameter_mm"],
                4,
            ),
            "crest_diametral": round(
                PARAMS["holder_female_thread_groove_diameter_mm"]
                - PARAMS["male_thread_crest_diameter_mm"],
                4,
            ),
        },
    }
    three_mf_keys = [key for key in paths if key.endswith("_3mf")]
    validation["three_mf"] = {key: validate_3mf(paths[key]) for key in three_mf_keys}
    validation["all_3mf_valid"] = all(item["zip_valid"] for item in validation["three_mf"].values())

    if validation["holder_step"]["solid_count"] != 1 or not validation["holder_step"]["all_brep_valid"]:
        raise RuntimeError("Holder must be one valid B-rep solid")
    if validation["socket_step"]["solid_count"] != 1 or not validation["socket_step"]["all_brep_valid"]:
        raise RuntimeError("Socket must be one valid B-rep solid")
    if validation["assembly_step"]["solid_count"] != 2:
        raise RuntimeError(f"Assembly must contain exactly two solids: {validation['assembly_step']}")
    if validation["socket_step"]["bbox_mm"] != [42.0, 42.0, 17.8]:
        raise RuntimeError(f"Unexpected socket envelope: {validation['socket_step']['bbox_mm']}")
    if validation["holder_step"]["bbox_mm"] != [161.0, 121.0, 8.0]:
        raise RuntimeError(f"Unexpected holder envelope: {validation['holder_step']['bbox_mm']}")
    if not validation["holder_stl"]["watertight"] or validation["holder_stl"]["component_count"] != 1:
        raise RuntimeError("Holder STL must be one watertight component")
    if not validation["socket_stl"]["watertight"] or validation["socket_stl"]["component_count"] != 1:
        raise RuntimeError("Socket STL must be one watertight component")
    if validation["print_layout_stl"]["component_count"] != 2:
        raise RuntimeError("Print layout must contain exactly two components")
    if not all(validation["point_checks"].values()):
        raise RuntimeError(f"Feature checks failed: {validation['point_checks']}")
    if validation["thread_clearance_mm"] != {"land_diametral": 0.2, "crest_diametral": 0.2}:
        raise RuntimeError(f"Unexpected thread clearance: {validation['thread_clearance_mm']}")
    if not validation["all_3mf_valid"]:
        raise RuntimeError("At least one 3MF package is invalid")

    run_blender()

    aliases = {
        f"USE_THIS_{STEM}_assembly.step": paths["assembly_step"],
        f"USE_THIS_{STEM}_c_branch_fit_check.step": paths["c_branch_fit_check_step"],
        f"PRINT_THIS_{STEM}_sample_holder_female30_thread.step": paths["sample_holder_female30_thread_step"],
        f"PRINT_THIS_{STEM}_sample_holder_female30_thread.stl": paths["sample_holder_female30_thread_stl"],
        f"PRINT_THIS_{STEM}_sample_holder_female30_thread.3mf": paths["sample_holder_female30_thread_3mf"],
        f"PRINT_THIS_{STEM}_c_branch_socket_male30_thread.step": paths["c_branch_socket_male30_thread_print_step"],
        f"PRINT_THIS_{STEM}_c_branch_socket_male30_thread.stl": paths["c_branch_socket_male30_thread_print_stl"],
        f"PRINT_THIS_{STEM}_c_branch_socket_male30_thread.3mf": paths["c_branch_socket_male30_thread_print_3mf"],
        f"PRINT_THIS_{STEM}_two_part_layout.step": paths["two_part_print_layout_step"],
        f"PRINT_THIS_{STEM}_two_part_layout.stl": paths["two_part_print_layout_stl"],
        f"PRINT_THIS_{STEM}_two_part_layout.3mf": paths["two_part_print_layout_3mf"],
    }
    render_names = [
        f"{STEM}_assembly_render.png",
        f"{STEM}_exploded_render.png",
        f"{STEM}_c_branch_fit_render.png",
        f"{STEM}_thread_section_render.png",
        f"{STEM}_two_part_print_layout_render.png",
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
