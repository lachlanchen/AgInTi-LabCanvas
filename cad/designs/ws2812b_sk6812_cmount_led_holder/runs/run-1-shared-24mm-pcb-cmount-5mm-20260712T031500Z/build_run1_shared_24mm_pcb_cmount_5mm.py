#!/usr/bin/env python3
"""Build a shared C-mount holder for the WS2812B and SK6812 24 mm LED PCBs."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import cadquery as cq
from cadquery import exporters
from OCP.BRepCheck import BRepCheck_Analyzer
import trimesh


ROOT = Path(__file__).resolve().parents[5]
RUN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = RUN_DIR / "artifacts"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "ws2812b_sk6812_cmount_led_holder"
    / RUN_DIR.name
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


STEM = "ws2812b_sk6812_cmount_led_holder_run1"
WS2812B_PCB = ROOT / "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb"
SK6812_PCB = ROOT / "pcb/sk6812rgbw-5050-rgbw-led/sk6812rgbw-5050-rgbw-led.kicad_pcb"

PARAMS = {
    "name": STEM,
    "units": "mm",
    "source_boards": [
        "pcb/ws2812b-5050-rgb-led/ws2812b-5050-rgb-led.kicad_pcb",
        "pcb/sk6812rgbw-5050-rgbw-led/sk6812rgbw-5050-rgbw-led.kicad_pcb",
    ],
    "shared_layout_note": "WS2812B and SK6812 boards have the same 24 mm round carrier outline, same 12 x 12 mm mounting holes, same side 1x02 headers, and same backside C_0603 decoupling capacitor footprint.",
    "board_outer_diameter_mm": 24.0,
    "board_sink_diameter_mm": 24.4,
    "board_thickness_mm": 1.6,
    "board_sink_depth_mm": 1.7,
    "holder_plate_width_y_mm": 42.0,
    "holder_plate_height_z_mm": 42.0,
    "holder_plate_thickness_x_mm": 5.0,
    "holder_edge_fillet_mm": 0.8,
    "pcb_fixation_pilot_diameter_mm": 1.8,
    "pcb_fixation_note": "Four 1.8 mm pilot holes for small self-tapping screws in printed plastic.",
    "pin_header_relief_diameter_mm": 3.0,
    "pin_header_relief_note": "Each 1x02 side header gets two overlapping 3.0 mm clearance holes plus a bridge so the material between pins is fully removed.",
    "pin_header_head_relief_extra_y_mm": 1.6,
    "pin_header_head_relief_extra_z_mm": 1.0,
    "led_aperture_diameter_mm": 10.0,
    "cmount_socket_length_mm": 5.0,
    "cmount_thread_length_mm": 5.0,
    "cmount_outer_diameter_mm": 34.0,
    "cmount_female_pilot_root_diameter_mm": 25.0,
    "cmount_female_thread_cutter_crest_diameter_mm": 25.4,
    "cmount_standard_note": "C-mount nominal major diameter is 25.4 mm and pitch is 1/32 inch = 0.79375 mm. This printable proxy uses a 25.0 mm pilot/root and a 25.4 mm cutter maximum with local 0.8 mm pitch.",
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.2,
    "thread_tooth_base_mm": 0.8,
    "thread_runout_extra_cycles_each_end": 0.5,
    "thread_runout_extra_length_each_end_mm": 0.4,
    "thread_boolean_note": "Female cutter is swept half-pitch beyond both ends, then subtracted from the 5 mm socket so the thread reaches both faces without leaving overflow. Socket and holder plate remain independent adjacent bodies.",
    "optical_bore_diameter_mm": 10.0,
    "independent_body_contact_plane_x_mm": 5.0,
    "print_orientation": "C-mount axis is X. Print/check in the supplied orientation; if support is undesirable, split socket/plate or rotate in slicer after inspecting the render.",
}


THREAD_OVERLAP = 0.02


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


def _footprint_blocks(text: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"\n\s*\(footprint\s+", text)]
    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else text.find("\n\t(gr_", start)
        if end < 0:
            end = len(text)
        blocks.append(text[start:end])
    return blocks


def _first_at(block: str) -> tuple[float, float, float]:
    match = re.search(r"\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+([-0-9.]+))?", block)
    if not match:
        raise ValueError("footprint has no (at x y) record")
    return float(match.group(1)), float(match.group(2)), float(match.group(3) or 0.0)


def _rotate(x: float, y: float, degrees: float) -> tuple[float, float]:
    rad = math.radians(degrees)
    return x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad)


def extract_led_board_geometry(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    edge = re.search(
        r'\(gr_circle\s+\(center\s+([-0-9.]+)\s+([-0-9.]+)\)\s+\(end\s+([-0-9.]+)\s+([-0-9.]+)\).*?\(layer\s+"Edge.Cuts"\)',
        text,
        re.S,
    )
    if not edge:
        raise ValueError(f"could not find circular board edge in {path}")
    cx, cy, ex, ey = (float(edge.group(i)) for i in range(1, 5))
    radius = math.hypot(ex - cx, ey - cy)

    mounting_holes: list[dict[str, float | str]] = []
    header_pads: list[dict[str, float | str]] = []
    header_bodies: dict[str, dict[str, float | str]] = {}
    capacitor = {"y": 0.0, "z": -3.7, "footprint": "Custom:C_0603", "note": "fallback"}
    led = {"y": 0.0, "z": 0.0, "footprint": "5050 LED", "body_size_mm": [5.0, 5.0]}

    for block in _footprint_blocks(text):
        if "MountingHole:MountingHole_2.2mm_M2" in block:
            x, y, _ = _first_at(block)
            mounting_holes.append(
                {
                    "y": round(x - cx, 4),
                    "z": round(y - cy, 4),
                    "source_drill_mm": 2.2,
                    "holder_pilot_mm": PARAMS["pcb_fixation_pilot_diameter_mm"],
                }
            )
        elif "PinHeader_1x02_P2.54mm_Vertical" in block:
            fx, fy, rotation = _first_at(block)
            ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
            ref = ref_match.group(1) if ref_match else "J?"
            body_y = fx - cx
            body_z = fy + 1.27 - cy
            header_bodies[ref] = {
                "reference": ref,
                "center_y": round(body_y, 4),
                "center_z": round(body_z, 4),
                "fab_width_y_mm": 2.54,
                "fab_height_z_mm": 5.08,
                "relief_width_y_mm": round(2.54 + PARAMS["pin_header_head_relief_extra_y_mm"], 4),
                "relief_height_z_mm": round(5.08 + PARAMS["pin_header_head_relief_extra_z_mm"], 4),
            }
            for pad in re.finditer(
                r'\(pad\s+"([^"]+)"\s+thru_hole\s+\w+\s+\(at\s+([-0-9.]+)\s+([-0-9.]+)',
                block,
            ):
                local_x, local_y = float(pad.group(2)), float(pad.group(3))
                rx, ry = _rotate(local_x, local_y, rotation)
                header_pads.append(
                    {
                        "reference": ref,
                        "pad": pad.group(1),
                        "y": round(fx + rx - cx, 4),
                        "z": round(fy + ry - cy, 4),
                        "source_drill_mm": 1.0,
                        "holder_clearance_mm": PARAMS["pin_header_relief_diameter_mm"],
                    }
                )
        elif 'Custom:C_0603' in block:
            x, y, _ = _first_at(block)
            capacitor = {
                "y": round(x - cx, 4),
                "z": round(y - cy, 4),
                "footprint": "Custom:C_0603",
                "body_size_mm": [1.6, 0.8],
                "courtyard_mm": [3.1, 1.5],
            }
        elif "WS2812B_5050_PLCC4" in block or "SK6812RGBW_5050_PLCC4" in block:
            x, y, _ = _first_at(block)
            led = {
                "y": round(x - cx, 4),
                "z": round(y - cy, 4),
                "footprint": "5050 PLCC4 LED",
                "body_size_mm": [5.0, 5.0],
            }

    mounting_holes.sort(key=lambda h: (h["z"], h["y"]))  # type: ignore[index]
    header_pads.sort(key=lambda h: (h["reference"], h["pad"]))  # type: ignore[index]
    if len(mounting_holes) != 4:
        raise ValueError(f"expected four mounting holes in {path}, got {len(mounting_holes)}")
    if len(header_pads) != 4:
        raise ValueError(f"expected four header pads in {path}, got {len(header_pads)}")
    return {
        "source": repo_path(path),
        "board_center_kicad_mm": {"x": cx, "y": cy},
        "board_outer_diameter_mm": round(radius * 2.0, 4),
        "mounting_holes_relative_mm": mounting_holes,
        "header_pads_relative_mm": header_pads,
        "header_bodies_relative_mm": list(header_bodies.values()),
        "backside_capacitor_relative_mm": capacitor,
        "led_relative_mm": led,
    }


def assert_same_layout(a: dict[str, object], b: dict[str, object]) -> None:
    keys = [
        "board_outer_diameter_mm",
        "mounting_holes_relative_mm",
        "header_pads_relative_mm",
        "backside_capacitor_relative_mm",
        "led_relative_mm",
    ]
    for key in keys:
        if a[key] != b[key]:
            raise ValueError(f"WS2812B/SK6812 layout mismatch at {key}: {a[key]} != {b[key]}")


def external_thread_brep(x0: float, length: float, root_d: float, extra_each_end: float = 0.0) -> cq.Workplane:
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
        lefthand=True,
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
    return thread.intersect(x_clip_box(x0, length, crest_d + 4.0))


def female_thread_cutter() -> cq.Workplane:
    return external_thread_brep(
        0.0,
        PARAMS["cmount_thread_length_mm"],
        PARAMS["cmount_female_pilot_root_diameter_mm"],
        extra_each_end=PARAMS["thread_runout_extra_length_each_end_mm"],
    )


def female_bore_cutter() -> cq.Workplane:
    return x_cylinder(
        PARAMS["cmount_female_pilot_root_diameter_mm"],
        PARAMS["cmount_socket_length_mm"] + 0.2,
        -0.1,
    )


def optical_bore_cutter(x0: float, length: float) -> cq.Workplane:
    return x_cylinder(PARAMS["optical_bore_diameter_mm"], length, x0)


def plate_x0() -> float:
    return PARAMS["cmount_socket_length_mm"]


def total_holder_length() -> float:
    return PARAMS["cmount_socket_length_mm"] + PARAMS["holder_plate_thickness_x_mm"]


def board_sink_cutter() -> cq.Workplane:
    x_end = total_holder_length()
    return x_cylinder(
        PARAMS["board_sink_diameter_mm"],
        PARAMS["board_sink_depth_mm"] + 0.1,
        x_end - PARAMS["board_sink_depth_mm"] - 0.05,
    )


def pcb_mount_cutter(y: float, z: float) -> cq.Workplane:
    return x_cylinder(
        PARAMS["pcb_fixation_pilot_diameter_mm"],
        PARAMS["holder_plate_thickness_x_mm"] + 1.2,
        plate_x0() - 0.6,
    ).translate((0, y, z))


def header_relief_cutter(layout: dict[str, object]) -> cq.Workplane:
    cutters: list[cq.Workplane] = []
    x0 = plate_x0() - 0.6
    length = PARAMS["holder_plate_thickness_x_mm"] + 1.2
    pads = layout["header_pads_relative_mm"]  # type: ignore[index]
    for pad in pads:
        cutters.append(
            x_cylinder(PARAMS["pin_header_relief_diameter_mm"], length, x0).translate((0, pad["y"], pad["z"]))
        )
    by_ref: dict[str, list[dict[str, float | str]]] = {}
    for pad in pads:
        by_ref.setdefault(str(pad["reference"]), []).append(pad)
    for ref, ref_pads in by_ref.items():
        y_mid = sum(float(pad["y"]) for pad in ref_pads) / len(ref_pads)
        z_min = min(float(pad["z"]) for pad in ref_pads)
        z_max = max(float(pad["z"]) for pad in ref_pads)
        cutters.append(
            x_box(
                (x0 + length / 2.0, y_mid, (z_min + z_max) / 2.0),
                (
                    length,
                    PARAMS["pin_header_relief_diameter_mm"],
                    z_max - z_min + 0.08,
                ),
            )
        )
    for body in layout["header_bodies_relative_mm"]:  # type: ignore[index]
        cutters.append(
            x_box(
                (x0 + length / 2.0, body["center_y"], body["center_z"]),
                (
                    length,
                    body["relief_width_y_mm"],
                    body["relief_height_z_mm"],
                ),
            )
        )
    result = cutters[0]
    for cutter in cutters[1:]:
        result = result.union(cutter)
    return result


def build_cmount_socket() -> cq.Workplane:
    socket = x_cylinder(PARAMS["cmount_outer_diameter_mm"], PARAMS["cmount_socket_length_mm"], 0.0)
    socket = fillet_if_possible(socket, "|X", 0.35)
    socket = socket.cut(female_bore_cutter()).cut(female_thread_cutter())
    socket = socket.cut(optical_bore_cutter(-0.1, PARAMS["cmount_socket_length_mm"] + 0.2))
    return socket.clean()


def build_holder_plate(layout: dict[str, object]) -> cq.Workplane:
    plate = x_box(
        (
            plate_x0() + PARAMS["holder_plate_thickness_x_mm"] / 2.0,
            0.0,
            0.0,
        ),
        (
            PARAMS["holder_plate_thickness_x_mm"],
            PARAMS["holder_plate_width_y_mm"],
            PARAMS["holder_plate_height_z_mm"],
        ),
    )
    plate = fillet_if_possible(plate, "|X", PARAMS["holder_edge_fillet_mm"])
    plate = plate.cut(optical_bore_cutter(plate_x0() - 0.6, PARAMS["holder_plate_thickness_x_mm"] + 1.2))
    plate = plate.cut(board_sink_cutter())
    for hole in layout["mounting_holes_relative_mm"]:  # type: ignore[index]
        plate = plate.cut(pcb_mount_cutter(hole["y"], hole["z"]))
    plate = plate.cut(header_relief_cutter(layout))
    return plate.clean()


def build_holder_compound(layout: dict[str, object]) -> cq.Compound:
    return cq.Compound.makeCompound([build_cmount_socket().val(), build_holder_plate(layout).val()])


def build_board_proxy(layout: dict[str, object]) -> cq.Workplane:
    x_start = total_holder_length() + 0.05
    board = x_cylinder(PARAMS["board_outer_diameter_mm"], PARAMS["board_thickness_mm"], x_start)
    for hole in layout["mounting_holes_relative_mm"]:  # type: ignore[index]
        board = board.cut(
            x_cylinder(float(hole["source_drill_mm"]), PARAMS["board_thickness_mm"] + 0.2, x_start - 0.1).translate(
                (0, hole["y"], hole["z"])
            )
        )
    for pad in layout["header_pads_relative_mm"]:  # type: ignore[index]
        board = board.cut(
            x_cylinder(float(pad["source_drill_mm"]), PARAMS["board_thickness_mm"] + 0.2, x_start - 0.1).translate(
                (0, pad["y"], pad["z"])
            )
        )
    return board.clean()


def build_led_proxy(layout: dict[str, object]) -> cq.Workplane:
    led = layout["led_relative_mm"]  # type: ignore[index]
    x0 = total_holder_length() + PARAMS["board_thickness_mm"] + 0.05
    return x_box((x0 + 0.6, led["y"], led["z"]), (1.2, 5.0, 5.0))


def build_capacitor_proxy(layout: dict[str, object]) -> cq.Workplane:
    cap = layout["backside_capacitor_relative_mm"]  # type: ignore[index]
    # Draw this slightly behind the PCB to make the backside footprint visible
    # in the assembly. It is documentation geometry, not a required pocket.
    x0 = total_holder_length() + PARAMS["board_thickness_mm"] + 0.15
    return x_box((x0 + 0.35, cap["y"], cap["z"]), (0.7, 1.6, 0.8))


def build_header_proxy(layout: dict[str, object]) -> cq.Workplane:
    x0 = total_holder_length() + PARAMS["board_thickness_mm"] + 0.15
    proxies: list[cq.Workplane] = []
    for body in layout["header_bodies_relative_mm"]:  # type: ignore[index]
        proxies.append(x_box((x0 + 2.0, body["center_y"], body["center_z"]), (4.0, 2.54, 5.08)))
    result = proxies[0]
    for proxy in proxies[1:]:
        result = result.union(proxy)
    return result.clean()


def build_axis_proxy() -> cq.Workplane:
    return x_cylinder(0.7, total_holder_length() + 8.0, -3.0)


def build_assembly(layout: dict[str, object]) -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_cmount_socket(), name="independent_5mm_cmount_socket_25p0_25p4", color=cq.Color(0.10, 0.10, 0.09, 1.0))
    assembly.add(build_holder_plate(layout), name="independent_5mm_ws2812b_sk6812_pcb_holder_plate", color=cq.Color(0.18, 0.18, 0.16, 1.0))
    assembly.add(build_board_proxy(layout), name="shared_24mm_ws2812b_sk6812_board_proxy", color=cq.Color(0.0, 0.24, 0.50, 0.58))
    assembly.add(build_led_proxy(layout), name="5050_led_proxy_on_optical_axis", color=cq.Color(0.95, 0.82, 0.24, 0.88))
    assembly.add(build_capacitor_proxy(layout), name="backside_C_0603_capacitor_footprint_proxy", color=cq.Color(0.08, 0.76, 0.44, 0.85))
    assembly.add(build_header_proxy(layout), name="two_side_1x02_header_head_proxy", color=cq.Color(0.82, 0.18, 0.18, 0.55))
    assembly.add(female_thread_cutter(), name="bounded_half_pitch_female_thread_cutter_reference", color=cq.Color(0.9, 0.2, 0.1, 0.28))
    assembly.add(build_axis_proxy(), name="optical_axis_proxy", color=cq.Color(1.0, 0.72, 0.08, 0.58))
    return assembly


def validate_step(path: Path) -> dict[str, object]:
    imported = cq.importers.importStep(str(path))
    shape = imported.val()
    bbox = shape.BoundingBox()
    return {
        "path": repo_path(path),
        "valid": bool(BRepCheck_Analyzer(shape.wrapped).IsValid()),
        "solid_count": len(shape.Solids()),
        "bbox_mm": [round(bbox.xlen, 4), round(bbox.ylen, 4), round(bbox.zlen, 4)],
    }


def validate_stl(path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(path, force="mesh")
    components = mesh.split(only_watertight=False)
    extents = mesh.bounds[1] - mesh.bounds[0]
    return {
        "path": repo_path(path),
        "is_watertight": bool(mesh.is_watertight),
        "component_count": len(components),
        "bbox_mm": [round(float(v), 4) for v in extents],
        "triangles": int(len(mesh.faces)),
    }


def validate_3mf(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path, "r") as archive:
        names = sorted(archive.namelist())
    return {"path": repo_path(path), "valid": "3D/3dmodel.model" in names, "zip_entries": names}


def write_alignment_svg(path: Path, layout: dict[str, object]) -> None:
    scale = 9.0
    margin = 54
    legend_w = 530
    view = 42.0
    svg_w = int(view * scale + margin * 2 + legend_w)
    svg_h = int(view * scale + margin * 2)

    def sx(y: float) -> float:
        return margin + (y + view / 2.0) * scale

    def sy(z: float) -> float:
        return margin + (view / 2.0 - z) * scale

    def circle(y: float, z: float, diameter: float, fill: str, stroke: str, label: str = "") -> str:
        text = ""
        if label:
            text = f'<text x="{sx(y)+8:.2f}" y="{sy(z)-8:.2f}" font-family="Arial" font-size="12" fill="#1a202c">{label}</text>'
        return f'<circle cx="{sx(y):.2f}" cy="{sy(z):.2f}" r="{diameter/2*scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>{text}'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-21):.2f}" y="{sy(21):.2f}" width="{42*scale:.2f}" height="{42*scale:.2f}" rx="8" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        f'<circle cx="{sx(0):.2f}" cy="{sy(0):.2f}" r="{12*scale:.2f}" fill="#e6f0ff" stroke="#2b6cb0" stroke-width="2" stroke-dasharray="8 5"/>',
        circle(0, 0, PARAMS["led_aperture_diameter_mm"], "#fff7d6", "#d69e2e", "LED / axis"),
    ]
    for hole in layout["mounting_holes_relative_mm"]:  # type: ignore[index]
        lines.append(circle(hole["y"], hole["z"], PARAMS["pcb_fixation_pilot_diameter_mm"], "#edf2f7", "#4a5568", "1.8" if hole["y"] < 0 and hole["z"] < 0 else ""))
    for pad in layout["header_pads_relative_mm"]:  # type: ignore[index]
        lines.append(circle(pad["y"], pad["z"], PARAMS["pin_header_relief_diameter_mm"], "#fff5f5", "#c53030", "3.0" if pad["pad"] == "1" else ""))
    for body in layout["header_bodies_relative_mm"]:  # type: ignore[index]
        lines.append(
            f'<rect x="{sx(body["center_y"]-body["relief_width_y_mm"]/2):.2f}" y="{sy(body["center_z"]+body["relief_height_z_mm"]/2):.2f}" width="{body["relief_width_y_mm"]*scale:.2f}" height="{body["relief_height_z_mm"]*scale:.2f}" fill="none" stroke="#c53030" stroke-width="1.5" stroke-dasharray="5 4"/>'
        )
    cap = layout["backside_capacitor_relative_mm"]  # type: ignore[index]
    lines.append(
        f'<rect x="{sx(cap["y"]-0.8):.2f}" y="{sy(cap["z"]+0.4):.2f}" width="{1.6*scale:.2f}" height="{0.8*scale:.2f}" fill="#9ae6b4" stroke="#276749" stroke-width="1.5"/>'
    )
    legend_x = margin + view * scale + 34
    legend = [
        "WS2812B / SK6812 shared C-mount holder",
        "Blue dashed circle: 24 mm PCB sink",
        "Gold circle: 10 mm LED/optical aperture",
        "Gray holes: 1.8 mm PCB fixation pilots",
        "Red capsules: 3 mm side header clearances",
        "Green rectangle: backside C_0603 footprint proxy",
        "C-mount: 5 mm socket/thread, 25.0 pilot, 25.4 nominal cutter",
    ]
    for i, text in enumerate(legend):
        lines.append(
            f'<text x="{legend_x:.2f}" y="{margin + i*25:.2f}" font-family="Arial" font-size="{17 if i == 0 else 13}" font-weight="{700 if i == 0 else 400}" fill="#1a202c">{text}</text>'
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
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run([rsvg, "-f", "png", "-o", str(svg_path.with_suffix(".png")), str(svg_path)], check=False)
        subprocess.run([rsvg, "-f", "pdf", "-o", str(svg_path.with_suffix(".pdf")), str(svg_path)], check=False)


def copy_print_ready(files: list[Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for path in files:
        if path.exists():
            shutil.copy2(path, NUTSTORE_DIR / path.name)


def write_readme(path: Path, layout: dict[str, object], outputs: dict[str, str], validations: dict[str, object]) -> None:
    output_rows = "\n".join(f"| {key} | `{value}` |" for key, value in outputs.items())
    mount_rows = "\n".join(
        f"| mount | `{hole['y']}` | `{hole['z']}` | `{hole['source_drill_mm']}` | `{hole['holder_pilot_mm']}` |"
        for hole in layout["mounting_holes_relative_mm"]  # type: ignore[index]
    )
    header_rows = "\n".join(
        f"| {pad['reference']} pad {pad['pad']} | `{pad['y']}` | `{pad['z']}` | `{pad['source_drill_mm']}` | `{pad['holder_clearance_mm']}` |"
        for pad in layout["header_pads_relative_mm"]  # type: ignore[index]
    )
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# WS2812B / SK6812 C-Mount LED Holder Run 1

Shared holder for the two 24 mm round addressable LED carrier PCBs:

- `pcb/ws2812b-5050-rgb-led`
- `pcb/sk6812rgbw-5050-rgbw-led`

The two KiCad boards have the same mechanical layout, so one holder works for
both. Both boards include a backside `Custom:C_0603` decoupling capacitor
footprint and no onboard series resistor footprint.

## Design

- C-mount side: `5 mm` long female socket with a `5 mm` bounded printable
  C-mount-style internal thread.
- Nominal thread: `25.0 mm` pilot/root, `25.4 mm` cutter crest, `0.8 mm`
  pitch. The thread cutter is swept an extra half pitch beyond both ends and
  then clipped/subtracted inside the socket so it reaches the faces without
  leaving overflow.
- Holder side: `5 mm` thick square plate, similar to the clean Lumileds PCB
  holder but without cage-rod holes.
- Bodies are decoupled: the C-mount socket is one body, the PCB holder plate is
  a second adjacent body. They touch at x=`{PARAMS['independent_body_contact_plane_x_mm']}`.
- PCB sink: `24.4 mm` diameter, `1.7 mm` deep for the `24 mm` board.
- PCB fixation pilots: four `1.8 mm` holes at the board's `12 x 12 mm`
  mounting-hole pattern.
- Header clearances: two side clearances. Each side uses two overlapping
  `3.0 mm` holes on the real `2.54 mm` pin pitch plus a bridge and a larger
  rectangular head clearance, so the material between pins is removed.
- LED aperture: `10 mm`, centered on the optical axis.

## Board Geometry

Mounting holes:

| Feature | y mm | z mm | PCB drill mm | holder cut mm |
| --- | ---: | ---: | ---: | ---: |
{mount_rows}

Header pads:

| Feature | y mm | z mm | PCB drill mm | holder cut mm |
| --- | ---: | ---: | ---: | ---: |
{header_rows}

Backside footprint:

```json
{json.dumps(layout['backside_capacitor_relative_mm'], indent=2)}
```

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

Nutstore sync folder:

`{NUTSTORE_DIR}`

## Validation

```json
{json.dumps(validations, indent=2)}
```

## Parameters

| Parameter | Value |
| --- | --- |
{param_rows}
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ws_layout = extract_led_board_geometry(WS2812B_PCB)
    sk_layout = extract_led_board_geometry(SK6812_PCB)
    assert_same_layout(ws_layout, sk_layout)
    layout = ws_layout

    holder = build_holder_compound(layout)
    socket = build_cmount_socket()
    plate = build_holder_plate(layout)
    board = build_board_proxy(layout)
    cutter = female_thread_cutter()
    assembly = build_assembly(layout)

    print_step = RUN_DIR / f"PRINT_THIS_{STEM}.step"
    print_stl = RUN_DIR / f"PRINT_THIS_{STEM}.stl"
    print_3mf = RUN_DIR / f"PRINT_THIS_{STEM}.3mf"
    use_step = RUN_DIR / f"USE_THIS_{STEM}_assembly.step"
    socket_step = ARTIFACT_DIR / f"{STEM}_cmount_socket.step"
    plate_step = ARTIFACT_DIR / f"{STEM}_holder_plate.step"
    holder_step = ARTIFACT_DIR / f"{STEM}_decoupled_holder.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}_decoupled_holder.stl"
    board_step = ARTIFACT_DIR / f"{STEM}_board_proxy.step"
    board_stl = ARTIFACT_DIR / f"{STEM}_board_proxy.stl"
    cutter_step = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.step"
    cutter_stl = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.stl"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly_with_proxies.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly_with_proxies.stl"
    alignment_svg = ARTIFACT_DIR / f"{STEM}_rear_alignment.svg"

    exporters.export(holder, str(print_step))
    exporters.export(holder, str(print_stl))
    exporters.export(holder, str(use_step))
    exporters.export(holder, str(holder_step))
    exporters.export(holder, str(holder_stl))
    exporters.export(socket, str(socket_step))
    exporters.export(plate, str(plate_step))
    exporters.export(board, str(board_step))
    exporters.export(board, str(board_stl))
    exporters.export(cutter, str(cutter_step))
    exporters.export(cutter, str(cutter_stl))
    assembly.save(str(assembly_step))
    assembly.save(str(assembly_stl))
    export_stl_as_3mf(print_stl, print_3mf, title=STEM)

    write_alignment_svg(alignment_svg, layout)
    convert_svg(alignment_svg)

    validations = {
        "print_step": validate_step(print_step),
        "print_stl": validate_stl(print_stl),
        "print_3mf": validate_3mf(print_3mf),
        "assembly_step_with_proxies": validate_step(assembly_step),
        "source_layout_match": True,
    }
    outputs = {
        "print_step": repo_path(print_step),
        "print_stl": repo_path(print_stl),
        "print_3mf": repo_path(print_3mf),
        "use_this_assembly_step": repo_path(use_step),
        "decoupled_holder_step": repo_path(holder_step),
        "decoupled_holder_stl": repo_path(holder_stl),
        "cmount_socket_step": repo_path(socket_step),
        "holder_plate_step": repo_path(plate_step),
        "board_proxy_step": repo_path(board_step),
        "board_proxy_stl": repo_path(board_stl),
        "female_thread_cutter_step": repo_path(cutter_step),
        "female_thread_cutter_stl": repo_path(cutter_stl),
        "assembly_with_proxies_step": repo_path(assembly_step),
        "assembly_with_proxies_stl": repo_path(assembly_stl),
        "rear_alignment_svg": repo_path(alignment_svg),
        "rear_alignment_png": repo_path(alignment_svg.with_suffix(".png")),
        "rear_alignment_pdf": repo_path(alignment_svg.with_suffix(".pdf")),
        "render_png": repo_path(RUN_DIR / f"PRINT_THIS_{STEM}_render.png"),
    }
    manifest = {
        "name": STEM,
        "params": PARAMS,
        "layout": layout,
        "sk6812_layout_checked_against_ws2812b": sk_layout,
        "outputs": outputs,
        "validations": validations,
        "nutstore_sync": str(NUTSTORE_DIR),
    }
    manifest_path = ARTIFACT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    outputs["manifest"] = repo_path(manifest_path)
    write_readme(RUN_DIR / "README.md", layout, outputs, validations)
    copy_print_ready([print_step, print_stl, print_3mf, use_step, RUN_DIR / "README.md", alignment_svg.with_suffix(".png")])


if __name__ == "__main__":
    main()
