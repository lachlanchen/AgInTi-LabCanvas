#!/usr/bin/env python3
"""Build a modular 30 mm cage sample holder.

Architecture:

1. A hollow cage frame holds the top and bottom cage rods.
2. A swappable sample cartridge screws onto the frame.
3. The slide cartridge handles the OpenHI-style narrow strip.
4. The petri cartridge handles a nominal 33 mm dish with a loose 35 mm seat.

For each experiment the printed assembly is two parts: frame + selected
cartridge. The second cartridge is an alternate part, not a required stack.
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
STEM = "cage_sample_holder_openhi_slide_petri35"


PARAMS = {
    "name": STEM,
    "architecture": "two-part-in-use: cage frame plus one swappable sample cartridge",
    "frame_width_mm": 90.0,
    "frame_height_mm": 54.0,
    "frame_thickness_mm": 6.0,
    "frame_window_width_mm": 76.0,
    "frame_window_height_mm": 22.0,
    "edge_fillet_mm": 0.8,
    "cartridge_width_mm": 86.0,
    "cartridge_height_mm": 46.0,
    "cartridge_thickness_mm": 3.2,
    "cartridge_gap_from_frame_mm": 0.4,
    "cage_rod_pitch_mm": 30.0,
    "frame_rod_clearance_diameter_mm": 6.4,
    "cartridge_rod_relief_diameter_mm": 7.0,
    "mount_screw_x_mm": 40.5,
    "mount_screw_clearance_diameter_mm": 2.7,
    "optical_window_diameter_mm": 20.0,
    "openhi_strip_nominal_mm": [72.96, 20.0],
    "openhi_strip_seat_clearance_mm": [74.5, 21.5],
    "slide_rail_width_mm": 2.0,
    "slide_rail_height_mm": 2.0,
    "slide_end_stop_width_mm": 1.8,
    "petri_nominal_diameter_mm": 33.0,
    "petri_clearance_diameter_mm": 35.2,
    "petri_outer_ring_diameter_mm": 39.4,
    "petri_ring_height_mm": 2.2,
    "standard_slide_reference_mm": [76.0, 26.0],
    "fit_warning": "A full 75-76 x 25-26 mm microscope slide is too wide for a centered 30 mm cage with 6 mm rods. Use the OpenHI narrow strip cartridge or an external slide tray.",
}


OPENHI_REFERENCE_DIMS = {
    "Light switch holder.step": {
        "bbox_mm": [72.958, 20.0, 66.0],
        "reason": "Local OpenHI STEP file with a 72.958 x 20 mm dimension, matching the remembered 70+ x 20+ strip.",
    },
    "Collimator holder FHPLP.step": {
        "bbox_mm": [71.0, 50.0, 10.0],
        "reason": "Another local OpenHI part with a 71 mm long dimension.",
    },
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float, vertices: int = 96) -> cq.Workplane:
    return cq.Workplane("XY", origin=(0, 0, z_min)).circle(diameter / 2.0).extrude(height)


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def rod_points() -> list[tuple[float, float]]:
    half = PARAMS["cage_rod_pitch_mm"] / 2.0
    return [(x, y) for x in (-half, half) for y in (-half, half)]


def screw_points() -> list[tuple[float, float]]:
    return [(-PARAMS["mount_screw_x_mm"], 0.0), (PARAMS["mount_screw_x_mm"], 0.0)]


def cut_standard_holes(part: cq.Workplane, *, rod_diameter: float, z_min: float, height: float) -> cq.Workplane:
    for x, y in rod_points():
        part = part.cut(z_cylinder(rod_diameter, height, z_min).translate((x, y, 0)))
    for x, y in screw_points():
        part = part.cut(z_cylinder(PARAMS["mount_screw_clearance_diameter_mm"], height, z_min).translate((x, y, 0)))
    return part


def build_frame() -> cq.Workplane:
    p = PARAMS
    frame = cq.Workplane("XY").box(p["frame_width_mm"], p["frame_height_mm"], p["frame_thickness_mm"])
    frame = frame.edges("|Z").fillet(p["edge_fillet_mm"])
    frame = frame.cut(
        z_box(
            (p["frame_window_width_mm"], p["frame_window_height_mm"], p["frame_thickness_mm"] + 1.2),
            (0, 0, 0),
        )
    )
    return cut_standard_holes(
        frame,
        rod_diameter=p["frame_rod_clearance_diameter_mm"],
        z_min=-p["frame_thickness_mm"] / 2.0 - 0.6,
        height=p["frame_thickness_mm"] + 1.2,
    )


def build_cartridge_base() -> cq.Workplane:
    p = PARAMS
    base = cq.Workplane("XY").box(p["cartridge_width_mm"], p["cartridge_height_mm"], p["cartridge_thickness_mm"])
    base = base.edges("|Z").fillet(0.5)
    z_min = -p["cartridge_thickness_mm"] / 2.0 - 0.6
    height = p["cartridge_thickness_mm"] + 1.2
    base = base.cut(z_cylinder(p["optical_window_diameter_mm"], height, z_min))
    return cut_standard_holes(base, rod_diameter=p["cartridge_rod_relief_diameter_mm"], z_min=z_min, height=height)


def build_slide_cartridge() -> cq.Workplane:
    p = PARAMS
    part = build_cartridge_base()
    top_z = p["cartridge_thickness_mm"] / 2.0
    rail_h = p["slide_rail_height_mm"]
    rail_w = p["slide_rail_width_mm"]
    seat_l, seat_w = p["openhi_strip_seat_clearance_mm"]
    rail_y = seat_w / 2.0 + rail_w / 2.0
    rail_len = seat_l + 4.0
    for y in (-rail_y, rail_y):
        part = part.union(z_box((rail_len, rail_w, rail_h), (0, y, top_z + rail_h / 2.0)))

    stop_x = seat_l / 2.0 + p["slide_end_stop_width_mm"] / 2.0
    stop_y = seat_w / 2.0 - 2.8
    for x in (-stop_x, stop_x):
        for y in (-stop_y, stop_y):
            part = part.union(
                z_box(
                    (p["slide_end_stop_width_mm"], 5.0, rail_h),
                    (x, y, top_z + rail_h / 2.0),
                )
            )

    # Re-cut rod reliefs after adding rails so the rails also clear the cage rods.
    z_min = -p["cartridge_thickness_mm"] / 2.0 - 0.6
    height = p["cartridge_thickness_mm"] + rail_h + 1.2
    for x, y in rod_points():
        part = part.cut(z_cylinder(p["cartridge_rod_relief_diameter_mm"], height, z_min).translate((x, y, 0)))
    return part


def build_petri_cartridge() -> cq.Workplane:
    p = PARAMS
    part = build_cartridge_base()
    top_z = p["cartridge_thickness_mm"] / 2.0
    ring_h = p["petri_ring_height_mm"]
    ring = z_cylinder(p["petri_outer_ring_diameter_mm"], ring_h, top_z).cut(
        z_cylinder(p["petri_clearance_diameter_mm"], ring_h + 0.6, top_z - 0.3)
    )
    part = part.union(ring)

    # Re-cut rod reliefs after adding the dish ring to make a segmented ring.
    z_min = -p["cartridge_thickness_mm"] / 2.0 - 0.6
    height = p["cartridge_thickness_mm"] + ring_h + 1.2
    for x, y in rod_points():
        part = part.cut(z_cylinder(p["cartridge_rod_relief_diameter_mm"], height, z_min).translate((x, y, 0)))
    return part


def build_openhi_strip_proxy(z_center: float) -> cq.Workplane:
    length, width = PARAMS["openhi_strip_nominal_mm"]
    return z_box((length, width, 1.1), (0, 0, z_center))


def build_petri_proxy(z_center: float) -> cq.Workplane:
    return z_cylinder(PARAMS["petri_nominal_diameter_mm"], 1.2, z_center - 0.6)


def build_rods_proxy() -> cq.Workplane:
    z_min = -7.0
    rods = None
    for x, y in rod_points():
        rod = z_cylinder(5.9, 24.0, z_min).translate((x, y, 0))
        rods = rod if rods is None else rods.union(rod)
    assert rods is not None
    return rods


def cartridge_z() -> float:
    p = PARAMS
    return p["frame_thickness_mm"] / 2.0 + p["cartridge_gap_from_frame_mm"] + p["cartridge_thickness_mm"] / 2.0


def build_slide_assembly() -> cq.Assembly:
    p = PARAMS
    z = cartridge_z()
    assembly = cq.Assembly(name=f"{STEM}_slide_assembly")
    assembly.add(build_frame(), name="hollow_cage_frame", color=cq.Color(0.08, 0.08, 0.075, 1.0))
    assembly.add(build_slide_cartridge().translate((0, 0, z)), name="openhi_strip_slide_cartridge", color=cq.Color(0.15, 0.15, 0.14, 1.0))
    assembly.add(build_openhi_strip_proxy(z + p["cartridge_thickness_mm"] / 2.0 + p["slide_rail_height_mm"] + 0.55), name="openhi_strip_proxy", color=cq.Color(0.2, 0.8, 0.95, 0.45))
    assembly.add(build_rods_proxy(), name="cage_rod_proxies", color=cq.Color(0.1, 0.45, 0.9, 0.35))
    return assembly


def build_petri_assembly() -> cq.Assembly:
    p = PARAMS
    z = cartridge_z()
    assembly = cq.Assembly(name=f"{STEM}_petri_assembly")
    assembly.add(build_frame(), name="hollow_cage_frame", color=cq.Color(0.08, 0.08, 0.075, 1.0))
    assembly.add(build_petri_cartridge().translate((0, 0, z)), name="petri_35mm_cartridge", color=cq.Color(0.15, 0.15, 0.14, 1.0))
    assembly.add(build_petri_proxy(z + p["cartridge_thickness_mm"] / 2.0 + p["petri_ring_height_mm"] + 0.6), name="petri_33mm_proxy", color=cq.Color(0.95, 0.95, 1.0, 0.45))
    assembly.add(build_rods_proxy(), name="cage_rod_proxies", color=cq.Color(0.1, 0.45, 0.9, 0.35))
    return assembly


def build_exploded_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_exploded")
    assembly.add(build_frame().translate((0, 0, 0)), name="hollow_cage_frame", color=cq.Color(0.08, 0.08, 0.075, 1.0))
    assembly.add(build_slide_cartridge().translate((0, -36, 10)), name="slide_cartridge_alternate", color=cq.Color(0.2, 0.45, 0.4, 1.0))
    assembly.add(build_petri_cartridge().translate((0, 36, 10)), name="petri_cartridge_alternate", color=cq.Color(0.35, 0.25, 0.55, 1.0))
    assembly.add(build_rods_proxy(), name="cage_rod_proxies", color=cq.Color(0.1, 0.45, 0.9, 0.35))
    return assembly


def write_alignment_svg(path: Path) -> None:
    p = PARAMS
    scale = 7.5
    pad = 55.0
    legend_w = 520
    w = p["frame_width_mm"]
    h = p["frame_height_mm"]
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
        rect(0, 0, p["frame_width_mm"], p["frame_height_mm"], "#f7fafc", "#1a202c"),
        rect(0, 0, p["frame_window_width_mm"], p["frame_window_height_mm"], "white", "#718096"),
        rect(0, 0, p["cartridge_width_mm"], p["cartridge_height_mm"], "rgba(49,151,149,0.10)", "#319795", dashed=True),
        rect(0, 0, p["openhi_strip_seat_clearance_mm"][0], p["openhi_strip_seat_clearance_mm"][1], "rgba(49,151,149,0.16)", "#319795"),
        circle(0, 0, p["petri_clearance_diameter_mm"], "none", "#805ad5", dashed=True),
        rect(0, 0, p["standard_slide_reference_mm"][0], p["standard_slide_reference_mm"][1], "none", "#e53e3e", dashed=True),
        circle(0, 0, p["optical_window_diameter_mm"], "#fffaf0", "#dd6b20"),
    ]
    for x, y in rod_points():
        lines.append(circle(x, y, p["frame_rod_clearance_diameter_mm"], "#ebf8ff", "#3182ce"))
    for x, y in screw_points():
        lines.append(circle(x, y, p["mount_screw_clearance_diameter_mm"], "#edf2f7", "#4a5568"))

    legend_x = pad + w * scale + 34
    clear_gap = p["cage_rod_pitch_mm"] - p["frame_rod_clearance_diameter_mm"]
    legend = [
        "Elegant modular cage sample holder",
        "Use as two parts: frame + one cartridge",
        f"Frame: {p['frame_width_mm']} x {p['frame_height_mm']} mm, middle removed",
        "Top/bottom cage rods pass through the four blue holes",
        f"Clear rod gap is about {clear_gap:.1f} mm",
        "OpenHI strip cartridge: 74.5 x 21.5 mm seat",
        "Petri cartridge: 35.2 mm loose cup for 33 mm dish",
        "Dashed red: standard 76 x 26 slide, too wide for cage gap",
        "Gray holes: M2.5/M2.6 cartridge screws",
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


def export_part(part: cq.Workplane, step_path: Path, stl_path: Path) -> None:
    exporters.export(part, str(step_path))
    exporters.export(part, str(stl_path))


def export_assembly(assembly: cq.Assembly, step_path: Path, stl_path: Path) -> None:
    compound = assembly.toCompound()
    exporters.export(compound, str(step_path))
    exporters.export(compound, str(stl_path))


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    p = PARAMS
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    param_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in p.items())
    reference_rows = "\n".join(
        f"| `{name}` | `{data['bbox_mm']}` | {data['reason']} |" for name, data in OPENHI_REFERENCE_DIMS.items()
    )
    clear_gap = p["cage_rod_pitch_mm"] - p["frame_rod_clearance_diameter_mm"]
    path.write_text(
        f"""# Modular Cage Sample Holder: OpenHI Strip and 33 mm Petri Dish

This is a new independent cage sample-holder design. It leaves the earlier
Lumileds holders untouched.

## Concept

The design is intentionally split into a clean two-part working assembly:

1. `frame`: a hollow 30 mm cage frame. The cage rods sit in the top and bottom
   rod holes, and the middle is removed.
2. `cartridge`: one swappable sample holder. Use either the OpenHI strip
   cartridge or the 33 mm petri cartridge.

This avoids forcing every sample into one complicated part. The frame stays on
the cage, while the sample cartridge can be replaced.

## Slide Size Used

I did not find a dedicated `slide holder` STEP in the local OpenHI files. The
closest local OpenHI dimensions are:

| OpenHI file | Bounding box mm | Note |
| --- | --- | --- |
{reference_rows}

So the slide cartridge uses a strip seat of `{p['openhi_strip_seat_clearance_mm'][0]} x {p['openhi_strip_seat_clearance_mm'][1]} mm`, sized for an inferred OpenHI strip around `{p['openhi_strip_nominal_mm'][0]} x {p['openhi_strip_nominal_mm'][1]} mm`.

A standard `{p['standard_slide_reference_mm'][0]} x {p['standard_slide_reference_mm'][1]} mm` microscope slide is shown only as a dashed red outline in the sketch. It is too wide for a centered 30 mm cage using `{p['frame_rod_clearance_diameter_mm']} mm` rod holes: the clear gap between the upper and lower rod holes is only about `{clear_gap:.1f} mm`.

## Geometry

- Frame: `{p['frame_width_mm']} x {p['frame_height_mm']} x {p['frame_thickness_mm']} mm`.
- Hollow frame window: `{p['frame_window_width_mm']} x {p['frame_window_height_mm']} mm`.
- Cage rod holes: four holes at `(+/-15, +/-15)`.
- Cartridge screw holes: two through holes at `x = +/-{p['mount_screw_x_mm']} mm`.
- Optical window: `{p['optical_window_diameter_mm']} mm` through the center.
- Petri cartridge: `{p['petri_clearance_diameter_mm']} mm` loose cup for a nominal `{p['petri_nominal_diameter_mm']} mm` dish.
- Rod reliefs are intentionally cut through each cartridge, so cartridge edges and rings do not collide with the cage rods.

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Name | Value |
| --- | --- |
{param_rows}

## Print Notes

- Print `frame` plus only the cartridge you need.
- The assembly files are for checking, not a single fused printable part.
- If you need a full standard microscope slide, make a later external tray that
  sits outside the cage rod plane. A centered 26 mm-wide slide does not fit
  cleanly between 6 mm rods in a 30 mm cage.
""",
        encoding="utf-8",
    )


def write_manifest(path: Path, outputs: dict[str, str]) -> None:
    manifest = {
        "name": STEM,
        "created_by": Path(__file__).name,
        "design_intent": "Hollow 30 mm cage frame plus swappable sample cartridges for an OpenHI strip and a 33 mm petri dish.",
        "parameters": PARAMS,
        "openhi_reference_dimensions": OPENHI_REFERENCE_DIMS,
        "outputs": outputs,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    frame = build_frame()
    slide_cartridge = build_slide_cartridge()
    petri_cartridge = build_petri_cartridge()

    paths = {
        "frame_step": ARTIFACT_DIR / f"{STEM}_frame.step",
        "frame_stl": ARTIFACT_DIR / f"{STEM}_frame.stl",
        "slide_cartridge_step": ARTIFACT_DIR / f"{STEM}_slide_cartridge.step",
        "slide_cartridge_stl": ARTIFACT_DIR / f"{STEM}_slide_cartridge.stl",
        "petri_cartridge_step": ARTIFACT_DIR / f"{STEM}_petri_cartridge.step",
        "petri_cartridge_stl": ARTIFACT_DIR / f"{STEM}_petri_cartridge.stl",
        "slide_assembly_step": ARTIFACT_DIR / f"{STEM}_slide_assembly.step",
        "slide_assembly_stl": ARTIFACT_DIR / f"{STEM}_slide_assembly.stl",
        "petri_assembly_step": ARTIFACT_DIR / f"{STEM}_petri_assembly.step",
        "petri_assembly_stl": ARTIFACT_DIR / f"{STEM}_petri_assembly.stl",
        "exploded_step": ARTIFACT_DIR / f"{STEM}_exploded.step",
        "exploded_stl": ARTIFACT_DIR / f"{STEM}_exploded.stl",
        "top_alignment_svg": ARTIFACT_DIR / f"{STEM}_top_alignment.svg",
        "top_alignment_png": ARTIFACT_DIR / f"{STEM}_top_alignment.png",
        "slide_assembly_render_png": ARTIFACT_DIR / f"{STEM}_slide_assembly_render.png",
        "petri_assembly_render_png": ARTIFACT_DIR / f"{STEM}_petri_assembly_render.png",
        "exploded_render_png": ARTIFACT_DIR / f"{STEM}_exploded_render.png",
        "blender_scene": ARTIFACT_DIR / f"{STEM}.blend",
        "manifest": ARTIFACT_DIR / "manifest.json",
    }

    export_part(frame, paths["frame_step"], paths["frame_stl"])
    export_part(slide_cartridge, paths["slide_cartridge_step"], paths["slide_cartridge_stl"])
    export_part(petri_cartridge, paths["petri_cartridge_step"], paths["petri_cartridge_stl"])
    export_assembly(build_slide_assembly(), paths["slide_assembly_step"], paths["slide_assembly_stl"])
    export_assembly(build_petri_assembly(), paths["petri_assembly_step"], paths["petri_assembly_stl"])
    export_assembly(build_exploded_assembly(), paths["exploded_step"], paths["exploded_stl"])
    write_alignment_svg(paths["top_alignment_svg"])
    svg_to_png(paths["top_alignment_svg"], paths["top_alignment_png"])

    outputs = {name: repo_path(path) for name, path in paths.items() if name != "manifest"}
    outputs["manifest"] = repo_path(paths["manifest"])
    write_manifest(paths["manifest"], outputs)
    write_readme(DESIGN_DIR / "README.md", outputs)

    print(json.dumps({"parameters": PARAMS, "outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
