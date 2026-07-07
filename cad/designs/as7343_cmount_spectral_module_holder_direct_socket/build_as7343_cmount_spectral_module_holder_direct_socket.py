#!/usr/bin/env python3
"""Build a direct-socket OpenHI-fit C-mount holder for an AS7343 spectral module."""

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
STEM = "as7343_cmount_spectral_module_holder_direct_socket"
REFERENCE_DIR = ROOT / "cad/references/as7343-spectral-analysis-module"


PARAMS = {
    "name": STEM,
    "design_variant": "direct C-mount socket to sensor holder plate; no bridge block and no middle tube",
    "design_date": "2026-07-03",
    "units": "mm",
    "cmount_standard_note": "Industrial C-mount is 1-32 UNS, 0.79375 mm pitch; this part follows the local OpenHI printed 0.8 mm pitch convention.",
    "openhi_female_root_diameter_mm": 24.8,
    "openhi_female_thread_cutter_crest_diameter_mm": 25.6,
    "thread_pitch_mm": 0.8,
    "thread_tooth_height_mm": 0.4,
    "thread_tooth_base_mm": 0.8,
    "female_socket_length_mm": 12.0,
    "female_thread_start_mm": 0.2,
    "female_thread_length_mm": 10.0,
    "socket_outer_diameter_mm": 34.0,
    "optical_bore_diameter_mm": 8.0,
    "omitted_middle_connector_length_mm": 0.0,
    "sensor_plate_thickness_mm": 7.0,
    "sensor_plate_width_y_mm": 50.0,
    "sensor_plate_height_z_mm": 42.0,
    "sensor_plate_center_z_mm": 0.0,
    "estimated_module_board_width_y_mm": 23.0,
    "estimated_module_board_height_z_mm": 15.0,
    "module_board_size_source": "User-corrected AS7343 module geometry: PCB is 15 x 23 mm; pin sockets are on the negative-Y short edge; AS7343 package is centered across the 15 mm short edge and 6 mm from the opposite positive-Y short edge.",
    "board_pocket_clearance_total_mm": 1.0,
    "board_pocket_depth_mm": 2.2,
    "board_thickness_mm": 1.6,
    "as7343_package_width_y_mm": 3.1,
    "as7343_package_height_z_mm": 2.0,
    "as7343_package_thickness_x_mm": 1.0,
    "as7343_window_diameter_mm": 1.0,
    "as7343_sensor_offset_y_mm": 5.5,
    "as7343_sensor_offset_z_mm": 0.0,
    "header_relief_side": "negative_y",
    "header_relief_width_y_mm": 12.0,
    "header_relief_height_z_mm": 18.0,
    "header_pin_tail_clearance_count": 5,
    "header_pin_tail_clearance_pitch_z_mm": 2.54,
    "header_pin_tail_clearance_diameter_mm": 1.4,
    "header_pin_tail_clearance_y_offset_from_board_edge_mm": 2.5,
    "optional_clamp_hole_diameter_mm": 2.4,
    "optional_clamp_hole_margin_y_mm": 4.0,
    "optional_clamp_hole_margin_z_mm": 4.0,
    "source_chip_product": "https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7343-spectral-sensor",
    "source_chip_datasheet_local": "cad/references/as7343-spectral-analysis-module/资料/AS7343_DS001046_6-00.pdf",
    "source_module_schematic_local": "cad/references/as7343-spectral-analysis-module/AS7343光谱分析模块原理图.png",
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


def fillet_if_possible(shape: cq.Workplane, selector: str, radius: float) -> cq.Workplane:
    try:
        return shape.edges(selector).fillet(radius)
    except Exception:
        return shape


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
    return PARAMS["female_socket_length_mm"] + PARAMS["sensor_plate_thickness_mm"]


def cmount_socket_length() -> float:
    return PARAMS["female_socket_length_mm"]


def sensor_plate_x0() -> float:
    return cmount_socket_length()


def board_reference_geometry() -> dict[str, object]:
    board_w = PARAMS["estimated_module_board_width_y_mm"]
    board_h = PARAMS["estimated_module_board_height_z_mm"]
    sensor_y = PARAMS["as7343_sensor_offset_y_mm"]
    sensor_z = PARAMS["as7343_sensor_offset_z_mm"]
    bounds = {
        "y_min": round(-board_w / 2.0 - sensor_y, 4),
        "y_max": round(board_w / 2.0 - sensor_y, 4),
        "z_min": round(-board_h / 2.0 - sensor_z, 4),
        "z_max": round(board_h / 2.0 - sensor_z, 4),
    }
    clamp_y_min = bounds["y_min"] - PARAMS["optional_clamp_hole_margin_y_mm"]
    clamp_y_max = bounds["y_max"] + PARAMS["optional_clamp_hole_margin_y_mm"]
    clamp_z = board_h / 2.0 + PARAMS["optional_clamp_hole_margin_z_mm"]
    clamp_holes = [
        {"name": "clamp_bottom_left", "y": clamp_y_min, "z": -clamp_z},
        {"name": "clamp_top_left", "y": clamp_y_min, "z": clamp_z},
        {"name": "clamp_bottom_right", "y": clamp_y_max, "z": -clamp_z},
        {"name": "clamp_top_right", "y": clamp_y_max, "z": clamp_z},
    ]
    return {
        "board_center_relative_to_sensor_mm": {
            "y": round(-sensor_y, 4),
            "z": round(-sensor_z, 4),
        },
        "board_bounds_relative_to_sensor_mm": bounds,
        "optional_clamp_holes_relative_to_sensor_mm": [
            {
                **hole,
                "cut_diameter_mm": PARAMS["optional_clamp_hole_diameter_mm"],
            }
            for hole in clamp_holes
        ],
        "notes": [
            PARAMS["module_board_size_source"],
            "Coordinate convention: Y is the 23 mm board length from pin-socket edge to sensor-side edge; Z is the 15 mm short-edge width. Sensor datum is on the optical axis at Y=0, Z=0; board center is 5.5 mm toward the pin sockets.",
        ],
    }


def female_thread_cutter() -> cq.Workplane:
    return external_thread_brep(
        PARAMS["female_thread_start_mm"],
        PARAMS["female_thread_length_mm"],
        PARAMS["openhi_female_root_diameter_mm"],
        lefthand=True,
    )


def female_bore_cutter() -> cq.Workplane:
    return x_cylinder(
        PARAMS["openhi_female_root_diameter_mm"],
        PARAMS["female_socket_length_mm"],
        0.0,
    )


def board_pocket_cutter() -> cq.Workplane:
    ref = board_reference_geometry()
    center = ref["board_center_relative_to_sensor_mm"]  # type: ignore[index]
    pocket_w = PARAMS["estimated_module_board_width_y_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    pocket_h = PARAMS["estimated_module_board_height_z_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    depth = PARAMS["board_pocket_depth_mm"]
    return x_box(
        (total_length() - depth / 2.0 + 0.05, center["y"], center["z"]),
        (depth + 0.2, pocket_w, pocket_h),
    )


def header_relief_cutter() -> cq.Workplane:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_sensor_mm"]  # type: ignore[index]
    start_y = bounds["y_min"] - 0.4
    plate_min_y = -PARAMS["sensor_plate_width_y_mm"] / 2.0
    width_y = abs(start_y - plate_min_y) + 1.0
    center_y = start_y - width_y / 2.0
    return x_box(
        (total_length() - PARAMS["board_pocket_depth_mm"] / 2.0 + 0.25, center_y, 0.0),
        (PARAMS["board_pocket_depth_mm"] + 1.0, width_y, PARAMS["header_relief_height_z_mm"]),
    )


def clamp_hole_cutter(y: float, z: float) -> cq.Workplane:
    x0 = sensor_plate_x0() - 1.0
    return x_cylinder(PARAMS["optional_clamp_hole_diameter_mm"], PARAMS["sensor_plate_thickness_mm"] + 2.5, x0).translate((0, y, z))


def header_pin_tail_clearance_cutter() -> cq.Workplane:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_sensor_mm"]  # type: ignore[index]
    count = int(PARAMS["header_pin_tail_clearance_count"])
    pitch = PARAMS["header_pin_tail_clearance_pitch_z_mm"]
    y = bounds["y_min"] - PARAMS["header_pin_tail_clearance_y_offset_from_board_edge_mm"]
    first_z = -((count - 1) * pitch) / 2.0
    cutters: list[cq.Workplane] = []
    x0 = sensor_plate_x0() - 0.6
    length = PARAMS["sensor_plate_thickness_mm"] + 1.2
    for index in range(count):
        cutters.append(
            x_cylinder(PARAMS["header_pin_tail_clearance_diameter_mm"], length, x0).translate(
                (0, y, first_z + index * pitch)
            )
        )
    result = cutters[0]
    for cutter in cutters[1:]:
        result = result.union(cutter)
    return result


def build_cmount_socket_body() -> cq.Workplane:
    socket = x_cylinder(PARAMS["socket_outer_diameter_mm"], PARAMS["female_socket_length_mm"], 0.0)
    body = socket
    body = fillet_if_possible(body, "|X", 0.55)
    body = body.cut(female_bore_cutter()).cut(female_thread_cutter())
    body = body.cut(x_cylinder(PARAMS["optical_bore_diameter_mm"], cmount_socket_length() + 0.2, -0.1))
    return body.clean()


def build_sensor_plate_body() -> cq.Workplane:
    plate_x0 = sensor_plate_x0()
    plate = x_box(
        (plate_x0 + PARAMS["sensor_plate_thickness_mm"] / 2.0, 0.0, PARAMS["sensor_plate_center_z_mm"]),
        (
            PARAMS["sensor_plate_thickness_mm"],
            PARAMS["sensor_plate_width_y_mm"],
            PARAMS["sensor_plate_height_z_mm"],
        ),
    )
    holder = fillet_if_possible(plate, "|X", 0.8)
    holder = holder.cut(
        x_cylinder(
            PARAMS["optical_bore_diameter_mm"],
            PARAMS["sensor_plate_thickness_mm"] + 1.2,
            sensor_plate_x0() - 0.6,
        )
    )
    holder = holder.cut(board_pocket_cutter()).cut(header_relief_cutter()).cut(header_pin_tail_clearance_cutter())
    ref = board_reference_geometry()
    for hole in ref["optional_clamp_holes_relative_to_sensor_mm"]:  # type: ignore[index]
        holder = holder.cut(clamp_hole_cutter(hole["y"], hole["z"]))
    return holder.clean()


def build_holder_compound() -> cq.Compound:
    return cq.Compound.makeCompound([build_cmount_socket_body().val(), build_sensor_plate_body().val()])


def build_board_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    center = ref["board_center_relative_to_sensor_mm"]  # type: ignore[index]
    return x_box(
        (
            total_length() + PARAMS["board_thickness_mm"] / 2.0 + 0.05,
            center["y"],
            center["z"],
        ),
        (
            PARAMS["board_thickness_mm"],
            PARAMS["estimated_module_board_width_y_mm"],
            PARAMS["estimated_module_board_height_z_mm"],
        ),
    )


def build_sensor_proxy() -> cq.Workplane:
    total_x = total_length()
    package = x_box(
        (
            total_x + PARAMS["board_thickness_mm"] + PARAMS["as7343_package_thickness_x_mm"] / 2.0,
            0.0,
            0.0,
        ),
        (
            PARAMS["as7343_package_thickness_x_mm"],
            PARAMS["as7343_package_width_y_mm"],
            PARAMS["as7343_package_height_z_mm"],
        ),
    )
    window = x_cylinder(PARAMS["as7343_window_diameter_mm"], 1.2, total_x + PARAMS["board_thickness_mm"] + 0.15)
    return package.union(window)


def build_header_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_sensor_mm"]  # type: ignore[index]
    return x_box(
        (
            total_length() + PARAMS["board_thickness_mm"] + 3.2,
            bounds["y_min"] - 2.5,
            0.0,
        ),
        (6.4, 5.0, 14.0),
    )


def build_axis_proxy() -> cq.Workplane:
    return x_cylinder(1.0, total_length() + 9.0, -4.0)


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_cmount_socket_body(), name="independent_openhi_24p8_threaded_cmount_socket", color=cq.Color(0.10, 0.10, 0.09, 1.0))
    assembly.add(build_sensor_plate_body(), name="independent_as7343_sensor_plate_holder", color=cq.Color(0.18, 0.18, 0.16, 1.0))
    assembly.add(build_board_proxy(), name="as7343_15x23_module_board_proxy_sensor_6mm_from_front_edge", color=cq.Color(0.0, 0.23, 0.48, 0.70))
    assembly.add(build_sensor_proxy(), name="as7343_package_centered_on_optical_axis", color=cq.Color(0.95, 0.78, 0.20, 1.0))
    assembly.add(build_header_proxy(), name="negative_y_pin_socket_clearance_proxy", color=cq.Color(0.95, 0.92, 0.82, 0.65))
    assembly.add(female_thread_cutter(), name="female_thread_boolean_cutter", color=cq.Color(0.9, 0.2, 0.1, 0.35))
    assembly.add(build_axis_proxy(), name="optical_axis_proxy", color=cq.Color(1.0, 0.72, 0.08, 0.6))
    return assembly


def write_alignment_svg(path: Path) -> None:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_sensor_mm"]  # type: ignore[index]
    scale = 9.0
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

    header_y0 = -view_w / 2.0
    header_y1 = bounds["y_min"] - 0.4
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-view_w/2):.2f}" y="{sy(view_h/2):.2f}" width="{view_w*scale:.2f}" height="{view_h*scale:.2f}" rx="8" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        f'<rect x="{sx(bounds["y_min"]):.2f}" y="{sy(bounds["z_max"]):.2f}" width="{(bounds["y_max"]-bounds["y_min"])*scale:.2f}" height="{(bounds["z_max"]-bounds["z_min"])*scale:.2f}" fill="#e6f0ff" stroke="#2b6cb0" stroke-width="2" stroke-dasharray="8 5"/>',
        f'<rect x="{sx(header_y0):.2f}" y="{sy(PARAMS["header_relief_height_z_mm"]/2):.2f}" width="{(header_y1-header_y0)*scale:.2f}" height="{PARAMS["header_relief_height_z_mm"]*scale:.2f}" fill="#fff5f5" stroke="#c53030" stroke-width="2" stroke-dasharray="5 4"/>',
        f'<line x1="{sx(-view_w/2):.2f}" y1="{sy(0):.2f}" x2="{sx(view_w/2):.2f}" y2="{sy(0):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        f'<line x1="{sx(0):.2f}" y1="{sy(view_h/2):.2f}" x2="{sx(0):.2f}" y2="{sy(-view_h/2):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        circle(0.0, 0.0, PARAMS["optical_bore_diameter_mm"], "#fff7d6", "#d69e2e", "optical axis / AS7343"),
        f'<rect x="{sx(-PARAMS["as7343_package_width_y_mm"]/2):.2f}" y="{sy(PARAMS["as7343_package_height_z_mm"]/2):.2f}" width="{PARAMS["as7343_package_width_y_mm"]*scale:.2f}" height="{PARAMS["as7343_package_height_z_mm"]*scale:.2f}" fill="#c69214" stroke="#1a202c" stroke-width="1.5"/>',
    ]
    for hole in ref["optional_clamp_holes_relative_to_sensor_mm"]:  # type: ignore[index]
        lines.append(circle(hole["y"], hole["z"], PARAMS["optional_clamp_hole_diameter_mm"], "#edf2f7", "#4a5568", hole["name"].replace("clamp_", "")))

    legend_x = pad + view_w * scale + 36.0
    legend = [
        "AS7343 C-mount spectral module holder",
        "View: rear tray, looking along optical axis",
        "Gold rectangle: AS7343 3.1 x 2 mm package centered on axis",
        "Blue dashed rectangle: 15 x 23 mm AS7343 module tray",
        "Gray holes: optional M2 clamp/lid holes outside the module area",
        "Red dashed slot: negative-Y pin-socket/cable relief side",
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
    clamp_rows = "\n".join(
        f"| {hole['name']} | `{hole['y']}` | `{hole['z']}` | `{hole['cut_diameter_mm']}` |"
        for hole in ref["optional_clamp_holes_relative_to_sensor_mm"]  # type: ignore[index]
    )
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    params_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# AS7343 C-Mount Spectral Module Holder Direct Socket

New independent CAD design for holding an AS7343 spectral analysis module behind
an OpenHI-print-fit C-mount receiver. This version removes both intermediate
connector shapes: no rectangular bridge/cube and no middle cylinder/tube. The
left C-mount socket directly touches the rear sensor plate at x=`{sensor_plate_x0()}`.
The C-mount socket and the sensor plate are exported as adjacent independent
bodies so Shapr3D can select and edit them separately. Older CAD designs are
not modified.

## Source References

- Local reference snapshot: `{repo_path(REFERENCE_DIR)}`
- Local AS7343 datasheet: `{PARAMS['source_chip_datasheet_local']}`
- Local module schematic: `{PARAMS['source_module_schematic_local']}`
- ams OSRAM product page: `{PARAMS['source_chip_product']}`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The supplied module references include the AS7343 datasheet, app notes, example
code, and a schematic image. The physical tray now follows the corrected module
geometry provided after checking the board: `15 x 23 mm`, pin sockets on the
negative-Y short edge, and the AS7343 package centered across the 15 mm short
edge and `6 mm` from the opposite positive-Y short edge. The board center is
therefore `5.5 mm` toward the pin sockets relative to the optical axis.

## Design Intent

- Put the AS7343 sensing package on the C-mount optical axis.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Keep the female thread cutter fully inside the `12 mm` C-mount socket:
  x=`{PARAMS['female_thread_start_mm']}` to
  x=`{PARAMS['female_thread_start_mm'] + PARAMS['female_thread_length_mm']}`.
- Export the C-mount socket and sensor plate as separate adjacent solids; they
  touch at x=`{sensor_plate_x0()}` without a bridge cube, middle cylinder, or
  boolean union.
- Provide a rear module tray with negative-Y pin-socket/cable relief.
- Add a five-hole pin-tail clearance row near the negative-Y header side.
- Add four optional M2 clamp/lid holes outside the corrected module footprint.

## C-Mount Size

The printed receiver uses the local OpenHI print-fit size: `24.8 mm` female
root/bore. It is not modeled as a raw `25.4 mm` cylinder. Standard C-mount is
`1-32 UNS` with `0.79375 mm` pitch; this printed design keeps the existing
OpenHI-compatible `0.8 mm` pitch thread convention.

## Geometry Used

Board center relative to the AS7343 package:

```json
{json.dumps(ref['board_center_relative_to_sensor_mm'], indent=2)}
```

Optional clamp holes:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
{clamp_rows}

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
cad/.conda/cad-python/bin/python cad/designs/as7343_cmount_spectral_module_holder_direct_socket/build_as7343_cmount_spectral_module_holder_direct_socket.py
blender --background --python cad/designs/as7343_cmount_spectral_module_holder_direct_socket/render_as7343_cmount_spectral_module_holder_direct_socket.py
```
""",
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cmount_socket = build_cmount_socket_body()
    sensor_plate = build_sensor_plate_body()
    holder_compound = build_holder_compound()
    assembly = build_assembly()
    cutter = female_thread_cutter()
    board = build_board_proxy()

    holder_step = ARTIFACT_DIR / f"{STEM}_multibody_holder.step"
    holder_stl = ARTIFACT_DIR / f"{STEM}_multibody_holder.stl"
    cmount_socket_step = ARTIFACT_DIR / f"{STEM}_cmount_socket.step"
    cmount_socket_stl = ARTIFACT_DIR / f"{STEM}_cmount_socket.stl"
    sensor_plate_step = ARTIFACT_DIR / f"{STEM}_sensor_plate.step"
    sensor_plate_stl = ARTIFACT_DIR / f"{STEM}_sensor_plate.stl"
    assembly_step = ARTIFACT_DIR / f"{STEM}_assembly.step"
    assembly_stl = ARTIFACT_DIR / f"{STEM}_assembly.stl"
    cutter_step = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.step"
    cutter_stl = ARTIFACT_DIR / f"{STEM}_female_thread_cutter.stl"
    board_proxy_step = ARTIFACT_DIR / f"{STEM}_board_proxy.step"
    board_proxy_stl = ARTIFACT_DIR / f"{STEM}_board_proxy.stl"
    alignment_svg = ARTIFACT_DIR / f"{STEM}_rear_alignment.svg"
    manifest_path = ARTIFACT_DIR / "manifest.json"

    exporters.export(holder_compound, str(holder_step))
    exporters.export(holder_compound, str(holder_stl))
    exporters.export(cmount_socket, str(cmount_socket_step))
    exporters.export(cmount_socket, str(cmount_socket_stl))
    exporters.export(sensor_plate, str(sensor_plate_step))
    exporters.export(sensor_plate, str(sensor_plate_stl))
    exporters.export(cutter, str(cutter_step))
    exporters.export(cutter, str(cutter_stl))
    exporters.export(board, str(board_proxy_step))
    exporters.export(board, str(board_proxy_stl))
    assembly.save(str(assembly_step))
    assembly.save(str(assembly_stl))
    write_alignment_svg(alignment_svg)
    convert_svg(alignment_svg)

    outputs = {
        "multibody_holder_step": repo_path(holder_step),
        "multibody_holder_stl": repo_path(holder_stl),
        "cmount_socket_step": repo_path(cmount_socket_step),
        "cmount_socket_stl": repo_path(cmount_socket_stl),
        "sensor_plate_step": repo_path(sensor_plate_step),
        "sensor_plate_stl": repo_path(sensor_plate_stl),
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
