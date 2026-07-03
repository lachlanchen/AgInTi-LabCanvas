#!/usr/bin/env python3
"""Build an OpenHI-fit C-mount holder for a Waveshare TSL25911 light sensor."""

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
STEM = "tsl25911_cmount_intensity_sensor_holder"
REFERENCE_DIR = ROOT / "cad/references/waveshare-tsl25911-light-sensor"


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
    "sensor_plate_width_y_mm": 50.0,
    "sensor_plate_height_z_mm": 36.0,
    "sensor_plate_center_z_mm": 0.0,
    "waveshare_board_width_y_mm": 27.0,
    "waveshare_board_height_z_mm": 20.0,
    "board_pocket_clearance_total_mm": 0.8,
    "board_pocket_depth_mm": 2.0,
    "board_thickness_mm": 1.6,
    "tsl25911_window_diameter_mm": 1.4,
    "tsl25911_window_x_from_left_edge_mm": 7.5,
    "tsl25911_window_from_board_top_mm": 10.0,
    "mount_hole_diameter_mm": 2.0,
    "mount_hole_clearance_diameter_mm": 2.4,
    "mount_hole_x_from_left_edge_mm": 2.0,
    "mount_hole_from_board_edge_z_mm": 2.0,
    "connector_relief_width_y_mm": 10.0,
    "connector_relief_height_z_mm": 18.0,
    "source_wiki": "https://www.waveshare.net/wiki/TSL25911_Light_Sensor",
    "source_product": "https://www.waveshare.net/shop/TSL25911-Light-Sensor.htm",
    "source_github": "https://github.com/waveshare/TSL2591X-Light-Sensor",
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


def board_reference_geometry() -> dict[str, object]:
    board_w = PARAMS["waveshare_board_width_y_mm"]
    board_h = PARAMS["waveshare_board_height_z_mm"]
    window_x = PARAMS["tsl25911_window_x_from_left_edge_mm"]
    window_from_top = PARAMS["tsl25911_window_from_board_top_mm"]
    window_z_from_bottom = board_h - window_from_top
    board_center = {
        "y": round(board_w / 2.0 - window_x, 4),
        "z": round(board_h / 2.0 - window_z_from_bottom, 4),
    }
    hole_y = PARAMS["mount_hole_x_from_left_edge_mm"] - window_x
    holes = []
    for name, hole_z_from_bottom in (
        ("M2_bottom", PARAMS["mount_hole_from_board_edge_z_mm"]),
        ("M2_top", board_h - PARAMS["mount_hole_from_board_edge_z_mm"]),
    ):
        holes.append(
            {
                "name": name,
                "y": round(hole_y, 4),
                "z": round(hole_z_from_bottom - window_z_from_bottom, 4),
                "source_diameter_mm": PARAMS["mount_hole_diameter_mm"],
                "cut_diameter_mm": PARAMS["mount_hole_clearance_diameter_mm"],
            }
        )
    return {
        "board_center_relative_to_window_mm": board_center,
        "mounting_holes_relative_to_window_mm": holes,
        "board_bounds_relative_to_window_mm": {
            "y_min": round(-window_x, 4),
            "y_max": round(board_w - window_x, 4),
            "z_min": round(-window_z_from_bottom, 4),
            "z_max": round(board_h - window_z_from_bottom, 4),
        },
        "notes": [
            "Board dimensions and hole sizes are vendor-published values.",
            "TSL25911 window datum is estimated from the vendor size image; keep the build script parametric for adjustment after a caliper check.",
        ],
    }


def total_length() -> float:
    return PARAMS["female_socket_length_mm"] + PARAMS["tube_length_mm"] + PARAMS["sensor_plate_thickness_mm"]


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
    center = ref["board_center_relative_to_window_mm"]  # type: ignore[index]
    pocket_w = PARAMS["waveshare_board_width_y_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    pocket_h = PARAMS["waveshare_board_height_z_mm"] + PARAMS["board_pocket_clearance_total_mm"]
    depth = PARAMS["board_pocket_depth_mm"]
    return x_box(
        (total_length() - depth / 2.0 + 0.05, center["y"], center["z"]),
        (depth + 0.2, pocket_w, pocket_h),
    )


def screw_hole_cutter(y: float, z: float) -> cq.Workplane:
    x0 = PARAMS["female_socket_length_mm"] + PARAMS["tube_length_mm"] - 1.0
    length = PARAMS["sensor_plate_thickness_mm"] + 2.5
    return x_cylinder(PARAMS["mount_hole_clearance_diameter_mm"], length, x0).translate((0, y, z))


def connector_relief_cutter() -> cq.Workplane:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_window_mm"]  # type: ignore[index]
    plate_half_y = PARAMS["sensor_plate_width_y_mm"] / 2.0
    start_y = bounds["y_max"] - 2.0
    width_y = max(PARAMS["connector_relief_width_y_mm"], plate_half_y - start_y + 1.0)
    center_y = start_y + width_y / 2.0
    depth = PARAMS["board_pocket_depth_mm"]
    return x_box(
        (total_length() - depth / 2.0 + 0.25, center_y, 0.0),
        (depth + 1.0, width_y, PARAMS["connector_relief_height_z_mm"]),
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
        (
            plate_x0 + PARAMS["sensor_plate_thickness_mm"] / 2.0,
            0.0,
            PARAMS["sensor_plate_center_z_mm"],
        ),
        (
            PARAMS["sensor_plate_thickness_mm"],
            PARAMS["sensor_plate_width_y_mm"],
            PARAMS["sensor_plate_height_z_mm"],
        ),
    )
    bridge = x_box(
        (
            PARAMS["female_socket_length_mm"] + PARAMS["tube_length_mm"] / 2.0,
            0.0,
            0.0,
        ),
        (PARAMS["tube_length_mm"] + 0.8, 32.0, 28.0),
    )
    holder = socket.union(tube).union(bridge).union(plate)
    holder = holder.edges("|X").fillet(0.8)
    holder = holder.cut(female_bore_cutter()).cut(female_thread_cutter())
    holder = holder.cut(x_cylinder(PARAMS["optical_bore_diameter_mm"], total_length() + 2.0, -1.0))
    holder = holder.cut(board_pocket_cutter()).cut(connector_relief_cutter())
    ref = board_reference_geometry()
    for hole in ref["mounting_holes_relative_to_window_mm"]:  # type: ignore[index]
        holder = holder.cut(screw_hole_cutter(hole["y"], hole["z"]))
    return holder


def build_board_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    center = ref["board_center_relative_to_window_mm"]  # type: ignore[index]
    total_x = total_length()
    board = x_box(
        (
            total_x + PARAMS["board_thickness_mm"] / 2.0 + 0.05,
            center["y"],
            center["z"],
        ),
        (
            PARAMS["board_thickness_mm"],
            PARAMS["waveshare_board_width_y_mm"],
            PARAMS["waveshare_board_height_z_mm"],
        ),
    )
    for hole in ref["mounting_holes_relative_to_window_mm"]:  # type: ignore[index]
        board = board.cut(
            x_cylinder(PARAMS["mount_hole_diameter_mm"], PARAMS["board_thickness_mm"] + 0.4, total_x - 0.15).translate(
                (0, hole["y"], hole["z"])
            )
        )
    return board


def build_sensor_proxy() -> cq.Workplane:
    total_x = total_length()
    package = x_box((total_x + PARAMS["board_thickness_mm"] + 0.45, 0.0, 0.0), (0.9, 3.0, 3.6))
    window = x_cylinder(PARAMS["tsl25911_window_diameter_mm"], 1.1, total_x + PARAMS["board_thickness_mm"] + 0.2)
    return package.union(window)


def build_connector_proxy() -> cq.Workplane:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_window_mm"]  # type: ignore[index]
    total_x = total_length()
    return x_box(
        (
            total_x + PARAMS["board_thickness_mm"] + 3.2,
            bounds["y_max"] + 2.5,
            0.0,
        ),
        (6.4, 5.0, 17.0),
    )


def build_axis_proxy() -> cq.Workplane:
    return x_cylinder(1.0, total_length() + 9.0, -4.0)


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_holder(), name="printed_holder_openhi_24p8_receiver", color=cq.Color(0.08, 0.08, 0.08, 1.0))
    assembly.add(build_board_proxy(), name="waveshare_tsl25911_board_proxy", color=cq.Color(0.0, 0.14, 0.42, 0.72))
    assembly.add(build_sensor_proxy(), name="tsl25911_window_proxy", color=cq.Color(0.08, 0.10, 0.04, 1.0))
    assembly.add(build_connector_proxy(), name="ph2_5pin_connector_clearance_proxy", color=cq.Color(0.95, 0.92, 0.82, 0.65))
    assembly.add(female_thread_cutter(), name="female_thread_boolean_cutter", color=cq.Color(0.9, 0.2, 0.1, 0.35))
    assembly.add(build_axis_proxy(), name="optical_axis_proxy", color=cq.Color(1.0, 0.72, 0.08, 0.6))
    return assembly


def write_alignment_svg(path: Path) -> None:
    ref = board_reference_geometry()
    bounds = ref["board_bounds_relative_to_window_mm"]  # type: ignore[index]
    scale = 9.0
    pad = 58.0
    legend_w = 560.0
    view_w = PARAMS["sensor_plate_width_y_mm"]
    view_h = PARAMS["sensor_plate_height_z_mm"]
    plate_center_z = PARAMS["sensor_plate_center_z_mm"]
    svg_w = int(view_w * scale + pad * 2 + legend_w)
    svg_h = int(view_h * scale + pad * 2)

    def sx(y: float) -> float:
        return pad + (y + view_w / 2.0) * scale

    def sy(z: float) -> float:
        top = plate_center_z + view_h / 2.0
        return pad + (top - z) * scale

    def circle(y: float, z: float, diameter: float, fill: str, stroke: str, label: str = "") -> str:
        text = ""
        if label:
            text = f'<text x="{sx(y)+8:.2f}" y="{sy(z)-8:.2f}" font-family="Arial" font-size="12" fill="#1a202c">{label}</text>'
        return f'<circle cx="{sx(y):.2f}" cy="{sy(z):.2f}" r="{diameter/2*scale:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>{text}'

    board_y = (bounds["y_min"] + bounds["y_max"]) / 2.0
    board_z = (bounds["z_min"] + bounds["z_max"]) / 2.0
    relief_y0 = bounds["y_max"] - 2.0
    relief_w = max(PARAMS["connector_relief_width_y_mm"], view_w / 2.0 - relief_y0 + 1.0)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<rect x="{sx(-view_w/2):.2f}" y="{sy(plate_center_z + view_h/2):.2f}" width="{view_w*scale:.2f}" height="{view_h*scale:.2f}" rx="8" fill="#f7fafc" stroke="#1a202c" stroke-width="2"/>',
        f'<rect x="{sx(bounds["y_min"]):.2f}" y="{sy(bounds["z_max"]):.2f}" width="{(bounds["y_max"]-bounds["y_min"])*scale:.2f}" height="{(bounds["z_max"]-bounds["z_min"])*scale:.2f}" fill="#e6f0ff" stroke="#2b6cb0" stroke-width="2" stroke-dasharray="8 5"/>',
        f'<line x1="{sx(-view_w/2):.2f}" y1="{sy(0):.2f}" x2="{sx(view_w/2):.2f}" y2="{sy(0):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        f'<line x1="{sx(0):.2f}" y1="{sy(plate_center_z + view_h/2):.2f}" x2="{sx(0):.2f}" y2="{sy(plate_center_z - view_h/2):.2f}" stroke="#cbd5e0" stroke-width="1"/>',
        circle(0.0, 0.0, PARAMS["optical_bore_diameter_mm"], "#fff7d6", "#d69e2e", "optical axis / TSL25911"),
        circle(0.0, 0.0, PARAMS["tsl25911_window_diameter_mm"], "#6b4e16", "#1a202c"),
    ]
    for hole in ref["mounting_holes_relative_to_window_mm"]:  # type: ignore[index]
        lines.append(circle(hole["y"], hole["z"], PARAMS["mount_hole_clearance_diameter_mm"], "#ebf8ff", "#3182ce", hole["name"]))

    lines.append(
        f'<rect x="{sx(relief_y0):.2f}" y="{sy(PARAMS["connector_relief_height_z_mm"]/2):.2f}" width="{relief_w*scale:.2f}" height="{PARAMS["connector_relief_height_z_mm"]*scale:.2f}" fill="#fff5f5" stroke="#c53030" stroke-width="2" stroke-dasharray="5 4"/>'
    )
    lines.append(f'<text x="{sx(board_y)-58:.2f}" y="{sy(board_z)-36:.2f}" font-family="Arial" font-size="13" fill="#2b6cb0">27 x 20 mm board pocket</text>')

    legend_x = pad + view_w * scale + 36.0
    legend = [
        "TSL25911 C-mount intensity sensor holder",
        "View: rear sensor plate, looking along optical axis",
        "Gold circle: 8 mm optical bore centered on estimated TSL25911 window",
        "Blue dashed rectangle: Waveshare 27 x 20 mm breakout + 0.8 mm clearance",
        "Blue holes: two M2 clearance holes, 16 mm spacing on left edge",
        "Red dashed notch: side clearance for 5-pin connector and Dupont wire",
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
        for hole in ref["mounting_holes_relative_to_window_mm"]  # type: ignore[index]
    )
    output_rows = "\n".join(f"| {name} | `{value}` |" for name, value in outputs.items())
    params_rows = "\n".join(f"| `{key}` | `{value}` |" for key, value in PARAMS.items())
    path.write_text(
        f"""# TSL25911 C-Mount Intensity Sensor Holder

New independent CAD design for holding a Waveshare TSL25911 Light Sensor behind
an OpenHI-print-fit C-mount receiver. Older CAD designs are not modified.

## Source References

- Waveshare wiki: `{PARAMS['source_wiki']}`
- Waveshare product page: `{PARAMS['source_product']}`
- Waveshare example code: `{PARAMS['source_github']}`
- Local reference snapshot: `{repo_path(REFERENCE_DIR)}`
- Local OpenHI print-fit table: `cad/references/openhi-print-fit-and-thread-reference.md`

The vendor documentation gives a `27 x 20 mm` breakout, two `2.0 mm`
mounting holes with `16 mm` spacing on the left side, `0-88000 Lux` range, and
I2C address `0x29`. I did not find an official STEP model in the vendor
downloads, so this holder uses the published size image and keeps the sensor
window datum parametric for later caliper adjustment.

## Design Intent

- Put the TSL25911 sensing window on the C-mount optical axis.
- Use the local OpenHI printed C-mount convention: `24.8 mm` female bore/root,
  `25.6 mm` internal thread-cutter crest, `0.8 mm` pitch, `0.4 mm` tooth height.
- Keep the board removable with a shallow rear pocket, two M2 clearance holes,
  and a right-side connector/Dupont wire relief.
- Keep the holder simple and printable: one solid receiver/plate part plus
  separate board, connector, axis, and thread-cutter reference objects.

## Board Geometry Used

Mounting holes are relative to the TSL25911 window/optical axis:

| Hole | y mm | z mm | holder cut dia mm |
| --- | ---: | ---: | ---: |
{hole_rows}

Board center relative to the sensor window:

```json
{json.dumps(ref['board_center_relative_to_window_mm'], indent=2)}
```

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
cad/.conda/cad-python/bin/python cad/designs/tsl25911_cmount_intensity_sensor_holder/build_tsl25911_cmount_intensity_sensor_holder.py
blender --background --python cad/designs/tsl25911_cmount_intensity_sensor_holder/render_tsl25911_cmount_intensity_sensor_holder.py
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
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_readme(DESIGN_DIR / "README.md", outputs | {"manifest": repo_path(manifest_path)})


if __name__ == "__main__":
    main()
