#!/usr/bin/env python3
"""Build a Lumileds 30 mm cage holder with right-angle 2P header clearance."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cadquery as cq

try:
    import cairosvg  # type: ignore
except Exception:  # The CadQuery env may not include CairoSVG; system Python usually does.
    cairosvg = None


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"


PARAMS = {
    "name": "lumileds_hengyang_30mm_cage_holder_2p_right_angle",
    "reference_family": "Hengyang Optics 30 mm cage components",
    "primary_reference": "GT-090101",
    "reference_folder": "cad/references/hengyang-optics",
    "openhi_led_holder_reference": "cad/extracted/OpenHI_STEP/LED holder.step",
    "openhi_led_holder_observation": (
        "Imported OpenHI LED holder is about 30.0 x 11.6 x 30.0 mm with a 10 mm main body, "
        "a 1.6 mm LED board layer, four about 1.8 mm mount holes, and two about 2.0 mm pin holes "
        "on 2.54 mm pitch."
    ),
    "body_width_mm": 40.0,
    "body_height_mm": 41.5,
    "body_thickness_mm": 11.0,
    "front_lip_depth_mm": 1.2,
    "front_lip_diameter_mm": 17.0,
    "corner_radius_mm": 2.0,
    "cage_rod_pitch_mm": 30.0,
    "cage_rod_clearance_diameter_mm": 6.35,
    "rod_boss_diameter_mm": 9.6,
    "light_aperture_diameter_mm": 9.6,
    "pcb_outer_diameter_mm": 24.0,
    "pcb_pocket_diameter_mm": 24.7,
    "pcb_pocket_depth_mm": 2.05,
    "pcb_thickness_mm": 1.6,
    "pcb_mount_pattern_mm": 12.0,
    "pcb_mount_hole_diameter_mm": 2.35,
    "pcb_mount_counterbore_diameter_mm": 4.8,
    "pcb_mount_counterbore_depth_mm": 2.1,
    "right_angle_header_pin_x_mm": 10.2,
    "right_angle_header_pin_pair_center_y_mm": -1.25,
    "right_angle_header_pin_pitch_mm": 2.54,
    "right_angle_header_nominal_pin_hole_diameter_mm": 2.0,
    "right_angle_header_pin_hole_diameter_add_mm": 0.4,
    "right_angle_header_pin_relief_diameter_mm": 2.4,
    "right_angle_header_front_popup_relief_diameter_mm": 3.2,
    "right_angle_header_front_popup_relief_depth_mm": 2.2,
    "right_angle_header_body_clearance_reach_mm": 17.5,
    "right_angle_header_body_clearance_width_mm": 8.8,
    "right_angle_header_body_clearance_height_mm": 6.8,
    "dupont_plug_clearance_reach_mm": 24.0,
    "dupont_plug_clearance_width_mm": 10.0,
    "dupont_plug_clearance_height_mm": 8.8,
    "dupont_wire_exit_channel_width_mm": 12.0,
    "dupont_wire_exit_channel_height_mm": 5.4,
    "m3_pilot_hole_diameter_mm": 2.6,
    "m3_pilot_depth_mm": 6.0,
    "m3_pilot_note": "M3 pilot/tapping hole, intentionally smaller than 3.0 mm; tune after print or tap/heat-set.",
    "print_clearance_note": (
        "Pin relief holes use nominal 2.0 mm plus 0.4 mm diameter clearance, following the OpenHI LED holder pattern."
    ),
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z_min).circle(diameter / 2).extrude(height)


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def x_cylinder(diameter: float, length: float, x_min: float, y: float, z: float) -> cq.Workplane:
    return cq.Workplane("YZ").workplane(offset=x_min).circle(diameter / 2).extrude(length).translate((0, y, z))


def pin_points() -> list[tuple[float, float]]:
    p = PARAMS
    half_pitch = p["right_angle_header_pin_pitch_mm"] / 2.0
    x = p["right_angle_header_pin_x_mm"]
    y0 = p["right_angle_header_pin_pair_center_y_mm"]
    return [(x, y0 - half_pitch), (x, y0 + half_pitch)]


def build_holder() -> cq.Workplane:
    p = PARAMS
    width = p["body_width_mm"]
    height = p["body_height_mm"]
    thickness = p["body_thickness_mm"]
    half_t = thickness / 2.0

    holder = cq.Workplane("XY").box(width, height, thickness)
    holder = holder.edges("|Z").fillet(p["corner_radius_mm"])

    cut_height = thickness + 2.0
    z_min = -half_t - 1.0
    rod_half = p["cage_rod_pitch_mm"] / 2.0
    rod_points = [(x, y) for x in (-rod_half, rod_half) for y in (-rod_half, rod_half)]

    corner_keep = p["rod_boss_diameter_mm"] / 2.0 + 1.8
    relief_w = (width - p["cage_rod_pitch_mm"]) - corner_keep
    relief_h = 6.2
    for y in (-rod_half, rod_half):
        holder = holder.cut(z_box((max(relief_w, 3.0), relief_h, cut_height), (0, y, 0)))
    for x in (-rod_half, rod_half):
        holder = holder.cut(z_box((relief_h, max(height - p["cage_rod_pitch_mm"] - corner_keep, 3.0), cut_height), (x, 0, 0)))

    for x, y in rod_points:
        holder = holder.cut(z_cylinder(p["cage_rod_clearance_diameter_mm"], cut_height, z_min).translate((x, y, 0)))

    holder = holder.cut(z_cylinder(p["light_aperture_diameter_mm"], cut_height, z_min))
    holder = holder.faces(">Z").workplane().hole(p["front_lip_diameter_mm"], p["front_lip_depth_mm"])
    holder = holder.cut(z_cylinder(p["pcb_pocket_diameter_mm"], p["pcb_pocket_depth_mm"], -half_t - 0.01))

    mount_half = p["pcb_mount_pattern_mm"] / 2.0
    mount_points = [(x, y) for x in (-mount_half, mount_half) for y in (-mount_half, mount_half)]
    for x, y in mount_points:
        holder = holder.cut(z_cylinder(p["pcb_mount_hole_diameter_mm"], cut_height, z_min).translate((x, y, 0)))
        holder = holder.cut(
            z_cylinder(
                p["pcb_mount_counterbore_diameter_mm"],
                p["pcb_mount_counterbore_depth_mm"],
                -half_t - 0.01,
            ).translate((x, y, 0))
        )

    # Open rear/right pocket for the 90-degree 2P pin header body.
    y0 = p["right_angle_header_pin_pair_center_y_mm"]
    header_reach = p["right_angle_header_body_clearance_reach_mm"]
    holder = holder.cut(
        z_box(
            (
                header_reach,
                p["right_angle_header_body_clearance_width_mm"],
                p["right_angle_header_body_clearance_height_mm"],
            ),
            (
                width / 2.0 - header_reach / 2.0,
                y0,
                -half_t + p["right_angle_header_body_clearance_height_mm"] / 2.0 - 0.02,
            ),
        )
    )

    # Larger path for a female Dupont 2P plug and the wire bend leaving the side.
    plug_reach = p["dupont_plug_clearance_reach_mm"]
    holder = holder.cut(
        z_box(
            (
                plug_reach,
                p["dupont_plug_clearance_width_mm"],
                p["dupont_plug_clearance_height_mm"],
            ),
            (
                width / 2.0 - plug_reach / 2.0,
                y0,
                -half_t + p["dupont_plug_clearance_height_mm"] / 2.0 - 0.04,
            ),
        )
    )
    holder = holder.cut(
        z_box(
            (
                7.5,
                p["dupont_wire_exit_channel_width_mm"],
                p["dupont_wire_exit_channel_height_mm"],
            ),
            (
                width / 2.0 - 7.5 / 2.0,
                y0,
                -half_t + p["dupont_wire_exit_channel_height_mm"] / 2.0 - 0.05,
            ),
        )
    )

    # Two through-relief holes for pin/solder protrusions on the LED/front side.
    for x, y in pin_points():
        holder = holder.cut(z_cylinder(p["right_angle_header_pin_relief_diameter_mm"], cut_height, z_min).translate((x, y, 0)))
        holder = holder.cut(
            z_cylinder(
                p["right_angle_header_front_popup_relief_diameter_mm"],
                p["right_angle_header_front_popup_relief_depth_mm"] + 0.1,
                half_t - p["right_angle_header_front_popup_relief_depth_mm"],
            ).translate((x, y, 0))
        )

    # Optional M3 pilot from the lower side. This is not a 3.0 mm clearance hole.
    holder = holder.cut(
        cq.Workplane("XZ")
        .workplane(offset=-height / 2.0 - 0.01)
        .center(0, 0)
        .circle(p["m3_pilot_hole_diameter_mm"] / 2.0)
        .extrude(p["m3_pilot_depth_mm"])
    )

    return holder


def build_pcb_proxy() -> cq.Workplane:
    p = PARAMS
    half_t = p["body_thickness_mm"] / 2.0
    pcb_center_z = -half_t + p["pcb_pocket_depth_mm"] - p["pcb_thickness_mm"] / 2.0
    pcb = cq.Workplane("XY").workplane(offset=pcb_center_z - p["pcb_thickness_mm"] / 2.0)
    pcb = pcb.circle(p["pcb_outer_diameter_mm"] / 2.0).extrude(p["pcb_thickness_mm"])
    pcb = pcb.faces(">Z").workplane().circle(2.5).extrude(0.7)
    mount_half = p["pcb_mount_pattern_mm"] / 2.0
    for x in (-mount_half, mount_half):
        for y in (-mount_half, mount_half):
            pcb = pcb.cut(z_cylinder(2.2, p["pcb_thickness_mm"] + 1.0, pcb_center_z - p["pcb_thickness_mm"] / 2.0 - 0.2).translate((x, y, 0)))
    for x, y in pin_points():
        pcb = pcb.cut(
            z_cylinder(
                p["right_angle_header_nominal_pin_hole_diameter_mm"],
                p["pcb_thickness_mm"] + 1.0,
                pcb_center_z - p["pcb_thickness_mm"] / 2.0 - 0.2,
            ).translate((x, y, 0))
        )
    return pcb


def build_header_proxy_parts() -> list[tuple[str, cq.Workplane, cq.Color]]:
    p = PARAMS
    width = p["body_width_mm"]
    half_t = p["body_thickness_mm"] / 2.0
    pcb_center_z = -half_t + p["pcb_pocket_depth_mm"] - p["pcb_thickness_mm"] / 2.0
    y0 = p["right_angle_header_pin_pair_center_y_mm"]
    pin_z = pcb_center_z + 0.35

    parts: list[tuple[str, cq.Workplane, cq.Color]] = []
    plastic = z_box((4.4, 5.8, 2.8), (12.7, y0, pcb_center_z - 0.6))
    dupont = z_box((12.0, 6.3, 5.2), (width / 2.0 + 5.8, y0, pcb_center_z - 0.25))
    parts.append(("right_angle_2p_header_plastic_proxy", plastic, cq.Color(0.02, 0.02, 0.02, 1.0)))
    parts.append(("female_dupont_2p_plug_proxy", dupont, cq.Color(0.03, 0.03, 0.035, 0.82)))

    for idx, (x, y) in enumerate(pin_points(), start=1):
        vertical_pin = z_cylinder(0.65, 8.4, pcb_center_z - 2.0).translate((x, y, 0))
        horizontal_pin = z_box((10.5, 0.65, 0.65), (17.1, y, pin_z))
        wire = x_cylinder(0.9, 18.0, width / 2.0 + 10.5, y, pin_z)
        parts.append((f"pin_{idx}_front_popup_proxy", vertical_pin, cq.Color(0.95, 0.63, 0.22, 1.0)))
        parts.append((f"pin_{idx}_right_angle_leg_proxy", horizontal_pin, cq.Color(0.95, 0.63, 0.22, 1.0)))
        parts.append((f"dupont_wire_{idx}_proxy", wire, cq.Color(0.8 if idx == 1 else 0.05, 0.05, 0.05 if idx == 1 else 0.8, 1.0)))
    return parts


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name="lumileds_hengyang_30mm_cage_holder_2p_right_angle_assembly")
    assembly.add(build_holder(), name="printed_holder_with_2p_header_clearance", color=cq.Color(0.02, 0.02, 0.02, 1.0))
    assembly.add(build_pcb_proxy(), name="lumileds_pcb_proxy_with_2p_holes", color=cq.Color(0.0, 0.45, 0.12, 0.75))
    for name, part, color in build_header_proxy_parts():
        assembly.add(part, name=name, color=color)
    return assembly


def write_dimension_svg(path: Path) -> None:
    p = PARAMS
    scale = 9
    pad = 48
    w = p["body_width_mm"]
    h = p["body_height_mm"]
    svg_w = int(w * scale + pad * 2 + 390)
    svg_h = int(h * scale + pad * 2 + 170)

    def sx(x: float) -> float:
        return pad + (x + w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (h / 2.0 - y) * scale

    rod_half = p["cage_rod_pitch_mm"] / 2.0
    mount_half = p["pcb_mount_pattern_mm"] / 2.0
    y0 = p["right_angle_header_pin_pair_center_y_mm"]
    plug_reach = p["dupont_plug_clearance_reach_mm"]
    plug_width = p["dupont_plug_clearance_width_mm"]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-w/2)}" y="{sy(h/2)}" width="{w*scale}" height="{h*scale}" rx="{p["corner_radius_mm"]*scale}" fill="#151515" stroke="#333" stroke-width="2"/>',
        f'<circle cx="{sx(0)}" cy="{sy(0)}" r="{p["pcb_pocket_diameter_mm"]/2*scale}" fill="none" stroke="#48bb78" stroke-width="2" stroke-dasharray="7 4"/>',
        f'<circle cx="{sx(0)}" cy="{sy(0)}" r="{p["light_aperture_diameter_mm"]/2*scale}" fill="white" stroke="#edf2f7" stroke-width="2"/>',
        f'<rect x="{sx(w/2-plug_reach)}" y="{sy(y0+plug_width/2)}" width="{plug_reach*scale}" height="{plug_width*scale}" fill="#805ad5" opacity="0.38" stroke="#553c9a" stroke-width="2"/>',
    ]
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            lines.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{p["cage_rod_clearance_diameter_mm"]/2*scale}" fill="#eef6ff" stroke="#63b3ed" stroke-width="2"/>')
    for x in (-mount_half, mount_half):
        for y in (-mount_half, mount_half):
            lines.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{p["pcb_mount_hole_diameter_mm"]/2*scale}" fill="#fff7bf" stroke="#d69e2e" stroke-width="2"/>')
    for x, y in pin_points():
        lines.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{p["right_angle_header_pin_relief_diameter_mm"]/2*scale}" fill="#fed7d7" stroke="#e53e3e" stroke-width="2"/>')
        lines.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{p["right_angle_header_front_popup_relief_diameter_mm"]/2*scale}" fill="none" stroke="#f56565" stroke-width="2" stroke-dasharray="4 3"/>')

    legend_x = int(w * scale + pad + 36)
    legend_y = pad
    text = [
        "Lumileds holder - 2P right-angle header variant",
        f"Envelope: {w} x {h} x {p['body_thickness_mm']} mm",
        f"Cage rods: 30 mm pitch, D{p['cage_rod_clearance_diameter_mm']} clearance",
        f"Pin holes: D{p['right_angle_header_pin_relief_diameter_mm']} mm = D2.0 + 0.4 print clearance",
        f"Pin pitch: {p['right_angle_header_pin_pitch_mm']} mm; front popup relief D{p['right_angle_header_front_popup_relief_diameter_mm']} mm",
        f"Dupont/header pocket: {plug_reach} x {plug_width} mm in plan",
        f"M3 pilot: D{p['m3_pilot_hole_diameter_mm']} mm, not a loose D3.0 mm clearance",
        "OpenHI LED holder reference: two D2.0-ish pin holes on 2.54 mm pitch",
    ]
    for i, row in enumerate(text):
        size = 17 if i == 0 else 13
        weight = "700" if i == 0 else "400"
        lines.append(f'<text x="{legend_x}" y="{legend_y + i*25}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    path.write_text(
        f"""# Lumileds Hengyang 30 mm Cage Holder With 2P Right-Angle Header Clearance

This is a new independent sibling of `cad/designs/lumileds_hengyang_30mm_cage_holder`.
The old design is not edited. This version keeps the same Hengyang-style 30 mm
cage interface and adds explicit clearance for a 2P right-angle pin header,
front-side pin/solder protrusions, a female Dupont plug, and wire exit.

## Design Intent

- Keep the GT-090101/Hengyang-compatible four-rod 30 mm cage interface.
- Keep the Lumileds round PCB rear pocket and M2-style PCB mounting holes.
- Add two 2.54 mm pitch pin-relief holes near the PCB edge.
- Add `+0.4 mm` diameter print clearance to the pin holes: nominal `2.0 mm`
  becomes `{PARAMS['right_angle_header_pin_relief_diameter_mm']} mm`.
- Add front/LED-side popup relief so solder or header pin tips do not collide
  with the holder face.
- Add a larger rear/right-side open pocket for the 90-degree header body,
  female Dupont 2P plug, and wire bend.
- Use a `{PARAMS['m3_pilot_hole_diameter_mm']} mm` M3 pilot hole, not a loose
  3.0 mm M3 clearance hole.

## OpenHI Reference Used

`{PARAMS['openhi_led_holder_reference']}` was imported with CadQuery. It measures
about `30.0 x 11.6 x 30.0 mm` and has two solids: a `10 mm` body and a `1.6 mm`
LED-board layer. Cylindrical face inspection shows four about `1.8 mm` mount
holes and two about `2.0 mm` pin holes separated by about `2.54 mm`. This new
holder applies the same pin-hole idea but adds the requested `0.4 mm` diameter
clearance for printing.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{rows}

## Notes

- The purple rectangle in the dimension sketch is the right-side Dupont/header
  clearance pocket in top view.
- Red circles are the two pin-relief holes and the dashed red circles are the
  larger front-side popup relief pockets.
- The STEP/STL `holder` files contain only the printable holder. The `assembly`
  files include PCB/header/Dupont/wire proxies for fit checking.
- Print one prototype and tune pin-hole/header pocket clearance from that first
  fit test before machining or ordering.
""",
        encoding="utf-8",
    )


def convert_svg_outputs(svg_path: Path, png_path: Path, pdf_path: Path) -> None:
    if cairosvg is not None:
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=1800)
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        return
    code = (
        "import cairosvg, sys; "
        "cairosvg.svg2png(url=sys.argv[1], write_to=sys.argv[2], output_width=1800); "
        "cairosvg.svg2pdf(url=sys.argv[1], write_to=sys.argv[3])"
    )
    candidates = [
        Path("/home/lachlan/miniconda3/bin/python3"),
        Path("/usr/bin/python3"),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            subprocess.run([str(candidate), "-c", code, str(svg_path), str(png_path), str(pdf_path)], check=True)
            return
        except subprocess.CalledProcessError:
            continue
    print("warning: CairoSVG conversion unavailable; SVG sketch was written but PNG/PDF were skipped")


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    holder = build_holder()
    assembly = build_assembly()

    stem = PARAMS["name"]
    holder_step = ARTIFACT_DIR / f"{stem}.step"
    holder_stl = ARTIFACT_DIR / f"{stem}.stl"
    assembly_step = ARTIFACT_DIR / f"{stem}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{stem}_assembly.stl"
    sketch_svg = ARTIFACT_DIR / f"{stem}_dimension_sketch.svg"
    sketch_png = ARTIFACT_DIR / f"{stem}_dimension_sketch.png"
    sketch_pdf = ARTIFACT_DIR / f"{stem}_dimension_sketch.pdf"
    render_png = ARTIFACT_DIR / f"{stem}_rear_dupont_render.png"
    front_render_png = ARTIFACT_DIR / f"{stem}_front_pin_relief_render.png"
    blend_file = ARTIFACT_DIR / f"{stem}.blend"

    cq.exporters.export(holder, str(holder_step))
    cq.exporters.export(holder, str(holder_stl))
    assembly_compound = assembly.toCompound()
    cq.exporters.export(assembly_compound, str(assembly_step))
    cq.exporters.export(assembly_compound, str(assembly_stl))
    write_dimension_svg(sketch_svg)
    convert_svg_outputs(sketch_svg, sketch_png, sketch_pdf)

    outputs = {
        "holder STEP": repo_path(holder_step),
        "holder STL": repo_path(holder_stl),
        "assembly STEP": repo_path(assembly_step),
        "assembly STL": repo_path(assembly_stl),
        "dimension sketch SVG": repo_path(sketch_svg),
        "dimension sketch PNG": repo_path(sketch_png),
        "dimension sketch PDF": repo_path(sketch_pdf),
        "rear Dupont/header render PNG": repo_path(render_png),
        "front pin-relief render PNG": repo_path(front_render_png),
        "Blender inspection scene": repo_path(blend_file),
    }
    (ARTIFACT_DIR / "manifest.json").write_text(
        json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_readme(DESIGN_DIR / "README.md", outputs)
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
