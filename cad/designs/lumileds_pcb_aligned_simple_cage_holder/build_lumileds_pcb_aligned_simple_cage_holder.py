#!/usr/bin/env python3
"""Build a simple PCB-derived Lumileds cage holder.

This version intentionally avoids the earlier counterbores, pockets, bottom
pilots, relief slots, and fragmented lightening cuts. The holder is a single
centered block whose holes are copied from the Lumileds PCB geometry.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "lumileds_pcb_aligned_simple_cage_holder"
SOURCE_PCB = ROOT / "pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb"


PARAMS = {
    "name": STEM,
    "source_pcb": "pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb",
    "body_width_mm": 42.0,
    "body_height_mm": 42.0,
    "body_thickness_mm": 8.0,
    "edge_fillet_mm": 0.8,
    "cage_rod_pitch_mm": 30.0,
    "cage_rod_clearance_diameter_mm": 6.4,
    "pcb_mount_clearance_diameter_mm": 2.4,
    "header_pin_relief_diameter_mm": 1.6,
    "led_aperture_diameter_mm": 10.0,
    "pcb_thickness_mm": 1.6,
    "pcb_mount_note": "No counterbore and no pocket: the PCB sits flat on the rear face and is located by four M2 holes.",
    "coordinate_rule": "PCB center is translated to holder origin. Every PCB-derived hole is stored relative to that center.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


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
    return {
        "source_pcb": repo_path(path),
        "pcb_center_kicad_mm": {"x": cx, "y": cy},
        "pcb_outer_diameter_mm": round(radius * 2.0, 4),
        "pcb_radius_mm": round(radius, 4),
        "led_center_relative_mm": led_center,
        "mounting_holes_relative_mm": mounting_holes,
        "header_pins_relative_mm": header_pins,
    }


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(float(diameter) / 2.0).extrude(float(height))


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


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

    for pin in geometry["header_pins_relative_mm"]:  # type: ignore[index]
        holder = holder.cut(
            z_cylinder(p["header_pin_relief_diameter_mm"], cut_height, z_min).translate((pin["x"], pin["y"], 0))
        )

    return holder


def build_pcb_proxy(geometry: dict[str, object]) -> cq.Workplane:
    p = PARAMS
    thickness = p["pcb_thickness_mm"]
    rear_face_z = -p["body_thickness_mm"] / 2.0
    pcb_z_min = rear_face_z - thickness
    pcb = z_cylinder(geometry["pcb_outer_diameter_mm"], thickness, pcb_z_min)  # type: ignore[arg-type]
    for hole in geometry["mounting_holes_relative_mm"]:  # type: ignore[index]
        pcb = pcb.cut(z_cylinder(hole["drill_mm"], thickness + 0.4, pcb_z_min - 0.2).translate((hole["x"], hole["y"], 0)))
    for pin in geometry["header_pins_relative_mm"]:  # type: ignore[index]
        pcb = pcb.cut(z_cylinder(pin["drill_mm"], thickness + 0.4, pcb_z_min - 0.2).translate((pin["x"], pin["y"], 0)))
    return pcb


def build_led_proxy(geometry: dict[str, object]) -> cq.Workplane:
    rear_face_z = -PARAMS["body_thickness_mm"] / 2.0
    led = geometry["led_center_relative_mm"]  # type: ignore[index]
    return z_cylinder(4.8, 0.75, rear_face_z - 0.02).translate((led["x"], led["y"], 0))


def build_header_proxy(geometry: dict[str, object]) -> cq.Workplane:
    p = PARAMS
    rear_face_z = -p["body_thickness_mm"] / 2.0
    pins = geometry["header_pins_relative_mm"]  # type: ignore[index]
    y_mid = sum(pin["y"] for pin in pins) / len(pins)
    x_mid = sum(pin["x"] for pin in pins) / len(pins)
    body = z_box((5.2, 6.4, 2.5), (x_mid + 2.2, y_mid, rear_face_z - p["pcb_thickness_mm"] - 1.25))
    for pin in pins:
        body = body.union(
            z_cylinder(0.72, p["body_thickness_mm"] + p["pcb_thickness_mm"] + 0.8, -p["body_thickness_mm"] / 2.0 - p["pcb_thickness_mm"] - 0.2)
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
    assembly.add(build_holder(geometry), name="single_piece_holder", color=cq.Color(0.08, 0.08, 0.08, 1.0))
    assembly.add(build_pcb_proxy(geometry), name="pcb_proxy_from_kicad_geometry", color=cq.Color(0.0, 0.45, 0.12, 0.72))
    assembly.add(build_led_proxy(geometry), name="led_emitter_proxy", color=cq.Color(1.0, 0.82, 0.18, 1.0))
    assembly.add(build_header_proxy(geometry), name="right_angle_2p_header_proxy", color=cq.Color(0.02, 0.02, 0.02, 1.0))
    assembly.add(build_alignment_rods(), name="30mm_cage_rod_alignment_proxy", color=cq.Color(0.2, 0.55, 0.9, 0.45))
    return assembly


def write_alignment_svg(path: Path, geometry: dict[str, object]) -> None:
    p = PARAMS
    scale = 9.0
    pad = 54.0
    legend_w = 410
    w = p["body_width_mm"]
    h = p["body_height_mm"]
    svg_w = int(w * scale + pad * 2 + legend_w)
    svg_h = int(h * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (h / 2.0 - y) * scale

    def circle(x: float, y: float, d: float, fill: str, stroke: str, label: str = "") -> str:
        label_svg = ""
        if label:
            label_svg = f'<text x="{sx(x)+6}" y="{sy(y)-6}" font-family="Arial" font-size="11" fill="#1a202c">{label}</text>'
        return (
            f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{d/2*scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            + label_svg
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-w/2):.2f}" y="{sy(h/2):.2f}" width="{w*scale:.2f}" height="{h*scale:.2f}" rx="{p["edge_fillet_mm"]*scale:.2f}" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        f'<circle cx="{sx(0):.2f}" cy="{sy(0):.2f}" r="{geometry["pcb_outer_diameter_mm"]/2*scale:.2f}" fill="none" stroke="#38a169" stroke-width="2" stroke-dasharray="7 5"/>',
        '<line x1="{0:.2f}" y1="{1:.2f}" x2="{2:.2f}" y2="{1:.2f}" stroke="#cbd5e0" stroke-width="1"/>'.format(sx(-w/2), sy(0), sx(w/2)),
        '<line x1="{0:.2f}" y1="{1:.2f}" x2="{0:.2f}" y2="{2:.2f}" stroke="#cbd5e0" stroke-width="1"/>'.format(sx(0), sy(h/2), sy(-h/2)),
    ]
    rod_half = p["cage_rod_pitch_mm"] / 2.0
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            lines.append(circle(x, y, p["cage_rod_clearance_diameter_mm"], "#ebf8ff", "#3182ce"))
    led = geometry["led_center_relative_mm"]  # type: ignore[index]
    lines.append(circle(led["x"], led["y"], p["led_aperture_diameter_mm"], "#fffaf0", "#dd6b20", "LED aperture"))
    for idx, hole in enumerate(geometry["mounting_holes_relative_mm"], start=1):  # type: ignore[index]
        lines.append(circle(hole["x"], hole["y"], p["pcb_mount_clearance_diameter_mm"], "#fefcbf", "#b7791f", f"M2 {idx}"))
    for pin in geometry["header_pins_relative_mm"]:  # type: ignore[index]
        lines.append(circle(pin["x"], pin["y"], p["header_pin_relief_diameter_mm"], "#fed7d7", "#c53030", f"J1-{pin['name']}"))

    legend_x = pad + w * scale + 34
    legend = [
        "Lumileds simple aligned holder",
        f"One body: {w} x {h} x {p['body_thickness_mm']} mm",
        f"PCB: dia {geometry['pcb_outer_diameter_mm']} mm, centered at origin",
        "PCB M2 holes: copied from KiCad, +/-6 mm",
        f"Cage rods: 30 mm pitch, dia {p['cage_rod_clearance_diameter_mm']} mm",
        "No counterbore, no recessed pocket, no bottom pilot",
        "PCB sits flat on rear face; holes do the alignment",
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
    center = geometry["pcb_center_kicad_mm"]  # type: ignore[index]
    led = geometry["led_center_relative_mm"]  # type: ignore[index]
    center_text = f"({center['x']}, {center['y']}) mm"
    led_text = f"({led['x']}, {led['y']}) mm from {led['source']}"
    mount_rows = "\n".join(
        f"| {i} | `{hole['x']}` | `{hole['y']}` | `{hole['drill_mm']}` |"
        for i, hole in enumerate(geometry["mounting_holes_relative_mm"], start=1)  # type: ignore[index]
    )
    pin_rows = "\n".join(
        f"| J1-{pin['name']} | `{pin['x']}` | `{pin['y']}` | `{pin['drill_mm']}` |"
        for pin in geometry["header_pins_relative_mm"]  # type: ignore[index]
    )
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# Lumileds PCB-Aligned Simple Cage Holder

This is a fourth, simplified replacement candidate for the earlier Lumileds
cage holder attempts. The three older designs are left untouched.

## Design Rule

Use the PCB as the source of truth. The KiCad board center is translated to the
holder origin, then the holder holes are copied from the PCB. The part is one
monolithic centered plate with through-holes only.

No counterbores. No recessed PCB pocket. No bottom post hole. No lightening
cutouts. The PCB sits flat on the rear face and is aligned by screws.

## PCB Geometry Used

- Source PCB: `{geometry['source_pcb']}`
- KiCad board center: `{center_text}`
- PCB outer diameter: `{geometry['pcb_outer_diameter_mm']} mm`
- LED center relative to holder: `{led_text}`

PCB mounting holes relative to the holder origin:

| # | x mm | y mm | source drill mm |
| --- | ---: | ---: | ---: |
{mount_rows}

Header pin holes from the KiCad right-angle 2P header:

| Pin | x mm | y mm | source drill mm |
| --- | ---: | ---: | ---: |
{pin_rows}

## Holder Geometry

- Body: `{PARAMS['body_width_mm']} x {PARAMS['body_height_mm']} x {PARAMS['body_thickness_mm']} mm`.
- 30 mm cage rod holes: centered at `(+/-15, +/-15)` with `{PARAMS['cage_rod_clearance_diameter_mm']} mm` through clearance.
- PCB M2 holes: copied from KiCad and opened to `{PARAMS['pcb_mount_clearance_diameter_mm']} mm`.
- Header pin relief holes: copied from KiCad and opened to `{PARAMS['header_pin_relief_diameter_mm']} mm`.
- LED aperture: `{PARAMS['led_aperture_diameter_mm']} mm`, centered on the KiCad LED footprint.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}

## Notes

- This model is intentionally plain so the physical alignment can be checked
  before adding any nicer clamps, pockets, cable reliefs, or screw-head
  features.
- If the first print is too tight, change only the relevant clearance diameter
  in the script and rebuild.
- The assembly files include PCB, LED, header, and cage-rod proxies only for fit
  checking. The holder-only STEP/STL files are the printable part.
""",
        encoding="utf-8",
    )


def write_manifest(path: Path, geometry: dict[str, object], outputs: dict[str, str]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": "Simple monolithic PCB-aligned holder with through-holes only.",
        "parameters": PARAMS,
        "pcb_geometry": geometry,
        "outputs": outputs,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def svg_to_png(svg: Path, png: Path) -> None:
    if subprocess.run(["which", "convert"], capture_output=True, text=True).returncode != 0:
        return
    subprocess.run(["convert", str(svg), str(png)], check=True)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    geometry = extract_pcb_geometry(SOURCE_PCB)

    holder = build_holder(geometry)
    assembly = build_assembly(geometry)
    assembly_compound = assembly.toCompound()

    holder_step = ARTIFACT_DIR / f"{STEM}.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}.stl"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    alignment_svg = ARTIFACT_DIR / f"{STEM}_top_alignment.svg"
    alignment_png = ARTIFACT_DIR / f"{STEM}_top_alignment.png"
    geometry_json = ARTIFACT_DIR / f"{STEM}_pcb_geometry.json"
    manifest = ARTIFACT_DIR / "manifest.json"

    exporters.export(holder, str(holder_step))
    exporters.export(holder, str(holder_stl))
    exporters.export(assembly_compound, str(assembly_step))
    exporters.export(assembly_compound, str(assembly_stl))
    write_alignment_svg(alignment_svg, geometry)
    svg_to_png(alignment_svg, alignment_png)
    geometry_json.write_text(json.dumps(geometry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    outputs = {
        "holder_step": repo_path(holder_step),
        "holder_stl": repo_path(holder_stl),
        "assembly_step": repo_path(assembly_step),
        "assembly_stl": repo_path(assembly_stl),
        "top_alignment_svg": repo_path(alignment_svg),
        "top_alignment_png": repo_path(alignment_png) if alignment_png.exists() else "",
        "pcb_geometry_json": repo_path(geometry_json),
        "manifest": repo_path(manifest),
    }
    write_manifest(manifest, geometry, outputs)
    write_readme(DESIGN_DIR / "README.md", geometry, outputs)

    print(json.dumps({"geometry": geometry, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
