#!/usr/bin/env python3
"""Compose paper-ready figures: white background, optional labels with leader lines, PNG + PDF.

Run with the CAD Python: cad/.conda/cad-python/bin/python compose_paper_figure_labels.py [--design-dir DIR]
Inputs: artifacts/paper_figure/<fig>_transparent.png and <fig>_labels.json (from the Blender script).
Outputs: <fig>.png (white), <fig>_labelled.png, <fig>_labelled.pdf, <fig>_labelled.svg
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

LABELS = {
    "holder": "EVK5 holder (moved onto light path)",
    "grating": "Diffraction grating",
    "sensor_board": "Sensor board (EBS)",
    "light_path": "Light path",
    "upper_shelf_window": "Shelf window",
    "incubator": "Incubator",
}
# per figure: which labels, and where to put the text (fraction of width/height, from top-left)
# value: (text x fraction, text y fraction[, anchor key]) ; anchor defaults to the label key
FIGS = {
    "figA_incubator_overview": {"holder": (0.82, 0.80, "holder_top"), "grating": (0.82, 0.55, "grating_edge"), "sensor_board": (0.16, 0.86, "sensor_board_left"), "light_path": (0.64, 0.12, "light_path_high"), "incubator": (0.12, 0.30)},
    "figB_optical_stack": {"holder": (0.80, 0.80, "holder_top"), "grating": (0.20, 0.22, "grating_edge"), "sensor_board": (0.14, 0.72, "sensor_board_left"), "light_path": (0.64, 0.08, "light_path_low"), "upper_shelf_window": (0.84, 0.38, "upper_shelf_window_right")},
    "figC_holder_under_grating_closeup": {"holder": (0.80, 0.84, "holder_top"), "grating": (0.18, 0.18, "grating_edge"), "sensor_board": (0.14, 0.86, "sensor_board_left"), "light_path": (0.64, 0.07, "light_path_low")},
    "figD_top_view_centred": {"holder": (0.80, 0.86, "holder_top"), "sensor_board": (0.16, 0.12, "sensor_board_left"), "light_path": (0.64, 0.10, "light_path_low")},
    "figE_section_through_light_path": {"holder": (0.82, 0.60, "holder_top"), "grating": (0.20, 0.34, "grating_edge"), "sensor_board": (0.16, 0.76, "sensor_board_left"), "light_path": (0.62, 0.08, "light_path_low"), "upper_shelf_window": (0.82, 0.44, "upper_shelf_window_right")},
}


def white_version(src: Path, dst: Path) -> Image.Image:
    im = Image.open(src).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, im).convert("RGB")
    out.save(dst, optimize=True)
    return out


def labelled(im: Image.Image, anchors: dict, layout: dict, stem: Path, dpi: int = 300) -> None:
    w, h = im.size
    fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(im)
    ax.set_axis_off()
    for key, spec in layout.items():
        fx, fy = spec[0], spec[1]
        akey = spec[2] if len(spec) > 2 else key
        if akey not in anchors:
            continue
        ax_px = anchors[akey]["x_px"]
        ay_px = anchors[akey]["y_px"]
        if not (0 <= ax_px <= w and 0 <= ay_px <= h):
            continue
        tx, ty = fx * w, fy * h
        ax.annotate(LABELS[key], xy=(ax_px, ay_px), xytext=(tx, ty), fontsize=7, ha="center", va="center", color="#111111",
                    bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#444444", lw=0.5),
                    arrowprops=dict(arrowstyle="-", color="#333333", lw=0.7, shrinkA=0, shrinkB=2))
    for ext in ("png", "pdf", "svg"):
        fig.savefig(stem.with_suffix(f".{ext}"), dpi=dpi)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design-dir", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    out = args.design_dir / "artifacts" / "paper_figure"
    for name, layout in FIGS.items():
        src = out / f"{name}_transparent.png"
        if not src.exists():
            print("missing", src)
            continue
        im = white_version(src, out / f"{name}.png")
        anchors = json.loads((out / f"{name}_labels.json").read_text())
        labelled(im, anchors, layout, out / f"{name}_labelled")
        print("composed", name)


if __name__ == "__main__":
    main()
