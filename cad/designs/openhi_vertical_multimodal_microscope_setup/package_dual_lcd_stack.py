#!/usr/bin/env python3
"""Compose the editable-label overview and checksum-sync the revised run."""

import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageChops

from build_dual_lcd_stack import DESIGN, ROOT, digest

NUTSTORE = Path("/home/lachlan/Nutstore Files/Projects/LabCanvas")


def main():
    latest = json.loads((DESIGN / "artifacts/dual_lcd_stack_latest.json").read_text())
    run = ROOT / latest["run_dir"]
    data = json.loads((run / "manifest.json").read_text())
    records = json.loads((run / "renders/camera_validation.json").read_text())
    if len(records) != 7:
        raise RuntimeError("Missing overview or detail renders")
    for row in records:
        b = row["projected_bounds"]
        if not (0.079 <= b["xmin"] < b["xmax"] <= 0.921 and 0.079 <= b["ymin"] < b["ymax"] <= 0.921):
            raise RuntimeError("Camera safety margin failed")
    fig_dir = run / "figures"
    fig_dir.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "pdf.fonttype": 42})
    fig = plt.figure(figsize=(12, 8.8), facecolor="white")
    panels = [
        ("a", "Single 4f relay", "single_4f_updated_stack_overview.png", (0.02, 0.16, 0.18, 0.77)),
        ("b", "Horizontal cascade", "dual_4f_updated_stack_overview.png", (0.21, 0.16, 0.32, 0.77)),
        ("c", "Vertical cascade", "dual_4f_vertical_updated_stack_overview.png", (0.54, 0.16, 0.18, 0.77)),
        ("d", "Shared lower optical stack", "updated_lower_optical_stack_detail.png", (0.73, 0.41, 0.25, 0.52)),
    ]
    panel_crops = []
    for letter, title, image_path, position in panels:
        ax = fig.add_axes(position)
        image = Image.open(run / "renders" / image_path).convert("RGB")
        difference = ImageChops.difference(image, Image.new("RGB", image.size, "white"))
        bounds = difference.convert("L").point(lambda v: 255 if v > 10 else 0).getbbox()
        if not bounds:
            raise RuntimeError(f"Blank publication render: {image_path}")
        x0, y0, x1, y1 = bounds
        px, py = max(8, int((x1 - x0) * 0.08)), max(8, int((y1 - y0) * 0.08))
        crop = (max(0, x0 - px), max(0, y0 - py), min(image.width, x1 + px), min(image.height, y1 + py))
        ax.imshow(image.crop(crop))
        ax.set_axis_off()
        ax.set_anchor("N")
        ax.set_title(f"{letter}  {title}", fontsize=10, loc="left", pad=8, weight="bold")
        panel_crops.append({"panel": letter, "source_png": image_path, "white_margin_crop_px": crop,
                            "nonwhite_content_bounds_px": bounds, "apparatus_geometry_changed": False})
    fig.text(0.74, 0.24, "Bottom to top\nDock / lamp + PCB\nGT090101 / LCD\nSpecimen holder\nLCD / GT090101\nMicroscope", fontsize=9, linespacing=1.55, va="bottom")
    fig.text(0.025, 0.055,
             "Revised fixed-polarizer apparatus. Two GT090101 mounts and two QYH1123 seats bracket the specimen holder.\n"
             "Accepted OpenHI relay geometry is reused in all layouts. Blue: frame camera; red: event camera; green PCB: C12880MA.\n"
             "Independent view scales. Panel d hides the upper apparatus only. Axial gaps are layout assumptions; detector housings are proxies.",
             fontsize=8.5, linespacing=1.5, va="bottom")
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(fig_dir / ("Figure_updated_dual_LCD_optical_setup." + suffix), dpi=250, facecolor="white")
    plt.close(fig)
    (fig_dir / "panel_layout.json").write_text(json.dumps(panel_crops, indent=2) + "\n")
    (run / "README.md").write_text(
        "# Updated dual-LCD / dual-GT090101 OpenHI apparatus\n\n"
        "Bottom to top: dock, lamp/PCB, GT090101, lower LCD holder, sample holder/dish/cap, upper LCD holder, GT090101, microscope, relay(s), detectors.\n\n"
        "Three assembly STEP files provide single-relay, horizontal-cascade and vertical-cascade layouts. All accepted upper components are moved together by +22 mm; their internal geometry and relative datums are unchanged. Both LCD seats use the accepted 45-degree through-pin-clearance holder.\n\n"
        "The photograph fixes order and orientation, not exact Z distances. Six imported 5 mm spacer layers fill the modeled gaps. See manifest.json for each layer, placement, source checksum, STEP round-trip and pin-intersection result. Focus, working distance and polarizer settings require experiment-specific adjustment. This is not a manufacturing or historical-acquisition claim.\n\n"
        "Use renders/*overview.png for complete apparatus views, renders/updated_lower_optical_stack_detail.png for the shared lower train, and figures/Figure_updated_dual_LCD_optical_setup.pdf or .svg for editable-label panel layout. All optical bodies remain separate in STEP; reference camera housings must not be printed as devices.\n")
    for file in (DESIGN / "build_dual_lcd_stack.py", DESIGN / "render_dual_lcd_stack.py",
                 Path(__file__), DESIGN / "README.md", ROOT / "tests/test_openhi_dual_lcd_stack.py"):
        shutil.copy2(file, run / "source" / file.name)
    target = NUTSTORE / DESIGN.name / run.name
    checksums = {}
    for file in sorted(run.rglob("*")):
        if not file.is_file() or file.suffix == ".blend1" or file.name == "sync_manifest.json":
            continue
        relative = file.relative_to(run)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, output)
        checksums[str(relative)] = digest(file)
        if digest(output) != checksums[str(relative)]:
            raise RuntimeError(f"Nutstore checksum mismatch: {relative}")
    for variant, row in data["variants"].items():
        source = run / row["assembly_step"]
        name = f"USE_THIS_openhi_dual_lcd_stack_{variant}.step"
        shutil.copy2(source, DESIGN / name)
        shutil.copy2(source, NUTSTORE / name)
    (run / "sync_manifest.json").write_text(json.dumps(checksums, indent=2) + "\n")
    shutil.copy2(run / "sync_manifest.json", target / "sync_manifest.json")
    print(json.dumps({"nutstore": str(target), "verified_files": len(checksums), "views": len(records)}, indent=2))


if __name__ == "__main__":
    main()
