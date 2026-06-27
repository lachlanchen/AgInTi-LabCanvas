#!/usr/bin/env python3
"""Build a two-piece locking sample holder for slide and 33 mm petri use.

The previous `cage_sample_holder_openhi_slide_petri35` design is intentionally
left untouched. This design uses a wider cage-derived frame so the rod sockets
stay outside an 80 x 40 mm central sample zone.
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
STEM = "cage_sample_holder_two_piece_lock_slide_petri35"


PARAMS = {
    "name": STEM,
    "architecture": "two printed parts: bottom tray with four male lock feet plus top frame with four matching holes",
    "outer_width_mm": 110.0,
    "outer_height_mm": 70.0,
    "plate_thickness_mm": 8.0,
    "chamber_gap_mm": 18.0,
    "assembled_height_mm": 34.0,
    "top_inner_window_mm": [82.0, 42.0],
    "usable_sample_zone_mm": [80.0, 40.0],
    "edge_fillet_mm": 0.8,
    "lock_nominal_diameter_mm": 6.0,
    "lock_foot_diameter_mm": 5.8,
    "lock_hole_diameter_mm": 6.2,
    "lock_foot_total_height_mm": 23.2,
    "lock_hole_depth_mm": 5.8,
    "lock_points_mm": [[-47.0, -27.0], [47.0, -27.0], [-47.0, 27.0], [47.0, 27.0]],
    "rod_diameter_nominal_mm": 6.0,
    "rod_socket_diameter_mm": 6.4,
    "rod_socket_depth_mm": 6.0,
    "m3_thread_pilot_diameter_mm": 2.6,
    "rod_socket_x_pitch_mm": 60.0,
    "rod_socket_y_pitch_mm": 56.0,
    "top_rod_socket_centers_mm": [[-30.0, -28.0], [30.0, -28.0], [-30.0, 28.0], [30.0, 28.0]],
    "bottom_rod_socket_centers_mm": [[-30.0, -28.0], [30.0, -28.0], [-30.0, 28.0], [30.0, 28.0]],
    "openhi_strip_nominal_mm": [72.96, 20.0],
    "openhi_strip_seat_mm": [75.0, 22.0],
    "openhi_strip_sink_depth_mm": 1.2,
    "petri_nominal_diameter_mm": 33.0,
    "petri_clearance_diameter_mm": 35.4,
    "petri_sink_depth_mm": 1.8,
    "optical_window_diameter_mm": 18.0,
    "finger_notch_width_mm": 18.0,
    "finger_notch_height_mm": 28.0,
    "finger_notch_depth_mm": 3.0,
    "print_fit_note": "Male lock feet are nominal -0.2 mm, matching holes are nominal +0.2 mm. Rod sockets use 6.4 mm clearance; M3 pilot/thread places use 2.6 mm.",
    "orientation_note": "Bottom part owns four lower rod sockets and sample seats. Top part owns four upper rod sockets and the open viewing/access window.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float, vertices: int = 96) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def add_edge_fillet(part: cq.Workplane) -> cq.Workplane:
    radius = float(PARAMS["edge_fillet_mm"])
    return part.edges("|Z").fillet(radius) if radius > 0 else part


def base_plate() -> cq.Workplane:
    p = PARAMS
    part = z_box(
        (p["outer_width_mm"], p["outer_height_mm"], p["plate_thickness_mm"]),
        (0, 0, p["plate_thickness_mm"] / 2.0),
    )
    return add_edge_fillet(part)


def cut_m3_pilot(part: cq.Workplane, points: list[list[float]], z_min: float, height: float) -> cq.Workplane:
    for x, y in points:
        part = part.cut(z_cylinder(PARAMS["m3_thread_pilot_diameter_mm"], height, z_min, vertices=48).translate((x, y, 0)))
    return part


def cut_bottom_rod_sockets(part: cq.Workplane) -> cq.Workplane:
    p = PARAMS
    socket_h = p["rod_socket_depth_mm"] + 0.2
    for x, y in p["bottom_rod_socket_centers_mm"]:
        part = part.cut(z_cylinder(p["rod_socket_diameter_mm"], socket_h, -0.1).translate((x, y, 0)))
    return cut_m3_pilot(part, p["bottom_rod_socket_centers_mm"], -0.1, p["plate_thickness_mm"] + 0.2)


def cut_top_rod_sockets(part: cq.Workplane) -> cq.Workplane:
    p = PARAMS
    z_min = p["plate_thickness_mm"] - p["rod_socket_depth_mm"]
    socket_h = p["rod_socket_depth_mm"] + 0.2
    for x, y in p["top_rod_socket_centers_mm"]:
        part = part.cut(z_cylinder(p["rod_socket_diameter_mm"], socket_h, z_min).translate((x, y, 0)))
    return cut_m3_pilot(part, p["top_rod_socket_centers_mm"], -0.1, p["plate_thickness_mm"] + 0.2)


def cut_lock_holes_from_bottom(part: cq.Workplane) -> cq.Workplane:
    p = PARAMS
    for x, y in p["lock_points_mm"]:
        part = part.cut(z_cylinder(p["lock_hole_diameter_mm"], p["lock_hole_depth_mm"] + 0.2, -0.1).translate((x, y, 0)))
    return part


def add_lock_feet(part: cq.Workplane) -> cq.Workplane:
    p = PARAMS
    z_min = p["plate_thickness_mm"]
    for x, y in p["lock_points_mm"]:
        foot = z_cylinder(p["lock_foot_diameter_mm"], p["lock_foot_total_height_mm"], z_min, vertices=72).translate((x, y, 0))
        part = part.union(foot)
    return part


def cut_bottom_sample_seats(part: cq.Workplane) -> cq.Workplane:
    p = PARAMS
    top_z = p["plate_thickness_mm"]

    zone_x, zone_y = p["usable_sample_zone_mm"]
    part = part.cut(z_box((zone_x, zone_y, 0.7), (0, 0, top_z - 0.35 + 0.1)))

    petri_depth = p["petri_sink_depth_mm"]
    part = part.cut(
        z_cylinder(p["petri_clearance_diameter_mm"], petri_depth + 0.25, top_z - petri_depth).translate((0, 0, 0))
    )

    slide_x, slide_y = p["openhi_strip_seat_mm"]
    slide_depth = p["openhi_strip_sink_depth_mm"]
    part = part.cut(z_box((slide_x, slide_y, slide_depth + 0.25), (0, 0, top_z - slide_depth / 2.0 + 0.1)))

    part = part.cut(z_cylinder(p["optical_window_diameter_mm"], p["plate_thickness_mm"] + 0.6, -0.3))

    notch_x = p["outer_width_mm"] / 2.0
    notch_z = top_z - p["finger_notch_depth_mm"] / 2.0 + 0.15
    notch_size = (p["finger_notch_width_mm"], p["finger_notch_height_mm"], p["finger_notch_depth_mm"] + 0.3)
    for sign in (-1, 1):
        part = part.cut(z_box(notch_size, (sign * notch_x, 0, notch_z)))
    return part


def build_bottom_part() -> cq.Workplane:
    part = base_plate()
    part = cut_bottom_sample_seats(part)
    part = cut_bottom_rod_sockets(part)
    part = add_lock_feet(part)
    return part


def build_top_part() -> cq.Workplane:
    p = PARAMS
    part = base_plate()
    win_x, win_y = p["top_inner_window_mm"]
    part = part.cut(z_box((win_x, win_y, p["plate_thickness_mm"] + 1.2), (0, 0, p["plate_thickness_mm"] / 2.0)))
    part = cut_top_rod_sockets(part)
    part = cut_lock_holes_from_bottom(part)
    return part


def top_part_z() -> float:
    return PARAMS["plate_thickness_mm"] + PARAMS["chamber_gap_mm"]


def build_slide_proxy() -> cq.Workplane:
    length, width = PARAMS["openhi_strip_nominal_mm"]
    return z_box((length, width, 1.0), (0, 0, PARAMS["plate_thickness_mm"] - 0.35))


def build_petri_proxy() -> cq.Workplane:
    return z_cylinder(PARAMS["petri_nominal_diameter_mm"], 1.2, PARAMS["plate_thickness_mm"] - 1.0)


def build_rod_proxies() -> cq.Workplane:
    p = PARAMS
    rods = None
    for x, y in p["top_rod_socket_centers_mm"]:
        rod = z_cylinder(5.9, 23.0, top_part_z() + p["plate_thickness_mm"] - 0.8).translate((x, y, 0))
        rods = rod if rods is None else rods.union(rod)
    for x, y in p["bottom_rod_socket_centers_mm"]:
        rod = z_cylinder(5.9, 23.0, -22.2).translate((x, y, 0))
        rods = rod if rods is None else rods.union(rod)
    assert rods is not None
    return rods


def build_print_layout() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_print_layout")
    assembly.add(build_bottom_part(), name="bottom_tray_with_lock_feet", color=cq.Color(0.12, 0.12, 0.12, 1.0))
    assembly.add(build_top_part().translate((0, 92, 0)), name="top_frame_with_lock_holes", color=cq.Color(0.18, 0.18, 0.18, 1.0))
    return assembly


def build_assembled() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembled")
    assembly.add(build_bottom_part(), name="bottom_tray_lower_rod_sockets", color=cq.Color(0.10, 0.10, 0.10, 1.0))
    assembly.add(build_top_part().translate((0, 0, top_part_z())), name="top_frame_upper_rod_sockets", color=cq.Color(0.17, 0.17, 0.16, 1.0))
    return assembly


def build_reference_assembly() -> cq.Assembly:
    assembly = build_assembled()
    assembly.add(build_slide_proxy(), name="openhi_strip_proxy_overlap_seat", color=cq.Color(0.15, 0.85, 0.95, 0.35))
    assembly.add(build_petri_proxy(), name="petri_33mm_proxy_overlap_seat", color=cq.Color(0.95, 0.95, 1.0, 0.35))
    assembly.add(build_rod_proxies(), name="6mm_rod_proxies_with_m3_axis", color=cq.Color(0.1, 0.45, 0.9, 0.38))
    return assembly


def build_exploded() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_exploded")
    assembly.add(build_bottom_part(), name="bottom_tray_with_lock_feet", color=cq.Color(0.10, 0.10, 0.10, 1.0))
    assembly.add(build_top_part().translate((0, 0, 48.0)), name="top_frame_with_lock_holes", color=cq.Color(0.17, 0.17, 0.16, 1.0))
    assembly.add(build_slide_proxy().translate((0, -48.0, 7.0)), name="openhi_strip_proxy", color=cq.Color(0.15, 0.85, 0.95, 0.35))
    assembly.add(build_petri_proxy().translate((0, 48.0, 7.0)), name="petri_proxy", color=cq.Color(0.95, 0.95, 1.0, 0.35))
    assembly.add(build_rod_proxies(), name="rod_proxies", color=cq.Color(0.1, 0.45, 0.9, 0.38))
    return assembly


def export_part(part: cq.Workplane, step_path: Path, stl_path: Path) -> None:
    exporters.export(part, str(step_path))
    exporters.export(part, str(stl_path))


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    compound = assembly.toCompound()
    exporters.export(compound, str(step_path))
    exporters.export(compound, str(stl_path))


def write_alignment_svg(path: Path) -> None:
    p = PARAMS
    scale = 6.5
    pad = 54.0
    legend_w = 560
    w = p["outer_width_mm"]
    h = p["outer_height_mm"]
    svg_w = int(w * scale + pad * 2 + legend_w)
    svg_h = int(h * scale + pad * 2)

    def sx(x: float) -> float:
        return pad + (x + w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (h / 2.0 - y) * scale

    def circle(x: float, y: float, diameter: float, fill: str, stroke: str, dashed: bool = False) -> str:
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        return (
            f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="{diameter / 2.0 * scale:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>'
        )

    def rect(cx: float, cy: float, rw: float, rh: float, fill: str, stroke: str, dashed: bool = False) -> str:
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        return (
            f'<rect x="{sx(cx - rw / 2.0):.2f}" y="{sy(cy + rh / 2.0):.2f}" '
            f'width="{rw * scale:.2f}" height="{rh * scale:.2f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2"{dash}/>'
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        rect(0, 0, p["outer_width_mm"], p["outer_height_mm"], "#f7fafc", "#1a202c"),
        rect(0, 0, p["usable_sample_zone_mm"][0], p["usable_sample_zone_mm"][1], "rgba(49,151,149,0.10)", "#319795", dashed=True),
        rect(0, 0, p["openhi_strip_seat_mm"][0], p["openhi_strip_seat_mm"][1], "rgba(49,151,149,0.18)", "#319795"),
        circle(0, 0, p["petri_clearance_diameter_mm"], "rgba(128,90,213,0.12)", "#805ad5"),
        circle(0, 0, p["optical_window_diameter_mm"], "#fffaf0", "#dd6b20"),
    ]
    for x, y in p["top_rod_socket_centers_mm"]:
        lines.append(circle(x, y, p["rod_socket_diameter_mm"], "#ebf8ff", "#3182ce"))
    for x, y in p["bottom_rod_socket_centers_mm"]:
        lines.append(circle(x, y, p["rod_socket_diameter_mm"], "#e6fffa", "#2c7a7b"))
    for x, y in p["lock_points_mm"]:
        lines.append(circle(x, y, p["lock_hole_diameter_mm"], "none", "#4a5568", dashed=True))
        lines.append(circle(x, y, p["lock_foot_diameter_mm"], "rgba(74,85,104,0.16)", "#4a5568"))

    legend_x = pad + w * scale + 34
    legend = [
        "Two-piece locking sample holder",
        "Outer: 110 x 70 mm; sample zone: 80 x 40 mm",
        "Bottom: slide sink + 35.4 mm petri sink + four lower rod sockets",
        "Top: open window + four upper rod sockets + lock holes",
        "Four lock feet: 5.8 mm; matching holes: 6.2 mm",
        "Rod sockets: 6.4 mm blind pockets; M3 pilot/thread axis: 2.6 mm",
        "Slide and petri seats overlap at the center by design",
        "18 mm chamber gap leaves finger room for placing/removing samples",
    ]
    for index, row in enumerate(legend):
        size = 17 if index == 0 else 13
        weight = "700" if index == 0 else "400"
        lines.append(
            f'<text x="{legend_x:.2f}" y="{pad + index * 25:.2f}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def svg_to_png(svg: Path, png: Path) -> None:
    if subprocess.run(["which", "convert"], capture_output=True, text=True).returncode != 0:
        return
    subprocess.run(["convert", str(svg), str(png)], check=True)


def write_manifest(path: Path, outputs: dict[str, str]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": "Two-piece wide sample holder with lock feet, 6 mm rod sockets, M3 pilot/thread places, overlapping slide and 35 mm petri seats, and finger access.",
        "parameters": PARAMS,
        "outputs": outputs,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    p = PARAMS
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in p.items())
    path.write_text(
        f"""# Two-Piece Locking Cage Sample Holder

This is a new independent design based on the successful
`cage_sample_holder_openhi_slide_petri35` geometry. The older design is not
changed.

## Design Intent

The holder is split into two printable parts:

1. `bottom_part`: tray for the sample, lower rod sockets, four male lock feet.
2. `top_part`: open frame, upper rod sockets, four matching lock holes.

The sample zone is intentionally large (`{p['usable_sample_zone_mm'][0]} x {p['usable_sample_zone_mm'][1]} mm`) so it can hold both the OpenHI-style strip
seat and a small petri dish seat in the same center. The top frame is open over
the sample zone and the assembled chamber gap is `{p['chamber_gap_mm']} mm`, so
there is room to place and remove the slide or dish with fingers.

## Fit Choices

- Lock feet: `{p['lock_foot_diameter_mm']} mm`, from nominal 6 mm minus 0.2 mm.
- Lock holes: `{p['lock_hole_diameter_mm']} mm`, from nominal 6 mm plus 0.2 mm.
- Rod sockets: `{p['rod_socket_diameter_mm']} mm` blind pockets for nominal 6 mm rods.
- M3 pilot/thread places: `{p['m3_thread_pilot_diameter_mm']} mm`, intended as a tight printed/tapped pilot rather than a loose clearance hole.

## Sample Seats

- OpenHI strip reference: `{p['openhi_strip_nominal_mm'][0]} x {p['openhi_strip_nominal_mm'][1]} mm`.
- Printed slide sink: `{p['openhi_strip_seat_mm'][0]} x {p['openhi_strip_seat_mm'][1]} mm`, `{p['openhi_strip_sink_depth_mm']} mm` deep.
- Petri seat: `{p['petri_clearance_diameter_mm']} mm` for a nominal `{p['petri_nominal_diameter_mm']} mm` dish, `{p['petri_sink_depth_mm']} mm` deep.
- The slide sink and petri sink overlap at the center by design.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}

## Print Notes

- Print `bottom_part` and `top_part`.
- The `assembled` files are for checking fit.
- The `reference_assembly` files include transparent rod/sample proxies and are not intended as print files.
- If the lock is too tight, lightly sand the four printed feet first; keep the holes unchanged unless necessary.
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    paths = {
        "bottom_part_step": ARTIFACT_DIR / f"{STEM}_bottom_part.step",
        "bottom_part_stl": ARTIFACT_DIR / f"{STEM}_bottom_part.stl",
        "top_part_step": ARTIFACT_DIR / f"{STEM}_top_part.step",
        "top_part_stl": ARTIFACT_DIR / f"{STEM}_top_part.stl",
        "assembled_step": ARTIFACT_DIR / f"{STEM}_assembled.step",
        "assembled_stl": ARTIFACT_DIR / f"{STEM}_assembled.stl",
        "reference_assembly_step": ARTIFACT_DIR / f"{STEM}_reference_assembly.step",
        "reference_assembly_stl": ARTIFACT_DIR / f"{STEM}_reference_assembly.stl",
        "print_layout_step": ARTIFACT_DIR / f"{STEM}_print_layout.step",
        "print_layout_stl": ARTIFACT_DIR / f"{STEM}_print_layout.stl",
        "exploded_step": ARTIFACT_DIR / f"{STEM}_exploded.step",
        "exploded_stl": ARTIFACT_DIR / f"{STEM}_exploded.stl",
        "top_alignment_svg": ARTIFACT_DIR / f"{STEM}_top_alignment.svg",
        "top_alignment_png": ARTIFACT_DIR / f"{STEM}_top_alignment.png",
        "assembled_render_png": ARTIFACT_DIR / f"{STEM}_assembled_render.png",
        "exploded_render_png": ARTIFACT_DIR / f"{STEM}_exploded_render.png",
        "print_layout_render_png": ARTIFACT_DIR / f"{STEM}_print_layout_render.png",
        "blender_scene": ARTIFACT_DIR / f"{STEM}.blend",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }

    export_part(build_bottom_part(), paths["bottom_part_step"], paths["bottom_part_stl"])
    export_part(build_top_part(), paths["top_part_step"], paths["top_part_stl"])
    export_assembly(build_assembled(), paths["assembled_step"], paths["assembled_stl"])
    export_assembly(build_reference_assembly(), paths["reference_assembly_step"], paths["reference_assembly_stl"])
    export_assembly(build_print_layout(), paths["print_layout_step"], paths["print_layout_stl"])
    export_assembly(build_exploded(), paths["exploded_step"], paths["exploded_stl"])
    write_alignment_svg(paths["top_alignment_svg"])
    svg_to_png(paths["top_alignment_svg"], paths["top_alignment_png"])

    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["manifest"] = repo_path(paths["manifest"])
    write_manifest(paths["manifest"], outputs)
    write_readme(DESIGN_DIR / "README.md", outputs)

    print(json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
