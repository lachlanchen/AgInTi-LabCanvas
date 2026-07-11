#!/usr/bin/env python3
"""Build a clean Lumileds cage holder with a simple PCB-thickness sink.

This is a sibling of `lumileds_pcb_aligned_simple_cage_holder`. It keeps the
same centered 42 mm plate and PCB-derived hole layout, then adds one rear
circular sink for the 24 mm Lumileds PCB. The sink depth equals the PCB
thickness so the board can sit flush in the holder.
"""

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
import trimesh


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "lumileds_pcb_aligned_sink_cage_holder"
SOURCE_PCB = ROOT / "pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb"
TOOLS_DIR = ROOT / "cad" / "tools"
NUTSTORE_DIR = (
    Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")
    / "lumileds_pcb_aligned_sink_cage_holder"
    / "pin-header-3mm-relief-print-ready"
)
sys.path.insert(0, str(TOOLS_DIR))

from simple_3mf import export_stl_as_3mf


PARAMS = {
    "name": STEM,
    "source_pcb": "pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb",
    "base_design": "self-contained rebuild of cad/designs/lumileds_pcb_aligned_simple_cage_holder geometry",
    "body_width_mm": 42.0,
    "body_height_mm": 42.0,
    "body_thickness_mm": 8.0,
    "edge_fillet_mm": 0.8,
    "cage_rod_pitch_mm": 30.0,
    "cage_rod_clearance_diameter_mm": 6.4,
    "pcb_outer_diameter_mm": 24.0,
    "pcb_sink_diameter_mm": 24.4,
    "pcb_thickness_mm": 1.6,
    "pcb_sink_depth_mm": 1.6,
    "pcb_mount_clearance_diameter_mm": 1.8,
    "pcb_mount_hole_note": "Four PCB fixation holes are 1.8 mm pilot holes for roughly 2 mm self-tapping screws in printed plastic.",
    "header_pin_relief_diameter_mm": 3.0,
    "header_pin_relief_style": "two overlapping 3.0 mm holes plus a rectangular bridge, forming one fully cleared capsule slot for pin overflow",
    "led_aperture_diameter_mm": 10.0,
    "print_ears_enabled": True,
    "print_ear_thickness_mm": 1.0,
    "print_ear_side_contact_mm": 5.0,
    "print_ear_breakaway_overlap_mm": 0.5,
    "print_ear_side_reach_mm": 10.0,
    "print_ear_side_width_mm": 5.0,
    "print_ear_diagonal_reach_mm": 12.0,
    "print_ear_tail_width_mm": 10.0,
    "print_orientation": "PRINT_THIS files are rotated so the PCB sink faces upward; four 1.0 mm sacrificial ears sit on the build-plate side.",
    "coordinate_rule": "PCB center is translated to holder origin. The rear PCB sink is concentric with the KiCad board outline.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(float(diameter) / 2.0).extrude(float(height))


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def z_poly(points: list[tuple[float, float]], height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).polyline(points).close().extrude(height)


def _footprint_blocks(text: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"\n\s*\(footprint\s+", text)]
    blocks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else text.find("\n  (gr_", start)
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


def extract_pcb_geometry(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    edge = None
    for match in re.finditer(
        r'\(gr_circle\s+\(center\s+([-0-9.]+)\s+([-0-9.]+)\)\s+\(end\s+([-0-9.]+)\s+([-0-9.]+)\)\s*\n\s+\(stroke[^\n]*\)\s+\(fill[^\n]*\)\s+\(layer\s+"([^"]+)"\)',
        text,
    ):
        if match.group(5) == "Edge.Cuts":
            edge = match
            break
    if edge is None:
        raise ValueError(f"could not find circular Edge.Cuts outline in {path}")
    cx, cy, ex, ey = (float(edge.group(i)) for i in range(1, 5))
    radius = math.hypot(ex - cx, ey - cy)

    mounting_holes: list[dict[str, float | str]] = []
    header_pins: list[dict[str, float | str]] = []
    led_center = {"x": 0.0, "y": 0.0, "source": "fallback_board_center"}

    for block in _footprint_blocks(text):
        if "MountingHole:MountingHole_2.2mm_M2" in block:
            x, y, _ = _first_at(block)
            drill_match = re.search(r"\(drill\s+([-0-9.]+)", block)
            mounting_holes.append(
                {
                    "x": round(x - cx, 4),
                    "y": round(y - cy, 4),
                    "drill_mm": float(drill_match.group(1)) if drill_match else 2.2,
                    "source": "MountingHole_2.2mm_M2",
                }
            )
        elif "Custom_Footprint_Library:LXCL_MN08_4000" in block:
            x, y, _ = _first_at(block)
            led_center = {"x": round(x - cx, 4), "y": round(y - cy, 4), "source": "LXCL_MN08_4000"}
        elif "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Horizontal" in block:
            fx, fy, rotation = _first_at(block)
            pads = re.finditer(
                r'\(pad\s+"([^"]+)"\s+thru_hole\s+\w+\s+\(at\s+([-0-9.]+)\s+([-0-9.]+)',
                block,
            )
            for pad in pads:
                local_x, local_y = float(pad.group(2)), float(pad.group(3))
                rx, ry = _rotate(local_x, local_y, rotation)
                header_pins.append(
                    {
                        "name": pad.group(1),
                        "x": round(fx + rx - cx, 4),
                        "y": round(fy + ry - cy, 4),
                        "drill_mm": 1.0,
                        "source": "PinHeader_1x02_P2.54mm_Horizontal",
                    }
                )

    if len(mounting_holes) != 4:
        raise ValueError(f"expected 4 PCB mounting holes, found {len(mounting_holes)}")
    if len(header_pins) != 2:
        raise ValueError(f"expected 2 header pin holes, found {len(header_pins)}")

    mounting_holes.sort(key=lambda row: (row["y"], row["x"]))  # type: ignore[index]
    header_pins.sort(key=lambda row: str(row["name"]))
    geometry = {
        "source_pcb": repo_path(path),
        "pcb_center_kicad_mm": {"x": cx, "y": cy},
        "pcb_outer_diameter_mm": round(radius * 2.0, 4),
        "pcb_radius_mm": round(radius, 4),
        "led_center_relative_mm": led_center,
        "mounting_holes_relative_mm": mounting_holes,
        "header_pins_relative_mm": header_pins,
    }
    if abs(float(geometry["pcb_outer_diameter_mm"]) - PARAMS["pcb_outer_diameter_mm"]) > 0.01:
        raise ValueError(
            f"expected PCB diameter {PARAMS['pcb_outer_diameter_mm']} mm, got {geometry['pcb_outer_diameter_mm']}"
        )
    return geometry


def build_holder(geometry: dict[str, object]) -> cq.Workplane:
    p = PARAMS
    width = p["body_width_mm"]
    height = p["body_height_mm"]
    thickness = p["body_thickness_mm"]
    z_min = -thickness / 2.0 - 0.6
    cut_height = thickness + 1.2

    holder = cq.Workplane("XY").box(width, height, thickness)
    if p["edge_fillet_mm"]:
        holder = holder.edges("|Z").fillet(p["edge_fillet_mm"])

    rear_face_z = -thickness / 2.0
    holder = holder.cut(
        z_cylinder(p["pcb_sink_diameter_mm"], p["pcb_sink_depth_mm"] + 0.1, rear_face_z - 0.05)
    )

    rod_half = p["cage_rod_pitch_mm"] / 2.0
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            holder = holder.cut(
                z_cylinder(p["cage_rod_clearance_diameter_mm"], cut_height, z_min).translate((x, y, 0))
            )

    led = geometry["led_center_relative_mm"]  # type: ignore[index]
    holder = holder.cut(
        z_cylinder(p["led_aperture_diameter_mm"], cut_height, z_min).translate((led["x"], led["y"], 0))
    )

    for hole in geometry["mounting_holes_relative_mm"]:  # type: ignore[index]
        holder = holder.cut(
            z_cylinder(p["pcb_mount_clearance_diameter_mm"], cut_height, z_min).translate((hole["x"], hole["y"], 0))
        )

    holder = holder.cut(build_header_pin_relief(geometry, cut_height, z_min))

    return holder


def build_header_pin_relief(geometry: dict[str, object], cut_height: float, z_min: float) -> cq.Workplane:
    p = PARAMS
    pins = geometry["header_pins_relative_mm"]  # type: ignore[index]
    diameter = p["header_pin_relief_diameter_mm"]
    x_mid = sum(pin["x"] for pin in pins) / len(pins)
    y_mid = sum(pin["y"] for pin in pins) / len(pins)
    y_min = min(pin["y"] for pin in pins)
    y_max = max(pin["y"] for pin in pins)

    relief = None
    for pin in pins:
        cut = z_cylinder(diameter, cut_height, z_min).translate((pin["x"], pin["y"], 0))
        relief = cut if relief is None else relief.union(cut)

    # The 2.54 mm pitch holes overlap at 4.0 mm diameter, but add a bridge
    # cutter anyway so Shapr/slicers see one continuous pin-overflow slot.
    bridge = z_box((diameter, max(0.01, y_max - y_min), cut_height), (x_mid, y_mid, z_min + cut_height / 2.0))
    assert relief is not None
    return relief.union(bridge)


def small_corner_ear(sx: int, sy: int) -> cq.Workplane:
    p = PARAMS
    half_w = p["body_width_mm"] / 2.0
    half_h = p["body_height_mm"] / 2.0
    overlap = p["print_ear_breakaway_overlap_mm"]
    contact = p["print_ear_side_contact_mm"]
    side_len = p["print_ear_side_reach_mm"]
    side_width = p["print_ear_side_width_mm"]
    reach = p["print_ear_diagonal_reach_mm"]
    tail = p["print_ear_tail_width_mm"]
    thickness = p["print_ear_thickness_mm"]

    # Add ears to the front face of the design coordinate system. The
    # print-layout export rotates this model 180 degrees so these ears become
    # the build-plate side and the PCB sink faces upward.
    z_min = p["body_thickness_mm"] / 2.0 - thickness

    def local_points(local: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(sx * (half_w + u), sy * (half_h + v)) for u, v in local]

    diagonal_corner_pull = [
        (-overlap, -overlap),
        (side_len, -overlap),
        (side_len, side_width),
        (reach + tail / 2.0, reach - tail / 2.0),
        (reach + tail / 2.0, reach + tail / 2.0),
        (reach - tail / 2.0, reach + tail / 2.0),
        (side_width, side_len),
        (-overlap, side_len),
    ]
    side_contact_a = [
        (-contact, -overlap),
        (side_len, -overlap),
        (side_len, side_width),
        (-contact, side_width),
    ]
    side_contact_b = [
        (-overlap, -contact),
        (side_width, -contact),
        (side_width, side_len),
        (-overlap, side_len),
    ]
    ear = z_poly(local_points(diagonal_corner_pull), thickness, z_min)
    ear = ear.union(z_poly(local_points(side_contact_a), thickness, z_min))
    ear = ear.union(z_poly(local_points(side_contact_b), thickness, z_min))
    return ear


def add_print_ears(holder: cq.Workplane) -> cq.Workplane:
    if not PARAMS["print_ears_enabled"]:
        return holder
    for sx in (-1, 1):
        for sy in (-1, 1):
            holder = holder.union(small_corner_ear(sx, sy))
    return holder


def build_print_holder(geometry: dict[str, object]) -> cq.Workplane:
    p = PARAMS
    holder = add_print_ears(build_holder(geometry))
    holder = holder.rotate((0, 0, 0), (1, 0, 0), 180)
    return holder.translate((0, 0, p["body_thickness_mm"] / 2.0))


def build_pcb_proxy(geometry: dict[str, object]) -> cq.Workplane:
    p = PARAMS
    rear_face_z = -p["body_thickness_mm"] / 2.0
    pcb_z_min = rear_face_z + 0.02
    pcb = z_cylinder(geometry["pcb_outer_diameter_mm"], p["pcb_thickness_mm"], pcb_z_min)  # type: ignore[arg-type]
    for hole in geometry["mounting_holes_relative_mm"]:  # type: ignore[index]
        pcb = pcb.cut(
            z_cylinder(hole["drill_mm"], p["pcb_thickness_mm"] + 0.4, pcb_z_min - 0.2).translate((hole["x"], hole["y"], 0))
        )
    for pin in geometry["header_pins_relative_mm"]:  # type: ignore[index]
        pcb = pcb.cut(
            z_cylinder(pin["drill_mm"], p["pcb_thickness_mm"] + 0.4, pcb_z_min - 0.2).translate((pin["x"], pin["y"], 0))
        )
    return pcb


def build_led_proxy(geometry: dict[str, object]) -> cq.Workplane:
    p = PARAMS
    rear_face_z = -p["body_thickness_mm"] / 2.0
    led = geometry["led_center_relative_mm"]  # type: ignore[index]
    return z_cylinder(4.8, 0.75, rear_face_z - 0.76).translate((led["x"], led["y"], 0))


def build_header_proxy(geometry: dict[str, object]) -> cq.Workplane:
    p = PARAMS
    rear_face_z = -p["body_thickness_mm"] / 2.0
    pins = geometry["header_pins_relative_mm"]  # type: ignore[index]
    y_mid = sum(pin["y"] for pin in pins) / len(pins)
    x_mid = sum(pin["x"] for pin in pins) / len(pins)
    body = z_box((5.2, 6.4, 2.5), (x_mid + 2.2, y_mid, rear_face_z - 1.25))
    for pin in pins:
        body = body.union(
            z_cylinder(0.72, p["body_thickness_mm"] + p["pcb_thickness_mm"] + 0.8, rear_face_z - 0.2)
            .translate((pin["x"], pin["y"], 0))
        )
    return body


def build_alignment_rods() -> cq.Workplane:
    p = PARAMS
    rod_half = p["cage_rod_pitch_mm"] / 2.0
    rods = None
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            rod = z_cylinder(5.9, p["body_thickness_mm"] + 4.0, -p["body_thickness_mm"] / 2.0 - 2.0).translate((x, y, 0))
            rods = rod if rods is None else rods.union(rod)
    assert rods is not None
    return rods


def build_assembly(geometry: dict[str, object]) -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_holder(geometry), name="single_piece_holder_with_rear_pcb_sink", color=cq.Color(0.08, 0.08, 0.08, 1.0))
    assembly.add(build_pcb_proxy(geometry), name="pcb_proxy_inside_1p6mm_sink", color=cq.Color(0.0, 0.45, 0.12, 0.72))
    assembly.add(build_led_proxy(geometry), name="led_emitter_proxy", color=cq.Color(1.0, 0.82, 0.18, 1.0))
    assembly.add(build_header_proxy(geometry), name="right_angle_2p_header_proxy", color=cq.Color(0.02, 0.02, 0.02, 1.0))
    assembly.add(build_alignment_rods(), name="30mm_cage_rod_alignment_proxy", color=cq.Color(0.2, 0.55, 0.9, 0.45))
    return assembly


def write_alignment_svg(path: Path, geometry: dict[str, object]) -> None:
    p = PARAMS
    scale = 9.0
    pad = 54.0
    legend_w = 430
    w = p["body_width_mm"]
    h = p["body_height_mm"]
    svg_w = int(w * scale + pad * 2 + legend_w)
    svg_h = int(h * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (h / 2.0 - y) * scale

    def circle(x: float, y: float, d: float, fill: str, stroke: str, label: str = "", dash: str = "") -> str:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        label_svg = ""
        if label:
            label_svg = f'<text x="{sx(x)+6}" y="{sy(y)-6}" font-family="Arial" font-size="11" fill="#1a202c">{label}</text>'
        return (
            f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{d/2*scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash_attr}/>'
            + label_svg
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-w/2):.2f}" y="{sy(h/2):.2f}" width="{w*scale:.2f}" height="{h*scale:.2f}" rx="{p["edge_fillet_mm"]*scale:.2f}" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        '<line x1="{0:.2f}" y1="{1:.2f}" x2="{2:.2f}" y2="{1:.2f}" stroke="#cbd5e0" stroke-width="1"/>'.format(sx(-w/2), sy(0), sx(w/2)),
        '<line x1="{0:.2f}" y1="{1:.2f}" x2="{0:.2f}" y2="{2:.2f}" stroke="#cbd5e0" stroke-width="1"/>'.format(sx(0), sy(h/2), sy(-h/2)),
        circle(0, 0, p["pcb_sink_diameter_mm"], "#e6fffa", "#319795", dash="8 5"),
        circle(0, 0, geometry["pcb_outer_diameter_mm"], "none", "#38a169", dash="5 4"),
    ]

    rod_half = p["cage_rod_pitch_mm"] / 2.0
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            lines.append(circle(x, y, p["cage_rod_clearance_diameter_mm"], "#ebf8ff", "#3182ce"))

    led = geometry["led_center_relative_mm"]  # type: ignore[index]
    lines.append(circle(led["x"], led["y"], p["led_aperture_diameter_mm"], "#fffaf0", "#dd6b20"))
    for idx, hole in enumerate(geometry["mounting_holes_relative_mm"], start=1):  # type: ignore[index]
        lines.append(circle(hole["x"], hole["y"], p["pcb_mount_clearance_diameter_mm"], "#fefcbf", "#b7791f"))
    pins = geometry["header_pins_relative_mm"]  # type: ignore[index]
    pin_x_mid = sum(pin["x"] for pin in pins) / len(pins)
    pin_y_min = min(pin["y"] for pin in pins)
    pin_y_max = max(pin["y"] for pin in pins)
    pin_d = p["header_pin_relief_diameter_mm"]
    lines.append(
        f'<rect x="{sx(pin_x_mid - pin_d / 2):.2f}" y="{sy(pin_y_max):.2f}" '
        f'width="{pin_d * scale:.2f}" height="{(pin_y_max - pin_y_min) * scale:.2f}" '
        'fill="#fed7d7" stroke="#c53030" stroke-width="2"/>'
    )
    for pin in pins:
        lines.append(circle(pin["x"], pin["y"], p["header_pin_relief_diameter_mm"], "#fed7d7", "#c53030"))

    legend_x = pad + w * scale + 34
    legend = [
        "Lumileds aligned holder with PCB sink",
        f"Body: {w} x {h} x {p['body_thickness_mm']} mm",
        f"PCB: dia {geometry['pcb_outer_diameter_mm']} mm, thickness {p['pcb_thickness_mm']} mm",
        f"Rear sink: dia {p['pcb_sink_diameter_mm']} mm, depth {p['pcb_sink_depth_mm']} mm",
        f"PCB fixation holes: {p['pcb_mount_clearance_diameter_mm']} mm pilot, +/-6 mm",
        f"Header relief: connected {p['header_pin_relief_diameter_mm']} mm two-hole slot",
        f"Cage rods: 30 mm pitch, dia {p['cage_rod_clearance_diameter_mm']} mm",
        "Rear PCB sink stays concentric with the board outline",
    ]
    for i, row in enumerate(legend):
        size = 17 if i == 0 else 13
        weight = "700" if i == 0 else "400"
        lines.append(
            f'<text x="{legend_x:.2f}" y="{pad + i * 25:.2f}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(path: Path, geometry: dict[str, object], outputs: dict[str, str]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    led = geometry["led_center_relative_mm"]  # type: ignore[index]
    led_text = f"({led['x']}, {led['y']}) mm from {led['source']}"
    path.write_text(
        f"""# Lumileds PCB-Aligned Sink Cage Holder

This is a sibling of `cad/designs/lumileds_pcb_aligned_simple_cage_holder`.
It keeps the same clean monolithic holder geometry, adds a rear PCB sink, uses
smaller PCB fixation pilot holes for self-tapping screws, opens the pin-header
relief into a connected slot, and provides a rotated direct-print layout with
four small removable ears.

## PCB Geometry Used

- Source PCB: `{geometry['source_pcb']}`
- PCB outer diameter: `{geometry['pcb_outer_diameter_mm']} mm`
- PCB thickness used for sink depth: `{PARAMS['pcb_thickness_mm']} mm`
- LED center: `{led_text}`
- Mount holes: `(+/-6, +/-6) mm`, opened to `{PARAMS['pcb_mount_clearance_diameter_mm']} mm`
- Header relief: `(10, 1)` and `(10, -1.54) mm`, opened as a connected `{PARAMS['header_pin_relief_diameter_mm']} mm` two-hole slot

## Design Rule

Use the PCB as the source of truth. The KiCad board center is translated to the
holder origin. The rear circular sink is concentric with the 24 mm PCB outline,
opened to `{PARAMS['pcb_sink_diameter_mm']} mm`, and cut `{PARAMS['pcb_sink_depth_mm']} mm` deep.

The PCB sink stays concentric. The four fixation holes are intentionally smaller
than the PCB drill size so roughly 2 mm self-tapping screws can bite into the
printed plastic. The header relief is intentionally larger and connected so pin
overflow does not collide with the holder.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}

## Notes

- Use the root `PRINT_THIS_*` files for printing. They are rotated so the PCB
  sink faces upward and include four small removable ears.
- Use the holder-only STEP/STL for clean CAD editing. The assembly STEP/STL
  includes PCB, LED, header, and cage-rod proxies only for fit checking.
- If the PCB is too tight, change `pcb_sink_diameter_mm`; keep the mount-hole
  coordinates unchanged.
- If the self-tapping screws are too tight, increase
  `pcb_mount_clearance_diameter_mm` in small steps such as `0.1 mm`.
""",
        encoding="utf-8",
    )


def write_manifest(path: Path, geometry: dict[str, object], outputs: dict[str, str], checks: dict[str, object]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": "Clean Lumileds holder with rear PCB-thickness sink, 1.8 mm self-tapping pilot holes, and a connected 3.0 mm pin-header relief slot.",
        "parameters": PARAMS,
        "pcb_geometry": geometry,
        "outputs": outputs,
        "validation": checks,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def svg_to_png(svg: Path, png: Path) -> None:
    if subprocess.run(["which", "convert"], capture_output=True, text=True).returncode != 0:
        return
    subprocess.run(["convert", str(svg), str(png)], check=True)


def mesh_checks(stl_path: Path) -> dict[str, object]:
    mesh = trimesh.load_mesh(stl_path, force="mesh")
    return {
        "watertight": bool(mesh.is_watertight),
        "bounds_mm": {
            "min": [round(float(v), 3) for v in mesh.bounds[0]],
            "max": [round(float(v), 3) for v in mesh.bounds[1]],
            "size": [round(float(v), 3) for v in (mesh.bounds[1] - mesh.bounds[0])],
        },
    }


def validate_3mf(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return sorted(archive.namelist())


def sync_print_ready(files: list[Path]) -> None:
    NUTSTORE_DIR.mkdir(parents=True, exist_ok=True)
    for src in files:
        if src.exists():
            shutil.copy2(src, NUTSTORE_DIR / src.name)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    geometry = extract_pcb_geometry(SOURCE_PCB)

    holder = build_holder(geometry)
    print_holder = build_print_holder(geometry)
    pcb = build_pcb_proxy(geometry)
    assembly = build_assembly(geometry).toCompound()

    holder_step = ARTIFACT_DIR / f"{STEM}.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}.stl"
    print_layout_step = ARTIFACT_DIR / f"{STEM}_print_layout.step"
    print_layout_stl = ARTIFACT_DIR / f"{STEM}_print_layout.stl"
    print_layout_3mf = ARTIFACT_DIR / f"{STEM}_print_layout.3mf"
    pcb_step = ARTIFACT_DIR / f"{STEM}_pcb_proxy.step"
    pcb_stl = ARTIFACT_DIR / f"{STEM}_pcb_proxy.stl"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    alignment_svg = ARTIFACT_DIR / f"{STEM}_top_alignment.svg"
    alignment_png = ARTIFACT_DIR / f"{STEM}_top_alignment.png"
    geometry_json = ARTIFACT_DIR / f"{STEM}_pcb_geometry.json"
    manifest = ARTIFACT_DIR / "manifest.json"

    exporters.export(holder, str(holder_step))
    exporters.export(holder, str(holder_stl))
    exporters.export(print_holder, str(print_layout_step))
    exporters.export(print_holder, str(print_layout_stl))
    export_stl_as_3mf(print_layout_stl, print_layout_3mf, title=f"{STEM} print layout")
    exporters.export(pcb, str(pcb_step))
    exporters.export(pcb, str(pcb_stl))
    exporters.export(assembly, str(assembly_step))
    exporters.export(assembly, str(assembly_stl))
    write_alignment_svg(alignment_svg, geometry)
    svg_to_png(alignment_svg, alignment_png)
    geometry_json.write_text(json.dumps(geometry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    use_this_step = DESIGN_DIR / f"USE_THIS_{STEM}.step"
    print_this_step = DESIGN_DIR / f"PRINT_THIS_{STEM}.step"
    print_this_stl = DESIGN_DIR / f"PRINT_THIS_{STEM}.stl"
    print_this_3mf = DESIGN_DIR / f"PRINT_THIS_{STEM}.3mf"
    shutil.copy2(holder_step, use_this_step)
    shutil.copy2(print_layout_step, print_this_step)
    shutil.copy2(print_layout_stl, print_this_stl)
    shutil.copy2(print_layout_3mf, print_this_3mf)

    outputs = {
        "holder_step": repo_path(holder_step),
        "holder_stl": repo_path(holder_stl),
        "print_layout_step": repo_path(print_layout_step),
        "print_layout_stl": repo_path(print_layout_stl),
        "print_layout_3mf": repo_path(print_layout_3mf),
        "pcb_proxy_step": repo_path(pcb_step),
        "pcb_proxy_stl": repo_path(pcb_stl),
        "assembly_step": repo_path(assembly_step),
        "assembly_stl": repo_path(assembly_stl),
        "top_alignment_svg": repo_path(alignment_svg),
        "top_alignment_png": repo_path(alignment_png) if alignment_png.exists() else "",
        "pcb_geometry_json": repo_path(geometry_json),
        "use_this_step": repo_path(use_this_step),
        "print_this_step": repo_path(print_this_step),
        "print_this_stl": repo_path(print_this_stl),
        "print_this_3mf": repo_path(print_this_3mf),
        "manifest": repo_path(manifest),
        "nutstore_print_ready_folder": str(NUTSTORE_DIR),
    }
    checks = {
        "holder_stl": mesh_checks(holder_stl),
        "print_layout_stl": mesh_checks(print_layout_stl),
        "print_layout_3mf_entries": validate_3mf(print_layout_3mf),
    }
    write_manifest(manifest, geometry, outputs, checks)
    write_readme(DESIGN_DIR / "README.md", geometry, outputs)
    sync_print_ready([print_this_step, print_this_stl, print_this_3mf, alignment_png, DESIGN_DIR / "README.md", manifest])

    print(json.dumps({"geometry": geometry, "outputs": outputs, "validation": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
