#!/usr/bin/env python3
"""Build a clean Lumileds cage holder with a simple PCB-thickness sink.

This is a sibling of `lumileds_pcb_aligned_simple_cage_holder`. It keeps the
same centered 42 mm plate and PCB-derived hole layout, then adds one rear
circular sink for the 24 mm Lumileds PCB. The sink depth equals the PCB
thickness so the board can sit flush in the holder.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "lumileds_pcb_aligned_sink_cage_holder"
SOURCE_PCB = ROOT / "pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb"
BASE_SCRIPT = ROOT / "cad/designs/lumileds_pcb_aligned_simple_cage_holder/build_lumileds_pcb_aligned_simple_cage_holder.py"


def load_base_module():
    spec = importlib.util.spec_from_file_location("lumileds_simple_base", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load base holder script: {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_base_module()


PARAMS = {
    "name": STEM,
    "source_pcb": "pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb",
    "base_design": "cad/designs/lumileds_pcb_aligned_simple_cage_holder",
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
    "pcb_mount_clearance_diameter_mm": 2.4,
    "header_pin_relief_diameter_mm": 1.6,
    "led_aperture_diameter_mm": 10.0,
    "coordinate_rule": "PCB center is translated to holder origin. The rear PCB sink is concentric with the KiCad board outline.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return BASE.z_cylinder(diameter, height, z_min)


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return BASE.z_box(size, center)


def extract_pcb_geometry(path: Path) -> dict[str, object]:
    geometry = BASE.extract_pcb_geometry(path)
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

    for pin in geometry["header_pins_relative_mm"]:  # type: ignore[index]
        holder = holder.cut(
            z_cylinder(p["header_pin_relief_diameter_mm"], cut_height, z_min).translate((pin["x"], pin["y"], 0))
        )

    return holder


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
    for pin in geometry["header_pins_relative_mm"]:  # type: ignore[index]
        lines.append(circle(pin["x"], pin["y"], p["header_pin_relief_diameter_mm"], "#fed7d7", "#c53030"))

    legend_x = pad + w * scale + 34
    legend = [
        "Lumileds aligned holder with PCB sink",
        f"Body: {w} x {h} x {p['body_thickness_mm']} mm",
        f"PCB: dia {geometry['pcb_outer_diameter_mm']} mm, thickness {p['pcb_thickness_mm']} mm",
        f"Rear sink: dia {p['pcb_sink_diameter_mm']} mm, depth {p['pcb_sink_depth_mm']} mm",
        "PCB M2 holes: copied from KiCad, +/-6 mm",
        f"Cage rods: 30 mm pitch, dia {p['cage_rod_clearance_diameter_mm']} mm",
        "Only change from clean base: simple PCB-thickness sink",
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
It keeps the same clean monolithic holder geometry and adds only a rear PCB
sink.

## PCB Geometry Used

- Source PCB: `{geometry['source_pcb']}`
- PCB outer diameter: `{geometry['pcb_outer_diameter_mm']} mm`
- PCB thickness used for sink depth: `{PARAMS['pcb_thickness_mm']} mm`
- LED center: `{led_text}`
- Mount holes: `(+/-6, +/-6) mm`, opened to `{PARAMS['pcb_mount_clearance_diameter_mm']} mm`
- Header relief pins: `(10, 1)` and `(10, -1.54) mm`, opened to `{PARAMS['header_pin_relief_diameter_mm']} mm`

## Design Rule

Use the PCB as the source of truth. The KiCad board center is translated to the
holder origin. The rear circular sink is concentric with the 24 mm PCB outline,
opened to `{PARAMS['pcb_sink_diameter_mm']} mm`, and cut `{PARAMS['pcb_sink_depth_mm']} mm` deep.

The sink is the only functional change from the clean base holder.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}

## Notes

- Print/check the holder-only STEP/STL. The assembly STEP/STL includes PCB,
  LED, header, and cage-rod proxies only for fit checking.
- If the PCB is too tight, change `pcb_sink_diameter_mm`; keep the mount-hole
  coordinates unchanged.
""",
        encoding="utf-8",
    )


def write_manifest(path: Path, geometry: dict[str, object], outputs: dict[str, str]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": "Clean Lumileds holder with one rear PCB-thickness sink.",
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
    pcb = build_pcb_proxy(geometry)
    assembly = build_assembly(geometry).toCompound()

    holder_step = ARTIFACT_DIR / f"{STEM}.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}.stl"
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
    exporters.export(pcb, str(pcb_step))
    exporters.export(pcb, str(pcb_stl))
    exporters.export(assembly, str(assembly_step))
    exporters.export(assembly, str(assembly_stl))
    write_alignment_svg(alignment_svg, geometry)
    svg_to_png(alignment_svg, alignment_png)
    geometry_json.write_text(json.dumps(geometry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    outputs = {
        "holder_step": repo_path(holder_step),
        "holder_stl": repo_path(holder_stl),
        "pcb_proxy_step": repo_path(pcb_step),
        "pcb_proxy_stl": repo_path(pcb_stl),
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
