#!/usr/bin/env python3
"""Build an OpenHI-fit C-mount holder for a GY-302 BH1750 light sensor module."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import cadquery as cq
from cadquery import exporters


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "gy302_bh1750_cmount_light_sensor_holder"
REFERENCE_DIR = ROOT / "cad/references/gy302-bh1750-light-sensor"


PARAMS = {
    "name": STEM,
    "design_date": "2026-07-03",
    "units": "mm",
    "cmount_standard_note": "Industrial C-mount is 1-32 UNS, 0.79375 mm pitch; this part follows the local OpenHI printed 0.8 mm pitch convention.",
    "openhi_female_root_diameter_mm": 24.8,
    "openhi_female_thread_cutter_crest_diameter_mm": 25.6,
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.4,
    "thread_tooth_base_mm": 0.8,
    "female_socket_length_mm": 12.0,
    "female_thread_length_mm": 10.0,
    "socket_outer_diameter_mm": 34.0,
    "body_tube_outer_diameter_mm": 30.0,
    "optical_bore_diameter_mm": 8.0,
    "tube_length_mm": 18.0,
    "sensor_plate_thickness_mm": 7.0,
    "sensor_plate_width_y_mm": 42.0,
    "sensor_plate_height_z_mm": 38.0,
    "sensor_plate_center_z_mm": 0.0,
    "gy302_board_width_y_mm": 14.0,
    "gy302_board_height_z_mm": 19.0,
    "board_size_source_note": "Common GY-302 BH1750 listings give about 13.9 x 18.5 mm; this design uses a 14 x 19 mm parametric tray.",
    "board_pocket_clearance_total_mm": 0.8,
    "board_pocket_depth_mm": 2.0,
    "board_thickness_mm": 1.6,
    "bh1750_package_width_y_mm": 2.0,
    "bh1750_package_height_z_mm": 1.6,
    "bh1750_package_thickness_x_mm": 0.8,
    "bh1750_pd_area_width_y_mm": 0.25,
    "bh1750_pd_area_height_z_mm": 0.30,
    "bh1750_sensor_offset_y_mm": 0.0,
    "bh1750_sensor_offset_z_mm": 0.0,
    "board_mount_hole_diameter_mm": 3.0,
    "board_mount_hole_clearance_diameter_mm": 3.3,
    "board_mount_hole_y_abs_mm": 4.0,
    "board_mount_hole_z_mm": 6.2,
    "header_relief_width_y_mm": 13.0,
    "header_relief_height_z_mm": 7.0,
    "header_relief_z_mm": -7.4,
    "source_local_datasheet": "cad/references/gy302-bh1750-light-sensor/1. 数据手册/BH1750FVI.pdf",
    "source_local_schematic": "cad/references/gy302-bh1750-light-sensor/2. 原理图/GY-302原理图.jpg",
    "source_module_size": "https://www.handsontec.com/dataspecs/sensor/BH1750%20Light%20Sensor.pdf",
}


THREAD_OVERLAP = 0.08


def repo_path(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def x_cylinder(diameter: float, length: float, x0: float) -> cq.Workplane:
    return cq.Workplane("YZ").workplane(offset=x0).circle(diameter / 2.0).extrude(length)


def x_box(center: tuple[float, float, float], size: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def x_clip_box(x0: float, length: float, span: float) -> cq.Workplane:
    return cq.Workplane("XY").box(length, span, span, centered=(False, True, True)).translate((x0, 0, 0))


def external_thread_brep(x0: float, length: float, root_d: float, lefthand: bool = False) -> cq.Workplane:
    root_r = root_d / 2.0 - THREAD_OVERLAP
    crest_d = root_d + 2.0 * PARAMS["thread_tooth_height_mm"]
    path = cq.Wire.makeHelix(
        PARAMS["thread_pitch_mm"],
        length,
        root_r,
        center=(x0, 0, 0),
        dir=(1, 0, 0),
        lefthand=lefthand,
    )
    profile = (
        cq.Workplane("XY")
        .center(x0, root_r)
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


def total_length() -> float:
    return PARAMS["female_socket_length_mm"] + PARAMS["tube_length_mm"] + PARAMS["sensor_plate_thickness_mm"]


def board_reference_geometry() -> dict[str, object]:
    board_w = PARAMS["gy302_board_width_y_mm"]
    board_h = PARAMS["gy302_board_height_z_mm"]
    sensor_y = PARAMS["bh1750_sensor_offset_y_mm"]
    sensor_z = PARAMS["bh1750_sensor_offset_z_mm"]
    bounds = {
        "y_min": round(-board_w / 2.0 - sensor_y, 4),
        "y_max": round(board_w / 2.0 - sensor_y, 4),
        "z_min": round(-board_h / 2.0 - sensor_z, 4),
        "z_max": round(board_h / 2.0 - sensor_z, 4),
    }
    holes = [
        {
            "name": "mount_left",
            "y": round(-PARAMS["board_mount_hole_y_abs_mm"] - sensor_y, 4),
            "z": round(PARAMS["board_mount_hole_z_mm"] - sensor_z, 4),
            "source_diameter_mm": PARAMS["board_mount_hole_diameter_mm"],
            "cut_diameter_mm": PARAMS["board_mount_hole_clearance_diameter_mm"],
        },
        {
            "name": "mount_right",
            "y": round(PARAMS["board_mount_hole_y_abs_mm"] - sensor_y, 4),
            "z": round(PARAMS["board_mount_hole_z_mm"] - sensor_z, 4),
            "source_diameter_mm": PARAMS["board_mount_hole_diameter_mm"],
            "cut_diameter_mm": PARAMS["board_mount_hole_clearance_diameter_mm"],
        },
    ]
    return {
        "board_center_relative_to_sensor_mm": {
            "y": round(-sensor_y, 4),
            "z": round(-sensor_z, 4),
        },
        "board_bounds_relative_to_sensor_mm": bounds,
        "mounting_holes_relative_to_sensor_mm": holes,
        "notes": [
            PARAMS["board_size_source_note"],
            "The holder centers the BH1750 light-sensitive area on the optical axis. If the real module sensor is offset, update bh1750_sensor_offset_y_mm/z_mm and regenerate.",
        ],
    }


def female_thread_cutter() -> cq.Workplane:
    return external_thread_brep(
        -0.2,
        PARAMS["female_thread_length_mm"],
        PARAMS["openhi_female_root_diameter_mm"],
        lefthand=True,
    )


def female_bore_cutter(extra: float = 0.4) -> cq.Workplane:
    return x_cylinder(
        PARAMS["openhi_female_root_diameter_mm"],
        PARAMS["female_socket_length_mm"] + extra,
        -extra / 2.0,
    )


def board_pocket_cutter() -> cq.Workplane:
    ref = board_reference_geometry()
    center = ref["board_center_relative_to_sensor_mm"]  # type: ignore[index]
    pocket_w = PARAMS["gy302_board_width_y_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    pocket_h = PARAMS["gy302_board_height_z_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    depth = PARAMS["board_pocket_depth_mm"]
    return x_box(
        (total_length() - depth / 2.0 + 0.05, center["y"], center["z"]),
        (depth + 0.2, pocket_w, pocket_h),
    )


def board_mount_hole_cutter(y: float, z: float) -> cq.Workplane:
    x0 = PARAMS["female_socket_length_mm"] + PARAMS["tube_length_mm"] - 1.0
    length = PARAMS["sensor_plate_thickness_mm"] + 2.5
    return x_cylinder(PARAMS["board_mount_hole_clearance_diameter_mm"], length, x0).translate((0, y, z))


def header_relief_cutter() -> cq.Workplane:
    depth = PARAMS["board_pocket_depth_mm"]
    return x_box(
        (
            total_length() - depth / 2.0 + 0.25,
            0.0,
            PARAMS["header_relief_z_mm"],
        ),
        (
            depth + 1.0,
            PARAMS["header_relief_width_y_mm"],
            PARAMS["header_relief_height_z_mm"],
        ),
    )


def build_holder() -> cq.Workplane:
    socket = x_cylinder(PARAMS["socket_outer_diameter_mm"], PARAMS["female_socket_length_mm"], 0.0)
    tube = x_cylinder(
        PARAMS["body_tube_outer_diameter_mm"],
        PARAMS["tube_length_mm"] + 0.25,
        PARAMS["female_socket_length_mm"] - 0.25,
    )
    plate_x0 = PARAMS["female_socket_length_mm"] + PARAMS["tube_length_mm"]
    plate = x_box(
        (plate_x0 + PARAMS["sensor_plate_thickness_mm"] / 2.0, 0.0, PARAMS["sensor_plate_center_z_mm"]),
        (
            PARAMS["sensor_plate_thickness_mm"],
            PARAMS["sensor_plate_width_y_mm"],
            PARAMS["sensor_plate_height_z_mm"],
        ),
    )
    bridge = x_box(
        (PARAMS["female_socket_length_mm"] + PARAMS["tube_length_mm"] / 2.0, 0.0, 0.0),
        (PARAMS["tube_length_mm"] + 0.8, 30.0, 28.0),
    )
    holder = socket.union(tube).union(bridge).union(plate)
    holder = holder.edges("|X").fillet(0.8)
    holder = holder.cut(female_bore_cutter()).cut(female_thread_cutter())
    holder = holder.cut(x_cylinder(PARAMS["optical_bore_diameter_mm"], total_length() + 2.0, -1.0))
    holder = holder.cut(board_pocket_cutter()).cut(header_relief_cutter())
    ref = board_reference_geometry()
    for hole in ref["mounting_holes_relative_to_sensor_mm"]:  # type: ignore[index]
        holder = holder.cut(board_mount_hole_cutter(hole["y"], hole["z"]))
    return holder


def build_board_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    center = ref["board_center_relative_to_sensor_mm"]  # type: ignore[index]
    total_x = total_length()
    board = x_box(
        (
            total_x + PARAMS["board_thickness_mm"] / 2.0 + 0.05,
            center["y"],
            center["z"],
        ),
        (
            PARAMS["board_thickness_mm"],
            PARAMS["gy302_board_width_y_mm"],
            PARAMS["gy302_board_height_z_mm"],
        ),
    )
    for hole in ref["mounting_holes_relative_to_sensor_mm"]:  # type: ignore[index]
        board = board.cut(
            x_cylinder(PARAMS["board_mount_hole_diameter_mm"], PARAMS["board_thickness_mm"] + 0.4, total_x - 0.15).translate(
                (0, hole["y"], hole["z"])
            )
        )
    return board


def build_sensor_proxy() -> cq.Workplane:
    total_x = total_length()
    package = x_box(
        (
            total_x + PARAMS["board_thickness_mm"] + PARAMS["bh1750_package_thickness_x_mm"] / 2.0,
            0.0,
            0.0,
        ),
        (
            PARAMS["bh1750_package_thickness_x_mm"],
            PARAMS["bh1750_package_width_y_mm"],
            PARAMS["bh1750_package_height_z_mm"],
        ),
    )
    pd = x_box(
        (
            total_x + PARAMS["board_thickness_mm"] + PARAMS["bh1750_package_thickness_x_mm"] + 0.06,
            0.0,
            0.0,
        ),
        (
            0.12,
            PARAMS["bh1750_pd_area_width_y_mm"],
            PARAMS["bh1750_pd_area_height_z_mm"],
        ),
    )
    return package.union(pd)


def build_header_proxy() -> cq.Workplane:
    total_x = total_length()
    return x_box(
        (
            total_x + PARAMS["board_thickness_mm"] + 3.1,
            0.0,
            PARAMS["header_relief_z_mm"],
        ),
        (6.4, PARAMS["header_relief_width_y_mm"], 4.0),
    )


def build_axis_proxy() -> cq.Workplane:
    return x_cylinder(1.0, total_length() + 9.0, -4.0)


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_holder(), name="printed_holder_openhi_24p8_receiver", color=cq.Color(0.08, 0.08, 0.08, 1.0))
    assembly.add(build_board_proxy(), name="gy302_bh1750_board_proxy", color=cq.Color(0.0, 0.20, 0.55, 0.72))
    assembly.add(build_sensor_proxy(), name="bh1750_sensor_centered_on_optical_axis", color=cq.Color(0.08, 0.10, 0.04, 1.0))
    assembly.add(build_header_proxy(), name="one_by_five_header_clearance_proxy", color=cq.Color(0.95, 0.92, 0.82, 0.65))
    assembly.add(female_thread_cutter(), name="female_thread_boolean_cutter", color=cq.Color(0.9, 0.2, 0.1, 0.35))
    assembly.add(build_axis_proxy(), name="optical_axis_proxy", color=cq.Color(1.0, 0.72, 0.08, 0.6))
    return assembly


def write_alignment_svg(path: Path) -> None:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_sensor_mm"]  # type: ignore[index]
    scale = 11.0
    pad = 58.0
    legend_w = 600.0
    view_w = PARAMS["sensor_plate_width_y_mm"]
    view_h = PARAMS["sensor_plate_height_z_mm"]
    svg_w = int(view_w * scale + pad * 2 + legend_w)
    svg_h = int(view_h * scale + pad * 2)

    def sx(y: float) -> float:
        return pad + (y + view_w / 2.0) * scale

    def sy(z: float) -> float:
        top = view_h / 2.0
        return pad + (top - z) * scale

    def circle(y: float, z: float, diameter: float, fill: str, stroke: str, label: str = "") -> str:
        text = ""
        if label:
            text = f'<text x="{sx(y)+8:.2f}" y="{sy(z)-8:.2f}" font-family="Arial" font-size="12" fill="#1a202c">{label}</text>'
        return f'<circle cx="{sx(y):.2f}" cy="{sy(z):.2f}" r="{diameter/2*scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>{text}'

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-view_w/2):.2f}" y="{sy(view_h/2):.2f}" width="{view_w*scale:.2f}" height="{view_h*scale:.2f}" rx="8" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        f'<rect x="{sx(bounds["y_min"]):.2f}" y="{sy(bounds["z_max"]):.2f}" width="{(bounds["y_max"]-bounds["y_min"])*scale:.2f}" height="{(bounds["z_max"]-bounds["z_min"])*scale:.2f}" fill="#e6f0ff" stroke="#2b6cb0" stroke-width="2" stroke-dasharray="8 5"/>',
        f'<rect x="{sx(-PARAMS["header_relief_width_y_mm"]/2):.2f}" y="{sy(PARAMS["header_relief_z_mm"] + PARAMS["header_relief_height_z_mm"]/2):.2f}" width="{PARAMS["header_relief_width_y_mm"]*scale:.2f}" height="{PARAMS["header_relief_height_z_mm"]*scale:.2f}" fill="#fff5f5" stroke="#c53030" stroke-width="2" stroke-dasharray="5 4"/>',
        f'<line x1="{sx(-view_w/2):.2f}" y1="{sy(0):.2f}" x2="{sx(view_w/2):.2f}" y2="{sy(0):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        f'<line x1="{sx(0):.2f}" y1="{sy(view_h/2):.2f}" x2="{sx(0):.2f}" y2="{sy(-view_h/2):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        circle(0.0, 0.0, PARAMS["optical_bore_diameter_mm"], "#fff7d6", "#d69e2e", "optical axis / BH1750"),
        f'<rect x="{sx(-PARAMS["bh1750_package_width_y_mm"]/2):.2f}" y="{sy(PARAMS["bh1750_package_height_z_mm"]/2):.2f}" width="{PARAMS["bh1750_package_width_y_mm"]*scale:.2f}" height="{PARAMS["bh1750_package_height_z_mm"]*scale:.2f}" fill="#1a202c" stroke="#1a202c" stroke-width="1.5"/>',
        f'<rect x="{sx(-PARAMS["bh1750_pd_area_width_y_mm"]/2):.2f}" y="{sy(PARAMS["bh1750_pd_area_height_z_mm"]/2):.2f}" width="{PARAMS["bh1750_pd_area_width_y_mm"]*scale:.2f}" height="{PARAMS["bh1750_pd_area_height_z_mm"]*scale:.2f}" fill="#ffe066" stroke="#d69e2e" stroke-width="1"/>',
    ]
    for hole in ref["mounting_holes_relative_to_sensor_mm"]:  # type: ignore[index]
        lines.append(circle(hole["y"], hole["z"], hole["cut_diameter_mm"], "#edf2f7", "#4a5568", hole["name"]))

    legend_x = pad + view_w * scale + 36.0
    legend = [
        "GY-302 BH1750 C-mount light sensor holder",
        "View: rear tray, looking along optical axis",
        "Black rectangle: BH1750 package centered on axis",
        "Yellow mark: 0.25 x 0.3 mm photodiode area from datasheet",
        "Blue dashed rectangle: 14 x 19 mm GY-302 tray + clearance",
        "Gray holes: estimated board mounting holes",
        "Red dashed slot: 1x5 header/cable relief",
        "C-mount side: OpenHI 24.8 mm female receiver, 0.8 mm pitch thread",
    ]
    for index, text in enumerate(legend):
        size = 17 if index == 0 else 13
        weight = "700" if index == 0 else "400"
        lines.append(
            f'<text x="{legend_x:.2f}" y="{pad + index*25:.2f}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="#1a202c">{text}</text>'
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
    python = shutil.which("python")
    if python:
        script = (
            "import cairosvg, sys; "
            "cairosvg.svg2png(url=sys.argv[1], write_to=sys.argv[2], output_width=1800); "
            "cairosvg.svg2pdf(url=sys.argv[1], write_to=sys.argv[3])"
        )
        result = subprocess.run(
            [python, "-c", script, str(svg_path), str(svg_path.with_suffix(".png")), str(svg_path.with_suffix(".pdf"))],
            check=False,
        )
        if result.returncode == 0:
            return
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run([rsvg, "-f", "png", "-o", str(svg_path.with_suffix(".png")), str(svg_path)], check=False)
        subprocess.run([rsvg, "-f", "pdf", "-o", str(svg_path.with_suffix(".pdf")), str(svg_path)], check=False)
        return
    convert = shutil.which("convert")
    if convert:
        subprocess.run([convert, str(svg_path), str(svg_path.with_suffix(".png"))], check=False)


def write_readme(path: Path, outputs: dict[str, str]) -> None:
    ref = board_reference_geometry()
    hole_rows = "\n".join(
        f"| {hole['name']} | `{hole['y']}` | `{hole['z']}` | `{hole['cut_diameter_mm']}` |"
        for hole in ref["mounting_holes_relative_to_sensor_mm"]  # type: ignore[index]
    )
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    params_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# GY-302 BH1750 C-Mount Light Sensor Holder

New independent CAD design for holding a GY-302 BH1750 light intensity module
behind an OpenHI-print-fit C-mount receiver. Older CAD designs are not modified.

## Source References

- Local reference snapshot: `{repo_path(REFERENCE_DIR)}`
- Local BH1750 datasheet: `{PARAMS['source_local_datasheet']}`
- Local GY-302 schematic: `{PARAMS['source_local_schematic']}`
- Public module size reference: `{PARAMS['source_module_size']}`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The local files include the BH1750 datasheet and GY-302 schematic but no module
STEP/DXF/mechanical drawing. Public GY-302 listings commonly give about
`13.9 x 18.5 mm`; this design uses a parametric `14 x 19 mm` board tray.

## Design Intent

- Put the BH1750 photodiode area on the C-mount optical axis.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Provide a rear GY-302 tray with estimated two-hole board mounting and 1x5
  header/cable relief.
- Keep board size, hole locations, and sensor offset editable in this script for
  caliper correction after checking the physical module.

## Geometry Used

Board center relative to the BH1750 photodiode datum:

```json
{json.dumps(ref['board_center_relative_to_sensor_mm'], indent=2)}
```

Mounting holes:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
{hole_rows}

## Outputs

| Output | Path |
| --- | --- |
{output_rows}

## Parameters

| Parameter | Value |
| --- | --- |
{params_rows}

## Regenerate

```bash
cad/.conda/cad-python/bin/python cad/designs/gy302_bh1750_cmount_light_sensor_holder/build_gy302_bh1750_cmount_light_sensor_holder.py
blender --background --python cad/designs/gy302_bh1750_cmount_light_sensor_holder/render_gy302_bh1750_cmount_light_sensor_holder.py
```
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    holder = build_holder()
    assembly = build_assembly()
    cutter = female_thread_cutter()
    board = build_board_proxy()

    holder_step = ARTIFACT_DIR / f"{STEM}.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}.stl"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    cutter_step = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.step"
    cutter_stl = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.stl"
    board_proxy_step = ARTIFACT_DIR / f"{STEM}_board_proxy.step"
    board_proxy_stl = ARTIFACT_DIR / f"{STEM}_board_proxy.stl"
    alignment_svg = ARTIFACT_DIR / f"{STEM}_rear_alignment.svg"
    manifest_path = ARTIFACT_DIR / "manifest.json"

    exporters.export(holder, str(holder_step))
    exporters.export(holder, str(holder_stl))
    exporters.export(cutter, str(cutter_step))
    exporters.export(cutter, str(cutter_stl))
    exporters.export(board, str(board_proxy_step))
    exporters.export(board, str(board_proxy_stl))
    assembly.save(str(assembly_step))
    assembly.save(str(assembly_stl))
    write_alignment_svg(alignment_svg)
    convert_svg(alignment_svg)

    outputs = {
        "holder_step": repo_path(holder_step),
        "holder_stl": repo_path(holder_stl),
        "assembly_step": repo_path(assembly_step),
        "assembly_stl": repo_path(assembly_stl),
        "thread_cutter_step": repo_path(cutter_step),
        "thread_cutter_stl": repo_path(cutter_stl),
        "board_proxy_step": repo_path(board_proxy_step),
        "board_proxy_stl": repo_path(board_proxy_stl),
        "rear_alignment_svg": repo_path(alignment_svg),
        "rear_alignment_png": repo_path(alignment_svg.with_suffix(".png")),
        "rear_alignment_pdf": repo_path(alignment_svg.with_suffix(".pdf")),
        "render_png": repo_path(ARTIFACT_DIR / f"{STEM}_render.png"),
        "rear_alignment_render_png": repo_path(ARTIFACT_DIR / f"{STEM}_rear_alignment_render.png"),
        "blend": repo_path(ARTIFACT_DIR / f"{STEM}.blend"),
    }
    manifest = {
        "name": STEM,
        "params": PARAMS,
        "reference_geometry": board_reference_geometry(),
        "outputs": outputs,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(DESIGN_DIR / "README.md", outputs | {"manifest": repo_path(manifest_path)})


if __name__ == "__main__":
    main()
