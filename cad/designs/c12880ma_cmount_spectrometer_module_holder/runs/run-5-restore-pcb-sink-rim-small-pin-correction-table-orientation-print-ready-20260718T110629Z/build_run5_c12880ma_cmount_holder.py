#!/usr/bin/env python3
"""Build run 5 by mapping the measured PCB into its mating holder face."""

from __future__ import annotations

import json
import math
import shutil
import sys
import zipfile
from pathlib import Path

import cadquery as cq
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
from cadquery import exporters
from OCP.BRepCheck import BRepCheck_Analyzer
import trimesh


ROOT = Path(__file__).resolve().parents[5]
RUN_DIR = Path(__file__).resolve().parent
DESIGN_DIR = RUN_DIR.parents[1]
ARTIFACT_DIR = RUN_DIR / "artifacts"
LATEST_ARTIFACT_DIR = DESIGN_DIR / "artifacts"
REFERENCE_DIR = ROOT / "cad/references/c12880ma-spectrometer-module"
TOOLS_DIR = ROOT / "cad/tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / DESIGN_DIR.name
    / RUN_DIR.name
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


STEM = "c12880ma_cmount_holder_42x42_mating_orientation_run5"
THREAD_BOOLEAN_OVERLAP_MM = 0.02
PRINT_BODY_OVERLAP_MM = 0.02

PARAMS = {
    "name": STEM,
    "units": "mm",
    "design_date": "2026-07-18",
    "baseline_run": (
        "run-3-component-side-orientation-pin-row-refined-print-ready-"
        "20260718T101655Z"
    ),
    "holder_plate_size_y_mm": 42.0,
    "holder_plate_size_z_mm": 42.0,
    "holder_plate_thickness_x_mm": 5.0,
    "rear_rim_height_x_mm": 2.0,
    "pcb_pocket_clearance_total_y_mm": 0.4,
    "pcb_pocket_clearance_total_z_mm": 0.4,
    "installed_pcb_recess_below_rim_mm": 0.5,
    "orientation_correction": (
        "The supplied values describe the component-side top view: sensor at the "
        "PCB top-left and the six-pin row below. Because that face mates against "
        "the holder, only the short-direction coordinates are inverted for the "
        "holder-side cutouts. The C-mount, plate, sink, thread, dimensions, and "
        "long-direction coordinates remain unchanged."
    ),
    "pcb_sink_construction_note": (
        "The original 5 mm plate and PCB seating datum are unchanged. A 2 mm "
        "rear rim is added only outside a 38.7 x 23.2 mm PCB pocket, so the "
        "1.5 mm PCB finishes 0.5 mm below the surrounding rim without moving "
        "the sensor toward the C-mount thread."
    ),
    "holder_plate_corner_radius_mm": 1.5,
    "cmount_socket_outer_diameter_mm": 34.0,
    "cmount_socket_length_x_mm": 16.0,
    "cmount_female_pilot_root_diameter_mm": 25.0,
    "cmount_female_thread_nominal_major_diameter_mm": 25.4,
    "cmount_thread_pitch_mm": 0.8,
    "cmount_thread_tooth_radial_height_mm": 0.2,
    "cmount_thread_tooth_base_mm": 0.8,
    "cmount_thread_start_x_mm": 0.2,
    "cmount_thread_length_x_mm": 5.0,
    "cmount_thread_half_pitch_runout_each_end_mm": 0.4,
    "pcb_length_y_mm": 38.3,
    "pcb_width_z_mm": 22.8,
    "pcb_thickness_x_mm": 1.5,
    "pcb_mount_hole_spacing_y_mm": 33.6,
    "left_mount_hole_to_sensor_axis_y_mm": 13.2,
    "pcb_left_edge_to_sensor_axis_y_mm": 15.55,
    "pcb_right_edge_from_sensor_axis_y_mm": 22.75,
    "source_component_view_pcb_top_edge_from_sensor_axis_z_mm": 10.3,
    "source_component_view_pcb_bottom_edge_from_sensor_axis_z_mm": 12.5,
    "source_component_view_pcb_center_z_from_sensor_axis_mm": -1.1,
    "source_component_view_six_pin_row_center_z_mm": -9.3,
    "pcb_top_edge_from_sensor_axis_z_mm": 12.5,
    "pcb_bottom_edge_from_sensor_axis_z_mm": 10.3,
    "pcb_center_y_from_sensor_axis_mm": 3.6,
    "pcb_center_z_from_sensor_axis_mm": 1.1,
    "holder_plate_center_y_from_sensor_axis_mm": 3.6,
    "holder_plate_center_z_from_sensor_axis_mm": 0.0,
    "left_mount_hole_y_mm": -13.2,
    "right_mount_hole_y_mm": 20.4,
    "mount_hole_z_mm": 0.0,
    "m2_printed_tap_pilot_diameter_mm": 1.6,
    "m2_printed_tap_pilot_depth_mm": 4.5,
    "pcb_proxy_mount_hole_diameter_mm": 2.4,
    "sensor_package_measured_max_y_mm": 20.5,
    "sensor_package_measured_max_z_mm": 13.0,
    "sensor_package_height_from_pcb_x_mm": 15.0,
    "sensor_package_clearance_y_mm": 20.9,
    "sensor_package_clearance_z_mm": 13.4,
    "sensor_package_clearance_corner_radius_mm": 1.5,
    "sensor_window_reference_diameter_mm": 3.2,
    "six_pin_count": 6,
    "six_pin_pitch_y_mm": 2.54,
    "six_pin_row_center_y_mm": -0.4,
    "six_pin_row_center_z_mm": 9.3,
    "six_pin_left_pcb_edge_margin_measured_mm": 9.0,
    "six_pin_right_pcb_edge_margin_measured_mm": 17.0,
    "six_pin_tail_relief_diameter_mm": 3.0,
    "six_pin_tail_relief_bridge_overlap_mm": 0.08,
    "six_pin_tail_reference_diameter_mm": 1.0,
    "six_pin_row_position_note": (
        "The source top view has the row below the sensor at Z=-9.3 mm. Its mating "
        "holder relief is therefore at Z=+9.3 mm. The run-1 long-direction position "
        "was already nearly correct: Y changes only from 0.0 to -0.4 mm, giving "
        "8.8 and 16.8 mm end margins. The 3.0 mm relief around a roughly 1.0 mm "
        "pin provides 1.0 mm radial clearance."
    ),
    "print_orientation": (
        "Socket front face on the build plate, C-mount axis vertical. This keeps the "
        "internal thread vertical and requires no generated support geometry."
    ),
    "source_priority": (
        "User caliper measurements and the exact vendor board image control module "
        "fit and mounting-hole placement; the official Hamamatsu datasheet controls "
        "the bare C12880MA package reference only."
    ),
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def x_cylinder(diameter: float, length: float, x0: float) -> cq.Workplane:
    return cq.Workplane("YZ").workplane(offset=x0).circle(diameter / 2.0).extrude(length)


def x_box(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def x_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(length, span, span, centered=(False, True, True))
        .translate((x0, 0, 0))
    )


def rounded_x_box(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    radius: float,
) -> cq.Workplane:
    box = x_box(center, size)
    try:
        return box.edges("|X").fillet(radius)
    except Exception:
        return box


def plate_x0() -> float:
    return PARAMS["cmount_socket_length_x_mm"]


def plate_rear_x() -> float:
    """Original PCB seating plane, intentionally unchanged from run 1."""
    return plate_x0() + PARAMS["holder_plate_thickness_x_mm"]


def rim_rear_x() -> float:
    return plate_rear_x() + PARAMS["rear_rim_height_x_mm"]


def board_geometry() -> dict[str, object]:
    left_edge = -PARAMS["pcb_left_edge_to_sensor_axis_y_mm"]
    right_edge = PARAMS["pcb_right_edge_from_sensor_axis_y_mm"]
    top_edge = PARAMS["pcb_top_edge_from_sensor_axis_z_mm"]
    bottom_edge = -PARAMS["pcb_bottom_edge_from_sensor_axis_z_mm"]
    pin_count = int(PARAMS["six_pin_count"])
    pitch = PARAMS["six_pin_pitch_y_mm"]
    first_y = PARAMS["six_pin_row_center_y_mm"] - (pin_count - 1) * pitch / 2.0
    pins = [
        {
            "index": index + 1,
            "y": round(first_y + index * pitch, 4),
            "z": PARAMS["six_pin_row_center_z_mm"],
            "relief_diameter_mm": PARAMS["six_pin_tail_relief_diameter_mm"],
        }
        for index in range(pin_count)
    ]
    holes = [
        {
            "name": "left_m2_tap_pilot",
            "y": PARAMS["left_mount_hole_y_mm"],
            "z": PARAMS["mount_hole_z_mm"],
        },
        {
            "name": "right_m2_tap_pilot",
            "y": PARAMS["right_mount_hole_y_mm"],
            "z": PARAMS["mount_hole_z_mm"],
        },
    ]
    return {
        "sensor_axis_yz_mm": [0.0, 0.0],
        "pcb_bounds_relative_to_sensor_axis_mm": {
            "y_min": left_edge,
            "y_max": right_edge,
            "z_min": bottom_edge,
            "z_max": top_edge,
        },
        "pcb_center_relative_to_sensor_axis_mm": {
            "y": PARAMS["pcb_center_y_from_sensor_axis_mm"],
            "z": PARAMS["pcb_center_z_from_sensor_axis_mm"],
        },
        "holder_plate_center_relative_to_sensor_axis_mm": {
            "y": PARAMS["holder_plate_center_y_from_sensor_axis_mm"],
            "z": PARAMS["holder_plate_center_z_from_sensor_axis_mm"],
        },
        "mount_holes_relative_to_sensor_axis_mm": holes,
        "six_pin_tail_reliefs_relative_to_sensor_axis_mm": pins,
        "derivation": {
            "pcb_end_margin_each_side_mm": round(
                (PARAMS["pcb_length_y_mm"] - PARAMS["pcb_mount_hole_spacing_y_mm"])
                / 2.0,
                4,
            ),
            "sensor_axis_from_left_pcb_edge_mm": PARAMS[
                "pcb_left_edge_to_sensor_axis_y_mm"
            ],
            "right_hole_from_sensor_axis_mm": PARAMS["right_mount_hole_y_mm"],
            "hole_positions_about_plate_center_mm": [
                round(
                    PARAMS["left_mount_hole_y_mm"]
                    - PARAMS["holder_plate_center_y_from_sensor_axis_mm"],
                    4,
                ),
                round(
                    PARAMS["right_mount_hole_y_mm"]
                    - PARAMS["holder_plate_center_y_from_sensor_axis_mm"],
                    4,
                ),
            ],
        },
    }


def external_thread_cutter(
    x0: float,
    length: float,
    root_diameter: float,
    extra_each_end: float,
) -> cq.Workplane:
    sweep_x0 = x0 - extra_each_end
    sweep_length = length + 2.0 * extra_each_end
    root_radius = root_diameter / 2.0 - THREAD_BOOLEAN_OVERLAP_MM
    path = cq.Wire.makeHelix(
        PARAMS["cmount_thread_pitch_mm"],
        sweep_length,
        root_radius,
        center=(sweep_x0, 0, 0),
        dir=(1, 0, 0),
        lefthand=True,
    )
    profile = (
        cq.Workplane("XY")
        .center(sweep_x0, root_radius)
        .polyline(
            [
                (0.0, 0.0),
                (
                    PARAMS["cmount_thread_tooth_base_mm"] / 2.0,
                    PARAMS["cmount_thread_tooth_radial_height_mm"]
                    + THREAD_BOOLEAN_OVERLAP_MM,
                ),
                (PARAMS["cmount_thread_tooth_base_mm"], 0.0),
            ]
        )
        .close()
    )
    thread = profile.sweep(path, isFrenet=True, combine=False)
    span = PARAMS["cmount_female_thread_nominal_major_diameter_mm"] + 4.0
    return thread.intersect(x_clip_box(sweep_x0, sweep_length, span))


def female_thread_cutter() -> cq.Workplane:
    return external_thread_cutter(
        PARAMS["cmount_thread_start_x_mm"],
        PARAMS["cmount_thread_length_x_mm"],
        PARAMS["cmount_female_pilot_root_diameter_mm"],
        PARAMS["cmount_thread_half_pitch_runout_each_end_mm"],
    )


def female_bore_cutter(length_extra: float = 0.4) -> cq.Workplane:
    return x_cylinder(
        PARAMS["cmount_female_pilot_root_diameter_mm"],
        PARAMS["cmount_socket_length_x_mm"] + length_extra,
        -length_extra / 2.0,
    )


def package_clearance_cutter(x0: float, length: float) -> cq.Workplane:
    return rounded_x_box(
        (x0 + length / 2.0, 0.0, 0.0),
        (
            length,
            PARAMS["sensor_package_clearance_y_mm"],
            PARAMS["sensor_package_clearance_z_mm"],
        ),
        PARAMS["sensor_package_clearance_corner_radius_mm"],
    )


def pcb_pocket_cutter(x0: float, length: float) -> cq.Workplane:
    return rounded_x_box(
        (
            x0 + length / 2.0,
            PARAMS["pcb_center_y_from_sensor_axis_mm"],
            PARAMS["pcb_center_z_from_sensor_axis_mm"],
        ),
        (
            length,
            PARAMS["pcb_length_y_mm"]
            + PARAMS["pcb_pocket_clearance_total_y_mm"],
            PARAMS["pcb_width_z_mm"]
            + PARAMS["pcb_pocket_clearance_total_z_mm"],
        ),
        1.0,
    )


def build_rear_rim() -> cq.Workplane:
    height = PARAMS["rear_rim_height_x_mm"]
    rim = rounded_x_box(
        (
            plate_rear_x() + height / 2.0,
            PARAMS["holder_plate_center_y_from_sensor_axis_mm"],
            PARAMS["holder_plate_center_z_from_sensor_axis_mm"],
        ),
        (
            height,
            PARAMS["holder_plate_size_y_mm"],
            PARAMS["holder_plate_size_z_mm"],
        ),
        PARAMS["holder_plate_corner_radius_mm"],
    )
    return rim.cut(
        pcb_pocket_cutter(plate_rear_x() - 0.2, height + 0.4)
    ).clean()


def pin_tail_relief_cutter(x0: float, length: float) -> cq.Workplane:
    geometry = board_geometry()
    pins = geometry["six_pin_tail_reliefs_relative_to_sensor_axis_mm"]
    cutters = [
        x_cylinder(PARAMS["six_pin_tail_relief_diameter_mm"], length, x0).translate(
            (0.0, pin["y"], pin["z"])
        )
        for pin in pins
    ]
    first_y = pins[0]["y"]
    last_y = pins[-1]["y"]
    cutters.append(
        x_box(
            (
                x0 + length / 2.0,
                (first_y + last_y) / 2.0,
                PARAMS["six_pin_row_center_z_mm"],
            ),
            (
                length,
                last_y
                - first_y
                + PARAMS["six_pin_tail_relief_bridge_overlap_mm"],
                PARAMS["six_pin_tail_relief_diameter_mm"],
            ),
        )
    )
    result = cutters[0]
    for cutter in cutters[1:]:
        result = result.union(cutter)
    return result.clean()


def m2_pilot_cutter(y: float, z: float) -> cq.Workplane:
    depth = PARAMS["m2_printed_tap_pilot_depth_mm"]
    return x_cylinder(
        PARAMS["m2_printed_tap_pilot_diameter_mm"],
        depth + 0.2,
        plate_rear_x() - depth,
    ).translate((0.0, y, z))


def build_cmount_socket(threaded: bool = True, overlap: float = 0.0) -> cq.Workplane:
    socket = x_cylinder(
        PARAMS["cmount_socket_outer_diameter_mm"],
        PARAMS["cmount_socket_length_x_mm"] + overlap,
        0.0,
    )
    socket = socket.cut(female_bore_cutter(overlap + 0.4))
    if threaded:
        socket = socket.cut(female_thread_cutter())
    return socket.clean()


def build_holder_plate(x_overlap: float = 0.0) -> cq.Workplane:
    x0 = plate_x0() - x_overlap
    thickness = PARAMS["holder_plate_thickness_x_mm"] + x_overlap
    plate = rounded_x_box(
        (
            x0 + thickness / 2.0,
            PARAMS["holder_plate_center_y_from_sensor_axis_mm"],
            PARAMS["holder_plate_center_z_from_sensor_axis_mm"],
        ),
        (
            thickness,
            PARAMS["holder_plate_size_y_mm"],
            PARAMS["holder_plate_size_z_mm"],
        ),
        PARAMS["holder_plate_corner_radius_mm"],
    )
    plate = plate.union(build_rear_rim()).clean()
    plate = plate.cut(package_clearance_cutter(x0 - 0.2, thickness + 0.4))
    plate = plate.cut(pin_tail_relief_cutter(x0 - 0.2, thickness + 0.4))
    geometry = board_geometry()
    for hole in geometry["mount_holes_relative_to_sensor_axis_mm"]:
        plate = plate.cut(m2_pilot_cutter(hole["y"], hole["z"]))
    return plate.clean()


def build_print_body(threaded: bool = True) -> cq.Workplane:
    socket = build_cmount_socket(threaded=threaded, overlap=PRINT_BODY_OVERLAP_MM)
    plate = build_holder_plate(x_overlap=PRINT_BODY_OVERLAP_MM)
    return socket.union(plate).clean()


def build_decoupled_holder() -> cq.Compound:
    return cq.Compound.makeCompound(
        [build_cmount_socket(threaded=True).val(), build_holder_plate().val()]
    )


def build_board_proxy() -> cq.Workplane:
    board = x_box(
        (
            plate_rear_x() + PARAMS["pcb_thickness_x_mm"] / 2.0,
            PARAMS["pcb_center_y_from_sensor_axis_mm"],
            PARAMS["pcb_center_z_from_sensor_axis_mm"],
        ),
        (
            PARAMS["pcb_thickness_x_mm"],
            PARAMS["pcb_length_y_mm"],
            PARAMS["pcb_width_z_mm"],
        ),
    )
    for y in (PARAMS["left_mount_hole_y_mm"], PARAMS["right_mount_hole_y_mm"]):
        board = board.cut(
            x_cylinder(
                PARAMS["pcb_proxy_mount_hole_diameter_mm"],
                PARAMS["pcb_thickness_x_mm"] + 0.4,
                plate_rear_x() - 0.2,
            ).translate((0.0, y, PARAMS["mount_hole_z_mm"]))
        )
    return board.clean()


def build_sensor_package_proxy() -> cq.Workplane:
    height = PARAMS["sensor_package_height_from_pcb_x_mm"]
    front_x = plate_rear_x() - height
    package = rounded_x_box(
        (front_x + height / 2.0, 0.0, 0.0),
        (
            height,
            PARAMS["sensor_package_measured_max_y_mm"],
            PARAMS["sensor_package_measured_max_z_mm"],
        ),
        1.4,
    )
    window = x_cylinder(
        PARAMS["sensor_window_reference_diameter_mm"], 0.5, front_x - 0.5
    )
    return package.union(window).clean()


def build_pin_tail_proxy() -> cq.Compound:
    geometry = board_geometry()
    pins = []
    for pin in geometry["six_pin_tail_reliefs_relative_to_sensor_axis_mm"]:
        pins.append(
            x_cylinder(
                PARAMS["six_pin_tail_reference_diameter_mm"],
                2.8,
                plate_rear_x() - 1.5,
            )
            .translate((0.0, pin["y"], pin["z"]))
            .val()
        )
    return cq.Compound.makeCompound(pins)


def build_optical_axis_proxy() -> cq.Workplane:
    return x_cylinder(0.8, plate_rear_x() + 7.0, -3.0)


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(
        build_cmount_socket(threaded=True),
        name="independent_cmount_socket_25p0_25p4",
        color=cq.Color(0.16, 0.17, 0.18, 1.0),
    )
    assembly.add(
        build_holder_plate(),
        name="independent_42x42_plate_with_verified_component_orientation",
        color=cq.Color(0.33, 0.35, 0.38, 1.0),
    )
    assembly.add(
        build_board_proxy(),
        name="c12880_module_pcb_proxy_sensor_up_socket_down",
        color=cq.Color(0.02, 0.34, 0.20, 0.85),
    )
    assembly.add(
        build_sensor_package_proxy(),
        name="measured_c12880_package_proxy_centered_on_cmount_axis",
        color=cq.Color(0.68, 0.70, 0.72, 1.0),
    )
    assembly.add(
        build_pin_tail_proxy(),
        name="six_pin_solder_tail_proxy_inside_connected_relief",
        color=cq.Color(0.92, 0.48, 0.08, 1.0),
    )
    assembly.add(
        build_optical_axis_proxy(),
        name="optical_axis_proxy",
        color=cq.Color(0.96, 0.74, 0.06, 0.75),
    )
    return assembly


def print_orientation(shape: cq.Workplane) -> cq.Workplane:
    return shape.rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)


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
        "bbox_mm": [
            round(bbox.xlen, 4),
            round(bbox.ylen, 4),
            round(bbox.zlen, 4),
        ],
    }


def validate_stl(path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(path, force="mesh")
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "watertight": bool(mesh.is_watertight),
        "body_count": int(mesh.body_count),
        "extents_mm": [round(float(value), 4) for value in mesh.extents],
        "face_count": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        names = sorted(archive.namelist())
    return {
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "zip_valid": "3D/3dmodel.model" in names,
        "members": names,
    }


def geometry_checks() -> dict[str, object]:
    geometry = board_geometry()
    bounds = geometry["pcb_bounds_relative_to_sensor_axis_mm"]
    pins = geometry["six_pin_tail_reliefs_relative_to_sensor_axis_mm"]
    plate_y_min = (
        PARAMS["holder_plate_center_y_from_sensor_axis_mm"]
        - PARAMS["holder_plate_size_y_mm"] / 2.0
    )
    plate_y_max = (
        PARAMS["holder_plate_center_y_from_sensor_axis_mm"]
        + PARAMS["holder_plate_size_y_mm"] / 2.0
    )
    plate_z_min = -PARAMS["holder_plate_size_z_mm"] / 2.0
    plate_z_max = PARAMS["holder_plate_size_z_mm"] / 2.0
    package_corner_radius = math.hypot(
        PARAMS["sensor_package_clearance_y_mm"] / 2.0,
        PARAMS["sensor_package_clearance_z_mm"] / 2.0,
    )
    thread_end = (
        PARAMS["cmount_thread_start_x_mm"] + PARAMS["cmount_thread_length_x_mm"]
    )
    package_front = plate_rear_x() - PARAMS["sensor_package_height_from_pcb_x_mm"]
    checks = {
        "sensor_axis_is_cmount_axis": [0.0, 0.0],
        "source_view_is_sensor_top_left_and_pin_row_below": (
            math.isclose(
                PARAMS["source_component_view_pcb_center_z_from_sensor_axis_mm"],
                -1.1,
            )
            and math.isclose(
                PARAMS["source_component_view_six_pin_row_center_z_mm"], -9.3
            )
        ),
        "holder_view_is_source_long_edge_flip": (
            math.isclose(PARAMS["pcb_center_z_from_sensor_axis_mm"], 1.1)
            and math.isclose(PARAMS["six_pin_row_center_z_mm"], 9.3)
            and math.isclose(bounds["z_min"], -10.3)
            and math.isclose(bounds["z_max"], 12.5)
        ),
        "holder_side_pcb_center_z_mm": PARAMS["pcb_center_z_from_sensor_axis_mm"],
        "holder_side_six_pin_row_z_mm": PARAMS["six_pin_row_center_z_mm"],
        "sensor_is_closer_to_left_edge": (
            PARAMS["pcb_left_edge_to_sensor_axis_y_mm"]
            < PARAMS["pcb_right_edge_from_sensor_axis_y_mm"]
        ),
        "six_pin_row_center_refined_y_mm": PARAMS["six_pin_row_center_y_mm"],
        "six_pin_y_adjustment_from_run1_is_only_0p4_mm": math.isclose(
            PARAMS["six_pin_row_center_y_mm"], -0.4
        ),
        "six_pin_first_center_from_left_edge_mm": round(
            pins[0]["y"] - bounds["y_min"], 4
        ),
        "six_pin_last_center_from_right_edge_mm": round(
            bounds["y_max"] - pins[-1]["y"], 4
        ),
        "six_pin_radial_clearance_mm": round(
            (
                PARAMS["six_pin_tail_relief_diameter_mm"]
                - PARAMS["six_pin_tail_reference_diameter_mm"]
            )
            / 2.0,
            4,
        ),
        "hole_spacing_is_33p6_mm": math.isclose(
            PARAMS["right_mount_hole_y_mm"] - PARAMS["left_mount_hole_y_mm"],
            PARAMS["pcb_mount_hole_spacing_y_mm"],
            abs_tol=1e-9,
        ),
        "holes_are_symmetric_about_plate_center": math.isclose(
            (
                PARAMS["right_mount_hole_y_mm"]
                + PARAMS["left_mount_hole_y_mm"]
            )
            / 2.0,
            PARAMS["holder_plate_center_y_from_sensor_axis_mm"],
            abs_tol=1e-9,
        ),
        "pcb_fits_42x42_plate": (
            bounds["y_min"] >= plate_y_min
            and bounds["y_max"] <= plate_y_max
            and bounds["z_min"] >= plate_z_min
            and bounds["z_max"] <= plate_z_max
        ),
        "socket_od_fits_plate": (
            -PARAMS["cmount_socket_outer_diameter_mm"] / 2.0 >= plate_y_min
            and PARAMS["cmount_socket_outer_diameter_mm"] / 2.0 <= plate_y_max
            and -PARAMS["cmount_socket_outer_diameter_mm"] / 2.0 >= plate_z_min
            and PARAMS["cmount_socket_outer_diameter_mm"] / 2.0 <= plate_z_max
        ),
        "rectangular_package_clearance_fits_25mm_chamber": (
            package_corner_radius
            < PARAMS["cmount_female_pilot_root_diameter_mm"] / 2.0
        ),
        "thread_to_sensor_front_gap_mm": round(package_front - thread_end, 4),
        "thread_does_not_reach_sensor_package": package_front > thread_end,
        "pcb_seating_plane_unchanged_from_run1_mm": plate_rear_x(),
        "rim_rear_plane_mm": rim_rear_x(),
        "installed_pcb_top_plane_mm": round(
            plate_rear_x() + PARAMS["pcb_thickness_x_mm"], 4
        ),
        "installed_pcb_is_sunk_below_rim_mm": round(
            rim_rear_x()
            - (plate_rear_x() + PARAMS["pcb_thickness_x_mm"]),
            4,
        ),
        "pcb_sink_is_exactly_0p5_mm_after_install": math.isclose(
            rim_rear_x()
            - (plate_rear_x() + PARAMS["pcb_thickness_x_mm"]),
            PARAMS["installed_pcb_recess_below_rim_mm"],
            abs_tol=1e-9,
        ),
        "sensor_front_unchanged_at_x_mm": package_front,
        "six_pin_relief_is_on_pcb_footprint": all(
            bounds["y_min"] <= pin["y"] <= bounds["y_max"]
            and bounds["z_min"] <= pin["z"] <= bounds["z_max"]
            for pin in geometry["six_pin_tail_reliefs_relative_to_sensor_axis_mm"]
        ),
        "plate_bounds_y_mm": [plate_y_min, plate_y_max],
        "plate_bounds_z_mm": [plate_z_min, plate_z_max],
        "pcb_bounds_yz_mm": bounds,
    }
    return checks


def save_figure_outputs(fig: object, path_base: Path) -> None:
    for suffix in (".png", ".pdf", ".svg"):
        output = path_base.with_suffix(suffix)
        fig.savefig(output, bbox_inches="tight")
        if suffix == ".svg":
            lines = output.read_text(encoding="utf-8").splitlines()
            output.write_text(
                "\n".join(line.rstrip() for line in lines) + "\n",
                encoding="utf-8",
            )


def draw_holder_side_alignment(path_base: Path) -> None:
    geometry = board_geometry()
    bounds = geometry["pcb_bounds_relative_to_sensor_axis_mm"]
    fig, ax = plt.subplots(figsize=(9.4, 8.0), dpi=180)
    plate_y_min = (
        PARAMS["holder_plate_center_y_from_sensor_axis_mm"]
        - PARAMS["holder_plate_size_y_mm"] / 2.0
    )
    plate_z_min = -PARAMS["holder_plate_size_z_mm"] / 2.0
    ax.add_patch(
        FancyBboxPatch(
            (plate_y_min, plate_z_min),
            PARAMS["holder_plate_size_y_mm"],
            PARAMS["holder_plate_size_z_mm"],
            boxstyle="round,pad=0,rounding_size=1.5",
            facecolor="#e8ecef",
            edgecolor="#252a2e",
            linewidth=2.0,
            label="42 x 42 holder plate",
        )
    )
    ax.add_patch(
        Circle(
            (0.0, 0.0),
            PARAMS["cmount_socket_outer_diameter_mm"] / 2.0,
            facecolor="#cfd5d9",
            edgecolor="#596168",
            linewidth=1.5,
            alpha=0.72,
            label="34 mm C-mount OD",
        )
    )
    ax.add_patch(
        Rectangle(
            (bounds["y_min"], bounds["z_min"]),
            PARAMS["pcb_length_y_mm"],
            PARAMS["pcb_width_z_mm"],
            facecolor="#b8e0c8",
            edgecolor="#137a48",
            linestyle="--",
            linewidth=2.0,
            alpha=0.82,
            label="38.3 x 22.8 PCB",
        )
    )
    pocket_y_min = (
        PARAMS["pcb_center_y_from_sensor_axis_mm"]
        - (
            PARAMS["pcb_length_y_mm"]
            + PARAMS["pcb_pocket_clearance_total_y_mm"]
        )
        / 2.0
    )
    pocket_z_min = (
        PARAMS["pcb_center_z_from_sensor_axis_mm"]
        - (
            PARAMS["pcb_width_z_mm"]
            + PARAMS["pcb_pocket_clearance_total_z_mm"]
        )
        / 2.0
    )
    ax.add_patch(
        FancyBboxPatch(
            (pocket_y_min, pocket_z_min),
            PARAMS["pcb_length_y_mm"]
            + PARAMS["pcb_pocket_clearance_total_y_mm"],
            PARAMS["pcb_width_z_mm"]
            + PARAMS["pcb_pocket_clearance_total_z_mm"],
            boxstyle="round,pad=0,rounding_size=1.0",
            facecolor="none",
            edgecolor="#6f42c1",
            linestyle=":",
            linewidth=2.0,
            label="2 mm raised-rim PCB pocket boundary",
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (
                -PARAMS["sensor_package_clearance_y_mm"] / 2.0,
                -PARAMS["sensor_package_clearance_z_mm"] / 2.0,
            ),
            PARAMS["sensor_package_clearance_y_mm"],
            PARAMS["sensor_package_clearance_z_mm"],
            boxstyle="round,pad=0,rounding_size=1.5",
            facecolor="#b9bdc1",
            edgecolor="#303438",
            linewidth=1.5,
            label="20.9 x 13.4 package clearance",
        )
    )
    for hole in geometry["mount_holes_relative_to_sensor_axis_mm"]:
        ax.add_patch(
            Circle(
                (hole["y"], hole["z"]),
                PARAMS["m2_printed_tap_pilot_diameter_mm"] / 2.0,
                facecolor="#ffffff",
                edgecolor="#8a2f2f",
                linewidth=1.7,
            )
        )
    pins = geometry["six_pin_tail_reliefs_relative_to_sensor_axis_mm"]
    first_y = pins[0]["y"]
    last_y = pins[-1]["y"]
    ax.add_patch(
        FancyBboxPatch(
            (
                first_y - PARAMS["six_pin_tail_relief_diameter_mm"] / 2.0,
                PARAMS["six_pin_row_center_z_mm"]
                - PARAMS["six_pin_tail_relief_diameter_mm"] / 2.0,
            ),
            last_y - first_y + PARAMS["six_pin_tail_relief_diameter_mm"],
            PARAMS["six_pin_tail_relief_diameter_mm"],
            boxstyle="round,pad=0,rounding_size=1.5",
            facecolor="#f8d2a0",
            edgecolor="#b85a00",
            linewidth=1.6,
            label="6P connected solder-tail relief",
        )
    )
    for pin in pins:
        ax.add_patch(
            Circle(
                (pin["y"], pin["z"]),
                PARAMS["six_pin_tail_relief_diameter_mm"] / 2.0,
                facecolor="#f8d2a0",
                edgecolor="#b85a00",
                linewidth=0.8,
            )
        )
    ax.plot(0.0, 0.0, marker="+", markersize=18, markeredgewidth=2.5, color="#cc1f1f")
    ax.annotate(
        "C-mount / sensor axis",
        xy=(0.0, 0.0),
        xytext=(4.0, 7.8),
        arrowprops={"arrowstyle": "->", "color": "#cc1f1f"},
        fontsize=10,
    )
    ax.annotate(
        "33.6 mm hole spacing",
        xy=(PARAMS["left_mount_hole_y_mm"], 1.7),
        xytext=(PARAMS["right_mount_hole_y_mm"], 1.7),
        ha="right",
        arrowprops={"arrowstyle": "<->", "color": "#8a2f2f"},
        fontsize=10,
        color="#8a2f2f",
    )
    ax.set_title("C12880MA holder mating face: source short direction inverted")
    ax.set_xlabel("PCB long direction Y (mm)")
    ax.set_ylabel("PCB short direction Z (mm)")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-19.5, 26.7)
    ax.set_ylim(-23.0, 23.0)
    ax.grid(True, linewidth=0.5, color="#d8dde1")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.95)
    fig.tight_layout()
    save_figure_outputs(fig, path_base)
    plt.close(fig)


def draw_side_section(path_base: Path) -> None:
    fig, ax = plt.subplots(figsize=(11.0, 4.8), dpi=180)
    socket_length = PARAMS["cmount_socket_length_x_mm"]
    plate_thickness = PARAMS["holder_plate_thickness_x_mm"]
    rear = plate_rear_x()
    rim_rear = rim_rear_x()
    package_front = rear - PARAMS["sensor_package_height_from_pcb_x_mm"]
    ax.add_patch(
        Rectangle(
            (0.0, -17.0),
            socket_length,
            34.0,
            facecolor="#cfd5d9",
            edgecolor="#353a3e",
            linewidth=1.5,
            label="C-mount socket",
        )
    )
    ax.add_patch(
        Rectangle(
            (0.0, -12.5),
            socket_length,
            25.0,
            facecolor="white",
            edgecolor="#6c747a",
            linewidth=1.0,
        )
    )
    ax.add_patch(
        Rectangle(
            (socket_length, -21.0),
            plate_thickness,
            42.0,
            facecolor="#e8ecef",
            edgecolor="#252a2e",
            linewidth=1.5,
            label="5 mm holder plate",
        )
    )
    pocket_top = (
        PARAMS["pcb_center_z_from_sensor_axis_mm"]
        + (
            PARAMS["pcb_width_z_mm"]
            + PARAMS["pcb_pocket_clearance_total_z_mm"]
        )
        / 2.0
    )
    pocket_bottom = (
        PARAMS["pcb_center_z_from_sensor_axis_mm"]
        - (
            PARAMS["pcb_width_z_mm"]
            + PARAMS["pcb_pocket_clearance_total_z_mm"]
        )
        / 2.0
    )
    ax.add_patch(
        Rectangle(
            (rear, pocket_top),
            PARAMS["rear_rim_height_x_mm"],
            21.0 - pocket_top,
            facecolor="#c1c8cd",
            edgecolor="#252a2e",
            linewidth=1.3,
            label="2 mm raised rear rim",
        )
    )
    ax.add_patch(
        Rectangle(
            (rear, -21.0),
            PARAMS["rear_rim_height_x_mm"],
            pocket_bottom + 21.0,
            facecolor="#c1c8cd",
            edgecolor="#252a2e",
            linewidth=1.3,
        )
    )
    ax.add_patch(
        Rectangle(
            (package_front, -6.5),
            PARAMS["sensor_package_height_from_pcb_x_mm"],
            13.0,
            facecolor="#aeb4b8",
            edgecolor="#303438",
            linewidth=1.4,
            label="15 mm measured sensor package",
        )
    )
    ax.add_patch(
        Rectangle(
            (rear, -PARAMS["pcb_bottom_edge_from_sensor_axis_z_mm"]),
            PARAMS["pcb_thickness_x_mm"],
            PARAMS["pcb_width_z_mm"],
            facecolor="#8ac5a2",
            edgecolor="#137a48",
            linewidth=1.4,
            label="PCB",
        )
    )
    thread_end = PARAMS["cmount_thread_start_x_mm"] + PARAMS["cmount_thread_length_x_mm"]
    ax.axvspan(
        PARAMS["cmount_thread_start_x_mm"],
        thread_end,
        ymin=0.34,
        ymax=0.66,
        color="#e48c45",
        alpha=0.7,
        label="5 mm female thread region",
    )
    ax.annotate(
        f"{package_front - thread_end:.1f} mm clear gap",
        xy=((thread_end + package_front) / 2.0, 9.8),
        ha="center",
        fontsize=10,
        color="#8a3d00",
    )
    ax.axhline(0.0, color="#cc1f1f", linewidth=1.0, linestyle="--")
    ax.annotate(
        "PCB top is 0.5 mm below rim",
        xy=(rear + PARAMS["pcb_thickness_x_mm"], 12.0),
        xytext=(rim_rear + 1.5, 15.0),
        arrowprops={"arrowstyle": "->", "color": "#137a48"},
        fontsize=9,
        color="#137a48",
    )
    ax.set_xlim(-1.0, rim_rear + 4.0)
    ax.set_ylim(-23.0, 23.0)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Optical axis X (mm)")
    ax.set_ylabel("Cross-section span (mm)")
    ax.set_title("C12880MA holder side section: sensor package faces C-mount")
    ax.grid(True, linewidth=0.45, color="#d8dde1")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.95)
    fig.tight_layout()
    save_figure_outputs(fig, path_base)
    plt.close(fig)


def write_readme(
    path: Path,
    outputs: dict[str, str],
    validations: dict[str, object],
) -> None:
    geometry = board_geometry()
    pin_rows = "\n".join(
        f"| {pin['index']} | `{pin['y']}` | `{pin['z']}` | `3.0` |"
        for pin in geometry["six_pin_tail_reliefs_relative_to_sensor_axis_mm"]
    )
    output_rows = "\n".join(
        f"| {key} | `{value}` |" for key, value in outputs.items()
    )
    parameter_rows = "\n".join(
        f"| `{key}` | `{value}` |" for key, value in PARAMS.items()
    )
    path.write_text(
        f"""# C12880MA 42 x 42 C-Mount Module Holder - Mating Orientation

This is the fifth print-ready run for the measured C12880MA spectrometer module.
The C-mount axis is centered on the **sensor package**, not on the PCB. The PCB
is deliberately offset because the sensor sits `15.55 mm` from the left board
edge while the `38.3 mm` board center is `19.15 mm` from that edge.

The supplied sketch and photos are used only to interpret the measured values.
Their top view shows the sensor at the PCB top-left and the pin row below it.
Because that component face mates against the holder, the PCB short-direction
offset and pin-row Z coordinate are inverted in the holder cutouts. No new
module detail, connector housing, or extra holder feature is introduced.

## Use These Files

- Editable design orientation: `USE_THIS_{STEM}_assembly.step`
- Direct-print STEP: `PRINT_THIS_{STEM}.step`
- Direct-print STL: `PRINT_THIS_{STEM}.stl`
- Direct-print 3MF: `PRINT_THIS_{STEM}.3mf`
- Exact print preview: `PRINT_THIS_{STEM}_render.png`
- Partially exploded board/sensor fit preview: `{STEM}_assembly_render.png`

The print files place the 34 mm C-mount front face on the build plate and make
the optical axis vertical. The editable STEP keeps the optical axis along X.

## Alignment

- Structural plate: `42 x 42 x 5 mm`.
- Rear rim: `2 mm` added only outside a `38.7 x 23.2 mm` PCB pocket.
- Installed `1.5 mm` PCB is sunk `0.5 mm` below the surrounding rim.
- C-mount OD: `34 mm`.
- Module PCB: `38.3 x 22.8 x 1.5 mm`.
- Measured package fit envelope: `20.5 x 13 x 15 mm`.
- Printed package opening: `20.9 x 13.4 mm` with rounded corners.
- Measured mounting-hole spacing: `33.6 mm`.
- Left hole to sensor axis: `13.2 mm`.
- Right hole to sensor axis: `20.4 mm`.
- Two blind `1.6 mm` pilots are intended for tapping M2 x 0.4 in printed
  plastic. Measure the physical PCB hole diameter and choose screw heads before
  committing a production batch.

The plate and pocket center are shifted `+3.6 mm` along the PCB long direction. That makes
the two mounting holes symmetric at `-16.8/+16.8 mm` about the plate center,
while the optical axis remains at the measured sensor center.

## 6P Socket Pin-Tail Clearance

The connector housing is not used as the clearance datum. The six solder tails
that protrude from the PCB into the holder surface are cleared directly on the
PCB footprint. Six `3.0 mm` holes at `2.54 mm` pitch overlap and are joined by a
bridge cut, forming one continuous slot with no thin material left between pins.

| Pin | Y mm from sensor axis | Z mm from sensor axis | relief diameter mm |
| ---: | ---: | ---: | ---: |
{pin_rows}

The source top view has the row below the sensor at
Z=`{PARAMS['source_component_view_six_pin_row_center_z_mm']} mm`; the mating
holder relief is therefore at Z=`{PARAMS['six_pin_row_center_z_mm']} mm`.
Its refined Y center is `{PARAMS['six_pin_row_center_y_mm']} mm`, which gives
approximately `8.8 mm` from the left PCB edge to the first pin center and
`16.8 mm` from the last pin center to the right PCB edge. The connected `3.0 mm`
relief gives `1.0 mm` radial clearance around the `1.0 mm` reference pin.

## PCB Sink Construction

The PCB seating surface stays at X=`{plate_rear_x()} mm`, exactly as in run 1.
Instead of cutting 2 mm out of the 5 mm structural plate, this run adds a 2 mm
rim only outside the board footprint. The rim rear face is X=`{rim_rear_x()} mm`;
the installed PCB rear face is X=`{plate_rear_x() + PARAMS['pcb_thickness_x_mm']} mm`.
This leaves the PCB `0.5 mm` below the rim while preserving the sensor front at
X=`{plate_rear_x() - PARAMS['sensor_package_height_from_pcb_x_mm']} mm`, the
M2 pilot depth, the 6P pin-tail relief, and the 0.8 mm thread/package gap.

## C-Mount Thread

This printable receiver uses a `25.0 mm` pilot/root and a `25.4 mm` nominal
internal groove maximum, with the locally proven `0.8 mm` triangular pitch.
The female cutter extends a half pitch beyond both nominal ends before boolean
subtraction, so the thread reaches the end cleanly without external overflow.
The threaded section is only `5 mm` long. The measured 15 mm package begins
`0.8 mm` behind the nominal thread end, preventing the package from occupying
the active mating-thread region.

## Source Evidence

- User measurement sketch: `{repo_path(REFERENCE_DIR / 'user-measured-dimensions.jpg')}`
- Vendor board image: `{repo_path(REFERENCE_DIR / 'vendor-board-dimensions.jpg')}`
- User front photo: `{repo_path(REFERENCE_DIR / 'user-module-front-elevation-20260718.jpg')}`
- User top photo: `{repo_path(REFERENCE_DIR / 'user-module-top-view-20260718.jpg')}`
- Hamamatsu datasheet: `{repo_path(REFERENCE_DIR / 'hamamatsu-c12880ma-datasheet.pdf')}`
- Vendor archive snapshot: `{repo_path(REFERENCE_DIR)}`

The bundled vendor `CCD3D.stp` contains a much larger assembly and TCD1304
labels, so it is retained as reference evidence but is not used as the exact
38.3 x 22.8 module geometry.

## Regenerate

```bash
cad/.conda/cad-python/bin/python {repo_path(path.parent / Path(__file__).name)}
blender --background --python {repo_path(path.parent / 'render_run5_c12880ma_cmount_holder.py')}
```

## Validation

```json
{json.dumps(validations, indent=2)}
```

## Outputs

| Artifact | Path |
| --- | --- |
{output_rows}

## Parameters

| Parameter | Value |
| --- | --- |
{parameter_rows}
""",
        encoding="utf-8",
    )


def copy_files(paths: list[Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.exists():
            shutil.copy2(path, destination / path.name)


def sync_latest(paths: list[Path]) -> None:
    LATEST_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    copy_files(paths, LATEST_ARTIFACT_DIR)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    print_body_design = build_print_body(threaded=True)
    print_body = print_orientation(print_body_design)
    smooth_editable = build_print_body(threaded=False)
    socket = build_cmount_socket(threaded=True)
    plate = build_holder_plate()
    decoupled = build_decoupled_holder()
    board = build_board_proxy()
    package = build_sensor_package_proxy()
    pin_tails = build_pin_tail_proxy()
    assembly = build_assembly()
    thread_cutter = female_thread_cutter()

    print_step = RUN_DIR / f"PRINT_THIS_{STEM}.step"
    print_stl = RUN_DIR / f"PRINT_THIS_{STEM}.stl"
    print_3mf = RUN_DIR / f"PRINT_THIS_{STEM}.3mf"
    use_step = RUN_DIR / f"USE_THIS_{STEM}_assembly.step"
    design_step = ARTIFACT_DIR / f"{STEM}_design_orientation.step"
    design_stl = ARTIFACT_DIR / f"{STEM}_design_orientation.stl"
    smooth_step = ARTIFACT_DIR / f"{STEM}_smooth_editable.step"
    decoupled_step = ARTIFACT_DIR / f"{STEM}_decoupled_socket_and_plate.step"
    socket_step = ARTIFACT_DIR / f"{STEM}_cmount_socket.step"
    socket_stl = ARTIFACT_DIR / f"{STEM}_cmount_socket.stl"
    plate_step = ARTIFACT_DIR / f"{STEM}_holder_plate.step"
    plate_stl = ARTIFACT_DIR / f"{STEM}_holder_plate.stl"
    board_step = ARTIFACT_DIR / f"{STEM}_board_proxy.step"
    board_stl = ARTIFACT_DIR / f"{STEM}_board_proxy.stl"
    package_step = ARTIFACT_DIR / f"{STEM}_sensor_package_proxy.step"
    package_stl = ARTIFACT_DIR / f"{STEM}_sensor_package_proxy.stl"
    pins_step = ARTIFACT_DIR / f"{STEM}_six_pin_tail_proxy.step"
    pins_stl = ARTIFACT_DIR / f"{STEM}_six_pin_tail_proxy.stl"
    cutter_step = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.step"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly_with_proxies.step"
    alignment_base = ARTIFACT_DIR / f"{STEM}_holder_side_alignment"
    section_base = ARTIFACT_DIR / f"{STEM}_side_section"

    exporters.export(print_body, str(print_step))
    exporters.export(print_body, str(print_stl))
    export_stl_as_3mf(print_stl, print_3mf, title=STEM)
    exporters.export(print_body_design, str(use_step))
    exporters.export(print_body_design, str(design_step))
    exporters.export(print_body_design, str(design_stl))
    exporters.export(smooth_editable, str(smooth_step))
    exporters.export(decoupled, str(decoupled_step))
    exporters.export(socket, str(socket_step))
    exporters.export(socket, str(socket_stl))
    exporters.export(plate, str(plate_step))
    exporters.export(plate, str(plate_stl))
    exporters.export(board, str(board_step))
    exporters.export(board, str(board_stl))
    exporters.export(package, str(package_step))
    exporters.export(package, str(package_stl))
    exporters.export(pin_tails, str(pins_step))
    exporters.export(pin_tails, str(pins_stl))
    exporters.export(thread_cutter, str(cutter_step))
    assembly.save(str(assembly_step))

    draw_holder_side_alignment(alignment_base)
    draw_side_section(section_base)

    geometry_validation = geometry_checks()
    validations = {
        "geometry": geometry_validation,
        "print_step": validate_step(print_step),
        "print_stl": validate_stl(print_stl),
        "print_3mf": validate_3mf(print_3mf),
        "use_this_design_step": validate_step(use_step),
        "smooth_editable_step": validate_step(smooth_step),
        "decoupled_step": validate_step(decoupled_step),
        "assembly_with_proxies_step": validate_step(assembly_step),
    }
    required_checks = [
        geometry_validation["hole_spacing_is_33p6_mm"],
        geometry_validation["source_view_is_sensor_top_left_and_pin_row_below"],
        geometry_validation["holder_view_is_source_long_edge_flip"],
        geometry_validation["sensor_is_closer_to_left_edge"],
        geometry_validation["six_pin_y_adjustment_from_run1_is_only_0p4_mm"],
        math.isclose(geometry_validation["six_pin_first_center_from_left_edge_mm"], 8.8),
        math.isclose(geometry_validation["six_pin_last_center_from_right_edge_mm"], 16.8),
        math.isclose(geometry_validation["six_pin_radial_clearance_mm"], 1.0),
        geometry_validation["holes_are_symmetric_about_plate_center"],
        geometry_validation["pcb_fits_42x42_plate"],
        geometry_validation["socket_od_fits_plate"],
        geometry_validation["rectangular_package_clearance_fits_25mm_chamber"],
        geometry_validation["thread_does_not_reach_sensor_package"],
        geometry_validation["pcb_sink_is_exactly_0p5_mm_after_install"],
        geometry_validation["six_pin_relief_is_on_pcb_footprint"],
        validations["print_step"]["all_brep_valid"],
        validations["print_step"]["solid_count"] == 1,
        validations["print_stl"]["watertight"],
        validations["print_3mf"]["zip_valid"],
        validations["use_this_design_step"]["all_brep_valid"],
        validations["smooth_editable_step"]["all_brep_valid"],
        validations["decoupled_step"]["solid_count"] == 2,
    ]
    if not all(required_checks):
        raise RuntimeError(json.dumps(validations, indent=2))

    outputs = {
        "print_step": repo_path(print_step),
        "print_stl": repo_path(print_stl),
        "print_3mf": repo_path(print_3mf),
        "use_this_assembly_step": repo_path(use_step),
        "design_orientation_step": repo_path(design_step),
        "smooth_editable_step": repo_path(smooth_step),
        "decoupled_socket_and_plate_step": repo_path(decoupled_step),
        "cmount_socket_step": repo_path(socket_step),
        "holder_plate_step": repo_path(plate_step),
        "board_proxy_step": repo_path(board_step),
        "sensor_package_proxy_step": repo_path(package_step),
        "six_pin_tail_proxy_step": repo_path(pins_step),
        "female_thread_cutter_step": repo_path(cutter_step),
        "assembly_with_proxies_step": repo_path(assembly_step),
        "holder_side_alignment_png": repo_path(alignment_base.with_suffix(".png")),
        "holder_side_alignment_pdf": repo_path(alignment_base.with_suffix(".pdf")),
        "holder_side_alignment_svg": repo_path(alignment_base.with_suffix(".svg")),
        "side_section_png": repo_path(section_base.with_suffix(".png")),
        "side_section_pdf": repo_path(section_base.with_suffix(".pdf")),
        "side_section_svg": repo_path(section_base.with_suffix(".svg")),
        "print_render_png": repo_path(RUN_DIR / f"PRINT_THIS_{STEM}_render.png"),
        "assembly_render_png": repo_path(RUN_DIR / f"{STEM}_assembly_render.png"),
    }
    manifest = {
        "name": STEM,
        "run": RUN_DIR.name,
        "params": PARAMS,
        "derived_geometry": board_geometry(),
        "outputs": outputs,
        "validations": validations,
        "nutstore_sync": str(NUTSTORE_DIR),
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    outputs["manifest"] = repo_path(manifest_path)
    readme_path = RUN_DIR / "README.md"
    write_readme(readme_path, outputs, validations)

    latest_paths = [
        print_step,
        print_stl,
        print_3mf,
        use_step,
        design_step,
        design_stl,
        smooth_step,
        decoupled_step,
        socket_step,
        socket_stl,
        plate_step,
        plate_stl,
        board_step,
        board_stl,
        package_step,
        package_stl,
        pins_step,
        pins_stl,
        cutter_step,
        assembly_step,
        alignment_base.with_suffix(".png"),
        alignment_base.with_suffix(".pdf"),
        alignment_base.with_suffix(".svg"),
        section_base.with_suffix(".png"),
        section_base.with_suffix(".pdf"),
        section_base.with_suffix(".svg"),
        manifest_path,
        readme_path,
    ]
    sync_latest(latest_paths)
    shutil.copy2(use_step, DESIGN_DIR / f"USE_THIS_{DESIGN_DIR.name}.step")
    copy_files(
        [
            print_step,
            print_stl,
            print_3mf,
            use_step,
            smooth_step,
            socket_step,
            plate_step,
            assembly_step,
            alignment_base.with_suffix(".png"),
            section_base.with_suffix(".png"),
            manifest_path,
            readme_path,
        ],
        NUTSTORE_DIR,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
