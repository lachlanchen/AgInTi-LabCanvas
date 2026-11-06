#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare readable previews, a short guide and checksum-verified Nutstore handoff."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as PDFImage
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

DESIGN = Path(__file__).resolve().parent
ROOT = DESIGN.parents[2]
NUTSTORE = Path.home() / "Nutstore Files/Projects/LabCanvas" / DESIGN.name


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flatten(path):
    original = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", original.size, "white")
    bg.alpha_composite(original)
    bg.convert("RGB").save(path)


def contacts(run, data):
    names = {**data["print_validation"], **data["fit_coupons"]}
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    rows = (len(names) + 3) // 4
    sheet = Image.new("RGB", (1680, rows * 390 + 70), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (30, 20),
        "Individual print files - supplied orientations, each part printed separately",
        fill="#20282c",
        font=font,
    )
    for i, (name, row) in enumerate(names.items()):
        picture = Image.open(run / Path(row["stem"]).parent / "print_orientation.png")
        picture.thumbnail((410, 335))
        x, y = (i % 4) * 420, (i // 4) * 390 + 65
        sheet.paste(picture, (x + (420 - picture.width) // 2, y))
        label = name.replace("bearing_", "brg_").replace("polarizer_", "optic_")
        draw.text((x + 12, y + 340), label, fill="#20282c", font=font)
    sheet.save(run / "renders/individual_print_layouts.png")


def pdf_guide(run, data):
    parameters = data["parameters"]
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13
    styles["Title"].fontSize = 21
    story = []

    def p(text, style="BodyText"):
        story.append(Paragraph(text, styles[style]))
        story.append(Spacer(1, 3 * mm))

    def table(rows):
        content = [
            [Paragraph(escape(str(x)), styles["BodyText"]) for x in row] for row in rows
        ]
        item = Table(content, colWidths=[68 * mm, 102 * mm], hAlign="LEFT")
        item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eff0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(item)

    p("OpenHI hollow rotary stage", "Title")
    p("Exact saved NEMA 17 motor / belt-drive mechanical prototype", "Heading2")
    story.append(
        PDFImage(
            str(run / "renders/assembled_overview.png"), width=170 * mm, height=138 * mm
        )
    )
    p(
        "A common carrier holds the bearing and motor. A separate footed stand sets the table height. The center stays open for the optical path. CAD-checked, but not physically tested; start with the fit coupons."
    )
    table(
        [
            ["Feature", "Dimension / meaning"],
            [
                "Motor source",
                "OpenHI named body: 42 x 42 x 40 mm; 31 mm hole square; 5 x 22 mm shaft",
            ],
            [
                "Drive",
                f"20T to 120T GT2; {parameters['belt_length_mm']:g} mm closed belt, "
                f"{parameters['belt_width_mm']:g} mm wide; 6:1 reduction",
            ],
            [
                "Optical opening",
                "30 mm bare stage; 24 mm with the removable 25.4 mm polarizer insert",
            ],
            [
                "Output interface",
                "Four M3 nuts on a 30 mm square; maximum screw insertion 6 mm",
            ],
        ]
    )
    story.append(PageBreak())
    p("Bearing retention and assembly", "Title")
    story.append(
        PDFImage(
            str(run / "renders/exploded_assembly.png"), width=92 * mm, height=135 * mm
        )
    )
    p(
        "Explanatory exploded view: offsets are for visibility, not assembly spacings. Bearing internals and belt backing are reference envelopes, not supplier-complete CAD."
    )
    p(
        "The inner bearing race is fixed by the small three-screw ring; the outer race turns inside the printed cup. Its cover clamps only the outer race. Keep belt tension low and verify free turning before adding a payload."
    )
    p(
        "Print the 52.0 / 52.1 / 52.2 mm bore coupons, 39.8 / 39.9 / 40.0 mm journal coupons and the GT2 tooth-fit coupon. Select a sliding fit that does not squeeze the bearing. Nominal build uses a 52.1 mm seat and 39.9 mm journal."
    )
    p(
        "The motor pulley is inverted, with its hub above the teeth. Rotate the motor 10 degrees to match the carrier holes and keep a 4 mm tool path clear of the belt. Motor screws: M3 x 6 plus 1 mm total washer thickness, giving 3 mm modeled motor engagement. Recessed heads sit 0.75 mm below the belt. Check real screw depth."
    )
    p(
        "Selected pulley: 20T, 5 mm bore, 16 mm overall height. Its individual channel, flange and hub lengths are not supplier-dimensioned; the CAD axial split is a reference. Slide the real pulley on the shaft to align the belt before locking its set screw."
    )
    story.append(PageBreak())
    p("Height, clearance and mounting", "Title")
    table(
        [
            ["Table datum", "Z in mm"],
            ["Carrier underside", "75"],
            ["Floor below cup / lowest moving cup", "78 / 79"],
            ["Motor front / bearing bottom", "80 / 81"],
            ["Main tray underside", "85"],
            ["Bearing top / belt midplane", "88 / 89.75"],
            ["Output face / polarizer insert top", "98.5 / 101.5"],
        ]
    )
    p(
        "Important: 85 mm is the tray datum, not an entirely empty space below the stage. Fixed hardware starts at Z75, outside the 30 mm optical passage."
    )
    p(
        "Fixed cage rods must stop below Z75 (preferably Z74 or lower). They cannot continue through the moving 30 mm-square interface. The old 30 mm dock's lower optical stack reaches Z79 and collides; a 25 mm dock lowers it to Z74, leaving only 1 mm. Measure the real setup. The optional 5 mm shim lifts the complete upper module to a 90 mm tray datum; use M4 x 20 bolts with 1 mm washers."
    )
    p(
        "Foot: X58..118, Y-42..42 mm relative to the optical axis. Four 6.4 mm clearance slots at X75/100 and Y+/-25 follow the 25 mm breadboard grid. Choose M6 bolt length from the actual table engagement limit. Remove ears before installing."
    )
    story.append(
        PDFImage(
            str(run / "renders/underside_access.png"), width=117 * mm, height=95 * mm
        )
    )
    story.append(PageBreak())
    p("Purchase and print checklist", "Title")
    table(
        [
            ["Buy", "Quantity / selection"],
            ["Bearing", "1 x 6808-ZZ, 40 x 52 x 7 mm"],
            [
                "Pulley and belt",
                f"1 x 20T 2GT, bore 5, height 16, for a 6 mm belt; "
                f"1 x {parameters['belt_length_mm']:g}-2GT-6 closed belt",
            ],
            [
                "Main screw sets",
                "4 x M3x6 motor; 3 x M3x12 countersunk rotor; 3 x M2x14 fixed ring; 4 x M4x16 stand",
            ],
            [
                "Nuts and washers",
                "7 x M3, 6 x M2, 4 x M4; 1 mm motor/stand washer stacks",
            ],
            ["Optional optic screws", "4 x M3x8 insert; 3 x M2x5 clip"],
            [
                "Table hardware",
                "At least 2 x M6 bolts and washers, length checked against the table",
            ],
            [
                "Drive electronics",
                "Existing controller and a suitable STEP/DIR driver; real motor current must be verified",
            ],
        ]
    )
    p(
        "Print separately: carrier, footed stand, rotor cup, rotor cap and inner-race retainer. Print the revised rotor cup upright: its underside has a 45-degree taper and only a 0.2 mm outer lip. The polarizer insert, clip and 5 mm height shim are optional. Each part has grounded STEP/STL/3MF files and a print preview."
    )
    p(
        "The printed 120T driven pulley is annular, not solid. Do not buy a solid 120T pulley. Selected retail options are recorded in source/taobao_selection.json. The bearing listing has conflicting origin/grade fields; its import and P4 claims have not been verified."
    )
    p(
        "Starting print settings: PETG, 0.2 mm layers, 5-6 walls, 40-50% infill. Small rings and teeth should be effectively solid. Local support is needed under the raised motor roof; short nut-pocket bridges remain. Remove 1 mm sacrificial tabs and support debris. Manufacturing files omit these tabs and all hardware references."
    )
    p(
        "First test: hand-turn fully; check screw tips and stationary rods; confirm belt alignment; then run slow forward/reverse moves with low current and an independent angle reference. The 0.01875-degree microstep command increment is not measured accuracy. No homing sensor, encoder, electrical wiring or firmware is supplied here."
    )
    p(
        "Full assembly order, Chinese purchase terms, source links, licensing and limitations are in README.md. This design adapts NopSCADlib's GPL-3.0-or-later GT2 groove construction; owner-supplied reference geometry retains its original rights."
    )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#566166"))
        canvas.drawString(
            20 * mm, 11 * mm, "CAD-checked prototype / physical fit testing required"
        )
        canvas.drawRightString(190 * mm, 11 * mm, str(document.page))
        canvas.restoreState()

    SimpleDocTemplate(
        str(run / "rotary_stage_build_guide.pdf"),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title="OpenHI hollow rotary stage - build guide",
    ).build(story, onFirstPage=footer, onLaterPages=footer)


def chinese_guide(run):
    for tool in ("pandoc", "xelatex"):
        if shutil.which(tool) is None:
            raise RuntimeError(
                f"Chinese tutorial needs {tool}; geometry does not need rebuilding"
            )
    source = run / "source"
    source.mkdir(exist_ok=True)
    shutil.copy2(DESIGN / "ASSEMBLY_GUIDE.zh-CN.md", run / "ASSEMBLY_GUIDE.zh-CN.md")
    shutil.copy2(DESIGN / "tutorial_zh_header.tex", source / "tutorial_zh_header.tex")
    shutil.copy2(DESIGN / "tutorial_tables.lua", source / "tutorial_tables.lua")
    tex = source / "rotary_stage_tutorial_zh.tex"
    subprocess.run(
        [
            "pandoc",
            str(run / "ASSEMBLY_GUIDE.zh-CN.md"),
            "--standalone",
            "--from=markdown+raw_tex",
            "--shift-heading-level-by=-1",
            "--metadata=lang:en-US",
            "--metadata=date:适用于 " + "-".join(run.name.split("-")[:2]) + " 机械模型",
            "--variable=documentclass:ctexart",
            "--variable=classoption:fontset=none",
            "--variable=fontsize:10pt",
            "--variable=papersize:a4",
            "--variable=geometry:margin=19mm,top=20mm,bottom=18mm",
            "--variable=mainfont:TeX Gyre Pagella",
            "--variable=monofont:DejaVu Sans Mono",
            "--include-in-header",
            str(source / "tutorial_zh_header.tex"),
            "--lua-filter",
            str(source / "tutorial_tables.lua"),
            "--resource-path",
            str(run),
            "--output",
            str(tex),
        ],
        check=True,
        cwd=run,
    )
    build = ROOT / "output/cad_reviews/rotary_stage/zh_tutorial_build"
    build.mkdir(parents=True, exist_ok=True)
    log = build / "build-output.txt"
    with log.open("w") as output:
        for _ in range(2):
            result = subprocess.run(
                [
                    "xelatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-file-line-error",
                    "-output-directory",
                    str(build),
                    str(tex),
                ],
                cwd=run,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            if result.returncode:
                raise RuntimeError(f"Chinese tutorial TeX build failed; inspect {log}")
    final_log = (build / "rotary_stage_tutorial_zh.log").read_text(errors="replace")
    if any(
        marker in final_log
        for marker in ("Overfull \\hbox", "Overfull \\vbox", "Missing character:")
    ):
        raise RuntimeError(
            f"Chinese tutorial has overflow or missing glyphs; inspect {build}"
        )
    shutil.copy2(
        build / "rotary_stage_tutorial_zh.pdf", run / "rotary_stage_tutorial_zh.pdf"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chinese-only",
        action="store_true",
        help="Add/update the Chinese tutorial without rerendering or rebuilding the English PDF",
    )
    args = parser.parse_args()
    run = ROOT / json.loads((DESIGN / "artifacts/latest.json").read_text())["run_dir"]
    data = json.loads((run / "manifest.json").read_text())
    if not args.chinese_only:
        checks = json.loads((run / "render_checks.json").read_text())
        for row in checks["renders"]:
            flatten(run / row["path"])
        contacts(run, data)
    source = run / "source"
    source.mkdir(exist_ok=True)
    for name in (
        "build_stage.py",
        "render_stage.py",
        "package_stage.py",
        "taobao_selection.json",
    ):
        shutil.copy2(DESIGN / name, source / name)
    supplier_diagram = ROOT / "output/cad_sourcing/references/qipang-size-b.png"
    if supplier_diagram.is_file():
        references = run / "references"
        references.mkdir(exist_ok=True)
        shutil.copy2(
            supplier_diagram, references / "selected_20t_pulley_dimensions.png"
        )
    for name in ("README.md", "LICENSE"):
        shutil.copy2(DESIGN / name, run / name)
    shutil.copy2(
        ROOT / "references/diy-hollow-rotary-stage-taobao-stock-2026-11-04.md",
        source / "taobao_sourcing_notes.md",
    )
    shutil.copy2(
        ROOT / "references/openhi-rotary-stage-printability-wenext-2026-11-06.md",
        source / "printability_and_wenext_notes.md",
    )
    if not args.chinese_only:
        pdf_guide(run, data)
    chinese_guide(run)
    final = DESIGN / "USE_THIS_diy_hollow_rotary_stage_85mm_assembly.step"
    shutil.copy2(run / data["assembly_step"], final)
    files = {
        str(p.relative_to(run)): digest(p)
        for p in run.rglob("*")
        if p.is_file() and p.name != "checksums.json"
    }
    (run / "checksums.json").write_text(json.dumps(files, indent=2) + "\n")
    target = NUTSTORE / run.name
    shutil.copytree(run, target, dirs_exist_ok=True)
    bad = [name for name, value in files.items() if digest(target / name) != value]
    if bad:
        raise RuntimeError(f"Nutstore copy failed: {bad}")
    shutil.copy2(final, NUTSTORE / final.name)
    for name in ("rotary_stage_tutorial_zh.pdf", "ASSEMBLY_GUIDE.zh-CN.md"):
        shutil.copy2(run / name, NUTSTORE / name)
        if digest(run / name) != digest(NUTSTORE / name):
            raise RuntimeError(f"Root tutorial copy failed: {name}")
    record = {
        "run_dir": str(run.relative_to(ROOT)),
        "nutstore_run": str(target),
        "assembly_step": str(target / data["assembly_step"]),
        "verified_files": len(files),
        "all_checksums_match": True,
        "prototype": True,
        "chinese_tutorial_pdf": str(NUTSTORE / "rotary_stage_tutorial_zh.pdf"),
    }
    (DESIGN / "artifacts/sync.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
