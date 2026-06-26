#!/usr/bin/env python3
"""Build an independent Lumileds holder using Hengyang 30 mm cage geometry."""

from __future__ import annotations

import json
from pathlib import Path

import cadquery as cq


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"


PARAMS = {
    "name": "lumileds_hengyang_30mm_cage_holder",
    "reference_family": "Hengyang Optics 30 mm cage components",
    "primary_reference": "GT-090101",
    "reference_folder": "cad/references/hengyang-optics",
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
    "rear_connector_relief_width_mm": 10.5,
    "rear_connector_relief_height_mm": 4.2,
    "rear_connector_relief_reach_mm": 18.0,
    "bottom_post_mount_hole_diameter_mm": 4.2,
    "bottom_post_mount_depth_mm": 7.0,
    "bottom_post_mount_note": "M4 clearance pilot for optional post/adapter; tap or heat-set after print if needed.",
    "print_clearance_note": "Cage and PCB pockets include practical print clearance; tune after test print.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z_min).circle(diameter / 2).extrude(height)


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


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

    # Lighten the printed body while leaving local material around rods and PCB screws.
    corner_keep = p["rod_boss_diameter_mm"] / 2.0 + 1.8
    relief_w = (width - p["cage_rod_pitch_mm"]) - corner_keep
    relief_h = 6.2
    for y in (-rod_half, rod_half):
        holder = holder.cut(z_box((max(relief_w, 3.0), relief_h, cut_height), (0, y, 0)))
    for x in (-rod_half, rod_half):
        holder = holder.cut(z_box((relief_h, max(height - p["cage_rod_pitch_mm"] - corner_keep, 3.0), cut_height), (x, 0, 0)))

    for x, y in rod_points:
        holder = holder.cut(
            z_cylinder(p["cage_rod_clearance_diameter_mm"], cut_height, z_min).translate((x, y, 0))
        )

    holder = holder.cut(z_cylinder(p["light_aperture_diameter_mm"], cut_height, z_min))
    holder = holder.faces(">Z").workplane().hole(p["front_lip_diameter_mm"], p["front_lip_depth_mm"])

    holder = holder.cut(z_cylinder(p["pcb_pocket_diameter_mm"], p["pcb_pocket_depth_mm"], -half_t - 0.01))

    mount_half = p["pcb_mount_pattern_mm"] / 2.0
    mount_points = [(x, y) for x in (-mount_half, mount_half) for y in (-mount_half, mount_half)]
    for x, y in mount_points:
        holder = holder.cut(
            z_cylinder(p["pcb_mount_hole_diameter_mm"], cut_height, z_min).translate((x, y, 0))
        )
        holder = holder.cut(
            z_cylinder(
                p["pcb_mount_counterbore_diameter_mm"],
                p["pcb_mount_counterbore_depth_mm"],
                -half_t - 0.01,
            ).translate((x, y, 0))
        )

    # Rear/right cable relief for the horizontal pin header on the Lumileds PCB.
    relief = z_box(
        (
            p["rear_connector_relief_reach_mm"],
            p["rear_connector_relief_width_mm"],
            p["rear_connector_relief_height_mm"],
        ),
        (
            width / 2.0 - p["rear_connector_relief_reach_mm"] / 2.0,
            -1.25,
            -half_t + p["rear_connector_relief_height_mm"] / 2.0 - 0.02,
        ),
    )
    holder = holder.cut(relief)

    # Optional lower post mount pilot, aligned with the same optical center plane.
    holder = holder.cut(
        cq.Workplane("XZ")
        .workplane(offset=-height / 2.0 - 0.01)
        .center(0, 0)
        .circle(p["bottom_post_mount_hole_diameter_mm"] / 2.0)
        .extrude(p["bottom_post_mount_depth_mm"])
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
            pcb = pcb.cut(
                z_cylinder(2.2, p["pcb_thickness_mm"] + 1.0, pcb_center_z - p["pcb_thickness_mm"] / 2.0 - 0.2)
                .translate((x, y, 0))
            )
    return pcb


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name="lumileds_hengyang_30mm_cage_holder_assembly")
    assembly.add(build_holder(), name="printed_lumileds_holder", color=cq.Color(0.02, 0.02, 0.02, 1.0))
    assembly.add(build_pcb_proxy(), name="lumileds_pcb_proxy", color=cq.Color(0.0, 0.45, 0.12, 0.75))
    return assembly


def write_dimension_svg(path: Path) -> None:
    p = PARAMS
    scale = 9
    pad = 48
    w = p["body_width_mm"]
    h = p["body_height_mm"]
    svg_w = int(w * scale + pad * 2 + 300)
    svg_h = int(h * scale + pad * 2 + 150)

    def sx(x: float) -> float:
        return pad + (x + w / 2.0) * scale

    def sy(y: float) -> float:
        return pad + (h / 2.0 - y) * scale

    rod_half = p["cage_rod_pitch_mm"] / 2.0
    mount_half = p["pcb_mount_pattern_mm"] / 2.0
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-w/2)}" y="{sy(h/2)}" width="{w*scale}" height="{h*scale}" rx="{p["corner_radius_mm"]*scale}" fill="#151515" stroke="#333" stroke-width="2"/>',
        f'<circle cx="{sx(0)}" cy="{sy(0)}" r="{p["pcb_pocket_diameter_mm"]/2*scale}" fill="none" stroke="#48bb78" stroke-width="2" stroke-dasharray="7 4"/>',
        f'<circle cx="{sx(0)}" cy="{sy(0)}" r="{p["light_aperture_diameter_mm"]/2*scale}" fill="white" stroke="#edf2f7" stroke-width="2"/>',
    ]
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            lines.append(
                f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{p["cage_rod_clearance_diameter_mm"]/2*scale}" fill="#eef6ff" stroke="#63b3ed" stroke-width="2"/>'
            )
    for x in (-mount_half, mount_half):
        for y in (-mount_half, mount_half):
            lines.append(
                f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{p["pcb_mount_hole_diameter_mm"]/2*scale}" fill="#fff7bf" stroke="#d69e2e" stroke-width="2"/>'
            )
    legend_x = int(w * scale + pad + 36)
    legend_y = pad
    text = [
        "Independent Lumileds holder",
        f"Envelope: {w} x {h} x {p['body_thickness_mm']} mm",
        f"Cage rods: 30 mm pitch, Ø{p['cage_rod_clearance_diameter_mm']} clearance",
        f"PCB pocket: Ø{p['pcb_pocket_diameter_mm']} x {p['pcb_pocket_depth_mm']} mm",
        f"PCB screws: M2 clearance on {p['pcb_mount_pattern_mm']} x {p['pcb_mount_pattern_mm']} mm",
        f"LED aperture: Ø{p['light_aperture_diameter_mm']} mm",
        "Reference: GT-090101/HCP/HCT geometry only",
    ]
    for i, row in enumerate(text):
        size = 17 if i == 0 else 14
        weight = "700" if i == 0 else "400"
        lines.append(
            f'<text x="{legend_x}" y="{legend_y + i*26}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" fill="#1a202c">{row}</text>'
        )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# Lumileds Hengyang 30 mm Cage Holder

This is a new independent holder for the Lumileds no-resistor round PCB. It uses
Hengyang Optics 30 mm cage dimensions as references, especially GT-090101 and
HCT rods, but it does not copy the GT-090101 rotating waveplate mechanics.

## Design Intent

- Share the same four-rod 30 mm cage setup as Hengyang 30 mm cage parts.
- Hold the Lumileds PCB from the rear with a printable pocket and M2 screws.
- Keep the center aperture small enough to preserve screw material around the
  12 x 12 mm Lumileds mounting pattern.
- Provide an optional bottom M4 pilot for a post or adapter, but the primary
  mechanical reference is the cage rod interface.

## Reference Materials

- Main reference folder: `{PARAMS['reference_folder']}`
- Primary reference: GT-090101 30 mm cage waveplate/polarizer holder.
- Similar references: HCP/HCP-08/GT-0803 lens holders, HCM-3 beam-splitter
  holders, HCM-3 45-degree flat holders, HKCB1PM right-angle mirror holder,
  and HCT 6 mm cage rods.

## Outputs

| Output | Path |
| --- | --- |
{chr(10).join(f"| {name} | `{path}` |" for name, path in outputs.items())}

## Parameters

| Name | Value |
| --- | --- |
{rows}

## Notes

- The holder envelope is close to the GT-090101 measured reference envelope, but
  thickness is reduced because this is a fixed LED PCB holder rather than a
  rotating optic mount.
- The shared cage geometry is four rod holes on 30 mm pitch, not the internal
  Ø25.4 mm optic clamp.
- Print one prototype before committing to metal machining; tune rod and PCB
  pocket clearances from that first fit test.
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    holder = build_holder()
    assembly = build_assembly()

    holder_step = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder.step"
    holder_stl = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder.stl"
    assembly_step = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder_assembly.step"
    assembly_stl = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder_assembly.stl"
    sketch_svg = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder_dimension_sketch.svg"
    sketch_png = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder_dimension_sketch.png"
    sketch_pdf = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder_dimension_sketch.pdf"
    render_png = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder_render.png"
    blend_file = ARTIFACT_DIR / "lumileds_hengyang_30mm_cage_holder.blend"

    cq.exporters.export(holder, str(holder_step))
    cq.exporters.export(holder, str(holder_stl))
    assembly_compound = assembly.toCompound()
    cq.exporters.export(assembly_compound, str(assembly_step))
    cq.exporters.export(assembly_compound, str(assembly_stl))
    write_dimension_svg(sketch_svg)

    outputs = {
        "holder STEP": repo_path(holder_step),
        "holder STL": repo_path(holder_stl),
        "assembly STEP": repo_path(assembly_step),
        "assembly STL": repo_path(assembly_stl),
        "dimension sketch SVG": repo_path(sketch_svg),
        "dimension sketch PNG": repo_path(sketch_png),
        "dimension sketch PDF": repo_path(sketch_pdf),
        "inspection render PNG": repo_path(render_png),
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
