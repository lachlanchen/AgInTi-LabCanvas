"""Generate STEP envelope files and support drawings for the reflector assembly."""

from __future__ import annotations

from pathlib import Path
import subprocess

import cadquery as cq
import ezdxf


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"

TUBE_TOTAL = 50.0
THREAD_LEN = 20.0
BODY_LEN = 10.0
BODY_D = 26.0
MALE_D = 24.4
BORE_D = 20.0
AXIS_Z = 13.0

WALL = 3.0
INNER = 20.0
HOLDER_SOCKET = 22.0
HOLDER_BOX_X = 23.0
HOLDER_Y = 26.0
HOLDER_Z = 23.0
SOCKET_OD = 32.0
FEMALE_MINOR = 23.6
ASSEMBLY_HOLDER_X = TUBE_TOTAL - THREAD_LEN


def x_cylinder(d: float, length: float, x0: float) -> cq.Workplane:
    return cq.Workplane("YZ").workplane(offset=x0).center(0, AXIS_Z).circle(d / 2).extrude(length)


def box(x0: float, y0: float, z0: float, dx: float, dy: float, dz: float) -> cq.Workplane:
    return cq.Workplane("XY").box(dx, dy, dz, centered=(False, False, False)).translate((x0, y0, z0))


def centered_y_box(x0: float, z0: float, dx: float, dy: float, dz: float) -> cq.Workplane:
    return cq.Workplane("XY").box(dx, dy, dz, centered=(False, True, False)).translate((x0, 0, z0))


def tube_envelope() -> cq.Workplane:
    left = x_cylinder(MALE_D, THREAD_LEN, 0)
    body = x_cylinder(BODY_D, BODY_LEN, THREAD_LEN)
    right = x_cylinder(MALE_D, THREAD_LEN, THREAD_LEN + BODY_LEN)
    tube = left.union(body).union(right)
    return tube.cut(x_cylinder(BORE_D, TUBE_TOTAL + 2, -1))


def holder_envelope(x0: float = 0) -> cq.Workplane:
    socket_left = x0
    box_left = x0 + HOLDER_SOCKET
    bottom = centered_y_box(box_left, 0, HOLDER_BOX_X, HOLDER_Y, WALL)
    side_a = box(box_left, -HOLDER_Y / 2, WALL, HOLDER_BOX_X, WALL, INNER)
    side_b = box(box_left, HOLDER_Y / 2 - WALL, WALL, HOLDER_BOX_X, WALL, INNER)
    right = box(box_left + INNER, -HOLDER_Y / 2, WALL, WALL, HOLDER_Y, INNER)

    socket = x_cylinder(SOCKET_OD, HOLDER_SOCKET, socket_left)
    clip = box(socket_left - 0.1, -SOCKET_OD / 2 - 0.5, 0, HOLDER_SOCKET + 0.2, SOCKET_OD + 1, SOCKET_OD)
    socket = socket.intersect(clip)
    reinforce = centered_y_box(socket_left, 0, HOLDER_SOCKET + WALL, HOLDER_Y, WALL)

    holder = bottom.union(side_a).union(side_b).union(right).union(socket).union(reinforce)
    return holder.cut(x_cylinder(FEMALE_MINOR, HOLDER_SOCKET + 1, socket_left - 0.5))


def export_steps() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tube = tube_envelope()
    holder = holder_envelope(0)
    cq.exporters.export(tube, str(ARTIFACTS / "male_male_cmount_tube_envelope.step"))
    cq.exporters.export(holder, str(ARTIFACTS / "top_open_reflector_holder_envelope.step"))

    assembly = cq.Assembly(name="threaded_reflector_assembly")
    assembly.add(tube, name="male_male_cmount_tube")
    assembly.add(holder_envelope(ASSEMBLY_HOLDER_X), name="top_open_reflector_holder")
    assembly.save(str(ARTIFACTS / "threaded_reflector_assembly_envelope.step"))


def svg_header(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#111827"/></marker></defs>',
    ]


def line(x1, y1, x2, y2, stroke="#111827", width=2, dash=None) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>'


def rect(x, y, w, h, fill, stroke="#111827", width=2, dash=None) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{dash_attr}/>'


def text(x, y, value, size=16, fill="#111827") -> str:
    return f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" fill="{fill}">{value}</text>'


def dim(x1, y1, x2, y2, label, tx, ty) -> list[str]:
    return [
        line(x1, y1, x2, y2, width=1.6),
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#111827" stroke-width="1.6" marker-start="url(#arrow)" marker-end="url(#arrow)"/>',
        text(tx, ty, label, 14),
    ]


def write_side_svg() -> Path:
    scale = 8
    x0 = 60
    z_base = 270
    tube_y = z_base - 26 * scale
    holder_x = x0 + ASSEMBLY_HOLDER_X * scale
    holder_box_x = holder_x + HOLDER_SOCKET * scale
    out = svg_header(900, 380)
    out += [
        text(60, 36, "Side section: 50 mm male-male C-mount tube into top-open reflector holder", 18),
        line(45, z_base, 840, z_base, "#94a3b8", 1),
        rect(x0, tube_y + 0.8 * scale, THREAD_LEN * scale, 24.4 * scale, "#bfdbfe", width=2),
        rect(x0 + THREAD_LEN * scale, z_base - 26 * scale, BODY_LEN * scale, 26 * scale, "#93c5fd", width=2),
        rect(x0 + (THREAD_LEN + BODY_LEN) * scale, tube_y + 0.8 * scale, THREAD_LEN * scale, 24.4 * scale, "#bfdbfe", width=2),
        rect(holder_x, z_base - 29 * scale, HOLDER_SOCKET * scale, 29 * scale, "#bbf7d0", width=2),
        rect(holder_box_x, z_base - HOLDER_Z * scale, HOLDER_BOX_X * scale, HOLDER_Z * scale, "#dcfce7", width=2),
        rect(holder_box_x, z_base - (WALL + INNER) * scale, INNER * scale, INNER * scale, "#f8fafc", "#16a34a", 2, "7 6"),
        rect(holder_box_x + INNER * scale, z_base - HOLDER_Z * scale, WALL * scale, HOLDER_Z * scale, "#86efac", width=2),
        line(x0, z_base - AXIS_Z * scale, 820, z_base - AXIS_Z * scale, "#ef4444", 1.5, "8 6"),
        text(x0 + 16, tube_y + 34, "left 20 mm thread", 13, "#1e40af"),
        text(x0 + 176, tube_y + 34, "body 10", 12, "#1e40af"),
        text(x0 + 266, tube_y + 34, "right 20 mm thread", 13, "#1e40af"),
        text(holder_box_x + 14, z_base - 190, "20 x 20 x 20 mm reflector pocket, top open", 13, "#166534"),
    ]
    out += dim(x0, z_base + 28, x0 + TUBE_TOTAL * scale, z_base + 28, "tube total 50 mm", x0 + 150, z_base + 52)
    out += dim(x0, z_base + 58, x0 + THREAD_LEN * scale, z_base + 58, "20 mm", x0 + 58, z_base + 82)
    out += dim(x0 + (THREAD_LEN + BODY_LEN) * scale, z_base + 58, x0 + TUBE_TOTAL * scale, z_base + 58, "20 mm", x0 + 292, z_base + 82)
    out.append("</svg>")
    path = ARTIFACTS / "assembly_side_section.svg"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def write_top_svg() -> Path:
    scale = 8
    x0 = 60
    y0 = 190
    holder_x = x0 + ASSEMBLY_HOLDER_X * scale
    holder_box_x = holder_x + HOLDER_SOCKET * scale
    out = svg_header(900, 360)
    out += [
        text(60, 36, "Top view: holder is top-open and left-open through the threaded socket", 18),
        rect(x0, y0 - 12.2 * scale, THREAD_LEN * scale, 24.4 * scale, "#bfdbfe"),
        rect(x0 + THREAD_LEN * scale, y0 - 13 * scale, BODY_LEN * scale, 26 * scale, "#93c5fd"),
        rect(x0 + (THREAD_LEN + BODY_LEN) * scale, y0 - 12.2 * scale, THREAD_LEN * scale, 24.4 * scale, "#bfdbfe"),
        rect(holder_x, y0 - 16 * scale, HOLDER_SOCKET * scale, 32 * scale, "#bbf7d0"),
        rect(holder_box_x, y0 - 13 * scale, HOLDER_BOX_X * scale, 26 * scale, "#dcfce7"),
        rect(holder_box_x, y0 - 10 * scale, INNER * scale, 20 * scale, "#f8fafc", "#16a34a", 2, "7 6"),
        rect(holder_box_x + INNER * scale, y0 - 13 * scale, WALL * scale, 26 * scale, "#86efac"),
        line(x0, y0, 830, y0, "#ef4444", 1.5, "8 6"),
        text(holder_box_x + 14, y0 - 96, "left side opens to tube", 13, "#166534"),
        text(holder_box_x + 14, y0 + 116, "top is open; no lid modeled", 13, "#166534"),
    ]
    out += dim(holder_box_x, y0 + 134, holder_box_x + INNER * scale, y0 + 134, "inner 20 mm", holder_box_x + 45, y0 + 158)
    out += dim(holder_x, y0 - 136, holder_x + HOLDER_SOCKET * scale, y0 - 136, "female socket 22 mm", holder_x + 35, y0 - 148)
    out.append("</svg>")
    path = ARTIFACTS / "assembly_top_view.svg"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def write_dxf() -> Path:
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, -13), (50, -13), (50, 13), (0, 13), (0, -13)], close=True)
    msp.add_line((20, -13), (20, 13))
    msp.add_line((30, -13), (30, 13))
    msp.add_lwpolyline([(30, -16), (52, -16), (52, 16), (30, 16), (30, -16)], close=True)
    msp.add_lwpolyline([(52, -13), (75, -13), (75, 13), (52, 13), (52, -13)], close=True)
    msp.add_lwpolyline([(52, -10), (72, -10), (72, 10), (52, 10), (52, -10)], close=True)
    msp.add_text("Top view, units mm: tube 50 mm, threads 20 mm each, holder pocket 20x20", height=2.5).set_placement((0, 25))
    path = ARTIFACTS / "threaded_reflector_assembly_top_sketch.dxf"
    doc.saveas(path)
    return path


def svg_to_pdf_and_png(svg: Path) -> None:
    pdf = svg.with_suffix(".pdf")
    png = svg.with_suffix(".png")
    try:
        subprocess.run(["convert", str(svg), str(pdf)], check=True)
    except Exception as exc:
        print(f"PDF conversion skipped for {svg.name}: {exc}")
    try:
        subprocess.run(["convert", str(svg), str(png)], check=True)
    except Exception as exc:
        print(f"PNG conversion skipped for {svg.name}: {exc}")


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    export_steps()
    svgs = [write_side_svg(), write_top_svg()]
    write_dxf()
    for svg in svgs:
        svg_to_pdf_and_png(svg)


if __name__ == "__main__":
    main()
