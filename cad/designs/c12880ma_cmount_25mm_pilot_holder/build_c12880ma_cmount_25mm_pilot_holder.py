#!/usr/bin/env python3
"""Build a two-piece C12880MA holder with a 25 mm C-mount-side pilot."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import cadquery as cq

try:
    import cairosvg
except Exception:  # Native Cairo is optional on Windows.
    cairosvg = None


ROOT = Path(__file__).resolve().parents[3]
DESIGN_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = DESIGN_DIR / "artifacts"
STEM = "c12880ma_cmount_25mm_pilot_holder"


PARAMS = {
    "name": STEM,
    "optical_axis": "+X from the 25 mm pilot toward the C12880MA slit",
    "pilot_type": "smooth external locating pilot; not a 1-32 thread",
    "pilot_diameter_mm": 25.0,
    "pilot_length_mm": 5.0,
    "pilot_shoulder_diameter_mm": 30.0,
    "pilot_shoulder_length_mm": 1.5,
    "flange_width_mm": 34.0,
    "flange_height_mm": 28.0,
    "flange_front_x_mm": -5.0,
    "flange_rear_x_mm": 1.4,
    "flange_corner_radius_mm": 2.0,
    "pilot_axis_y_mm": 0.0,
    "pilot_axis_z_mm": 0.0,
    "pilot_bore_diameter_mm": 18.0,
    "intermediate_bore_diameter_mm": 12.0,
    "sensor_aperture_diameter_mm": 5.0,
    "official_sensor_length_mm": 20.12,
    "official_sensor_width_mm": 12.5,
    "official_sensor_thickness_mm": 10.12,
    "official_entrance_opening_diameter_mm": 3.2,
    "official_slit_width_mm": 0.05,
    "official_slit_height_mm": 0.5,
    "slit_offset_from_package_center_y_mm": 0.5,
    "sensor_center_y_mm": -0.5,
    "sensor_center_z_mm": 0.0,
    "sensor_pocket_clearance_per_side_mm": 0.20,
    "sensor_pocket_depth_mm": 1.4,
    "sensor_axial_clearance_mm": 0.25,
    "standoff_diameter_mm": 5.5,
    "standoff_y_mm": 13.5,
    "standoff_z_mm": 9.5,
    "body_m2p5_pilot_diameter_mm": 2.2,
    "retainer_m2p5_clearance_diameter_mm": 2.8,
    "retainer_width_mm": 32.0,
    "retainer_height_mm": 24.0,
    "retainer_thickness_mm": 2.8,
    "retainer_window_width_mm": 18.0,
    "retainer_window_height_mm": 9.5,
    "lead_length_mm": 3.3,
    "lead_diameter_mm": 0.47,
    "fastening_pin_diameter_mm": 1.4,
    "electrical_note": (
        "The C12880MA case is conductive and tied to pin 5. Use an insulating printed holder "
        "or keep every contacting metal part at the same potential as pin 5."
    ),
}


def x_box(size: tuple[float, float, float], center: tuple[float, float, float]) -> cq.Workplane:
    return cq.Workplane("XY").box(*size).translate(center)


def x_cylinder(
    diameter: float,
    length: float,
    x_min: float,
    y: float = 0.0,
    z: float = 0.0,
) -> cq.Workplane:
    return (
        cq.Workplane("YZ")
        .workplane(offset=x_min)
        .center(y, z)
        .circle(diameter / 2.0)
        .extrude(length)
    )


def screw_points() -> list[tuple[float, float]]:
    p = PARAMS
    return [
        (y, z)
        for y in (-p["standoff_y_mm"], p["standoff_y_mm"])
        for z in (-p["standoff_z_mm"], p["standoff_z_mm"])
    ]


def sensor_face_x() -> float:
    return PARAMS["flange_rear_x_mm"] - PARAMS["sensor_pocket_depth_mm"]


def retainer_front_x() -> float:
    return sensor_face_x() + PARAMS["official_sensor_thickness_mm"] + PARAMS["sensor_axial_clearance_mm"]


def build_body() -> cq.Workplane:
    p = PARAMS
    front_x = p["flange_front_x_mm"]
    rear_x = p["flange_rear_x_mm"]
    flange_length = rear_x - front_x
    body = x_box(
        (flange_length, p["flange_width_mm"], p["flange_height_mm"]),
        ((front_x + rear_x) / 2.0, 0.0, 0.0),
    )
    body = body.edges("|X").fillet(p["flange_corner_radius_mm"])

    pilot_x_min = front_x - p["pilot_length_mm"]
    body = body.union(
        x_cylinder(
            p["pilot_diameter_mm"],
            p["pilot_length_mm"],
            pilot_x_min,
            p["pilot_axis_y_mm"],
            p["pilot_axis_z_mm"],
        )
    )
    body = body.union(
        x_cylinder(
            p["pilot_shoulder_diameter_mm"],
            p["pilot_shoulder_length_mm"],
            front_x - p["pilot_shoulder_length_mm"],
            p["pilot_axis_y_mm"],
            p["pilot_axis_z_mm"],
        )
    )

    cap_x = retainer_front_x()
    standoff_length = cap_x - rear_x
    for y, z in screw_points():
        body = body.union(x_cylinder(p["standoff_diameter_mm"], standoff_length, rear_x, y, z))

    pocket_width = p["official_sensor_length_mm"] + 2.0 * p["sensor_pocket_clearance_per_side_mm"]
    pocket_height = p["official_sensor_width_mm"] + 2.0 * p["sensor_pocket_clearance_per_side_mm"]
    pocket = x_box(
        (p["sensor_pocket_depth_mm"] + 0.04, pocket_width, pocket_height),
        (
            rear_x - p["sensor_pocket_depth_mm"] / 2.0 + 0.01,
            p["sensor_center_y_mm"],
            p["sensor_center_z_mm"],
        ),
    )
    body = body.cut(pocket)

    # The index-corner relief makes a 180-degree insertion error visibly wrong.
    index_y = p["sensor_center_y_mm"] - p["official_sensor_length_mm"] / 2.0 + 1.1
    index_z = p["sensor_center_z_mm"] - p["official_sensor_width_mm"] / 2.0 + 1.1
    body = body.cut(
        x_box(
            (p["sensor_pocket_depth_mm"] + 0.3, 2.2, 2.2),
            (rear_x - p["sensor_pocket_depth_mm"] / 2.0, index_y, index_z),
        )
    )

    axis_y = p["pilot_axis_y_mm"]
    axis_z = p["pilot_axis_z_mm"]
    body = body.cut(
        x_cylinder(
            p["pilot_bore_diameter_mm"],
            p["pilot_length_mm"] + 1.3,
            pilot_x_min - 0.1,
            axis_y,
            axis_z,
        )
    )
    body = body.cut(
        x_cylinder(
            p["intermediate_bore_diameter_mm"],
            2.8,
            front_x - 1.4,
            axis_y,
            axis_z,
        )
    )
    body = body.cut(
        x_cylinder(
            p["sensor_aperture_diameter_mm"],
            rear_x + 1.7,
            -1.5,
            axis_y,
            axis_z,
        )
    )

    for y, z in screw_points():
        body = body.cut(
            x_cylinder(
                p["body_m2p5_pilot_diameter_mm"],
                cap_x + 3.2,
                -3.0,
                y,
                z,
            )
        )
    return body


def build_retainer() -> cq.Workplane:
    p = PARAMS
    front_x = retainer_front_x()
    retainer = x_box(
        (p["retainer_thickness_mm"], p["retainer_width_mm"], p["retainer_height_mm"]),
        (front_x + p["retainer_thickness_mm"] / 2.0, 0.0, 0.0),
    )
    retainer = retainer.edges("|X").fillet(1.2)
    retainer = retainer.cut(
        x_box(
            (
                p["retainer_thickness_mm"] + 0.4,
                p["retainer_window_width_mm"],
                p["retainer_window_height_mm"],
            ),
            (front_x + p["retainer_thickness_mm"] / 2.0, p["sensor_center_y_mm"], 0.0),
        )
    )
    for y, z in screw_points():
        retainer = retainer.cut(
            x_cylinder(
                p["retainer_m2p5_clearance_diameter_mm"],
                p["retainer_thickness_mm"] + 0.4,
                front_x - 0.2,
                y,
                z,
            )
        )
    return retainer


def lead_y_positions() -> list[float]:
    center = PARAMS["sensor_center_y_mm"]
    return [center + value for value in (-6.35, -3.81, 3.81, 6.35, 8.89)]


def build_sensor_proxy() -> cq.Workplane:
    p = PARAMS
    face_x = sensor_face_x()
    thickness = p["official_sensor_thickness_mm"]
    sensor = x_box(
        (thickness, p["official_sensor_length_mm"], p["official_sensor_width_mm"]),
        (
            face_x + thickness / 2.0,
            p["sensor_center_y_mm"],
            p["sensor_center_z_mm"],
        ),
    )
    sensor = sensor.edges("|X").fillet(1.0)
    sensor = sensor.cut(
        x_cylinder(
            p["official_entrance_opening_diameter_mm"],
            0.8,
            face_x - 0.05,
            p["pilot_axis_y_mm"],
            p["pilot_axis_z_mm"],
        )
    )

    lead_x = face_x + thickness
    rows = (-3.81, 3.81)
    for row_index, z in enumerate(rows):
        for pin_index, y in enumerate(lead_y_positions()):
            diameter = p["lead_diameter_mm"]
            if row_index == 0 and pin_index == 2:
                diameter = p["fastening_pin_diameter_mm"]
            sensor = sensor.union(x_cylinder(diameter, p["lead_length_mm"], lead_x, y, z))
    return sensor


def build_assembly() -> cq.Assembly:
    assembly = cq.Assembly(name=f"{STEM}_assembly")
    assembly.add(build_body(), name="printed_optical_body", color=cq.Color(0.12, 0.46, 0.72, 1.0))
    assembly.add(build_sensor_proxy(), name="C12880MA_dimensional_proxy", color=cq.Color(0.08, 0.09, 0.11, 1.0))
    assembly.add(build_retainer(), name="printed_rear_retainer", color=cq.Color(0.92, 0.42, 0.12, 1.0))
    return assembly


def write_dimension_svg(path: Path) -> None:
    p = PARAMS
    width = 1500
    height = 920
    side_origin_x = 120
    side_origin_y = 420
    side_scale = 18
    face_origin_x = 1050
    face_origin_y = 310
    face_scale = 12

    def sx(value: float) -> float:
        return side_origin_x + (value + 11.5) * side_scale

    def sz(value: float) -> float:
        return side_origin_y - value * side_scale

    def fy(value: float) -> float:
        return face_origin_x + value * face_scale

    def fz(value: float) -> float:
        return face_origin_y - value * face_scale

    front_x = p["flange_front_x_mm"]
    rear_x = p["flange_rear_x_mm"]
    pilot_x = front_x - p["pilot_length_mm"]
    sensor_x = sensor_face_x()
    cap_x = retainer_front_x()
    retainer_end = cap_x + p["retainer_thickness_mm"]

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7fafc"/>',
        '<text x="70" y="55" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#14213d">C12880MA 25 mm pilot holder - dimensional intent</text>',
        '<text x="70" y="91" font-family="Arial, sans-serif" font-size="16" fill="#475569">Optical axis runs left to right. The pilot is smooth and is not a 1-32 thread.</text>',
        '<text x="80" y="130" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#1e293b">Side view</text>',
        f'<rect x="{sx(pilot_x)}" y="{sz(p["pilot_diameter_mm"] / 2)}" width="{p["pilot_length_mm"] * side_scale}" height="{p["pilot_diameter_mm"] * side_scale}" fill="#7dd3fc" stroke="#0369a1" stroke-width="3"/>',
        f'<rect x="{sx(front_x)}" y="{sz(p["flange_height_mm"] / 2)}" width="{(rear_x-front_x) * side_scale}" height="{p["flange_height_mm"] * side_scale}" rx="8" fill="#38bdf8" stroke="#0369a1" stroke-width="3"/>',
        f'<rect x="{sx(sensor_x)}" y="{sz(p["official_sensor_width_mm"] / 2)}" width="{p["official_sensor_thickness_mm"] * side_scale}" height="{p["official_sensor_width_mm"] * side_scale}" fill="#334155" stroke="#0f172a" stroke-width="3"/>',
        f'<rect x="{sx(cap_x)}" y="{sz(p["retainer_height_mm"] / 2)}" width="{p["retainer_thickness_mm"] * side_scale}" height="{p["retainer_height_mm"] * side_scale}" fill="#fb923c" stroke="#c2410c" stroke-width="3"/>',
        f'<line x1="{sx(pilot_x)-20}" y1="{sz(0)}" x2="{sx(retainer_end)+35}" y2="{sz(0)}" stroke="#ef4444" stroke-width="2" stroke-dasharray="10 7"/>',
        f'<text x="{sx(pilot_x)}" y="158" font-family="Arial" font-size="15" fill="#075985">external pilot D25.0 x 5.0</text>',
        f'<text x="{sx(sensor_x)+15}" y="{sz(-8.7)}" font-family="Arial" font-size="15" fill="#334155">C12880MA 20.12 x 12.5 x 10.12</text>',
        f'<text x="{sx(cap_x)-45}" y="183" font-family="Arial" font-size="15" fill="#9a3412">lead-window retainer</text>',
        '<text x="920" y="125" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#1e293b">Pilot/front face</text>',
        f'<rect x="{fy(-p["flange_width_mm"]/2)}" y="{fz(p["flange_height_mm"]/2)}" width="{p["flange_width_mm"]*face_scale}" height="{p["flange_height_mm"]*face_scale}" rx="24" fill="#38bdf8" stroke="#0369a1" stroke-width="3"/>',
        f'<circle cx="{fy(0)}" cy="{fz(0)}" r="{p["pilot_diameter_mm"]/2*face_scale}" fill="#bae6fd" stroke="#0369a1" stroke-width="3"/>',
        f'<circle cx="{fy(0)}" cy="{fz(0)}" r="{p["pilot_bore_diameter_mm"]/2*face_scale}" fill="#f8fafc" stroke="#64748b" stroke-width="2"/>',
    ]
    for y, z in screw_points():
        lines.append(
            f'<circle cx="{fy(y)}" cy="{fz(z)}" r="{p["retainer_m2p5_clearance_diameter_mm"]/2*face_scale}" fill="#fed7aa" stroke="#c2410c" stroke-width="2"/>'
        )
    table_x = 75
    table_y = 735
    notes = [
        "Sensor locating pocket: 20.52 x 12.90 mm (0.20 mm clearance per side)",
        "Final sensor-side aperture: D5.0 mm; official entrance opening: D3.2 mm",
        "Slit: 0.05 x 0.5 mm; package center shifted -0.5 mm so slit meets pilot axis",
        "Retainer: 32 x 24 x 2.8 mm with 18 x 9.5 mm lead window",
        "Four M2.5 positions: Y +/-13.5 mm, Z +/-9.5 mm",
        "Print in insulating polymer; do not electrically short the conductive sensor case",
    ]
    lines.append(f'<text x="{table_x}" y="{table_y-35}" font-family="Arial" font-size="20" font-weight="700" fill="#1e293b">Critical dimensions and constraints</text>')
    for index, note in enumerate(notes):
        lines.append(f'<text x="{table_x}" y="{table_y + index*31}" font-family="Arial" font-size="16" fill="#334155">- {note}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_dimension_outputs(svg_path: Path, png_path: Path, pdf_path: Path) -> None:
    if cairosvg is not None:
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=2100)
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
        return

    inkscape = shutil.which("inkscape")
    if not inkscape:
        candidate = Path(r"C:\Program Files\Inkscape\bin\inkscape.exe")
        if candidate.is_file():
            inkscape = str(candidate)
    if inkscape:
        subprocess.run(
            [inkscape, str(svg_path), "--export-type=png", f"--export-filename={png_path}", "--export-width=2100"],
            check=True,
        )
        subprocess.run(
            [inkscape, str(svg_path), "--export-type=pdf", f"--export-filename={pdf_path}"],
            check=True,
        )
        return

    edge = shutil.which("msedge")
    if not edge:
        for candidate in (
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ):
            if candidate.is_file():
                edge = str(candidate)
                break
    if not edge:
        print("warning: CairoSVG, Inkscape, and Edge are unavailable; keeping the SVG only")
        return
    with tempfile.TemporaryDirectory(prefix="c12880_edge_render_") as profile:
        common = [edge, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}"]
        subprocess.run(
            common + [f"--screenshot={png_path}", "--window-size=2100,1288", svg_path.resolve().as_uri()],
            check=True,
        )
        subprocess.run(
            common + [f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", svg_path.resolve().as_uri()],
            check=True,
        )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    body = build_body()
    retainer = build_retainer()
    sensor = build_sensor_proxy()
    assembly = build_assembly()

    paths = {
        "body_step": ARTIFACT_DIR / f"{STEM}_body.step",
        "body_stl": ARTIFACT_DIR / f"{STEM}_body.stl",
        "retainer_step": ARTIFACT_DIR / f"{STEM}_retainer.step",
        "retainer_stl": ARTIFACT_DIR / f"{STEM}_retainer.stl",
        "sensor_proxy_step": ARTIFACT_DIR / f"{STEM}_sensor_proxy.step",
        "sensor_proxy_stl": ARTIFACT_DIR / f"{STEM}_sensor_proxy.stl",
        "assembly_step": ARTIFACT_DIR / f"{STEM}_assembly.step",
        "assembly_stl": ARTIFACT_DIR / f"{STEM}_assembly.stl",
        "dimension_svg": ARTIFACT_DIR / f"{STEM}_dimension_sketch.svg",
        "dimension_png": ARTIFACT_DIR / f"{STEM}_dimension_sketch.png",
        "dimension_pdf": ARTIFACT_DIR / f"{STEM}_dimension_sketch.pdf",
    }

    cq.exporters.export(body, str(paths["body_step"]))
    cq.exporters.export(body, str(paths["body_stl"]), tolerance=0.03, angularTolerance=0.08)
    cq.exporters.export(retainer, str(paths["retainer_step"]))
    cq.exporters.export(retainer, str(paths["retainer_stl"]), tolerance=0.03, angularTolerance=0.08)
    cq.exporters.export(sensor, str(paths["sensor_proxy_step"]))
    cq.exporters.export(sensor, str(paths["sensor_proxy_stl"]), tolerance=0.03, angularTolerance=0.08)
    compound = assembly.toCompound()
    cq.exporters.export(compound, str(paths["assembly_step"]))
    cq.exporters.export(compound, str(paths["assembly_stl"]), tolerance=0.03, angularTolerance=0.08)

    write_dimension_svg(paths["dimension_svg"])
    convert_dimension_outputs(
        paths["dimension_svg"],
        paths["dimension_png"],
        paths["dimension_pdf"],
    )

    outputs = {name: str(path.resolve().relative_to(ROOT)) for name, path in paths.items()}
    manifest = {
        "parameters": PARAMS,
        "sources": {
            "official_product_page": "https://www.hamamatsu.com/us/en/product/optical-sensors/spectrometers/mini-spectrometer/C12880MA.html",
            "official_datasheet": "https://hub.hamamatsu.com/content/dam/hamamatsu-photonics/sites/documents/99_SALES_LIBRARY/ssd/c12880ma_c16767ma_kacc1226e.pdf",
            "vendor_archive_observation": (
                "The supplied CCD3D.stp models the controller PCB and connectors, not the separate C12880MA optical head."
            ),
        },
        "outputs": outputs,
    }
    (ARTIFACT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
