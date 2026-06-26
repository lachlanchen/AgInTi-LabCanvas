#!/usr/bin/env python3
"""Build a GT-090101-style 30 mm cage holder for the Lumileds PCB."""

from __future__ import annotations

import json
import math
from pathlib import Path

import cadquery as cq


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
REFERENCE_DIR = ROOT / "cad/references/hengyang-gt090101"


PARAMS = {
    "name": "lumileds_gt090101_cage",
    "reference_product": "Hengyang Optics GT-090101",
    "reference_page": "https://www.hengyangbuy.com/Product3?cid=790",
    "reference_stp": "cad/references/hengyang-gt090101/GT-090101.stp",
    "reference_pdf": "cad/references/hengyang-gt090101/GT-090101.pdf",
    "body_width_mm": 42.0,
    "body_height_mm": 42.0,
    "body_thickness_mm": 9.0,
    "corner_radius_mm": 2.0,
    "cage_rod_pitch_mm": 30.0,
    "cage_rod_clearance_diameter_mm": 6.35,
    "light_aperture_diameter_mm": 9.5,
    "front_chamfer_diameter_mm": 13.5,
    "pcb_outer_diameter_mm": 24.0,
    "pcb_pocket_diameter_mm": 24.6,
    "pcb_thickness_mm": 1.6,
    "pcb_pocket_depth_mm": 1.9,
    "pcb_mount_pattern_mm": 12.0,
    "pcb_mount_hole_diameter_mm": 2.35,
    "pcb_mount_counterbore_diameter_mm": 4.8,
    "pcb_mount_counterbore_depth_mm": 2.2,
    "connector_relief_width_mm": 10.5,
    "connector_relief_depth_mm": 2.4,
    "connector_relief_reach_mm": 16.0,
    "print_clearance_note": "Rod and PCB pockets include clearance for FDM/resin printed prototypes; tune after first print.",
}


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def z_cylinder(diameter: float, height: float, z_min: float) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z_min).circle(diameter / 2).extrude(height)


def z_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    x, y, z = center
    return cq.Workplane("XY").box(*size).translate((x, y, z))


def build_holder() -> cq.Workplane:
    p = PARAMS
    width = p["body_width_mm"]
    height = p["body_height_mm"]
    thickness = p["body_thickness_mm"]
    half_t = thickness / 2

    holder = cq.Workplane("XY").box(width, height, thickness)
    holder = holder.edges("|Z").fillet(p["corner_radius_mm"])

    cut_height = thickness + 2.0
    z_min = -half_t - 1.0

    holder = holder.cut(z_cylinder(p["light_aperture_diameter_mm"], cut_height, z_min))
    holder = holder.faces(">Z").workplane().hole(p["front_chamfer_diameter_mm"], 1.0)

    cage_half_pitch = p["cage_rod_pitch_mm"] / 2
    rod_points = [
        (-cage_half_pitch, -cage_half_pitch),
        (-cage_half_pitch, cage_half_pitch),
        (cage_half_pitch, -cage_half_pitch),
        (cage_half_pitch, cage_half_pitch),
    ]
    for x, y in rod_points:
        holder = holder.cut(
            z_cylinder(p["cage_rod_clearance_diameter_mm"], cut_height, z_min).translate((x, y, 0))
        )

    pocket = z_cylinder(p["pcb_pocket_diameter_mm"], p["pcb_pocket_depth_mm"], -half_t - 0.01)
    holder = holder.cut(pocket)

    mount_half = p["pcb_mount_pattern_mm"] / 2
    mount_points = [
        (-mount_half, -mount_half),
        (-mount_half, mount_half),
        (mount_half, -mount_half),
        (mount_half, mount_half),
    ]
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

    slot = z_box(
        (
            p["connector_relief_reach_mm"],
            p["connector_relief_width_mm"],
            p["connector_relief_depth_mm"],
        ),
        (
            width / 2 - p["connector_relief_reach_mm"] / 2,
            -1.25,
            -half_t + p["connector_relief_depth_mm"] / 2 - 0.01,
        ),
    )
    holder = holder.cut(slot)

    return holder


def build_pcb_proxy() -> cq.Workplane:
    p = PARAMS
    thickness = p["pcb_thickness_mm"]
    z = -p["body_thickness_mm"] / 2 + p["pcb_pocket_depth_mm"] - thickness / 2
    pcb = cq.Workplane("XY").circle(p["pcb_outer_diameter_mm"] / 2).extrude(thickness).translate((0, 0, z - thickness / 2))
    pcb = pcb.faces(">Z").workplane().circle(2.45).extrude(0.65)
    mount_half = p["pcb_mount_pattern_mm"] / 2
    for x in (-mount_half, mount_half):
        for y in (-mount_half, mount_half):
            pcb = pcb.cut(z_cylinder(2.2, thickness + 1.0, z - thickness / 2 - 0.2).translate((x, y, 0)))
    return pcb


def build_assembly() -> cq.Assembly:
    holder = build_holder()
    pcb = build_pcb_proxy()
    assembly = cq.Assembly(name="lumileds_gt090101_cage_assembly")
    assembly.add(holder, name="printed_cage_holder", color=cq.Color(0.02, 0.02, 0.02, 1.0))
    assembly.add(pcb, name="lumileds_pcb_proxy", color=cq.Color(0.0, 0.45, 0.12, 0.75))
    return assembly


def write_dimension_svg(path: Path) -> None:
    p = PARAMS
    w = p["body_width_mm"]
    h = p["body_height_mm"]
    scale = 8
    pad = 42
    svg_w = max(900, int(w * scale + pad * 2))
    svg_h = int(h * scale + pad * 2 + 110)

    def sx(x: float) -> float:
        return pad + (x + w / 2) * scale

    def sy(y: float) -> float:
        return pad + (h / 2 - y) * scale

    rod_r = p["cage_rod_clearance_diameter_mm"] / 2 * scale
    m2_r = p["pcb_mount_hole_diameter_mm"] / 2 * scale
    aperture_r = p["light_aperture_diameter_mm"] / 2 * scale
    pocket_r = p["pcb_pocket_diameter_mm"] / 2 * scale
    rod_half = p["cage_rod_pitch_mm"] / 2
    mount_half = p["pcb_mount_pattern_mm"] / 2
    y_text = int(h * scale + pad * 2 + 24)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-w/2)}" y="{sy(h/2)}" width="{w*scale}" height="{h*scale}" rx="{p["corner_radius_mm"]*scale}" fill="#111" stroke="#333" stroke-width="2"/>',
        f'<circle cx="{sx(0)}" cy="{sy(0)}" r="{pocket_r}" fill="none" stroke="#38a169" stroke-width="2" stroke-dasharray="6 4"/>',
        f'<circle cx="{sx(0)}" cy="{sy(0)}" r="{aperture_r}" fill="white" stroke="#ddd" stroke-width="2"/>',
    ]
    for x in (-rod_half, rod_half):
        for y in (-rod_half, rod_half):
            lines.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{rod_r}" fill="#f7fafc" stroke="#90cdf4" stroke-width="2"/>')
    for x in (-mount_half, mount_half):
        for y in (-mount_half, mount_half):
            lines.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{m2_r}" fill="#fefcbf" stroke="#d69e2e" stroke-width="2"/>')
    lines += [
        f'<text x="{pad}" y="{y_text}" font-family="Arial, sans-serif" font-size="14">GT-090101-style 30 mm cage holes: pitch {p["cage_rod_pitch_mm"]} mm, clearance Ø{p["cage_rod_clearance_diameter_mm"]} mm</text>',
        f'<text x="{pad}" y="{y_text+24}" font-family="Arial, sans-serif" font-size="14">Lumileds PCB: Ø{p["pcb_outer_diameter_mm"]} mm board pocket Ø{p["pcb_pocket_diameter_mm"]} mm, M2 holes on {p["pcb_mount_pattern_mm"]} x {p["pcb_mount_pattern_mm"]} mm pattern</text>',
        f'<text x="{pad}" y="{y_text+48}" font-family="Arial, sans-serif" font-size="14">Central LED aperture Ø{p["light_aperture_diameter_mm"]} mm; right-side rear relief for connector/cable</text>',
        "</svg>",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(path: Path) -> None:
    p = PARAMS
    rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in p.items())
    path.write_text(
        f"""# Lumileds GT-090101-Style Cage Holder

This is a printable 30 mm cage-compatible holder for the Lumileds round PCB.
It borrows the GT-090101 cage interface, but replaces the large waveplate
aperture with a smaller LED aperture and a rear PCB pocket.

## Reference

- Product: Hengyang Optics GT-090101 30 mm cage waveplate/polarizer holder.
- Public product page: {p["reference_page"]}
- Downloaded reference STEP: `{p["reference_stp"]}`
- Downloaded reference PDF: `{p["reference_pdf"]}`
- Reference dimensions checked from STEP: about 40.0 x 41.5 x 18.0 mm.
- Product data: 30 mm cage, four Ø6 mm rod holes, Ø25.4 mm optic clamp,
  Ø23 mm clear aperture, SM1 lock ring, aluminum black anodized.

## Lumileds PCB Interface

- Board source: `pcb/lumileds-no-resistor/lumileds-no-resistor.kicad_pcb`.
- Board outline: Ø24 mm circle.
- Mount holes: four Ø2.2 mm holes on a 12 x 12 mm square pattern.
- Holder pocket: Ø24.6 mm x 1.9 mm rear pocket with M2 clearance holes and
  counterbores.

## Parameters

| Name | Value |
| --- | --- |
{rows}

## Notes

- The central aperture is Ø9.5 mm, not the GT-090101 Ø23 mm aperture, because
  the Lumileds board's four M2 holes sit inside a 12 x 12 mm pattern. A Ø23 mm
  aperture would remove the material needed to mount the PCB.
- The four cage holes keep the 30 mm pitch and use Ø6.35 mm printed clearance.
- Tune rod and PCB pocket clearances after the first print if the printer runs
  tight or loose.
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    holder = build_holder()
    assembly = build_assembly()
    holder_step = ARTIFACT_DIR / "lumileds_gt090101_cage_holder.step"
    holder_stl = ARTIFACT_DIR / "lumileds_gt090101_cage_holder.stl"
    assembly_step = ARTIFACT_DIR / "lumileds_gt090101_cage_assembly.step"
    assembly_stl = ARTIFACT_DIR / "lumileds_gt090101_cage_assembly.stl"
    cq.exporters.export(holder, str(holder_step))
    cq.exporters.export(holder, str(holder_stl), tolerance=0.08, angularTolerance=0.12)
    assembly.save(str(assembly_step))
    cq.exporters.export(assembly.toCompound(), str(assembly_stl), tolerance=0.08, angularTolerance=0.12)
    write_dimension_svg(ARTIFACT_DIR / "lumileds_gt090101_cage_dimension_sketch.svg")
    write_readme(DESIGN_DIR / "README.md")
    manifest = {
        "parameters": PARAMS,
        "artifacts": {
            "holder_step": repo_path(holder_step),
            "holder_stl": repo_path(holder_stl),
            "assembly_step": repo_path(assembly_step),
            "assembly_stl": repo_path(assembly_stl),
            "dimension_svg": repo_path(ARTIFACT_DIR / "lumileds_gt090101_cage_dimension_sketch.svg"),
        },
    }
    (ARTIFACT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
