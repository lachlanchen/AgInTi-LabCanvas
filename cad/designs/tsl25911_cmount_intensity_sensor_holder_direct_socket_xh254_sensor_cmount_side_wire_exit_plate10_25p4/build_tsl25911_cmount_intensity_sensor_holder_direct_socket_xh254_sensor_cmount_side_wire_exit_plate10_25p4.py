#!/usr/bin/env python3
"""Build a direct-socket 25.4 mm C-mount holder for a TSL25911 light sensor module."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_plate10_25p4"
REFERENCE_DIR = ROOT / "cad/references/waveshare-tsl25911-light-sensor"


PARAMS = {
    "name": STEM,
    "design_variant": "direct C-mount socket to TSL25911 sensor holder plate; 10 mm holder plate keeps margin behind the 8.75 mm net socket/PCB sink relief; standard 25.4 mm female C-mount bore/root; half-pitch thread runout cutter for fully developed end threads; TSL25911 package visualized on C-mount-facing PCB side; XH2.54 5P socket relief opens fully to holder edge for Dupont/male-header wire exit",
    "design_date": "2026-07-08",
    "units": "mm",
    "cmount_standard_note": "Industrial C-mount is 1-32 UNS, 25.4 mm major diameter and 0.79375 mm pitch; this high-precision-print variant uses 25.4 mm female bore/root while retaining the local 0.8 mm pitch tooth profile.",
    "openhi_female_root_diameter_mm": 25.4,
    "openhi_female_thread_cutter_crest_diameter_mm": 26.2,
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.4,
    "thread_tooth_base_mm": 0.8,
    "thread_runout_extra_cycles_each_end": 0.5,
    "thread_runout_extra_length_each_end_mm": 0.4,
    "female_socket_length_mm": 12.0,
    "female_thread_start_mm": 0.2,
    "female_thread_length_mm": 10.0,
    "socket_outer_diameter_mm": 34.0,
    "optical_bore_diameter_mm": 8.0,
    "omitted_middle_connector_length_mm": 0.0,
    "sensor_plate_thickness_mm": 10.0,
    "sensor_plate_width_y_mm": 50.0,
    "sensor_plate_height_z_mm": 36.0,
    "sensor_plate_center_z_mm": 0.0,
    "module_board_long_y_mm": 27.0,
    "module_board_short_z_mm": 20.0,
    "sensor_to_sensor_side_short_edge_y_mm": 7.5,
    "connector_side": "positive_y_edge_opposite_sensor_side",
    "component_side": "c_mount_facing_negative_x_side_of_board",
    "module_board_size_source": "User-corrected TSL25911 module geometry: PCB is 20 x 27 mm; TSL25911 sensing window is centered across the 20 mm short edge and 7.5 mm from the sensor-side short edge opposite the connector/socket edge. The TSL25911 package is on the C-mount-facing side of the PCB.",
    "board_pocket_clearance_total_mm": 1.0,
    "board_pocket_depth_mm": 2.25,
    "board_thickness_mm": 1.6,
    "tsl25911_package_width_y_mm": 3.0,
    "tsl25911_package_height_z_mm": 3.6,
    "tsl25911_package_thickness_x_mm": 1.0,
    "tsl25911_window_diameter_mm": 1.4,
    "mount_hole_diameter_mm": 2.0,
    "mount_hole_clearance_diameter_mm": 2.4,
    "mount_hole_y_from_sensor_side_edge_mm": 2.0,
    "mount_hole_z_from_board_edge_mm": 2.0,
    "xh254_5p_socket_width_z_mm": 14.0,
    "xh254_5p_socket_depth_y_mm": 6.0,
    "xh254_5p_socket_height_x_mm": 5.5,
    "xh254_socket_net_relief_height_from_pcb_sink_floor_x_mm": 6.5,
    "xh254_socket_clearance_total_mm": 1.0,
    "xh254_socket_relief_extra_y_mm": 1.0,
    "wire_exit_relief_to_holder_edge_mm": 0.6,
    "source_wiki": "https://www.waveshare.net/wiki/TSL25911_Light_Sensor",
    "source_product": "https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm",
    "source_github": "https://github.com/waveshare/TSL2591X-Light-Sensor",
}


THREAD_OVERLAP = 0.08


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def x_cylinder(diameter: float, length: float, x0: float) -> cq.Workplane:
    return cq.Workplane("YZ").workplane(offset=x0).circle(diameter / 2.0).extrude(length)


def x_box(center: tuple[float, float, float], size: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def x_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
    return cq.Workplane("XY").box(length, span, span, centered=(False, True, True)).translate((x0, 0, 0))


def fillet_if_possible(shape: cq.Workplane, selector: str, radius: float) -> cq.Workplane:
    try:
        return shape.edges(selector).fillet(radius)
    except Exception:
        return shape


def external_thread_brep(
    x0: float,
    length: float,
    root_d: float,
    lefthand: bool = False,
    extra_each_end: float = 0.0,
) -> cq.Workplane:
    sweep_x0 = x0 - extra_each_end
    sweep_length = length + 2.0 * extra_each_end
    root_r = root_d / 2.0 - THREAD_OVERLAP
    crest_d = root_d + 2.0 * PARAMS["thread_tooth_height_mm"]
    path = cq.Wire.makeHelix(
        PARAMS["thread_pitch_mm"],
        sweep_length,
        root_r,
        center=(sweep_x0, 0, 0),
        dir=(1, 0, 0),
        lefthand=lefthand,
    )
    profile = (
        cq.Workplane("XY")
        .center(sweep_x0, root_r)
        .polyline(
            [
                (0, 0),
                (PARAMS["thread_tooth_base_mm"] / 2.0, PARAMS["thread_tooth_height_mm"] + THREAD_OVERLAP),
                (PARAMS["thread_tooth_base_mm"], 0),
            ]
        )
        .close()
    )
    thread = profile.sweep(path, isFrenet=True, combine=False)
    return thread.intersect(x_clip_box(sweep_x0, sweep_length, crest_d + 4.0))


def total_length() -> float:
    return PARAMS["female_socket_length_mm"] + PARAMS["sensor_plate_thickness_mm"]


def cmount_socket_length() -> float:
    return PARAMS["female_socket_length_mm"]


def sensor_plate_x0() -> float:
    return cmount_socket_length()


def board_reference_geometry() -> dict[str, object]:
    board_w = PARAMS["module_board_long_y_mm"]
    board_h = PARAMS["module_board_short_z_mm"]
    sensor_edge = PARAMS["sensor_to_sensor_side_short_edge_y_mm"]
    bounds = {
        "y_min": round(-sensor_edge, 4),
        "y_max": round(board_w - sensor_edge, 4),
        "z_min": round(-board_h / 2.0, 4),
        "z_max": round(board_h / 2.0, 4),
    }
    board_center = {
        "y": round((bounds["y_min"] + bounds["y_max"]) / 2.0, 4),
        "z": 0.0,
    }
    hole_y = bounds["y_min"] + PARAMS["mount_hole_y_from_sensor_side_edge_mm"]
    hole_z = board_h / 2.0 - PARAMS["mount_hole_z_from_board_edge_mm"]
    mount_holes = [
        {
            "name": "M2_bottom",
            "y": round(hole_y, 4),
            "z": round(-hole_z, 4),
            "source_diameter_mm": PARAMS["mount_hole_diameter_mm"],
            "cut_diameter_mm": PARAMS["mount_hole_clearance_diameter_mm"],
        },
        {
            "name": "M2_top",
            "y": round(hole_y, 4),
            "z": round(hole_z, 4),
            "source_diameter_mm": PARAMS["mount_hole_diameter_mm"],
            "cut_diameter_mm": PARAMS["mount_hole_clearance_diameter_mm"],
        },
    ]
    socket_clearance = PARAMS["xh254_socket_clearance_total_mm"] / 2.0
    socket_depth = PARAMS["xh254_5p_socket_depth_y_mm"]
    socket_half_z = PARAMS["xh254_5p_socket_width_z_mm"] / 2.0
    socket = {
        "name": "XH2.54_5P_socket_relief",
        "assumed_side": PARAMS["connector_side"],
        "y_min": round(bounds["y_max"] - socket_depth - socket_clearance, 4),
        "y_max": round(bounds["y_max"] + PARAMS["xh254_socket_relief_extra_y_mm"] + socket_clearance, 4),
        "z_min": round(-socket_half_z - socket_clearance, 4),
        "z_max": round(socket_half_z + socket_clearance, 4),
        "height_x_mm": PARAMS["xh254_5p_socket_height_x_mm"],
        "net_relief_height_from_pcb_sink_floor_x_mm": PARAMS["xh254_socket_net_relief_height_from_pcb_sink_floor_x_mm"],
        "total_relief_depth_from_holder_rear_x_mm": round(xh254_socket_total_relief_depth_x(), 4),
        "nominal_body_mm": {
            "parallel_to_short_edge_z": PARAMS["xh254_5p_socket_width_z_mm"],
            "height_x": PARAMS["xh254_5p_socket_height_x_mm"],
            "parallel_to_long_edge_y": PARAMS["xh254_5p_socket_depth_y_mm"],
        },
    }
    wire_exit = {
        "name": "Dupont_or_male_header_wire_exit_relief",
        "y_min": socket["y_min"],
        "y_max": round(PARAMS["sensor_plate_width_y_mm"] / 2.0 + PARAMS["wire_exit_relief_to_holder_edge_mm"], 4),
        "z_min": socket["z_min"],
        "z_max": socket["z_max"],
        "net_relief_height_from_pcb_sink_floor_x_mm": PARAMS["xh254_socket_net_relief_height_from_pcb_sink_floor_x_mm"],
        "total_relief_depth_from_holder_rear_x_mm": round(xh254_socket_total_relief_depth_x(), 4),
        "note": "This relief extends the socket cutout to the positive-Y holder edge, leaving the XH2.54/Dupont wire side fully open.",
    }
    return {
        "board_center_relative_to_sensor_mm": board_center,
        "board_bounds_relative_to_sensor_mm": bounds,
        "mounting_holes_relative_to_sensor_mm": mount_holes,
        "xh254_socket_relative_to_sensor_mm": socket,
        "wire_exit_relative_to_sensor_mm": wire_exit,
        "notes": [
            PARAMS["module_board_size_source"],
            "Coordinate convention: Y is the 27 mm long direction between the two short edges; Z is the 20 mm short-edge direction. Sensor datum is on the optical axis at Y=0, Z=0. The connector/socket side is positive Y unless a caliper check says otherwise. The component side is negative X, facing the C-mount receiver.",
        ],
    }


def female_thread_cutter() -> cq.Workplane:
    return external_thread_brep(
        PARAMS["female_thread_start_mm"],
        PARAMS["female_thread_length_mm"],
        PARAMS["openhi_female_root_diameter_mm"],
        lefthand=True,
        extra_each_end=PARAMS["thread_runout_extra_length_each_end_mm"],
    )


def female_bore_cutter() -> cq.Workplane:
    return x_cylinder(
        PARAMS["openhi_female_root_diameter_mm"],
        PARAMS["female_socket_length_mm"],
        0.0,
    )


def xh254_socket_total_relief_depth_x() -> float:
    return PARAMS["board_pocket_depth_mm"] + PARAMS["xh254_socket_net_relief_height_from_pcb_sink_floor_x_mm"]


def board_pocket_cutter() -> cq.Workplane:
    ref = board_reference_geometry()
    center = ref["board_center_relative_to_sensor_mm"]  # type: ignore[index]
    pocket_w = PARAMS["module_board_long_y_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    pocket_h = PARAMS["module_board_short_z_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    depth = PARAMS["board_pocket_depth_mm"]
    return x_box(
        (total_length() - depth / 2.0 + 0.05, center["y"], center["z"]),
        (depth + 0.2, pocket_w, pocket_h),
    )


def board_proxy_cmount_face_x() -> float:
    return total_length() + 0.05


def board_proxy_rear_face_x() -> float:
    return board_proxy_cmount_face_x() + PARAMS["board_thickness_mm"]


def sensor_package_center_x() -> float:
    return board_proxy_cmount_face_x() - PARAMS["tsl25911_package_thickness_x_mm"] / 2.0


def xh254_socket_relief_cutter() -> cq.Workplane:
    ref = board_reference_geometry()
    exit_relief = ref["wire_exit_relative_to_sensor_mm"]  # type: ignore[index]
    width_y = exit_relief["y_max"] - exit_relief["y_min"]
    height_z = exit_relief["z_max"] - exit_relief["z_min"]
    center_y = (exit_relief["y_min"] + exit_relief["y_max"]) / 2.0
    center_z = (exit_relief["z_min"] + exit_relief["z_max"]) / 2.0
    relief_depth_x = xh254_socket_total_relief_depth_x()
    return x_box(
        (total_length() - relief_depth_x / 2.0 + 0.05, center_y, center_z),
        (relief_depth_x + 0.2, width_y, height_z),
    )


def xh254_socket_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    socket = ref["xh254_socket_relative_to_sensor_mm"]  # type: ignore[index]
    center_y = (socket["y_min"] + socket["y_max"]) / 2.0
    center_z = (socket["z_min"] + socket["z_max"]) / 2.0
    return x_box(
        (
            total_length() + PARAMS["board_thickness_mm"] + PARAMS["xh254_5p_socket_height_x_mm"] / 2.0,
            center_y,
            center_z,
        ),
        (
            PARAMS["xh254_5p_socket_height_x_mm"],
            PARAMS["xh254_5p_socket_depth_y_mm"],
            PARAMS["xh254_5p_socket_width_z_mm"],
        ),
    )


def wire_exit_clearance_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    exit_relief = ref["wire_exit_relative_to_sensor_mm"]  # type: ignore[index]
    center_y = (exit_relief["y_min"] + exit_relief["y_max"]) / 2.0
    center_z = (exit_relief["z_min"] + exit_relief["z_max"]) / 2.0
    return x_box(
        (
            total_length() + PARAMS["board_thickness_mm"] + PARAMS["xh254_5p_socket_height_x_mm"] / 2.0,
            center_y,
            center_z,
        ),
        (
            PARAMS["xh254_5p_socket_height_x_mm"],
            exit_relief["y_max"] - exit_relief["y_min"],
            exit_relief["z_max"] - exit_relief["z_min"],
        ),
    )


def mount_hole_cutter(y: float, z: float) -> cq.Workplane:
    x0 = sensor_plate_x0() - 1.0
    return x_cylinder(PARAMS["mount_hole_clearance_diameter_mm"], PARAMS["sensor_plate_thickness_mm"] + 2.5, x0).translate((0, y, z))


def build_cmount_socket_body() -> cq.Workplane:
    socket = x_cylinder(PARAMS["socket_outer_diameter_mm"], PARAMS["female_socket_length_mm"], 0.0)
    body = socket
    body = fillet_if_possible(body, "|X", 0.55)
    body = body.cut(female_bore_cutter()).cut(female_thread_cutter())
    body = body.cut(x_cylinder(PARAMS["optical_bore_diameter_mm"], cmount_socket_length() + 0.2, -0.1))
    return body.clean()


def build_sensor_plate_body() -> cq.Workplane:
    plate_x0 = sensor_plate_x0()
    plate = x_box(
        (plate_x0 + PARAMS["sensor_plate_thickness_mm"] / 2.0, 0.0, PARAMS["sensor_plate_center_z_mm"]),
        (
            PARAMS["sensor_plate_thickness_mm"],
            PARAMS["sensor_plate_width_y_mm"],
            PARAMS["sensor_plate_height_z_mm"],
        ),
    )
    holder = fillet_if_possible(plate, "|X", 0.8)
    holder = holder.cut(
        x_cylinder(
            PARAMS["optical_bore_diameter_mm"],
            PARAMS["sensor_plate_thickness_mm"] + 1.2,
            sensor_plate_x0() - 0.6,
        )
    )
    holder = holder.cut(board_pocket_cutter()).cut(xh254_socket_relief_cutter())
    ref = board_reference_geometry()
    for hole in ref["mounting_holes_relative_to_sensor_mm"]:  # type: ignore[index]
        holder = holder.cut(mount_hole_cutter(hole["y"], hole["z"]))
    return holder.clean()


def build_holder_compound() -> cq.Compound:
    return cq.Compound.makeCompound([build_cmount_socket_body().val(), build_sensor_plate_body().val()])


def build_board_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    center = ref["board_center_relative_to_sensor_mm"]  # type: ignore[index]
    return x_box(
        (
            board_proxy_cmount_face_x() + PARAMS["board_thickness_mm"] / 2.0,
            center["y"],
            center["z"],
        ),
        (
            PARAMS["board_thickness_mm"],
            PARAMS["module_board_long_y_mm"],
            PARAMS["module_board_short_z_mm"],
        ),
    )


def build_sensor_proxy() -> cq.Workplane:
    package = x_box(
        (
            sensor_package_center_x(),
            0.0,
            0.0,
        ),
        (
            PARAMS["tsl25911_package_thickness_x_mm"],
            PARAMS["tsl25911_package_width_y_mm"],
            PARAMS["tsl25911_package_height_z_mm"],
        ),
    )
    window = x_cylinder(
        PARAMS["tsl25911_window_diameter_mm"],
        1.2,
        sensor_package_center_x() - PARAMS["tsl25911_package_thickness_x_mm"] / 2.0 - 0.1,
    )
    return package.union(window)


def build_axis_proxy() -> cq.Workplane:
    return x_cylinder(1.0, total_length() + 9.0, -4.0)


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_cmount_socket_body(), name="independent_standard_25p4_threaded_cmount_socket", color=cq.Color(0.10, 0.10, 0.09, 1.0))
    assembly.add(build_sensor_plate_body(), name="independent_tsl25911_sensor_plate_holder", color=cq.Color(0.18, 0.18, 0.16, 1.0))
    assembly.add(build_board_proxy(), name="tsl25911_20x27_module_board_proxy_sensor_7p5mm_from_sensor_edge", color=cq.Color(0.0, 0.23, 0.48, 0.70))
    assembly.add(build_sensor_proxy(), name="tsl25911_window_on_cmount_facing_side_centered_on_optical_axis", color=cq.Color(0.95, 0.78, 0.20, 1.0))
    assembly.add(wire_exit_clearance_proxy(), name="full_edge_open_wire_exit_clearance_proxy", color=cq.Color(1.0, 0.58, 0.22, 0.35))
    assembly.add(xh254_socket_proxy(), name="xh2p54_5p_socket_clearance_proxy_positive_y", color=cq.Color(0.95, 0.92, 0.82, 0.65))
    assembly.add(female_thread_cutter(), name="female_thread_boolean_cutter", color=cq.Color(0.9, 0.2, 0.1, 0.35))
    assembly.add(build_axis_proxy(), name="optical_axis_proxy", color=cq.Color(1.0, 0.72, 0.08, 0.6))
    return assembly


def write_alignment_svg(path: Path) -> None:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_sensor_mm"]  # type: ignore[index]
    socket = ref["xh254_socket_relative_to_sensor_mm"]  # type: ignore[index]
    wire_exit = ref["wire_exit_relative_to_sensor_mm"]  # type: ignore[index]
    scale = 9.0
    pad = 58.0
    legend_w = 600.0
    view_w = PARAMS["sensor_plate_width_y_mm"]
    view_h = PARAMS["sensor_plate_height_z_mm"]
    svg_w = int(view_w * scale + pad * 2 + legend_w)
    svg_h = int(view_h * scale + pad * 2)

    def sx(y: float) -> float:
        return pad + (y + view_w / 2.0) * scale

    def sy(z: float) -> float:
        top = view_h / 2.0
        return pad + (top - z) * scale

    def circle(y: float, z: float, diameter: float, fill: str, stroke: str, label: str = "") -> str:
        text = ""
        if label:
            text = f'<text x="{sx(y)+8:.2f}" y="{sy(z)-8:.2f}" font-family="Arial" font-size="12" fill="#1a202c">{label}</text>'
        return f'<circle cx="{sx(y):.2f}" cy="{sy(z):.2f}" r="{diameter/2*scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>{text}'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-view_w/2):.2f}" y="{sy(view_h/2):.2f}" width="{view_w*scale:.2f}" height="{view_h*scale:.2f}" rx="8" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        f'<rect x="{sx(bounds["y_min"]):.2f}" y="{sy(bounds["z_max"]):.2f}" width="{(bounds["y_max"]-bounds["y_min"])*scale:.2f}" height="{(bounds["z_max"]-bounds["z_min"])*scale:.2f}" fill="#e6f0ff" stroke="#2b6cb0" stroke-width="2" stroke-dasharray="8 5"/>',
        f'<rect x="{sx(wire_exit["y_min"]):.2f}" y="{sy(wire_exit["z_max"]):.2f}" width="{(wire_exit["y_max"]-wire_exit["y_min"])*scale:.2f}" height="{(wire_exit["z_max"]-wire_exit["z_min"])*scale:.2f}" fill="#fff4e6" stroke="#dd6b20" stroke-width="2" stroke-dasharray="7 4"/>',
        f'<rect x="{sx(socket["y_min"]):.2f}" y="{sy(socket["z_max"]):.2f}" width="{(socket["y_max"]-socket["y_min"])*scale:.2f}" height="{(socket["z_max"]-socket["z_min"])*scale:.2f}" fill="#fff5f5" stroke="#c53030" stroke-width="2" stroke-dasharray="5 4"/>',
        f'<line x1="{sx(-view_w/2):.2f}" y1="{sy(0):.2f}" x2="{sx(view_w/2):.2f}" y2="{sy(0):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        f'<line x1="{sx(0):.2f}" y1="{sy(view_h/2):.2f}" x2="{sx(0):.2f}" y2="{sy(-view_h/2):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        circle(0.0, 0.0, PARAMS["optical_bore_diameter_mm"], "#fff7d6", "#d69e2e", "optical axis / TSL25911"),
        f'<rect x="{sx(-PARAMS["tsl25911_package_width_y_mm"]/2):.2f}" y="{sy(PARAMS["tsl25911_package_height_z_mm"]/2):.2f}" width="{PARAMS["tsl25911_package_width_y_mm"]*scale:.2f}" height="{PARAMS["tsl25911_package_height_z_mm"]*scale:.2f}" fill="#c69214" stroke="#1a202c" stroke-width="1.5"/>',
    ]
    for hole in ref["mounting_holes_relative_to_sensor_mm"]:  # type: ignore[index]
        lines.append(circle(hole["y"], hole["z"], hole["cut_diameter_mm"], "#edf2f7", "#4a5568", hole["name"]))

    legend_x = pad + view_w * scale + 36.0
    legend = [
        "TSL25911 C-mount intensity sensor holder",
        "View: rear tray, looking along optical axis",
        "Gold rectangle: TSL25911 package/window centered on axis",
        "Blue dashed rectangle: 20 x 27 mm module tray",
        "Gray holes: two M2 holes from the sensor-side short edge",
        "Red dashed slot: XH2.54 5P socket body clearance on connector edge",
        "Orange slot: same connector zone opened fully to holder edge for wires",
        f"Socket X-depth: {PARAMS['board_pocket_depth_mm']} mm PCB sink + {PARAMS['xh254_socket_net_relief_height_from_pcb_sink_floor_x_mm']} mm net = {xh254_socket_total_relief_depth_x()} mm",
        "C-mount side: standard 25.4 mm female receiver, 0.8 mm pitch printed thread",
    ]
    for index, text in enumerate(legend):
        size = 17 if index == 0 else 13
        weight = "700" if index == 0 else "400"
        lines.append(
            f'<text x="{legend_x:.2f}" y="{pad + index*25:.2f}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{text}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_svg(svg_path: Path) -> None:
    try:
        import cairosvg

        cairosvg.svg2png(url=str(svg_path), write_to=str(svg_path.with_suffix(".png")), output_width=1800)
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(svg_path.with_suffix(".pdf")))
        return
    except Exception:
        pass
    python = shutil.which("python")
    if python:
        script = (
            "import cairosvg, sys; "
            "cairosvg.svg2png(url=sys.argv[1], write_to=sys.argv[2], output_width=1800); "
            "cairosvg.svg2pdf(url=sys.argv[1], write_to=sys.argv[3])"
        )
        result = subprocess.run(
            [python, "-c", script, str(svg_path), str(svg_path.with_suffix(".png")), str(svg_path.with_suffix(".pdf"))],
            check=False,
        )
        if result.returncode == 0:
            return
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run([rsvg, "-f", "png", "-o", str(svg_path.with_suffix(".png")), str(svg_path)], check=False)
        subprocess.run([rsvg, "-f", "pdf", "-o", str(svg_path.with_suffix(".pdf")), str(svg_path)], check=False)
        return
    convert = shutil.which("convert")
    if convert:
        subprocess.run([convert, str(svg_path), str(svg_path.with_suffix(".png"))], check=False)


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    ref = board_reference_geometry()
    mount_rows = "\n".join(
        f"| {hole['name']} | `{hole['y']}` | `{hole['z']}` | `{hole['cut_diameter_mm']}` |"
        for hole in ref["mounting_holes_relative_to_sensor_mm"]  # type: ignore[index]
    )
    socket = ref["xh254_socket_relative_to_sensor_mm"]  # type: ignore[index]
    wire_exit = ref["wire_exit_relative_to_sensor_mm"]  # type: ignore[index]
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    params_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# TSL25911 C-Mount Intensity Sensor Holder Direct Socket XH2.54 Wire Exit

New independent CAD design for holding a Waveshare-style TSL25911 light sensor
module behind a standard-size `25.4 mm` C-mount receiver. This version follows the
clean direct-socket lesson from the AS7343 holder: no rectangular bridge/cube
and no middle cylinder. It also fixes the previous visualization mistake by
placing the TSL25911 package on the C-mount-facing side of the PCB.
The left C-mount socket directly touches the rear sensor plate at
x=`{sensor_plate_x0()}`. The C-mount socket and sensor plate are exported as
adjacent independent bodies so Shapr3D can select and edit them separately.
Older CAD designs are not modified.

## Source References

- Local reference snapshot: `{repo_path(REFERENCE_DIR)}`
- Waveshare wiki: `{PARAMS['source_wiki']}`
- Waveshare product page: `{PARAMS['source_product']}`
- Waveshare example code: `{PARAMS['source_github']}`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The physical tray follows the corrected geometry from the latest module check:
the board is `20 x 27 mm`; the TSL25911 sensing window is centered across the
`20 mm` short side and is `7.5 mm` from the sensor-side short edge, opposite the
connector/socket edge. The connector edge stays the same; only the component
side visualization is flipped so the sensor package faces the C-mount.

## Design Intent

- Put the TSL25911 sensing package on the C-mount optical axis.
- Use a standard/high-precision-printer C-mount receiver size:
  `{PARAMS['openhi_female_root_diameter_mm']} mm` female bore/root,
  `{PARAMS['openhi_female_thread_cutter_crest_diameter_mm']} mm` internal
  thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Keep the female thread cutter fully inside the `12 mm` C-mount socket:
  x=`{PARAMS['female_thread_start_mm']}` to
  x=`{PARAMS['female_thread_start_mm'] + PARAMS['female_thread_length_mm']}`.
- Generate the female thread cutter with an extra
  `{PARAMS['thread_runout_extra_length_each_end_mm']} mm` half-pitch runout
  beyond each nominal end before subtraction, so the internal thread reaches
  the socket end faces more completely without changing pitch or tooth shape.
- Export the C-mount socket and sensor plate as separate adjacent solids; they
  touch at x=`{sensor_plate_x0()}` without a bridge cube, middle cylinder, or
  boolean union.
- Provide a rear module tray for the `20 x 27 mm` board.
- Add an XH2.54-style 5-pin socket relief, nominal body
  `14 mm` along Z x `6 mm` along Y x `5.5 mm` high along X, on the connector
  edge.
- Cut the socket relief as a net clearance measured from the PCB sink floor:
  `{PARAMS['xh254_socket_net_relief_height_from_pcb_sink_floor_x_mm']} mm`
  beyond the `{PARAMS['board_pocket_depth_mm']} mm` PCB sink, for
  `{xh254_socket_total_relief_depth_x()} mm` total depth from the holder rear
  surface.
- This plate-10 variant uses a `{PARAMS['sensor_plate_thickness_mm']} mm`
  holder plate, leaving about
  `{PARAMS['sensor_plate_thickness_mm'] - xh254_socket_total_relief_depth_x():.2f} mm`
  of material behind the deepest socket/PCB relief.
- Extend the connector relief to the positive-Y holder edge so a Dupont jumper,
  matching male header, or cable can exit without hitting the printed wall.
- Add two M2 clearance holes matching the published board-hole pattern.

## C-Mount Size

This high-precision-printer variant uses a `25.4 mm` female root/bore rather
than the older `24.8 mm` OpenHI print-fit receiver. Standard C-mount is
`1-32 UNS` with `25.4 mm` major diameter and `0.79375 mm` pitch. The modeled
thread still uses the local proven triangular `0.8 mm` pitch, `0.4 mm` tooth
height, and `0.8 mm` tooth base unless a real tap/chase workflow replaces it.

Thread runout rule used here:

- Female/internal thread by subtraction: generate the cutter with an extra
  half pitch beyond each end, then subtract it from the socket. No extra trim is
  needed because only the intersection with the socket body remains.
- Male/external thread: generate the thread with an extra half pitch beyond the
  nominal end, then cut/trim the final solid back to the mount end face so the
  thread is complete but does not overflow.

## Geometry Used

Board center relative to the TSL25911 package:

```json
{json.dumps(ref['board_center_relative_to_sensor_mm'], indent=2)}
```

Board bounds relative to the TSL25911 sensing window:

```json
{json.dumps(ref['board_bounds_relative_to_sensor_mm'], indent=2)}
```

XH2.54 5P socket relief:

```json
{json.dumps(socket, indent=2)}
```

Wire/header exit relief:

```json
{json.dumps(wire_exit, indent=2)}
```

M2 mounting holes:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
{mount_rows}

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Parameter | Value |
| --- | --- |
{params_rows}

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_plate10_25p4/build_tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_plate10_25p4.py
blender --background --python cad/designs/tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_plate10_25p4/render_tsl25911_cmount_intensity_sensor_holder_direct_socket_xh254_sensor_cmount_side_wire_exit_plate10_25p4.py
```
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cmount_socket = build_cmount_socket_body()
    sensor_plate = build_sensor_plate_body()
    holder_compound = build_holder_compound()
    assembly = build_assembly()
    cutter = female_thread_cutter()
    board = build_board_proxy()

    holder_step = ARTIFACT_DIR / f"{STEM}_multibody_holder.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}_multibody_holder.stl"
    cmount_socket_step = ARTIFACT_DIR / f"{STEM}_cmount_socket.step"
    cmount_socket_stl = ARTIFACT_DIR / f"{STEM}_cmount_socket.stl"
    sensor_plate_step = ARTIFACT_DIR / f"{STEM}_sensor_plate.step"
    sensor_plate_stl = ARTIFACT_DIR / f"{STEM}_sensor_plate.stl"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    cutter_step = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.step"
    cutter_stl = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.stl"
    board_proxy_step = ARTIFACT_DIR / f"{STEM}_board_proxy.step"
    board_proxy_stl = ARTIFACT_DIR / f"{STEM}_board_proxy.stl"
    alignment_svg = ARTIFACT_DIR / f"{STEM}_rear_alignment.svg"
    manifest_path = ARTIFACT_DIR / "manifest.json"

    exporters.export(holder_compound, str(holder_step))
    exporters.export(holder_compound, str(holder_stl))
    exporters.export(cmount_socket, str(cmount_socket_step))
    exporters.export(cmount_socket, str(cmount_socket_stl))
    exporters.export(sensor_plate, str(sensor_plate_step))
    exporters.export(sensor_plate, str(sensor_plate_stl))
    exporters.export(cutter, str(cutter_step))
    exporters.export(cutter, str(cutter_stl))
    exporters.export(board, str(board_proxy_step))
    exporters.export(board, str(board_proxy_stl))
    assembly.save(str(assembly_step))
    assembly.save(str(assembly_stl))
    write_alignment_svg(alignment_svg)
    convert_svg(alignment_svg)

    outputs = {
        "multibody_holder_step": repo_path(holder_step),
        "multibody_holder_stl": repo_path(holder_stl),
        "cmount_socket_step": repo_path(cmount_socket_step),
        "cmount_socket_stl": repo_path(cmount_socket_stl),
        "sensor_plate_step": repo_path(sensor_plate_step),
        "sensor_plate_stl": repo_path(sensor_plate_stl),
        "assembly_step": repo_path(assembly_step),
        "assembly_stl": repo_path(assembly_stl),
        "thread_cutter_step": repo_path(cutter_step),
        "thread_cutter_stl": repo_path(cutter_stl),
        "board_proxy_step": repo_path(board_proxy_step),
        "board_proxy_stl": repo_path(board_proxy_stl),
        "rear_alignment_svg": repo_path(alignment_svg),
        "rear_alignment_png": repo_path(alignment_svg.with_suffix(".png")),
        "rear_alignment_pdf": repo_path(alignment_svg.with_suffix(".pdf")),
        "render_png": repo_path(ARTIFACT_DIR / f"{STEM}_render.png"),
        "rear_alignment_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_rear_alignment_render.png"),
        "blend": repo_path(ARTIFACT_DIR / f"{STEM}.blend"),
    }
    manifest = {
        "name": STEM,
        "params": PARAMS,
        "reference_geometry": board_reference_geometry(),
        "outputs": outputs,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(DESIGN_DIR / "README.md", outputs | {"manifest": repo_path(manifest_path)})


if __name__ == "__main__":
    main()
