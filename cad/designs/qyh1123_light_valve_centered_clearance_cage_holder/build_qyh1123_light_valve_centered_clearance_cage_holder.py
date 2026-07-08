#!/usr/bin/env python3
"""Build a centered 30 mm cage holder for the QYH1123 LCD light valve.

This sibling variant keeps the clean cage-holder layout but removes the old
0.9 mm lateral body shift. The optical origin, cage center, LCD pocket center,
active aperture, and pin relief are all centered on the same datum. The LCD sink
also adds 0.1 mm clearance on each side relative to the previous aligned holder.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "qyh1123_light_valve_centered_clearance_cage_holder"


PARAMS = {
    "name": STEM,
    "reference_folder": "cad/references/qiyun-display-qyh1123-light-valve",
    "body_width_mm": 42.0,
    "body_height_mm": 42.0,
    "body_thickness_mm": 8.0,
    "edge_fillet_mm": 0.8,
    "cage_rod_pitch_mm": 30.0,
    "cage_rod_clearance_diameter_mm": 6.4,
    "valve_outer_width_mm": 18.0,
    "valve_outer_height_mm": 20.0,
    "valve_thickness_mm": 2.0,
    "valve_pocket_clearance_mm": 0.6,
    "valve_pocket_extra_clearance_each_side_from_previous_mm": 0.1,
    "valve_pocket_depth_mm": 2.2,
    "active_aperture_width_mm": 15.0,
    "active_aperture_height_mm": 15.0,
    "terrace_lip_per_side_mm": 1.0,
    "terrace_rule": "The full 18 x 20 mm LCD body sits in a 2.2 mm sink; the through-window is V.A. minus the terrace lip on each side.",
    "active_center_offset_from_valve_center_x_mm": 0.0,
    "active_center_offset_from_valve_center_y_mm": 0.0,
    "alignment_override": "Centered fit variant: LCD body, active aperture, pin pair, pin relief, and 30 mm cage datum all share x=0/y=0. This intentionally removes the prior -0.9 mm active-area offset assumption.",
    "pin_pitch_mm": 2.54,
    "pin_width_mm": 0.70,
    "pin_thickness_mm": 0.50,
    "pin_length_mm": 8.0,
    "pin_exit_relief_width_mm": 6.6,
    "pin_exit_relief_depth_mm": 2.7,
    "drawing_tolerance_mm": 0.2,
    "coordinate_rule": "Holder origin is the QYH1123 active aperture center, LCD body center, pin relief center, and 30 mm cage center.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(float(diameter) / 2.0).extrude(float(height))


def valve_center_xy() -> tuple[float, float]:
    """Return the physical glass body center in optical-origin coordinates."""
    return (
        -PARAMS["active_center_offset_from_valve_center_x_mm"],
        -PARAMS["active_center_offset_from_valve_center_y_mm"],
    )


def light_window_xy() -> tuple[float, float]:
    """Return the derived through-window size after the support terrace."""
    lip = PARAMS["terrace_lip_per_side_mm"]
    return (
        PARAMS["active_aperture_width_mm"] - 2.0 * lip,
        PARAMS["active_aperture_height_mm"] - 2.0 * lip,
    )


def build_holder() -> cq.Workplane:
    p = PARAMS
    holder = cq.Workplane("XY").box(p["body_width_mm"], p["body_height_mm"], p["body_thickness_mm"])
    if p["edge_fillet_mm"]:
        holder = holder.edges("|Z").fillet(p["edge_fillet_mm"])

    cut_height = p["body_thickness_mm"] + 1.2
    z_min = -p["body_thickness_mm"] / 2.0 - 0.6

    rod_half = p["cage_rod_pitch_mm"] / 2.0
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            holder = holder.cut(
                z_cylinder(p["cage_rod_clearance_diameter_mm"], cut_height, z_min).translate((x, y, 0))
            )

    light_w, light_h = light_window_xy()
    aperture = (light_w, light_h, cut_height)
    holder = holder.cut(z_box(aperture, (0, 0, 0)))

    front_z = p["body_thickness_mm"] / 2.0
    pocket_depth = p["valve_pocket_depth_mm"]
    pocket_z = front_z - pocket_depth / 2.0 + 0.04
    pocket_center_x, pocket_center_y = valve_center_xy()
    pocket = (
        p["valve_outer_width_mm"] + p["valve_pocket_clearance_mm"],
        p["valve_outer_height_mm"] + p["valve_pocket_clearance_mm"],
        pocket_depth + 0.1,
    )
    holder = holder.cut(z_box(pocket, (pocket_center_x, pocket_center_y, pocket_z)))

    # Bottom-edge shallow relief for the 2.54 mm pitch metal pin tails.
    valve_bottom_y = pocket_center_y - (p["valve_outer_height_mm"] + p["valve_pocket_clearance_mm"]) / 2.0
    relief_len = p["body_height_mm"] / 2.0 + valve_bottom_y + 0.35
    relief_center_y = valve_bottom_y - relief_len / 2.0 + 0.02
    relief = (
        p["pin_exit_relief_width_mm"],
        relief_len,
        p["pin_exit_relief_depth_mm"],
    )
    holder = holder.cut(z_box(relief, (0.0, relief_center_y, front_z - relief[2] / 2.0 + 0.04)))

    return holder


def build_valve_proxy() -> cq.Workplane:
    p = PARAMS
    x0, y0 = valve_center_xy()
    front_z = p["body_thickness_mm"] / 2.0
    glass_center_z = front_z - p["valve_pocket_depth_mm"] + p["valve_thickness_mm"] / 2.0 + 0.18
    valve = z_box((p["valve_outer_width_mm"], p["valve_outer_height_mm"], p["valve_thickness_mm"]), (x0, y0, glass_center_z))
    active = z_box(
        (p["active_aperture_width_mm"], p["active_aperture_height_mm"], 0.18),
        (0, 0, glass_center_z + p["valve_thickness_mm"] / 2.0 + 0.1),
    )
    valve = valve.union(active)

    pin_y0 = y0 - p["valve_outer_height_mm"] / 2.0 - p["pin_length_mm"] / 2.0
    pin_z = glass_center_z - p["valve_thickness_mm"] / 2.0 + p["pin_thickness_mm"] / 2.0
    for x in (x0 - p["pin_pitch_mm"] / 2.0, x0 + p["pin_pitch_mm"] / 2.0):
        valve = valve.union(z_box((p["pin_width_mm"], p["pin_length_mm"], p["pin_thickness_mm"]), (x, pin_y0, pin_z)))
    return valve


def build_cage_rods_proxy() -> cq.Workplane:
    p = PARAMS
    rod_half = p["cage_rod_pitch_mm"] / 2.0
    rods = None
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            rod = z_cylinder(5.9, p["body_thickness_mm"] + 5.0, -p["body_thickness_mm"] / 2.0 - 2.5).translate((x, y, 0))
            rods = rod if rods is None else rods.union(rod)
    assert rods is not None
    return rods


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_holder(), name="printable_qyh1123_holder", color=cq.Color(0.11, 0.11, 0.105, 1.0))
    assembly.add(build_valve_proxy(), name="qyh1123_valve_proxy_active_area_centered", color=cq.Color(0.30, 0.78, 0.92, 0.55))
    assembly.add(build_cage_rods_proxy(), name="30mm_cage_rod_alignment_proxy", color=cq.Color(0.16, 0.45, 0.92, 0.45))
    return assembly


def write_alignment_svg(path: Path) -> None:
    p = PARAMS
    scale = 9.2
    pad = 54.0
    legend_w = 480.0
    body_w = p["body_width_mm"]
    body_h = p["body_height_mm"]
    svg_w = int(body_w * scale + pad * 2 + legend_w)
    svg_h = int(body_h * scale + pad * 2)
    pocket_x, pocket_y = valve_center_xy()

    def sx(x: float) -> float:
        return pad + (x + body_w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (body_h / 2.0 - y) * scale

    def rect(cx: float, cy: float, w: float, h: float, fill: str, stroke: str, label: str = "", dash: str = "") -> str:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        label_svg = ""
        if label:
            label_svg = f'<text x="{sx(cx - w / 2):.2f}" y="{sy(cy + h / 2) - 8:.2f}" font-family="Arial" font-size="12" fill="#1a202c">{label}</text>'
        return (
            f'<rect x="{sx(cx - w / 2):.2f}" y="{sy(cy + h / 2):.2f}" width="{w*scale:.2f}" height="{h*scale:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"{dash_attr}/>'
            + label_svg
        )

    def circle(x: float, y: float, d: float, fill: str, stroke: str) -> str:
        return f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{d/2*scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        rect(0, 0, body_w, body_h, "#f7fafc", "#1a202c", "42 x 42 mm holder"),
        '<line x1="{0:.2f}" y1="{1:.2f}" x2="{2:.2f}" y2="{1:.2f}" stroke="#cbd5e0" stroke-width="1"/>'.format(sx(-body_w / 2), sy(0), sx(body_w / 2)),
        '<line x1="{0:.2f}" y1="{1:.2f}" x2="{0:.2f}" y2="{2:.2f}" stroke="#cbd5e0" stroke-width="1"/>'.format(sx(0), sy(body_h / 2), sy(-body_h / 2)),
    ]
    rod_half = p["cage_rod_pitch_mm"] / 2.0
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            lines.append(circle(x, y, p["cage_rod_clearance_diameter_mm"], "#ebf8ff", "#3182ce"))

    lines.append(rect(pocket_x, pocket_y, p["valve_outer_width_mm"] + p["valve_pocket_clearance_mm"], p["valve_outer_height_mm"] + p["valve_pocket_clearance_mm"], "#e6fffa", "#319795"))
    lines.append(rect(pocket_x, pocket_y, p["valve_outer_width_mm"], p["valve_outer_height_mm"], "none", "#2c7a7b", dash="6 4"))
    light_w, light_h = light_window_xy()
    lines.append(rect(0, 0, p["active_aperture_width_mm"], p["active_aperture_height_mm"], "none", "#718096", dash="5 4"))
    lines.append(rect(0, 0, light_w, light_h, "#fffaf0", "#dd6b20"))

    pin_y = pocket_y - p["valve_outer_height_mm"] / 2.0 - p["pin_length_mm"] / 2.0
    for x in (pocket_x - p["pin_pitch_mm"] / 2.0, pocket_x + p["pin_pitch_mm"] / 2.0):
        lines.append(rect(x, pin_y, p["pin_width_mm"], p["pin_length_mm"], "#feebc8", "#c05621"))

    legend_x = pad + body_w * scale + 34
    legend = [
        "QYH1123 light-valve cage holder",
        "Origin: active aperture center and 30 mm cage center",
        "Valve body: 18 x 20 x 2 mm",
        f"Active area: 15 x 15 mm; through window: {light_w:g} x {light_h:g} mm",
        "Pocket/sink: +0.6 mm XY clearance, 2.2 mm deep",
        f"Terrace lip: {p['terrace_lip_per_side_mm']} mm per side inside the V.A.",
        "Centered variant: valve body, active area, pin pair, and cage datum share x=0",
        "Pins: 2.54 mm pitch, bottom shallow relief for 8 mm tails",
        "Cage rods: 30 mm pitch, 6.4 mm clearance",
    ]
    for i, row in enumerate(legend):
        size = 17 if i == 0 else 13
        weight = "700" if i == 0 else "400"
        lines.append(
            f'<text x="{legend_x:.2f}" y="{pad + i * 25:.2f}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def svg_to_png(svg: Path, png: Path) -> None:
    if subprocess.run(["which", "convert"], capture_output=True, text=True).returncode != 0:
        return
    subprocess.run(["convert", str(svg), str(png)], check=True)


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    light_w, light_h = light_window_xy()
    path.write_text(
        f"""# QYH1123 Light-Valve Centered Clearance Cage Holder

This is a new independent 30 mm cage holder for the Qiyun Display QYH1123 LCD
light valve. It follows the clean Lumileds cage-holder style and keeps the old
design unchanged, but fixes the practical alignment issue seen in the print:
the LCD body, active window, pin pair, pin relief, and cage center are all
centered on the same datum.

## Design Rule

The 15 x 15 mm visible aperture is the optical origin and is also used as the
physical glass/pin center for this centered-fit variant. This intentionally
removes the previous `0.9 mm` lateral shift so the margin on the side parallel
to the pin-header side is equal left/right. The LCD sink is enlarged by
`0.1 mm` on each side relative to the previous holder.

The holder is a single printable body with separate CAD proxies for the valve
and rods. There are no fragile clamps or decorative cuts.

## QYH1123 Dimensions Used

- Outer body: `18.0 x 20.0 x 2.0 mm`.
- Visible area: `15.0 x 15.0 mm`.
- Through light window: `{light_w} x {light_h} mm`, derived from the
  `15.0 x 15.0 mm` visible area minus a `{PARAMS['terrace_lip_per_side_mm']} mm`
  terrace on each side.
- Pin connector: two metal pins, `2.54 mm` pitch, `8.0 mm` tail length.
- Drawing tolerance: `+/-0.2 mm`.
- Electrical table: pin 1 = `COM`, pin 2 = `SEG`.
- Official page: `http://www.qiyun-display.cn/Products_1/59.html`.
- Reference folder: `{PARAMS['reference_folder']}`.

## Holder Geometry

- Body: `{PARAMS['body_width_mm']} x {PARAMS['body_height_mm']} x {PARAMS['body_thickness_mm']} mm`.
- Cage rod holes: 30 mm pitch at `(+/-15, +/-15)`, `{PARAMS['cage_rod_clearance_diameter_mm']} mm` clearance.
- LCD sink: `{PARAMS['valve_outer_width_mm'] + PARAMS['valve_pocket_clearance_mm']} x {PARAMS['valve_outer_height_mm'] + PARAMS['valve_pocket_clearance_mm']} x {PARAMS['valve_pocket_depth_mm']} mm`, centered on the cage datum.
- Optical through-window: `{light_w} x {light_h} mm`, derived from the QYH1123 visible area.
- Support terrace: `{PARAMS['terrace_lip_per_side_mm']} mm` per side between the 15 x 15 mm V.A. and the through-window.
- Pin relief: shallow bottom channel for the two metal tails, centered on x=0 and widened by `0.1 mm` on each side.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}

## Notes

- Print/check the holder-only STEP or STL. The assembly includes transparent
  valve and rod proxies only for alignment inspection.
- If the physical valve is too tight, increase only `valve_pocket_clearance_mm`.
- If the pins need more room, increase `pin_exit_relief_width_mm` or
  `pin_exit_relief_depth_mm`; avoid changing cage-hole coordinates.
""",
        encoding="utf-8",
    )


def write_manifest(path: Path, outputs: dict[str, str]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": "Clean 30 mm cage holder with QYH1123 active aperture centered on the optical axis.",
        "parameters": PARAMS,
        "outputs": outputs,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    holder = build_holder()
    valve = build_valve_proxy()
    rods = build_cage_rods_proxy()
    assembly = build_assembly().toCompound()

    holder_step = ARTIFACT_DIR / f"{STEM}.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}.stl"
    valve_step = ARTIFACT_DIR / f"{STEM}_valve_proxy.step"
    valve_stl = ARTIFACT_DIR / f"{STEM}_valve_proxy.stl"
    rods_step = ARTIFACT_DIR / f"{STEM}_cage_rods_proxy.step"
    rods_stl = ARTIFACT_DIR / f"{STEM}_cage_rods_proxy.stl"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    top_svg = ARTIFACT_DIR / f"{STEM}_top_alignment.svg"
    top_png = ARTIFACT_DIR / f"{STEM}_top_alignment.png"
    manifest = ARTIFACT_DIR / "manifest.json"

    exporters.export(holder, str(holder_step))
    exporters.export(holder, str(holder_stl))
    exporters.export(valve, str(valve_step))
    exporters.export(valve, str(valve_stl))
    exporters.export(rods, str(rods_step))
    exporters.export(rods, str(rods_stl))
    exporters.export(assembly, str(assembly_step))
    exporters.export(assembly, str(assembly_stl))
    write_alignment_svg(top_svg)
    svg_to_png(top_svg, top_png)

    outputs = {
        "holder_step": repo_path(holder_step),
        "holder_stl": repo_path(holder_stl),
        "valve_proxy_step": repo_path(valve_step),
        "valve_proxy_stl": repo_path(valve_stl),
        "cage_rods_proxy_step": repo_path(rods_step),
        "cage_rods_proxy_stl": repo_path(rods_stl),
        "assembly_step": repo_path(assembly_step),
        "assembly_stl": repo_path(assembly_stl),
        "top_alignment_svg": repo_path(top_svg),
        "top_alignment_png": repo_path(top_png) if top_png.exists() else "",
        "manifest": repo_path(manifest),
    }
    write_manifest(manifest, outputs)
    write_readme(DESIGN_DIR / "README.md", outputs)

    print(json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
